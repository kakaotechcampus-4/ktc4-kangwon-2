#!/usr/bin/env bash
# 서버에서 도는 배포 스크립트. GitHub Actions 가 SSM send-command 로 이 파일의
# 내용을 통째로 보낸다(.github/workflows/deploy.yml). 서버에 미리 있을 필요가 없다.
#
# **이 쉬뱅이 보내는 글의 첫 줄이어야 한다.** SSM 은 `commands` 배열을 줄로 이어 붙여
# 한 파일로 만들고, 첫 줄이 `#!` 가 아니면 bash 가 아니라 `sh`(우분투는 dash)로 돈다.
# dash 에는 `pipefail` 이 없어서 아래 `set -euo pipefail` 에서 바로 죽는다
# (2026-10-20 에 실제로 당했다 — `_script.sh: 9: set: Illegal option -o pipefail`).
# 워크플로가 앞에 다른 줄을 끼울 일이 생기면 쉬뱅을 맨 앞에 따로 넣어 준다.
#
# 손으로 배포할 때도 같은 것을 쓴다 — Session Manager 로 들어가서
#   bash /home/ubuntu/ktc4-kangwon-2/scripts/deploy.sh
# 자동과 수동이 다른 명령을 돌면 「손으로는 되는데 CI 는 안 된다」가 생긴다.
set -euo pipefail

DEPLOY_PATH=/home/ubuntu/ktc4-kangwon-2
REPO_URL=https://github.com/kakaotechcampus-4/ktc4-kangwon-2.git

# <트리> 안에서 리비전 <rev> 를 **선언한** 파일 경로를 찍는다. 없으면 아무것도 안 찍는다.
# 파일 이름이 아니라 선언(`revision = '…'` · `revision: str = "…"` 둘 다 있다)을 본다 —
# `down_revision` 에 적힌 것은 선언이 아니다. <rev> 는 부르는 쪽이 12자리 16진수로 걸러 온다.
revision_file() {
  local tree=$1 rev=$2 out rc=0 f
  out=$(git grep -l -E "^revision(: str)? = ['\"]${rev}['\"]" "$tree" -- backend/alembic/versions/) || rc=$?
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

main() {
  # 무엇을 올릴지. 브랜치 이름이거나 커밋 SHA 다. 기본은 main 이다.
  #
  # **develop 을 올리는 일이 실제로 있다.** 멘토 리뷰 전에 서버에 미리 올려 두기 때문이다.
  # 전에는 이 값이 main 으로 박혀 있어서, 손으로 develop 을 올려 둔 서버에 자동 배포를
  # 한 번 돌리면 조용히 main 으로 되돌아갔다. 무엇이 돌고 있는지 아무도 모르게 된다.
  #
  # **Actions 는 늘 커밋 SHA 를 넘긴다**(deploy.yml 「올릴 커밋 고정」). 브랜치 이름을 넘기면
  # 이 스크립트가 도는 순간의 끝 커밋이 올라가서, 그 사이 들어온 머지가 다른 run 의 이름으로 나갔다.
  # 롤백도 같은 길이다 — 직전 커밋 SHA 를 넣어 다시 돌린다. 롤백 전용 길을 따로 만들지 않는다.
  # 평소에 안 쓰는 길은 정작 급할 때 안 돈다.
  #   직전에 무엇이 돌았는지 보기:  Actions 의 배포 기록, 또는 서버에서
  #   cd /home/ubuntu/ktc4-kangwon-2 && git log --oneline -5
  #
  # **마이그레이션을 건너는 롤백은 한 칸까지만 된다**(ADR-073). 마이그레이션이 든 PR 하나의
  # 머지 직전 커밋으로는 되감기고(upgrade 를 건너뛴다), 그보다 더 옛 커밋은 서버를 건드리기 전에 멈춘다.
  DEPLOY_REF="${DEPLOY_REF:-main}"
  case "$DEPLOY_REF" in
    *[!A-Za-z0-9._/-]*) echo "브랜치 이름에 쓸 수 없는 글자가 있다: $DEPLOY_REF"; exit 1 ;;
  esac

  # SSM 은 root 로 돈다. git 을 root 로 돌리면 .git 안에 root 소유 파일이 생겨
  # 다음에 ubuntu 가 서버에서 손을 못 댄다. ubuntu 로 내려가서 돈다.
  # 이미 ubuntu 면(손으로 실행) 그냥 이어서 돈다.
  if [ "$(id -un)" != "ubuntu" ]; then
    # SSM 이 만든 원본 스크립트는 ubuntu 가 읽을 수 있다는 보장이 없다. 복사해서 넘긴다.
    INNER=$(mktemp /tmp/ssuksak-deploy.XXXXXX.sh)
    cat "$0" > "$INNER"
    chmod 0644 "$INNER"
    set +e
    # runuser 가 환경을 물려준다는 보장이 없다. 쓰는 값은 손으로 넘긴다.
    runuser -u ubuntu -- env DEPLOY_REF="$DEPLOY_REF" bash "$INNER"
    status=$?
    set -e
    rm -f "$INNER"
    exit "$status"
  fi

  # docker 그룹에 들어 있지 않을 수 있어 sudo 로 통일한다.
  # Ubuntu AMI 의 ubuntu 계정은 비밀번호 없이 sudo 가 된다.
  sudo -n true || { echo "ubuntu 가 sudo 를 못 쓴다. 서버 설정을 봐야 한다"; exit 1; }

  cd "$DEPLOY_PATH"

  # 저장소가 공개라 HTTPS 는 인증이 필요 없다. SSH 원격이면 서버에 GitHub 키를
  # 따로 관리해야 하고, 없으면 fetch 가 Permission denied 로 죽는다.
  # 그 상태에서 reset --hard 를 하면 옛 커밋으로 되감긴다(실제로 당했다).
  git remote set-url origin "$REPO_URL"

  git fetch --prune origin

  # 올릴 커밋을 **checkout 하기 전에** 전체 SHA 로 정한다. 브랜치면 origin 쪽 끝이고, 아니면 그 커밋이다.
  if git rev-parse --verify --quiet "origin/$DEPLOY_REF" >/dev/null; then
    target=$(git rev-parse "origin/$DEPLOY_REF^{commit}")
  else
    target=$(git rev-parse --verify --quiet "${DEPLOY_REF}^{commit}") \
      || { echo "그런 브랜치도 커밋도 없다: $DEPLOY_REF"; exit 1; }
  fi

  # 마이그레이션을 건너뛰어도 되는지도 checkout 전에 정한다. 여기서 멈추면 서버 폴더와 이미지는
  # 그대로다 — 멈춘 뒤에 반쯤 바뀐 서버(옛 코드 폴더 + 새 DB)가 남지 않는다.
  revs=$(db_revisions) || { echo "DB 리비전을 읽지 못했다. 서버는 바꾸지 않았다"; exit 1; }
  step=$(migration_step "$target" "$revs")
  case "$step" in
    reject*) echo "배포를 멈춘다. 서버는 바꾸지 않았다 — ${step#reject }"; exit 1 ;;
  esac

  # 브랜치면 origin 쪽을 따라가고, SHA 면 그 커밋으로 바로 간다.
  # `git reset --hard origin/<SHA>` 는 그런 ref 가 없어서 죽는다 — 갈라야 한다.
  if git rev-parse --verify --quiet "origin/$DEPLOY_REF" >/dev/null; then
    git checkout -f "$DEPLOY_REF"
    git reset --hard "origin/$DEPLOY_REF"
  else
    # 커밋이다. Actions 배포는 늘 이리로 온다. 브랜치에서 떨어져 나온 상태(detached HEAD)가
    # 되는데 배포에는 문제가 없다. 서버에서 git pull 을 하지 않는다 — 붙은 브랜치가 없어 실패한다.
    git checkout -f --detach "$target"
  fi

  # fetch 가 실패하면 origin/<브랜치> 가 옛 커밋을 가리킨 채 남는다.
  # 그대로 reset 하면 조용히 과거로 돌아간다. 파일이 있는지 본다.
  test -f docker-compose.yml || { echo "docker-compose.yml 이 없다. fetch 가 안 됐다"; exit 1; }

  # .env 는 커밋하지 않으므로 서버에만 있다.
  test -f .env || { echo ".env 가 없다. 서버에서 한 번 만들어야 한다"; exit 1; }

  echo "배포 $DEPLOY_REF $(git rev-parse --short HEAD) — $(git log -1 --format=%s)"

  # nginx 설정을 build · 마이그레이션 · 컨테이너 교체 전에 검사한다. 깨졌으면 여기서 멈춘다.
  # 파일은 위 checkout 으로 이미 바뀌었다 — 떠 있는 nginx 는 옛 설정으로 계속 돌지만 다시 시작되면 못 뜬다.
  # 새 컨테이너로 검사해서 방금 꺼낸 커밋의 compose 연결을 그대로 쓴다 — 롤백(옛 SHA)도 같은 길이다.
  # nginx -t 는 upstream 이름이 안 풀리면 실패한다. 앱이 죽어 있을 때(롤백이 그렇다)도 검사가 되게
  # compose 의 서비스 이름을 전부 자기 자신으로 둔다. 여기서 보는 건 문법 · 파일 · 인증서다.
  services=$(sudo docker compose config --services | tr '\n' ' ')
  sudo docker compose run --rm -T --no-deps nginx \
    sh -c "echo '127.0.0.1 $services' >> /etc/hosts && nginx -t"

  sudo docker compose build backend frontend

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

  sudo docker compose up -d

  # nginx 는 nginx/ 폴더를 통째로 본다(docker-compose.yml). 컨테이너를 다시 만들지 않으면
  # 새 설정을 안 읽으므로 reload 로 읽힌다. 접속은 안 끊기고, 진행 중인 요청은 끝까지 간다.
  # reload 가 안 되면 다시 시작한다 — up -d 가 방금 다시 만들어 아직 준비 전이거나, 재시작을 반복하는
  # 중일 때다(up -d 는 재시작 반복 중인 컨테이너를 건드리지 않는다). 그때 nginx 는 어차피 응답을 못 하고 있다.
  sudo docker compose exec -T nginx nginx -s reload || sudo docker compose restart nginx

  sudo docker image prune -f

  echo "배포 끝"
}

# source 됐을 때만 main 을 건너뛴다 — 테스트가 함수만 부른다(backend/tests/test_deploy_script.py).
# 환경변수로 가르지 않는다. 그 변수가 서버에 남으면 배포를 건너뛰고도 종료 코드 0 이 난다.
# return 은 source 된 파일 안에서만 성공한다 — SSM 이 보내는 파일 · `bash 파일` 은 늘 main 을 돈다.
if ! (return 0 2>/dev/null); then main "$@"; fi
