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

교체 뒤 서버 안 확인(`wait_ready`)과 자동 롤백도 같은 가짜 서버로 본다(ADR-078). 종료 코드가 알림을
움직인다 — 0 성공 · 3 실패했고 직전 성공 커밋으로 되돌림 · 4 교체 뒤 실패했고 못 되돌림 ·
1 교체 전에 멈춤. 되돌리기는 **L 의 deploy.sh** 를 `git show` 로 꺼내 자식으로 돌린다 —
가짜 저장소의 L 커밋(a1)에 시험용 `scripts/deploy.sh` 가 들어 있고(부른 모습을 기록하고
가짜 서버를 L 로 돌려 놓고 `FAKE_L_EXIT` 로 끝난다), F 커밋(c)에는 일부러 망가뜨린 스크립트가
들어 있다. 가짜 curl 은 도는 컨테이너가 `bad` 목록에 있으면 /health/ready 를 503 으로
답해서 「이 커밋은 안 살아나고 저 커밋은 산다」를 흉내 낸다. 코드가 다른 실패에 새거나
(어떤 명령이 3 으로 죽어도 3 은 안 나온다), 되돌리는 도중의 실패가 1 로 뭉개지거나,
root → ubuntu 재실행을 지나다 사라지면 알림이 틀리므로 그것들을 시험한다.
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

# 가짜 저장소의 L 커밋(a1)에 들어 있는 `scripts/deploy.sh`. 되돌리기가 이것을 꺼내 돌린다.
# 부른 모습(env)을 FAKE_L_RECORD 에 적고, 자식이 시작할 때 서버 잠금이 풀려 있는지 `flock -n` 으로
# 잡아 보고, 가짜 서버(폴더 · 이미지 · 컨테이너)를 DEPLOY_REF 로 돌려 놓고, FAKE_L_EXIT 로 끝난다.
L_DEPLOY_STUB = """#!/bin/sh
{
  echo "ran-L-script"
  echo "DEPLOY_REF=$DEPLOY_REF"
  echo "AUTO_ROLLBACK=$AUTO_ROLLBACK"
} >> "$FAKE_L_RECORD"
exec 8>"$SIM_LOCK"
if flock -n 8; then state=free; else state=busy; fi
echo "lock=$state" >> "$FAKE_L_RECORD"
exec 8>&-
git -C "$SIM_DIR" checkout -q -f --detach "$DEPLOY_REF" 2>/dev/null
git -C "$SIM_DIR" rev-parse HEAD > "$FAKE_BUILT_FILE"
cp "$FAKE_BUILT_FILE" "$FAKE_RUNNING_FILE"
echo "L-stdout"
echo "L-stderr" >&2
[ -z "$FAKE_L_STDERR_PAD" ] || printf '%9000s' '' | tr ' ' x >&2
exit "${FAKE_L_EXIT:-0}"
"""
# 잠금이라는 것을 모르는 옛 L 의 deploy.sh 흉내(이 PR 보다 옛 스크립트). 부모는 파일 안의 그 글자로
# 「잠금을 직접 잡는 스크립트」를 가른다. 그래서 아래 명령 이름을 글자 그대로 쓰지 않고
# 셸이 붙여 읽게 했다 — 잠금을 쥐고 있는지는 같은 명령으로 본다.
L_DEPLOY_STUB_OLD = """#!/bin/sh
{
  echo "ran-L-script"
  echo "DEPLOY_REF=$DEPLOY_REF"
  echo "AUTO_ROLLBACK=$AUTO_ROLLBACK"
} >> "$FAKE_L_RECORD"
exec 8>"$SIM_LOCK"
if fl''ock -n 8; then state=free; else state=busy; fi
echo "lock=$state" >> "$FAKE_L_RECORD"
exec 8>&-
git -C "$SIM_DIR" checkout -q -f --detach "$DEPLOY_REF" 2>/dev/null
git -C "$SIM_DIR" rev-parse HEAD > "$FAKE_BUILT_FILE"
cp "$FAKE_BUILT_FILE" "$FAKE_RUNNING_FILE"
echo "L-stdout"
exit "${FAKE_L_EXIT:-0}"
"""
# F 커밋(c)의 `scripts/deploy.sh` — 일부러 망가뜨렸다. F 의 스크립트로 되돌리면 이것이 돌고
# 99 로 죽는다.
F_DEPLOY_BROKEN = """#!/bin/sh
echo "ran-F-script" >> "$FAKE_L_RECORD"
exit 99
"""


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
    sha.a1 = commit("A1", {"README.md": "y\n", "scripts/deploy.sh": L_DEPLOY_STUB})
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
    sha.c = commit("C", {"README.md": "z\n", "scripts/deploy.sh": F_DEPLOY_BROKEN})
    g("switch", "-q", "-c", "other", sha.a1)
    sha.x = commit("X", {"README.md": "other\n", "scripts/deploy.sh": L_DEPLOY_STUB_OLD})
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
    cat "$FAKE_REV_FILE"
    exit 0 ;;
  "docker compose config --services") printf 'backend\\nfrontend\\n'; exit 0 ;;
esac
echo "$*" >> "$FAKE_LOG"
# `alembic upgrade head` 를 받으면 DB 리비전이 FAKE_UPGRADE_TO 로 올라간다
case "$*" in
  *"alembic upgrade head"*)
    [ -z "$FAKE_UPGRADE_TO" ] || echo "$FAKE_UPGRADE_TO" > "$FAKE_REV_FILE" ;;
esac
# FAKE_FAIL_PATTERN(정규식)에 맞는 명령은 앞의 FAKE_FAIL_SKIP 번(없으면 0)을 지나 보내고, 그다음
# FAKE_FAIL_TIMES 번(없으면 계속) FAKE_FAIL_CODE 로 죽는다
if [ -n "$FAKE_FAIL_PATTERN" ] && echo "$*" | grep -Eq "$FAKE_FAIL_PATTERN"; then
  n=$(cat "$FAKE_FAIL_COUNT" 2>/dev/null || echo 0)
  echo $((n + 1)) > "$FAKE_FAIL_COUNT"
  skip=${FAKE_FAIL_SKIP:-0}
  last=$((skip + ${FAKE_FAIL_TIMES:-999}))
  [ "$n" -lt "$skip" ] || [ "$n" -ge "$last" ] || exit "${FAKE_FAIL_CODE:-1}"
fi
# 이미지 · 컨테이너를 흉내 낸다. build 는 지금 서버 HEAD 로 이미지를 만들고(FAKE_BUILT_FILE),
# up -d 는 만들어 둔 이미지로 컨테이너를 바꾼다(FAKE_RUNNING_FILE). 지금 도는 것이 누구냐는
# HEAD 가 아니라 이 둘이 정한다 — build 나 up -d 를 건너뛰면 checkout 만 바뀌고
# 옛 컨테이너가 계속 돈다.
# build 출력은 길다. deploy.sh 는 이것을 stdout 이 아니라 파일로 돌려야 한다
case "$*" in
  *"compose build"*)
    echo BUILD-NOISE
    [ "${FAKE_BUILD_EXIT:-0}" -eq 0 ] || exit "$FAKE_BUILD_EXIT"
    git -C "$SIM_DIR" rev-parse HEAD > "$FAKE_BUILT_FILE" ;;
  *"compose up -d"*)
    [ -z "$FAKE_UP_NOEOL" ] || printf 'up-noeol' >&2
    cp "$FAKE_BUILT_FILE" "$FAKE_RUNNING_FILE" ;;
  # nginx 가 떠 있나. 기본은 떠 있다(id 한 줄). FAKE_NGINX_DOWN 이면 빈 값(종료 0)이다
  *"compose ps -q --status running nginx"*)
    [ -n "$FAKE_NGINX_DOWN" ] || echo fake-nginx-id ;;
esac
"""
# 평소에는 이미 ubuntu 라서 runuser 로 내려가지 않는다. FAKE_ROOT 면 root 로 보이다가
# 가짜 runuser 가 FAKE_AS_UBUNTU 를 세워 준 뒤부터 ubuntu 로 보인다.
FAKE_ID = '#!/bin/sh\n[ -n "$FAKE_ROOT" ] && [ -z "$FAKE_AS_UBUNTU" ] && echo root || echo ubuntu\n'
# `runuser -u ubuntu -- env NAME=값 … bash <복사본>` 을 받아, `env` 인자를 이름으로 읽어 내보내고
# 복사본을 source 해서 진짜 main 을 돈다. 스크립트로 돌리면 DEPLOY_PATH · REPO_URL 같은 상수를
# 로컬 경로로 바꿀 수 없다. env 인자가 늘어도(DEPLOY_REF · AUTO_ROLLBACK) 이름으로 읽어서 안 밀린다.
FAKE_RUNUSER = """#!/bin/sh
# runuser 가 환경을 물려준다는 보장이 없다 — 손으로 넘긴 것만 남긴다
unset DEPLOY_REF AUTO_ROLLBACK
while [ "$1" != -- ]; do shift; done
shift 2           # -- env
while [ "$1" != bash ]; do export "$1"; shift; done
shift             # bash
inner=$1
export FAKE_AS_UBUNTU=1
exec bash -c 'source "$1"
DEPLOY_PATH="$SIM_DIR"
REPO_URL="$SIM_URL"
READY_TRIES="$SIM_READY_TRIES"
READY_INTERVAL=0
LOCK_FILE="$SIM_LOCK"
LOCK_WAIT="$SIM_LOCK_WAIT"
LAST_GOOD_FILE="$SIM_LAST_GOOD"
BUILD_LOG="$SIM_BUILD_LOG"
main' bash "$inner"
"""
# 마지막 인자가 주소다. FAKE_READY · FAKE_PAGE 가 그 주소가 줄 응답 코드,
# *_RC 가 curl 의 종료 코드다. FAKE_FAIL_FIRST=N 이면 처음 N 번의 호출은 연결 실패(000, 종료 7)다.
# FAKE_BAD_SHAS(공백으로 나눈 목록)에 **지금 도는 컨테이너의 커밋**(FAKE_RUNNING_FILE, 가짜 sudo 의
# build → up -d 가 정한다)이 있으면 /health/ready 는 503 이다 — 「이 커밋은 안 살아난다」를
# 커밋 단위로 흉내 낸다. 서버 폴더(HEAD)가 아니라 컨테이너를 봐서, L 을 build · up -d 하지 않고
# checkout 만 한 되돌리기는 계속 503 이다.
FAKE_CURL = """#!/bin/sh
for url; do :; done
echo "$url" >> "$FAKE_CURL_LOG"
if [ -n "$FAKE_FAIL_FIRST" ]; then
  n=$(cat "$FAKE_CURL_COUNT" 2>/dev/null || echo 0)
  echo $((n + 1)) > "$FAKE_CURL_COUNT"
  [ "$n" -ge "$FAKE_FAIL_FIRST" ] || { printf 000; exit 7; }
fi
ready=$FAKE_READY
running=$(cat "$FAKE_RUNNING_FILE" 2>/dev/null)
for bad in $FAKE_BAD_SHAS; do [ "$bad" = "$running" ] && ready=503; done
case "$url" in
  */health/ready) printf '%s' "$ready"; exit "${FAKE_READY_RC:-0}" ;;
  *) printf '%s' "$FAKE_PAGE"; exit "${FAKE_PAGE_RC:-0}" ;;
esac
"""
# macOS 에는 flock 이 없다. 서버(Linux)의 flock(1) 과 같은 flock(2) 를 거는 가짜다.
# `flock -w <초> <fd>` 와 `flock -n <fd>`(기다리지 않는다)만 안다.
FAKE_FLOCK = f"""#!{sys.executable}
import fcntl, sys, time
args = sys.argv[1:]
secs, fd = (0, args[1]) if args[0] == "-n" else (args[1], args[2])
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
    기본은 교체 뒤 서버 안 확인이 둘 다 200 이다. `ready` · `page` 로 응답 코드를, `bad` 로
    「이 커밋이 서버 HEAD 일 때는 안 살아난다」를, `env_extra` 로 가짜 명령의 동작을 바꾼다.
    `last_good` 은 서버가 기억한 마지막 성공 커밋(파일 내용), `auto` 는 AUTO_ROLLBACK 값이다.
    """
    bare = tmp_path / "origin.git"
    srv = tmp_path / "srv"
    log = tmp_path / "server-commands.log"
    curl_log = tmp_path / "server-curl.log"
    db_rev = tmp_path / "db-revision"
    built_file = tmp_path / "built-image"  # 만들어 둔 이미지의 커밋(가짜 build 가 적는다)
    running_file = tmp_path / "running-container"  # 지금 도는 컨테이너의 커밋(가짜 up -d 가 적는다)
    last_good_path = tmp_path / "last-good"
    l_record = tmp_path / "l-script-record"  # L 의 deploy.sh(시험용)가 부른 모습을 적는다
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
        # 서버는 `at` 을 build 해서 올려 둔 채로 시작한다
        built_file.write_text(f"{at}\n")
        running_file.write_text(f"{at}\n")

        def run(
            ref: str,
            rev: str,
            *,
            db_fail: bool = False,
            ready: str = "200",
            page: str = "200",
            bad: tuple[str, ...] = (),
            tries: int = 3,
            lock: Path = tmp_path / "deploy.lock",
            lock_wait: int = 5,
            last_good: str | None = None,
            last_good_file: Path = last_good_path,
            auto: str | None = None,
            upgrade_to: str | None = None,
            l_exit: int = 0,
            as_root: bool = False,
            env_extra: dict[str, str] | None = None,
        ) -> subprocess.CompletedProcess:
            db_rev.write_text(f"{rev}\n")
            if last_good is not None:
                last_good_file.write_text(last_good)
            run_env = {
                **env,
                "DEPLOY_REF": ref,
                "FAKE_REV_FILE": str(db_rev),
                "FAKE_BUILT_FILE": str(built_file),
                "FAKE_RUNNING_FILE": str(running_file),
                "FAKE_LOG": str(log),
                "FAKE_CURL_LOG": str(curl_log),
                "FAKE_CURL_COUNT": str(tmp_path / "curl-count"),
                "FAKE_FAIL_COUNT": str(tmp_path / "fail-count"),
                "FAKE_READY": ready,
                "FAKE_PAGE": page,
                "FAKE_BAD_SHAS": " ".join(bad),
                "SIM_DIR": str(srv),
                "SIM_URL": str(bare),
                "SIM_READY_TRIES": str(tries),
                "SIM_LOCK": str(lock),
                "SIM_LOCK_WAIT": str(lock_wait),
                "FAKE_L_RECORD": str(l_record),
                "FAKE_L_EXIT": str(l_exit),
                "SIM_LAST_GOOD": str(last_good_file),
                "SIM_BUILD_LOG": str(tmp_path / "build.log"),
                **(env_extra or {}),
            }
            if auto is not None:
                run_env["AUTO_ROLLBACK"] = auto
            if upgrade_to is not None:
                run_env["FAKE_UPGRADE_TO"] = upgrade_to
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
                    'LAST_GOOD_FILE="$SIM_LAST_GOOD"\nBUILD_LOG="$SIM_BUILD_LOG"\n'
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
            last_good=lambda: (
                last_good_path.read_text().strip() if last_good_path.exists() else None
            ),
            last_good_path=last_good_path,
            l_record=lambda: l_record.read_text().splitlines() if l_record.exists() else [],
            built=lambda: built_file.read_text().strip(),
            running=lambda: running_file.read_text().strip(),
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


def resolve(repo, name: str | None) -> str | None:
    """테스트 표에 적은 이름(c · a1 …)을 커밋 SHA 로 바꾼다."""
    return None if name is None else getattr(repo, name, name)


def test_main_교체_뒤_서버_안이_둘_다_200이면_그_뒤에야_기록하고_prune_하고_끝난다(server, repo):
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
    # 서버 안 확인을 통과한 커밋이 「마지막 성공」으로 적힌다. 처음이라 그 전 기록은 없었다
    assert srv.last_good() == repo.c
    assert srv.running() == repo.c  # 컨테이너가 실제로 바뀌었다(build → up -d)
    assert proc.stdout.startswith("직전 성공 없음\n")
    assert proc.stderr.count("되돌") == 0


def test_main_build_출력은_stdout_이_아니라_파일로_간다(server, repo, tmp_path):
    # SSM 은 stdout 앞 24000자만 돌려준다. next build 출력이 그 자리를 다 쓰면 뒤의 진단이 잘린다
    srv = server(repo.a1)

    proc = srv.run(repo.c, B)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "BUILD-NOISE" not in proc.stdout
    assert "BUILD-NOISE" in (tmp_path / "build.log").read_text()


def test_main_build_가_실패하면_끝줄을_보여_주고_1이다(server, repo):
    # 3 은 「교체 뒤 안 살아났다」와 무관하다 — 어떤 명령이 3 으로 죽어도 교체 전이면 1
    srv = server(repo.a1)

    proc = srv.run(repo.c, B, last_good=repo.a1, auto="1", env_extra={"FAKE_BUILD_EXIT": "3"})

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "build 가 실패했다" in proc.stdout and "BUILD-NOISE" in proc.stdout
    assert "docker compose up -d" not in srv.log()  # build 에서 멈췄다
    assert srv.last_good() == repo.a1  # 기록은 그대로
    assert "되돌" not in proc.stderr  # 교체 전이라 되돌릴 것이 없다


def test_main_가드_없는_명령이_3으로_죽어도_1이다(server, repo):
    # nginx -t 는 `||` 로 받지 않는다 — ERR 트랩이 받는다. 그 코드가 3 이어도 3 은 안 나온다
    srv = server(repo.a1)

    proc = srv.run(
        repo.c,
        B,
        auto="1",
        last_good=repo.a1,
        env_extra={"FAKE_FAIL_PATTERN": "no-deps nginx", "FAKE_FAIL_CODE": "3"},
    )

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "docker compose up -d" not in srv.log()


@pytest.mark.parametrize(
    ("ready", "page", "env_extra", "last"),
    [
        ("503", "200", {}, "health/ready 503 · 화면 200"),  # backend · DB 가 안 살아났다
        ("200", "502", {}, "health/ready 200 · 화면 502"),  # 화면(frontend)만 안 살아났다
        # 응답 코드는 200 인데 curl 이 도중에 죽었다(타임아웃). 200 으로 읽으면 안 된다
        ("200", "200", {"FAKE_READY_RC": "28"}, "health/ready 200(curl 28) · 화면 200"),
    ],
)
def test_main_교체_뒤_서버_안이_안_살아나면_롤백이_꺼져_있으면_4로_끝나고_prune_은_안_한다(
    server, repo, ready, page, env_extra, last
):
    srv = server(repo.a1)

    proc = srv.run(repo.c, B, ready=ready, page=page, env_extra=env_extra, last_good=repo.a1)

    assert proc.returncode == 4, proc.stdout + proc.stderr
    log = srv.log()
    assert "docker compose up -d" in log  # 교체는 했다
    assert "docker image prune -f" not in log  # 실패한 판에서는 옛 이미지를 지우지 않는다
    assert "배포 끝" not in proc.stdout
    assert f"마지막 {last}" in proc.stdout
    assert len(srv.curls()) == 3 * 2  # 3번 × (ready · 화면)
    assert srv.head() == repo.c  # 되돌리지 않았다
    assert srv.last_good() == repo.a1  # 서버 안 확인을 통과하지 못한 커밋은 기록하지 않는다


def test_main_처음_몇_번_못_닿아도_결국_둘_다_200이면_통과한다(server, repo):
    srv = server(repo.a1)

    proc = srv.run(repo.c, B, env_extra={"FAKE_FAIL_FIRST": "4"})  # 두 번째 시도까지 연결 실패

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "000(curl 7)" in proc.stdout  # 기다리는 동안 무엇을 봤는지 남는다
    assert "(3회째)" in proc.stdout
    assert "docker image prune -f" in srv.log()


def test_main_F_가_안_살아나면_L_의_deploy_sh_로_되돌리고_3으로_끝난다(server, repo):
    # 서버는 a1(= L, 직전 성공)에서 돈다. c(= F)를 올렸더니 안 살아난다
    srv = server(repo.a1)

    proc = srv.run(repo.c, A, auto="1", last_good=f"{repo.a1}\n", bad=(repo.c,))

    assert proc.returncode == 3, proc.stdout + proc.stderr
    # L 의 스크립트가 돌았다 — 자식은 DEPLOY_REF=L, AUTO_ROLLBACK=0 으로 불렸고,
    # 시작할 때 서버 잠금이 풀려 있었다
    assert srv.l_record() == [
        "ran-L-script",
        f"DEPLOY_REF={repo.a1}",
        "AUTO_ROLLBACK=0",
        "lock=free",
    ]
    assert srv.head() == repo.a1  # (시험용 L 스크립트가) 서버를 L 로 돌려 놓았다
    assert srv.running() == repo.a1
    assert srv.last_good() == repo.a1  # 되돌리기는 기록을 안 바꾼다
    assert proc.stdout.startswith(f"직전 성공 {repo.a1}\n")
    assert f"되돌린다 → {repo.a1} (L 의 deploy.sh)" in proc.stdout
    # 자식 출력은 흐른다 — 자식의 stderr 도 stdout 으로 합쳐 와서,
    # 부모의 stderr 에는 결과 줄만 남는다
    assert "L-stdout" in proc.stdout and "L-stderr" in proc.stdout
    assert "L-stderr" not in proc.stderr
    # 결과 줄은 stderr 의 마지막 줄, 줄 맨 앞이다 — deploy.yml 은 이런 줄 중 마지막 하나를 읽는다
    assert proc.stderr.splitlines()[-1] == f"되돌렸다 → {repo.a1} (L 의 deploy.sh)"
    log = srv.log()
    assert log.count("docker compose up -d") == 1  # F 의 것뿐. 되돌리기는 L 의 스크립트가 한다
    assert "docker image prune -f" not in log
    assert "배포 끝" not in proc.stdout


@pytest.mark.parametrize("l_exit", [0, 1])
def test_main_앞선_stderr_가_줄바꿈_없이_끝나도_결과_줄은_줄_맨_앞이다(server, repo, l_exit):
    # deploy.yml 은 줄 맨 앞의 결과 줄 중 마지막 하나를 읽는다.
    # 가짜 `up -d` 가 줄바꿈 없는 글을 stderr 에 남긴다
    srv = server(repo.a1)

    proc = srv.run(
        repo.c,
        A,
        auto="1",
        last_good=repo.a1,
        bad=(repo.c,),
        l_exit=l_exit,
        env_extra={"FAKE_UP_NOEOL": "1"},
    )

    lines = proc.stderr.splitlines()
    assert "up-noeol" in lines  # 그 글이 자기 줄로 끝났다
    assert lines[-1].startswith("되돌렸다 → " if l_exit == 0 else "되돌리기도 실패 — ")


@pytest.mark.parametrize("l_exit", [0, 1])
def test_main_자식이_stderr_를_많이_써도_부모의_결과_줄은_stderr_에_남는다(server, repo, l_exit):
    # SSM stderr 한도는 8000자다. 옛 L 스크립트의 build 출력이 그것을 채우면
    # 부모의 결과 줄이 밀려난다.
    # 자식의 stderr 는 stdout 으로 합쳐서 부모의 stderr 를 작게 지킨다
    srv = server(repo.a1)

    proc = srv.run(
        repo.c,
        A,
        auto="1",
        last_good=repo.a1,
        bad=(repo.c,),
        l_exit=l_exit,
        env_extra={"FAKE_L_STDERR_PAD": "1"},
    )

    assert proc.returncode == (3 if l_exit == 0 else 4), proc.stdout + proc.stderr
    assert "x" * 9000 in proc.stdout  # 자식이 쓴 글은 stdout 으로 갔다
    assert len(proc.stderr) < 1500
    assert proc.stderr.splitlines()[-1].startswith(
        "되돌렸다 → " if l_exit == 0 else "되돌리기도 실패 — "
    )


def test_main_L_이_잠금을_모르는_옛_스크립트면_잠금을_쥔_채_돌려도_3이다(server, repo):
    # 이 PR 보다 옛 deploy.sh 에는 잠금이 없다. 부모가 잠금을 풀면 되돌리기 내내
    # 잠금 없이 도는 셈이라 그 동안 Session Manager 배포가 끼어들 수 있다.
    # 자식이 잠금을 달라고 하지 않으니 쥔 채로 돌려도 교착이 없다
    srv = server(repo.a1)

    proc = srv.run(repo.c, A, auto="1", last_good=repo.x, bad=(repo.c,))

    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert srv.l_record() == [
        "ran-L-script",
        f"DEPLOY_REF={repo.x}",
        "AUTO_ROLLBACK=0",
        "lock=busy",  # 자식이 돌 때 부모가 서버 잠금을 쥐고 있었다
    ]
    assert "서버 잠금을 안 잡는 옛 스크립트" in proc.stdout
    assert srv.head() == repo.x
    assert proc.stderr.splitlines()[-1] == f"되돌렸다 → {repo.x} (L 의 deploy.sh)"


def test_main_F_의_deploy_sh_가_망가졌어도_L_의_것으로_되돌린다(server, repo):
    # F 커밋(c)의 scripts/deploy.sh 는 99 로 죽는다. 서버 폴더는 F 를 checkout 한 상태지만
    # 되돌리기는 거기 있는 파일이 아니라 `git show L:scripts/deploy.sh` 를 돌린다
    srv = server(repo.a1)

    proc = srv.run(repo.c, A, auto="1", last_good=repo.a1, bad=(repo.c,))

    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert "ran-L-script" in srv.l_record()
    assert "ran-F-script" not in srv.l_record()


@pytest.mark.parametrize("code", [1, 3, 4, 255])
def test_main_L_의_deploy_sh_가_0_이_아니게_끝나면_4다(server, repo, code):
    # 자식의 3 도 4 다 — 자식이 자기 직전으로 되돌렸어도 L 에 도착한 것이 아니다.
    # 어떤 코드도 1 이나 0 으로 안 샌다
    srv = server(repo.a1)

    proc = srv.run(repo.c, A, auto="1", last_good=repo.a1, bad=(repo.c,), l_exit=code)

    assert proc.returncode == 4, proc.stdout + proc.stderr
    assert f"DEPLOY_REF={repo.a1}" in srv.l_record()  # 자식은 L 로 불렸다
    lines = proc.stderr.splitlines()
    assert lines[-1] == f"되돌리기도 실패 — L 의 deploy.sh 가 {code} 로 끝났다"
    assert "되돌렸다" not in proc.stderr


def test_main_L_커밋에_deploy_sh_가_없으면_되돌리지_않고_4다(server, repo):
    # a0 에는 scripts/deploy.sh 가 없다
    srv = server(repo.a1)

    proc = srv.run(repo.c, A, auto="1", last_good=repo.a0, bad=(repo.c,))

    assert proc.returncode == 4, proc.stdout + proc.stderr
    assert any(
        line.startswith("되돌리지 않는다 — L 의 deploy.sh 를 꺼내지 못했다")
        for line in proc.stderr.splitlines()
    )
    assert srv.l_record() == []  # 아무것도 돌리지 않았다
    assert srv.head() == repo.c


@pytest.mark.parametrize(
    ("auto", "last_good", "why"),
    [
        (None, "a1", "자동 롤백이 꺼져 있다"),  # Session Manager 손 배포
        ("0", "a1", "자동 롤백이 꺼져 있다"),
        ("true", "a1", "자동 롤백이 꺼져 있다"),  # '1' 만 켠다
        ("1", None, "직전 성공 기록이 없다"),  # 이 PR 머지 뒤 첫 성공 배포 전
        ("1", "garbage", "직전 성공 기록이 없다"),  # 40자리 16진수가 아니다
        ("1", "c", "직전 성공이 이번에 올린 커밋과 같다"),
    ],
)
def test_main_못_되돌리는_경우는_이유를_stderr_에_적고_4로_끝난다(
    server, repo, auto, last_good, why
):
    srv = server(repo.a1)

    proc = srv.run(repo.c, A, auto=auto, last_good=resolve(repo, last_good), bad=(repo.c,))

    assert proc.returncode == 4, proc.stdout + proc.stderr
    assert any(line.startswith(f"되돌리지 않는다 — {why}") for line in proc.stderr.splitlines())
    assert "되돌렸다" not in proc.stderr
    assert srv.head() == repo.c  # 서버 폴더를 안 건드렸다
    assert srv.l_record() == []  # L 의 스크립트도 안 돌렸다
    assert srv.log().count("docker compose up -d") == 1
    assert "docker image prune -f" not in srv.log()


def test_main_up_d_가_실패해도_L_의_deploy_sh_로_되돌린다(server, repo):
    srv = server(repo.a1)

    proc = srv.run(
        repo.c,
        A,
        auto="1",
        last_good=repo.a1,
        env_extra={"FAKE_FAIL_PATTERN": "compose up -d", "FAKE_FAIL_TIMES": "1"},
    )

    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert srv.head() == repo.a1
    assert "ran-L-script" in srv.l_record()
    assert srv.log().count("docker compose up -d") == 1  # F 의 시도뿐


NGINX_RELOAD = "docker compose exec -T nginx nginx -s reload"
NGINX_RESTART = "docker compose restart nginx"


def test_main_떠_있는_nginx_가_reload_를_끝내_안_받으면_다시_시작하지_않고_되돌린다(server, repo):
    # reload 가 거절돼도 떠 있는 nginx 는 옛 설정으로 계속 돈다.
    # restart 하면 같은 이유로 못 떠서 /api 까지 죽는다
    srv = server(repo.a1)

    proc = srv.run(
        repo.c,
        A,
        auto="1",
        last_good=repo.a1,
        env_extra={"FAKE_FAIL_PATTERN": "nginx -s reload"},  # 횟수 제한 없이 계속 실패
    )

    assert proc.returncode == 3, proc.stdout + proc.stderr
    log = srv.log()
    assert log.count(NGINX_RELOAD) == 5
    assert NGINX_RESTART not in log
    assert "떠 있는 nginx 가 reload 를 끝내 받지 않았다" in proc.stdout
    assert srv.head() == repo.a1
    assert "ran-L-script" in srv.l_record()


def test_main_떠_있는_nginx_가_reload_를_끝내_안_받아도_롤백이_꺼져_있으면_4다(server, repo):
    srv = server(repo.a1)

    proc = srv.run(
        repo.c,
        A,
        auto="0",
        last_good=repo.a1,
        env_extra={"FAKE_FAIL_PATTERN": "nginx -s reload"},
    )

    assert proc.returncode == 4, proc.stdout + proc.stderr
    log = srv.log()
    assert log.count(NGINX_RELOAD) == 5
    assert NGINX_RESTART not in log
    assert "docker image prune -f" not in log
    assert srv.head() == repo.c  # 되돌리지 않았다
    assert srv.l_record() == []


def test_main_떠_있는_nginx_의_reload_가_처음_몇_번만_실패하면_다시_해_보고_통과한다(server, repo):
    # up -d 가 방금 다시 만든 nginx 는 아직 준비 전일 수 있다
    srv = server(repo.a1)

    proc = srv.run(
        repo.c,
        B,
        env_extra={"FAKE_FAIL_PATTERN": "nginx -s reload", "FAKE_FAIL_TIMES": "2"},
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    log = srv.log()
    assert log.count(NGINX_RELOAD) == 3  # 실패 둘 + 통과 하나
    assert NGINX_RESTART not in log
    assert "nginx reload 1/5 실패" in proc.stdout and "nginx reload 2/5 실패" in proc.stdout
    assert "nginx reload 3/5 실패" not in proc.stdout
    assert "배포 끝" in proc.stdout


def test_main_nginx_가_떠_있지_않으면_reload_없이_다시_시작한다(server, repo):
    # 재시작을 반복하는 nginx 는 exec 이 안 된다. up -d 는 그런 컨테이너를 건드리지 않는다
    srv = server(repo.a1)

    proc = srv.run(repo.c, B, env_extra={"FAKE_NGINX_DOWN": "1"})

    assert proc.returncode == 0, proc.stdout + proc.stderr
    log = srv.log()
    assert NGINX_RELOAD not in log
    ps = log.index("docker compose ps -q --status running nginx")
    assert log.index("docker compose up -d") < ps < log.index(NGINX_RESTART)
    assert log.index(NGINX_RESTART) < log.index("docker image prune -f")


def test_main_떠_있지_않던_nginx_를_다시_시작하지_못하면_되돌린다(server, repo):
    srv = server(repo.a1)

    proc = srv.run(
        repo.c,
        A,
        auto="1",
        last_good=repo.a1,
        env_extra={"FAKE_NGINX_DOWN": "1", "FAKE_FAIL_PATTERN": "restart nginx"},
    )

    assert proc.returncode == 3, proc.stdout + proc.stderr
    log = srv.log()
    assert NGINX_RELOAD not in log
    assert log.count(NGINX_RESTART) == 1
    assert "떠 있지 않던 nginx 를 다시 시작하지 못했다" in proc.stdout
    assert srv.head() == repo.a1
    assert "ran-L-script" in srv.l_record()


def test_main_nginx_를_다시_시작했어도_서버_안이_안_살아나면_성공으로_안_끝난다(server, repo):
    # restart 가 종료 0 이어도 nginx 가 못 뜰 수 있다 — 그건 서버 안 확인이 잡는다
    srv = server(repo.a1)

    proc = srv.run(repo.c, A, ready="503", last_good=repo.a1, env_extra={"FAKE_NGINX_DOWN": "1"})

    assert proc.returncode == 4, proc.stdout + proc.stderr
    log = srv.log()
    assert NGINX_RESTART in log and NGINX_RELOAD not in log
    assert "docker image prune -f" not in log
    assert "배포 끝" not in proc.stdout
    assert len(srv.curls()) == 3 * 2  # 서버 안 확인이 3번 다 돌았다
    assert srv.last_good() == repo.a1  # 성공 기록을 안 바꿨다


def test_main_nginx_상태를_못_읽으면_reload_도_restart_도_없이_되돌린다(server, repo):
    # 떠 있는지 모르는 nginx 를 다시 시작하지 않는다. 조회 실패는 swap_failed 를 한 번만 부른다
    srv = server(repo.a1)

    proc = srv.run(
        repo.c,
        A,
        auto="1",
        last_good=repo.a1,
        env_extra={"FAKE_FAIL_PATTERN": "compose ps -q --status running nginx"},
    )

    assert proc.returncode == 3, proc.stdout + proc.stderr
    log = srv.log()
    assert "docker compose ps -q --status running nginx" in log
    assert NGINX_RELOAD not in log and NGINX_RESTART not in log
    assert proc.stdout.count("교체한 서비스가 살아나지 않았다") == 1
    assert "nginx 상태를 읽지 못했다" in proc.stdout
    assert srv.head() == repo.a1
    assert "ran-L-script" in srv.l_record()


def test_교체_뒤_예상_밖_명령이_죽으면_4_앞이면_1이다(sh):
    # 교체 뒤 명령은 모두 `||` 로 받아서 실제 흐름으로는 안 닿는다. 마지막 안전망 on_err 를 본다
    before = sh("false")
    after = sh("swapped=1; false")

    assert before.returncode == 1 and "되돌리" not in before.stderr
    assert after.returncode == 4, after.stderr
    assert "되돌리지 않는다 — 교체 뒤 예상 밖 명령이 실패했다" in after.stderr


def test_die_는_swapped_로_1_이나_4를_고른다(sh):
    before = sh('die "멈춘다"')
    after = sh('swapped=1; die "멈춘다"')

    assert before.returncode == 1 and before.stdout == "멈춘다\n" and before.stderr == ""
    assert after.returncode == 4
    assert after.stdout == "멈춘다\n"
    assert after.stderr.splitlines() == ["되돌리지 않는다 — 멈춘다"]


def test_main_prune_이_실패해도_결과는_0이다(server, repo):
    srv = server(repo.a1)

    proc = srv.run(repo.c, B, env_extra={"FAKE_FAIL_PATTERN": "image prune"})

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert srv.last_good() == repo.c
    assert "배포 끝" in proc.stdout


def test_main_기록을_못_써도_결과는_0이다(server, repo, tmp_path):
    srv = server(repo.a1)

    proc = srv.run(repo.c, B, last_good_file=tmp_path / "no-such-dir" / "last-good")

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "직전 성공 기록을 쓰지 못했다" in proc.stdout
    assert "배포 끝" in proc.stdout


@pytest.mark.parametrize("case", ["성공", "되돌림", "L 이 실패", "못 되돌림", "교체 전 실패"])
def test_main_root_로_시작해도_ubuntu_쪽_종료_코드와_결과_줄이_그대로_나온다(server, repo, case):
    # SSM 은 root 로 돈다. root → runuser → ubuntu 를 지나다 3 · 4 가 1 로 뭉개지면 알림이 틀리고,
    # AUTO_ROLLBACK 이 안 넘어가면 되돌려야 할 때 4 가 나온다.
    # 되돌리기(L 의 스크립트)도 이 경로에서 돈다
    srv = server(repo.a1)
    rollback = {"auto": "1", "last_good": repo.a1, "bad": (repo.c,)}
    kwargs, code, head, last = {
        "성공": ({}, 0, repo.c, None),
        "되돌림": (rollback, 3, repo.a1, f"되돌렸다 → {repo.a1} (L 의 deploy.sh)"),
        "L 이 실패": (
            {**rollback, "l_exit": 1},
            4,
            repo.a1,
            "되돌리기도 실패 — L 의 deploy.sh 가 1 로 끝났다",
        ),
        "못 되돌림": (
            {"bad": (repo.c,)},
            4,
            repo.c,
            "되돌리지 않는다 — 자동 롤백이 꺼져 있다 (손 배포는 AUTO_ROLLBACK=1)",
        ),
        "교체 전 실패": ({"db_fail": True}, 1, repo.a1, None),
    }[case]

    proc = srv.run(repo.c, A, as_root=True, **kwargs)

    assert proc.returncode == code, proc.stdout + proc.stderr
    assert srv.head() == head  # 가짜 runuser 를 지나 진짜 main 이 돌았다
    if last is not None:
        assert proc.stderr.splitlines()[-1] == last
    if case in ("되돌림", "L 이 실패"):  # 이 둘만 L 의 스크립트가 돈다
        assert srv.l_record()[:3] == ["ran-L-script", f"DEPLOY_REF={repo.a1}", "AUTO_ROLLBACK=0"]


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


def test_스크립트_맨_끝은_main_바로_뒤에_exit_다():
    # 배포 도중 checkout 이 이 파일을 바꿔도 bash 가 뒷부분을 더 읽지 않게 한다(하민 리뷰 9번)
    last = DEPLOY_SH.read_text().rstrip().splitlines()[-1]

    assert re.fullmatch(r'if ! \(return 0 2>/dev/null\); then main "\$@"; exit; fi', last)


def test_git_fetch_는_서버_잠금_fd_9_를_닫고_부른다():
    # fetch 가 백그라운드로 띄우는 `git gc --auto` 는 fd 9 를 물려받아, 부모가 `exec 9>&-` 로
    # 잠금을 풀어도 끝날 때까지 잠금을 쥔다. git 에게만 fd 9 를 닫아 넘긴다(하민 3차 리뷰 4번)
    fetches = [
        line.strip()
        for line in DEPLOY_SH.read_text().splitlines()
        if line.strip().startswith("git fetch")
    ]

    assert fetches
    assert all(line.endswith(" 9>&-") for line in fetches), fetches
