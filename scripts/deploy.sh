#!/usr/bin/env bash
# 서버에서 도는 배포 스크립트. GitHub Actions 가 SSM send-command 로 이 파일의
# 내용을 통째로 보낸다(scripts/ssm-deploy.sh 가 보내고 .github/workflows/deploy.yml 이 그것을 부른다).
# 서버에 미리 있을 필요가 없다.
#
# **이 쉬뱅이 보내는 글의 첫 줄이어야 한다.** SSM 은 `commands` 배열을 줄로 이어 붙여
# 한 파일로 만들고, 첫 줄이 `#!` 가 아니면 bash 가 아니라 `sh`(우분투는 dash)로 돈다.
# dash 에는 `pipefail` 이 없어서 아래 `set -Eeuo pipefail` 에서 바로 죽는다
# (2026-10-20 에 실제로 당했다 — `_script.sh: 9: set: Illegal option -o pipefail`).
# ssm-deploy.sh 가 앞에 다른 줄을 끼울 일이 생기면 쉬뱅을 맨 앞에 따로 넣어 준다.
#
# 손으로 배포할 때도 같은 것을 쓴다 — Session Manager 로 들어가서
#   bash /home/ubuntu/ktc4-kangwon-2/scripts/deploy.sh
# 자동과 수동이 다른 명령을 돌면 「손으로는 되는데 CI 는 안 된다」가 생긴다.
#
# **종료 코드에 뜻이 있다**(ADR-078). deploy.yml 의 알림이 이 숫자를 읽는다. 다른 명령이 어떤 코드로 죽어도 아래 넷 밖은 안 나온다.
#   0  성공
#   3  컨테이너를 바꾼 뒤 실패했고, 직전 성공 커밋의 deploy.sh 가 그 커밋으로 되돌렸다(서버는 그 커밋으로 돈다)
#   4  컨테이너를 바꾼 뒤 실패했고, 못 되돌렸다 — 자동 롤백이 꺼져 있거나 · 직전 성공 기록이 없거나 · 그 커밋에 deploy.sh 가 없거나 ·
#      그 deploy.sh 가 0 이 아니게 끝났다. 서비스 상태를 모른다
#   1  컨테이너를 바꾸기 전에 멈췄다(판정 거절 · 잠금 · build · 마이그레이션 …)
# 1 인지 4 인지는 `swapped`(`up -d` 를 부르기 직전에 1) 하나가 정한다. 명시적 `exit` 도, 예상 밖 실패를 받는 ERR 트랩도
# `die` · `on_err` 를 지나므로 교체 뒤 실패가 1 로 새지 않는다. docker 나 git 이 3 으로 죽어도 3 은 안 나온다.
# 트랩은 `set +e` 로도 안 꺼진다. 명령의 코드를 직접 받아야 하면 `|| status=$?` 로 받는다(아래 root → ubuntu).
set -Eeuo pipefail
trap 'on_err "$BASH_COMMAND"' ERR

DEPLOY_PATH=/home/ubuntu/ktc4-kangwon-2
REPO_URL=https://github.com/kakaotechcampus-4/ktc4-kangwon-2.git

# 교체 뒤 서버 안에서 서비스를 묻는 횟수 · 간격(초), 서버 잠금 파일 · 기다리는 시간(초), 마지막 성공 커밋을 적어 두는 파일,
# build 출력 파일. 환경변수로 받지 않는다 — 서버에 남은 값이 배포를 바꾸면 안 된다. 시험은 source 한 뒤에 바꾼다.
# 2초 × 30번이면 빠른 실패는 약 60초, curl 이 5초씩 다 쓰면 약 360초다.
# 잠금 300초 + 이번 배포 + 되돌리기가 SSM 한도(executionTimeout 2700초) 안에 들어야 한다.
# LAST_GOOD_FILE 은 저장소 밖(홈 폴더)에 둔다 — checkout 이 건드리지 않는다.
READY_TRIES=30
READY_INTERVAL=2
LOCK_FILE=/tmp/ssuksak-deploy.lock
LOCK_WAIT=300
LAST_GOOD_FILE=/home/ubuntu/.ssuksak-last-good
BUILD_LOG=/tmp/ssuksak-build.log

# 호출하는 쪽이 정하는 입력이다. '1' 이면 교체 뒤 실패를 직전 성공 커밋으로 되돌린다. deploy.yml 이 push 배포에는 늘 '1',
# 손 배포에는 auto_rollback 입력대로 넘긴다. Session Manager 로 손수 돌리면 없어서 꺼진다(`AUTO_ROLLBACK=1 bash …` 로 켠다).
# 위 상수와 달리 환경변수로 받아도 된다 — 켜는 쪽으로만 작용하고, 서버에 남아 있어도 되돌리기를 켤 뿐이라 안전한 쪽으로 틀린다.
AUTO_ROLLBACK=${AUTO_ROLLBACK:-0}

swapped=0       # `up -d` 직전에 1. 그 뒤의 실패는 서비스가 어떤 상태인지 모른다
last_good=""    # 서버가 기억한 마지막 성공 커밋(LAST_GOOD_FILE)
F_SHA=""        # 이번에 올리는 커밋

# <트리> 안에서 리비전 <rev> 를 **선언한** 파일 경로를 찍는다. 없으면 아무것도 안 찍는다.
# 파일 이름이 아니라 선언(`revision = '…'` · `revision: str = "…"` 둘 다 있다)을 본다 —
# `down_revision` 에 적힌 것은 선언이 아니다. <rev> 는 부르는 쪽이 12자리 16진수로 걸러 온다.
revision_file() {
  local tree=$1 rev=$2 out rc=0 f
  # 안쪽 `|| exit "$?"` 가 있어야 git grep 의 종료 코드가 바깥까지 온다 — 없으면 `$(…)` 안에서 ERR 트랩이 걸려 전부 1 이 된다.
  out=$(git grep -l -E "^revision(: str)? = ['\"]${rev}['\"]" "$tree" -- backend/alembic/versions/ || exit "$?") || rc=$?
  # git grep 은 못 찾으면 1, 깨지면 2 이상이다. 못 찾은 것은 「없다」이고 깨진 것은 오류다.
  [ "$rc" -le 1 ] || return "$rc"
  [ -n "$out" ] || return 0
  while IFS= read -r f; do printf '%s\n' "${f#"$tree":}"; done <<<"$out"
}

# 지금 DB 가 서 있는 리비전을 한 줄에 하나씩 찍는다.
# **지금 돌고 있는 backend 이미지로, 앱이 쓰는 DATABASE_URL 그대로** 읽는다. psql -d ssuksak 은
# 앱이 보는 DB 가 아닐 수 있다. 이 이미지는 checkout · build 전의 것이라 DB 가 서 있는 리비전을 안다.
db_revisions() {
  sudo docker compose run --rm -T --no-deps backend python -c '
import os
from sqlalchemy import create_engine, text
with create_engine(os.environ["DATABASE_URL"]).connect() as c:
    for (v,) in c.execute(text("SELECT version_num FROM alembic_version")):
        print(v)
'
}

# 이 커밋을 올려도 되나. 늘 0 으로 끝나고, 글자 하나로 답한다(ADR-073).
#   upgrade                  평소대로 `alembic upgrade head`
#   skip <R> <M> <B>         upgrade 를 건너뛴다. DB 는 리비전 R 에 있고 올릴 코드는 R 을 모른다
#   reject <이유>            checkout 하기 전에 멈춘다
# 인자는 <올릴 커밋 전체 SHA> <DB 리비전 글(db_revisions 출력)>.
#
# **`set -e` 에 기대지 않는다.** `if` · `$(…)` 안에서 불리면 errexit 이 꺼져서, 명령이 실패해도
# 다음 줄로 넘어가 엉뚱한 답이 나온다. 실패할 수 있는 명령마다 직접 검사하고 reject 로 답한다.
#
# 건너뛰는 것은 **R 을 들여온 PR 의 머지 직전 커밋(B)** 으로 되감을 때뿐이다. B 는 CI 의
# rollback compat 이 「새 스키마에서 B 코드가 도는지」를 시험한 유일한 코드다. 서버가 지금 도는 코드나
# 리비전의 부모로 판정하면 「A 는 칸을 쓰고, B 는 안 쓰고, C 가 지운다」에서 시험하지 않은 A 도 통과한다.
migration_step() {
  local target=$1 rev file m b
  # 리비전은 정확히 하나, 12자리 16진수. 둘 이상이면 갈래가 갈라진 것이라 어디로도 못 간다.
  rev=$(printf '%s\n' "$2" | grep -v '^$') || rev=""
  [[ "$rev" =~ ^[0-9a-f]{12}$ ]] || {
    echo "reject DB 리비전을 12자리 16진수 하나로 읽지 못했다 (읽은 줄 $(printf '%s' "$rev" | grep -c '^') 개)"
    return 0
  }

  # 올릴 코드가 R 파일을 갖는다 — 평소 배포 · 같은 SHA 재배포 · 롤백한 뒤 다시 앞으로.
  file=$(revision_file "$target" "$rev") || {
    echo "reject 올릴 커밋 ${target:0:8} 의 마이그레이션 폴더를 읽지 못했다"
    return 0
  }
  if [ -n "$file" ]; then
    echo upgrade
    return 0
  fi

  # 올릴 코드가 R 을 모른다 — 마이그레이션을 건너는 롤백이다. R 을 들여온 곳을 develop 에서 찾는다.
  file=$(revision_file origin/develop "$rev") || {
    echo "reject origin/develop 의 마이그레이션 폴더를 읽지 못했다"
    return 0
  }
  [ -n "$file" ] || {
    echo "reject DB 리비전 $rev 을 origin/develop 도 모른다 — 다른 브랜치에서 올라간 리비전이다"
    return 0
  }
  m=$(git log origin/develop --first-parent --diff-filter=A --format=%H -1 -- "$file") || m=""
  [ -n "$m" ] || {
    echo "reject 리비전 $rev 을 들여온 develop 커밋을 찾지 못했다"
    return 0
  }
  b=$(git rev-parse --verify --quiet "${m}^1") || b=""
  [ -n "$b" ] || {
    echo "reject 리비전 $rev 을 들여온 커밋 ${m:0:8} 의 앞 커밋을 찾지 못했다"
    return 0
  }

  if [ "$b" = "$target" ]; then
    echo "skip $rev $m $b"
  else
    echo "reject DB 가 $rev 에 있다(${m:0:8} 에서 들어왔다). 그것을 건너뛰는 되감기는 ${b:0:8} 로만 된다. 올리려는 ${target:0:8} 은 CI 가 시험한 적이 없다"
  fi
}

# 주소 하나를 물어 응답 코드를 찍는다. curl 이 응답을 받고도 도중에 죽었으면 코드 뒤에 curl 종료 코드를 붙여
# 200 으로 안 읽히게 한다(`200(curl 28)`). `-f` 를 쓰지 않는다 — `-f` 와 `|| echo 000` 을 같이 쓰면 `404000` 처럼 이어 붙는다.
# 종료 코드는 `$(…)` 밖에서 받지 못한다 — 그 안에서 죽은 명령에도 ERR 트랩이 걸려 1 로 바뀐다. 안에서 `||` 로 받는다.
probe() {
  curl -s -m 5 -o /dev/null -w '%{http_code}' "$1" || printf '(curl %s)' "$?"
}

# 교체가 끝난 서비스가 살아났는지 **서버 안에서** 본다(ADR-078). 러너가 인터넷을 건너 도메인으로 묻는
# deploy.yml 의 확인과 달리 DNS · 인증서 · IP 가 끼지 않는다. 안 살아났으면 1 을 돌려준다.
# `/health/ready`(backend · DB)와 `/`(frontend 화면)가 둘 다 200 이어야 한다. nginx 의 localhost 블록이 받는다 —
# 출발지는 172.28.0.1 로 보인다. `localhost` 는 ::1 로 붙어서 127.0.0.1 로 고정한다.
wait_ready() {
  local i ready=- page=-
  for ((i = 1; i <= READY_TRIES; i++)); do
    ready=$(probe http://127.0.0.1/health/ready)
    page=$(probe http://127.0.0.1/)
    if [ "$ready" = 200 ] && [ "$page" = 200 ]; then
      echo "서버 안 확인 통과 — health/ready 200 · 화면 200 (${i}회째)"
      return 0
    fi
    echo "서버 안 대기 ${i}/${READY_TRIES} — health/ready ${ready} · 화면 ${page}"
    sleep "$READY_INTERVAL"
  done
  echo "${READY_TRIES}번 물었지만 둘 다 200 이 오지 않았다 — 마지막 health/ready ${ready} · 화면 ${page}"
  return 1
}

# 서버를 안 바꿨을 때만 덧붙이는 글. 컨테이너를 바꾼 뒤에는 이 말이 거짓이다.
unless_swapped() { [ "$swapped" = 1 ] || printf '%s' "$1"; }

# 멈춘다. 1 인지 4 인지는 swapped 가 정한다. 명시적 exit 를 곳곳에 두면 교체 뒤 실패가 1 로 샌다.
# 교체 뒤면 결과 줄을 stderr 로도 찍는다. SSM 은 stdout 의 앞 24000자만 돌려줘서(run 42505477177 이 next build 출력 중간에서 잘렸다)
# 끝에 찍는 줄은 안 온다 — stderr 는 한도가 따로(8000자)고 평소 2K 안팎이라 결과 줄이 온다.
die() {
  echo "$*"
  if [ "$swapped" = 1 ]; then
    echo "되돌리지 않는다 — $*" >&2
  fi
  exit $((swapped ? 4 : 1))
}

# 예상 밖 명령이 죽었을 때(ERR 트랩). 교체 전이면 1, 뒤면 4. `$(…)` 안에서도 걸리는데 거기서는 조용히 나간다 —
# 바깥이 `|| die` 로 받아 한 번만 말한다.
on_err() {
  if [ "$BASH_SUBSHELL" = 0 ] && [ "$swapped" = 1 ]; then
    echo "되돌리지 않는다 — 교체 뒤 예상 밖 명령이 실패했다: $1" >&2
  fi
  exit $((swapped ? 4 : 1))
}

# 이번 배포가 서버 안 확인까지 통과했을 때만 부른다. 되돌리기 성공은 기록을 안 바꾼다(L 이 이미 적혀 있다).
# 40자리 16진수만 받는다(읽을 때도 같은 검사). 임시 파일에 쓰고 옮겨서 반쯤 쓰인 파일이 남지 않는다.
# 쓰기가 실패해도 배포 결과는 안 바꾼다 — 서버는 이미 새 커밋으로 돈다. 다음 롤백 대상이 옛것으로 남을 뿐이다.
record_good() {
  { printf '%s\n' "$1" > "$LAST_GOOD_FILE.tmp" && mv -f "$LAST_GOOD_FILE.tmp" "$LAST_GOOD_FILE"; } \
    || echo "직전 성공 기록을 쓰지 못했다 ($LAST_GOOD_FILE). 다음 롤백 대상이 옛 커밋으로 남는다"
}

# 컨테이너를 바꾼 뒤 실패했다. 직전 성공 커밋으로 되돌리거나, 못 되돌리면 4 로 끝난다. 늘 exit 한다.
# 결과 줄(「되돌렸다 → L」 · 「되돌리지 않는다 — 이유」 · 「되돌리기도 실패 — 이유」)은 stderr 로, 줄 맨 앞에 쓴다 —
# deploy.yml 이 이 줄 중 마지막 하나를 읽어 알림에 붙인다. 모양을 바꾸면 알림이 빈다.
#
# **되돌리기는 L 의 deploy.sh 로 한다**(하민 리뷰 ③). 이번 스크립트(F 의 것)가 망가졌으면 F 의 스크립트로는 되돌리기도 실패한다.
# `git show L:scripts/deploy.sh` 를 꺼내 자식 프로세스로 돌린다 — `DEPLOY_REF=L` 로, 자식이 또 되돌리지 않게 `AUTO_ROLLBACK=0` 으로.
# 자식은 L 시절의 판정 · build · 교체 · 확인을 L 의 코드로 한다. 자식이 0 이면 3, 아니면 4 다(자식의 3 도 4 다 — 자식이 자기 직전으로
# 되돌렸어도 L 에 도착한 것이 아니다).
#
# **L 의 스크립트가 잠금을 직접 잡을 때만 서버 잠금을 먼저 푼다.** 그런 자식은 같은 잠금을 기다리니, 안 풀면 부모(이 프로세스)를
# LOCK_WAIT 만큼 기다리다 실패한다. 푼 순간부터 자식이 다시 잡을 때까지 틈이 있다 — Actions 배포끼리는 concurrency 가 막고,
# Session Manager 와 겹칠 때만 열린다(ADR-078 한계). 이 PR 보다 옛 스크립트는 잠금이 없다(`flock` 글자가 없다). 그 자식은 잠금을
# 달라고 하지 않으니 풀 까닭이 없다 — 쥔 채로 돌려서 되돌리기 동안 다른 배포가 끼어들지 못하게 한다. 가르는 표지는 스크립트 안의
# `flock` 글자 하나다(주석에만 있어도 푼다 — 그 틈이 열릴 뿐이다).
# 자식의 stderr 는 stdout 으로 합친다(`2>&1`). 옛 스크립트의 build 출력이 SSM stderr 한도(8000자)를 채워 이 함수의 결과 줄을 밀어내지
# 못하게 한다. 부모의 결과 줄만 stderr 에 남는다.
#
# L 이 이 PR 보다 옛 스크립트면 서버 안 확인이 없어서 자식의 0 은 「배포는 끝남」까지만 뜻한다. 그때는 deploy.yml 의 밖 확인(3 이면 돈다)이
# 「되돌렸는데 밖에서 안 닿음」으로 대신 알린다. #445 보다 옛 스크립트면 마이그레이션 판정도 없다.
#
# **deploy_one 은 `||` · `&&` · `if` 안에서 부르지 않는다.** 거기서 부른 함수 안에서는 errexit 도 ERR 트랩도 꺼져서,
# 실패한 단계를 넘어 계속 가고 성공한 척한다. 이 함수 자체는 `cmd || swap_failed` 의 오른쪽이라 꺼지지 않는다.
swap_failed() {
  echo "교체한 서비스가 살아나지 않았다 — $1"
  if [ "$AUTO_ROLLBACK" != 1 ]; then
    echo "되돌리지 않는다 — 자동 롤백이 꺼져 있다 (손 배포는 AUTO_ROLLBACK=1)" >&2
    exit 4
  fi
  if [ -z "$last_good" ]; then
    echo "되돌리지 않는다 — 직전 성공 기록이 없다 ($LAST_GOOD_FILE)" >&2
    exit 4
  fi
  if [ "$last_good" = "$F_SHA" ]; then
    echo "되돌리지 않는다 — 직전 성공이 이번에 올린 커밋과 같다" >&2
    exit 4
  fi

  # 끝에 X 가 오게 — X 가 맨 끝이 아니면 BSD mktemp 는 글자 그대로의 이름을 만든다
  local script status=0
  script=$(mktemp "${TMPDIR:-/tmp}/ssuksak-rollback.XXXXXX") || die "임시 파일을 만들지 못했다"
  git show "$last_good:scripts/deploy.sh" > "$script" \
    || { rm -f "$script"; die "L 의 deploy.sh 를 꺼내지 못했다 (${last_good:0:8}:scripts/deploy.sh)"; }

  echo "되돌린다 → $last_good (L 의 deploy.sh)"
  if grep -q flock "$script"; then
    echo "L 의 deploy.sh 가 서버 잠금을 직접 잡는다 — 잠금을 풀고 돌린다"
    exec 9>&-
  else
    echo "L 의 deploy.sh 는 서버 잠금을 안 잡는 옛 스크립트다 — 잠금을 쥔 채 돌린다"
  fi
  # 자식의 종료 코드를 직접 받는다. `||` 뒤라 errexit · ERR 트랩이 자식의 0 이 아닌 코드를 1 로 바꾸지 않는다.
  env DEPLOY_REF="$last_good" AUTO_ROLLBACK=0 bash "$script" 2>&1 || status=$?
  rm -f "$script"
  # 앞서 stderr 에 나간 글이 줄바꿈 없이 끝났어도 결과 줄이 줄 맨 앞에 오게 한다
  echo >&2
  if [ "$status" -eq 0 ]; then
    echo "되돌렸다 → $last_good (L 의 deploy.sh)" >&2
    exit 3
  fi
  echo "되돌리기도 실패 — L 의 deploy.sh 가 $status 로 끝났다" >&2
  exit 4
}

# <sha> 를 올린다. <ref> 는 DEPLOY_REF — 브랜치 이름이거나 SHA.
# 교체 전 실패는 die · 트랩으로 1, 교체 뒤 실패는 `|| swap_failed`.
deploy_one() {
  local target=$1 ref=$2 revs step services rev m b

  # 마이그레이션을 건너뛰어도 되는지도 checkout 전에 정한다. 여기서 멈추면 서버 폴더와 이미지는
  # 그대로다 — 멈춘 뒤에 반쯤 바뀐 서버(옛 코드 폴더 + 새 DB)가 남지 않는다.
  revs=$(db_revisions) || die "DB 리비전을 읽지 못했다$(unless_swapped '. 서버는 바꾸지 않았다')"
  step=$(migration_step "$target" "$revs")
  case "$step" in
    reject*) die "배포를 멈춘다$(unless_swapped '. 서버는 바꾸지 않았다') — ${step#reject }" ;;
  esac

  # 브랜치면 origin 쪽을 따라가고, SHA 면 그 커밋으로 바로 간다.
  # `git reset --hard origin/<SHA>` 는 그런 ref 가 없어서 죽는다 — 갈라야 한다.
  if git rev-parse --verify --quiet "origin/$ref" >/dev/null; then
    git checkout -f "$ref"
    git reset --hard "origin/$ref"
  else
    # 커밋이다. Actions 배포는 늘 이리로 온다. 브랜치에서 떨어져 나온 상태(detached HEAD)가
    # 되는데 배포에는 문제가 없다. 서버에서 git pull 을 하지 않는다 — 붙은 브랜치가 없어 실패한다.
    git checkout -f --detach "$target"
  fi

  # fetch 가 실패하면 origin/<브랜치> 가 옛 커밋을 가리킨 채 남는다.
  # 그대로 reset 하면 조용히 과거로 돌아간다. 파일이 있는지 본다.
  test -f docker-compose.yml || die "docker-compose.yml 이 없다. fetch 가 안 됐다"

  # .env 는 커밋하지 않으므로 서버에만 있다.
  test -f .env || die ".env 가 없다. 서버에서 한 번 만들어야 한다"

  echo "배포 $ref $(git rev-parse --short HEAD) — $(git log -1 --format=%s)"

  # nginx 설정을 build · 마이그레이션 · 컨테이너 교체 전에 검사한다. 깨졌으면 여기서 멈춘다.
  # 파일은 위 checkout 으로 이미 바뀌었다 — 떠 있는 nginx 는 옛 설정으로 계속 돌지만 다시 시작되면 못 뜬다.
  # 새 컨테이너로 검사해서 방금 꺼낸 커밋의 compose 연결을 그대로 쓴다 — 롤백(옛 SHA)도 같은 길이다.
  # nginx -t 는 upstream 이름이 안 풀리면 실패한다. 앱이 죽어 있을 때(롤백이 그렇다)도 검사가 되게
  # compose 의 서비스 이름을 전부 자기 자신으로 둔다. 여기서 보는 건 문법 · 파일 · 인증서다.
  services=$(sudo docker compose config --services | tr '\n' ' ')
  sudo docker compose run --rm -T --no-deps nginx \
    sh -c "echo '127.0.0.1 $services' >> /etc/hosts && nginx -t"

  # build 출력은 길다(next build). SSM 이 stdout 앞 24000자만 돌려줘서 뒤에 오는 진단이 잘린다 —
  # 파일로 돌리고, 실패했을 때만 끝을 보인다.
  sudo docker compose build backend frontend >"$BUILD_LOG" 2>&1 || {
    echo "build 가 실패했다 — 끝 40줄 ($BUILD_LOG)"
    tail -n 40 "$BUILD_LOG" || true
    die "build 실패$(unless_swapped '. 컨테이너는 그대로다')"
  }

  # 마이그레이션을 앱보다 먼저 돌린다. 반대로 하면 새 코드가 없는 컬럼을 읽는다.
  # 건너뛸 때는 DB 가 올릴 코드보다 앞서 있다(한 칸 롤백). 코드가 모르는 리비전이라 upgrade 가 죽는다.
  case "$step" in
    skip*)
      read -r _ rev m b <<<"$step"
      echo "마이그레이션을 건너뛴다 — DB 는 ${rev}(${m:0:8} 에서 들어옴), 올리는 코드는 그 직전 ${b:0:8}. CI rollback compat 이 이 조합을 시험했다 (ADR-073)"
      ;;
    *)
      sudo docker compose run --rm backend alembic upgrade head
      ;;
  esac

  # 여기부터는 컨테이너를 바꾼다. 이 뒤의 실패는 서비스가 어떤 상태인지 모른다(4, 또는 L 의 deploy.sh 로 되돌린다).
  swapped=1
  sudo docker compose up -d || swap_failed "up -d 가 실패했다"

  # nginx 는 nginx/ 폴더를 통째로 본다(docker-compose.yml). 컨테이너를 다시 만들지 않으면
  # 새 설정을 안 읽으므로 reload 로 읽힌다. 접속은 안 끊기고, 진행 중인 요청은 끝까지 간다.
  # reload 가 안 되면 다시 시작한다 — up -d 가 방금 다시 만들어 아직 준비 전이거나, 재시작을 반복하는
  # 중일 때다(up -d 는 재시작 반복 중인 컨테이너를 건드리지 않는다). 그때 nginx 는 어차피 응답을 못 하고 있다.
  sudo docker compose exec -T nginx nginx -s reload || sudo docker compose restart nginx \
    || swap_failed "nginx reload 와 restart 가 둘 다 실패했다"

  # 교체가 끝났다. 서버 안에서 살아났는지 본다.
  wait_ready || swap_failed "서버 안 확인(health/ready · 화면)이 통과하지 못했다"
}

main() {
  # 무엇을 올릴지. 브랜치 이름이거나 커밋 SHA 다. 기본은 main 이다.
  #
  # **develop 을 올리는 일이 실제로 있다.** 멘토 리뷰 전에 서버에 미리 올려 두기 때문이다.
  # 전에는 이 값이 main 으로 박혀 있어서, 손으로 develop 을 올려 둔 서버에 자동 배포를
  # 한 번 돌리면 조용히 main 으로 되돌아갔다. 무엇이 돌고 있는지 아무도 모르게 된다.
  #
  # **Actions 는 늘 커밋 SHA 를 넘긴다**(deploy.yml 「올릴 커밋 고정」). 브랜치 이름을 넘기면
  # 이 스크립트가 도는 순간의 끝 커밋이 올라가서, 그 사이 들어온 머지가 다른 run 의 이름으로 나갔다.
  # 롤백도 같은 길이다 — 직전 성공 커밋의 deploy.sh 를 SHA 로 한 번 더 돈다(swap_failed). 롤백 전용 길을
  # 따로 만들지 않는다. 평소에 안 쓰는 길은 정작 급할 때 안 돈다.
  #   직전에 무엇이 돌았는지 보기:  서버가 기억한 마지막 성공(첫 줄 「직전 성공 …」), 또는 서버에서
  #   cd /home/ubuntu/ktc4-kangwon-2 && git log --oneline -5
  #
  # **마이그레이션을 건너는 롤백은 한 칸까지만 된다**(ADR-073). 마이그레이션이 든 PR 하나의
  # 머지 직전 커밋으로는 되감기고(upgrade 를 건너뛴다), 그보다 더 옛 커밋은 서버를 건드리기 전에 멈춘다.
  # 자동 롤백도 이 판정을 그대로 받는다.
  DEPLOY_REF="${DEPLOY_REF:-main}"
  case "$DEPLOY_REF" in
    *[!A-Za-z0-9._/-]*) die "브랜치 이름에 쓸 수 없는 글자가 있다: $DEPLOY_REF" ;;
  esac

  # SSM 은 root 로 돈다. git 을 root 로 돌리면 .git 안에 root 소유 파일이 생겨
  # 다음에 ubuntu 가 서버에서 손을 못 댄다. ubuntu 로 내려가서 돈다.
  # 이미 ubuntu 면(손으로 실행) 그냥 이어서 돈다.
  if [ "$(id -un)" != "ubuntu" ]; then
    # SSM 이 만든 원본 스크립트는 ubuntu 가 읽을 수 있다는 보장이 없다. 복사해서 넘긴다.
    INNER=$(mktemp /tmp/ssuksak-deploy.XXXXXX.sh)
    cat "$0" > "$INNER"
    chmod 0644 "$INNER"
    # 자식의 종료 코드를 그대로 낸다(3 · 4 가 알림 신호다). `set +e` 로 감싸면 안 된다 — ERR 트랩이 그래도 걸려서 1 이 된다.
    # `||` 뒤의 실패에는 트랩이 안 걸린다.
    status=0
    # runuser 가 환경을 물려준다는 보장이 없다. 쓰는 값은 손으로 넘긴다.
    runuser -u ubuntu -- env DEPLOY_REF="$DEPLOY_REF" AUTO_ROLLBACK="$AUTO_ROLLBACK" bash "$INNER" || status=$?
    rm -f "$INNER"
    exit "$status"
  fi

  # 서버에서 배포가 둘 겹치면 컨테이너가 반쯤 바뀐다. deploy.yml 의 concurrency 는 러너 쪽만 막는다 —
  # 손 배포(Session Manager)와 자동 배포가 서버에서 만나는 것은 이 잠금이 막는다. 프로세스가 끝나면 저절로 풀린다.
  # ubuntu 로 도는 쪽에서만 잠근다. root 쪽도 잠그면 자식이 같은 파일을 다시 잠그려다 부모를 기다린다.
  # 300초만 기다린다 — 잠금 + 배포 + 되돌리기가 SSM 한도 안에 들어야 해서다. 손 배포가 그보다 오래 쥐면 이 배포는 1 로 멈춘다.
  # 되돌리기 직전(swap_failed)에 이 잠금을 풀고, L 의 deploy.sh 가 자기 잠금을 다시 잡는다.
  exec 9>"$LOCK_FILE" || die "잠금 파일을 못 연다: $LOCK_FILE"
  flock -w "$LOCK_WAIT" 9 || die "잠금을 못 잡았다 — 다른 배포가 ${LOCK_WAIT}초 넘게 돌고 있거나 flock 이 없다. 서버는 바꾸지 않았다"

  # 서버가 기억한 마지막 성공 커밋. 서버 안 확인을 통과할 때마다 적는다(아래 record_good).
  # **이 스크립트를 지난 성공만 기록된다.** 옛 run 의 re-run 이나 옛 체크아웃의 deploy.sh 를 손으로 돌리면 옛 스크립트가 돌아 기록이 안 남는다 —
  # 옛 버전은 현재 워크플로의 Run workflow(ref=<SHA>)로 올린다.
  # 40자리 16진수가 아니면 없는 것으로 친다(비었거나 깨졌다). 맨 앞 stdout 에 찍어 둔다 — 안 잘린다.
  last_good=$(cat "$LAST_GOOD_FILE" 2>/dev/null) || last_good=""
  [[ "$last_good" =~ ^[0-9a-f]{40}$ ]] || last_good=""
  echo "직전 성공 ${last_good:-없음}"

  # docker 그룹에 들어 있지 않을 수 있어 sudo 로 통일한다.
  # Ubuntu AMI 의 ubuntu 계정은 비밀번호 없이 sudo 가 된다.
  sudo -n true || die "ubuntu 가 sudo 를 못 쓴다. 서버 설정을 봐야 한다"

  cd "$DEPLOY_PATH"

  # 저장소가 공개라 HTTPS 는 인증이 필요 없다. SSH 원격이면 서버에 GitHub 키를
  # 따로 관리해야 하고, 없으면 fetch 가 Permission denied 로 죽는다.
  # 그 상태에서 reset --hard 를 하면 옛 커밋으로 되감긴다(실제로 당했다).
  git remote set-url origin "$REPO_URL"

  # fetch 는 가끔 백그라운드로 `git gc --auto` 를 띄운다. 그 프로세스는 표준 입출력만 닫고 fd 9(서버 잠금)는 그대로 쥐어서,
  # swap_failed 가 `exec 9>&-` 로 잠금을 풀어도 gc 가 끝날 때까지 잠금이 남는다(자식 L 이나 다음 배포가 그만큼 기다린다).
  # git 에게만 fd 9 를 닫아 넘긴다. 이 파일이 잠금을 쥔 채 부르는 git 중 gc 를 띄우는 것은 fetch 뿐이다
  # (checkout · reset · rev-parse · log · show · grep · remote set-url 은 GIT_TRACE 로 확인했다).
  git fetch --prune origin 9>&-

  # 올릴 커밋을 **checkout 하기 전에** 전체 SHA 로 정한다. 브랜치면 origin 쪽 끝이고, 아니면 그 커밋이다.
  if git rev-parse --verify --quiet "origin/$DEPLOY_REF" >/dev/null; then
    F_SHA=$(git rev-parse "origin/$DEPLOY_REF^{commit}")
  else
    F_SHA=$(git rev-parse --verify --quiet "${DEPLOY_REF}^{commit}") \
      || die "그런 브랜치도 커밋도 없다: $DEPLOY_REF"
  fi

  # **deploy_one 을 `||` · `if` 안에서 부르지 않는다** (swap_failed 머리 주석).
  deploy_one "$F_SHA" "$DEPLOY_REF"

  # 여기까지 왔으면 서버 안 확인을 통과했다.
  record_good "$F_SHA"
  # 쓰지 않는 이미지 정리. 실패해도 배포 결과는 안 바꾼다 — 이미 새 커밋으로 잘 돌고 있다.
  sudo docker image prune -f || echo "docker image prune 이 실패했다. 배포 결과는 그대로다"

  echo "배포 끝"
}

# source 됐을 때만 main 을 건너뛴다 — 테스트가 함수만 부른다(backend/tests/test_deploy_script.py).
# 환경변수로 가르지 않는다. 그 변수가 서버에 남으면 배포를 건너뛰고도 종료 코드 0 이 난다.
# return 은 source 된 파일 안에서만 성공한다 — SSM 이 보내는 파일 · `bash 파일` 은 늘 main 을 돈다.
# `exit` 가 main 바로 뒤에 있어야 한다: 배포 도중 checkout 이 이 파일(저장소 안에서 직접 돌렸을 때)을 바꿔도
# bash 가 바뀐 파일의 뒷부분을 더 읽지 않는다.
if ! (return 0 2>/dev/null); then main "$@"; exit; fi
