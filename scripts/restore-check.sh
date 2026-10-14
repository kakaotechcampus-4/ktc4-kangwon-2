#!/usr/bin/env bash
# 백업이 **진짜로 복구되는지** 확인한다.
#
#   scripts/restore-check.sh <백업파일.sql.gz>   버리는 DB 에 복구해 보고 지운다 (한 달에 한 번)
#   scripts/restore-check.sh --db <DB이름>       이미 복구해 둔 DB 를 검사만 한다 (안 지운다)
#
# **왜 필요한가** — 백업 파일이 있다는 것과 그 파일로 되돌릴 수 있다는 것은 다르다.
# 안 되는 백업은 없는 것보다 나쁘다. 있다고 믿고 아무것도 안 하게 된다.
#
# **진짜 복구 때는 `--db` 로 「바꿔 끼울 그 DB」를 검사한다.** 파일만 검사하고 다른 DB 를
# 끼우면, 파일은 멀쩡한데 끼운 쪽이 덜 들어간 경우를 못 본다.
set -euo pipefail

DEPLOY_PATH=${DEPLOY_PATH:-/home/ubuntu/ktc4-kangwon-2}
LIVE_DB=${LIVE_DB:-ssuksak}
CHECK_DB=${CHECK_DB:-ssuksak_restore_check}

cd "$DEPLOY_PATH"
psql() { docker compose exec -T db psql -U ssuksak "$@"; }

# 복구본이 쓸 만한지 본다. **여기서 죽어도 쓰던 DB 는 건드리지 않는다.**
verify_db() {
  local db=$1 label=$2

  # 표가 다 왔는지 먼저 본다. 잘린 백업도 앞부분은 멀쩡해서 복구가 0 으로 끝날 수 있다.
  #
  # **표 몇 개만 꼽아 보지 않는다.** 핵심 표는 다 왔는데 forms · observations ·
  # routine_records 가 빠진 DB 를 「끼워도 된다」고 하면, 교사가 적은 기록이 조용히 사라진다.
  # 운영 DB 를 읽을 수 있으면 **그쪽 표 목록 전부**와 맞춰 본다.
  local tables_here tables_live missing
  tables_here=$(psql -d "$db" -tAc \
    "SELECT string_agg(tablename, ' ' ORDER BY tablename) FROM pg_tables WHERE schemaname='public';" \
    | tr -d '\n' | sed 's/^ *//;s/ *$//')
  tables_live=$(psql -d "$LIVE_DB" -tAc \
    "SELECT string_agg(tablename, ' ' ORDER BY tablename) FROM pg_tables WHERE schemaname='public';" \
    2>/dev/null | tr -d '\n' | sed 's/^ *//;s/ *$//' || true)

  if [ -n "$tables_live" ]; then
    missing=$(comm -23 <(tr ' ' '\n' <<<"$tables_live" | sort -u) \
                       <(tr ' ' '\n' <<<"$tables_here" | sort -u) | tr '\n' ' ' | sed 's/ *$//')
    if [ -n "$missing" ]; then
      echo "restore-check FAILED: $db 에 표가 없다 ($missing) — 백업이 잘렸을 수 있다" >&2
      return 1
    fi
  else
    # 운영을 못 읽는다(= 날아갔다). 전체 대조는 못 하니 핵심만 보고 그 사실을 말한다.
    missing=$(psql -d "$db" -tAc "
      SELECT string_agg(t, ' ') FROM unnest(ARRAY[
        'alembic_version','centers','users','classes','children','plans','documents',
        'observations','routine_records','forms'
      ]) AS t
      WHERE to_regclass('public.'||t) IS NULL;" | tr -d '\n' | sed 's/^ *//;s/ *$//')
    if [ -n "$missing" ]; then
      echo "restore-check FAILED: $db 에 표가 없다 ($missing) — 백업이 잘렸을 수 있다" >&2
      return 1
    fi
  fi

  local head live_head counts
  head=$(psql -d "$db" -tAc "SELECT version_num FROM alembic_version;" | tr -d '[:space:]')
  # **운영 DB 를 못 읽어도 계속 간다.** 이 스크립트가 가장 필요한 때가 운영이 날아간 때인데,
  # 거기서 운영 쪽 조회가 실패해 죽으면 백업을 확인할 길이 없어진다.
  live_head=$(psql -d "$LIVE_DB" -tAc "SELECT version_num FROM alembic_version;" 2>/dev/null \
    | tr -d '[:space:]' || true)
  counts=$(psql -d "$db" -tAc "
    SELECT 'centers='||(SELECT count(*) FROM centers)
        || ' users='||(SELECT count(*) FROM users)
        || ' plans='||(SELECT count(*) FROM plans)
        || ' documents='||(SELECT count(*) FROM documents);")

  # **새 행이 들어가는지까지 본다.** 시퀀스가 안 따라오면 복구 뒤 첫 저장에서 키 충돌이 난다 —
  # 행 수만 세면 이걸 못 잡는다. 넣어 보고 바로 지운다.
  if ! psql -d "$db" -q -v ON_ERROR_STOP=1 -c "
    BEGIN;
    INSERT INTO centers (name, director_name, region_sido, region_sigungu)
    VALUES ('복구확인', '확인', '충청북도', '충주시');
    ROLLBACK;" >/dev/null 2>&1; then
    echo "restore-check FAILED: $db 에 새 행을 넣지 못했다 (시퀀스 확인)" >&2
    return 1
  fi

  # **alembic head 가 다르면 통과시키지 않는다.** 백업이 마이그레이션보다 오래된 것이라,
  # 그대로 끼우고 지금 백엔드를 띄우면 새 컬럼을 쓰는 요청이 터진다. 끼우기 전에 올려야 한다.
  if [ -n "$live_head" ] && [ "$head" != "$live_head" ]; then
    echo "restore-check FAILED: alembic head 가 운영과 다르다 ($head ≠ $live_head)" >&2
    echo "  백업 뒤에 마이그레이션이 돌았다. 이대로 끼우면 새 컬럼을 쓰는 요청이 터진다." >&2
    echo "  끼우기 전에 복구본에 마이그레이션을 올린다:" >&2
    echo "    docker compose run --rm -v \"\$(pwd)/backend:/app\" \\" >&2
    echo "      -e DATABASE_URL=...$db backend alembic upgrade head" >&2
    return 1
  fi

  echo "restore-check ok  $label"
  echo "  행       $counts"
  if [ -z "$live_head" ]; then
    echo "  alembic  $head (운영은 못 읽었다 — 운영 DB 가 없거나 표가 없다)"
    echo "  ⚠️ 운영과 표 목록을 맞춰보지 못했다. 핵심 표 10개만 확인했다"
  else
    echo "  alembic  $head (운영과 같다)"
    echo "  표       운영에 있는 표가 전부 있다"
  fi
}

if [ "${1:-}" = "--db" ]; then
  TARGET=${2:-}
  [ -n "$TARGET" ] || { echo "쓰는 법: $0 --db <DB이름>" >&2; exit 2; }
  # 검사만 한다. 만들지도 지우지도 않는다 — 운영 DB 를 넣어도 안전하다.
  verify_db "$TARGET" "$TARGET"
  exit
fi

FILE=${1:-}
if [ -z "$FILE" ]; then
  echo "쓰는 법: $0 <백업파일.sql.gz>  |  $0 --db <DB이름>" >&2
  exit 2
fi
if [ ! -s "$FILE" ]; then
  echo "백업 파일이 없거나 비었다: $FILE" >&2
  exit 1
fi

# **지울 DB 이름을 먼저 막는다.** CHECK_DB 는 환경변수로 바꿀 수 있어서, 실수로 ssuksak 을
# 넣으면 아래 DROP 이 운영을 지운다. 「버리려고 만든 이름」만 받는다.
case "$CHECK_DB" in
  *_restore_check) ;;
  *)
    echo "CHECK_DB 는 '_restore_check' 로 끝나야 한다. 받은 값: $CHECK_DB" >&2
    echo "이 스크립트는 그 DB 를 지우고 다시 만든다 — 쓰던 이름을 넣으면 안 된다." >&2
    exit 2
    ;;
esac
if [ "$CHECK_DB" = "$LIVE_DB" ]; then
  echo "CHECK_DB 와 LIVE_DB 가 같다: $CHECK_DB" >&2
  exit 2
fi

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

verify_db "$CHECK_DB" "$FILE"
