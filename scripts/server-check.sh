#!/usr/bin/env bash
# 운영 서버 점검 — 배포 · 백업 · 인증서가 의도대로 걸려 있고 실제로 돌았는지 본다.
#
#   bash scripts/server-check.sh     서버에서 ubuntu 로 (Session Manager → sudo -iu ubuntu)
#
# **서비스 · 설정 · DB · 인증서 · 백업을 바꾸지 않는다.** docker exec 기록 · 접속 로그 같은
# 관측 흔적만 남는다. 능동 점검(certbot renew --dry-run)은 넣지 않았다.
#
#   OK    기계가 가를 수 있는 것 — 통과
#   FAIL  위와 같은데 실패. 하나라도 있으면 종료 코드 1
#   --    사람이 보고 판단할 것
#
# **출력은 돌린 터미널에만 나온다.** 채팅 · 이슈에 붙이기 쉽게 crontab · 훅 · 로그 원문은 찍지 않는다 —
# 비밀번호 · 키가 섞일 수 있다. 시각 · 대상 · 변수 이름 · 정해진 사건 이름만 다시 써서 보여 준다.
# 예외 둘 — 가리면 고장을 놓친다(2026-10-21: S3 백업이 한 번도 안 갔는데 이 점검이 못 보여 줬다).
#   BACKUP_S3_URI 주소    비밀이 아니다. cron 줄 앞 · cron 변수 줄 · .env 어디에 있어도 s3:// 꼴이면 보여 준다
#   백업 로그 끝 6줄       원문이다. 사건 이름만 고르면 처음 보는 오류 줄(aws 등)이 빠진다 — 붙이기 전에 한 번 본다
#
# 저장소에 없을 때는 붙여 넣어 돌린다. 점검은 전부 main() 안에 있고 마지막 줄에서만 돌므로,
# 붙여 넣은 나머지 줄을 중간 명령이 stdin 으로 삼키지 않는다.
#   bash -s <<'SERVER_CHECK_EOF'
#   …이 파일 내용…
#   SERVER_CHECK_EOF
set -uo pipefail

DEPLOY_PATH=${DEPLOY_PATH:-/home/ubuntu/ktc4-kangwon-2}
BACKUP_DIR=${BACKUP_DIR:-/home/ubuntu/backup}
DOMAIN=${DOMAIN:-ssample.duckdns.org}
MAX_BACKUP_AGE_H=${MAX_BACKUP_AGE_H:-26} # 하루 한 번 + 여유
MIN_CERT_DAYS=${MIN_CERT_DAYS:-25}       # certbot 은 30일 전부터 갱신한다. 그보다 적으면 갱신이 안 된 것
# crontab 의 작업 줄은 분(숫자 · *) 이나 @ 로 시작한다. 주석 · 빈 줄이 아닌 나머지는 변수 줄로 본다.
# 이 나눔은 틀릴 수 있다(cron 은 `1PASSWORD=…` 같은 이름도 받는다). 그래서 **안전은 나눔이 아니라 출력이 지킨다** —
# show_cron 은 꼴을 확인한 조각(시각 칸 · 사용자 · 변수 이름 · s3:// 주소)만 찍는다.
CRON_JOB_RE='^[[:space:]]*[0-9*@]'
S3_URI_RE='s3://[A-Za-z0-9._/-]+'

fails=0
ok() { printf 'OK    %s\n' "$*"; }
fail() {
  printf 'FAIL  %s\n' "$*"
  fails=$((fails + 1))
}
info() { printf -- '--    %s\n' "$*"; }
sub() { sed 's/^/        /'; }

# certbot 컨테이너 안에서 돈다. 로그 원문 대신 파일 시각과 사건 이름만 낸다.
# 순서가 중요하다 — 정상 실행 로그의 디버그 줄에도 error 라는 글자가 섞일 수 있다.
read -r -d '' CERTBOT_SH <<'SH'
echo "인증서: $(ls /etc/letsencrypt/renewal 2>/dev/null | sed 's/\.conf$//' | tr '\n' ' ')"
echo "훅: renewal 설정에 $(cat /etc/letsencrypt/renewal/*.conf 2>/dev/null | grep -ci hook)줄 · 훅 파일 $(find /etc/letsencrypt/renewal-hooks -type f 2>/dev/null | wc -l)개"
cd /var/log/letsencrypt 2>/dev/null || { echo "로그 폴더 없음"; exit 0; }
for f in $(ls -t letsencrypt.log* 2>/dev/null | head -n 6); do
  if grep -q 'not yet due' "$f"; then e='갱신할 때 아님'
  elif grep -qiE 'Congratulations|successfully renewed' "$f"; then e='갱신함'
  elif grep -qiE 'error|failed' "$f"; then e='실패 흔적 — 서버에서 원문을 볼 것'
  else e='그 밖'; fi
  echo "$(ls -l "$f" | awk '{print $6, $7, $8}')  $e"
done
SH

# 서버 소스(git HEAD)만 본다. 도는 컨테이너의 버전은 아니다 — deploy.sh 는 HEAD 를 바꾼 뒤 빌드해서,
# 빌드가 실패하면 옛 컨테이너가 돌고 있어도 여기는 새 커밋이 보인다. 그건 Actions 배포 기록이 알려 준다.
# 배포는 main 말고도 브랜치 · 커밋을 고를 수 있다(deploy.yml DEPLOY_REF). main 이나 develop 끝이면 통과다.
check_commit() {
  local head refs main_c dev_c dirty note=""
  head=$(git -C "$DEPLOY_PATH" rev-parse HEAD 2>/dev/null)
  # 읽기만 한다 — ls-remote 는 refs 를 안 바꾸고, status 는 잠금 파일을 안 만들게 한다.
  refs=$(GIT_TERMINAL_PROMPT=0 timeout 10 git -C "$DEPLOY_PATH" ls-remote origin refs/heads/main refs/heads/develop 2>/dev/null)
  main_c=$(awk '$2 == "refs/heads/main" { print $1 }' <<<"$refs")
  dev_c=$(awk '$2 == "refs/heads/develop" { print $1 }' <<<"$refs")
  dirty=$(git -C "$DEPLOY_PATH" --no-optional-locks status --porcelain 2>/dev/null | grep -c .)
  [ "$dirty" -gt 0 ] && note=" · 서버에서 바뀐 파일 ${dirty}개"
  if [ -z "$head" ]; then
    fail "서버 소스 커밋을 못 읽었다"
  elif [ -z "$main_c$dev_c" ]; then
    info "서버 소스 ${head:0:7} — GitHub 을 못 읽어 비교 못 함${note}"
  elif [ "$head" = "$main_c" ]; then
    ok "서버 소스 ${head:0:7} = GitHub main${note}"
  elif [ "$head" = "$dev_c" ]; then
    ok "서버 소스 ${head:0:7} = GitHub develop${note}"
  else
    info "서버 소스 ${head:0:7} — main ${main_c:0:7} · develop ${dev_c:0:7} 어느 끝과도 다르다. 그 뒤 머지가 있었거나 커밋으로 되감았다 — Actions 배포 기록과 맞춰 본다${note}"
  fi
}

# 배포 판정과 같은 길이다(deploy.yml 의 /health/ready). 서버 안에서 nginx 80 으로 묻는다 — 80 의 /health 는 백엔드로 넘긴다.
# 컨테이너가 running 이어도 DB 에 못 붙으면 503 이다. 이게 없으면 앱이 죽어 있어도 「FAIL 없음」이 나온다.
check_ready() {
  local code
  code=$(curl -sS -m 10 -o /dev/null -w '%{http_code}' http://127.0.0.1/health/ready 2>/dev/null)
  if [ "$code" = 200 ]; then
    ok "앱 준비됨 — /health/ready 200"
  else
    [ -z "$code" ] || [ "$code" = 000 ] && code="연결 안 됨"
    fail "앱 준비 안 됨 — /health/ready ${code}"
  fi
}

check_containers() {
  local dk=$1 rows svc row n st hl rc oom pol h why
  rows=$($dk compose ps -aq 2>/dev/null | xargs -r $dk inspect --format \
    '{{index .Config.Labels "com.docker.compose.service"}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}} {{.RestartCount}} {{.State.OOMKilled}} {{.HostConfig.RestartPolicy.Name}}' 2>/dev/null)
  for svc in db backend frontend nginx certbot; do
    row=$(awk -v s="$svc" '$1 == s' <<<"$rows")
    n=$(grep -c . <<<"$row")
    if [ "$n" -ne 1 ]; then
      fail "$svc 컨테이너가 ${n}개 — 1개여야 한다"
      continue
    fi
    read -r _ st hl rc oom pol <<<"$row"
    why=""
    [ "$st" = running ] || why="$why · $st"
    # db 만 healthcheck 가 있다(docker-compose.yml). 나머지는 health 가 없는 게 정상이다.
    if [ "$svc" = db ] || [ "$hl" != - ]; then [ "$hl" = healthy ] || why="$why · health $hl"; fi
    [ "$oom" = false ] || why="$why · 메모리 부족으로 죽었다"
    [ "$pol" = unless-stopped ] || why="$why · 재시작 정책 $pol"
    h=""
    [ "$hl" != - ] && h=" · $hl"
    # 재시작 횟수는 지난 이력이라 판정에 안 넣는다. 0 이 아니면 그 컨테이너 로그를 사람이 본다.
    if [ -z "$why" ]; then
      ok "$(printf '%-9s' "$svc") ${st}${h} · 재시작 ${rc}회"
    else
      fail "$(printf '%-9s' "$svc")${why} · 재시작 ${rc}회"
    fi
  done
}

check_systemd() {
  local en u a
  en=$(systemctl is-enabled docker 2>/dev/null)
  if [ "$en" = enabled ]; then ok "docker 부팅 시 자동 시작"; else fail "docker 부팅 시 자동 시작 — ${en:-확인 못 함}"; fi
  # 한 줄에 둘을 물으면 하나만 active 여도 성공으로 끝난다. 따로 묻는다.
  for u in docker cron; do
    a=$(systemctl is-active "$u" 2>/dev/null)
    if [ "$a" = active ]; then ok "$u 실행 중"; else fail "$u — ${a:-확인 못 함}"; fi
  done
}

# 출처<TAB>줄. 주석 · 빈 줄은 뺀다. 변수 줄(NAME=…)은 남긴다 — cron 이 그 아래 작업에 넘기는 값이다.
# **작업 줄을 고를 때는 cron_jobs 를 먼저 거친다.** 변수 값에 pg_dump 같은 글자가 들어 있으면
# 작업 줄로 오인해 값을 찍는다(예: PGPASSWORD=…pg_dump…).
cron_lines() {
  local f
  {
    sudo -n crontab -l -u root 2>/dev/null | awk '{print "root\t" $0}'
    sudo -n crontab -l -u ubuntu 2>/dev/null | awk '{print "ubuntu\t" $0}'
    sudo -n cat /etc/crontab 2>/dev/null | awk '{print "/etc/crontab\t" $0}'
    for f in /etc/cron.d/*; do
      [ -f "$f" ] && sudo -n cat "$f" 2>/dev/null | awk -v s="$f" '{print s "\t" $0}'
    done
  } | awk '{ l = substr($0, index($0, "\t") + 1) } l !~ /^[[:space:]]*(#|$)/'
}

cron_jobs() { awk -v re="$CRON_JOB_RE" '$0 != "" { l = substr($0, index($0, "\t") + 1); if (l ~ re) print }'; }
cron_vars() { awk -v re="$CRON_JOB_RE" '$0 != "" { l = substr($0, index($0, "\t") + 1); if (l !~ re) print }'; }

check_backup() {
  local cron=$1 newest ts f now age why=""
  newest=$(sudo -n find "$BACKUP_DIR" -maxdepth 1 -type f -name 'ssuksak_*.sql.gz' -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -n 1)
  if [ -z "$newest" ]; then
    # cron 형태가 문서에 둘이다 — backup.sh(로컬에 남김) · pg_dump 한 줄(S3 로 바로, deploy.md).
    if ! grep -q 'backup\.sh' <<<"$cron" && grep -q 'pg_dump' <<<"$cron"; then
      info "최신 백업 — 로컬 파일 없음. cron 이 S3 로 바로 보내는 형태라 S3 를 봐야 한다"
    else
      fail "최신 백업 — $BACKUP_DIR 에 백업 파일이 없다"
    fi
    return
  fi
  ts=${newest%%.*}
  f=${newest#* }
  now=$(date +%s)
  age=$(((now - ts) / 3600))
  [ "$ts" -le "$now" ] || why="$why · 파일 시각이 미래"
  [ "$age" -lt "$MAX_BACKUP_AGE_H" ] || why="$why · ${age}시간 전 (${MAX_BACKUP_AGE_H}시간 넘음)"
  # 한 번 풀면서 둘 다 본다 — 압축이 깨졌나(gzip), 끝까지 쓴 덤프인가(마지막 줄).
  # pg_dump 가 끝까지 쓴 덤프만 이 줄로 끝난다. 실패한 백업도 20바이트짜리 gzip 은 남는다.
  sudo -n gzip -cd "$f" 2>/dev/null | tail -n 20 | grep -q '^-- PostgreSQL database dump complete$'
  local st=("${PIPESTATUS[@]}")
  if [ "${st[0]}" -ne 0 ]; then
    why="$why · 압축이 깨졌다"
  elif [ "${st[2]}" -ne 0 ]; then
    why="$why · 덤프 끝 표시 없음"
  fi
  if [ -z "$why" ]; then
    ok "최신 백업 $(basename "$f") · ${age}시간 전 · gzip 통과 · 덤프 끝 표시 있음"
  else
    fail "최신 백업 $(basename "$f")${why}"
  fi
}

check_cert() {
  local dk=$1 served stored end days fp_s fp_t why=""
  # 밖이 아니라 이 서버의 nginx 가 실제로 내주는 것. 도메인 · 체인 검증까지 통과해야 받는다.
  served=$(echo | timeout 10 openssl s_client -connect 127.0.0.1:443 -servername "$DOMAIN" \
    -verify_hostname "$DOMAIN" -verify_return_error 2>/dev/null | openssl x509 2>/dev/null)
  if [ -z "$served" ]; then
    fail "인증서 — 127.0.0.1:443 에서 $DOMAIN 로 검증되는 인증서를 못 받았다"
    return
  fi
  end=$(openssl x509 -noout -enddate <<<"$served" | cut -d= -f2)
  days=$((($(date -d "$end" +%s) - $(date +%s)) / 86400))
  [ "$days" -ge "$MIN_CERT_DAYS" ] || why="$why · ${MIN_CERT_DAYS}일 미만 — 갱신이 됐어야 한다"
  # 갱신돼도 nginx 가 다시 읽지 않으면 옛 것을 계속 내준다. nginx 가 읽는 그 파일과 비교한다(nginx.conf).
  if [ -n "$dk" ]; then
    stored=$($dk compose exec -T nginx cat "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" 2>/dev/null)
    fp_s=$(openssl x509 -noout -fingerprint -sha256 <<<"$served" | cut -d= -f2)
    fp_t=$(openssl x509 -noout -fingerprint -sha256 <<<"$stored" 2>/dev/null | cut -d= -f2)
    if [ -z "$fp_t" ]; then
      why="$why · 저장된 인증서를 못 읽었다"
    elif [ "$fp_s" != "$fp_t" ]; then
      why="$why · 저장된 것과 내주는 것이 다르다 — nginx 가 새 인증서를 안 읽었다"
    fi
  else
    why="$why · docker 에 못 닿아 저장된 인증서와 비교 못 함"
  fi
  if [ -z "$why" ]; then
    ok "인증서 남은 날 ${days}일 · 저장된 것 = 내주는 것"
  else
    fail "인증서 남은 날 ${days}일${why}"
  fi
}

show_cron() {
  local jobs vars bl env_s3
  jobs=$(cron_jobs <<<"$1")
  vars=$(cron_vars <<<"$1")
  info "백업 cron — 시각 · 대상 · S3 주소 (원문은 서버에서. 꼴을 확인한 조각만 찍고 나머지는 ?)"
  bl=$(grep -E 'backup\.sh|pg_dump' <<<"$jobs")
  if [ -z "$bl" ]; then
    echo "(백업 줄 없음 — systemd timer 는 안 봤다. 「없음」이 아니라 「미발견」)" | sub
  else
    # 크론 줄 자체에도 탭이 들어간다 — 출처 뒤 첫 탭부터가 크론 줄이다.
    # 시각 칸은 꼴이 맞을 때만 다시 쓴다. @daily 처럼 한 단어 시각이면 그 하나만.
    # /etc/crontab · /etc/cron.d 는 시각 뒤에 실행할 사용자 칸이 하나 더 있다.
    # 명령 앞 변수는 공백으로 나누지 않는다 — 따옴표 안 공백에서 다른 값이 딸려 나온다. s3:// 주소 꼴만 줄에서 찾는다.
    # **시각 · 사용자 칸 중 하나라도 꼴이 틀리면 줄 전체를 가린다.** 칸마다 따로 가리면, 작업 줄로 잘못 나뉜
    # 변수 줄에서 우연히 꼴이 맞는 조각(따옴표 안 낱말 등)이 사용자 · 시각 자리로 새어 나온다.
    awk -v s3re="BACKUP_S3_URI=$S3_URI_RE" '
      function ok_(s, re) { if (s !~ re) bad = 1; return s }
      {
        i = index($0, "\t"); src = substr($0, 1, i - 1); l = substr($0, i + 1)
        sub(/^[[:space:]]+/, "", l)
        split(l, w, /[[:space:]]+/)
        bad = 0
        if (w[1] ~ /^@/) {
          when = ok_(w[1], "^@(reboot|yearly|annually|monthly|weekly|daily|midnight|hourly)$"); k = 2
        } else {
          when = ""
          for (j = 1; j <= 5; j++)
            when = when ((j > 1) ? " " : "") ok_(w[j], "^([0-9*/,-]+|[A-Za-z][A-Za-z][A-Za-z])$")
          k = 6
        }
        user = (src ~ /^(root|ubuntu)$/) ? "" : "  (" ok_(w[k], "^[a-z_][a-z0-9_-]*$") ")"
        if (bad) { print src "  ? (cron 작업 줄 꼴이 아니다 — 서버에서 원문을 볼 것)"; next }
        s3 = match(l, s3re) ? "  · " substr(l, RSTART, RLENGTH) : ""
        t = (l ~ /backup\.sh/) ? "scripts/backup.sh" : (l ~ /aws s3/) ? "pg_dump → S3 로 바로" : "pg_dump"
        print src "  " when user "  → " t s3
      }' <<<"$bl" | sub
  fi
  # 변수 줄은 그 crontab 의 아래 작업 전부에 넘어간다. backup.sh 는 이 값을 .env 보다 먼저 본다.
  # 이름은 꼴이 맞을 때만, 값은 BACKUP_S3_URI 의 s3:// 주소만 찍는다.
  [ -z "$vars" ] || awk -v s3re="^$S3_URI_RE\$" '{
      i = index($0, "\t"); l = substr($0, i + 1); e = index(l, "=")
      name = (e > 0) ? substr(l, 1, e - 1) : ""; gsub(/[[:space:]]/, "", name)
      if (name !~ /^[A-Za-z_][A-Za-z0-9_]*$/) { print substr($0, 1, i - 1) ": 변수 줄 ? (이름 꼴이 아니다 — 서버에서 원문을 볼 것)"; next }
      val = substr(l, e + 1); sub(/^[[:space:]]+/, "", val); sub(/[[:space:]]+$/, "", val)
      if (name == "BACKUP_S3_URI") name = name "=" ((val ~ s3re) ? val : "? (s3:// 꼴이 아니다)")
      print substr($0, 1, i - 1) ": 변수 줄 " name
    }' <<<"$vars" | sub
  env_s3=$(grep -h '^BACKUP_S3_URI=' "$DEPLOY_PATH/.env" 2>/dev/null | tail -n 1 | cut -d= -f2-)
  if [ -z "$env_s3" ]; then
    env_s3="BACKUP_S3_URI 없음"
  elif [[ "$env_s3" =~ ^$S3_URI_RE$ ]]; then
    env_s3="BACKUP_S3_URI=$env_s3"
  else
    env_s3="BACKUP_S3_URI=? (s3:// 꼴이 아니다)"
  fi
  echo ".env: $env_s3 · cron PATH 의 aws: $(PATH=/usr/bin:/bin command -v aws || echo 없음)" | sub
  [ -z "$jobs" ] || awk '$0 !~ /backup\.sh|pg_dump/ { n[substr($0, 1, index($0, "\t") - 1)]++ }
    END { for (s in n) print s ": 그 밖의 줄 " n[s] "개" }' <<<"$jobs" | sub
}

show_certbot() {
  info "certbot — 인증서 · 훅 · 최근 실행 (12시간 간격인지, 「갱신할 때 아님」인지 보세요)"
  $1 compose exec -T certbot sh -c "$CERTBOT_SH" 2>/dev/null | sub
  [ "${PIPESTATUS[0]}" -eq 0 ] || echo "(certbot 컨테이너에 못 들어갔다)" | sub
}

show_nginx() {
  local out
  info "nginx reload — 최근 48시간 (6시간 간격인지 보세요. 시각은 UTC)"
  out=$($1 compose logs --since 48h --timestamps nginx 2>&1 |
    grep -E 'signal process started|reconfiguring|\[emerg\]|\[alert\]' |
    sed -nE 's/^.*([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})[^ ]* .*(signal process started|reconfiguring|\[emerg\]|\[alert\]).*$/\1Z  \2/p' |
    tail -n 8)
  if [ -n "$out" ]; then sub <<<"$out"; else echo "(흔적 없음 — 「증거 미검출」. reload 가 안 됐다는 뜻은 아니다)" | sub; fi
}

show_backup_log() {
  local out
  # 고르지 않고 끝 줄을 그대로 낸다. 한 번 돌 때 두 줄(backup ok · 그 뒤 s3 ok / s3 skip / 오류)이라 3번치다.
  info "백업 로그 — 마지막 6줄 그대로 (줄마다 160자까지. 시각은 UTC. backup ok 다음 줄을 보세요)"
  out=$(sudo -n tail -n 6 /var/log/ssuksak-backup.log 2>/dev/null | cut -c1-160)
  if [ -n "$out" ]; then sub <<<"$out"; else echo "(기록 없음 — 로그 파일이 없거나 backup.sh 형태 cron 이 아니다)" | sub; fi
}

main() {
  local tz dk="" cron
  tz=$(timedatectl show -p Timezone --value 2>/dev/null)
  printf 'server-check  %s  (UTC %s · %s)\n\n' "$(date -Is)" "$(date -u +%H:%M)" "${tz:-시간대 모름}"

  sudo -n true 2>/dev/null || fail "sudo -n 이 안 된다 — 아래 백업 · crontab 항목이 실패로 나온다"

  # compose 는 지금 폴더의 docker-compose.yml 을 본다. 못 들어가면 엉뚱한 프로젝트를 보지 않게 건너뛴다.
  # ubuntu 가 docker 그룹에 없을 수 있다(deploy.sh 가 sudo 를 쓰는 이유). `ps` 는 데몬에 닿는다.
  if ! cd "$DEPLOY_PATH" 2>/dev/null; then
    fail "$DEPLOY_PATH 로 못 들어갔다 — 컨테이너 항목을 건너뛴다"
  elif docker compose ps >/dev/null 2>&1; then
    dk="docker"
  elif sudo -n docker compose ps >/dev/null 2>&1; then
    dk="sudo -n docker"
  else
    fail "docker 데몬에 닿지 못한다 — 컨테이너 항목을 건너뛴다"
  fi

  cron=$(cron_lines)
  check_commit
  [ -n "$dk" ] && check_containers "$dk"
  check_ready
  check_systemd
  check_backup "$(cron_jobs <<<"$cron")"
  check_cert "$dk"

  echo
  show_cron "$cron"
  [ -n "$dk" ] && show_certbot "$dk"
  [ -n "$dk" ] && show_nginx "$dk"
  show_backup_log

  echo
  if [ "$fails" -eq 0 ]; then echo "FAIL 없음"; else echo "FAIL ${fails}건"; fi
  [ "$fails" -eq 0 ]
}

# 테스트는 SERVER_CHECK_LIB=1 로 source 해서 함수만 부른다(backend/tests/test_server_check_script.py).
[ -n "${SERVER_CHECK_LIB:-}" ] || main "$@" </dev/null
