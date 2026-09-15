# ADR-011: CI 가 검증하는 범위를 정한다

- 날짜: 2026-09-15
- 상태 — 채택

## 맥락

기존 CI 는 Ruff, Alembic 정합성, frontend 린트·빌드를 검증하지만 pytest 와
backend 이미지 빌드는 실행하지 않는다. 파서의 `_selfcheck()` 는 사람이 직접
실행해야 하고, Dockerfile 문제는 서버 배포 때 처음 드러난다.

기능을 바꾸지 않고 PR 마다 테스트와 이미지 빌드를 독립적으로 확인할 범위를 정한다.

## 결정

1. 기존 job 과 합치지 않고 `backend (pytest)` 와 `backend (docker build)` job 을
   추가한다. 기존 세 job 은 유지한다.
2. pytest job 에 postgres 서비스를 띄운다. `/health/ready` 의 200 을 실제 DB 로
   검증하고, 503 은 `SessionLocal` 을 모의해서 검증한다.
3. 이미지는 `docker compose build` 가 아니라 `docker build ./backend` 로 빌드하고
   컨테이너에서 `import app.main` 까지 확인한다.
4. frontend 이미지는 빌드하지 않고, 빌드 캐시는 후속 PR 로 분리한다.
5. 테스트 의존성으로 `pytest` 와 `TestClient` 실행에 필요한 `httpx` 를 dev extra 에
   추가한다.

## 근거

- **[실측]** SQLAlchemy 의 `create_engine` 은 커넥션을 열지 않고 dialect 만
  로드한다. 못 붙는 `DATABASE_URL` 로도 import 는 통과하고, `SessionLocal()` 뒤
  `execute` 시점에 연결이 실패한다.
- **[실측]** `docker compose config` 는 `POSTGRES_PASSWORD` 없이 보간 단계에서
  실패한다. `docker compose build` 도 같은 보간 경로를 탄다.
- **[실측]** `frontend/Dockerfile` 은 `npm ci` 와 `npm run build` 를 실행해 기존
  frontend job 과 실행 내용이 같다.
- **[실측]** `backend/app/shared/` 의 여섯 도구 영역에는 내용 있는 구현이 없다.
  다섯 디렉터리는 0바이트 `__init__.py`, `childCode` 는 0바이트 `.gitkeep` 만 있고
  repository·service 가 없다. 지금 테스트할 DB 로직이 없다.
- **[실측]** 한 job 안의 step 은 앞 step 이 실패하면 뒤 step 이 건너뛰어진다.
  저장소가 public 이라 GitHub Actions 러너 분은 무료다.
- **[판단]** 독립 job 두 개가 린트 실패와 무관하게 테스트와 이미지 빌드 결과를
  모두 보여 주므로 실패 원인을 한 번에 확인하기 쉽다.
- **[실측]** 실패를 흉내내는 모의가 성공을 흉내내는 모의보다 짧다. `SessionLocal`
  이 터지게 만드는 데는 3줄이면 되지만, 성공을 흉내내려면 `__enter__` ·
  `__exit__` · `execute` 를 갖춘 객체가 필요해 5줄이 든다. postgres 를 띄우면
  200 은 모의 없이, 503 은 3줄로 — 둘 다 검증된다.
- **[실측]** `main.py` docstring 과 `CLAUDE.md` 는 배포 판정을 `/health/ready` 로
  정해뒀는데 `deploy.yml` 은 `/health` 를 보고 있었다. 배포 판정이 DB 를 안 보는
  상태였다. 이 PR 에서 맞췄다.

## 대안

- **pytest 를 기존 backend job 에 추가** — 앞의 Ruff 가 실패하면 pytest 가
  실행되지 않아 테스트 결과를 볼 수 없으므로 기각했다.
- **postgres 없이 503 만 검증** — DB 없이도 `create_engine` 이 연결을 열지 않아
  503 분기가 모의 없이 돈다. 그러나 배포 판정이 보는 200 을 CI 가 한 번도 밟지
  않게 되고, 엔드포인트가 "항상 503" 이 되는 버그를 잡지 못한다. 기각했다.
- **`docker compose build` 로 두 이미지 빌드** — `.env` 없는 CI 에서 보간이
  실패하고 frontend 검증을 중복하므로 기각했다.
- **Dockerfile 레이어 수정과 buildx/gha 캐시 추가** — 배포 경로를 건드리므로
  이번 변경에서 분리했다.

## 결과

- CI 는 기존 세 job 과 신규 두 job 을 서로 막지 않고 실행한다.
- **로컬에서 `pytest` 를 돌리려면 DB 가 필요하다.** `conftest.py` 가
  `DATABASE_URL` 을 요구한다. `docker compose up -d db` 후 환경변수를 주고 돌린다.
  없으면 무엇을 하라는지 알려주고 죽는다.
- 브랜치 보호의 required checks 에 `backend (pytest)` 와
  `backend (docker build)` 를 추가해야 한다. 이는 별도 작업이다.
- 빌드 캐시는 Dockerfile 레이어 순서 수정과 세트로 후속 PR 에서 다룬다.
