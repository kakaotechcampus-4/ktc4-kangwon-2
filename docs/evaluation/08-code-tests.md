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
| 2026-11-07 | 기관 근거 파일(14MB)을 요청마다 다시 읽지 않고 프로세스당 한 번만 읽는다 | `backend (pytest)` 잡 692초 → 398 · 374초 · CI 전체 820초 → 413 · 735초 | PR #425 |

- 「전」은 최근 초록 CI 12회의 중앙값, 「후」는 PR #425 의 CI 2회(run 42353030368 · 42353547619)다
- 2회차 CI 전체 735초에는 러너가 잡을 늦게 잡은 대기 약 4분이 들어 있다
- 지금 가장 늦게 끝나는 잡은 `e2e (playwright)`(404 · 507초)다. pytest 를 더 줄여도 CI 전체는 거의 안 줄어든다

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

## 규칙

- 구현이 하나뿐인 인터페이스는 안 만든다 — [CLAUDE.md](../../CLAUDE.md) §일하는 방식 ②
- **건드린 것만 건드린다.** 리뷰어가 diff 에서 본론을 찾을 수 있어야 한다 — ③
- PR 500줄 내외로 쪼갠다

## 아직 아닌 것

- 커버리지를 재지 않는다
- 프런트 테스트가 가짜 `useState` 하네스라 실제 렌더 경로를 전부 안 지난다

## 더 모을 근거

- [x] `pytest` 통과 건수(파일 수 아님) — 위 「통과 건수」
- [x] CI 평균 소요 시간 — 8.8분
