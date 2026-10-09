#!/usr/bin/env bash
# LLM 토큰 사용량 합계. 서버 로그의 `llm_usage` 줄을 긁어 날짜별로 더한다.
#
# **왜 필요한가.** 엘리스 키가 팀 공용이라 대시보드가 팀 전체 합계만 준다.
# 생성 한 번이 얼마인지, 파일럿 30건이 얼마인지 알 길이 없다.
#
# 로그에 남는 것은 숫자 네 개뿐이다 — 프롬프트 내용은 찍지 않는다 (ADR-004).
#
#   sh scripts/llm-usage.sh           최근 7일
#   sh scripts/llm-usage.sh 24h       최근 24시간
set -euo pipefail

SINCE="${1:-168h}"

# ────────────────────────────────────────────────────────────────────
# 단가 — 엘리스 콘솔 gpt-6-luna Serverless 기준 (2026-10-10 확인, VAT 별도).
#   ₩152 / 1M input · ₩15 / 1M cached input · ₩761 / 1M output
# 모델을 바꾸면 여기도 바꾼다 — 안 바꾸면 옛 단가로 계산된 금액이 나온다.
#
# **캐시 할인은 안 센다.** 응답의 usage 가 캐시된 입력을 따로 알려주지 않아서,
# 전부 정가 입력으로 계산한다. 그래서 **여기 나오는 금액은 실제보다 조금 비싸다** —
# 적게 나오는 것보다 낫다.
#
# **장문 요금도 안 센다.** 입력이 272,000 토큰을 넘으면 그 요청 전체가 입력 2배·출력 1.5배다.
# 우리 프롬프트는 3천 토큰대라 걸릴 일이 없다. 넘기 시작하면 여기에 분기를 넣는다.
PROMPT_WON_PER_1K=0.152      # 입력 1,000 토큰당 원  (152 / 1000)
COMPLETION_WON_PER_1K=0.761  # 출력 1,000 토큰당 원  (761 / 1000)
# ────────────────────────────────────────────────────────────────────

cd "$(dirname "$0")/.."

sudo docker compose logs backend --since "$SINCE" --no-color 2>/dev/null \
  | grep 'llm_usage ' \
  | awk -v pw="$PROMPT_WON_PER_1K" -v cw="$COMPLETION_WON_PER_1K" '
      {
        # 로그 한 줄: 2026-10-09 14:22:07 INFO app.server llm_usage model=... prompt=... total=...
        # 날짜로 묶으려면 줄 전체가 필요하다 — grep -o 로 자르면 날짜가 사라진다.
        day = "합계"
        if (match($0, /[0-9]{4}-[0-9]{2}-[0-9]{2}/)) day = substr($0, RSTART, RLENGTH)
        for (i = 1; i <= NF; i++) {
          split($i, kv, "=")
          if (kv[1] == "prompt"     && kv[2] ~ /^[0-9]+$/) p[day] += kv[2]
          if (kv[1] == "completion" && kv[2] ~ /^[0-9]+$/) c[day] += kv[2]
          if (kv[1] == "total"      && kv[2] ~ /^[0-9]+$/) t[day] += kv[2]
        }
        n[day] += 1
      }
      END {
        if (length(n) == 0) { print "llm_usage 줄이 없다. 아직 생성을 안 했거나 로그가 돌았다."; exit }
        printf "%-12s %6s %12s %12s %12s", "날짜", "호출", "입력", "출력", "합계"
        if (pw > 0 || cw > 0) printf " %10s", "원"
        printf "\n"
        TN = TP = TC = TT = 0
        for (d in n) days[++k] = d
        for (i = 1; i <= k; i++) for (j = i + 1; j <= k; j++)
          if (days[i] > days[j]) { tmp = days[i]; days[i] = days[j]; days[j] = tmp }
        for (i = 1; i <= k; i++) {
          d = days[i]
          printf "%-12s %6d %12d %12d %12d", d, n[d], p[d], c[d], t[d]
          if (pw > 0 || cw > 0) printf " %10.0f", p[d]/1000*pw + c[d]/1000*cw
          printf "\n"
          TN += n[d]; TP += p[d]; TC += c[d]; TT += t[d]
        }
        printf "%-12s %6d %12d %12d %12d", "─ 합계", TN, TP, TC, TT
        if (pw > 0 || cw > 0) {
          won = TP/1000*pw + TC/1000*cw
          printf " %10.0f\n", won
          printf "\n호출 1회 평균: %.0f 토큰 · %.1f 원\n", TT/TN, won/TN
        } else {
          printf "\n\n호출 1회 평균: %.0f 토큰\n", TT/TN
          printf "금액을 보려면 이 파일 맨 위의 단가 두 줄을 채운다.\n"
        }
      }'
