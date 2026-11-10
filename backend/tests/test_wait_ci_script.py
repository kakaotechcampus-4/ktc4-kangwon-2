"""push 배포 전에 같은 커밋의 CI 를 기다리는 스크립트.

`scripts/wait-ci.sh` · deploy.yml 「CI 기다리기」.

이 스크립트가 틀리면 둘 중 하나다 — 빨간 CI 커밋이 운영에 나가거나, 멀쩡한 배포가 멈춘다.
앞쪽이 막으려던 사고라서, 성공이 아닌 결과는 전부 막히는지를 본다.

진짜 gh 는 부르지 않는다. 가짜 `gh` 를 PATH 앞에 두고, 호출마다 정해 둔 줄을 하나씩 준다
(진짜 gh 는 --jq 로 「status|conclusion|url」 한 줄을 찍는다). `ERR` 줄은 조회 실패(종료 1)다.
"""

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WAIT_CI_SH = ROOT / "scripts" / "wait-ci.sh"
STILL_TIP_SH = ROOT / "scripts" / "still-tip.sh"

SHA = "0123456789abcdef0123456789abcdef01234567"
URL = "https://github.com/o/r/actions/runs/1"

# FAKE_LINES 파일의 줄을 호출마다 하나씩 준다. 다 쓰면 마지막 줄을 계속 준다.
# 인자는 FAKE_ARGS 에 적는다.
FAKE_GH = f"""#!{sys.executable}
import os, sys
with open(os.environ["FAKE_ARGS"], "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1] == "api":  # 브랜치 끝 조회 — FAKE_TIP 을 준다
    tip = os.environ["FAKE_TIP"]
    if tip == "ERR":
        sys.exit(1)
    print(tip)
    sys.exit(0)
lines = open(os.environ["FAKE_LINES"]).read().splitlines()
count_file = os.environ["FAKE_COUNT"]
n = int(open(count_file).read()) if os.path.exists(count_file) else 0
open(count_file, "w").write(str(n + 1))
line = lines[min(n, len(lines) - 1)]
if line == "ERR":
    sys.exit(1)
print(line)
"""


@pytest.fixture
def run(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    output = tmp_path / "github-output"
    args = tmp_path / "gh-args"

    def go(*lines: str, tries: int = 10, tip: str = "f" * 40, script: Path = WAIT_CI_SH):
        (tmp_path / "lines").write_text("\n".join(lines) + "\n")
        proc = subprocess.run(
            ["bash", str(script), SHA],
            env={
                **os.environ,
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                "GITHUB_REPOSITORY": "o/r",
                "GITHUB_REF_NAME": "main",
                "FAKE_TIP": tip,
                "GITHUB_OUTPUT": str(output),
                "WAIT_TRIES": str(tries),
                "WAIT_INTERVAL": "0",
                "TIP_RETRY_INTERVAL": "0",
                "FAKE_LINES": str(tmp_path / "lines"),
                "FAKE_COUNT": str(tmp_path / "count"),
                "FAKE_ARGS": str(args),
            },
            capture_output=True,
            text=True,
            timeout=30,
        )
        written = output.read_text().splitlines() if output.exists() else []
        outputs = dict(line.split("=", 1) for line in written)
        calls = args.read_text().splitlines() if args.exists() else []
        calls = [c for c in calls if not c.startswith("api ")]  # run list 호출만 센다
        return proc, outputs, calls

    return go


def test_CI_가_성공으로_끝나면_올린다(run):
    proc, out, calls = run("queued||", "in_progress||", f"completed|success|{URL}")

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out == {"ok": "true", "url": URL}
    assert len(calls) == 3  # 끝날 때까지 다시 물었다


def test_같은_커밋의_push_CI_만_본다(run):
    _, _, calls = run(f"completed|success|{URL}")

    assert f"--commit {SHA}" in calls[0]
    assert "--branch main" in calls[0]
    assert "--event push" in calls[0]
    assert "--workflow ci.yml" in calls[0]


@pytest.mark.parametrize(
    "conclusion", ["failure", "timed_out", "skipped", "action_required", "startup_failure", ""]
)
def test_성공도_취소도_아니면_막는다(run, conclusion):
    proc, out, _ = run(f"completed|{conclusion}|{URL}")

    assert proc.returncode == 1
    assert out["ok"] == "false"
    assert out["url"] == URL  # 알림에 실패한 CI 주소를 싣는다


def test_더_새_push_가_취소한_CI_는_조용히_건너뛴다(run):
    # 브랜치 끝이 이미 다른 커밋이다 — 실패가 아니다. 뒤 배포 run 이 올린다
    proc, out, _ = run(f"completed|cancelled|{URL}", tip="f" * 40)

    assert proc.returncode == 0
    assert out["ok"] == "false"


@pytest.mark.parametrize("tip", [SHA, "ERR"])
def test_뒤따를_배포가_없는_취소는_막는다(run, tip):
    # 손으로 취소했거나 job 시간 초과 — 브랜치 끝이 아직 이 커밋이거나 끝을 못 읽었다.
    # 건너뛰면 아무도 올리지 않고 알림도 없다
    proc, out, _ = run(f"completed|cancelled|{URL}", tip=tip)

    assert proc.returncode == 1
    assert out["ok"] == "false"


def test_조회가_실패하거나_run_이_아직_없어도_다시_묻는다(run):
    proc, out, calls = run("ERR", "", "ERR", f"completed|success|{URL}")

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out["ok"] == "true"
    assert len(calls) == 4


def test_시간_안에_안_끝나면_막는다(run):
    proc, out, calls = run("in_progress||", tries=3)

    assert proc.returncode == 1
    assert out["ok"] == "false"
    assert len(calls) == 3


# 아래는 deploy job 이 잠금을 얻은 뒤 서버를 바꾸기 직전에 부르는 확인(scripts/still-tip.sh)이다.
# 「CI 기다리기」는 잠금 밖이라, 그 사이 더 새 push 가 먼저 올라갔을 수 있다(하민 리뷰 #549 P2).


def test_아직_브랜치_끝이면_올린다(run):
    proc, out, _ = run(tip=SHA, script=STILL_TIP_SH)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out == {"stale": "false"}


def test_더_새_push_가_있으면_옛_커밋은_올리지_않는다(run):
    proc, out, _ = run(tip="f" * 40, script=STILL_TIP_SH)

    assert proc.returncode == 0
    assert out == {"stale": "true"}


def test_브랜치_끝을_못_읽으면_막는다(run):
    proc, out, _ = run(tip="ERR", script=STILL_TIP_SH)

    assert proc.returncode == 1
    assert "stale" not in out


def test_성공했지만_대체된_커밋은_배포하지_않는다(run):
    # 하민 리뷰 #549 P2 재현: A 의 CI 는 성공했는데 조회가 두 번 실패하는 사이 B 가 main 끝이 됐다.
    # 「CI 기다리기」는 성공만 보고 ok=true 를 낸다 — 막는 것은 잠금 안의 still-tip 이다
    proc, out, _ = run("ERR", "ERR", f"completed|success|{URL}", tip="f" * 40)
    assert (proc.returncode, out["ok"]) == (0, "true")

    proc, out, _ = run(tip="f" * 40, script=STILL_TIP_SH)
    assert out["stale"] == "true"
