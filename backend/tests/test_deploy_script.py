"""운영 배포 스크립트의 마이그레이션 판정 (scripts/deploy.sh · ADR-073).

`migration_step` 이 틀리면 둘 중 하나다 — 멀쩡한 되감기를 막거나, **CI 가 시험하지 않은 코드를
새 DB 위에 올린다.** 뒤쪽이 사고라서, 막는 쪽 시험이 더 많다.

스크립트를 source 해서 함수 하나씩 부른다(source 되면 main 을 안 돈다). 판정은 git 이력을
보므로 임시 저장소를 만든다 — develop 의 first-parent 이력에 머지 커밋이 하나 있고, 거기서
리비전이 들어온다. 서버 쪽 명령(sudo · docker · runuser)은 가짜 실행 파일을 PATH 앞에 둬서,
불리면 기록하고 실패한다.

판정이 맞아도 **main 이 그 판정을 지키지 않으면** 소용없다 — 거절인데 checkout 을 하거나,
건너뛰기인데 upgrade 를 돌리는 식이다. 그래서 끝에는 main 을 통째로 돌린다: 로컬 bare 저장소를
원격으로 둔 가짜 서버 폴더에서, `sudo` 가짜가 서버 명령을 로그에 적는다.

교체 뒤 서버 안 확인(`wait_ready`)도 같은 가짜 서버로 본다 — 안 살아나면 **종료 코드 3** 이고,
deploy.yml 의 자동 롤백이 그 숫자 하나로 움직인다(ADR-078). 3 이 다른 실패에 새거나
(예상 밖 실패는 1), root → ubuntu 재실행을 지나다 사라지면(트랩) 롤백이 안 돌거나
엉뚱할 때 돈다. 그래서 둘 다 시험한다.
"""

import fcntl
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SH = ROOT / "scripts" / "deploy.sh"

# 불리면 FAKE_CALLS 에 한 줄 남기고 실패한다. source 가 서버 명령에 닿으면 이 파일이 생긴다.
FAKE = '#!/bin/sh\necho "$(basename "$0") $*" >> "$FAKE_CALLS"\nexit 99\n'
FAKES = {name: FAKE for name in ("sudo", "docker", "runuser")}

A = "aaaaaaaaaaaa"
B = "bbbbbbbbbbbb"


@pytest.fixture
def sh(tmp_path):
    """deploy.sh 의 함수를 불러 (stdout, 종료 코드) 를 준다. 쓰는 저장소는 cwd 로 고른다."""
    fake = tmp_path / "bin"
    fake.mkdir()
    for name, body in FAKES.items():
        p = fake / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    calls = tmp_path / "fake-calls.log"

    # 개발자 설정(서명 · 별칭)이 임시 저장소를 흔들지 않게 git 설정을 끊는다.
    # 훅 안에서 돌 때 물려받는 GIT_* 는 지운다.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        PATH=f"{fake}{os.pathsep}{os.environ['PATH']}",
        FAKE_CALLS=str(calls),
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@example.com",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@example.com",
    )

    def run(body: str, *args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-c", f'source "{DEPLOY_SH}"\n{body}', "bash", *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    run.env = env
    run.calls = calls
    return run


def git(env: dict, cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


@pytest.fixture
def repo(tmp_path, sh):
    """P0 → A0(리비전 a) → A1 → [side: S(리비전 b)] → M1(머지) → C. origin/develop = C.

    other 는 A1 에서 갈라진 다른 브랜치(X)다. 리비전 b 를 모른다.
    """
    path = tmp_path / "repo"
    path.mkdir()

    def g(*args: str) -> str:
        return git(sh.env, path, *args)

    def commit(name: str, files: dict[str, str]) -> str:
        for rel, text in files.items():
            f = path / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text)
        g("add", "-A")
        g("commit", "-q", "-m", name)
        return g("rev-parse", "HEAD")

    versions = "backend/alembic/versions"
    g("init", "-q", "-b", "develop")
    sha = SimpleNamespace()
    # docker-compose.yml 은 main 이 checkout 뒤에 있는지 본다(가짜 서버 시험).
    sha.p0 = commit("P0", {"README.md": "x\n", "docker-compose.yml": "services: {}\n"})
    # 두 가지 선언 꼴이 다 있다. b 의 down_revision 은 a 를 적지만 a 를 선언한 것이 아니다.
    sha.a0 = commit(
        "A0",
        {f"{versions}/20260101_0000_{A}_first.py": f"revision = '{A}'\ndown_revision = None\n"},
    )
    sha.a1 = commit("A1", {"README.md": "y\n"})
    g("switch", "-q", "-c", "side")
    sha.s = commit(
        "S",
        {
            f"{versions}/20260102_0000_{B}_second.py": (
                f'revision: str = "{B}"\ndown_revision: str | None = "{A}"\n'
            )
        },
    )
    g("switch", "-q", "develop")
    g("merge", "-q", "--no-ff", "-m", "M1", "side")
    sha.m1 = g("rev-parse", "HEAD")
    sha.c = commit("C", {"README.md": "z\n"})
    g("switch", "-q", "-c", "other", sha.a1)
    sha.x = commit("X", {"README.md": "other\n"})
    g("switch", "-q", "develop")
    g("update-ref", "refs/remotes/origin/develop", sha.c)

    def step(target: str, revs: str) -> str:
        proc = sh('migration_step "$1" "$2"', target, revs, cwd=path)
        assert proc.returncode == 0, proc.stderr  # 판정은 늘 0 으로 끝나고 글자로 답한다
        return proc.stdout.strip()

    def rev_file(tree: str, rev: str) -> str:
        proc = sh('revision_file "$1" "$2"', tree, rev, cwd=path)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout.strip()

    sha.path = path
    sha.step = step
    sha.rev_file = rev_file
    return sha


# main 이 부르는 서버 명령을 흉내 낸다. 읽는 셋은 답하고, 나머지는 FAKE_LOG 에 한 줄 적고 성공한다.
FAKE_SUDO = """#!/bin/sh
[ "$1" = -n ] && shift
case "$*" in
  true) exit 0 ;;
  *"backend python -c"*)
    [ -z "$FAKE_DB_FAIL" ] || { echo "connection refused" >&2; exit 1; }
    printf '%s\\n' "$FAKE_REV"
    exit 0 ;;
  "docker compose config --services") printf 'backend\\nfrontend\\n'; exit 0 ;;
esac
echo "$*" >> "$FAKE_LOG"
case "$*" in *"compose build"*) exit "${FAKE_BUILD_EXIT:-0}" ;; esac
"""
# 평소에는 이미 ubuntu 라서 runuser 로 내려가지 않는다. FAKE_ROOT 면 root 로 보이다가
# 가짜 runuser 가 FAKE_AS_UBUNTU 를 세워 준 뒤부터 ubuntu 로 보인다.
FAKE_ID = '#!/bin/sh\n[ -n "$FAKE_ROOT" ] && [ -z "$FAKE_AS_UBUNTU" ] && echo root || echo ubuntu\n'
# `runuser -u ubuntu -- env DEPLOY_REF=<ref> bash <복사본>` 을 받아, 복사본을 source 해서
# 진짜 main 을 돈다. 스크립트로 돌리면 DEPLOY_PATH · REPO_URL 같은 상수를 로컬 경로로 바꿀 수 없다.
FAKE_RUNUSER = """#!/bin/sh
while [ "$1" != -- ]; do shift; done
shift 2           # -- env
ref=$1            # DEPLOY_REF=<ref>
shift 2           # DEPLOY_REF=… bash
inner=$1
export FAKE_AS_UBUNTU=1
exec env "$ref" bash -c 'source "$1"
DEPLOY_PATH="$SIM_DIR"
REPO_URL="$SIM_URL"
READY_TRIES="$SIM_READY_TRIES"
READY_INTERVAL=0
LOCK_FILE="$SIM_LOCK"
LOCK_WAIT="$SIM_LOCK_WAIT"
main' bash "$inner"
"""
# 마지막 인자가 주소다. FAKE_READY · FAKE_PAGE 가 그 주소가 줄 응답 코드,
# *_RC 가 curl 의 종료 코드다. FAKE_FAIL_FIRST=N 이면 처음 N 번의 호출은 연결 실패(000, 종료 7)다.
FAKE_CURL = """#!/bin/sh
for url; do :; done
echo "$url" >> "$FAKE_CURL_LOG"
if [ -n "$FAKE_FAIL_FIRST" ]; then
  n=$(cat "$FAKE_CURL_COUNT" 2>/dev/null || echo 0)
  echo $((n + 1)) > "$FAKE_CURL_COUNT"
  [ "$n" -ge "$FAKE_FAIL_FIRST" ] || { printf 000; exit 7; }
fi
case "$url" in
  */health/ready) printf '%s' "$FAKE_READY"; exit "${FAKE_READY_RC:-0}" ;;
  *) printf '%s' "$FAKE_PAGE"; exit "${FAKE_PAGE_RC:-0}" ;;
esac
"""
# macOS 에는 flock 이 없다. 서버(Linux)의 flock(1) 과 같은 flock(2) 를 거는 가짜다.
# `flock -w <초> <fd>` 만 안다.
FAKE_FLOCK = f"""#!{sys.executable}
import fcntl, sys, time
_, _, secs, fd = sys.argv
deadline = time.monotonic() + float(secs)
while True:
    try:
        fcntl.flock(int(fd), fcntl.LOCK_EX | fcntl.LOCK_NB)
        sys.exit(0)
    except BlockingIOError:
        if time.monotonic() >= deadline:
            sys.exit(1)
        time.sleep(0.05)
"""


@pytest.fixture
def server(tmp_path, sh, repo):
    """main 을 돌려 볼 가짜 서버. 원격은 repo 를 복제한 bare 저장소이고 서버 폴더는 그 복제본이다.

    `server(at)` 은 서버가 커밋 `at` 에 서 있는 채로 시작하고, `.run(ref, rev)` 가 main 을 돌린다.
    기본은 교체 뒤 서버 안 확인이 둘 다 200 이다. `ready` · `page` 로 응답 코드를,
    `env_extra` 로 가짜 명령의 동작을 바꾼다.
    """
    bare = tmp_path / "origin.git"
    srv = tmp_path / "srv"
    log = tmp_path / "server-commands.log"
    curl_log = tmp_path / "server-curl.log"
    fake = tmp_path / "server-bin"
    fake.mkdir()
    fakes = {"sudo": FAKE_SUDO, "id": FAKE_ID, "curl": FAKE_CURL, "runuser": FAKE_RUNUSER}
    if shutil.which("flock") is None:
        fakes["flock"] = FAKE_FLOCK
    for name, body in fakes.items():
        p = fake / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    env = {**sh.env, "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}"}

    def make(at: str) -> SimpleNamespace:
        git(env, tmp_path, "clone", "-q", "--bare", str(repo.path), str(bare))
        git(env, tmp_path, "clone", "-q", str(bare), str(srv))
        git(env, srv, "checkout", "-q", "-f", "--detach", at)
        (srv / ".env").write_text("")  # 커밋하지 않는 파일. main 이 있는지 본다

        def run(
            ref: str,
            rev: str,
            *,
            db_fail: bool = False,
            ready: str = "200",
            page: str = "200",
            tries: int = 3,
            lock: Path = tmp_path / "deploy.lock",
            lock_wait: int = 5,
            as_root: bool = False,
            env_extra: dict[str, str] | None = None,
        ) -> subprocess.CompletedProcess:
            run_env = {
                **env,
                "DEPLOY_REF": ref,
                "FAKE_REV": rev,
                "FAKE_LOG": str(log),
                "FAKE_CURL_LOG": str(curl_log),
                "FAKE_CURL_COUNT": str(tmp_path / "curl-count"),
                "FAKE_READY": ready,
                "FAKE_PAGE": page,
                "SIM_DIR": str(srv),
                "SIM_URL": str(bare),
                "SIM_READY_TRIES": str(tries),
                "SIM_LOCK": str(lock),
                "SIM_LOCK_WAIT": str(lock_wait),
                **(env_extra or {}),
            }
            if db_fail:
                run_env["FAKE_DB_FAIL"] = "1"
            if as_root:
                # 스크립트 파일로 돈다(복사해 넘기려고 $0 을 읽는다).
                # 상수는 가짜 runuser 가 로컬 값으로 바꾼다
                run_env["FAKE_ROOT"] = "1"
                cmd = ["bash", str(DEPLOY_SH)]
            else:
                # DEPLOY_PATH · REPO_URL 같은 상수는 스크립트 위쪽에 있어
                # source 한 뒤에 로컬 값으로 바꾼다
                body = (
                    f'source "{DEPLOY_SH}"\n'
                    'DEPLOY_PATH="$SIM_DIR"\nREPO_URL="$SIM_URL"\n'
                    'READY_TRIES="$SIM_READY_TRIES"\nREADY_INTERVAL=0\n'
                    'LOCK_FILE="$SIM_LOCK"\nLOCK_WAIT="$SIM_LOCK_WAIT"\n'
                    "main"
                )
                cmd = ["bash", "-c", body]
            return subprocess.run(
                cmd,
                cwd=tmp_path,
                env=run_env,
                capture_output=True,
                text=True,
                timeout=120,
            )

        return SimpleNamespace(
            run=run,
            head=lambda: git(env, srv, "rev-parse", "HEAD"),
            log=lambda: log.read_text().splitlines() if log.exists() else [],
            curls=lambda: curl_log.read_text().splitlines() if curl_log.exists() else [],
        )

    return make


@pytest.mark.parametrize("target", ["c", "m1", "s"])
def test_올릴_코드가_리비전을_알면_평소대로_올린다(repo, target):
    # 평소 배포 · 같은 SHA 를 다시 올릴 때 · 롤백했다가 다시 앞으로 갈 때
    assert repo.step(getattr(repo, target), B) == "upgrade"


def test_더_앞선_코드에_옛_리비전이_있어도_올린다(repo):
    assert repo.step(repo.c, A) == "upgrade"


def test_리비전을_들여온_머지_직전_커밋으로는_건너뛴다(repo):
    assert repo.step(repo.a1, B) == f"skip {B} {repo.m1} {repo.a1}"


@pytest.mark.parametrize("target", ["a0", "p0", "x"])
def test_직전_커밋이_아니면_checkout_전에_거절한다(repo, target):
    # 한 칸보다 멀리(a0 · p0) 또는 다른 갈래(x). CI 가 새 스키마에서 시험한 코드는 a1 하나뿐이다.
    out = repo.step(getattr(repo, target), B)

    assert out.startswith("reject ")
    assert "\n" not in out
    # 어느 리비전이 · 어느 머지에서 · 어디로만 되는지 이유에 있다
    assert B in out and repo.m1[:8] in out and repo.a1[:8] in out


@pytest.mark.parametrize(
    "revs",
    [
        "",
        "\n\n",
        f"{A}\n{B}",  # 갈래가 둘이다
        "not-a-revision",
        A.upper(),
        A[:-1],  # 11자리
        f"{A} ",
        f"{A}\r",
    ],
)
def test_리비전을_하나로_못_읽으면_거절한다(repo, revs):
    # 올릴 코드는 리비전을 아는 c 다 — 거절 이유가 코드가 아니라 리비전 글이라는 것을 가른다
    assert repo.step(repo.c, revs).startswith("reject ")


def test_빈_줄이_섞여도_리비전이_하나면_읽는다(repo):
    assert repo.step(repo.c, f"\n{B}\n\n") == "upgrade"


def test_develop_도_모르는_리비전이면_거절한다(repo):
    out = repo.step(repo.c, "cccccccccccc")

    assert out.startswith("reject ")
    assert "origin/develop" in out


def test_올릴_커밋을_못_읽으면_거절한다(repo):
    out = repo.step("0" * 40, B)

    assert out.startswith("reject ")
    # 「못 찾았다」가 아니라 「읽지 못했다」로 답해야 한다. git grep 이 깨졌다는 종료 코드가
    # ERR 트랩에 1(못 찾음)로 뭉개지면 develop 쪽 이유로 새 나간다
    assert "마이그레이션 폴더를 읽지 못했다" in out


def test_선언한_파일만_찾고_down_revision_은_세지_않는다(repo):
    assert repo.rev_file(repo.c, A).endswith(f"_{A}_first.py")
    assert repo.rev_file(repo.c, B).endswith(f"_{B}_second.py")
    # 아직 b 가 없는 커밋에서는 b 의 파일도 없고, a 를 적은 down_revision 도 a 로 안 센다
    assert repo.rev_file(repo.a1, B) == ""
    assert repo.rev_file(repo.p0, A) == ""


def test_경로에_트리_접두사가_붙지_않는다(repo):
    assert repo.rev_file(repo.c, A) == f"backend/alembic/versions/20260101_0000_{A}_first.py"


def test_실제_리비전을_전부_선언한_파일로_찾는다(sh):
    # 실제 저장소 HEAD 의 리비전 전부 — `revision = '…'` 꼴과 `revision: str = "…"` 꼴이 섞여 있다.
    # 작업 폴더가 아니라 HEAD 를 읽는다. rollback compat job 은 HEAD 위에 다른 PR 의
    # 마이그레이션 파일을 얹어 둔다.
    top = "backend/alembic/versions/"
    listing = git(sh.env, ROOT, "ls-tree", "-r", "--name-only", "HEAD", top).splitlines()
    files = [f for f in listing if f.endswith(".py")]
    expected = {}
    for f in files:
        text = git(sh.env, ROOT, "show", f"HEAD:{f}")
        found = re.findall(r"""^revision(?:: str)? = ['"]([0-9a-f]{12})['"]""", text, re.M)
        assert len(found) == 1, f"{f} 의 revision 선언이 {len(found)}개다"
        expected[found[0]] = f
    assert files and len(expected) == len(files)  # 리비전 하나에 파일 하나

    proc = sh(
        'for r in "$@"; do printf "%s %s\\n" "$r" "$(revision_file HEAD "$r")"; done',
        *expected,
    )

    assert proc.returncode == 0, proc.stderr
    got = dict(line.split(" ", 1) for line in proc.stdout.splitlines())
    assert got == expected


def test_source_하면_함수만_정의하고_서버_명령은_안_부른다(sh):
    proc = sh('type -t migration_step revision_file db_revisions main; echo "after-source"')

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split() == ["function"] * 4 + ["after-source"]
    assert not sh.calls.exists()


def test_직접_돌리면_main_이_돈다(sh, tmp_path):
    # source 가드가 거꾸로 걸려 main 이 영영 안 도는 일을 막는다 — 가짜 runuser(또는 sudo)가 불린다
    proc = subprocess.run(
        ["bash", str(DEPLOY_SH)],
        env={**sh.env, "DEPLOY_REF": "main"},
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert proc.returncode != 0
    assert sh.calls.exists()


def test_main_거절이면_checkout_도_build_도_전에_멈춘다(server, repo):
    srv = server(repo.c)
    before = srv.head()

    proc = srv.run(repo.a0, B)  # B 는 a1 이다. a0 로는 건너뛰지 못한다

    assert proc.returncode != 0
    assert "배포를 멈춘다" in proc.stdout
    assert srv.head() == before  # checkout 안 했다
    assert srv.log() == []  # nginx -t · build · up -d 어느 것도 안 불렸다


def test_main_DB_리비전을_못_읽으면_서버를_안_바꾸고_멈춘다(server, repo):
    srv = server(repo.c)
    before = srv.head()

    proc = srv.run(repo.c, B, db_fail=True)

    assert proc.returncode != 0
    assert "DB 리비전을 읽지 못했다" in proc.stdout
    assert srv.head() == before
    assert srv.log() == []


def test_main_건너뛰기면_upgrade_만_빼고_나머지는_한다(server, repo):
    srv = server(repo.c)

    proc = srv.run(repo.a1, B)  # a1 은 b 를 들여온 머지의 직전 커밋이다

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert srv.head() == repo.a1
    assert "마이그레이션을 건너뛴다" in proc.stdout
    log = srv.log()
    assert "docker compose build backend frontend" in log
    assert "docker compose up -d" in log
    assert not any("alembic" in line for line in log)
    assert proc.stdout.rstrip().endswith("배포 끝")


@pytest.mark.parametrize("ref", ["c", "develop"])
def test_main_올릴_코드가_리비전을_알면_up_전에_upgrade_를_돈다(server, repo, ref):
    srv = server(repo.a1)

    proc = srv.run(repo.c if ref == "c" else ref, B)  # 커밋 SHA 로도 브랜치 이름으로도

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert srv.head() == repo.c
    assert "마이그레이션을 건너뛴다" not in proc.stdout
    log = srv.log()
    upgrade = "docker compose run --rm backend alembic upgrade head"
    assert log.index(upgrade) < log.index("docker compose up -d")
    assert log.index("docker compose build backend frontend") < log.index(upgrade)


def test_main_교체_뒤_서버_안이_둘_다_200이면_그_뒤에야_prune_하고_끝난다(server, repo):
    srv = server(repo.a1)

    proc = srv.run(repo.c, B)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    log = srv.log()
    reload = "docker compose exec -T nginx nginx -s reload"
    up, prune = log.index("docker compose up -d"), log.index("docker image prune -f")
    assert up < log.index(reload) < prune
    assert "서버 안 확인 통과" in proc.stdout and "(1회째)" in proc.stdout
    # 러너가 도메인으로 묻는 것과 따로, 서버 안 nginx 에 IPv4 로 묻는다 — localhost 는 ::1 로 붙는다
    assert set(srv.curls()) == {"http://127.0.0.1/health/ready", "http://127.0.0.1/"}


@pytest.mark.parametrize(
    ("ready", "page", "env_extra", "last"),
    [
        ("503", "200", {}, "health/ready 503 · 화면 200"),  # backend · DB 가 안 살아났다
        ("200", "502", {}, "health/ready 200 · 화면 502"),  # 화면(frontend)만 안 살아났다
        # 응답 코드는 200 인데 curl 이 도중에 죽었다(타임아웃). 200 으로 읽으면 안 된다
        ("200", "200", {"FAKE_READY_RC": "28"}, "health/ready 200(curl 28) · 화면 200"),
    ],
)
def test_main_교체_뒤_서버_안이_안_살아나면_3으로_끝나고_prune_은_안_한다(
    server, repo, ready, page, env_extra, last
):
    srv = server(repo.a1)

    proc = srv.run(repo.c, B, ready=ready, page=page, env_extra=env_extra)

    assert proc.returncode == 3, proc.stdout + proc.stderr
    log = srv.log()
    assert "docker compose up -d" in log  # 교체는 했다
    assert "docker image prune -f" not in log  # 실패한 판에서는 옛 이미지를 지우지 않는다
    assert "배포 끝" not in proc.stdout
    assert f"마지막 {last}" in proc.stdout
    assert len(srv.curls()) == 3 * 2  # 3번 × (ready · 화면)


def test_main_처음_몇_번_못_닿아도_결국_둘_다_200이면_통과한다(server, repo):
    srv = server(repo.a1)

    proc = srv.run(repo.c, B, env_extra={"FAKE_FAIL_FIRST": "4"})  # 두 번째 시도까지 연결 실패

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "000(curl 7)" in proc.stdout  # 기다리는 동안 무엇을 봤는지 남는다
    assert "(3회째)" in proc.stdout
    assert "docker image prune -f" in srv.log()


def test_main_예상_밖_명령이_3으로_죽어도_1로_끝난다(server, repo):
    # 3 은 「교체 뒤 안 살아났다」 하나의 뜻이다. docker 가 3 으로 죽었다고 롤백이 돌면 안 된다
    srv = server(repo.a1)

    proc = srv.run(repo.c, B, env_extra={"FAKE_BUILD_EXIT": "3"})

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "docker compose up -d" not in srv.log()  # build 에서 멈췄다


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [({}, 0), ({"ready": "503"}, 3), ({"db_fail": True}, 1)],
)
def test_main_root_로_시작해도_ubuntu_쪽_종료_코드가_그대로_나온다(server, repo, kwargs, code):
    # SSM 은 root 로 돈다. root → runuser → ubuntu 를 지나다 3 이 1 로 뭉개지면
    # 롤백이 영영 안 돈다
    srv = server(repo.a1)

    proc = srv.run(repo.c, B, as_root=True, **kwargs)

    assert proc.returncode == code, proc.stdout + proc.stderr
    if code != 1:
        assert srv.head() == repo.c  # 가짜 runuser 를 지나 진짜 main 이 돌았다


def test_다른_배포가_잠금을_쥐고_있으면_서버를_안_바꾸고_멈춘다(server, repo, tmp_path):
    srv = server(repo.c)
    before = srv.head()
    lock = tmp_path / "held.lock"

    with lock.open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        proc = srv.run(repo.a1, B, lock=lock, lock_wait=1)

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "잠금을 못 잡았다" in proc.stdout
    assert srv.head() == before
    assert srv.log() == []


def test_잠금이_풀리면_기다리던_배포가_이어서_돈다(server, repo, tmp_path):
    srv = server(repo.a1)
    lock = tmp_path / "held.lock"
    held = lock.open("w")
    fcntl.flock(held, fcntl.LOCK_EX)
    timer = threading.Timer(1.0, held.close)  # 닫으면 잠금이 풀린다
    timer.start()

    try:
        proc = srv.run(repo.c, B, lock=lock, lock_wait=30)
    finally:
        timer.cancel()
        held.close()

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert srv.head() == repo.c
