#!/usr/bin/env bash
# 동시 생성 부하 측정(#457)의 서버 · 로컬 작업 스크립트. 절차는 docs/load-check.md.
#
#   bash loadtest.sh <명령> [인자]
#
#   preflight        읽기만 한다. 도구 · 운영 backend · 메모리 · 망 대역 · 볼륨 · 도는 배포를 본다
#   env              .env 를 만든다(이미 있으면 거절)
#   tag              운영 backend 이미지에 loadtest 태그를 붙인다
#   gate [-v]        docker compose config 를 JSON 으로 받아 loadtest_gate.py 로 검사. 어긋나면 exit 1
#   up               [잠금] gate → db → gate → alembic → gate → backend → 준비될 때까지
#   loadgen ARGS…    부하기(load_check.py)를 일회용 컨테이너로. setup · burst 는 [잠금]
#   stage            로그를 덤프하고 마지막 단계를 분석한다(읽기)
#   budget           기준선 로그로 남은 계획 전체의 예산을 한 번 판정한다. 진행 가능이 아니면 exit 1
#   final            전체 표(읽기)
#   down             [잠금] gate → 로그 덤프 → down -v → 태그 삭제 → 남은 것이 없는지
#   locked CMD…      배포 잠금을 잡고 CMD 를 돈다(잠금 확인용)
#   ps
#
# **이 스크립트는 loadtest 프로젝트만 건드린다.** 모든 compose 명령이 `lt()` 하나를 지나고,
# 거기서 프로젝트 이름(-p loadtest) · 파일(-f) · env 파일을 명령줄로 못 박는다 — 셸의 COMPOSE_PROJECT_NAME 은
# 파일 안의 `name:` 보다 우선해서, 파일만 믿으면 운영 이름의 망 · 볼륨으로 렌더링된다.
# 그래서 시작할 때 셸의 COMPOSE_* 를 지우고, 있었다면 거절한다(오염된 셸이다).
#
# **[잠금]** 서버 DB 를 바꾸거나 LLM 을 부르는 단계는 `scripts/deploy.sh` 와 같은 파일 `/tmp/ssuksak-deploy.lock` 에
# `flock -w 60` 을 건 채로 돈다. 못 잡으면 그 단계를 돌리지 않고 exit 1. 단계가 끝나거나 죽으면 잠금은 저절로 풀린다.
# 단계 사이는 막지 못한다 — 그 사이는 Deploy 워크플로 비활성화가 막는다(docs/load-check.md).
#
# 환경변수(모두 선택):
#   LT_DIR           작업 폴더. 기본 /home/ubuntu/loadtest-457
#   LT_MODE          real(기본) | mock — mock 은 로컬 리허설용. real 이면 .env 에 IS_SERVER=1 · 엘리스 값
#   LT_SUDO=1        docker 앞에 sudo
#   LT_PROD_ENV · LT_PROD_BACKEND   운영 .env 경로 · 운영 backend 컨테이너 이름
#   LT_SSM_INSTANCE  SSM 에서 도는 배포 명령을 볼 인스턴스(real 에서는 필수)
#   --- 아래는 mock 일 때만 읽는다(real 에서는 무시 — 서버에서 우회로가 되지 않게) ---
#   LT_LOCK          잠금 파일 경로. none 이면 잠금을 건너뛴다(flock 이 없는 macOS 리허설)
#   LT_LOCK_WAIT     잠금을 기다리는 초(기본 60)
#   LT_AVAILABLE_MB  preflight 의 available 메모리를 직접 준다
#   LT_SKIP_SSM=1    SSM 확인을 건너뛴다
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
PROD_ENV=${LT_PROD_ENV:-/home/ubuntu/ktc4-kangwon-2/.env}
PROD_BACKEND=${LT_PROD_BACKEND:-ktc4-kangwon-2-backend-1}
# 세 상한 합(512 + 1024 + 256) + 운영 여유 500 (MiB). compose.loadtest.yml · loadtest_gate.py 의 상한과 같이 바꾼다.
NEED_AVAILABLE_MB=2292

case "$LT_MODE" in
  real)
    WANT_SERVER=1
    LOCK_FILE=/tmp/ssuksak-deploy.lock
    LOCK_WAIT=60
    ;;
  mock)
    WANT_SERVER=0
    LOCK_FILE=${LT_LOCK:-/tmp/ssuksak-deploy.lock}
    LOCK_WAIT=${LT_LOCK_WAIT:-60}
    ;;
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

gate() {
  command -v python3 >/dev/null || { echo "FAIL python3 가 없다"; exit 1; }
  local f cfg
  for f in .env docker-compose.yml compose.loadtest.yml load_check.py loadtest_gate.py; do
    [ -f "$LT_DIR/$f" ] || { echo "FAIL $LT_DIR/$f 가 없다"; exit 1; }
  done
  cfg=$(lt config --format json) || { echo "FAIL docker compose config 가 실패했다"; exit 1; }
  printf '%s' "$cfg" \
    | LT_WANT_MODE="$LT_MODE" LT_WANT_SERVER="$WANT_SERVER" LT_DIR="$LT_DIR" \
      python3 "$LT_DIR/loadtest_gate.py" "$@" \
    || { echo "게이트 실패 — 멈춘다"; exit 1; }
  [ "${1:-}" = "-v" ] && echo "게이트 통과"
  return 0
}

# ── 배포 잠금 ────────────────────────────────────────────────────────────────
# scripts/deploy.sh 는 ubuntu 쪽에서 `exec 9>/tmp/ssuksak-deploy.lock; flock -w 300 9` 로 잠근다. 같은 파일을 같은 방식으로 잠근다.
# 이 프로세스(= 이 단계)가 끝나거나 죽으면 fd 가 닫혀 잠금이 풀린다. 뒤에 남는 프로세스가 없다.

with_lock() {
  if [ "$LOCK_FILE" = none ]; then "$@"; return; fi
  command -v flock >/dev/null || { echo "FAIL flock 이 없다 — 배포 잠금을 못 잡아 이 단계를 돌리지 않는다"; exit 1; }
  exec 9>"$LOCK_FILE" || { echo "FAIL 잠금 파일을 못 연다: $LOCK_FILE"; exit 1; }
  flock -w "$LOCK_WAIT" 9 \
    || { echo "FAIL 배포 잠금($LOCK_FILE)을 ${LOCK_WAIT}초 안에 못 잡았다 — 이 단계를 돌리지 않는다"; exit 1; }
  "$@"
}

# ── 준비 ─────────────────────────────────────────────────────────────────────

cmd_preflight() {
  local bad=0 avail rc state ids subnets names n t
  ok() { echo "ok   $*"; }
  fail() { echo "FAIL $*"; bad=1; }

  for t in python3 openssl pgrep; do
    command -v "$t" >/dev/null && ok "$t 있다" || fail "$t 가 없다"
  done
  [ "$LOCK_FILE" = none ] || { command -v flock >/dev/null && ok "flock 있다" || fail "flock 이 없다"; }
  [ "$LT_MODE" = mock ] && [ "${LT_SKIP_SSM:-0}" = 1 ] || {
    command -v aws >/dev/null && ok "aws 있다" || fail "aws 가 없다"
  }

  state=$(docker inspect "$PROD_BACKEND" --format '{{.State.Running}} {{.Image}} 로그={{.HostConfig.LogConfig.Type}}') \
    || state=""
  if [ -z "$state" ]; then
    fail "운영 backend($PROD_BACKEND)를 조회하지 못했다"
  elif [ "${state%% *}" != true ]; then
    fail "운영 backend 가 Running 이 아니다: $state"
  else
    ok "운영 backend 실행 중: $state"
  fi

  df -h / | tail -1
  avail=""
  if [ "$LT_MODE" = mock ] && [ -n "${LT_AVAILABLE_MB:-}" ]; then
    avail=$LT_AVAILABLE_MB
  elif command -v free >/dev/null; then
    free -m
    avail=$(free -m | awk '/^Mem:/ {print $7}')
  fi
  if [ -z "$avail" ]; then
    fail "available 메모리를 못 읽었다"
  elif [ "$avail" -lt "$NEED_AVAILABLE_MB" ]; then
    fail "available ${avail}MB < ${NEED_AVAILABLE_MB}MB (세 상한 합 1792 + 운영 여유 500)"
  else
    ok "available ${avail}MB >= ${NEED_AVAILABLE_MB}MB"
  fi

  if ids=$(docker network ls -q) && subnets=$(docker network inspect $ids --format '{{range .IPAM.Config}}{{.Subnet}} {{end}}'); then
    n=$(grep -c '172\.29\.' <<<"$subnets" || true)
    [ "$n" = 0 ] && ok "172.29 대역 비어 있다" || fail "172.29 대역을 쓰는 망이 있다"
  else
    fail "docker 망 조회가 실패했다"
  fi
  if names=$(docker volume ls --format '{{.Name}}'); then
    n=$(grep -c '^loadtest' <<<"$names" || true)
    [ "$n" = 0 ] && ok "loadtest 볼륨 없다" || fail "loadtest 볼륨이 남아 있다"
  else
    fail "docker 볼륨 조회가 실패했다"
  fi
  if names=$(docker ps -a --format '{{.Names}}'); then
    n=$(grep -c '^loadtest' <<<"$names" || true)
    [ "$n" = 0 ] && ok "loadtest 컨테이너 없다" || fail "loadtest 컨테이너가 남아 있다"
  else
    fail "docker 컨테이너 조회가 실패했다"
  fi

  # SSM 이 보낸 deploy.sh 는 root 로 시작해 /tmp/ssuksak-deploy.XXXXXX.sh 사본으로 ubuntu 에서 이어 돈다.
  # pgrep: 0 = 찾았다 · 1 = 없다 · 그 밖 = 조회 실패. 조회 실패는 「없다」가 아니다.
  rc=0
  pgrep -f 'scripts/deploy\.sh|ssuksak-deploy\.' >/dev/null 2>&1 || rc=$?
  case $rc in
    0) fail "서버에서 deploy.sh 가 돌고 있다" ;;
    1) ok "도는 deploy.sh 없다" ;;
    *) fail "pgrep 이 실패했다 (코드 $rc)" ;;
  esac
  if [ "$LOCK_FILE" != none ] && command -v flock >/dev/null; then
    if ( exec 8>"$LOCK_FILE" && flock -n 8 ); then
      ok "배포 잠금($LOCK_FILE)을 아무도 안 쥐고 있다"
    else
      fail "배포 잠금($LOCK_FILE)을 누가 쥐고 있거나 파일을 못 연다"
    fi
  fi

  if [ "$LT_MODE" = mock ] && [ "${LT_SKIP_SSM:-0}" = 1 ]; then
    echo "--   SSM 배포 명령 확인을 건너뛴다(mock · LT_SKIP_SSM=1 — 로컬 리허설만)"
  elif [ -z "${LT_SSM_INSTANCE:-}" ]; then
    fail "LT_SSM_INSTANCE 가 없다 — SSM 에서 도는 배포 명령을 확인하지 못했다"
  else
    # ubuntu 의 역할에 ssm:ListCommands 가 있어야 한다. 조회가 실패하면 「없다」가 아니라 실패다.
    if n=$(aws ssm list-commands --region ap-northeast-2 --instance-id "$LT_SSM_INSTANCE" \
      --query "length(Commands[?Status=='InProgress'||Status=='Pending'||Status=='Cancelling'])" --output text); then
      [ "$n" = 0 ] && ok "SSM 에서 도는 명령 없다" || fail "SSM 에서 도는 명령이 ${n}개 있다 (InProgress · Pending · Cancelling)"
    else
      fail "SSM 조회가 실패했다 (ssm:ListCommands 권한?)"
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
  local f
  gate
  mkdir -p "$LT_DIR/out"
  f=$(dump_log)
  cmd_loadgen analyze --out /lt/out --backend-log "/lt/out/$f" --last-only \
    | tee "$LT_DIR/out/analysis-${f%.log}.txt"
}

cmd_budget() {
  local f
  gate
  mkdir -p "$LT_DIR/out"
  f=$(dump_log)
  cmd_loadgen budget --out /lt/out --backend-log "/lt/out/$f" | tee "$LT_DIR/out/budget.txt"
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

# ── 진입 ─────────────────────────────────────────────────────────────────────

cmd=${1:-}
[ $# -gt 0 ] && shift
case "$cmd" in
  preflight) cmd_preflight ;;
  env) cmd_env ;;
  tag) cmd_tag ;;
  gate) gate "${1:--q}" ;;
  up) with_lock cmd_up ;;
  loadgen)
    case "${1:-}" in
      setup | burst) with_lock cmd_loadgen "$@" ;;
      *) cmd_loadgen "$@" ;;
    esac
    ;;
  stage) cmd_stage ;;
  budget) cmd_budget ;;
  final) cmd_final ;;
  down) with_lock cmd_down ;;
  locked) with_lock "$@" ;;
  ps) lt ps ;;
  *) sed -n '2,24p' "$0"; exit 1 ;;
esac
