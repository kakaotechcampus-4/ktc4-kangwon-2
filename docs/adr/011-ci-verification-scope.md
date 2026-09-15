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
2. pytest job 에 postgres 서비스를 띄우지 않는다. 현재 DB 테스트가 없고,
   못 붙는 `DATABASE_URL` 로 `/health/ready` 의 503 분기를 모의 없이 검증한다.
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
- **[실측]** `conftest.py` 의 `os.environ["DATABASE_URL"] = ...` 는 대입이라
  CI job 의 `env:` 로 주입한 값을 덮어쓴다. `DATABASE_URL=sqlite://` 를 주고
  `pytest tests/test_health.py` 를 돌려도 503 테스트가 그대로 통과한다.
  같은 URL 로 conftest 없이 `/health/ready` 를 부르면 200 이 나온다.

## 대안

- **pytest 를 기존 backend job 에 추가** — 앞의 Ruff 가 실패하면 pytest 가
  실행되지 않아 테스트 결과를 볼 수 없으므로 기각했다.
- **pytest job 에 postgres service 추가** — 현재 DB 로직이 없어 서비스를 쓸
  테스트가 없다. 게다가 `conftest.py` 가 `DATABASE_URL` 을 덮어쓰므로 서비스를
  붙여도 테스트는 그 DB 를 쓰지 않는다. 실제 DB 테스트가 생기면 job 을
  분리하거나 환경변수 주입 방식을 다시 설계한다.
- **`docker compose build` 로 두 이미지 빌드** — `.env` 없는 CI 에서 보간이
  실패하고 frontend 검증을 중복하므로 기각했다.
- **Dockerfile 레이어 수정과 buildx/gha 캐시 추가** — 배포 경로를 건드리므로
  이번 변경에서 분리했다.

## 결과

- CI 는 기존 세 job 과 신규 두 job 을 서로 막지 않고 실행한다.
- **`conftest.py` 가 `DATABASE_URL` 을 대입으로 덮어쓴다.** 이 job 에
  `services: db` 와 `env: DATABASE_URL` 을 붙여도 conftest 가 덮어써서 그 DB 는
  쓰이지 않는다 — 붙인 사람은 붙었다고 믿는다. 반대로 실제 DB 테스트를 하려고
  그 대입을 지우면 `/health/ready` 503 테스트가 200 을 받아 깨진다.
  둘 중 하나만 바꾸지 않는다.
- 브랜치 보호의 required checks 에 `backend (pytest)` 와
  `backend (docker build)` 를 추가해야 한다. 이는 별도 작업이다.
- 빌드 캐시는 Dockerfile 레이어 순서 수정과 세트로 후속 PR 에서 다룬다.
