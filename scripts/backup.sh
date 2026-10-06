#!/usr/bin/env bash
# DB 백업. cron 이 매일 새벽에 돌린다.
#
#   sudo crontab -e
#   15 3 * * * /home/ubuntu/ktc4-kangwon-2/scripts/backup.sh >> /var/log/ssuksak-backup.log 2>&1
#
# **왜 필요한가** — Docker 로 띄운 Postgres 는 자동 백업이 없다. 볼륨이 날아가면
# 교사가 쓴 일지도, 원장이 올린 양식 원본도 같이 사라진다. 파일럿 중에 터지면 복구가 없다.
#
# **복구를 한 번 해보고 끝낸다.** 안 되는 백업은 없는 것보다 나쁘다 — 있다고 믿는다.
#   gunzip -c <파일> | docker compose exec -T db psql -U ssuksak -d ssuksak
set -euo pipefail

DEPLOY_PATH=${DEPLOY_PATH:-/home/ubuntu/ktc4-kangwon-2}
BACKUP_DIR=${BACKUP_DIR:-/home/ubuntu/backup}
KEEP_DAYS=${KEEP_DAYS:-14}
# S3 로도 보내려면 .env 에 BACKUP_S3_URI=s3://<버킷>/<경로> 를 넣는다.
# **같은 디스크에만 두면 디스크가 죽을 때 백업도 같이 죽는다.**
BACKUP_S3_URI=${BACKUP_S3_URI:-}

cd "$DEPLOY_PATH"
mkdir -p "$BACKUP_DIR"

stamp=$(date +%Y%m%d_%H%M%S)
target="$BACKUP_DIR/ssuksak_$stamp.sql.gz"

# -T 로 TTY 를 끈다. cron 에는 TTY 가 없어 안 끄면 "the input device is not a TTY" 로 죽는다.
docker compose exec -T db pg_dump -U ssuksak -d ssuksak | gzip > "$target"

# 빈 파일이 남으면 백업이 있다고 착각한다. pg_dump 가 실패해도 gzip 은 성공하므로 여기서 본다.
if [ ! -s "$target" ]; then
  rm -f "$target"
  echo "backup failed: pg_dump 결과가 비었다" >&2
  exit 1
fi

echo "$(date -Is) backup ok $target ($(du -h "$target" | cut -f1))"

if [ -n "$BACKUP_S3_URI" ]; then
  aws s3 cp "$target" "$BACKUP_S3_URI/" --only-show-errors
  echo "$(date -Is) s3 ok $BACKUP_S3_URI/$(basename "$target")"
fi

# 오래된 것만 지운다. 지우기 전에 새 백업이 성공한 것을 위에서 확인했다.
find "$BACKUP_DIR" -name 'ssuksak_*.sql.gz' -mtime "+$KEEP_DAYS" -delete
