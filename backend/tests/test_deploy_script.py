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
"""

import os
import re
import stat
import subprocess
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
"""
FAKE_ID = "#!/bin/sh\necho ubuntu\n"  # 이미 ubuntu 라서 runuser 로 내려가지 않는다


@pytest.fixture
def server(tmp_path, sh, repo):
    """main 을 돌려 볼 가짜 서버. 원격은 repo 를 복제한 bare 저장소이고 서버 폴더는 그 복제본이다.

    `server(at)` 은 서버가 커밋 `at` 에 서 있는 채로 시작하고, `.run(ref, rev)` 가 main 을 돌린다.
    """
    bare = tmp_path / "origin.git"
    srv = tmp_path / "srv"
    log = tmp_path / "server-commands.log"
    fake = tmp_path / "server-bin"
    fake.mkdir()
    for name, body in {"sudo": FAKE_SUDO, "id": FAKE_ID}.items():
        p = fake / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    env = {**sh.env, "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}"}

    def make(at: str) -> SimpleNamespace:
        git(env, tmp_path, "clone", "-q", "--bare", str(repo.path), str(bare))
        git(env, tmp_path, "clone", "-q", str(bare), str(srv))
        git(env, srv, "checkout", "-q", "-f", "--detach", at)
        (srv / ".env").write_text("")  # 커밋하지 않는 파일. main 이 있는지 본다

        def run(ref: str, rev: str, *, db_fail: bool = False) -> subprocess.CompletedProcess:
            run_env = {
                **env,
                "DEPLOY_REF": ref,
                "FAKE_REV": rev,
                "FAKE_LOG": str(log),
                "SIM_DIR": str(srv),
                "SIM_URL": str(bare),
            }
            if db_fail:
                run_env["FAKE_DB_FAIL"] = "1"
            # DEPLOY_PATH · REPO_URL 은 스크립트 위쪽 상수라 source 한 뒤에 로컬 경로로 바꾼다
            body = f'source "{DEPLOY_SH}"\nDEPLOY_PATH="$SIM_DIR"\nREPO_URL="$SIM_URL"\nmain'
            return subprocess.run(
                ["bash", "-c", body],
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
    assert repo.step("0" * 40, B).startswith("reject ")


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
