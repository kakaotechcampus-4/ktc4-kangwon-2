# ADR-050: v1 월간에 실내 대체활동 행을 선택 항목으로 둔다

- 날짜: 2026-10-31
- 상태: 제안 — 결정 D-1~D-5 는 하민 확정(2026-10-31). Template v0.2.2 파일은 2026-10-31 하민 승인(`reviewer_ai_lead_001`, D-3). PR 전 번호 중복 확인 필요.
- 보충: ADR-027(v0.1.1 의 `indoor_alternative` 「반복 단위 미결정」을 v0.2.2 에서 `WEEK` 로 정한다). 기존 Template · Profile · 계획은 바꾸지 않는다.

## 맥락

[실측] Template A v0.2.1 의 `indoor_alternative` 는 `repeat_by: null` 인 Template 고유 칸이라 Profile 에 넣을 수 없었다.
주간에는 이미 사람이 승인한 실내 대체활동 분류(`WeeklySemanticClass.INDOOR_ALTERNATIVE`)가 있다.

## 결정

1. **D-1 선택 항목.** 새 Template `monthly-template-a-v0.2.2` 에서 `indoor_alternative` 를 `repeat_by: WEEK` ·
   `category: OPTIONAL` 로 두고, 바깥놀이 바로 아래에 배치한다. v0.2.1 과 그 Profile · 계획은 그대로다 —
   v0.2.1 에서는 계속 `NOT_SUPPORTED` 다.
2. **D-2 주간 분류 재사용.** 근거는 기관 자료 중 주간 분류가 `INDOOR_ALTERNATIVE` 로 정한 기록이고, 연령을 확인할 수
   있는 것만 쓴다. 주간 분류가 지금 자료 묶음의 SHA 와 맞지 않으면 LLM 호출 · 저장 전에
   `evidence_classification_store_mismatch` 로 멈춘다. 쓴 분류 판은 Context lineage 의 `weekly_classification_version`
   에 남긴다. 실내대체가 없는 요청에서는 이 값을 직렬화하지 않아 기존 fingerprint 가 바뀌지 않는다.
3. **D-3 승인.** v0.2.2 는 `PENDING_HUMAN_REVIEW` 로 들어온 뒤, 하민이 완성된 파일을 보고 2026-10-31 승인했다
   (`reviewer_ai_lead_001`). 승인 커밋은 승인 메타데이터만 바꾸고, 내용 SHA 는 `test_freeze.py` 가 그대로 확인한다.
   v0.2.1 의 승인을 물려받은 것이 아니다(ADR-027 §3).
4. **D-4 칸 재생성 없음.** 실내대체 칸은 교사가 직접 고칠 수 있지만 재생성은 이번에 제공하지 않는다.
5. **D-5 근거 없음 = 빈칸.** 그 달 그 연령에 맞는 근거가 없으면 LLM 대상에서 빼고, 행과 주별 빈칸을 남겨 교사가 쓴다.
   근거 없이 생성하지 않는다.

LLM 은 같은 주의 바깥놀이를 실내에서 대신할 활동을 쓴다. 프롬프트 판은 기존 판 뒤에 `+indoor-alternative-v1` 을
붙여 구분하고, 실내대체가 없는 요청의 프롬프트 · 판은 바뀌지 않는다. 생성 방식은 `RULE_LLM`,
근거는 `PARENT_PLAN` + `INSTITUTION_SAMPLE` 이다.

## 하지 않은 것

- 새 공개 API 필드 · DB 변경 없음. `selection` 값이 Template 판에 따라 `OPTIONAL` 이 될 수 있을 뿐이다.
- 날씨 판단 · 「실제로 실내에서 했다」 기록 · 재료 · 공간 보유 단정은 만들지 않는다.
- 화면 mock(MSW)에 v0.2.2 를 추가하는 것은 FE 담당 범위로 남긴다.

## 근거

- `p0-planning/data/templates/monthly_template_a_v0_2_2.json`
- `p0-planning/src/ssuksak/planning/retrieval/retriever.py` · `planning/planner/prompt.py`
- `p0-planning/tests/application/test_monthly_application.py` (실내대체 생성 · 다른 분류 · 모르는 근거 · 분류 결합)
- `backend/tests/test_monthly_lifecycle_api.py` (근거 있음 / 없음 → 편집 → 확정 → 한글 문서)
