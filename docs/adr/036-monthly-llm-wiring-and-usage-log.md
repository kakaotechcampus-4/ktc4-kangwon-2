# ADR-036: 월간 LLM 은 `shared/llm` 한 문으로 나가고, 호출 기록은 그 문에서 한 줄 남긴다

- 2026-10-19 (결정은 2026-10-06 · 2026-10-09)
- 상태 — 채택 (옮겨 적기, PM-13 C · AP-06)
- 보충 — ADR-023
- 관련 — `backend/app/shared/llm/client.py` · `backend/app/features/plans/monthly_llm.py` · `p0-planning/src/ssuksak/adapters/elice_openai_monthly.py`

## 맥락

월간 생성은 Core 의 Planner 가 LLM 을 부른다. Core 와 Backend 중 어디서 공급자 주소 · 키 · mock 여부를 정하는지, 오류를 어떻게 나누는지,
호출 기록을 어디서 남기는지가 개인 결정 문서(12.3 D-2 · 12.9-1)에만 있었다(K-25). 루트 `CLAUDE.md` 「LLM 예산」은 「우리가 세지 않는다 —
카운터 무효」만 적고, 호출 기록(관측 로그)과 차단용 카운터를 구분하지 않았다(K-43).

## 결정

### 1. 배선 (12.3 D-2 = C, 2026-10-06)

```text
GenerateMonthlyPlan / RegenerateMonthlyPlanItem          (Core)
  → MonthlyPlanner — 검증 · 수리 1회                       (Core, ADR-033)
  → MonthlyLlmProvider 포트
  → EliceOpenAiMonthlyAdapter — 요청 모양 · strict json_schema · 응답 해석   (Core)
  → transport = backend/app/shared/llm 의 post_json        (Backend — 주소 · 키 · LLM_MODE · 오류 3종)
  → 엘리스 (gpt-6.1-sol, ADR-023)
```

- **Backend 에서 LLM 으로 나가는 문은 `shared/llm` 하나다.** 연간 · 월간 · 문서가 같은 문을 쓴다.
- Core 어댑터의 strict 스키마는 그대로 쓴다. Backend 가 스키마를 다시 만들지 않는다.
- `LLM_MODE=mock` 이면 엘리스 대신 요청 기반 결정적 provider 를 꽂는다. 연간만 가짜이고 월간만 진짜로 나가는 상태를 만들지 않는다.
- 오류: transport 가 `LlmBudgetExceeded` · `LlmUnavailable` · `LlmFailed` 를 낸다 → Core 가 `monthly_llm_planning_failed`
  (칸이면 `monthly_llm_cell_planning_failed`)로 감싸고 원인을 `__cause__` 에 둔다 → Backend 가 원인을 보고 503 `LLM_BUDGET_EXCEEDED` /
  503 `DEPENDENCY_UNAVAILABLE` / 500 `GENERATION_FAILED` 로 가른다. 공급자 401 · 403 · 429 가 `LlmBudgetExceeded` 다.
- LLM 이 실패하면 가짜 결과로 대체하지 않는다(ADR-033 §3).

### 2. 동기 실행 — 조건부 채택 (D-M4-04 · 12.9-1, 2026-10-09)

- 월간 생성은 동기 201 이다. 비동기 큐 · Job 테이블 · polling 을 만들지 않는다.
- 근거는 실측 3건이다(LLM 10.3 ~ 13.0초, 호출 타임아웃 30초, nginx `proxy_read_timeout 120s`). **표본 3건이라 장기 실패율 · p95 는 모른다.**
- 다시 볼 조건(제안): 호출 시간이 20초를 자주 넘거나, 타임아웃 · 수리가 반복되거나, 동시 생성으로 요청 스레드가 모자라면 비동기를 다시 검토한다.

### 3. 호출 기록 — 차단하지 않고 남긴다 (K-43)

- **차단용 카운터는 두지 않는다**(루트 `CLAUDE.md` 「LLM 예산」, 2026-09-21 무효). 사용량 판단은 사람이 한다.
- **관측용 호출 기록은 남긴다.** `shared/llm/client.py` 의 `post_json` 이 **성공한 호출마다 한 줄** `llm_usage` 를 남긴다 —
  모델 · 입력 토큰 · 출력 토큰 · 합계, 숫자 넷뿐이다. 프롬프트 · 응답 내용은 찍지 않는다(아동 실명이 섞일 수 있다, ADR-004).
- 모델 이름은 보낸 요청(payload)의 값이다. 응답에 usage 가 없으면 남기지 않고 생성은 계속한다.
- 합계는 `scripts/llm-usage.sh` 가 이 줄들을 모아 낸다.
- 월간은 이에 더해 `plans/monthly_llm.py` 가 호출 시간 · 성공 여부를 남긴다. 실패한 칸 재생성은 검증 코드 · 예외 종류만 남긴다.

## 근거

- **[출처]** 사용자 결정 12.3 D-2(2026-10-06), D-M4-04 조건부 채택(2026-10-09, 12.9-1). 원문은 개인 결정 문서, 이 ADR 이 원 ID 를 보존해
  옮긴다(PM-13 C).
- **[실측]** `backend/app/shared/llm/client.py` `post_json` → `_log_usage`(develop `abf97f0`). 연간 · 문서 · 월간이 모두 이 함수를 지난다.
- **[실측]** Luna-6 실측 3건(2026-10-09): 400 없음 · strict 수락 · 수리 0회 · 1건 약 2원.

## 대안

결정 당시 대안(데모용 자체 `.env` 읽기 배선, Backend 가 스키마를 다시 만들기 등)과 기각 이유는 원 결정 기록에 있다.

## 결과

- 루트 `CLAUDE.md` 「LLM 예산」에 「카운터는 무효, 호출당 `llm_usage` 한 줄은 `post_json` 이 남긴다」를 적는다.
- api-spec §9-1 「동기 실행」의 「결정 문서 12.9-1」 인용은 이 ADR 을 가리킨다.
- 남은 것: 실제 Luna-6 + HTTP + PostgreSQL 을 한 번에 지나는 수동 확인, OD-N04 의 남은 부분(재시도 · 최종 실패 정책 수치, 미확정사항 U-13).
