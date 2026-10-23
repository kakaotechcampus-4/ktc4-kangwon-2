"""LLM 실측이 읽는 INFO 줄이 기본 서버 설정에서 실제로 나가는지 본다 (Codex W7a2-01).

pytest 는 로그 수준을 따로 만지므로, 앱을 **새 프로세스에서** 아무 설정 없이 불러와 확인한다 —
배포의 Uvicorn 과 같은 조건이다.
"""

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

PROBE = """
import logging
import app.main  # noqa: F401 — 서버가 뜰 때와 같이 로그 설정을 탄다
transport = logging.getLogger("app.features.plans.monthly_llm")
transport.info("probe-transport schema=weekly_plan_proposal")
logging.getLogger("ssuksak.planning.planner.weekly").info("probe-planner repaired=0")
transport.debug("probe-debug-must-not-show")
"""


def test_전송_성공과_주간_성공_로그가_기본_설정에서_나간다():
    env = {**os.environ, "SECRET_KEY": os.environ.get("SECRET_KEY", "test-only-not-a-secret")}
    done = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    assert "probe-transport schema=weekly_plan_proposal" in done.stderr
    assert "probe-planner repaired=0" in done.stderr
    # 수준을 INFO 로만 연다 — DEBUG 까지 열지 않는다.
    assert "probe-debug-must-not-show" not in done.stderr
