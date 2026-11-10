"""동시 생성 부하 측정 (#457 — 절차 · 결과: docs/load-check.md).

생성 요청을 한꺼번에 보냈을 때 응답 시간 · 실패 · 실패 원인(LLM 대기 vs DB 연결 대기)과,
생성이 몰릴 때 다른 화면 요청(`GET /api/auth/me`)이 받는 피해를 잰다. 한 번에 한 단계만 한다.

    setup    교사 · 원 · 반(요청 수만큼) · 일과 기록을 실제 API 로 만든다
    burst    S1(일지 초안) 또는 S2(주제형 연간)를 N 개 동시에 보낸다
    analyze  burst 결과 + backend 로그 덤프 → 단계별 표 · 원화 지출 · 다음 단계 최악 비용

**돈이 드는 것은 서버 쪽 LLM 호출이다.** 이 스크립트는 LLM 을 부르지 않고 키도 읽지 않는다.
`LLM_MODE` 를 정하는 것은 부하를 받는 backend 의 환경이다.

**운영을 못 건드리게 막아 둔다.**
  · `--base` 의 호스트가 backend · localhost · 127.0.0.1 이 아니면 거절한다
    (`ssample.duckdns.org` 는 항상).
  · 환경에 `LOADTEST=1` 이 없으면 거절한다 — `backend/scripts/compose.loadtest.yml` 이
    loadtest 프로젝트 backend 에만 넣는다. 운영 backend 컨테이너에서 실수로 부르면 여기서 멈춘다.
  · 둘 다 `--i-know-this-is-not-prod` 로 풀 수 있다(로컬 개발 스택 시험용).
    운영 주소는 그래도 거절한다.

표준 라이브러리 + httpx + psycopg 만 쓴다(backend 이미지에 이미 있다).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import secrets
import sys
import threading
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import httpx
import psycopg

SAFE_HOSTS = frozenset({"backend", "localhost", "127.0.0.1"})
PROD_HOST = "ssample.duckdns.org"

EMAIL = "lt01@example.com"  # EmailStr 가 .test · .local 을 거절한다
CLIENT_TIMEOUT = 180.0  # 서버 최악 ≈ 풀 대기 30 + LLM 30 + 저장 뒤 재대여 30 = 90초 안팎
ME_TIMEOUT = 35.0  # 풀 대기 30초 뒤에 500 이 오는 것까지 본다
LEAD_SECONDS = 2.0  # burst 전후로 표본만 도는 시간 — 평소 값을 같이 남긴다

# 단가는 scripts/llm-usage.sh 와 같다(엘리스 콘솔 gpt-6.1-sol, 2026-10-29, VAT 별도).
# 캐시 할인은 안 센다 — 실제보다 조금 비싸게 나온다. 단가를 바꾸면 두 곳을 같이 바꾼다.
PROMPT_WON_PER_1K = 2.835
COMPLETION_WON_PER_1K = 14.175
# 요청 하나가 부를 수 있는 LLM 시도 수(재시도 1회 포함): S1 은 호출 1 · S2 는 호출 2.
MAX_CALLS = {"s1": 2, "s2": 4}
BUDGET_CAP_WON = 30_000

PG_SQL = (
    "SELECT state, count(*) FROM pg_stat_activity "
    "WHERE datname = current_database() AND backend_type = 'client backend' "
    "AND pid <> pg_backend_pid() GROUP BY state"
)


# ── 순수 함수 (tests/test_load_check.py 가 본다) ─────────────────────────────


def check_base(base: str, allow_other: bool) -> None:
    """부하를 보낼 곳이 허용된 호스트인가. 운영 주소는 플래그가 있어도 거절한다."""
    host = (urlparse(base).hostname or "").lower()
    if host == PROD_HOST or host.endswith("." + PROD_HOST):
        raise SystemExit(f"거절: {host} 는 운영 주소다. 이 스크립트는 운영에 부하를 보내지 않는다.")
    if host not in SAFE_HOSTS and not allow_other:
        raise SystemExit(
            f"거절: --base 의 호스트가 {host!r} 이다. backend · localhost · 127.0.0.1 만 받는다."
            " 로컬 개발 스택이면 --i-know-this-is-not-prod."
        )


def check_env(environ, allow_other: bool) -> None:
    """loadtest 프로젝트 안에서만 돈다 — 운영 backend 컨테이너에서는 이 값이 없다."""
    if environ.get("LOADTEST") != "1" and not allow_other:
        raise SystemExit(
            "거절: 환경에 LOADTEST=1 이 없다. "
            "loadtest 프로젝트(compose.loadtest.yml)의 컨테이너에서만 돈다."
        )


def percentile(values, p: float):
    """선형 보간 백분위. 값이 없으면 None."""
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo = math.floor(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def classify(rec: dict) -> tuple:
    """실패표의 열쇠 (HTTP 상태, error.code, error.message). 성공은 (201, '', '')."""
    if rec.get("timeout"):
        return ("CLIENT_TIMEOUT", "", "")
    if rec.get("exc"):
        return ("CONN_ERROR", rec["exc"], "")
    if rec.get("status") == 201:
        return (201, "", "")
    return (rec.get("status"), rec.get("code") or "-", rec.get("message") or "")


def cost_won(prompt: int, completion: int) -> float:
    return prompt / 1000 * PROMPT_WON_PER_1K + completion / 1000 * COMPLETION_WON_PER_1K


def llm_start_time(ts: datetime, ms: float) -> datetime:
    """`llm_call` 줄은 호출이 **끝난** 뒤에 찍힌다. 시작은 거기서 걸린 시간을 뺀 때다."""
    return ts - timedelta(milliseconds=ms)


def first_starts(calls: list[dict]) -> list[datetime]:
    """요청 하나가 LLM 을 여러 번 부르면(S2 는 연달아 2번, 재시도도) 처음 시작만 센다.

    두 번째 호출의 시작은 풀 대기가 아니라 앞 호출이 끝난 때라서, 그대로 그리면 물결처럼 보인다.
    `run=` 이 `-` 인 호출(S1 — 생성 실행 밖)은 요청 하나가 호출 하나라 모두 센다.
    """
    firsts: dict[str, datetime] = {}
    loose = []
    for e in calls:
        start = llm_start_time(e["ts"], float(e["kv"].get("ms", 0)))
        run = e["kv"].get("run", "-")
        if run == "-":
            loose.append(start)
        elif run not in firsts or start < firsts[run]:
            firsts[run] = start
    return [*firsts.values(), *loose]


_DOCKER_TS = re.compile(r"(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(?:\.(\d+))?Z")
_ASCTIME = re.compile(r"(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d),(\d{3})")
_EVENT = re.compile(r"\b(llm_call|llm_usage|plan_timing|unexpected_error)\s+\w+=")


def parse_log_line(line: str) -> dict | None:
    """`docker compose logs -t backend` 한 줄 → {kind, ts, kv}. 관심 없는 줄은 None.

    시각은 docker 의 `-t` 접두(UTC)를 먼저 쓰고, 없으면 앱 asctime(컨테이너 시간대 = UTC)을 쓴다.
    """
    m = _EVENT.search(line)
    if m is None:
        return None
    d = _DOCKER_TS.search(line)
    if d:
        y, mo, da, h, mi, s, frac = d.groups()
        micro = int(((frac or "") + "000000")[:6])
    else:
        a = _ASCTIME.search(line)
        if a is None:
            return None
        y, mo, da, h, mi, s, ms3 = a.groups()
        micro = int(ms3) * 1000
    ts = datetime(int(y), int(mo), int(da), int(h), int(mi), int(s), micro, tzinfo=UTC)
    kv = dict(re.findall(r"(\w+)=(\S+)", line[m.start() :]))
    return {"kind": m.group(1), "ts": ts, "kv": kv}


# ── HTTP ─────────────────────────────────────────────────────────────────────


def now_utc() -> datetime:
    return datetime.now(UTC)


def error_of(resp: httpx.Response) -> tuple[str, str]:
    """공통 에러 봉투 `{error: {code, message}}`. 다른 모양이면 앞부분만 남긴다."""
    try:
        body = resp.json()
    except ValueError:
        return "", resp.text[:120]
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        return str(body["error"].get("code", "")), str(body["error"].get("message", ""))
    return "", str(body)[:120]


def must(resp: httpx.Response, expect: int, what: str) -> dict:
    if resp.status_code != expect:
        code, message = error_of(resp)
        raise SystemExit(f"{what} 실패: {resp.status_code} {code} {message}")
    return resp.json()


def db_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise SystemExit("DATABASE_URL 이 없다. loadtest 의 backend 컨테이너 안에서 돌린다.")
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


def load_state(out: Path) -> dict | None:
    path = out / "state.json"
    return json.loads(path.read_text()) if path.exists() else None


def save_state(out: Path, state: dict) -> None:
    (out / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=1))


# ── setup ────────────────────────────────────────────────────────────────────


def cmd_setup(a) -> None:
    check_base(a.base, a.i_know_this_is_not_prod)
    check_env(os.environ, a.i_know_this_is_not_prod)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    fresh = load_state(out) is None
    state = load_state(out) or {
        "email": EMAIL,
        "password": secrets.token_urlsafe(12),
        "classes": [],
    }
    with httpx.Client(base_url=a.base, timeout=30.0) as c:
        credentials = {"email": state["email"], "password": state["password"]}
        r = c.post("/api/auth/signup", json={**credentials, "name": "부하측정"})
        if r.status_code == 409 and not fresh:
            r = c.post("/api/auth/login", json=credentials)
            token = must(r, 200, "로그인")["token"]
        elif r.status_code == 409:
            raise SystemExit(
                f"{EMAIL} 가 이미 있고 이 폴더에 state.json 이 없다. DB 가 새것이 아니다."
            )
        else:
            token = must(r, 201, "가입")["token"]
        state["token"] = token
        c.headers["Authorization"] = f"Bearer {token}"

        if "center_id" not in state:
            body = {
                "name": "부하측정원",
                "director_name": "부하측정",
                "region_sido": "서울특별시",
                "region_sigungu": "종로구",
            }
            state["center_id"] = must(c.post("/api/centers", json=body), 201, "원 만들기")["id"]
        day = a.date or now_utc().date().isoformat()
        first = len(state["classes"]) + 1
        try:
            for i in range(first, first + a.classes):
                body = {
                    "name": f"lt-{i:04d}",
                    "age_min": 4,
                    "age_max": 4,
                    "teacher_name": "부하측정",
                }
                class_id = must(
                    c.post(f"/api/centers/{state['center_id']}/classes", json=body),
                    201,
                    "반 만들기",
                )["id"]
                routine = {
                    "class_id": class_id,
                    "date": day,
                    "position": 0,
                    "name": "오전 실내놀이",
                    "plan": "블록 쌓기",
                    "execution": "블록으로 높은 탑을 쌓고 친구들과 함께 무너뜨리며 웃었다.",
                }
                routine_id = must(c.post("/api/routines", json=routine), 201, "일과 기록")["id"]
                state["classes"].append({"id": class_id, "routine_id": routine_id, "date": day})
        finally:
            save_state(out, state)
    print(f"setup 끝: 반 {len(state['classes'])}개 (이번에 {a.classes}개 추가) → {out}/state.json")


# ── burst ────────────────────────────────────────────────────────────────────


def request_for(scenario: str, cls: dict) -> tuple[str, dict]:
    if scenario == "s1":
        day = cls["date"]
        body = {
            "kind": "dailyLog",
            "class_id": cls["id"],
            "start": day,
            "end": day,
            "source_ids": [cls["routine_id"]],
            "source_kind": "dailyLog",
        }
        return "/api/documents", body
    return "/api/plans/annual", {"format": "MONTHLY_THEME", "class_id": cls["id"]}


def fire(base, token, scenario, cls, seq, barrier, marks, recs) -> None:
    path, body = request_for(scenario, cls)
    rec = {"seq": seq, "class_id": cls["id"], "status": None, "timeout": False}
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=base, headers=headers, timeout=httpx.Timeout(CLIENT_TIMEOUT)) as c:
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        start, rec["start_utc"] = time.monotonic(), now_utc()
        try:
            r = c.post(path, json=body)
            rec["status"] = r.status_code
            if r.status_code != 201:
                rec["code"], rec["message"] = error_of(r)
        except httpx.TimeoutException as exc:
            rec["timeout"], rec["exc"] = True, type(exc).__name__
        except httpx.HTTPError as exc:
            rec["exc"] = type(exc).__name__
        end, rec["end_utc"] = time.monotonic(), now_utc()
    rec["ms"] = (end - start) * 1000
    rec["rel_start_s"] = start - marks["t0_mono"]
    rec["rel_end_s"] = end - marks["t0_mono"]
    for key in ("start_utc", "end_utc"):
        rec[key] = rec[key].isoformat(timespec="milliseconds")
    recs[seq] = rec


def sample_me(base, token, stop, samples) -> None:
    """LLM 을 안 부르는 인증 GET 을 1초마다. 생성이 몰릴 때 다른 화면이 받는 피해(M6)."""
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=base, headers=headers, timeout=ME_TIMEOUT) as c:
        while not stop.is_set():
            began, utc = time.monotonic(), now_utc()
            sample = {"utc": utc.isoformat(timespec="milliseconds"), "status": None}
            try:
                sample["status"] = c.get("/api/auth/me").status_code
            except httpx.HTTPError as exc:
                sample["exc"] = type(exc).__name__
            sample["ms"] = (time.monotonic() - began) * 1000
            samples.append(sample)
            stop.wait(max(0.0, 1.0 - (time.monotonic() - began)))


def summarize_pg(rows) -> dict:
    states = {state or "-": n for state, n in rows}
    return {
        "total": sum(states.values()),
        "active": states.get("active", 0),
        "idle": states.get("idle", 0),
        "idle_in_tx": sum(n for s, n in states.items() if s.startswith("idle in transaction")),
    }


def sample_pg(stop, samples) -> None:
    """붙잡힌 연결 수 · idle in transaction. 풀(5+10)이 막히면 여기서 15 가 보인다."""
    try:
        conn = psycopg.connect(db_url(), autocommit=True)
    except Exception as exc:  # noqa: BLE001 — 표본이 안 돼도 부하 자체는 돌린다
        samples.append({"error": type(exc).__name__})
        return
    with conn:
        while not stop.is_set():
            began = time.monotonic()
            try:
                row = summarize_pg(conn.execute(PG_SQL).fetchall())
            except Exception as exc:  # noqa: BLE001
                samples.append({"error": type(exc).__name__})
                return
            samples.append({"utc": now_utc().isoformat(timespec="milliseconds"), **row})
            stop.wait(max(0.0, 1.0 - (time.monotonic() - began)))


def saved_class_ids(scenario: str, class_ids: list[int]) -> list[int]:
    """DB 에 실제로 저장된 행이 있는 반. 201 수와 맞춰 「저장됐는데 실패 응답」을 센다."""
    with psycopg.connect(db_url(), autocommit=True) as conn:
        if scenario == "s1":
            sql = "SELECT class_id FROM documents WHERE kind = 'dailyLog' AND class_id = ANY(%s)"
            return sorted(r[0] for r in conn.execute(sql, [class_ids]))
        sql = "SELECT classroom_ref FROM plans WHERE kind = 'annual' AND classroom_ref = ANY(%s)"
        return sorted(int(r[0]) for r in conn.execute(sql, [[str(i) for i in class_ids]]))


def run_round(a, state, classes, index) -> dict:
    n = len(classes)
    stop, me, pg = threading.Event(), [], []
    samplers = [
        threading.Thread(target=sample_me, args=(a.base, state["token"], stop, me)),
        threading.Thread(target=sample_pg, args=(stop, pg)),
    ]
    for t in samplers:
        t.start()
    time.sleep(LEAD_SECONDS)

    marks: dict = {}

    def stamp() -> None:
        marks["t0_mono"], marks["t0_utc"] = time.monotonic(), now_utc()

    barrier = threading.Barrier(n, action=stamp)
    recs: list = [None] * n
    workers = [
        threading.Thread(
            target=fire, args=(a.base, state["token"], a.scenario, cls, seq, barrier, marks, recs)
        )
        for seq, cls in enumerate(classes)
    ]
    for t in workers:
        t.start()
    for t in workers:
        t.join()
    time.sleep(LEAD_SECONDS)
    stop.set()
    for t in samplers:
        t.join(timeout=ME_TIMEOUT + 5)

    # 클라이언트 시간 초과 요청은 서버에서 계속 돌다 나중에 저장될 수 있다. 세기 전에 기다린다.
    if any(r["timeout"] for r in recs):
        print(
            f"  클라이언트 시간 초과가 있다. 서버가 끝나길 {a.settle:.0f}초 기다린 뒤 행 수를 센다."
        )
        time.sleep(a.settle)
    ids = [c["id"] for c in classes]
    ok = sorted(r["class_id"] for r in recs if r["status"] == 201)
    saved = saved_class_ids(a.scenario, ids)
    return {
        "round": index,
        "warmup": index < a.warmup,
        "t0_utc": marks["t0_utc"].isoformat(timespec="milliseconds"),
        "class_ids": ids,
        "requests": recs,
        "me": me,
        "pg": pg,
        "ok_class_ids": ok,
        "saved_class_ids": saved,
    }


def one_line(rnd: dict) -> str:
    tally = Counter(str(classify(r)[0]) for r in rnd["requests"])
    worst = max(r["ms"] for r in rnd["requests"])
    pg_max = max((p.get("total", 0) for p in rnd["pg"]), default=0)
    return (
        f"{dict(tally)} 최대 {worst:.0f}ms · 저장 {len(rnd['saved_class_ids'])}행 · "
        f"201 {len(rnd['ok_class_ids'])} · pg 연결 최대 {pg_max}"
    )


def cmd_burst(a) -> None:
    check_base(a.base, a.i_know_this_is_not_prod)
    check_env(os.environ, a.i_know_this_is_not_prod)
    out = Path(a.out)
    state = load_state(out)
    if state is None:
        raise SystemExit(f"{out}/state.json 이 없다. setup 을 먼저 돌린다.")
    flag = f"used_{a.scenario}"
    free = [c for c in state["classes"] if not c.get(flag)]
    need = a.n * a.repeat
    if len(free) < need:
        raise SystemExit(
            f"반이 모자란다: 필요 {need} · 남은 {len(free)}. "
            f"setup --classes {need - len(free)} 이상을 먼저 돌린다(요청마다 새 반이 든다)."
        )
    # 로그인을 다시 해 토큰 만료(12시간)를 피한다.
    with httpx.Client(base_url=a.base, timeout=30.0) as c:
        login = {"email": state["email"], "password": state["password"]}
        state["token"] = must(c.post("/api/auth/login", json=login), 200, "로그인")["token"]

    stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
    path = out / f"burst-{a.scenario}-n{a.n}-{stamp}.json"
    result = {"scenario": a.scenario, "n": a.n, "base": a.base, "started_utc": stamp, "rounds": []}
    for r in range(a.repeat):
        classes = free[r * a.n : (r + 1) * a.n]
        for (
            cls
        ) in classes:  # 보내기 전에 쓴 것으로 적는다 — 중간에 죽어도 같은 반을 다시 쓰지 않는다
            cls[flag] = True
        save_state(out, state)
        print(f"[{a.scenario} n={a.n} 회차 {r + 1}/{a.repeat}] 보낸다…")
        rnd = run_round(a, state, classes, r)
        result["rounds"].append(rnd)
        path.write_text(json.dumps(result, ensure_ascii=False))
        print(f"  {one_line(rnd)}" + (" (예열 — 표에서 따로 센다)" if rnd["warmup"] else ""))
        if r + 1 < a.repeat:
            time.sleep(a.pause)
    print(f"burst 끝 → {path}")


# ── analyze ──────────────────────────────────────────────────────────────────


def iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def load_rounds(out: Path) -> list[dict]:
    rounds = []
    for f in sorted(out.glob("burst-*.json")):
        data = json.loads(f.read_text())
        for rnd in data["rounds"]:
            rnd = {**rnd, "scenario": data["scenario"], "n": data["n"], "t0": iso(rnd["t0_utc"])}
            tag = " 예열" if rnd["warmup"] else ""
            rnd["label"] = f"{data['scenario'].upper()} n={data['n']}{tag}"
            rounds.append(rnd)
    return sorted(rounds, key=lambda r: r["t0"])


def assign(ts: datetime, rounds: list[dict]) -> dict | None:
    """이 시각이 속한 회차 = t0 가 이 시각(1초 여유) 이전인 마지막 회차."""
    owner = None
    for rnd in rounds:
        if rnd["t0"] <= ts + timedelta(seconds=1):
            owner = rnd
    return owner


def rtt_gaps(requests: list[tuple], timings: list[tuple]) -> list[float]:
    """(끝 시각, 왕복 ms) 와 (끝 시각, total_ms) 를 끝 시각이 가장 가까운 것끼리 짝지어 차를 낸다.

    `plan_timing` 은 의존성(첫 질의 = 풀 대기) 뒤에 시작해 풀 대기를 못 본다. 그래서 차이가
    스레드풀 대기 + 풀 대기 + 인증 질의 + 응답 직렬화다.
    """
    left, gaps = list(requests), []
    for t_end, total in sorted(timings):
        if not left:
            break
        j = min(range(len(left)), key=lambda k: abs((left[k][0] - t_end).total_seconds()))
        gaps.append(left.pop(j)[1] - total)
    return gaps


def fmt(value, unit: str = "ms") -> str:
    return "-" if value is None else f"{value:,.0f}{unit}"


def stats(values) -> str:
    return (
        f"n={len(values)} p50 {fmt(percentile(values, 50))} "
        f"p95 {fmt(percentile(values, 95))} max {fmt(max(values) if values else None)}"
    )


def histogram(offsets: list[float], width: float) -> list[str]:
    if not offsets:
        return ["    (llm_call 없음)"]
    bins = Counter(int(o // width) for o in offsets)
    top = max(bins.values())
    return [
        f"    {f'{k * width:g}-{(k + 1) * width:g}s':>9} "
        f"{'#' * max(1, round(30 * bins[k] / top))} {bins[k]}"
        for k in range(min(bins), max(bins) + 1)
        if bins.get(k)
    ]


def analyze_stage(label: str, rnds: list[dict], events: list[dict], a) -> None:
    scenario = rnds[0]["scenario"]
    reqs = [r for rnd in rnds for r in rnd["requests"]]
    print(f"\n=== {label} · 회차 {len(rnds)} · 요청 {len(reqs)} ===")
    ok_ms = [r["ms"] for r in reqs if r["status"] == 201]
    print(f"  응답 시간 전체: {stats([r['ms'] for r in reqs])}")
    print(f"  응답 시간 201만: {stats(ok_ms)}")
    table = Counter(classify(r) for r in reqs)
    print("  결과표 (상태, code, message) → 건수")
    for key, n in sorted(table.items(), key=lambda kv: -kv[1]):
        print(f"    {n:4d}  {key[0]} {key[1]} {key[2][:70]}")

    me = [s for rnd in rnds for s in rnd["me"]]
    me_bad = [s for s in me if s["status"] != 200]
    print(
        f"  /auth/me: {stats([s['ms'] for s in me])} · 실패 {len(me_bad)} "
        f"{dict(Counter(str(s['status'] or s.get('exc')) for s in me_bad))}"
    )
    pg = [p for rnd in rnds for p in rnd["pg"] if "total" in p]
    print(
        "  pg_stat 최대: "
        f"연결 {max((p['total'] for p in pg), default=0)} · "
        f"idle in transaction {max((p['idle_in_tx'] for p in pg), default=0)} · "
        f"active {max((p['active'] for p in pg), default=0)}"
    )
    ok = {c for rnd in rnds for c in rnd["ok_class_ids"]}
    saved = {c for rnd in rnds for c in rnd["saved_class_ids"]}
    print(
        f"  행 수 대조: 201 {len(ok)} · 저장된 행 {len(saved)} · "
        f"저장됐는데 201 아님 {len(saved - ok)} · 201인데 행 없음 {len(ok - saved)}"
    )

    mine = [e for e in events if e["rnd"] is not None and e["rnd"]["label"] == label]
    calls = [e for e in mine if e["kind"] == "llm_call"]
    print(f"  서버 llm_call {len(calls)}건: {dict(Counter(e['kv'].get('outcome') for e in calls))}")
    errors = [e for e in mine if e["kind"] == "unexpected_error"]
    # 경로까지 센다 — /auth/me 표본이 맞은 풀 대기 초과와 burst 요청이 맞은 것을 가른다.
    by_path = Counter(f"{e['kv'].get('path')} {e['kv'].get('error')}" for e in errors)
    print(f"  unexpected_error {len(errors)}건: {dict(by_path)}")
    timings = [e for e in mine if e["kind"] == "plan_timing"]
    if scenario == "s2":
        missing = len(reqs) - len(timings)
        print(f"  요청 {len(reqs)} − plan_timing {len(timings)} = {missing} (핸들러에 못 닿은 수)")
        reached = [
            (iso(r["end_utc"]), r["ms"])
            for r in reqs
            if not r["timeout"]
            and r.get("code") not in ("INTERNAL_ERROR", "UNAUTHENTICATED")
            and r["status"] is not None
        ]
        gaps = rtt_gaps(reached, [(e["ts"], float(e["kv"]["total_ms"])) for e in timings])
        print(f"  왕복 − total_ms: {stats(gaps)}")
    else:
        print("  plan_timing: S1(일지)은 이 줄을 안 남긴다 — llm_call 시작 시각으로 본다")
    # 같은 회차의 t0 를 쓰려고 회차별로 나눠 처음 시작만 모은다.
    offsets = []
    for rnd in rnds:
        mine_in_round = [e for e in calls if e["rnd"] is rnd]
        offsets += [(t - rnd["t0"]).total_seconds() for t in first_starts(mine_in_round)]
    print(f"  LLM 첫 시작 시각 (burst t0 기준 {a.bin:g}초 칸 — 0 · H · 2H 에 몰리면 풀 병목)")
    print("\n".join(histogram(offsets, a.bin)))


def spend(events: list[dict]) -> dict:
    """원화 지출. 시간 초과(`outcome=timeout`)는 과금됐을 수 있어 최대 관측 단가로 센다."""
    costs: dict = {}
    for e in events:
        if e["kind"] != "llm_usage":
            continue
        p, c = e["kv"].get("prompt", "-"), e["kv"].get("completion", "-")
        if p.isdigit() and c.isdigit():
            scenario = e["rnd"]["scenario"] if e["rnd"] else None
            costs.setdefault(scenario, []).append((int(p), int(c), cost_won(int(p), int(c))))
    flat = [x for v in costs.values() for x in v]
    overall_max = max((x[2] for x in flat), default=0.0)
    per_max = {s: max(x[2] for x in v) for s, v in costs.items() if s}
    timeouts = [
        e for e in events if e["kind"] == "llm_call" and e["kv"].get("outcome") == "timeout"
    ]
    timeout_won = sum(
        per_max.get(e["rnd"]["scenario"] if e["rnd"] else None, overall_max) for e in timeouts
    )
    return {
        "calls": len(flat),
        "prompt": sum(x[0] for x in flat),
        "completion": sum(x[1] for x in flat),
        "ok_won": sum(x[2] for x in flat),
        "timeouts": len(timeouts),
        "timeout_won": timeout_won,
        "per_max": per_max,
        "overall_max": overall_max,
    }


def print_spend(sp: dict, next_n: int | None) -> None:
    total = sp["ok_won"] + sp["timeout_won"]
    print("\n=== 원화 지출 (llm_usage 단가: scripts/llm-usage.sh, VAT 별도, 캐시 할인 없음) ===")
    tokens = f"입력 {sp['prompt']:,} · 출력 {sp['completion']:,} 토큰"
    print(f"  성공 호출 {sp['calls']}건 · {tokens} → ₩{sp['ok_won']:,.0f}")
    print(f"  시간 초과 {sp['timeouts']}건 × 최대 관측 단가 → ₩{sp['timeout_won']:,.0f} (추정)")
    print(f"  합계 ₩{total:,.0f} / 상한 ₩{BUDGET_CAP_WON:,}")
    units = {k.upper(): round(v, 1) for k, v in sp["per_max"].items()}
    print(f"  호출 1회 최대 관측 단가(원): {units}")
    if next_n is None:
        return
    print(
        f"\n=== 다음 단계 동시 {next_n} 의 최악 비용 (요청 수 × 요청당 최대 호출 × 최대 단가) ==="
    )
    for scenario, calls in MAX_CALLS.items():
        unit = sp["per_max"].get(scenario, sp["overall_max"])
        if unit == 0:
            print(f"  {scenario.upper()}: 단가를 아직 못 봤다 — 기준선(동시 1)부터 잰다")
            continue
        if scenario not in sp["per_max"]:
            print(f"  ({scenario.upper()} 관측이 없어 전체 최대 단가 ₩{unit:,.1f} 로 센다)")
        worst = next_n * calls * unit
        verdict = "진행 가능" if total + worst <= BUDGET_CAP_WON else "멈춘다 — 상한을 넘을 수 있다"
        after = f"₩{total + worst:,.0f} / ₩{BUDGET_CAP_WON:,}"
        print(f"  {scenario.upper()}: ₩{worst:,.0f} → 지출 합계 {after} : {verdict}")


def cmd_analyze(a) -> None:
    out = Path(a.out)
    rounds = load_rounds(out)
    if not rounds:
        raise SystemExit(f"{out} 에 burst-*.json 이 없다.")
    events = []
    for line in Path(a.backend_log).read_text(errors="replace").splitlines():
        ev = parse_log_line(line)
        if ev is None:
            continue
        # llm_call 은 시작 시각으로, 나머지는 찍힌 시각으로 회차를 정한다.
        at = (
            llm_start_time(ev["ts"], float(ev["kv"].get("ms", 0)))
            if ev["kind"] == "llm_call"
            else ev["ts"]
        )
        ev["rnd"] = assign(at, rounds)
        events.append(ev)
    loose = sum(e["rnd"] is None for e in events)
    print(f"백엔드 로그 {len(events)}줄 읽음 (회차에 못 붙인 줄 {loose})")
    print(f"회차 {len(rounds)} · 요청 {sum(len(r['requests']) for r in rounds)}")

    by_label: dict = {}
    for rnd in rounds:
        by_label.setdefault(rnd["label"], []).append(rnd)
    shown = [rounds[-1]["label"]] if a.last_only else list(by_label)
    for label in shown:
        analyze_stage(label, by_label[label], events, a)
    print_spend(spend(events), a.next_n)


# ── main ─────────────────────────────────────────────────────────────────────


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, base: bool = True) -> None:
        sp.add_argument("--out", required=True, help="state.json · burst-*.json 을 두는 폴더")
        if base:
            sp.add_argument("--base", required=True, help="예: http://backend:8000")
            sp.add_argument("--i-know-this-is-not-prod", action="store_true")

    s = sub.add_parser("setup", help="교사 · 원 · 반 · 일과 기록 (여러 번 돌리면 반이 더해진다)")
    common(s)
    s.add_argument("--classes", type=int, required=True, help="이번에 더할 반 수")
    s.add_argument("--date", help="일과 기록 날짜 YYYY-MM-DD (기본 오늘 UTC)")
    s.set_defaults(fn=cmd_setup)

    b = sub.add_parser("burst", help="N 개를 동시에 (회차마다 새 반을 쓴다)")
    common(b)
    b.add_argument("--scenario", choices=["s1", "s2"], required=True)
    b.add_argument("--n", type=int, required=True, help="동시 요청 수")
    b.add_argument("--repeat", type=int, default=1, help="회차 수")
    b.add_argument("--warmup", type=int, default=0, help="앞의 몇 회차를 예열로 따로 센다")
    b.add_argument("--pause", type=float, default=5.0, help="회차 사이 쉬는 초")
    b.add_argument(
        "--settle", type=float, default=60.0, help="시간 초과가 있을 때 행 수 세기 전 대기 초"
    )
    b.set_defaults(fn=cmd_burst)

    z = sub.add_parser("analyze", help="burst 결과 + backend 로그 → 표")
    common(z, base=False)
    z.add_argument("--backend-log", required=True, help="docker compose logs -t backend 덤프")
    z.add_argument("--next-n", type=int, help="다음 단계 동시 요청 수 — 최악 비용을 낸다")
    z.add_argument("--bin", type=float, default=5.0, help="LLM 시작 히스토그램 칸(초)")
    z.add_argument("--last-only", action="store_true", help="마지막 단계 표만 (지출은 누적 전체)")
    z.set_defaults(fn=cmd_analyze)

    args = p.parse_args(argv)
    try:
        args.fn(args)
    except httpx.HTTPError as exc:  # setup · 로그인 중 서버에 못 닿았다
        raise SystemExit(f"서버에 못 닿았다: {type(exc).__name__} {exc}") from exc


if __name__ == "__main__":
    sys.exit(main())
