#!/usr/bin/env bash
# 밖에서 공개 주소를 보고 서비스가 내려갔는지 판정해 알린다 — .github/workflows/uptime.yml 이 10분마다 돌린다.
#
# `$BASE/` 와 `$BASE/health/ready` 가 둘 다 200 이어야 정상이다. 하나라도 아니면 UPTIME_RETRY_WAIT 초(기본 30) 뒤
# 한 번 더 보고, 그래도 아니면 「내려감」이다 — 한 번 튀는 실패로는 알리지 않는다.
#
#   내려감 + Deploy run 이 끝나지 않은 것이 있다   새로 알리지 않는다 — 배포 중이다(시간 창이 아니라 run 상태를 본다. 47분짜리 배포도 덮는다).
#                                                직전 업타임 run 이 failure 였으면 그 상태를 이어 종료 1, 아니면 종료 0
#   내려감 + 직전 업타임 run 이 failure            이미 알렸다. 새 알림 없음 · 종료 1
#   내려감 + 그 밖                                🔴 알림 · 종료 1
#   정상   + 직전 업타임 run 이 failure            🟢 복구 알림 · 종료 0
#   정상   + 그 밖                                조용히 종료 0
#   TEST_ALERT=true                              🧪 시험 알림 + 지금 확인 결과를 보내고 종료 0 (위 판정과 무관).
#                                                다만 내려가 있고 직전이 failure 였으면 그 상태를 이어 종료 1
#
# 「직전 업타임 run」은 지금 run 을 뺀 가장 최근의 success · failure run 이다. 취소 · 시간 초과로 끝난 run 은 건너뛴다.
#
# gh 조회가 실패하면: 배포 중인지 모르면 **알린다**(조용히 삼키면 진짜 장애를 놓친다) · 직전 결론을 모르면 「그 밖」으로 본다.
# WEBHOOK 이 비면 보낼 내용을 로그에 찍기만 한다 — 로컬에서 그대로 돌려 볼 수 있다. 전송이 실패해도 판정은 그대로다.
#
# 환경: BASE · REPO(owner/repo) 필수. WEBHOOK · RUN_URL · TEST_ALERT · UPTIME_RETRY_WAIT 은 선택. gh 는 GH_TOKEN 을 쓴다.
set -euo pipefail

base=${BASE:?확인할 주소(BASE)}
repo=${REPO:?owner/repo(REPO)}
webhook=${WEBHOOK:-}
run_url=${RUN_URL:-(로컬 실행)}
nl=$'\n'

# 두 주소를 한 번씩 본다. 200 이 아닌 것만 「주소 → 코드」 줄로 stdout 에 찍는다(진행은 stderr).
# curl 이 닿지도 못하면 -w 가 000 을 찍고 실패로 끝난다 — 그 000 을 쓴다.
probe() {
  local path code
  for path in / /health/ready; do
    code=$(curl -sS -m 10 -o /dev/null -w '%{http_code}' "$base$path") || code=000
    echo "$base$path → $code" >&2
    [ "$code" = 200 ] || echo "$base$path → $code"
  done
}

send() {
  if [ -z "$webhook" ]; then
    echo "WEBHOOK 이 비어 있어 보내지 않는다. 보낼 내용:${nl}$1"
    return 0
  fi
  curl -fsS -X POST "$webhook" \
    -H 'Content-Type: application/json' \
    -d "$(jq -n --arg c "$1" '{content: $c}')" \
    || echo "알림 전송 실패"
}

# 지금 run 이 아닌 가장 최근 업타임 run 중 success · failure 로 끝난 것의 결론. 첫 run 이면 빈 값이다.
# 취소 · 시간 초과 같은 결론은 건너뛴다 — 알렸는지 아닌지를 말해 주지 않는다. 호출하는 쪽이 실패를 빈 값으로 본다.
prev_conclusion() {
  gh api "repos/$repo/actions/workflows/uptime.yml/runs?status=completed&per_page=5" \
    --jq "[.workflow_runs[] | select(.id != ${GITHUB_RUN_ID:-0} and (.conclusion == \"success\" or .conclusion == \"failure\"))][0].conclusion // empty"
}

bad=$(probe)
if [ -n "$bad" ]; then
  echo "실패가 있다. ${UPTIME_RETRY_WAIT:-30}초 뒤 한 번 더 본다"
  sleep "${UPTIME_RETRY_WAIT:-30}"
  bad=$(probe)
fi

# 「이미 알렸다」는 직전 run 의 결론으로 이어진다. 알리지 않는 갈래도 그 상태를 이어 가야 한다 —
# 내려간 채 초록으로 끝나 버리면 다음 정상 run 이 직전을 success 로 읽어 복구 알림이 빠진다.
prev=$(prev_conclusion) || prev=""

if [ "${TEST_ALERT:-}" = true ]; then
  send "🧪 시험 알림 — 실제 장애 아님${nl}지금 확인 결과: ${bad:-두 주소 모두 200}${nl}${run_url}"
  # 내려가 있고 이미 알린 상태였으면 시험이 그 상태를 지우지 않게 이 run 도 실패로 끝낸다
  if [ -n "$bad" ] && [ "$prev" = failure ]; then exit 1; fi
  exit 0
fi

if [ -z "$bad" ]; then
  if [ "$prev" = failure ]; then
    send "🟢 서비스가 돌아왔다 — 두 주소 모두 200${nl}${run_url}"
  else
    echo "정상"
  fi
  exit 0
fi

echo "내려감:${nl}${bad}"

unknown=""
if deploying=$(gh api "repos/$repo/actions/workflows/deploy.yml/runs?per_page=20" \
  --jq '[.workflow_runs[] | select(.status != "completed")] | length'); then
  if [ "$deploying" -gt 0 ]; then
    echo "Deploy run 이 ${deploying}개 도는 중이다. 배포 중이라 새로 알리지 않는다"
    if [ "$prev" = failure ]; then exit 1; fi
    exit 0
  fi
else
  unknown="${nl}(배포 중인지 못 읽었다)"
fi

if [ "$prev" = failure ]; then
  echo "직전 업타임 run 이 이미 실패였다. 알렸으니 다시 알리지 않는다"
  exit 1
fi

send "🔴 서비스가 응답하지 않는다 — 두 번 연속 확인했다${nl}${bad}${unknown}${nl}${run_url}"
exit 1
