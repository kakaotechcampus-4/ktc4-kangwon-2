#!/usr/bin/env bash
# push 배포 전에 같은 커밋의 CI(push) 결과를 기다린다 — deploy.yml 「CI 기다리기」.
#
#   종료 0 · ok=true    CI 성공 — 올린다
#   종료 0 · ok=false   CI 가 취소됐다 — 더 새 push 가 CI 를 취소한 것이다(ci.yml concurrency). 뒤 배포 run 이 올린다
#   종료 1 · ok=false   CI 가 실패했거나(성공 · 취소 말고 전부) 시간 안에 안 끝났다 — 올리지 않는다
#
# 조회가 실패해도(네트워크 · 아직 run 이 안 생김) 다시 묻는다. 기다림의 끝은 WAIT_TRIES × WAIT_INTERVAL 초다.
# 결과는 GITHUB_OUTPUT 에 `ok` · `url`(CI run 주소)로 남긴다.
set -u

sha=${1:?올릴 커밋 SHA}
tries=${WAIT_TRIES:-135}
interval=${WAIT_INTERVAL:-20}

out() {
  if [ -n "${GITHUB_OUTPUT:-}" ]; then echo "$1" >>"$GITHUB_OUTPUT"; fi
}

for ((i = 1; i <= tries; i++)); do
  # 구분자를 탭으로 두면 빈 conclusion 이 붙은 탭 둘이 하나로 뭉개진다. 공백이 아닌 | 로 나눈다.
  line=$(gh run list -R "$GITHUB_REPOSITORY" --workflow ci.yml --commit "$sha" --event push --limit 1 \
    --json status,conclusion,url --jq '.[0] // empty | "\(.status)|\(.conclusion)|\(.url)"' 2>/dev/null) || line=""
  IFS='|' read -r status conclusion url <<<"$line"
  if [ "${status:-}" = completed ]; then
    echo "CI ${conclusion:-?} — ${url:-}"
    out "url=${url:-}"
    case "$conclusion" in
      success)
        out ok=true
        exit 0
        ;;
      cancelled)
        echo "더 새 push 가 CI 를 취소했다. 이 커밋은 올리지 않는다 — 뒤 배포 run 이 올린다"
        out ok=false
        exit 0
        ;;
      *)
        out ok=false
        exit 1
        ;;
    esac
  fi
  echo "CI 기다림 $i/$tries — ${status:-아직 run 이 없다}"
  sleep "$interval"
done

echo "CI 가 $((tries * interval))초 안에 끝나지 않았다. 올리지 않는다"
out ok=false
exit 1
