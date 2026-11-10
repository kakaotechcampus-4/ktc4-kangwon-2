# 평가 기록 재고 — 추가 호출 0회 (2026-11-10)

11-08~11-10 실측의 응답 · `calls.jsonl` · 서버 로그 · `usage.log` 에서 **추가 호출 없이** 셀 수 있는 것을 모았다. 다시 세는 스크립트: `analysis/quality-eval/measure/eval_inventory.py`(저장소 밖). 숫자만 있고 생성 글 · 기관 정보 · 키는 없다. 11-10 밤에 다시 돌린 10회 재측정(`plan-repeat-after-20261110`)은 끝난 뒤 따로 더한다.

## 1. Provenance 완결성 (생성된 칸 기준)

| 계획안 | 응답 수 | 칸 수 (생성 / 교사 입력 · 빈 칸) | 생성 칸 중 evidence ≥1 | 생성 칸 중 rule_id · rule_version 있음 | 둘 다 | audit 필드 |
|---|---|---|---|---|---|---|
| annual_theme | 10 | 120 / 0 | 120/120 (1.00) | 120/120 (1.00) | 120/120 (1.00) | 없음 |
| monthly_theme | 10 | 210 / 160 | 210/210 (1.00) | 210/210 (1.00) | 210/210 (1.00) | 없음 |
| annual_play | 10 | 1600 / 0 | 400/1600 (0.25) | 1600/1600 (1.00) | 400/1600 (0.25) | 없음 |
| monthly_play | 10 | 580 / 270 | 580/580 (1.00) | 580/580 (1.00) | 580/580 (1.00) | 없음 |
| weekly (11-10 최종) | 29 | 912 / 203 | 680/912 (0.75) | 912/912 (1.00) | 680/912 (0.75) | 없음 |

어디서 셌나 · 한계: 응답 JSON 에서 `evidence` 나 `generation` 키를 가진 dict 를 칸으로 셌다. `generation` 도 `evidence` 도 없는 칸(교사 입력 · 빈 칸)은 따로 셌다. audit 는 응답이 아니라 별도 API(`/audit`)에 있어 여기서는 못 센다. 놀이 연간은 후보의 배움 칸만 CURRICULUM 근거가 있고 놀이 이름 · 재료 · 지원 방향 칸은 evidence 가 없다(LLM 이 만든 값, generation 만 있음).

## 2. Rule / LLM 결정 비율 (한 장당 평균 칸 수)

| 계획안 | RULE_ONLY | RULE_LLM | 그 밖 |
|---|---|---|---|
| annual_theme | 0.0 | 12.0 | — |
| monthly_theme | 5.0 | 16.0 | — |
| annual_play | 0.0 | 160.0 | — |
| monthly_play | 5.0 | 53.0 | — |
| weekly (11-10 최종) | 8.0 | 23.4 | — |

어디서 셌나 · 한계: 1번과 같은 칸의 `generation.method`. 교사가 고친 칸(MANUAL)은 실측에 없다.

## 3. 검증 · 실패 작동 빈도

| 실측 | 요청 수 | 2xx | 4xx | 5xx (code) |
|---|---|---|---|---|
| plan-repeat-20261108 | 89 | 89 | 0 | 0 |
| weekly-repeat-20261108 | 31 | 31 | 0 | 0 |
| weekly-shuffle-live-20261110 | 94 | 93 | 0 | 1 (500 weekly_2026-12-W5) |
| weekly-tier-live-20261110 | 80 | 80 | 0 | 0 |
| weekly-final-live-20261110 | 80 | 80 | 0 | 0 |
| retry-live-20261110 | 없음(calls.jsonl 없음) | | | |

| 실측 (server.log) | LLM 호출 | 고쳐 쓰기 0회 / ≥1회 | 계획안 outcome | llm_call outcome | 검증 코드 |
|---|---|---|---|---|---|
| plan-repeat-20261108 | 없음(배포 서버 실측, 서버 로그 없음) | | | | |
| weekly-repeat-20261108 | 없음(배포 서버 실측, 서버 로그 없음) | | | | |
| weekly-shuffle-live-20261110 | 45 | 32 / 1 | ok 39 · http_500 1 | ok 45 | ACTIVITY_CANDIDATE_INVALID 1 · GENERATION_FAILED 1 |
| weekly-tier-live-20261110 | 35 | 29 / 0 | ok 33 | ok 35 | — |
| weekly-final-live-20261110 | 35 | 29 / 0 | ok 33 | ok 35 | — |
| retry-live-20261110 | 2 | 0 / 0 | http_500 1 · ok 1 | not_delivered 3 · ok 2 | GENERATION_FAILED 1 |

어디서 셌나 · 한계: `calls.jsonl`(요청별 상태)와 로컬 실험 서버 `server.log`. 11-08 두 실측은 배포 서버라 서버 로그가 없다. 「고쳐 쓰기」는 주간 planner 의 `repaired=N` 줄만 있다(연간 · 월간은 같은 줄이 없어 못 셌다).

## 4. 생성 시간 (초, 성공한 생성 요청만)

| 종류 (실측) | 회 | 중앙 | p90 | 최대 |
|---|---|---|---|---|
| annual (weekly-final-live-20261110) | 2 | 20.1 | 20.8 | 20.8 |
| annual (weekly-repeat-20261108) | 1 | 16.3 | 16.3 | 16.3 |
| annual (weekly-shuffle-live-20261110) | 3 | 20.5 | 21.4 | 21.4 |
| annual (weekly-tier-live-20261110) | 2 | 18.4 | 18.9 | 18.9 |
| annual_play (plan-repeat-20261108) | 10 | 149.2 | 157.0 | 160.3 |
| annual_theme (plan-repeat-20261108) | 10 | 13.8 | 14.3 | 14.7 |
| monthly (weekly-final-live-20261110) | 2 | 16.1 | 16.6 | 16.6 |
| monthly (weekly-repeat-20261108) | 1 | 11.6 | 11.6 | 11.6 |
| monthly (weekly-shuffle-live-20261110) | 3 | 16.4 | 19.2 | 19.2 |
| monthly (weekly-tier-live-20261110) | 2 | 17.0 | 19.9 | 19.9 |
| monthly_play (plan-repeat-20261108) | 10 | 35.5 | 35.8 | 36.3 |
| monthly_theme (plan-repeat-20261108) | 10 | 11.2 | 12.6 | 13.6 |
| weekly (weekly-final-live-20261110) | 29 | 26.1 | 29.1 | 31.3 |
| weekly (weekly-repeat-20261108) | 10 | 21.7 | 25.0 | 25.4 |
| weekly (weekly-shuffle-live-20261110) | 33 | 26.9 | 30.7 | 36.8 |
| weekly (weekly-tier-live-20261110) | 29 | 27.2 | 31.1 | 32.2 |

어디서 셌나 · 한계: `calls.jsonl` 의 요청 왕복 시간(클라이언트 기준). 11-08 `annual_play` 는 병렬(#464) 전 순차 4호출이다.

## 5. 토큰 · 비용 (usage.log 가 있는 실측)

| 실측 | 종류 | 호출 | 입력 토큰 중앙 | 출력 토큰 중앙 | 1회 원 중앙 | 합계 원 |
|---|---|---|---|---|---|---|
| plan-repeat-20261108 | 없음(usage.log 없음) | | | | | |
| weekly-repeat-20261108 | 없음(usage.log 없음) | | | | | |
| weekly-shuffle-live-20261110 | annual_theme | 6 | 5,527 | 573 | 24 | 139 |
| weekly-shuffle-live-20261110 | monthly_theme | 3 | 17,125 | 1,489 | 70 | 207 |
| weekly-shuffle-live-20261110 | weekly | 36 | 19,443 | 2,387 | 89 | 3,148 |
| weekly-tier-live-20261110 | annual_theme | 4 | 5,570 | 506 | 23 | 92 |
| weekly-tier-live-20261110 | monthly_theme | 2 | 16,913 | 1,460 | 69 | 137 |
| weekly-tier-live-20261110 | weekly | 29 | 19,412 | 2,415 | 90 | 2,604 |
| weekly-final-live-20261110 | annual_theme | 4 | 5,562 | 529 | 23 | 95 |
| weekly-final-live-20261110 | monthly_theme | 2 | 16,904 | 1,480 | 69 | 138 |
| weekly-final-live-20261110 | weekly | 29 | 19,422 | 2,451 | 90 | 2,594 |
| retry-live-20261110 | annual_theme | 2 | 5,570 | 505 | 23 | 46 |
| **합계** | | | | | | **9,200** |

어디서 셌나 · 한계: `usage.log`(호출별 원, 단가는 `.env.sol`)와 `server.log` 의 `llm_call` 줄을 순서로 맞췄다. 11-08 배포 서버 실측은 usage.log 가 없어 빠졌다(어림은 `analysis/ai-call-baseline-20261108.md`).

## 6. 개인정보 치환 로그

- 서버 로그에서 치환 · 가명화 관련 줄: **0건** — 횟수를 남기는 로그 줄이 없다(치환은 요청 처리 안에서 끝나고 로그를 남기지 않는다). 테스트(ADR-060 · ADR-079)로만 확인된다.
- 11-08 반복 실측은 요청 사항(메모)을 넣고 돌렸지만 배포 서버라 서버 로그가 없다.

## 7. 테스트 규모

| 무엇 | 수 |
|---|---|
| p0-planning 테스트(pytest --co) | 1776 tests collected in 1.50s |
| backend 테스트(`def test_` 수, 어림 — DATABASE_URL 없이는 수집이 안 됨) | 1213 |
| Golden 파일 (`tests/finalization/golden/`) | 9 |
| 고정 SHA (`test_freeze.py`, 승인 Artifact) | 36 |

어디서 셌나 · 한계: `C:\MAIN\P0_WORKTREES\techspec-docs` 작업 트리. backend 는 DB 가 없어 수집 대신 정의 수를 셌다.

## 8. 교사 요청 사항 반영 (11-08, `memo_stats.md` 그대로)

| 계획안 | 회 | 반영 표시(평균) | 반영 못 한 요청(평균) | 요청 낱말이 나온 회 | 낱말별 나온 회 | 요청 문장 그대로 |
|---|---|---|---|---|---|---|
| annual_play | 10 | 0.0 | 0.0 | 10/10 | 블록 10 · 자연물 2 · 낙엽 10 · 열매 1 · 솔방울 5 · 움직 10 · 바깥 2 | 0/10 |
| annual_theme | 10 | 0.0 | 0.0 | 10/10 | 움직 6 · 겨울 10 | 0/10 |
| monthly_play | 10 | 0.0 | 0.0 | 10/10 | 솔방울 0 · 점토 0 · 낙엽 10 | 0/10 |
| monthly_theme | 10 | 0.0 | 0.0 | 10/10 | 낙엽 0 · 바람 10 · 김장 0 | 0/10 |
- 반영 표시 = 응답에서 `memo_applied: true` 인 칸 · 후보 수. 반영 못 한 요청 = `memo_notices` 수.
- 요청 낱말 = 요청 사항의 핵심 낱말이 화면 글(value · name · description · 소주제)에 나온 회수.
- 요청 문장 그대로 = 요청 사항 문장 하나가 글자 그대로 화면 글에 들어간 회수.
