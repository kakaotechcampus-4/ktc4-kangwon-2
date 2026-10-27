# 08 · 코드와 테스트

**기준 원문** — (받은 기준 문장을 그대로 붙인다)

---

## 숫자 (2026-10-28 기준)

| 무엇 | 수 | 세는 법 |
|---|---|---|
| 백엔드 테스트 파일 | 64 | `ls backend/tests \| grep -c '^test_'` |
| 계획 코어 테스트 파일 | 65 | `find p0-planning/tests -name 'test_*.py' \| wc -l` |
| 프런트 테스트 파일 | 39 | `ls frontend/tests/*.test.mjs \| wc -l` |
| E2E 시나리오 | 4 | `frontend/e2e/` — `first-record` · `home-record` · `mentor-pilot` · `routines` |
| ADR | 41 | `ls docs/adr/*.md \| grep -v README \| wc -l` |

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

## 규칙

- 구현이 하나뿐인 인터페이스는 안 만든다 — [CLAUDE.md](../../CLAUDE.md) §일하는 방식 ②
- **건드린 것만 건드린다.** 리뷰어가 diff 에서 본론을 찾을 수 있어야 한다 — ③
- PR 500줄 내외로 쪼갠다

## 아직 아닌 것

- 커버리지를 재지 않는다
- 프런트 테스트가 가짜 `useState` 하네스라 실제 렌더 경로를 전부 안 지난다

## 더 모을 근거

- [ ] `pytest` 통과 건수(파일 수 아님) 한 번 찍어 붙이기
- [ ] CI 평균 소요 시간
