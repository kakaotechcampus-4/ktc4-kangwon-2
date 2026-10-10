#!/usr/bin/env bash
# HTTPS 인증서를 처음 한 번 받는다. 서버에서 한 번만 돌린다.
#
#   bash /home/ubuntu/ktc4-kangwon-2/scripts/https-setup.sh
#
# **갱신은 이 스크립트가 아니라 compose 의 certbot 서비스가 한다.**
# 12시간마다 보고 만료 30일 전부터 갱신하며, nginx 는 6시간마다 reload 한다.
#
# **닭과 달걀** — nginx 설정이 인증서 파일을 가리키는데 그 파일이 없으면 nginx 가 안 뜬다.
# 그래서 가짜 인증서를 먼저 깔아 nginx 를 띄우고, 진짜를 받아 덮어쓴다.
set -euo pipefail

DOMAIN=${DOMAIN:-ssample.duckdns.org}
EMAIL=${EMAIL:-}
DEPLOY_PATH=${DEPLOY_PATH:-/home/ubuntu/ktc4-kangwon-2}
LIVE=/etc/letsencrypt/live/$DOMAIN

cd "$DEPLOY_PATH"
# -T 로 TTY 를 안 잡는다. SSM 같은 비대화형 셸에서 `compose run` 이 TTY 를 잡으려다 멈춘다.
compose() { sudo docker compose "$@"; }
crun() { compose run --rm -T "$@"; }

if [ -z "$EMAIL" ]; then
  echo "EMAIL 이 필요하다. 만료 7일 전 알림이 여기로 온다." >&2
  echo "  EMAIL=you@example.com bash scripts/https-setup.sh" >&2
  exit 1
fi

# 도메인이 이 서버를 가리키는지 먼저 본다. 아니면 발급이 실패하고
# Let's Encrypt 는 같은 도메인에 시간당 5회만 허용한다.
resolved=$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || true)
public=$(curl -s --max-time 5 https://checkip.amazonaws.com || true)
echo "도메인 $DOMAIN -> ${resolved:-없음}"
echo "이 서버      -> ${public:-모름}"
if [ -n "$resolved" ] && [ -n "$public" ] && [ "$resolved" != "$public" ]; then
  echo "도메인이 이 서버를 안 가리킨다. DuckDNS 의 current ip 를 고치고 다시 돌린다." >&2
  exit 1
fi

# certbot 이 관리하는 인증서인지 본다. 갱신 설정 파일이 있으면 certbot 이 발급한 것이고,
# 없으면 아래 1번이 만든 임시이거나 찌꺼기다. 이 판정으로 3번에서 지울지 말지가 갈린다.
managed=0
if crun --entrypoint sh certbot -c "test -f /etc/letsencrypt/renewal/$DOMAIN.conf"; then
  managed=1
  echo "이미 certbot 이 관리하는 인증서가 있다. 지우지 않고 덮어쓴다."
fi

# 1. 가짜 인증서 — nginx 를 띄우기 위한 자리끼다. 바로 덮어쓴다.
if [ ! -f "$LIVE/fullchain.pem" ]; then
  echo "== 임시 인증서 =="
  crun --entrypoint sh certbot -c "
    mkdir -p $LIVE &&
    openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
      -keyout $LIVE/privkey.pem -out $LIVE/fullchain.pem -subj '/CN=$DOMAIN'"
fi

# 2. nginx 를 띄운다. 이제 80 의 ACME 경로가 열린다.
echo "== nginx =="
compose up -d nginx
sleep 3

# 3. 진짜 인증서.
#
# **진짜 인증서가 있으면 지우지 않는다** (멘토 리뷰 #119). 지우고 받다가 발급이 실패하면
# — 발급 횟수 제한, DNS 불일치 — 인증서가 하나도 안 남는다. nginx 는 메모리에 들고 있어
# 당장은 살아 있지만, compose 가 6시간마다 reload 하므로 그 안에 사이트가 죽는다.
#
# 임시 인증서(또는 찌꺼기)는 certbot 이 모르는 파일이라 지워야 한다 — 안 지우면
# certbot 이 "live 디렉터리가 이미 있다" 로 멈춘다. 그래서 둘을 갈라 처리한다.
echo "== 인증서 발급 =="
# --entrypoint certbot 이 필요하다. compose 의 certbot 서비스는 entrypoint 가
# 12시간 자는 갱신 루프라, 그냥 run 하면 certonly 가 무시되고 잠들어 버린다.
if [ "$managed" = 1 ]; then
  # 지우지 않고 덮어쓴다. --force-renewal 이 없으면 "아직 만료가 멀다" 로 건너뛴다.
  crun --entrypoint certbot certbot certonly \
    --webroot -w /var/www/certbot \
    -d "$DOMAIN" \
    --email "$EMAIL" --agree-tos --no-eff-email \
    --non-interactive --force-renewal
else
  crun --entrypoint sh certbot -c "rm -rf /etc/letsencrypt/live/$DOMAIN /etc/letsencrypt/archive/$DOMAIN /etc/letsencrypt/renewal/$DOMAIN.conf"
  crun --entrypoint certbot certbot certonly \
    --webroot -w /var/www/certbot \
    -d "$DOMAIN" \
    --email "$EMAIL" --agree-tos --no-eff-email \
    --non-interactive
fi

# 4. nginx 가 새 인증서를 읽게 한다.
echo "== nginx 다시 읽기 =="
compose exec -T nginx nginx -s reload

# 5. 갱신 담당을 띄운다.
compose up -d certbot

echo
echo "확인:"
echo "  curl -sI https://$DOMAIN | head -1"
echo "  curl -sI http://$DOMAIN  | head -1     301 이면 https 로 보내는 중"
