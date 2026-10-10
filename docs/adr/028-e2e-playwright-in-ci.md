# ADR-028: E2E 는 Playwright 로, 실제 스택 위에서 CI 가 돌린다

- 날짜: 2026-10-10
- 상태 — 채택

## 맥락

CI 는 백엔드(pytest)와 화면(node:test · next build)을 따로 본다. 화면 테스트는 MSW 목업이나
함수 단위라, 화면과 API 가 칸 이름·주소에서 어긋나도 양쪽 다 통과한다. 그 어긋남은
교사가 처음 쓰는 흐름 — 가입 → 원·반·아동 등록 → 관찰 기록 — 에서 터진다(#103).

## 결정

1. `@playwright/test` 를 frontend devDependency 로 넣는다. 브라우저는 chromium 하나.
2. 스펙은 `frontend/e2e/` 에 둔다. `npm run e2e` 로 돌고, `npm test`(node:test)와 섞이지 않는다.
3. CI 에 `e2e (playwright)` job 을 추가한다. postgres:15 서비스 · uvicorn(`LLM_MODE=mock`) ·
   `next start` 를 띄우고 MSW 를 끈 채 돌린다. 화면은 `FASTAPI_BASE_URL` rewrite 로 같은 출처 `/api` 를 탄다.
4. 첫 스펙은 행복 경로 하나다 — 가입부터 「아이별 모아보기」 건수까지.

## 근거

- **[실측]** 로컬(postgres:15 · 백엔드 이미지 · `next start`)에서 스펙 한 개가 약 3초에 통과한다.
  돌린 뒤 DB 의 `observations` · `children` 에 행이 생긴다 — 목업이 아니라 실제 API 를 탔다.
- **[실측]** Next 의 `rewrites()` 는 빌드 때 `.next/routes-manifest.json` 에 박힌다.
  `FASTAPI_BASE_URL` 은 `next build` 시점에 있어야 한다.
- **[실측]** node 22 의 `node --test` 기본 패턴은 `*.test.*` · `test/` 등이고 `*.spec.ts` 를
  집지 않는다. Playwright 는 `testDir: "e2e"` 밖을 보지 않는다.
- **[실측]** `next` 가 `@playwright/test` 를 선택적 peer 로 이미 적어 두었다. 추가되는 패키지는
  `@playwright/test` · `playwright` · `playwright-core` 셋이다.
- **[판단]** 저장소가 public 이라 러너 시간은 무료다. job 은 대략 5~7분으로 본다(실측 아님).

## 대안

- **Cypress** — 바이너리가 크고 기본이 Electron 이다. 여러 탭·출처 제약이 있고, 지금 원하는 것은
  흐름 하나라 장점이 없다. 기각.
- **node:test + fetch 로 API 만 연쇄 호출** — 화면이 실제 API 를 타는지가 목적인데 화면을 건너뛴다. 기각.
- **docker compose 로 전체를 띄우기** — `.env` 없이 보간에서 죽는다(ADR-011). nginx·certbot 까지
  뜬다. 기각. 운영의 nginx 경로(`/api` 분기)는 이 job 이 보지 않는다.
- **Playwright `webServer` 로 Next 를 띄우기** — DB·백엔드는 못 띄워 어차피 밖에서 세워야 한다.
  로컬과 CI 를 같은 방식(띄워 둔 서버에 붙기)으로 맞췄다.
- **firefox · webkit 까지** — 설치 시간이 늘고, 지금 잡으려는 것은 브라우저 차이가 아니다. 보류.

## 결과

- 화면이나 API 를 고쳐 이 흐름이 깨지면 PR 이 빨갛게 된다. 화면 문구(라벨·버튼 이름)를 바꾸면
  `e2e/first-record.spec.ts` 도 같이 고친다 — 셀렉터가 한국어 라벨이다.
- 실패하면 Playwright 리포트·trace 와 백엔드·Next 로그가 artifact `e2e-report` 로 남는다.
- 브랜치 보호의 required checks 에 `e2e (playwright)` 를 넣을지는 별도로 정한다.
