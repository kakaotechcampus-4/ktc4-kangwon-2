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

# 브랜치면 origin 쪽을 따라가고, SHA 면 그 커밋으로 바로 간다.
# `git reset --hard origin/<SHA>` 는 그런 ref 가 없어서 죽는다 — 갈라야 한다.
if git rev-parse --verify --quiet "origin/$DEPLOY_REF" >/dev/null; then
  git checkout -f "$DEPLOY_REF"
  git reset --hard "origin/$DEPLOY_REF"
else
  # 커밋이다. Actions 배포는 늘 이리로 온다. 브랜치에서 떨어져 나온 상태(detached HEAD)가
  # 되는데 배포에는 문제가 없다. 서버에서 git pull 을 하지 않는다 — 붙은 브랜치가 없어 실패한다.
  git rev-parse --verify --quiet "${DEPLOY_REF}^{commit}" >/dev/null \
    || { echo "그런 브랜치도 커밋도 없다: $DEPLOY_REF"; exit 1; }
  git checkout -f --detach "$DEPLOY_REF"
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
sudo docker compose run --rm backend alembic upgrade head

sudo docker compose up -d

# nginx 는 nginx/ 폴더를 통째로 본다(docker-compose.yml). 컨테이너를 다시 만들지 않으면
# 새 설정을 안 읽으므로 reload 로 읽힌다. 접속은 안 끊기고, 진행 중인 요청은 끝까지 간다.
# reload 가 안 되면 다시 시작한다 — up -d 가 방금 다시 만들어 아직 준비 전이거나, 재시작을 반복하는
# 중일 때다(up -d 는 재시작 반복 중인 컨테이너를 건드리지 않는다). 그때 nginx 는 어차피 응답을 못 하고 있다.
sudo docker compose exec -T nginx nginx -s reload || sudo docker compose restart nginx

sudo docker image prune -f

echo "배포 끝"
