# 디렉터리 구조

어느 디렉터리에 무엇을 두는지 정리한다.

트리 전체를 보려면:

```bash
tree -a --dirsfirst -I '.git|node_modules|.next|.ruff_cache'
```

## 최상위

| 경로 | 무엇을 두는가 |
|---|---|
| `backend/` | FastAPI 애플리케이션 |
| `p0-planning/` | 계획안 엔진(Python 패키지). 규칙과 근거 자료(`data/`). `backend` 이미지에 같이 설치된다. 이 안에서는 `p0-planning/CLAUDE.md` 가 우선한다 |
| `frontend/` | Next.js 애플리케이션 (App Router, TypeScript) |
| `nginx/` | nginx 설정 (`nginx.conf` · `app-routes.conf`) |
| `scripts/` | 서버 배포 · 백업 · 점검 셸 스크립트 |
| `docs/` | 팀 문서 |
| `.github/` | PR 템플릿과 GitHub Actions |

### 루트 파일

| 파일 | 무엇을 두는가 |
|---|---|
| `docker-compose.yml` | db · backend · frontend · nginx · certbot 5개 서비스 |
| `docker-compose.server.yml` | 운영 서버에서만 붙이는 덧칠 — backend 로그를 journald 로(ADR-058) |
| `.env.example` | 환경변수 예시. 실제 `.env` 는 커밋하지 않는다 |
| `.gitignore` | 무시 목록. 비밀값 패턴이 들어 있어 함부로 지우지 않는다 |
| `README.md` | 서비스 소개, 구조와 폴더, 실행, 테스트, 알려진 제한, 자주 찾는 문서 |
| `CLAUDE.md` | AI 도구용 프로젝트 규칙 요약 |

새 최상위 디렉터리는 팀 합의 후에 만든다.

---

## backend

`tests/` — pytest. `/health/ready` 200 검증에 postgres 가 필요하다.

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
| `auth` | 회원가입 · 로그인 · 카카오 로그인(`users`). 이 라우터만 인증 없이 열린다 |
| `centers` | 원 · 반 · 아동 명단 · 성품인사 · 반 열람 요청 테이블. 정부 어린이집 목록 사본(`registry.py`, ADR-068) |
| `children` | 아동 명단 API. 테이블은 `centers` 의 것을 쓴다 |
| `class_access` | 같은 원 다른 반 열람 요청 · 승인과 반 요약 API(ADR-059). 테이블은 `centers` 의 것 |
| `activities` | 활동 풀 |
| `observations` | 관찰 기록. 생성 API 가 없다 — 교사가 적은 그대로 저장한다 |
| `routines` | 일과 기록 · 일과 초안 · 날씨(ADR-025 · ADR-089). 생성 API 가 없다 |
| `template_profiles` | 월간 양식 설정(TemplateProfile) — 원 기본 · 반 override |
| `plans` | 연간 · 월간 · 주간 계획안. `rules/verify.py` 는 만들어진 계획안을 검사한다(ADR-014) |
| `forms` | 원이 등록한 양식의 파싱 결과 · 원본 저장 · 숨김(ADR-020 · ADR-026). parse 는 저장하지 않는다 |
| `documents` | 일지 · 평가 문서. 다른 기능은 `service.py` 창구로 읽는다 |
| `trends` | 트렌드 소재. 승인은 저장소 파일이고 큐가 아니다(ADR-016) |
| `evaluation` | 평가제 대조 — 라우터 GET · PUT · 판정 규칙 · 지표 카탈로그(resources/evaluation) · 자기 점검 체크 저장(`evaluation_checks`, ADR-022) |
| `notifications` | 상단바 알림함 — 열람 요청이 오고 답이 나온 사건의 화면 안 알림(`notifications`, ADR-097). 다른 기능은 `service.py` 의 `notify` · `mark_request_read` 로만 부른다 |

### 규칙

**다른 feature 의 `router` · `schemas` 는 import 하지 않는다.** 다른 feature 의 `models` 와
함수 모듈(`service` · `planning` 등)은 직접 import 해도 된다([ADR-002](adr/002-features-folder.md) 2026-11-11 개정).

**파일을 미리 만들어 두지 않는다.** `models.py` 는 DB 테이블이 필요해진 feature 에만
있다(`children` · `class_access` · `trends` 에는 없다). 아래 파일은 필요해진 사람이 그때 추가한다.

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
| `llm` | backend 에서 LLM 으로 나가는 유일한 문(`client.py` · `errors.py`). `p0-planning` 은 자기 어댑터를 따로 갖는다 |
| `gates` | 해석형 문서의 3단 게이트 — 스키마 · 추출 대조(`sections.py`), AI 판정(`judge.py`) |
| `auth` | 토큰 · 비밀번호 · 현재 사용자 의존성 · 자기 원/반 소유 검사(`ownership.py`) |
| `childCode` | 아동 실명 ↔ 가명 치환 |
| `citation` | 빈 `__init__.py` 만 있다 |
| `audit` | 빈 `__init__.py` 만 있다 |
| `hwpx.py` | hwpx 내보내기 — 양식 표 칸 글자만 바꾼다(ADR-021). `?format=hwp` 면 그 hwpx 를 `.hwp` 로 바꾼다(ADR-039). 양식 파일은 각 feature 의 `templates/` |
| `hwpx_pdf.py` | 채운 hwpx 를 PDF 로 바꾼다(ADR-061) |
| `school_year.py` | 학년도 계산. 3월 1일에 바뀐다 |

칸의 출처는 `citation` 이 아니라 각 계획안 응답이 두 축으로 따로 적는다. `evidence` 는
무엇을 근거로 썼나(`source_type` · `source_id` · `source_version`), `generation` 은 어떤
방식으로 만들었나(`method` · `rule_id` · `rule_version`)다. **AI(LLM) 는 근거가 아니다** —
LLM 이 쓴 칸은 `generation.method` 가 `RULE_LLM` 일 뿐이다(CLAUDE.md §13). 변경 이력도
`audit` 폴더가 아니라 계획안 feature 의 `/audit` 조회가 낸다.

### 규칙

**여기에 두는 기준은 둘 이상의 feature 가 실제로 쓰는가이다.** 한 feature 만 쓰는
코드는 그 feature 안에 둔다. 두 번째 사용처가 생기면 그때 옮긴다.

**테이블을 두지 않는다.** `models.py` · `repository.py` 는 `shared` 에 만들지 않는다.
DB 테이블이 필요한 것은 소유자를 정해 `features/` 에 둔다.

### `childCode` — 구현됨

```
pool.py         가명 발급.  받침으로 두 묶음 (backend/resources/pseudonyms.yaml)
names.py        등록 이름에서 실제 표기를 뽑는다 (박서준 -> 박서준 · 서준)
allocation.py   등록 전 반 전체 치환표 검증. 이미 발급한 가명은 바꾸지 않는다
substitute.py   NameTable · mask · unmask
```

`mask` 와 `unmask` 가 같은 `NameTable` 을 쓴다. 따로 넘기면 한쪽만 고치는 날이 오고,
그날 실명이 LLM 으로 나간다. 전부 fail-closed 다 — 치환할 수 없으면
`SubstitutionError` 를 내고 호출하는 쪽은 LLM 을 부르지 않는다.

---

## backend/resources — 데이터 파일

| 경로 | 무엇이 있는가 |
|---|---|
| `pseudonyms.yaml` | 아동 가명 풀(`childCode`) |
| `daycares/` | 정부 어린이집 목록 사본 `daycares.csv`(ADR-068) |
| `evaluation/` | 평가제 지표 카탈로그 v1 · v2, 체크리스트 규칙 |
| `forms/` | 양식 칸 이름 매핑 `label_mapping.json` |
| `rules/` | `safety_flags.yaml` |
| `trends/` | 승인 출처 · 위험어 목록, 그림책(`books/`), 수집본(`collected/`) |
| `weather/` | 기상청 격자 `kma_grid.csv` |
| `activities/` · `calendars/` · `curriculum/` | 비어 있다(`.gitkeep` 만 있음) |

계획안 쪽 근거 자료(누리과정 · 활동 · Theme · 규칙 · 양식 등)는 여기가 아니라 `p0-planning/data/` 에 있다.

JSON · YAML · CSV 로 둔다. **이런 데이터를 코드에 하드코딩하지 않는다.**

`backend/Dockerfile` 이 `COPY backend/resources ./resources` 로 이미지에 넣는다.
따라서 **파일을 고치면 이미지를 다시 빌드해야 반영된다.**

---

## backend/alembic — DB 마이그레이션

| 경로 | 무엇을 두는가 |
|---|---|
| `env.py` | 모델 목록 연결. `DATABASE_URL` 을 환경변수에서 읽는다 |
| `versions/` | 마이그레이션 파일. 2026-11-11 기준 57개 |
| `script.py.mako` | 마이그레이션 파일 템플릿 |

설정 파일 `alembic.ini` 는 이 폴더가 아니라 `backend/` 바로 아래에 있다.

### models.py 를 만들면 env.py 도 같이 고친다

`env.py` 에는 지금 `Base` 와 모델 모듈 11개(`models.py` 가 있는 feature 전부)가 연결돼 있다.
새 `models.py` 를 만들면 **같은 PR 에서** import 한 줄을 추가한다.

```python
from app.features.activities import models as _activities  # noqa: F401
from app.features.auth import models as _auth  # noqa: F401
# ... 이하 feature 이름순
```

자동 스캔을 쓰지 않는다. 이 줄을 빠뜨리면 상황에 따라 실패 방향이 다르다.

- **새 모델을 추가할 때 — 빈 마이그레이션이 생긴다.** 메타데이터에도 DB 에도 없으니
  차이가 0 이다. 에러 없이 성공한 것처럼 끝나므로 **생성된 파일을 열어 `create_table`
  이 있는지 확인한다.**
- **이미 적용된 테이블의 import 를 지웠을 때 — `DROP TABLE` 이 생긴다.** DB 에는
  있는데 코드에 없다고 판단한다.

### 마이그레이션 생성 절차

먼저 db 를 띄우고 DB 를 최신 리비전까지 올린다. `--autogenerate` 는 라이브 DB 와
비교하는데, DB 가 뒤처져 있으면 `Target database is not up to date` 로 거부한다.

```bash
docker compose up -d db
# Dockerfile 이나 pyproject.toml 을 고쳤으면 --build 를 붙인다
docker compose run --rm -v "$(pwd)/backend:/app" backend alembic upgrade head
```

그다음 마이그레이션을 만든다. 위의 `env.py` 모델 import 를 빠뜨리지 않는다.

```bash
# 레포 루트에서 실행한다. backend/ 안에서 실행하면 alembic.ini not found 로 실패한다
docker compose run --rm -v "$(pwd)/backend:/app" --user "$(id -u):$(id -g)" backend \
  alembic revision --autogenerate -m "add plans table"
```

일회성 컨테이너에 `-v` 로 호스트의 `backend/` 를 마운트하므로 생성 파일이
호스트의 `backend/alembic/versions/` 에 남는다. `--user` 는 그 파일의 소유자를
실행한 사람으로 맞추기 위한 것이다. `Dockerfile` 이 `USER app`(uid 1000)을 지정하므로
root 소유로 생기지는 않지만, 호스트 uid 가 1000 이 아닌 환경(macOS 는 보통 501)에서는
빼면 소유자가 어긋난다. 서버의 `ubuntu` 가 uid 1000 이라 거기서는 없어도 맞는다.
호스트에 파일을 만드는 명령은 `revision` 뿐이므로 나머지 명령에는 붙이지 않는다.

실측: macOS(uid 501)에서 `--user "$(id -u):$(id -g)"` 로 생성하면 소유자가
실행한 사용자로 찍힌다.

**적용하기 전에 생성된 파일을 열어서 확인한다.** 의도한 `op.create_table` 이 다 있고
없어야 할 `op.drop_table` 이 없는지, `downgrade()` 가 비어 있지 않은지 본다. 위의
import 를 빠뜨리면 `DROP TABLE` 이 들어가므로, 확인 전에 적용하면 `pgdata` 의 테이블이
실제로 지워진다.

확인이 끝나면 적용한다.

```bash
docker compose run --rm -v "$(pwd)/backend:/app" backend alembic upgrade head
docker compose run --rm -v "$(pwd)/backend:/app" backend alembic check
docker compose run --rm -v "$(pwd)/backend:/app" backend alembic downgrade -1   # 되돌릴 때
```

**`docker compose exec backend alembic ...` 은 쓰지 않는다.** backend 서비스에는
마운트가 없어 방금 만든 마이그레이션을 못 보고, 그런데도 **아무것도 적용하지 않고
성공한 것처럼 끝난다.**

초기 마이그레이션 `20260914_1409_979d1991638a_initial_schema.py` 가
`centers` · `classes` · `children` · `activities` 테이블을 만든다.

---

## frontend

| 경로 | 무엇을 두는가 |
|---|---|
| `app/` | 화면. 라우팅 규칙은 `frontend/CLAUDE.md` 「라우팅」 |
| `components/` | 화면 조각. `app/` 아래 폴더 이름과 짝을 맞춘다 |
| `lib/` | 화면이 아닌 것 — API 호출 · 목업 데이터 모델 · 훅 |
| `msw/` | 목업 서버 핸들러. 켜고 끄는 법은 `msw/README.md` |
| `scripts/` | `msw-worker.mjs` — `predev` · `prebuild` 가 불러 `public/mockServiceWorker.js` 를 놓거나 지운다. 이 워커 파일은 커밋하지 않는다 |
| `tests/` | `node --test` 로 도는 테스트 |
| `e2e/` | Playwright 브라우저 테스트. `npm run e2e` 로만 돈다 — 아래 「E2E」 |
| `styles/` | 폰트 `@font-face` 와 디자인 토큰 |
| `public/fonts/` | 서브셋 woff2 |
| `package-lock.json` | 버전 고정. **반드시 커밋한다** |
| `.prettierrc.json` | Prettier 설정. CI 가 `--check` 로 검사한다 |
| `Dockerfile` | frontend 이미지 빌드 |

**루트 경로(`/`)는 `app/(app)/page.tsx` 하나다.** 괄호 폴더는 주소에 안 들어가므로
`app/page.tsx` 를 만들면 같은 주소를 두 파일이 갖게 된다. 만들지 않는다.

`next-env.d.ts` 는 커밋하지 않는다. Next 가 자동 생성한다.

---

## .github

### 팀이 관리하는 파일

| 파일 | 무엇을 하는가 |
|---|---|
| `.github/workflows/ci.yml` | PR 마다 Ruff · pytest · alembic check · backend 이미지 빌드 · ESLint · Prettier · `next build` · E2E |
| `.github/workflows/deploy.yml` | 배포 브랜치(`on.push.branches`)에 push 되면 그 커밋을 SSM 으로 서버에 올린다 · 손 배포 · 롤백 |
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

### E2E

`frontend/e2e/` 는 띄워 둔 서버에 붙기만 한다. DB · 백엔드 · Next 를 먼저 세운다(ADR-028).
CI 의 `e2e (playwright)` job 이 하는 일과 같다.

```bash
docker compose up -d db backend          # LLM_MODE 는 기본 mock 이다
docker compose run --rm -v "$(pwd)/backend:/app" backend alembic upgrade head

cd frontend
# FASTAPI_BASE_URL 은 build 때 박힌다. NEXT_PUBLIC_API_MOCKING 은 비워 둔다(MSW 끔).
FASTAPI_BASE_URL=http://127.0.0.1:8000 npm run build
FASTAPI_BASE_URL=http://127.0.0.1:8000 npm run start -- --hostname 127.0.0.1 --port 3000 &
npx playwright install chromium          # 최초 1회
npm run e2e                              # 다른 포트면 E2E_BASE_URL=http://127.0.0.1:3100
```

실행마다 새 계정을 만든다. 아동 이름은 가명이다 — 개발 DB 에 실명을 넣지 않는다.

`e2e/routines.spec.ts` 는 DB 를 직접 읽어 확인하는 단계가 있다. `E2E_DATABASE_URL` 이
없으면 실패한다. 그 확인에 쓸 Python 은 `E2E_PYTHON` 으로 바꿀 수 있다(기본 `python`).

`npm test` 의 `tests/api-workspace.test.mjs` 4개는 `SAESSAK_TEST_URL` 이 없으면 건너뛴다.
주면 그 주소의 띄워 둔 서버에 HTTP 로 붙는다.

### 문서 재확정

확정본 문서의 근거 비교 · 재확정은 `backend/app/features/documents/review.py` 와 화면
`frontend/components/workspace/SourceReview.tsx` · `document-selection.ts` 가 맡는다(ADR-040).
테이블 `document_reconfirmations` 는 재확정 영수증이고, `document_source_resolutions` 는
**초안** 에서 사라진 근거를 빼거나 바꾼 흔적이다. 둘을 섞지 않는다.
