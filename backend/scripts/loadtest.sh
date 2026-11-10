#!/usr/bin/env bash
# 동시 생성 부하 측정(#457)의 서버 · 로컬 작업 스크립트. 절차는 docs/load-check.md.
#
#   bash loadtest.sh <명령> [인자]
#
#   preflight        읽기만 한다. 메모리 · 망 대역 · 볼륨 · 도는 배포를 본다
#   env              .env 를 만든다(이미 있으면 거절)
#   tag              운영 backend 이미지에 loadtest 태그를 붙인다
#   gate [-v]        docker compose config 를 JSON 으로 받아 하나라도 어긋나면 exit 1
#   up               gate → db → gate → alembic → gate → backend → 준비될 때까지
#   loadgen ARGS…    부하기(load_check.py)를 일회용 컨테이너로. gate 를 먼저 돈다
#   stage S:NxR      로그를 덤프하고 마지막 단계를 분석한다. 다음 단계(예: s2:10x2)의 최악 비용도
#   final            전체 표
#   lock | unlock    서버 배포 잠금(/tmp/ssuksak-deploy.lock)을 쥐고 놓는다
#   down             gate → 로그 덤프 → down -v → 태그 삭제 → 남은 것이 없는지
#   ps
#
# **이 스크립트는 loadtest 프로젝트만 건드린다.** 모든 compose 명령이 `lt()` 하나를 지나고,
# 거기서 프로젝트 이름(-p loadtest) · 파일(-f) · env 파일을 명령줄로 못 박는다 — 셸의 COMPOSE_PROJECT_NAME 은
# 파일 안의 `name:` 보다 우선해서, 파일만 믿으면 운영 이름의 망 · 볼륨으로 렌더링된다.
# 그래서 시작할 때 셸의 COMPOSE_* 를 지우고, 있었다면 거절한다(오염된 셸이다).
#
# 환경변수(모두 선택):
#   LT_DIR           작업 폴더. 기본 /home/ubuntu/loadtest-457
#   LT_MODE          real(기본) | mock — mock 은 로컬 리허설용. real 이면 .env 에 IS_SERVER=1 · 엘리스 값
#   LT_SUDO=1        docker 앞에 sudo
#   LT_PROD_ENV · LT_PROD_BACKEND   운영 .env 경로 · 운영 backend 컨테이너 이름
#   LT_LOCK_FILE · LT_LOCK_SECONDS  배포 잠금 파일 · 최대 쥐는 시간(기본 4시간 — 잊어도 풀린다)
#   LT_AVAILABLE_MB  preflight 의 available 메모리를 직접 준다(로컬 시험용)
#   LT_SSM_INSTANCE  SSM 에서 도는 배포 명령을 볼 인스턴스. LT_SKIP_SSM=1 이면 건너뛴다(로컬 리허설만)
set -euo pipefail

polluted=$(env | grep -E '^COMPOSE_(PROJECT_NAME|FILE|PROFILES|ENV_FILES)=' | cut -d= -f1 | tr '\n' ' ' || true)
unset COMPOSE_PROJECT_NAME COMPOSE_FILE COMPOSE_PROFILES COMPOSE_ENV_FILES
if [ -n "$polluted" ]; then
  echo "거절: 셸에 ${polluted}가 있다 — 지우고 새 셸에서 다시 한다" >&2
  exit 1
fi

LT_DIR=${LT_DIR:-/home/ubuntu/loadtest-457}
LT_MODE=${LT_MODE:-real}
IMAGE=ssample-loadtest-backend:457
LOCK_FILE=${LT_LOCK_FILE:-/tmp/ssuksak-deploy.lock}
PROD_ENV=${LT_PROD_ENV:-/home/ubuntu/ktc4-kangwon-2/.env}
PROD_BACKEND=${LT_PROD_BACKEND:-ktc4-kangwon-2-backend-1}
# 세 상한 합(512 + 1024 + 256) + 운영 여유 500 (MiB). compose.loadtest.yml 의 mem_limit 와 같이 바꾼다.
NEED_AVAILABLE_MB=2292

case "$LT_MODE" in
  real) WANT_SERVER=1 ;;
  mock) WANT_SERVER=0 ;;
  *) echo "LT_MODE 는 real | mock" >&2; exit 1 ;;
esac

docker() {
  if [ "${LT_SUDO:-0}" = 1 ]; then sudo docker "$@"; else command docker "$@"; fi
}

lt() {
  docker compose --project-directory "$LT_DIR" --env-file "$LT_DIR/.env" \
    -f "$LT_DIR/docker-compose.yml" -f "$LT_DIR/compose.loadtest.yml" \
    --profile loadgen -p loadtest "$@"
}

# ── gate ─────────────────────────────────────────────────────────────────────

GATE_PY='
import json, os, sys
from urllib.parse import urlparse

text = sys.stdin.read()
cfg = json.loads(text)
verbose = sys.argv[1:] == ["-v"]
mode, server = os.environ["LT_WANT_MODE"], os.environ["LT_WANT_SERVER"]
bad = 0


def check(ok, label):
    global bad
    if ok:
        if verbose:
            print("ok   ", label)
    else:
        bad += 1
        print("FAIL ", label)


def mib(service, key):
    try:
        return int(service.get(key)) // (1 << 20)
    except (TypeError, ValueError):
        return None


svc = cfg.get("services", {})
image = "ssample-loadtest-backend:457"
check(cfg.get("name") == "loadtest", "프로젝트 이름 loadtest")
check(set(svc) == {"db", "backend", "loadgen"}, "서비스 db backend loadgen 만 (지금 %s)" % sorted(svc))
for name, limit in (("db", 512), ("backend", 1024), ("loadgen", 256)):
    for key in ("mem_limit", "memswap_limit"):
        check(mib(svc.get(name, {}), key) == limit, "%s %s %dm" % (name, key, limit))
for name, s in svc.items():
    check(not s.get("ports"), "%s 호스트 포트 없음" % name)
    check(s.get("restart") == "no", "%s restart no" % name)
    check("build" not in s, "%s build 없음" % name)
    check(s.get("logging", {}).get("driver") != "journald", "%s 로그 journald 아님" % name)
for name in ("backend", "loadgen"):
    check(svc.get(name, {}).get("image") == image, "%s 이미지 %s" % (name, image))
check(not svc.get("loadgen", {}).get("depends_on"), "loadgen depends_on 없음")
env = svc.get("backend", {}).get("environment", {})
check(env.get("LOADTEST") == "1", "backend LOADTEST=1")
check(env.get("LLM_MODE") == mode, "backend LLM_MODE=%s (지금 %s)" % (mode, env.get("LLM_MODE")))
check(env.get("IS_SERVER") == server, "backend IS_SERVER=%s (지금 %s)" % (server, env.get("IS_SERVER")))
check(env.get("ALLOW_TEST_RESET") == "0", "backend ALLOW_TEST_RESET=0")
check(urlparse(env.get("DATABASE_URL", "")).hostname == "db", "backend DATABASE_URL 호스트 db")
check(
    set(svc.get("loadgen", {}).get("environment", {})) == {"DATABASE_URL", "LOADTEST"},
    "loadgen 환경변수는 DATABASE_URL · LOADTEST 뿐 (LLM 설정 없음)",
)
net = cfg.get("networks", {}).get("default", {})
check(net.get("name") == "loadtest_default", "망 이름 loadtest_default")
check(
    net.get("ipam", {}).get("config") == [{"subnet": "172.29.0.0/16", "gateway": "172.29.0.1"}],
    "망 대역은 172.29.0.0/16 하나",
)
vols = cfg.get("volumes", {})
check(vols.get("pgdata", {}).get("name") == "loadtest_pgdata", "볼륨 loadtest_pgdata")
check(all(v.get("name", "").startswith("loadtest_") for v in vols.values()), "모든 볼륨 이름이 loadtest_ 로 시작")
for needle in ("ktc4-kangwon-2", "172.28.", "journald"):
    check(needle not in text, "설정 어디에도 %s 없음" % needle)
sys.exit(1 if bad else 0)
'

gate() {
  command -v python3 >/dev/null || { echo "FAIL python3 가 없다"; exit 1; }
  local f
  for f in .env docker-compose.yml compose.loadtest.yml load_check.py; do
    [ -f "$LT_DIR/$f" ] || { echo "FAIL $LT_DIR/$f 가 없다"; exit 1; }
  done
  local cfg
  cfg=$(lt config --format json) || { echo "FAIL docker compose config 가 실패했다"; exit 1; }
  printf '%s' "$cfg" \
    | LT_WANT_MODE="$LT_MODE" LT_WANT_SERVER="$WANT_SERVER" python3 -c "$GATE_PY" "$@" \
    || { echo "게이트 실패 — 멈춘다"; exit 1; }
  [ "${1:-}" = "-v" ] && echo "게이트 통과"
  return 0
}

# ── 준비 ─────────────────────────────────────────────────────────────────────

cmd_preflight() {
  local bad=0 avail n
  echo "운영 backend: $(docker inspect "$PROD_BACKEND" --format '{{.Image}} {{.State.Status}} 로그={{.HostConfig.LogConfig.Type}}' 2>&1 || true)"
  if [ -n "${LT_AVAILABLE_MB:-}" ]; then
    avail=$LT_AVAILABLE_MB
  elif command -v free >/dev/null; then
    free -m
    avail=$(free -m | awk '/^Mem:/ {print $7}')
  else
    avail=""
  fi
  df -h / | tail -1
  if [ -z "$avail" ]; then
    echo "FAIL available 메모리를 못 읽었다"; bad=1
  elif [ "$avail" -lt "$NEED_AVAILABLE_MB" ]; then
    echo "FAIL available ${avail}MB < ${NEED_AVAILABLE_MB}MB (세 상한 합 1792 + 운영 여유 500)"; bad=1
  else
    echo "ok   available ${avail}MB >= ${NEED_AVAILABLE_MB}MB"
  fi
  n=$(docker network inspect $(docker network ls -q) --format '{{range .IPAM.Config}}{{.Subnet}} {{end}}' | grep -c '172\.29\.' || true)
  [ "$n" = 0 ] && echo "ok   172.29 대역 비어 있다" || { echo "FAIL 172.29 대역을 쓰는 망이 있다"; bad=1; }
  n=$(docker volume ls --format '{{.Name}}' | grep -c '^loadtest' || true)
  [ "$n" = 0 ] && echo "ok   loadtest 볼륨 없다" || { echo "FAIL loadtest 볼륨이 남아 있다"; bad=1; }
  n=$(docker ps -a --format '{{.Names}}' | grep -c '^loadtest' || true)
  [ "$n" = 0 ] && echo "ok   loadtest 컨테이너 없다" || { echo "FAIL loadtest 컨테이너가 남아 있다"; bad=1; }
  # SSM 이 보낸 deploy.sh 는 root 로 시작해 /tmp/ssuksak-deploy.XXXXXX.sh 사본으로 ubuntu 에서 이어 돈다.
  if pgrep -f 'scripts/deploy\.sh|ssuksak-deploy\.' >/dev/null 2>&1; then
    echo "FAIL 서버에서 deploy.sh 가 돌고 있다"; bad=1
  else
    echo "ok   도는 deploy.sh 없다"
  fi
  if command -v flock >/dev/null; then
    if flock -n "$LOCK_FILE" true 2>/dev/null; then
      echo "ok   배포 잠금($LOCK_FILE)을 아무도 안 쥐고 있다"
    else
      echo "FAIL 배포 잠금($LOCK_FILE)을 누가 쥐고 있다"; bad=1
    fi
  else
    echo "--   flock 이 없어 잠금 확인을 건너뛴다(로컬). 서버에서는 lock 이 어차피 flock 을 요구한다"
  fi
  if [ "${LT_SKIP_SSM:-0}" = 1 ]; then
    echo "--   SSM 배포 명령 확인을 건너뛴다(LT_SKIP_SSM=1 — 로컬 리허설만)"
  elif [ -z "${LT_SSM_INSTANCE:-}" ]; then
    echo "FAIL LT_SSM_INSTANCE 가 없다 — SSM 에서 도는 배포 명령을 확인하지 못했다"; bad=1
  else
    n=$(aws ssm list-commands --region ap-northeast-2 --instance-id "$LT_SSM_INSTANCE" \
      --query "length(Commands[?Status=='InProgress'||Status=='Pending'])" --output text) \
      || { echo "FAIL SSM 조회가 실패했다"; bad=1; n=""; }
    if [ -n "$n" ]; then
      [ "$n" = 0 ] && echo "ok   SSM 에서 도는 명령 없다" || { echo "FAIL SSM 에서 도는 명령이 ${n}개 있다"; bad=1; }
    fi
  fi
  [ "$bad" = 0 ] || { echo "preflight 실패 — 멈춘다"; exit 1; }
  echo "preflight 통과"
}

cmd_env() {
  [ ! -e "$LT_DIR/.env" ] || { echo "거절: $LT_DIR/.env 가 이미 있다"; exit 1; }
  umask 077
  local pw secret
  pw=$(openssl rand -hex 24)
  secret=$(openssl rand -hex 32)
  {
    echo "COMPOSE_PROJECT_NAME=loadtest"
    echo "COMPOSE_FILE=docker-compose.yml:compose.loadtest.yml"
    echo "POSTGRES_PASSWORD=$pw"
    echo "DATABASE_URL=postgresql+psycopg://ssuksak:$pw@db:5432/ssuksak"
    echo "SECRET_KEY=$secret"
    echo "LLM_MODE=$LT_MODE"
    echo "IS_SERVER=$WANT_SERVER"
    echo "ALLOW_TEST_RESET=0"
  } > "$LT_DIR/.env"
  if [ "$LT_MODE" = real ]; then
    # 화면에 안 찍는다. 두 줄이 아니면 만든 .env 를 지우고 멈춘다.
    grep -E '^(ELICE_MLAPI_BASE_URL|ELICE_MLAPI_API_KEY)=' "$PROD_ENV" >> "$LT_DIR/.env" || true
    if [ "$(grep -c '^ELICE_MLAPI_' "$LT_DIR/.env")" != 2 ]; then
      rm -f "$LT_DIR/.env"
      echo "거절: 운영 .env 에서 ELICE_MLAPI_BASE_URL · ELICE_MLAPI_API_KEY 두 줄을 못 찾았다 — .env 를 지웠다"
      exit 1
    fi
  fi
  echo ".env 를 만들었다 (키 이름만): $(cut -d= -f1 "$LT_DIR/.env" | tr '\n' ' ')"
}

cmd_tag() {
  local img
  img=$(docker inspect "$PROD_BACKEND" --format '{{.Image}}')
  docker tag "$img" "$IMAGE"
  [ "$(docker image inspect "$IMAGE" --format '{{.Id}}')" = "$img" ] || { echo "FAIL 태그가 운영 이미지와 다르다"; exit 1; }
  echo "$IMAGE ← $img (운영 $PROD_BACKEND 의 이미지)"
}

# ── 띄우기 · 부하 · 정리 ─────────────────────────────────────────────────────

wait_ready() {
  local i
  for i in $(seq 30); do
    lt exec -T backend python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health/ready')" >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

cmd_up() {
  gate
  lt up -d --wait db
  gate
  lt run --rm --no-deps backend alembic upgrade head
  gate
  lt up -d --no-build backend
  wait_ready || { echo "backend 가 60초 안에 안 떴다"; lt logs --tail 30 backend; exit 1; }
  lt exec -T backend python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/health/ready').read())"
  lt ps
}

cmd_loadgen() {
  gate
  mkdir -p "$LT_DIR/out"
  lt run --rm --no-deps -T loadgen "$@"
}

dump_log() {
  local f="backend-$(date -u +%Y%m%dT%H%M%SZ).log"
  lt logs -t --no-color backend > "$LT_DIR/out/$f"
  echo "$f"
}

cmd_stage() {
  [ $# -eq 1 ] || { echo "사용: stage <시나리오>:<n>x<반복>   예) stage s2:10x2"; exit 1; }
  local f
  gate
  mkdir -p "$LT_DIR/out"
  f=$(dump_log)
  cmd_loadgen analyze --out /lt/out --backend-log "/lt/out/$f" --next "$1" --last-only \
    | tee "$LT_DIR/out/analysis-${f%.log}.txt"
}

cmd_final() {
  local f
  gate
  mkdir -p "$LT_DIR/out"
  f=$(dump_log)
  cmd_loadgen analyze --out /lt/out --backend-log "/lt/out/$f" | tee "$LT_DIR/out/analysis-final.txt"
}

cmd_down() {
  gate
  mkdir -p "$LT_DIR/out"
  lt logs -t --no-color backend > "$LT_DIR/out/backend-final.log" || echo "경고: 마지막 로그를 못 덤프했다(컨테이너가 이미 없다?)"
  lt down -v
  docker rmi "$IMAGE" || echo "경고: 태그를 못 지웠다 (-f 는 쓰지 않는다)"
  local left=0 n
  n=$(docker volume ls --format '{{.Name}}' | grep -c '^loadtest' || true)
  [ "$n" = 0 ] || { echo "남음: loadtest 볼륨 ${n}개"; left=1; }
  n=$(docker network ls --format '{{.Name}}' | grep -c '^loadtest' || true)
  [ "$n" = 0 ] || { echo "남음: loadtest 망 ${n}개"; left=1; }
  n=$(docker ps -a --format '{{.Names}}' | grep -c '^loadtest' || true)
  [ "$n" = 0 ] || { echo "남음: loadtest 컨테이너 ${n}개"; left=1; }
  n=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -c '^ssample-loadtest' || true)
  [ "$n" = 0 ] || { echo "남음: ssample-loadtest 이미지 태그 ${n}개"; left=1; }
  [ "$left" = 0 ] || exit 1
  echo "정리 끝 — loadtest 흔적 없음. out/ 를 옮긴 뒤 $LT_DIR 를 지운다"
}

# ── 서버 배포 잠금 ───────────────────────────────────────────────────────────
# scripts/deploy.sh 는 `exec 9>/tmp/ssuksak-deploy.lock; flock -w 300 9` 로 잠근다(ubuntu 쪽에서).
# 같은 파일에 flock 을 쥐면 그동안 오는 배포는 300초 기다리다 「잠금을 못 잡았다 … 서버는 바꾸지 않았다」 로 1 에 끝난다.
# 쥐는 프로세스는 `exec sleep` 이다 — 이 pid 를 죽이면 풀린다(sleep 이 열린 fd 를 쥐고 있다).

lock_pid() { cat "$LT_DIR/deploy-lock.pid" 2>/dev/null || true; }

# pid 파일은 **잠금을 잡은 뒤에** 자식이 쓴다. 잠금을 누가 쥐고 있는지(배포가 쥔 것인지 우리 것인지)는
# `flock -n` 으로는 가를 수 없어서, 파일이 생겼다는 것이 「우리가 잡았다」는 표지다.
cmd_lock() {
  command -v flock >/dev/null || { echo "FAIL flock 이 없다"; exit 1; }
  local pid i
  pid=$(lock_pid)
  if [ -n "$pid" ]; then
    kill -0 "$pid" 2>/dev/null && { echo "거절: 이미 잠금을 쥐고 있다 (pid $pid)"; exit 1; }
    rm -f "$LT_DIR/deploy-lock.pid"   # 죽은 pid 가 남은 것이다
  fi
  setsid bash -c 'exec 8>"$2"; flock -w 60 8 || exit 1; echo $$ > "$1"; exec sleep "$3"'     _ "$LT_DIR/deploy-lock.pid" "$LOCK_FILE" "${LT_LOCK_SECONDS:-14400}" >/dev/null 2>&1 </dev/null &
  for i in $(seq 70); do
    pid=$(lock_pid)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && ! flock -n "$LOCK_FILE" true 2>/dev/null; then
      echo "배포 잠금을 쥐었다: $LOCK_FILE (pid $pid, 최대 ${LT_LOCK_SECONDS:-14400}초). 끝나면 unlock"
      return 0
    fi
    sleep 1
  done
  echo "FAIL 배포 잠금을 못 잡았다 — 다른 배포가 60초 넘게 돌고 있거나 잠금 파일을 못 연다. 측정하지 않는다"
  exit 1
}

cmd_unlock() {
  local pid
  pid=$(lock_pid)
  [ -n "$pid" ] || { echo "쥔 잠금이 없다"; return 0; }
  if [ "$(cat "/proc/$pid/comm" 2>/dev/null || ps -o comm= -p "$pid" 2>/dev/null)" = sleep ]; then
    kill "$pid"
  else
    echo "경고: pid $pid 가 우리 sleep 이 아니다 — 죽이지 않는다"
  fi
  rm -f "$LT_DIR/deploy-lock.pid"
  sleep 1
  if flock -n "$LOCK_FILE" true 2>/dev/null; then echo "배포 잠금을 풀었다"; else echo "FAIL 잠금이 아직 잡혀 있다"; exit 1; fi
}

# ── 진입 ─────────────────────────────────────────────────────────────────────

cmd=${1:-}
[ $# -gt 0 ] && shift
case "$cmd" in
  preflight) cmd_preflight ;;
  env) cmd_env ;;
  tag) cmd_tag ;;
  gate) gate "${1:--q}" ;;
  up) cmd_up ;;
  loadgen) cmd_loadgen "$@" ;;
  stage) cmd_stage "$@" ;;
  final) cmd_final ;;
  lock) cmd_lock ;;
  unlock) cmd_unlock ;;
  down) cmd_down ;;
  ps) lt ps ;;
  *) sed -n '2,22p' "$0"; exit 1 ;;
esac
