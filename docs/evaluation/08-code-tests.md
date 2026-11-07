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
