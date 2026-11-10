#!/usr/bin/env bash
# push 배포 전에 같은 커밋의 CI(push) 결과를 기다린다 — deploy.yml 「CI 기다리기」.
#
#   종료 0 · ok=true    CI 성공 — 올린다
#   종료 0 · ok=false   CI 가 취소됐고 브랜치 끝이 이미 다른 커밋이다 — 더 새 push 가 CI 를 취소한 것이다
#                       (ci.yml concurrency). 뒤 배포 run 이 올린다
#   종료 1 · ok=false   그 밖 전부 — CI 실패 · 시간 초과, 그리고 취소됐는데 브랜치 끝이 아직 이 커밋인 것(손으로
#                       취소했거나 job 시간 초과). 뒤따를 배포가 없으니 조용히 넘기지 않는다
#
# 조회가 실패해도(네트워크 · 아직 run 이 안 생김) 다시 묻는다. 기다림의 끝은 WAIT_TRIES × WAIT_INTERVAL 초다.
# 결과는 GITHUB_OUTPUT 에 `ok` · `url`(CI run 주소)로 남긴다.
set -u

sha=${1:?올릴 커밋 SHA}
branch=${GITHUB_REF_NAME:?push 된 브랜치 이름}
tries=${WAIT_TRIES:-135}
interval=${WAIT_INTERVAL:-20}

out() {
  if [ -n "${GITHUB_OUTPUT:-}" ]; then echo "$1" >>"$GITHUB_OUTPUT"; fi
}

for ((i = 1; i <= tries; i++)); do
  # 구분자를 탭으로 두면 빈 conclusion 이 붙은 탭 둘이 하나로 뭉개진다. 공백이 아닌 | 로 나눈다.
  line=$(gh run list -R "$GITHUB_REPOSITORY" --workflow ci.yml --commit "$sha" --branch "$branch" --event push --limit 1 \
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
        out ok=false
        tip=$(gh api "repos/$GITHUB_REPOSITORY/commits/$branch" --jq .sha 2>/dev/null) || tip=""
        if [ -n "$tip" ] && [ "$tip" != "$sha" ]; then
          echo "더 새 push(${tip:0:8})가 CI 를 취소했다. 이 커밋은 올리지 않는다 — 뒤 배포 run 이 올린다"
          exit 0
        fi
        echo "CI 가 취소됐는데 $branch 끝이 ${tip:-(못 읽음)} 이다 — 뒤따를 배포가 없다. 올리지 않는다"
        exit 1
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
