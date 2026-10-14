#!/usr/bin/env bash
# 백업이 **진짜로 복구되는지** 확인한다. 쓰던 DB 는 건드리지 않는다.
#
#   scripts/restore-check.sh /home/ubuntu/backup/ssuksak_20261014_031500.sql.gz
#
# **왜 필요한가** — 백업 파일이 있다는 것과 그 파일로 되돌릴 수 있다는 것은 다르다.
# 안 되는 백업은 없는 것보다 나쁘다. 있다고 믿고 아무것도 안 하게 된다.
#
# **한 달에 한 번은 돌린다.** 터진 뒤에 처음 해보면 그때는 고칠 시간이 없다.
set -euo pipefail

FILE=${1:-}
DEPLOY_PATH=${DEPLOY_PATH:-/home/ubuntu/ktc4-kangwon-2}
CHECK_DB=${CHECK_DB:-ssuksak_restore_check}

if [ -z "$FILE" ]; then
  echo "쓰는 법: $0 <백업파일.sql.gz>" >&2
  exit 2
fi
if [ ! -s "$FILE" ]; then
  echo "백업 파일이 없거나 비었다: $FILE" >&2
  exit 1
fi

cd "$DEPLOY_PATH"
psql() { docker compose exec -T db psql -U ssuksak "$@"; }

# **빈 DB 에 붓는다.** 쓰던 DB 에 그대로 부으면 CREATE TABLE 이 「already exists」로 줄줄이
# 실패하고, psql 은 그걸 넘기고 계속 간 뒤 0 으로 끝난다 — 복구된 줄 알게 된다.
psql -d postgres -q -c "DROP DATABASE IF EXISTS $CHECK_DB;"
psql -d postgres -q -c "CREATE DATABASE $CHECK_DB OWNER ssuksak;"
trap 'docker compose exec -T db psql -U ssuksak -d postgres -q -c "DROP DATABASE IF EXISTS $CHECK_DB;" >/dev/null 2>&1 || true' EXIT

# **`ON_ERROR_STOP=1` 을 반드시 붙인다.** 없으면 위와 같은 이유로 실패를 못 본다.
if ! gunzip -c "$FILE" | docker compose exec -T db psql -U ssuksak -d "$CHECK_DB" \
    -v ON_ERROR_STOP=1 -q >/dev/null; then
  echo "restore-check FAILED: 복구 중 오류가 났다 — $FILE" >&2
  exit 1
fi

# **표가 다 왔는지 먼저 본다.** 잘린 백업도 앞부분은 멀쩡해서 복구가 0 으로 끝날 수 있다.
# 그러면 아래 집계가 「relation does not exist」로 죽는데, 그건 읽어도 무슨 일인지 모른다.
missing=$(psql -d "$CHECK_DB" -tAc "
  SELECT string_agg(t, ' ') FROM unnest(ARRAY[
    'alembic_version','centers','users','classes','children','plans','documents'
  ]) AS t
  WHERE to_regclass('public.'||t) IS NULL;" | tr -d '\n' | sed 's/^ *//;s/ *$//')
if [ -n "$missing" ]; then
  echo "restore-check FAILED: 복구본에 표가 없다 ($missing) — 백업이 잘렸을 수 있다" >&2
  exit 1
fi

head=$(psql -d "$CHECK_DB" -tAc "SELECT version_num FROM alembic_version;" | tr -d '[:space:]')
live_head=$(psql -d ssuksak -tAc "SELECT version_num FROM alembic_version;" | tr -d '[:space:]')
counts=$(psql -d "$CHECK_DB" -tAc "
  SELECT 'centers='||(SELECT count(*) FROM centers)
      || ' users='||(SELECT count(*) FROM users)
      || ' plans='||(SELECT count(*) FROM plans)
      || ' documents='||(SELECT count(*) FROM documents);")

# **새 행이 들어가는지까지 본다.** 시퀀스가 안 따라오면 복구 뒤 첫 저장에서 키 충돌이 난다 —
# 행 수만 세면 이걸 못 잡는다.
if ! psql -d "$CHECK_DB" -q -c "
  INSERT INTO centers (name, director_name, region_sido, region_sigungu)
  VALUES ('복구확인', '확인', '충청북도', '충주시');" >/dev/null 2>&1; then
  echo "restore-check FAILED: 복구본에 새 행을 넣지 못했다 (시퀀스 확인)" >&2
  exit 1
fi

echo "restore-check ok  $FILE"
echo "  alembic  $head (운영 $live_head)"
echo "  행       $counts"
[ "$head" = "$live_head" ] || echo "  ⚠️ alembic head 가 운영과 다르다 — 백업 뒤에 마이그레이션이 돌았다"
