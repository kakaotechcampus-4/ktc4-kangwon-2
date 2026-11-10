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
import re
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
    # FAKE_CALL_PLAN("r e e r …") 은 호출마다 읽기(r) 아니면 오류(e)를 정한다.
    # 끝나면 마지막 토큰을 따른다
    plan = os.environ.get("FAKE_CALL_PLAN", "").split()
    plan_error = bool(plan) and plan[min(n - fail_first, len(plan) - 1)] == "e"
    if plan_error or n - fail_first >= int(os.environ.get("FAKE_ERROR_AFTER", "999")):
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


def test_처음_읽기_전의_InvocationDoesNotExist_는_세지_않는다(ssm):
    # 보낸 직후 명령이 아직 등록되지 않은 정상이다. 네 번을 넘겨도 포기하지 않는다
    proc = ssm("Success", FAKE_CODE="0", FAKE_GET_FAIL_FIRST="6", SSM_WAIT_TRIES="50")

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert ssm.polls() == 7


@pytest.mark.parametrize("errors", [1, 2, 3])
def test_처음_읽기_전의_일시_오류도_세_번까지는_다시_물어_본다(ssm, errors):
    # send-command 가 성공했으면 서버는 이미 명령을 받았다.
    # 첫 조회의 네트워크 · throttling 오류에 1 로 끝내면 안 된다
    proc = ssm(
        "Success",
        FAKE_CODE="0",
        FAKE_GET_FAIL_FIRST=str(errors),
        FAKE_FAIL_TEXT="ThrottlingException",
        SSM_WAIT_TRIES="50",
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert ssm.polls() == errors + 1


@pytest.mark.parametrize("text", ["AccessDeniedException", "ThrottlingException"])
def test_처음_읽기_전에도_조회_오류가_연속_네_번째면_오류를_찍고_124다(ssm, text):
    # 예전에는 첫 조회의 InvocationDoesNotExist 아닌 오류가 바로 1 이었다. 서버는 이미 돌고 있다
    proc = ssm("Success", FAKE_GET_FAIL_FIRST="99", FAKE_FAIL_TEXT=text, SSM_WAIT_TRIES="50")

    assert proc.returncode == 124, proc.stdout + proc.stderr
    assert text in proc.stdout
    assert "서버는 아직 돌 수 있다" in proc.stdout
    assert ssm.polls() == 4  # 오류 4번(세 번 다시 물었다). 50번 다 묻지 않았다


def test_처음_읽기_전_오류의_세기도_읽기에_성공하면_다시_시작한다(ssm):
    # 오류 3번 → 읽기(InProgress) → 오류 3번 → 읽기.
    # 처음 읽기 전의 3번도 합쳐서 6번이지만 연속은 3번뿐이다
    proc = ssm(
        "InProgress InProgress InProgress InProgress InProgress InProgress InProgress Success",
        FAKE_CODE="0",
        FAKE_CALL_PLAN="e e e r e e e r",
        SSM_WAIT_TRIES="50",
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert ssm.polls() == 8


def test_상태가_바뀔_때와_6번째_조회마다_대기_줄을_stdout_에_찍는다(ssm):
    statuses = "Pending InProgress InProgress InProgress InProgress InProgress InProgress Success"
    proc = ssm(statuses, FAKE_CODE="0", SSM_WAIT_TRIES="50")

    assert proc.returncode == 0, proc.stdout + proc.stderr
    waits = [line for line in proc.stdout.splitlines() if line.startswith("대기 — ")]
    assert waits == [
        "대기 — 상태 Pending (1/50)",  # 처음 읽은 상태
        "대기 — 상태 InProgress (2/50)",  # 바뀔 때
        "대기 — 상태 InProgress (6/50)",  # 6번째 조회마다(약 1분) — 바뀌지 않아도
    ]
    assert proc.stderr == ""  # stdout 으로만 나간다


def test_읽기_전에는_상태_대신_못_읽음을_알린다(ssm):
    proc = ssm("Success", FAKE_CODE="0", FAKE_GET_FAIL_FIRST="2", SSM_WAIT_TRIES="50")

    waits = [line for line in proc.stdout.splitlines() if line.startswith("대기 — ")]
    assert waits == ["대기 — 아직 상태를 못 읽음 (1/50)"]  # 바뀐 것은 한 번뿐. 읽은 뒤 끝났다


def test_대기_줄은_deploy_yml_이_뽑는_결과_줄_접두사로_시작하지_않는다(ssm):
    # deploy.yml 의 결과 줄 `grep -E '^(되돌렸다 → |…)'` 와 겹치면 알림이 대기 줄을 집어 간다
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    match = re.search(r"grep -E '(\^\([^']*\))'", workflow)
    assert match, "deploy.yml 에서 결과 줄 grep 을 못 찾았다"
    result_line = re.compile(match.group(1))
    statuses = "Pending InProgress InProgress InProgress InProgress InProgress InProgress Success"

    proc = ssm(statuses, FAKE_CODE="0", SSM_WAIT_TRIES="50")

    waits = [line for line in proc.stdout.splitlines() if line.startswith("대기 — ")]
    assert waits and not any(result_line.match(line) for line in proc.stdout.splitlines())


@pytest.mark.parametrize("errors", [1, 2, 3])
def test_상태를_읽은_뒤_일시_오류_세_번까지는_다시_물어_본다(ssm, errors):
    # 서버 명령은 이미 돌고 있다. 네트워크 끊김 · throttling 한 번에 run 을 1 로 끝내면 안 된다
    plan = "r " + "e " * errors + "r"
    proc = ssm(
        "InProgress InProgress Success", FAKE_CODE="0", FAKE_CALL_PLAN=plan, SSM_WAIT_TRIES="50"
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert ssm.polls() == 2 + errors


def test_일시_오류는_읽기에_성공할_때마다_세기를_다시_시작한다(ssm):
    # 오류 3번 → 읽기 → 오류 3번 → 읽기. 합치면 6번이지만 연속은 3번뿐이다
    proc = ssm(
        "InProgress InProgress InProgress InProgress InProgress InProgress InProgress Success",
        FAKE_CODE="0",
        FAKE_CALL_PLAN="r e e e r e e e r",
        SSM_WAIT_TRIES="50",
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert ssm.polls() == 9


@pytest.mark.parametrize(
    "text", ["An error occurred (AccessDeniedException)", "InvocationDoesNotExist"]
)
def test_상태를_읽은_뒤_조회_오류가_연속_네_번째면_오류를_찍고_124다(ssm, text):
    # 서버는 아직 돌 수 있다 — 1 이 아니라 124.
    # 이미 읽은 명령에 InvocationDoesNotExist 가 나와도 보통 오류로 센다
    proc = ssm("InProgress", FAKE_ERROR_AFTER="1", FAKE_ERROR_TEXT=text, SSM_WAIT_TRIES="50")

    assert proc.returncode == 124, proc.stdout + proc.stderr
    assert text in proc.stdout  # AWS 오류 글
    assert "서버는 아직 돌 수 있다" in proc.stdout
    assert ssm.polls() == 5  # 읽기 1번 + 오류 4번(세 번 다시 물었다). 50번 다 묻지 않았다


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("3", 3),  # deploy.sh: 교체 뒤 실패했고 직전 성공으로 되돌렸다
        ("4", 4),  # deploy.sh: 교체 뒤 실패했고 못 되돌렸다
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


def test_취소하는_중에는_끝날_때까지_더_기다린다(ssm):
    # Cancelling 은 아직 끝난 것이 아니다. 끝난 것으로 치면 서버가 아직 도는데 125 로 손을 뗀다
    proc = ssm("InProgress Cancelling Cancelled", FAKE_CODE="-1")

    assert proc.returncode == 125, proc.stdout + proc.stderr
    assert ssm.polls() == 3


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
    assert parameters["commands"][2] == "export AUTO_ROLLBACK=0"  # 안 주면 꺼진다
    assert parameters["commands"][3] == DEPLOY_SH.read_text()
    # 잠금 300초 + 배포 + 되돌리기가 한 명령 안에 든다. 러너 대기(280번 × 10초)가 이보다 길다
    assert parameters["executionTimeout"] == ["2700"]


def test_AUTO_ROLLBACK_은_서버로_넘어간다(ssm):
    proc = ssm("Success", FAKE_CODE="0", AUTO_ROLLBACK="1")
    assert proc.returncode == 0, proc.stdout + proc.stderr

    parameters = json.loads(ssm.sent()[ssm.sent().index("--parameters") + 1])
    assert parameters["commands"][1:3] == [f"export DEPLOY_REF={SHA}", "export AUTO_ROLLBACK=1"]


@pytest.mark.parametrize("value", ["2", "true", "1; rm -rf /", " 1", "01"])
def test_AUTO_ROLLBACK_이_0_1_이_아니면_보내지_않는다(ssm, value):
    # 이 값은 서버에서 도는 셸 줄(`export AUTO_ROLLBACK=…`)에 그대로 들어간다
    proc = ssm("Success", FAKE_CODE="0", AUTO_ROLLBACK=value)

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "AUTO_ROLLBACK 은 0 이나 1 이다" in proc.stdout
    with pytest.raises(FileNotFoundError):
        ssm.sent()  # send-command 를 부르지 않았다


def test_올릴_커밋을_안_주면_보내지_않는다():
    proc = subprocess.run(
        ["bash", str(SSM_DEPLOY_SH)],
        env={**os.environ, "INSTANCE_ID": "i-test"},
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert proc.returncode == 1
