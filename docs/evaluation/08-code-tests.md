# 08 · 코드와 테스트

**멘토 심사 기준(기술·개발 중심) ⑧ 코드 품질·테스트 — 10점**

> 단위 테스트에 더해 통합·E2E 테스트까지 갖춰 핵심 기능이 자동으로 검증되는가

---

## 숫자 (2026-11-04 기준, 10-28 → 11-04)

| 무엇 | 수 | 세는 법 |
|---|---|---|
| 백엔드 테스트 파일 | 64 → **85** | `ls backend/tests \| grep -c '^test_'` |
| 계획 코어 테스트 파일 | 65 → **74** | `find p0-planning/tests -name 'test_*.py' \| wc -l` |
| 프런트 테스트 파일 | 39 → **65** | `ls frontend/tests/*.test.mjs \| wc -l` |
| E2E 시나리오 파일 | 4 → **5** | `frontend/e2e/` — `document-archive-layout` 추가 |
| ADR | 41 → **58** | `ls docs/adr/*.md \| grep -v README \| wc -l` |

**통과 건수 (파일 수 아님)** — CI 2026-11-04 (run 41796637037, PR #373)

```
backend         1,558 passed
planning core   1,601 passed · 1 skipped
frontend          909 pass · 0 fail
```

**CI 한 번 평균 8.8분** — 최근 완료 25회 (`gh run list --workflow ci.yml --status completed --limit 25`, 시작~끝)

## CI — PR 마다 6개가 돈다

`.github/workflows/ci.yml`

```
backend (ruff)                 ruff check · ruff format --check
backend (alembic check)        postgres:15 띄우고 upgrade head → alembic check
frontend (eslint·prettier·build)  + 프런트 테스트
backend (pytest)               backend + planning core 둘 다
backend (docker build)         이미지가 앱을 import 하나 · 참조자료를 읽나
e2e (playwright)               실제 DB 로
```

- **머지 커밋 자체도 검사한다.** PR 두 개가 각자 통과해도 합친 결과가 깨질 수 있다 —
  import 두 개가 각자 옳은 위치에 있다가 머지 후 빈 줄이 남은 것이 실제 사례다 (`ci.yml` 머리 주석)
- 같은 PR 에 연달아 push 하면 이전 실행을 취소한다 (`concurrency`)
- E2E 를 CI 에 넣은 이유 — ADR-028
- CI 로 무엇을 검증하고 무엇을 안 하는지 — ADR-011

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

- 연간 → 월간 → 주간계획안을 API 로 건너뛰지 않고 화면으로 만들고 · 고치고 · 확정해 한글로 받는다 — `frontend/e2e/mentor-pilot.spec.ts` · PR #402
- 주간 보육일지 확정본을 한글로 받아 교사가 고친 글이 파일 안에 있는지 연다 — `frontend/e2e/routines.spec.ts` 「주간 보육일지 — … 한글 다운로드」

## 규칙

- 구현이 하나뿐인 인터페이스는 안 만든다 — [CLAUDE.md](../../CLAUDE.md) §일하는 방식 ②
- **건드린 것만 건드린다.** 리뷰어가 diff 에서 본론을 찾을 수 있어야 한다 — ③
- PR 500줄 내외로 쪼갠다

## 아직 아닌 것

- 커버리지를 재지 않는다
- 프런트 테스트가 가짜 `useState` 하네스라 실제 렌더 경로를 전부 안 지난다
- 영유아 평가 · 놀이 프로젝트형 연간 · 월간은 화면 경로 E2E 가 없다. 영유아 평가는 만든 문서를 보관함에서 열 길부터 없다 — `frontend/components/workspace/DocumentArchiveView.tsx` 의 `ArchiveType` 에 종류가 없음

## 더 모을 근거

- [x] `pytest` 통과 건수(파일 수 아님) — 위 「통과 건수」
- [x] CI 평균 소요 시간 — 8.8분
