#!/usr/bin/env bash
# DB 백업. cron 이 매일 새벽에 돌린다.
#
#   sudo crontab -e
#   15 18 * * * /home/ubuntu/ktc4-kangwon-2/scripts/backup.sh >> /var/log/ssuksak-backup.log 2>&1
#
# **시각은 UTC 로 적는다.** 서버 cron 이 UTC 로 돈다. `15 3 * * *` 으로 적으면 한국 시각
# **낮 12시 15분** — 교사가 한창 쓰는 때에 DB 덤프가 돈다. 18:15 UTC 가 다음날 새벽 3시 15분이다.
#   date            서버 시각이 UTC 인지 확인
#   sudo crontab -l 지금 걸린 줄 확인
#
# **왜 필요한가** — Docker 로 띄운 Postgres 는 자동 백업이 없다. 볼륨이 날아가면
# 교사가 쓴 일지도, 원장이 올린 양식 원본도 같이 사라진다. 파일럿 중에 터지면 복구가 없다.
#
# **복구를 한 번 해보고 끝낸다.** 안 되는 백업은 없는 것보다 나쁘다 — 있다고 믿는다.
#   scripts/restore-check.sh <파일>      한 달에 한 번. 쓰던 DB 를 건드리지 않는다
#
# **쓰던 DB 에 그대로 붓지 않는다.** CREATE TABLE 이 「already exists」로 줄줄이 실패하는데
# psql 은 그걸 넘기고 0 으로 끝난다 — 복구된 줄 알게 된다. 실제로 2026-10-14 에 해 봤고
# 오류 105줄이 나면서 **아무것도 복구되지 않았다.** 진짜 복구 절차는 docs/deploy.md 에 있다.
set -euo pipefail

DEPLOY_PATH=${DEPLOY_PATH:-/home/ubuntu/ktc4-kangwon-2}
BACKUP_DIR=${BACKUP_DIR:-/home/ubuntu/backup}
KEEP_DAYS=${KEEP_DAYS:-14}
# S3 로도 보내려면 .env 에 BACKUP_S3_URI=s3://<버킷>/<경로> 를 넣는다.
# **같은 디스크에만 두면 디스크가 죽을 때 백업도 같이 죽는다.**
BACKUP_S3_URI=${BACKUP_S3_URI:-}

cd "$DEPLOY_PATH"
mkdir -p "$BACKUP_DIR"

# cron 은 `.env` 를 읽지 않는다. 안 읽어오면 BACKUP_S3_URI 가 늘 비어서 **백업이 EC2 디스크에만
# 남는다** — 디스크가 죽으면 백업도 같이 죽는데, 설정은 해 뒀다고 믿게 된다.
# 파일을 통째로 source 하지 않는다. `.env` 에는 DB 비밀번호가 있고, 여기서 필요한 건 이 한 줄뿐이다.
if [ -z "$BACKUP_S3_URI" ] && [ -f "$DEPLOY_PATH/.env" ]; then
  BACKUP_S3_URI=$(grep -E '^BACKUP_S3_URI=' "$DEPLOY_PATH/.env" | tail -1 | cut -d= -f2- \
    | sed 's/^["'"'"']//;s/["'"'"']$//' || true)
fi

stamp=$(date +%Y%m%d_%H%M%S)
target="$BACKUP_DIR/ssuksak_$stamp.sql.gz"

# -T 로 TTY 를 끈다. cron 에는 TTY 가 없어 안 끄면 "the input device is not a TTY" 로 죽는다.
# cron 은 root 로 돌지만 손으로 돌릴 때는 ubuntu 다. docker 그룹에 없을 수 있어 맞춰 쓴다.
# `version` 은 데몬에 안 닿아서 권한이 없어도 성공한다. `ps` 로 본다.
if docker compose ps >/dev/null 2>&1; then dc() { docker compose "$@"; }
elif sudo -n docker compose ps >/dev/null 2>&1; then dc() { sudo docker compose "$@"; }
else echo "docker 데몬에 닿지 못한다" >&2; exit 1; fi

dc exec -T db pg_dump -U ssuksak -d ssuksak | gzip > "$target"

# **크기로는 못 가른다.** gzip 은 입력이 하나도 없어도 20바이트짜리 올바른 파일을 만든다.
# `-s`(0바이트 아님)는 그걸 통과시키고, 백업이 있는 것처럼 보인다 — 복구하려는 순간에야 안다.
# 그래서 풀어서 pg_dump 머리글이 실제로 있는지 본다.
#
# `set -o pipefail` 이 있어도 부족하다. `docker compose exec` 가 안쪽 종료 코드를 늘
# 그대로 돌려준다는 보장이 없다. 결과물을 직접 확인하는 쪽이 확실하다.
header=$(gzip -dc "$target" 2>/dev/null | head -c 400 || true)
case "$header" in
  *"PostgreSQL database dump"*) ;;
  *)
    rm -f "$target"
    echo "$(date -Is) backup failed: 덤프가 비었거나 깨졌다" >&2
    exit 1
    ;;
esac

echo "$(date -Is) backup ok $target ($(du -h "$target" | cut -f1))"

if [ -n "$BACKUP_S3_URI" ]; then
  aws s3 cp "$target" "$BACKUP_S3_URI/" --only-show-errors
  echo "$(date -Is) s3 ok $BACKUP_S3_URI/$(basename "$target")"
else
  # 설정만 해 두고 안 넣은 채 지나가는 일이 실제로 있었다. 매일 로그에 적어 둔다.
  echo "$(date -Is) s3 skip: BACKUP_S3_URI 가 없다 — 백업이 이 디스크에만 있다" >&2
fi

# 오래된 것만 지운다. 지우기 전에 새 백업이 성공한 것을 위에서 확인했다.
find "$BACKUP_DIR" -name 'ssuksak_*.sql.gz' -mtime "+$KEEP_DAYS" -delete
