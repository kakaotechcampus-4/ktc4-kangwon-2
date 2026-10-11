#!/usr/bin/env sh
# 내 컴퓨터에서 쓸 자체 서명 인증서를 만든다.
#
# **왜 필요한가.** nginx.conf 가 Let's Encrypt 인증서를 가리키는데(#113), 그 파일은
# 서버에만 있다. 없으면 nginx 가 뜨다가 죽어서 `docker compose up` 이 통째로 안 된다.
# 한 번만 돌리면 된다 — 인증서는 certbot-etc 볼륨에 남는다.
#
# 서버에서는 절대 돌리지 않는다. 진짜 인증서를 덮어쓴다.
set -eu

DOMAIN=ssample.duckdns.org
LIVE=/etc/letsencrypt/live/$DOMAIN

if [ "${1:-}" != "--i-am-not-the-server" ]; then
  echo "이 스크립트는 로컬 전용이다. 서버에서 돌리면 진짜 인증서를 덮어쓴다." >&2
  echo "확인했으면: sh scripts/local-cert.sh --i-am-not-the-server" >&2
  exit 1
fi

docker compose run --rm -T --entrypoint sh certbot -c "
  set -e
  if [ -f $LIVE/fullchain.pem ]; then echo '이미 있다. 그대로 쓴다.'; exit 0; fi
  mkdir -p $LIVE
  openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
    -keyout $LIVE/privkey.pem -out $LIVE/fullchain.pem \
    -subj '/CN=$DOMAIN' >/dev/null 2>&1
  echo '만들었다.'
"
docker compose up -d nginx
echo
echo "브라우저는 http://localhost 로 연다. https 는 자체 서명이라 경고가 뜬다."
