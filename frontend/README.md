# frontend

쌤플 교사용 웹 화면이다. Next.js 16.3 (App Router) · React 19.2 · TypeScript · Tailwind CSS 3.4.
Node 22 를 쓴다(`Dockerfile` · CI 와 같다).

서비스 소개와 전체 실행은 [루트 README](../README.md), 폴더 설명은 [docs/structure.md](../docs/structure.md) 「frontend」를 본다.

## 실행

전체 서비스는 루트에서 `docker compose up -d --build` 로 띄우고 **`http://localhost`** 로 연다.
nginx 를 거쳐야 `/api` 가 FastAPI 로 간다(루트 README 「실행」).

화면만 고칠 때:

```bash
cd frontend
npm ci
npm run dev        # http://localhost:3000
```

`next dev` 는 Next 16 기본값인 Turbopack 으로 돈다. `--webpack` 을 붙이지 않는다.

`FASTAPI_BASE_URL` 을 주면 `/api/...` 를 그 주소로 넘긴다(`next.config.ts` rewrite).
`build` 때 값이 박히므로 바꾸면 다시 빌드한다.

## MSW 목업 모드

백엔드 없이 화면을 볼 때 쓴다. `frontend/.env.local` 에 적는다.

```bash
NEXT_PUBLIC_API_MOCKING=enabled
```

- `enabled` 일 때만 켜진다. 비우거나 다른 값이면 꺼진다.
- `predev` · `prebuild` 가 `scripts/msw-worker.mjs` 를 불러 `public/mockServiceWorker.js` 를 놓거나 지운다. 이 파일은 커밋하지 않는다.
- 값을 바꾸면 dev 서버를 다시 띄운다. `NEXT_PUBLIC_*` 는 빌드 때 고정된다.
- 오류 · 지연 재현 쿼리(`mswTarget` · `mswError` 등)와 서버와 다른 점은 [msw/README.md](msw/README.md).

## 검사와 테스트

| 명령                   | 무엇을 하나                       |
| ---------------------- | --------------------------------- |
| `npm run lint`         | ESLint                            |
| `npm run format:check` | Prettier 검사(CI 와 같다)         |
| `npm test`             | `tests/` 를 `node --test` 로 돈다 |
| `npm run e2e`          | `e2e/` 를 Playwright 로 돈다      |

E2E 는 띄워 둔 서버에 붙기만 한다. DB · 백엔드 · Next 를 먼저 세우고 MSW 는 끈다.
기본 주소는 `http://127.0.0.1:3000`, 다르면 `E2E_BASE_URL` 로 바꾼다.
순서는 [docs/structure.md](../docs/structure.md) 「E2E」에 있다.

## 참고 문서

- [docs/screen-spec.md](../docs/screen-spec.md) — 화면 명세
- [docs/api-spec.md](../docs/api-spec.md) — API 계약
- [CLAUDE.md](CLAUDE.md) — 이 폴더의 작업 규칙(라우팅 등)
