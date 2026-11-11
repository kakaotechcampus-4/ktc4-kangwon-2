"""밖에서 공개 주소를 보고 서비스가 내려갔는지 알리는 스크립트.

`scripts/uptime-check.sh` · .github/workflows/uptime.yml.

이 스크립트가 틀리면 둘 중 하나다 — 서비스가 죽었는데 아무도 모르거나,
멀쩡한데(배포 중 · 한 번 튀는 실패) 알림이 울려 팀이 알림을 믿지 않게 된다.
그래서 판정표 한 줄 한 줄과, gh 를 못 읽었을 때 어느 쪽으로 기우는지를 본다.

진짜 curl · gh 는 부르지 않는다. 가짜 `curl` · `gh` 를 PATH 앞에 둔다.
- 가짜 curl: 주소마다 「몇 번째로 물었나」에 따라 정해 둔 코드를 준다
  (`ERR` 은 닿지도 못한 것). `-X POST`(알림 전송)는 보낼 내용만 적는다.
- 가짜 gh: 정해 둔 JSON 을 진짜 jq 로 `--jq` 식에 통과시킨다 — 식이 틀려도 잡힌다.
  `ERR` 은 조회 실패(404 따위)다.
"""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
UPTIME_SH = ROOT / "scripts" / "uptime-check.sh"

BASE = "https://site.test"
RUN_URL = "https://github.com/o/r/actions/runs/300"

# FAKE_ROUNDS 의 n 번째 줄이 n 번째로 묻는 응답이다(「`/` 코드 `/health/ready` 코드」).
# 다 쓰면 마지막 줄을 계속 준다.
FAKE_CURL = f"""#!{sys.executable}
import json, os, sys
args = sys.argv[1:]
if "-X" in args:  # 알림 전송
    with open(os.environ["FAKE_POSTS"], "a") as f:
        payload = json.loads(args[args.index("-d") + 1])
        f.write(json.dumps(payload) + "\\n")
    sys.exit(22 if os.environ.get("FAKE_POST_FAIL") else 0)
with open(os.environ["FAKE_PROBES"], "a") as f:
    f.write(" ".join(args) + "\\n")
idx = 1 if args[-1].endswith("/health/ready") else 0
count_file = os.environ["FAKE_COUNT"]
counts = json.load(open(count_file)) if os.path.exists(count_file) else [0, 0]
rounds = [line.split() for line in open(os.environ["FAKE_ROUNDS"]).read().splitlines()]
code = rounds[min(counts[idx], len(rounds) - 1)][idx]
counts[idx] += 1
json.dump(counts, open(count_file, "w"))
if code == "ERR":  # 진짜 curl 은 못 닿으면 000 을 찍고 0 이 아닌 코드로 끝난다
    print("000", end="")
    sys.exit(7)
print(code, end="")
"""

# deploy.yml · uptime.yml 의 run 목록을 FAKE_DEPLOY_RUNS · FAKE_UPTIME_RUNS 에서 읽어
# --jq 식을 진짜 jq 로 돌린다.
FAKE_GH = f"""#!{sys.executable}
import os, subprocess, sys
args = sys.argv[1:]
with open(os.environ["FAKE_GH_ARGS"], "a") as f:
    f.write(" ".join(args) + "\\n")
path = args[1]  # 모르는 경로는 실패로 끝낸다 — 워크플로 파일 이름이 틀리면 시험이 깨진다
if path == "repos/o/r/actions/workflows/deploy.yml/runs?per_page=20":
    which = "FAKE_DEPLOY_RUNS"
elif path == "repos/o/r/actions/workflows/uptime.yml/runs?status=completed&per_page=5":
    which = "FAKE_UPTIME_RUNS"
else:
    print("gh: 모르는 경로 " + path, file=sys.stderr)
    sys.exit(2)
body = open(os.environ[which]).read()
if body == "ERR":
    print("gh: Not Found (HTTP 404)", file=sys.stderr)
    sys.exit(1)
jq = args[args.index("--jq") + 1]
sys.exit(subprocess.run(["jq", "-r", jq], input=body, text=True).returncode)
"""


def _executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def run(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _executable(bin_dir / "curl", FAKE_CURL)
    _executable(bin_dir / "gh", FAKE_GH)

    def go(
        *rounds,
        deploy=("completed",),
        prev=(),
        webhook="https://hooks.test/x",
        test_alert=False,
        post_fail=False,
        run_id="300",
    ):
        """rounds: 묻는 차례마다의 「`/` 코드 `/health/ready` 코드」.
        deploy: Deploy run 들의 status 또는 "ERR".
        prev: 끝난 업타임 run 들의 결론(가장 최근 것부터) 또는 "ERR"."""
        (tmp_path / "rounds").write_text("\n".join(rounds or ("200 200",)) + "\n")
        (tmp_path / "deploy").write_text(
            "ERR"
            if deploy == "ERR"
            else json.dumps({"workflow_runs": [{"status": s} for s in deploy]})
        )
        (tmp_path / "uptime").write_text(
            "ERR"
            if prev == "ERR"
            else json.dumps(
                {"workflow_runs": [{"id": 200 - i, "conclusion": c} for i, c in enumerate(prev)]}
            )
        )
        proc = subprocess.run(
            ["bash", str(UPTIME_SH)],
            env={
                **os.environ,
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                "BASE": BASE,
                "REPO": "o/r",
                "WEBHOOK": webhook,  # 이 PC 의 진짜 WEBHOOK 이 새지 않게 늘 덮어쓴다
                "RUN_URL": RUN_URL,
                "TEST_ALERT": "true" if test_alert else "",
                "GITHUB_RUN_ID": run_id,
                "UPTIME_RETRY_WAIT": "0",
                "FAKE_ROUNDS": str(tmp_path / "rounds"),
                "FAKE_COUNT": str(tmp_path / "count"),
                "FAKE_PROBES": str(tmp_path / "probes"),
                "FAKE_POSTS": str(tmp_path / "posts"),
                "FAKE_POST_FAIL": "1" if post_fail else "",
                "FAKE_DEPLOY_RUNS": str(tmp_path / "deploy"),
                "FAKE_UPTIME_RUNS": str(tmp_path / "uptime"),
                "FAKE_GH_ARGS": str(tmp_path / "gh-args"),
            },
            capture_output=True,
            text=True,
            timeout=30,
        )
        posts = tmp_path / "posts"
        sent = (
            [json.loads(line)["content"] for line in posts.read_text().splitlines()]
            if posts.exists()
            else []
        )
        probes = (
            (tmp_path / "probes").read_text().splitlines() if (tmp_path / "probes").exists() else []
        )
        return proc, sent, probes

    return go


DOWN = "200 503"  # 한 주소만 죽어도 내려간 것이다
FINE = "200 200"


# ── 정상 / 내려감 가르기 ──


def test_두_주소가_200_이면_정상이고_조용하다(run):
    proc, sent, probes = run(FINE)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert sent == []
    assert len(probes) == 2  # 다시 보지 않았다
    assert all("-m 10" in p for p in probes)  # 응답 없는 주소에 매달리지 않는다


@pytest.mark.parametrize("code", ["503", "502", "404", "301", "500", "ERR"])
@pytest.mark.parametrize("which", ["root", "ready"])
def test_200_이_아닌_주소가_하나라도_있으면_내려감이다(run, code, which):
    # 301 도 정상이 아니다 — 200 만 정상이다. ERR 은 DNS · 연결 실패(코드 000)
    row = f"{code} 200" if which == "root" else f"200 {code}"
    proc, sent, _ = run(row)

    assert proc.returncode == 1
    assert len(sent) == 1
    assert sent[0].startswith("🔴")
    path = "/" if which == "root" else "/health/ready"
    assert (
        f"{BASE}{path} → {'000' if code == 'ERR' else code}" in sent[0]
    )  # 어느 주소가 무슨 코드였나
    assert RUN_URL in sent[0]
    other = f"{BASE}/health/ready" if which == "root" else f"{BASE}/ →"
    assert other not in sent[0]  # 멀쩡한 주소는 적지 않는다


def test_첫_실패_뒤_다시_보니_괜찮으면_알리지_않는다(run):
    # 한 번 튀는 실패로 알리지 않으려고 다시 보는 것이다 — 두 번째 확인이 정상이면 정상
    proc, sent, probes = run(DOWN, FINE)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert sent == []
    assert len(probes) == 4  # 실제로 한 번 더 봤다


def test_다시_봐도_실패면_내려감이다(run):
    proc, sent, probes = run(DOWN, DOWN)

    assert proc.returncode == 1
    assert len(sent) == 1
    assert len(probes) == 4


def test_다시_봤을_때_코드가_알림에_실린다(run):
    # 첫 번째가 아니라 두 번째 확인 결과가 「지금」이다
    _, sent, _ = run("503 503", "200 502")

    assert f"{BASE}/health/ready → 502" in sent[0]
    assert "503" not in sent[0]


# ── 판정표: 내려감 ──


@pytest.mark.parametrize(
    "deploy", [["in_progress"], ["completed", "queued"], ["waiting", "completed"]]
)
def test_내려감_배포가_끝나지_않았으면_알리지_않는다(run, deploy):
    proc, sent, _ = run(DOWN, deploy=deploy, prev=["success"])

    assert proc.returncode == 0
    assert sent == []


def test_내려감_배포_중이어도_직전이_실패였으면_그_상태를_이어_간다(run):
    # 새로 알리지는 않지만 초록으로 끝내면 안 된다
    # — 직전이 success 로 바뀌어 배포 뒤 복구 알림이 빠진다
    proc, sent, _ = run(DOWN, deploy=["in_progress"], prev=["failure"])

    assert proc.returncode == 1
    assert sent == []


def test_알린_뒤_고치는_배포_중에_낀_run_이_있어도_배포_뒤_복구가_알려진다(run):
    # 🔴(failure) → 배포 중 run → 배포가 끝난 뒤 정상.
    # 가운데 run 의 종료 코드가 GitHub 의 결론이 된다
    during, sent, _ = run(DOWN, deploy=["in_progress"], prev=["failure"])
    assert (during.returncode, sent) == (1, [])
    conclusion = "failure" if during.returncode else "success"

    after, sent, _ = run(FINE, prev=[conclusion, "failure"])

    assert after.returncode == 0
    assert len(sent) == 1
    assert sent[0].startswith("🟢")


def test_내려감_배포가_다_끝났으면_알린다(run):
    proc, sent, _ = run(DOWN, deploy=["completed", "completed"], prev=["success"])

    assert proc.returncode == 1
    assert sent[0].startswith("🔴")
    assert "못 읽었다" not in sent[0]  # 배포 중인지 읽었다


def test_내려감_직전_업타임이_실패였으면_이미_알렸으니_또_알리지_않는다(run):
    proc, sent, _ = run(DOWN, prev=["failure", "success"])

    assert proc.returncode == 1  # run 은 계속 빨갛다
    assert sent == []


@pytest.mark.parametrize("prev", [["success"], ["timed_out"], ["cancelled"], [], "ERR"])
def test_내려감_직전이_실패가_아니거나_모르면_알린다(run, prev):
    # [] 는 첫 run, ERR 은 조회 실패(uptime.yml 이 아직 기본 브랜치에 없으면 404)
    proc, sent, _ = run(DOWN, prev=prev)

    assert proc.returncode == 1
    assert len(sent) == 1
    assert sent[0].startswith("🔴")


def test_내려감_배포_조회가_실패하면_알리고_못_읽었다고_적는다(run):
    # 배포 중인지 모른다고 조용히 넘기면 진짜 장애를 놓친다
    proc, sent, _ = run(DOWN, deploy="ERR", prev=["success"])

    assert proc.returncode == 1
    assert len(sent) == 1
    assert sent[0].startswith("🔴")
    assert "배포 중인지 못 읽었다" in sent[0]


def test_내려감_배포_조회가_실패해도_이미_알렸으면_또_알리지_않는다(run):
    proc, sent, _ = run(DOWN, deploy="ERR", prev=["failure"])

    assert proc.returncode == 1
    assert sent == []


# ── 판정표: 정상 ──


def test_정상_직전_업타임이_실패였으면_복구를_알린다(run):
    proc, sent, _ = run(FINE, prev=["failure"])

    assert proc.returncode == 0
    assert len(sent) == 1
    assert sent[0].startswith("🟢")
    assert RUN_URL in sent[0]


@pytest.mark.parametrize("prev", [["success"], ["cancelled"], [], "ERR"])
def test_정상_직전이_실패가_아니거나_모르면_조용하다(run, prev):
    proc, sent, _ = run(FINE, prev=prev)

    assert proc.returncode == 0
    assert sent == []


@pytest.mark.parametrize("ended", ["cancelled", "timed_out", "skipped", "startup_failure"])
def test_직전_결론은_success_failure_인_run_만_본다_내려감(run, ended):
    # 취소 · 시간 초과로 끝난 run 은 알렸는지 아닌지를 말해 주지 않는다 — 그 앞의 failure 를 본다
    proc, sent, _ = run(DOWN, prev=[ended, "failure"])

    assert proc.returncode == 1
    assert sent == []


@pytest.mark.parametrize("ended", ["cancelled", "timed_out", "skipped", "startup_failure"])
def test_직전_결론은_success_failure_인_run_만_본다_정상(run, ended):
    proc, sent, _ = run(FINE, prev=[ended, "failure"])

    assert proc.returncode == 0
    assert len(sent) == 1
    assert sent[0].startswith("🟢")


def test_직전_run_은_지금_run_을_빼고_찾는다(run):
    # 지금 run(200)의 결론이 아니라 그 앞 run(199)의 것을 본다
    proc, sent, _ = run(FINE, prev=["failure", "success"], run_id="200")

    assert proc.returncode == 0
    assert sent == []


# ── 시험 알림 ──


@pytest.mark.parametrize(
    ("prev", "code"),
    [
        (["success"], 0),
        # 이미 알린 장애가 이어지는 중이면 시험이 그 상태를 지우지 않는다
        # — 초록으로 끝나면 복구 알림이 빠진다
        (["failure"], 1),
    ],
)
@pytest.mark.parametrize("deploy", [["completed"], ["in_progress"]])
def test_시험_알림은_내려갔어도_늘_보낸다(run, prev, code, deploy):
    # 배포 중이든 이미 알렸든 상관없이 — 알림 경로가 열려 있는지 보려는 것이다
    proc, sent, _ = run(DOWN, prev=prev, deploy=deploy, test_alert=True)

    assert proc.returncode == code
    assert len(sent) == 1
    assert sent[0].startswith("🧪")
    assert "실제 장애 아님" in sent[0]
    assert f"{BASE}/health/ready → 503" in sent[0]  # 지금 확인 결과를 싣는다


def test_시험_알림은_정상일_때도_보낸다(run):
    proc, sent, _ = run(FINE, prev=["failure"], test_alert=True)

    assert proc.returncode == 0
    assert len(sent) == 1
    assert sent[0].startswith("🧪")
    assert "두 주소 모두 200" in sent[0]  # 복구 알림이 아니라 시험 알림 하나다


# ── 알림 전송 ──


def test_WEBHOOK_이_비면_보내지_않고_내용을_로그에_찍는다(run):
    proc, sent, _ = run(DOWN, prev=["success"], webhook="")

    assert proc.returncode == 1  # 판정은 그대로
    assert sent == []
    assert "보내지 않는다" in proc.stdout
    assert "🔴" in proc.stdout
    assert f"{BASE}/health/ready → 503" in proc.stdout


def test_전송이_실패해도_판정은_그대로다(run):
    proc, sent, _ = run(DOWN, prev=["success"], post_fail=True)

    assert proc.returncode == 1
    assert "알림 전송 실패" in proc.stdout
    assert len(sent) == 1  # 보내려고는 했다


def test_복구_알림_전송이_실패해도_성공으로_끝난다(run):
    proc, _, _ = run(FINE, prev=["failure"], post_fail=True)

    assert proc.returncode == 0
    assert "알림 전송 실패" in proc.stdout
