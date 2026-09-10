# 디렉터리 구조

어느 디렉터리에 무엇을 두는지 정리한다.

트리 전체를 보려면:

```bash
tree -a --dirsfirst -I '.git|node_modules|.next|.ruff_cache'
```

## 최상위

| 경로 | 무엇을 두는가 |
|---|---|
| `backend/` | FastAPI 애플리케이션. Python 코드는 전부 여기 |
| `frontend/` | Next.js 애플리케이션 (App Router, TypeScript) |
| `docs/` | 팀 문서 |
| `.github/` | PR 템플릿과 GitHub Actions |

### 루트 파일

| 파일 | 무엇을 두는가 |
|---|---|
| `docker-compose.yml` | db · backend · frontend 3개 서비스 |
| `.env.example` | 환경변수 예시. 실제 `.env` 는 커밋하지 않는다 |
| `.gitignore` | 무시 목록. 비밀값 패턴이 들어 있어 함부로 지우지 않는다 |
| `README.md` | 실행 방법과 문서 링크 |
| `CLAUDE.md` | AI 도구용 프로젝트 규칙 요약 |

새 최상위 디렉터리는 팀 합의 후에 만든다.

---

## backend

### 루트 파일

| 파일 | 무엇을 두는가 | 언제 고치는가 |
|---|---|---|
| `pyproject.toml` | 의존성과 Ruff 설정 | 패키지를 추가하거나 린트 규칙을 바꿀 때 |
| `Dockerfile` | backend 이미지 빌드 | 시스템 패키지나 실행 명령이 바뀔 때 |
| `.dockerignore` | 이미지에 넣지 않을 것 | 새 캐시·산출물 디렉터리가 생길 때 |
| `alembic.ini` | Alembic 설정. **DB URL 을 여기 적지 않는다** | 파일 이름 규칙을 바꿀 때 |

`alembic.ini` 는 `backend/` 바로 아래에 있다. `backend/alembic/` **안이 아니라 옆**이다.

---

## backend/app

```
app/
├─ config.py  db.py  main.py     배선
├─ features/                     기능별 소유 영역
└─ shared/                       여러 기능이 함께 쓰는 도구
```

### 직하 파일

| 파일 | 무엇을 두는가 | 언제 고치는가 |
|---|---|---|
| `main.py` | FastAPI 앱 생성, `GET /health` | feature router 를 연결할 때 |
| `config.py` | `.env`·환경변수 로드 (pydantic-settings) | 새 설정값을 추가할 때 |
| `db.py` | `Base` · `engine` · `SessionLocal` · `get_session` | 세션 정책이 바뀔 때 |

모든 모델은 `db.py` 의 `Base` 를 상속한다. `shared/db` 를 따로 만들지 않는다.

---

## backend/app/features — 기능별 소유 영역

| 폴더 | 소유 데이터 |
|---|---|
| `centers` | 원 · 반 · 아동 명단 · 성품인사 |
| `activities` | 활동 풀 |
| `plans` | 연간 · 월간 · 주간 계획안 |
| `forms` | 없음 (hwp 양식 파싱, DB 미사용) |
| `trends` | 트렌드 소재 · 승인 큐 |

### 규칙

**한 feature 는 다른 feature 를 직접 import 하지 않는다.** 다른 기능의 데이터가
필요하면 그 소유자의 service 를 통한다.

**파일을 미리 만들어 두지 않는다.** 지금 각 폴더에는 `__init__.py` 하나뿐이다.
아래 파일은 필요해진 사람이 그때 추가한다.

| 파일 | 언제 만드는가 |
|---|---|
| `router.py` | HTTP 엔드포인트를 노출할 때 |
| `schemas.py` | 요청·응답 모델이 필요할 때 |
| `service.py` | 로직이 router 에 담기 어려울 때 |
| `models.py` | DB 테이블이 필요할 때 |
| `repository.py` | 쿼리가 service 에 담기 어려울 때 |
| `dependencies.py` | 이 feature 전용 FastAPI 의존성이 필요할 때 |
| `exceptions.py` | 이 feature 전용 예외가 필요할 때 |

**feature 마다 구성이 달라도 된다.** DB 를 쓰지 않는 feature 에 `models.py` 가 없어도
되고, 외부 API 가 없는 feature 에 `router.py` 가 없어도 된다.

`router.py` 를 만들었으면 `main.py` 에서 `app.include_router(...)` 로 연결한다.

---

## backend/app/shared — 여러 기능이 함께 쓰는 도구

| 폴더 | 무엇을 두는가 |
|---|---|
| `llm` | LLM 호출 래퍼 |
| `gates` | 검증 — 스키마 게이트 · 추출 대조 · LLM Judge |
| `citation` | 칸 단위 출처 기록 (`TEMPLATE` / `TREND` / `AI`) |
| `auth` | 인증 |
| `audit` | 변경 이력 |
| `childCode` | 아동 실명 ↔ 코드 치환 |

`childCode` 를 뺀 5개는 빈 `__init__.py` 만 있는 상태다. 구현은 각 담당자가 채운다.

### 규칙

**여기에 두는 기준은 둘 이상의 feature 가 실제로 쓰는가이다.** 한 feature 만 쓰는
코드는 그 feature 안에 둔다. 두 번째 사용처가 생기면 그때 옮긴다.

**테이블을 두지 않는다.** `models.py` · `repository.py` 는 `shared` 에 만들지 않는다.
DB 테이블이 필요한 것은 소유자를 정해 `features/` 에 둔다.

`childCode` 는 아직 `.gitkeep` 만 있고 `__init__.py` 가 없다. 파이썬 패키지가 아니다.
구현할 때 `__init__.py` 를 만들어 패키지로 바꾼다.

---

## backend/resources — 데이터 파일

**네 폴더 모두 아직 비어 있다(`.gitkeep` 만 있음).** 아래는 각 폴더가 받을 데이터다.

| 폴더 | 무엇을 두는가 |
|---|---|
| `activities` | 활동 풀 |
| `calendars` | 달력 |
| `curriculum` | 누리과정 5영역 준거표 |
| `rules` | 법정 로테이션 규칙 |

JSON · YAML 로 둔다. **이런 데이터를 코드에 하드코딩하지 않는다.**

`backend/Dockerfile` 이 `COPY resources ./resources` 로 이미지에 넣는다.
따라서 **파일을 고치면 이미지를 다시 빌드해야 반영된다.**

---

## backend/alembic — DB 마이그레이션

| 경로 | 무엇을 두는가 |
|---|---|
| `env.py` | 모델 목록 연결. `DATABASE_URL` 을 환경변수에서 읽는다 |
| `versions/` | 마이그레이션 파일. 아직 비어 있다(`.gitkeep` 만 있음) |
| `script.py.mako` | 마이그레이션 파일 템플릿 |

설정 파일 `alembic.ini` 는 이 폴더가 아니라 `backend/` 바로 아래에 있다.

### models.py 를 만들면 env.py 도 같이 고친다

`env.py` 에는 지금 `Base` 만 연결돼 있다. 새 `models.py` 를 만들면 **같은 PR 에서**
import 한 줄을 추가한다.

```python
from app.features.centers import models as _centers  # noqa: F401
```

자동 스캔을 쓰지 않는다. **이 줄을 빠뜨리면 `--autogenerate` 가 해당 테이블을
"코드에 없다"고 판단해 `DROP TABLE` 마이그레이션을 만든다.**

### 마이그레이션 생성 절차

`--autogenerate` 는 라이브 DB 와 비교하므로 먼저 `docker compose up -d db` 로 db 를
띄운다. 위의 `env.py` 모델 import 도 빠뜨리지 않는다.

```bash
# 레포 루트에서 실행한다. backend/ 안에서 실행하면 alembic.ini not found 로 실패한다
docker compose run --rm -v "$(pwd)/backend:/app" backend \
  alembic revision --autogenerate -m "add centers table"

docker compose run --rm -v "$(pwd)/backend:/app" backend alembic upgrade head
docker compose run --rm -v "$(pwd)/backend:/app" backend alembic downgrade -1
docker compose run --rm -v "$(pwd)/backend:/app" backend alembic check
```

일회성 컨테이너에 `-v` 로 호스트의 `backend/` 를 마운트하므로 생성 파일이
호스트의 `backend/alembic/versions/` 에 남는다. Linux 는 컨테이너가 root 로 돌아
생성 파일이 root 소유가 될 수 있으니 `--user "$(id -u):$(id -g)"` 를 붙인다
(macOS 에서만 실측했다. Linux 는 확인이 필요하다).

**생성된 파일을 열어서 확인한다.** 의도한 `op.create_table` 이 다 있고 없어야 할
`op.drop_table` 이 없는지, `downgrade()` 가 비어 있지 않은지 본다. 위의 import 를
빠뜨리면 빈 `upgrade()` 가 정상처럼 생성되므로 파일을 봐야 알 수 있다.

**`docker compose exec backend alembic ...` 은 쓰지 않는다.** backend 서비스에는
마운트가 없어 방금 만든 마이그레이션을 못 보고, 그런데도 **아무것도 적용하지 않고
성공한 것처럼 끝난다.**

초기 마이그레이션은 만들지 않았다. 첫 모델을 추가하는 사람이 만든다.

---

## frontend

`create-next-app` 산출물을 그대로 유지하고 4개만 추가했다 —
`Dockerfile` · `.dockerignore` · `.prettierrc.json` · `.prettierignore`.

| 경로 | 무엇을 두는가 |
|---|---|
| `app/layout.tsx` | 전체 페이지를 감싸는 레이아웃 |
| `app/page.tsx` | 루트 경로(`/`) 페이지 |
| `package.json` | 의존성과 `dev` · `build` · `start` · `lint` 스크립트 |
| `package-lock.json` | 버전 고정. **반드시 커밋한다** |
| `next.config.ts` | Next 설정 |
| `tsconfig.json` | TypeScript 설정 |
| `eslint.config.mjs` | ESLint 설정 |
| `.prettierrc.json` | Prettier 설정. CI 가 `--check` 로 검사한다 |
| `Dockerfile` | frontend 이미지 빌드 |

`--empty` 로 만들어 `public/` 과 `globals.css` 가 없다. 필요해지면 그때 만든다.

`next-env.d.ts` 는 커밋하지 않는다. Next 가 자동 생성한다.

---

## .github

### 팀이 관리하는 파일

| 파일 | 무엇을 하는가 |
|---|---|
| `.github/workflows/ci.yml` | PR 마다 Ruff · ESLint · Prettier · `next build` |
| `.github/workflows/deploy.yml` | `main` push 시 배포. 아직 골격만 |
| `.github/pull_request_template.md` | PR 템플릿 |

이 세 파일과 새로 추가하는 워크플로는 팀이 자유롭게 고쳐도 된다.

### 운영진 소유 파일 — 수정·삭제 금지

| 파일 | 무엇을 하는가 | 지우면 |
|---|---|---|
| `.github/workflows/assign-mentor.yml` | `develop` → `main` PR 에 멘토 자동 지정 | 멘토가 안 붙어 리뷰가 시작되지 않는다 |
| `.github/workflows/notify-discord.yml` | PR 상황을 Discord 로 알림 | 알림이 오지 않는다 |
| `.github/workflows/convention-check.yml` | `develop` → `main` PR 의 컨벤션 이탈을 안내(차단하지 않음) | 안내 코멘트가 달리지 않는다 |
| `.github/CODEOWNERS` | 위 세 파일을 건드리면 운영진 리뷰를 요구 | 보호가 풀린다 |

---

## 실행

```bash
docker compose up -d
curl -f http://localhost:8000/health
```

`.env.example` 의 `DATABASE_URL` 호스트는 `db` 다.
Docker 밖에서 uvicorn 을 직접 띄우면 `localhost` 로 바꾼다.
