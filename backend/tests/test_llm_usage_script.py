"""LLM 사용량 스크립트 (scripts/llm-usage.sh).

배포로 컨테이너가 바뀌어도 사용량을 볼 수 있어야 한다 — journald 에서 읽는지와
날짜별 토큰 합계를 함께 본다. 진짜 sudo · journalctl · docker 대신 가짜 명령을 쓴다.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

LLM_USAGE_SH = Path(__file__).resolve().parents[2] / "scripts" / "llm-usage.sh"

FAKES = {
    "sudo": '#!/bin/sh\nexec "$@"\n',
    "journalctl": """#!/bin/sh
printf '%s\\n' "$@" > "$FAKE_ARGS"
cat "$FAKE_LOG"
""",
    "docker": """#!/bin/sh
printf '%s\\n' "$@" > "$FAKE_DOCKER"
exit 1
""",
}

# client.py 의 app.server 로거와 main.py 의 로그 형식
USAGE = (
    "2026-10-29 14:22:07,123 INFO app.server "
    "llm_usage model=openai/gpt-6.1-sol prompt=100 completion=20 total=120\n"
)


@pytest.fixture
def run_usage(tmp_path):
    """가짜 journald 로그로 스크립트를 돌리고 실행 결과와 명령 기록을 준다."""
    fake = tmp_path / "bin"
    fake.mkdir()
    for name, body in FAKES.items():
        p = fake / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "journal.log"
    args = tmp_path / "journal-args"
    docker = tmp_path / "docker-args"

    def run(*arguments: str, log_text: str = USAGE):
        log.write_text(log_text)
        env = {
            **os.environ,
            "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}",
            "FAKE_ARGS": str(args),
            "FAKE_LOG": str(log),
            "FAKE_DOCKER": str(docker),
        }
        proc = subprocess.run(
            ["bash", str(LLM_USAGE_SH), *arguments],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc, args, docker

    return run


def test_지정한_기간을_journalctl에_넘긴다(run_usage):
    """24시간의 backend 로그를 원문으로 읽는다."""
    proc, args, _ = run_usage("24h")

    assert proc.returncode == 0, proc.stderr
    received = args.read_text().splitlines()
    assert "CONTAINER_TAG=ssample-backend" in received
    assert received[received.index("--since") + 1] == "-24h"
    assert received[received.index("-o") + 1] == "cat"
    assert "--no-pager" in received


def test_기간을_생략하면_7일을_읽는다(run_usage):
    """기간 인자가 없으면 journalctl 에 168시간을 넘긴다."""
    proc, args, _ = run_usage()

    assert proc.returncode == 0, proc.stderr
    received = args.read_text().splitlines()
    assert received[received.index("--since") + 1] == "-168h"


def test_docker_로그로_돌아가지_않는다(run_usage):
    """배포 때 사라지는 컨테이너 로그를 읽지 않는다."""
    proc, _, docker = run_usage()

    assert not docker.exists()
    assert proc.returncode == 0, proc.stderr


def test_사용량만_날짜별로_합산한다(run_usage):
    """다른 로그를 빼고 날짜별 호출 수와 토큰 수를 더한다."""
    logs = (
        USAGE + "2026-10-29 15:00:00,000 ERROR app.server unexpected_error prompt=999 "
        "completion=999 total=1998\n" + "2026-10-29 16:00:00,000 INFO app.server llm_usage "
        "model=openai/gpt-6.1-sol prompt=30 completion=40 total=70\n"
        + "2026-10-30 09:00:00,000 INFO app.server llm_usage "
        "model=openai/gpt-6.1-sol prompt=7 completion=8 total=15\n"
    )
    proc, _, _ = run_usage(log_text=logs)

    assert proc.returncode == 0, proc.stderr
    rows = [line.split() for line in proc.stdout.splitlines()]
    days = {row[0]: row[1:5] for row in rows if row and row[0].startswith("2026-")}
    assert days == {
        "2026-10-29": ["2", "130", "60", "190"],
        "2026-10-30": ["1", "7", "8", "15"],
    }
    assert any(row[:6] == ["─", "합계", "3", "137", "68", "205"] for row in rows)


def test_사용량이_없으면_journald_안내를_보여준다(run_usage):
    """사용량 줄이 없을 때 journald 를 아직 켜지 않았을 수 있음을 알린다."""
    proc, _, _ = run_usage(log_text="2026-10-29 15:00:00,000 ERROR app.server unexpected_error\n")

    assert any(
        line.startswith("llm_usage 줄이 없다") and "journald" in line
        for line in proc.stdout.splitlines()
    )
