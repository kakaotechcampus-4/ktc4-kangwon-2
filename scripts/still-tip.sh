#!/usr/bin/env bash
# push 배포가 배포 잠금을 얻은 뒤, 올릴 커밋이 아직 브랜치 끝인지 본다 — deploy.yml 「아직 브랜치 끝인지」.
#
#   종료 0 · stale=false   아직 끝이다 — 올린다
#   종료 0 · stale=true    더 새 push 가 있다 — 올리지 않는다. 그 push 의 run 이 올린다(또는 이미 올렸다)
#   종료 1                 끝을 못 읽었다 — 올리지 않는다
#
# 「CI 기다리기」는 잠금 밖에서 돈다. 그 사이 더 새 push 가 먼저 CI 를 통과해 올라가면, 늦게 잠금을 얻은
# 옛 커밋이 그 위를 덮는다(하민 리뷰 #549). 그래서 잠금 안에서, 서버를 바꾸기 직전에 다시 본다.
set -u

sha=${1:?올릴 커밋 SHA}
branch=${GITHUB_REF_NAME:?push 된 브랜치 이름}

out() {
  if [ -n "${GITHUB_OUTPUT:-}" ]; then echo "$1" >>"$GITHUB_OUTPUT"; fi
}

tip=""
for _ in 1 2 3; do
  tip=$(gh api "repos/$GITHUB_REPOSITORY/commits/$branch" --jq .sha 2>/dev/null) && [ -n "$tip" ] && break
  tip=""
  sleep "${TIP_RETRY_INTERVAL:-5}"
done

if [ -z "$tip" ]; then
  echo "$branch 끝을 읽지 못했다. 올리지 않는다"
  exit 1
fi
if [ "$tip" != "$sha" ]; then
  echo "$branch 끝이 ${tip:0:8} 이다 — 더 새 push 가 있다. ${sha:0:8} 은 올리지 않는다"
  out stale=true
  exit 0
fi
echo "$branch 끝이 ${sha:0:8} 그대로다 — 올린다"
out stale=false
