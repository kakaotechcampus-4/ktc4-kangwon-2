"""러너에서 서버로 배포 명령을 보내고 기다리는 스크립트 (scripts/ssm-deploy.sh · ADR-078).

이 스크립트의 종료 코드가 deploy.yml 의 자동 롤백을 움직인다 — 서버의 deploy.sh 가 낸 숫자(특히 3)가
그대로 나와야 하고, 이 스크립트가 3 을 따로 만들어 내서는 안 된다. 서버 명령이 끝나지 않았거나(124)
취소됐으면(125) 롤백 판정에서 3 과 달라야 한다.

진짜 aws 는 부르지 않는다. 가짜 `aws` 를 PATH 앞에 두고 스크립트를 통째로 돌린다.
가짜는 send-command 의 인자를 파일에 적고, get-command-invocation 에는 정해 둔 상태를
차례로 준다. jq 는 진짜를 쓴다.
"""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SSM_DEPLOY_SH = ROOT / "scripts" / "ssm-deploy.sh"
DEPLOY_SH = ROOT / "scripts" / "deploy.sh"

SHA = "0123456789abcdef0123456789abcdef01234567"

# FAKE_STATUSES(공백으로 나눈 목록)를 get-command-invocation 호출마다 하나씩 준다.
# 끝나면 마지막을 계속 준다. FAKE_CODE 는 ResponseCode 에 넣을 JSON 값이다(3 · "x" · -1).
FAKE_AWS = f"""#!{sys.executable}
import json, os, sys

args = sys.argv[1:]
state = os.environ["FAKE_AWS_STATE"]

def bump():
    try:
        n = int(open(state + "/count").read())
    except OSError:
        n = 0
    open(state + "/count", "w").write(str(n + 1))
    return n

if args[:2] == ["ssm", "send-command"]:
    json.dump(args, open(state + "/send.json", "w"))
    if os.environ.get("FAKE_SEND_FAIL"):
        print("AccessDeniedException", file=sys.stderr)
        sys.exit(254)
    print("cmd-123")
elif args[:2] == ["ssm", "get-command-invocation"]:
    n = bump()
    fail_first = int(os.environ.get("FAKE_GET_FAIL_FIRST", "0"))
    if n < fail_first:
        # 보낸 직후에는 응답이 아직 없다. FAKE_FAIL_TEXT 로 다른 오류도 흉내 낸다
        print(os.environ.get("FAKE_FAIL_TEXT", "InvocationDoesNotExist"), file=sys.stderr)
        sys.exit(254)
    if n - fail_first >= int(os.environ.get("FAKE_ERROR_AFTER", "999")):
        text = os.environ.get("FAKE_ERROR_TEXT", "An error occurred (AccessDeniedException)")
        print(text, file=sys.stderr)
        sys.exit(254)  # 상태를 몇 번 읽은 뒤에 나는 오류
    if os.environ.get("FAKE_RAW"):
        print(os.environ["FAKE_RAW"])
        sys.exit(0)
    statuses = os.environ["FAKE_STATUSES"].split()
    status = statuses[min(n - fail_first, len(statuses) - 1)]
    print(json.dumps({{
        "Status": status,
        "ResponseCode": json.loads(os.environ.get("FAKE_CODE", "-1")),
        "StandardOutputContent": "서버 출력 줄\\n",
        "StandardErrorContent": "서버 오류 줄\\n",
    }}))
else:
    sys.exit(2)
"""


# 예상 밖 명령 노릇을 한다. FAKE_SLEEP_EXIT 로 어떤 코드로 죽을지 정한다.
FAKE_SLEEP = '#!/bin/sh\nexit "${FAKE_SLEEP_EXIT:-0}"\n'


@pytest.fixture
def ssm(tmp_path):
    """ssm-deploy.sh 를 SHA 하나로 돌려 CompletedProcess 를 준다. 가짜 aws 는 env 로 고른다."""
    fake = tmp_path / "bin"
    fake.mkdir()
    for name, body in {"aws": FAKE_AWS, "sleep": FAKE_SLEEP}.items():
        p = fake / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    state = tmp_path / "state"
    state.mkdir()

    def run(statuses: str, **env_extra: str) -> subprocess.CompletedProcess:
        env = {
            **os.environ,
            "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}",
            "INSTANCE_ID": "i-test",
            "FAKE_AWS_STATE": str(state),
            "FAKE_STATUSES": statuses,
            "SSM_WAIT_TRIES": "4",
            "SSM_WAIT_INTERVAL": "0",
            **env_extra,
        }
        return subprocess.run(
            ["bash", str(SSM_DEPLOY_SH), SHA],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    run.sent = lambda: json.loads((state / "send.json").read_text())
    run.polls = lambda: int((state / "count").read_text())
    return run


def test_성공하면_0이고_서버_출력을_보여_준다(ssm):
    proc = ssm("Success", FAKE_CODE="0")

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "배포 명령 cmd-123" in proc.stdout
    assert "서버 출력 줄" in proc.stdout and "서버 오류 줄" in proc.stdout
    assert "상태 Success" in proc.stdout


def test_끝날_때까지_다시_묻는다(ssm):
    proc = ssm("Pending InProgress Delayed Success", FAKE_CODE="0")

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert ssm.polls() == 4


def test_보낸_직후_InvocationDoesNotExist_는_다시_물어_본다(ssm):
    proc = ssm("Success", FAKE_CODE="0", FAKE_GET_FAIL_FIRST="2")

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert ssm.polls() == 3  # 두 번 물러서고 세 번째에 읽었다


def test_다른_조회_오류는_다시_묻지_않고_오류_글을_찍고_1이다(ssm):
    # 권한이 없는데 InvocationDoesNotExist 처럼 재시도하면 30분을 기다리고 124 로 끝난다
    proc = ssm("Success", FAKE_GET_FAIL_FIRST="99", FAKE_FAIL_TEXT="AccessDeniedException")

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "AccessDeniedException" in proc.stdout
    assert ssm.polls() == 1


def test_상태를_읽은_뒤_조회가_오류로_바뀌면_기다리지_않고_1이다(ssm):
    # 한 번 InProgress 를 본 뒤 오류만 나온다. 마지막에 본 상태를 계속 쓰면 124 가 된다
    proc = ssm("InProgress", FAKE_ERROR_AFTER="1", SSM_WAIT_TRIES="50")

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "AccessDeniedException" in proc.stdout
    assert ssm.polls() == 2  # 50번 다 묻지 않았다


def test_InvocationDoesNotExist_재시도는_처음_한_번도_못_읽었을_때만이다(ssm):
    # 이미 상태를 읽은 명령이 갑자기 없다고 하면 이상한 것이다 — 기다리지 않고 1
    proc = ssm(
        "InProgress",
        FAKE_ERROR_AFTER="1",
        FAKE_ERROR_TEXT="InvocationDoesNotExist",
        SSM_WAIT_TRIES="50",
    )

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert ssm.polls() == 2


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("3", 3),  # deploy.sh: 교체 뒤 서버 안에서 안 살아났다 — 자동 롤백 신호
        ("1", 1),
        ("255", 255),
        ('"abc"', 1),  # 정수가 아니다
        ("-1", 1),  # 서버 명령이 못 시작됐다
        ("0", 1),  # Failed 인데 0 으로 새면 성공으로 읽힌다
        ("256", 1),
        ("null", 1),
    ],
)
def test_실패하면_서버_종료_코드를_그대로_낸다(ssm, code, expected):
    proc = ssm("Failed", FAKE_CODE=code)

    assert proc.returncode == expected, proc.stdout + proc.stderr


@pytest.mark.parametrize("status", ["Cancelled", "TimedOut", "ExecutionTimedOut"])
def test_취소되거나_시간_초과면_125다(ssm, status):
    # 서버 안 확인 실패(3)와 달라야 한다 — 서버가 어떤 상태인지 모르니 롤백하지 않고 사람이 본다
    proc = ssm(status, FAKE_CODE="-1")

    assert proc.returncode == 125, proc.stdout + proc.stderr


def test_기다린_시간_안에_안_끝나면_124다(ssm):
    proc = ssm("InProgress", FAKE_CODE="-1")

    assert proc.returncode == 124, proc.stdout + proc.stderr
    assert ssm.polls() == 4  # SSM_WAIT_TRIES
    assert "서버는 아직 돌 수 있다" in proc.stdout


def test_명령을_못_보내면_1이다(ssm):
    proc = ssm("Success", FAKE_SEND_FAIL="1")

    assert proc.returncode == 1
    assert "배포 명령을 보내지 못했다" in proc.stdout


def test_상태를_한_번도_못_읽으면_1이다(ssm):
    proc = ssm("Success", FAKE_GET_FAIL_FIRST="99")

    assert proc.returncode == 1
    assert "상태를 한 번도 읽지 못했다" in proc.stdout


def test_예상_밖_명령이_3으로_죽어도_1이다(ssm):
    # 서버의 3(교체 뒤 안 살아남)과 섞이면 멀쩡한 서버를 되감는다
    proc = ssm("InProgress Success", FAKE_CODE="0", FAKE_SLEEP_EXIT="3")

    assert proc.returncode == 1, proc.stdout + proc.stderr


@pytest.mark.parametrize("raw", ["not json", "{}", '{"Status": null}'])
def test_응답을_해석하지_못하면_1이다(ssm, raw):
    # jq 는 해석에 실패하면 2 나 3 같은 자기 코드를 낸다. 서버의 3 과 섞이면 안 된다
    proc = ssm("Success", FAKE_RAW=raw)

    assert proc.returncode == 1, proc.stdout + proc.stderr


def test_보내는_명령의_첫_줄이_쉬뱅이고_deploy_sh_를_통째로_담는다(ssm):
    proc = ssm("Success", FAKE_CODE="0")
    assert proc.returncode == 0, proc.stdout + proc.stderr

    args = ssm.sent()
    value = lambda flag: args[args.index(flag) + 1]  # noqa: E731
    assert value("--instance-ids") == "i-test"
    assert value("--document-name") == "AWS-RunShellScript"
    assert value("--comment") == f"deploy {SHA}"
    parameters = json.loads(value("--parameters"))
    # 첫 원소가 쉬뱅이 아니면 SSM 이 sh(dash)로 돌려서 pipefail 에서 죽는다
    # (scripts/deploy.sh 머리 주석)
    assert parameters["commands"][0] == "#!/usr/bin/env bash"
    assert parameters["commands"][1] == f"export DEPLOY_REF={SHA}"
    assert parameters["commands"][2] == DEPLOY_SH.read_text()
    assert parameters["executionTimeout"] == ["1800"]


def test_올릴_커밋을_안_주면_보내지_않는다():
    proc = subprocess.run(
        ["bash", str(SSM_DEPLOY_SH)],
        env={**os.environ, "INSTANCE_ID": "i-test"},
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert proc.returncode == 1
