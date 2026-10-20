#!/usr/bin/env bash
# 서버에서 도는 배포 스크립트. GitHub Actions 가 SSM send-command 로 이 파일의
# 내용을 통째로 보낸다(.github/workflows/deploy.yml). 서버에 미리 있을 필요가 없다.
#
# 손으로 배포할 때도 같은 것을 쓴다 — Session Manager 로 들어가서
#   bash /home/ubuntu/ktc4-kangwon-2/scripts/deploy.sh
# 자동과 수동이 다른 명령을 돌면 「손으로는 되는데 CI 는 안 된다」가 생긴다.
set -euo pipefail

DEPLOY_PATH=/home/ubuntu/ktc4-kangwon-2
REPO_URL=https://github.com/kakaotechcampus-4/ktc4-kangwon-2.git

# 어느 브랜치를 올릴지. 기본은 main 이다.
#
# **develop 을 올리는 일이 실제로 있다.** 멘토 리뷰 전에 서버에 미리 올려 두기 때문이다.
# 전에는 이 값이 main 으로 박혀 있어서, 손으로 develop 을 올려 둔 서버에 자동 배포를
# 한 번 돌리면 조용히 main 으로 되돌아갔다. 무엇이 돌고 있는지 아무도 모르게 된다.
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
git checkout "$DEPLOY_REF"
git reset --hard "origin/$DEPLOY_REF"

# fetch 가 실패하면 origin/<브랜치> 가 옛 커밋을 가리킨 채 남는다.
# 그대로 reset 하면 조용히 과거로 돌아간다. 파일이 있는지 본다.
test -f docker-compose.yml || { echo "docker-compose.yml 이 없다. fetch 가 안 됐다"; exit 1; }

# .env 는 커밋하지 않으므로 서버에만 있다.
test -f .env || { echo ".env 가 없다. 서버에서 한 번 만들어야 한다"; exit 1; }

echo "배포 $DEPLOY_REF $(git rev-parse --short HEAD) — $(git log -1 --format=%s)"

sudo docker compose build backend frontend

# 마이그레이션을 앱보다 먼저 돌린다. 반대로 하면 새 코드가 없는 컬럼을 읽는다.
sudo docker compose run --rm backend alembic upgrade head

sudo docker compose up -d
sudo docker image prune -f

echo "배포 끝"
