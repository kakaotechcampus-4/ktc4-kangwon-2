"""loadtest.sh gate — `docker compose config --format json` 을 stdin 으로 받아 어긋나면 exit 1.

**fail-closed 다.** 기대하는 것을 하나씩 확인하고, 하나라도 다르면 멈춘다.
모르는 모양은 통과가 아니라 실패다. loadtest 프로젝트가 운영의 이름 · 망 · 볼륨 · 폴더를
만지지 못하게 하는 마지막 확인이다(docs/load-check.md).
"""

from __future__ import annotations

import json
import os
import posixpath
import sys
from urllib.parse import urlparse

IMAGE = "ssample-loadtest-backend:457"
# 서비스별 메모리 상한(MiB). compose.loadtest.yml 의 mem_limit · memswap_limit 와,
# loadtest.sh 의 NEED_AVAILABLE_MB(세 상한 합 + 운영 여유 500)를 같이 바꾼다.
LIMITS_MIB = {"db": 512, "backend": 1024, "loadgen": 256}


def _mib(service: dict, key: str):
    try:
        return int(service.get(key)) // (1 << 20)
    except (TypeError, ValueError):
        return None


def _names(value) -> set:
    return set(value) if isinstance(value, (dict, list)) else set()


def results(cfg: dict, text: str, mode: str, server: str, lt_dir: str) -> list[tuple[bool, str]]:
    out: list[tuple[bool, str]] = []

    def check(ok: bool, label: str) -> None:
        out.append((bool(ok), label))

    svc = cfg.get("services") or {}
    check(cfg.get("name") == "loadtest", "프로젝트 이름 loadtest")
    check(set(svc) == set(LIMITS_MIB), f"서비스 db backend loadgen 만 (지금 {sorted(svc)})")
    for name, limit in LIMITS_MIB.items():
        for key in ("mem_limit", "memswap_limit"):
            check(_mib(svc.get(name) or {}, key) == limit, f"{name} {key} {limit}m")

    for name, s in svc.items():
        check(not s.get("ports"), f"{name} 호스트 포트 없음")
        check(s.get("restart") == "no", f"{name} restart no")
        check("build" not in s, f"{name} build 없음")
        check((s.get("logging") or {}).get("driver") != "journald", f"{name} 로그 journald 아님")
        check(_names(s.get("networks")) == {"default"}, f"{name} 연결 네트워크는 default 하나뿐")
        check("network_mode" not in s, f"{name} network_mode 없음")
    check((svc.get("db") or {}).get("image") == "postgres:15", "db 이미지 postgres:15")
    for name in ("backend", "loadgen"):
        check((svc.get(name) or {}).get("image") == IMAGE, f"{name} 이미지 {IMAGE}")
    check(not (svc.get("loadgen") or {}).get("depends_on"), "loadgen depends_on 없음")

    env = (svc.get("backend") or {}).get("environment") or {}
    check(env.get("LOADTEST") == "1", "backend LOADTEST=1")
    check(env.get("LLM_MODE") == mode, f"backend LLM_MODE={mode} (지금 {env.get('LLM_MODE')})")
    check(
        env.get("IS_SERVER") == server, f"backend IS_SERVER={server} (지금 {env.get('IS_SERVER')})"
    )
    check(env.get("ALLOW_TEST_RESET") == "0", "backend ALLOW_TEST_RESET=0")
    check(urlparse(env.get("DATABASE_URL", "")).hostname == "db", "backend DATABASE_URL 호스트 db")
    # `?host=…` 는 URL 의 호스트를 덮어쓰고, PG* 환경변수(PGHOST 등)도 접속 대상을 바꾼다.
    loadgen_env = (svc.get("loadgen") or {}).get("environment") or {}
    for name, e in (("backend", env), ("loadgen", loadgen_env)):
        check(
            not urlparse(e.get("DATABASE_URL", "")).query, f"{name} DATABASE_URL 에 쿼리(?…) 없음"
        )
        check(not [k for k in e if k.upper().startswith("PG")], f"{name} 환경에 PG* 변수 없음")
    loadgen_env = set(loadgen_env)
    check(
        loadgen_env == {"DATABASE_URL", "LOADTEST"},
        "loadgen 환경변수는 DATABASE_URL · LOADTEST 뿐 (LLM 설정 없음)",
    )

    # 마운트: bind 는 loadgen 의 load_check.py · out/ 둘뿐, 이름 있는 볼륨은 db 의 pgdata 하나뿐
    allowed_binds = {
        ("loadgen", posixpath.normpath(lt_dir + "/load_check.py"), "/lt/load_check.py"),
        ("loadgen", posixpath.normpath(lt_dir + "/out"), "/lt/out"),
    }
    for name, s in svc.items():
        for v in s.get("volumes") or []:
            kind, source, target = v.get("type"), str(v.get("source")), v.get("target")
            if kind == "bind":
                ok = (name, posixpath.normpath(source), target) in allowed_binds
                check(ok, f"{name} bind mount {source} → {target} 는 허용 목록에 있다")
            elif kind == "volume":
                check(
                    (name, source) == ("db", "pgdata"), f"{name} 볼륨 {source} 는 db 의 pgdata 뿐"
                )
            else:
                check(False, f"{name} 마운트 종류 {kind} 는 허용되지 않는다")
    vols = cfg.get("volumes") or {}
    check(set(vols) == {"pgdata"}, f"볼륨은 pgdata 하나뿐 (지금 {sorted(vols)})")
    pg = vols.get("pgdata") or {}
    check(pg.get("name") == "loadtest_pgdata", "볼륨 이름 loadtest_pgdata")
    check(not pg.get("driver_opts"), "볼륨 driver_opts 없음")
    check(
        pg.get("driver") in (None, "local") and not pg.get("external"),
        "볼륨은 local · external 아님",
    )

    nets = cfg.get("networks") or {}
    net = nets.get("default") or {}
    check(set(nets) == {"default"}, f"망은 default 하나뿐 (지금 {sorted(nets)})")
    check(net.get("name") == "loadtest_default" and not net.get("external"), "망 loadtest_default")
    ipam = (net.get("ipam") or {}).get("config")
    check(
        ipam == [{"subnet": "172.29.0.0/16", "gateway": "172.29.0.1"}], "망 대역 172.29.0.0/16 하나"
    )

    for needle in ("ktc4-kangwon-2", "172.28.", "journald"):
        check(needle not in text, f"설정 어디에도 {needle} 없음")
    return out


def main(argv: list[str]) -> int:
    text = sys.stdin.read()
    try:
        cfg = json.loads(text)
    except ValueError:
        print("FAIL config 가 JSON 이 아니다")
        return 1
    env = os.environ
    res = results(cfg, text, env["LT_WANT_MODE"], env["LT_WANT_SERVER"], env["LT_DIR"].rstrip("/"))
    bad = False
    for ok, label in res:
        if not ok:
            bad = True
            print("FAIL ", label)
        elif "-v" in argv:
            print("ok   ", label)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
