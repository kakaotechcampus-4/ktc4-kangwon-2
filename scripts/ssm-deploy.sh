#!/usr/bin/env bash
# scripts/deploy.sh 를 서버에 보내고 끝날 때까지 기다린다. 러너(deploy.yml)에서 돈다.
#   scripts/ssm-deploy.sh <올릴 커밋 전체 SHA>
# 환경변수: INSTANCE_ID(필수), AWS 자격증명 · 리전(aws CLI 가 읽는다).
# SSM_WAIT_TRIES · SSM_WAIT_INTERVAL 은 시험이 줄이려고 둔 것이다(기본 190번 × 10초).
#
# 종료 코드는 서버에서 돈 deploy.sh 의 것을 그대로 낸다. deploy.yml 의 자동 롤백이 이 숫자를 읽는다(ADR-078).
#   0     서버 명령이 성공했다
#   1~255 서버 명령이 이 코드로 실패했다. 3 은 deploy.sh 가 「교체 뒤 서버 안에서 서비스가 안 살아났다」에 쓴다
#   124   기다린 시간 안에 끝나지 않았다. 서버는 아직 돌 수 있다
#   125   서버 명령이 취소됐거나 시간 초과로 끝났다
#   1     그 밖 — 명령을 못 보냈거나, 상태를 못 읽었거나, 응답을 해석하지 못했다
# **3 을 이 스크립트가 만들어 내는 일이 없어야 한다.** jq 도 컴파일 오류에 3 을 낸다. 아래 ERR 트랩이 예상 밖 실패를 1 로 바꾼다.
set -Eeuo pipefail
trap 'exit 1' ERR

sha=${1:?"올릴 커밋 SHA 를 넘긴다"}
: "${INSTANCE_ID:?INSTANCE_ID 가 없다}"
# 서버 한도(executionTimeout 1800초)보다 오래 기다린다. 190번 × 10초 = 1900초.
tries=${SSM_WAIT_TRIES:-190}
interval=${SSM_WAIT_INTERVAL:-10}

# 스크립트 파일을 서버에 미리 둘 필요가 없다. 이 커밋의 내용을 그대로 보낸다.
# **쉬뱅이 commands 의 첫 원소여야 한다.** SSM 이 배열을 줄로 이어 붙여 파일로 만드는데, 첫 줄이 `#!` 가 아니면
# `sh`(dash)로 돌아 `pipefail` 에서 죽는다(scripts/deploy.sh 머리 주석). executionTimeout 은 서버에서 도는 시간이다.
# docker build 가 오래 걸린다.
command_id=$(aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --comment "deploy $sha" \
  --parameters "$(jq -n --rawfile script "$(dirname "$0")/deploy.sh" --arg ref "$sha" \
    '{commands: ["#!/usr/bin/env bash", "export DEPLOY_REF=\($ref)", $script],
      executionTimeout: ["1800"]}')" \
  --query Command.CommandId --output text) || { echo "배포 명령을 보내지 못했다"; exit 1; }
echo "배포 명령 $command_id"

# send-command 는 보내고 바로 끝난다. 끝날 때까지 안 기다리면 실패해도 초록불이 뜬다.
# aws ssm wait 는 100초에서 포기해서 docker build 를 못 기다린다. 직접 돈다.
# 상태 · 종료 코드 · 출력은 **마지막 응답 하나에서** 같이 읽는다. 따로 물으면 서로 다른 시점의 값이 된다.
# 보낸 직후에는 명령이 아직 등록되지 않아 InvocationDoesNotExist 가 날 수 있다 — 그 오류만, 아직 한 번도 못 읽었을 때만
# 다시 묻는다. 다른 오류(권한 · 네트워크 · 만료된 자격증명)는 오류 글을 찍고 바로 1 로 끝난다. 삼켜서 마지막에 본 상태를
# 계속 쓰면 30분을 기다리고 124 로 끝난다.
inv=""
status=Pending
errfile=$(mktemp)
trap 'rm -f "$errfile"' EXIT
for ((attempt = 1; attempt <= tries; attempt++)); do
  if out=$(aws ssm get-command-invocation --command-id "$command_id" --instance-id "$INSTANCE_ID" --output json 2>"$errfile"); then
    inv=$out
    status=$(jq -er .Status <<<"$inv") || { echo "응답에서 상태를 읽지 못했다"; exit 1; }
    case "$status" in
      Pending | InProgress | Delayed | Cancelling) ;;
      *) break ;;
    esac
  elif [ -n "$inv" ] || ! grep -q InvocationDoesNotExist "$errfile"; then
    echo "상태를 읽지 못했다 (명령 $command_id):"
    cat "$errfile"
    exit 1
  fi
  sleep "$interval"
done

[ -n "$inv" ] || { echo "상태를 한 번도 읽지 못했다 (명령 $command_id)"; exit 1; }

echo "--- 서버 출력 ---"
jq -r .StandardOutputContent <<<"$inv" || exit 1
echo "--- 서버 오류 ---"
jq -r .StandardErrorContent <<<"$inv" || exit 1

# 출력은 24000자에서 잘린다. 전문이 필요해지면 S3 로 내보내는 설정을 붙인다.
code=$(jq -r .ResponseCode <<<"$inv") || exit 1
echo "상태 $status (서버 종료 코드 $code)"
case "$status" in
  Success) exit 0 ;;
  Failed)
    # 1~255 정수일 때만 그대로 낸다. 서버 명령이 못 시작되면 -1 이 온다.
    if [[ "$code" =~ ^[0-9]+$ ]] && [ "$code" -ge 1 ] && [ "$code" -le 255 ]; then exit "$code"; fi
    exit 1
    ;;
  Pending | InProgress | Delayed | Cancelling)
    echo "$((tries * interval))초를 기다렸지만 서버 명령이 끝나지 않았다. 서버는 아직 돌 수 있다"
    exit 124
    ;;
  *) exit 125 ;; # Cancelled · TimedOut · DeliveryTimedOut · ExecutionTimedOut · Undeliverable · Terminated …
esac
