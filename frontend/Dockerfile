FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# `NEXT_PUBLIC_*` 는 **빌드 때** 글자로 박힌다. 실행 환경변수로는 안 바뀐다.
# 시험용 「전부 지우기」 단추를 켜는 값이고, 기본은 꺼짐이다 — 파일럿 전에 끈다.
# 서버에도 같은 이름의 스위치가 있고 그쪽이 최종이다(꺼져 있으면 경로가 404).
ARG NEXT_PUBLIC_ALLOW_TEST_RESET=0
ENV NEXT_PUBLIC_ALLOW_TEST_RESET=$NEXT_PUBLIC_ALLOW_TEST_RESET
# 구글 Search Console 소유권 확인 토큰. 비워 두면 태그를 넣지 않는다.
ARG GOOGLE_SITE_VERIFICATION=""
ENV GOOGLE_SITE_VERIFICATION=$GOOGLE_SITE_VERIFICATION

RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]
