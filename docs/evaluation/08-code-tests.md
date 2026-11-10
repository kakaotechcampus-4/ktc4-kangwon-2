# 08 · 코드와 테스트

**멘토 심사 기준(기술·개발 중심) ⑧ 코드 품질·테스트 — 10점**

> 단위 테스트에 더해 통합·E2E 테스트까지 갖춰 핵심 기능이 자동으로 검증되는가

---

## 숫자 (2026-11-10 기준, 11-04 → 11-10)

| 무엇 | 수 | 세는 법 |
|---|---|---|
| 백엔드 테스트 파일 | 85 → **98** | `ls backend/tests \| grep -c '^test_'` |
| 계획 코어 테스트 파일 | 74 → **78** | `find p0-planning/tests -name 'test_*.py' \| wc -l` |
| 프런트 테스트 파일 | 65 → **71** | `ls frontend/tests/*.test.mjs \| wc -l` |
| E2E 시나리오 파일 | 5 → **8** | `ls frontend/e2e/*.spec.ts \| wc -l` — 무엇을 덮는지는 아래 「화면 경로 E2E」 |
| ADR | 58 → **78** | `ls docs/adr/*.md \| grep -v README \| wc -l` |

**통과 건수 (파일 수 아님)** — develop CI 2026-11-10 (run 42754752760, `e532701b`)

```
backend         1,558 → 1,885 passed
planning core   1,601 → 1,759 passed · 1 skipped · 19 xfailed
frontend          909 →   934 pass · 0 fail
e2e                        35 passed   실제 Postgres · FastAPI · Next 빌드본, MSW 끔, LLM 은 mock
```

놀이 중심형 e2e(`play-plans.spec.ts`)를 더한 PR #518 CI(run 42812595690, `a57875ee`)는 e2e **36 passed** 다.

**CI 한 번 평균 8.8분 → 4.0분** — 최근 완료 25회, 같은 세는 법 (`gh run list --workflow ci.yml --status completed --limit 25`, 시작~끝).
성공한 25회만 보면 평균 4.7분 · 중앙값 5.8분(문서만 바뀐 PR 은 수 초). 줄인 기록은 아래 「CI 시간」.

## CI — PR 마다 6개가 돈다

`.github/workflows/ci.yml`

```
backend (ruff)                 ruff check · ruff format --check
backend (alembic check)        postgres:15 띄우고 upgrade head → alembic check
frontend (eslint·prettier·build)  + 프런트 테스트
backend (pytest)               backend 2단계(real_db · 나머지) + planning core
backend (docker build)         이미지가 앱을 import 하나 · 참조자료를 읽나
e2e (playwright)               실제 DB 로
```

- **머지 커밋 자체도 검사한다.** PR 두 개가 각자 통과해도 합친 결과가 깨질 수 있다 —
  import 두 개가 각자 옳은 위치에 있다가 머지 후 빈 줄이 남은 것이 실제 사례다 (`ci.yml` 머리 주석)
- 같은 PR 에 연달아 push 하면 이전 실행을 취소한다 (`concurrency`)
- E2E 를 CI 에 넣은 이유 — ADR-028
- CI 로 무엇을 검증하고 무엇을 안 하는지 — ADR-011
- 7번째 잡 `backend (rollback compat)` 는 develop 으로 가는 PR 에서 마이그레이션이 바뀔 때만 돈다 — 머지 전 코드가 새 스키마에서도 도나 본다. 아직 필수 검사가 아니다 (`ci.yml:271`)

## 머지 전에 CI 를 통과해야 한다 — develop 규칙 (2026-11-10 부터)

develop 에 **켜진(active) 규칙**이 있다 — ruleset `23517686` 「develop」, 2026-11-10 에 필수 검사를 켰다.
`gh api repos/kakaotechcampus-4/ktc4-kangwon-2/rulesets/23517686` 로 본다.

| 무엇 | 값 |
|---|---|
| 필수 검사 6개 | `backend (alembic check)` · `backend (ruff)` · `backend (pytest)` · `backend (docker build)` · `frontend (eslint · prettier · build)` · `e2e (playwright)` |
| 브랜치를 최신으로 | 요구하지 않는다(non-strict, `strict_required_status_checks_policy: false`) — 머지 커밋은 머지 뒤 develop push CI 가 다시 본다 |
| 그 밖의 규칙 | develop 삭제 금지 · 강제 push 금지 |
| 우회 | 저장소 관리자 역할만(`bypass_actors` RepositoryRole 5) — 운영 장애 같은 급할 때만 쓴다 |

- 문서만 바뀐 PR 은 무거운 잡이 건너뛰어지고(위 「CI 시간」 2026-11-06), 건너뛴 필수 검사는 통과로 친다

**바뀐 기록** — `gh api repos/kakaotechcampus-4/ktc4-kangwon-2/rulesets/23517686/history`

| 언제 | 상태 | 필수 검사 | 최신으로 | 우회 |
|---|---|---|---|---|
| ~ 2026-11-03 | 켜짐 | 5개(e2e 없음) | 요구 | 없음 |
| 2026-11-03 16:45 ~ 11-10 | **꺼짐** — 빨간 CI 로도 머지할 수 있었다 | 〃 | 〃 | 〃 |
| 2026-11-10 21:21 ~ | 켜짐 | 6개(e2e 더함) | 요구 안 함 | 관리자 |

## 통합 테스트 범위 — 백엔드가 진짜 Postgres 를 쓰는 테스트

CI 의 `backend (pytest)` 잡은 `postgres:15` 서비스 컨테이너를 띄우고 그 DB 로 돈다(`ci.yml:204` ~ `:219`).
테스트는 처음 한 번 `alembic upgrade head` 로 스키마를 올리고(`backend/tests/conftest.py:45`),
테스트마다 바깥 트랜잭션을 열어 끝나면 통째로 되돌린다(`db_session`, `conftest.py:61`).
`create_all` 이 아니라 마이그레이션을 쓰므로 마이그레이션이 깨지면 테스트도 깨진다.

**숫자 (2026-11-10, develop `0e02a19c` + 이 PR, `backend/tests/test_*.py` 105개 — 위 「숫자」 표의 98개는 같은 날 앞선 커밋 `e532701b` 기준)**

| 종류 | 파일 수 | 무엇을 지나나 | 예 |
|---|---|---|---|
| API 통합 | **53** | `TestClient` → FastAPI 라우터 · 의존성 → Postgres 15 | `test_documents.py` · `test_routines_db.py` · `test_play_project_export_api.py` |
| DB 통합 (HTTP 없이) | **10** | 저장소 · 쿼리 · 서비스 함수를 같은 Postgres 로. 동시 요청 시험 3개 포함 | `test_plans_repository.py` · `test_reconfirm_concurrency.py` |
| DB 안 씀 | 42 | 규칙 · 코덱 · 한글 파일 채우기 · LLM 가짜 응답 · 운영 스크립트 | `test_gates_sections.py` · `test_plan_rules.py` |

- 표시 — 실 DB 를 쓰는 시험에는 `real_db` 마커가 붙는다. 마이그레이션을 올리는 `_schema` 를 거치는 시험에 `conftest.py` 끝의 훅이 붙이고, 픽스처 없이 앱의 `SessionLocal` 로 붙는 `/health/ready` 한 개는 직접 달았다. **시험 1,236개**(전체 2,021개)가 **파일 63개**에 있다
- CI 는 이 마커로 두 단계로 나눠 돈다 — `pytest — 실 Postgres 통합 (real_db)` 와 `pytest — DB 없는 테스트`(`ci.yml:241` ~ `:247`). 백엔드 두 단계는 앞 단계가 실패해도 뒤 단계가 돌아 실패가 한 번에 보인다
- 세는 법 — `cd backend && DATABASE_URL=… pytest -m real_db --collect-only -q | tail -1`(시험 수, 앞 숫자) · `… | grep :: | cut -d: -f1 | sort -u | wc -l`(파일 수). 그 파일 중 `TestClient` 를 쓰거나 `test_monthly_lifecycle_api` 의 `client` 를 가져다 쓰는 파일(`grep -lE "TestClient|test_monthly_lifecycle_api"`)이 API 통합, 나머지가 DB 통합이다. DB 안 씀은 `test_*.py` 전체(105)에서 63을 뺀 값이다
- e2e 는 따로다 — 같은 `postgres:15` 위에 실제 FastAPI · Next 빌드본을 띄우고 브라우저가 누른다(`ci.yml:378` ~ `:409`, 아래 「화면 경로 E2E」)
- LLM 은 CI 에서 부르지 않는다(가짜 응답). 실제 모델은 운영 서버에서 따로 잰다 — [06 AI 품질](06-ai-quality.md)

## CI 시간 — 줄인 기록

| 날짜 | 바꾼 것 | 전 → 후 | 근거 |
|---|---|---|---|
| 2026-11-06 | 바뀐 곳만 검사 — 문서만 바뀐 PR 은 무거운 잡 6개, 화면만 바뀐 PR 은 backend 잡 4개를 건너뛴다 | 문서만 바뀐 PR: 15분 안팎 → 판정 잡 5초 | PR #397 · 시험 PR #395 |
| 2026-11-07 | 기관 근거 파일(14MB)을 요청마다 다시 읽지 않고 프로세스당 한 번만 읽는다 | `backend (pytest)` 잡 692초 → 약 337초 · CI 전체 820초 → 약 512초 | PR #425 |
| 2026-11-07 | 계획안을 읽을 때 타입 정보를 클래스당 한 번만 풀고, 활동 목록도 한 번만 읽는다 | `backend (pytest)` 잡 약 337초 → 221초 | PR #431 |
| 2026-11-07 | CI 에서 e2e 를 둘씩 동시에, 파일 안 테스트까지 나눠 돌린다 | `e2e (playwright)` 잡 499초 → 274 · 337초 | PR #432 |
| 2026-11-07 | e2e 브라우저 설치에서 apt 를 빼고, 같은 글꼴 9개는 캐시에서 깐다 | 설치 16~23초(92번 중 12번은 2분 넘음, 최대 771초) → 14초 | PR #433 · #434 |

- PR #425 의 「전」은 그 전 초록 CI 12회의 중앙값, 「후」는 그 뒤 CI 8회의 중앙값이다(CI 전체 406~735초.
  735초에는 러너가 잡을 늦게 잡은 대기 약 4분이 들어 있다)
- PR #431 의 「후」는 그 PR 의 CI 1회(run 42377230602)다. CI 전체는 그때 가장 늦게 끝나는
  `e2e (playwright)` 잡(512초)이 정해서 거의 안 줄었다 — pytest 를 더 줄여도 CI 전체는 e2e 를 따라간다
- PR #432 의 「전」은 #425 머지 뒤 CI 6회의 중앙값, 「후」는 PR #432 의 CI 2회(run 42378612447 1 · 2회차)다.
  둘 다 테스트 35개 통과 · 깜빡임 0. 둘씩 돌리기만 하면 가장 긴 `routines.spec.ts` 가 한 워커에 몰려 302 · 431초였다
- #431 · #432 가 같이 든 CI(run 42404310827): `backend (pytest)` 잡 177초 · `e2e (playwright)` 잡 288초 · CI 전체 299초
- PR #433 의 「후」는 캐시가 맞은 CI(run 42397165526 2회차: 브라우저 8초 + 글꼴 6초)다. 캐시가 빈 날은
  apt 를 한 번 타서 지금과 같다(20초). 글꼴을 다른 것으로 바꾸면 `routines.spec.ts:883` 이 390px 에서 깨진다

## CI 시험 기록 — 재 보고 바꾸지 않은 것

**e2e 워커 수 — 2개 유지** (시험 PR #449, 2026-11-09, run 42506084367 1~3회차, 같은 커밋 · 매번 동시에)

| 워커 | playwright 스텝 (1 · 2 · 3회차) | 중앙값 | e2e 잡 중앙값 | 깜빡임 |
|---|---|---|---|---|
| 1 | 389 · 304 · 248초 | 304초 | 430초 | 0 |
| **2 (지금)** | 171 · 245 · 178초 | **178초** | **279초** | 0 |
| 3 | 148 · 242 · 180초 | 180초 | 300초 | 0 |
| 4 | 176 · 235 · 183초 | 183초 | 312초 | 0 |
| 6 | 153 · 247 · 251초 | 247초 | 377초 | 3번 중 2번 — `routines.spec.ts:205` 가 90초 제한에 걸렸다 재시도로 통과 |

- 러너는 CPU 4개이고 같은 러너에서 백엔드(uvicorn 1개) · Next · Postgres 도 돈다. 3 · 4 개의 차이는 회차별 흔들림보다 작다

**e2e 를 도커 이미지 안에서 — 바꾸지 않음** (시험 PR #450, 2026-11-09, run 42510265251 1~3회차, 세 잡 모두 35개 통과)

| 방식 | e2e 잡 중앙값 (1 · 2 · 3회차) | 컨테이너 준비 | 브라우저 · 글꼴 · Python 준비 | 준비 합 |
|---|---|---|---|---|
| **지금, 글꼴 캐시 있음** | 302초 (388 · 256 · 302) | 12~14초 | 12~15초 | **약 27초** |
| 지금, 글꼴 캐시 없음 (apt) | 356초 (406 · 356 · 315) | 12~14초 | 17~23초 | 약 31초 |
| Playwright 공식 이미지 `v1.64.0-noble` | 299초 (320 · 250 · 299) | 38~41초 | 0~1초 | 약 41초 |

- 도커는 브라우저 · 글꼴 설치가 없지만 약 1GB 이미지를 매번 받아 준비가 10~14초 더 걸린다. 잡 전체 차이는 러너마다 흔들리는 테스트 시간(163~258초)보다 작다
- 공식 이미지에는 Python 이 없다. `setup-python` 은 컨테이너 안에서 실패해(`pip` 경로 · ssl) `uv` 로 받았다. 컨테이너 안에서 DB 주소는 `db` 다
- 우리 이미지(우분투 24.04 + Python 3.12 + Node 22 + Chromium, 압축 전 578MB)는 GHCR 에 올리는 것이 막혔다(`denied`, 조직 패키지 권한)
- 다시 꺼낼 때: 러너 우분투 판이 바뀌어 e2e 가 깨지거나 apt 지연이 잦아질 때. 이미지는 develop push 에서만 올리고 Dockerfile 해시로 태그를 붙인다(PR 이 덮어쓰지 못하게)
- 러너에 깔린 Chrome 을 쓰는 안은 #434

## 테스트가 사고에서 나온 것

| 사고 | 남긴 테스트 |
|---|---|
| 한 번 말한 받아쓰기가 네댓 번 적힘 | `frontend/tests/dictation.test.mjs` (3건) |
| 아동 배정 동시 요청 | `test_child_allocation_concurrency.py` |
| 확정 재시도 | `test_documents_reconfirm.py` |
| 백업 스크립트 | `test_backup_script.py` |
| 시간표를 나눈 월간 PDF 에서 두 줄에 걸친 칸의 긴 글이 다른 줄을 덮음 | `test_play_monthly_hwpx.py` `test_a_long_day_over_split_rows_gets_room_in_the_pdf` |
| 화면 문구를 바꿨는데 e2e 가 옛 버튼을 찾아 develop CI 가 빨간불 | `frontend/e2e/mentor-pilot.spec.ts` |
| 휴대폰에서 보육일지 주간 칸 날짜가 넘침 | `frontend/e2e/document-archive-layout.spec.ts` (390 · 375px) |

## 화면 경로 E2E

교사가 누르는 순서대로 브라우저가 누른다. 생성은 API 로 건너뛰지 않고, 저장 · 확정 결과는 서버에서 다시 읽어 본다.
한글 파일은 받은 hwpx 를 열어 본문 · 미리보기에 **교사가 넣은 글**이 있는지 본다(`frontend/e2e/hwpx.ts`) — 모델 문장은 기대값으로 두지 않는다(ADR-023).

| 무엇 | 화면에서 하는 것 | 어디 |
|---|---|---|
| 계획안 연간 → 월간 → 주간 (월별 주제형) | 생성 · 칸 수정 · 새로고침 뒤 유지 · 확정 · 한글 받기 · 보관함에서 다시 열기 | `mentor-pilot.spec.ts:60` · PR #402 |
| 계획안 연간 → 월간 (놀이 중심형) | 생성 · 놀이 고르기(계절마다 5개) · 칸 수정 · 새로고침 뒤 유지 · 확정 · 한글 받기, 월간은 활동 고르기(5 + 5) 뒤 같은 흐름 · 연간에서 고친 놀이를 월간이 이어받음 · 주간 링크 없음(ADR-046 §4) | `play-plans.spec.ts:58` |
| 일일 보육일지 | 일과 입력 → 생성 · 확정 · 한글 받기 · 평가 점검 4-1 에 집계 | `mentor-pilot.spec.ts:284` · `routines.spec.ts:205` |
| 주간 보육일지 | 근거 두 갈래(확정 일일 · 일과 기록) → 생성 · 편집 · 확정 · 한글 받기 | `routines.spec.ts:1056` · PR #427 |
| 관찰일지 | 관찰 기록 → 생성 · 수정 · 확정 · 한글 받기 · 근거를 고치면 바뀐 근거 반영 후 재확정 | `mentor-pilot.spec.ts:340` |
| 일과 기록 · 근거 바뀜 | 7줄 · 드래그 저장 · 401 저장 실패 재시도 · 삭제된 근거 대체 · 제외 · 재확정 | `routines.spec.ts:205~1002` (11개) |
| 가입 · 온보딩 · 첫 기록 | 가입 → 원 · 반 등록 안내 → 첫 관찰 기록 | `first-record.spec.ts:11` |
| 홈 기록 · 두 반 | 홈에서 남긴 관찰이 홈에 그대로 보이고, 반이 둘이면 저장 · 조회 · 뒤로 가기에서 같은 반을 유지한다 | `home-record.spec.ts:134` · `:158` |
| 문서 보관함 | 탐색 · 상태 · 다시 열기 · 키보드 · 화면 4가지 크기 · 실패 · 재시도 | `document-archive-layout` · `-design` · `-card-size` |
| 평가 점검 | 서버의 9개 지표 · 19개 요소 · 체크 보존 | `mentor-pilot.spec.ts:423` |
| 설정 · 반 수정 | 설정 · 기관 양식 · 트렌드봇 진입, 등록한 반 고치기 · 동의 잠금 | `mentor-pilot.spec.ts:456` · `:483` · `:497` |

- 타반 놀이 월간 누락·관찰일지 생성 중 선택 경합·검색 실패와 빈 결과 혼동·기간 이동 뒤 옛 일지 유지에 회귀 검사를 두고, 미저장·저장 실패·이동 취소도 확인한다 — `frontend/tests/cross-review-regressions.test.mjs` · `frontend/tests/routines-server.test.mjs` · `frontend/tests/documents-server.test.mjs`

## 규칙

- 구현이 하나뿐인 인터페이스는 안 만든다 — [CLAUDE.md](../../CLAUDE.md) §일하는 방식 ②
- **건드린 것만 건드린다.** 리뷰어가 diff 에서 본론을 찾을 수 있어야 한다 — ③
- PR 500줄 내외로 쪼갠다

## 아직 아닌 것

- 커버리지를 재지 않는다
- 프런트 테스트가 가짜 `useState` 하네스라 실제 렌더 경로를 전부 안 지난다
- 영유아 평가는 화면 경로 E2E 가 없다. 2026-11-10 부터 만들지 않는다(ADR-091). 올린 평가를 보관함에서 열 길은 아직 없다 — `frontend/components/workspace/DocumentArchiveView.tsx` 의 `ArchiveType` 에 종류가 없음 · 이슈 #496

## 더 모을 근거

- [x] `pytest` 통과 건수(파일 수 아님) — 위 「통과 건수」
- [x] CI 평균 소요 시간 — 8.8분(11/04) → 4.0분(11/10)
