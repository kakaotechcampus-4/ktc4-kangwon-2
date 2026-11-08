# (시험) e2e 러너 이미지 — 머지하지 않는다.
# 우분투 24.04 + Python 3.12(venv) + Node 22 + Playwright 1.64.0 Chromium(시스템 부품 · 글꼴 포함).
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git python3 python3-venv \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && python3 -m venv /opt/venv \
 && npx -y playwright@1.64.0 install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/* /root/.npm
