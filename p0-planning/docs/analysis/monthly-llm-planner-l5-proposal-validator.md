# Monthly LLM Planner vNext — L5 Deterministic Proposal Validator

- 작성일: 2026-09-13
- 선행: L4 GPT-4.1 mini Planner 완료 (`MONTHLY_LLM_PLANNER_L4_COMPLETE`)
- 산출물
  - `src/ssuksak/planning/rules/monthly_llm_validation.py` — Validator · 결과/위반 model
  - `src/ssuksak/planning/rules/monthly_llm_text_policy.py` — 정규화 · 금지 패턴
  - 테스트 `tests/planner/` 3파일 (121건 신규)
- 범위 밖: GenerateMonthlyPlan 통합 · Monthly DRAFT 저장 · Regenerate 통합 ·
  Demo · Golden · Production default 전환

---

## 1. Scope

L4는 "계약 형태의 Proposal이 오는가"까지 보장한다. 그것만으로 저장하면 안 된다.

```text
MonthlyContextPacket + MonthlyPlanProposal
        ↓
validate_monthly_proposal()        ← LLM 호출 없음
        ↓
VALID  또는  결정론적 violation 목록 (+ repairable 여부)
```

L5가 필요한 이유는 추측이 아니라 실측이다. L4 Live Smoke에서 나온
`LLM_SYNTHESIZED` 활동 **2건이 모두** `CONTEXT_ONLY` 근거 문장의 글자 그대로
복사였고, Prompt 강화(v0.1.0 → v0.1.1)로 사라지지 않고 다른 Case로 옮겨 갔다.

---

## 2. LLM을 호출하지 않는다

```text
LLM-as-a-judge          쓰지 않음
semantic grading API    쓰지 않음
embedding API           쓰지 않음
GPT 재검토              쓰지 않음
```

모델에게 자기 출력을 다시 평가시키면 같은 착각을 두 번 한다. L5는 코드로
확인 가능한 사실만 판정한다. 테스트가 Validator 모듈에 Adapter·`openai`·
`FakeLLM`·`plan_monthly(` 문자열이 없음을 고정한다.

---

## 3. 위치와 구조

```text
src/ssuksak/planning/rules/
├── monthly_llm_validation.py    Validator · ProposalViolationCode ·
│                                MonthlyProposalValidationResult · PacketIndex ·
│                                WeekProvenanceDraft
└── monthly_llm_text_policy.py   normalize_for_comparison ·
                                 금지 Claim / Safety 패턴 · 식별자 누출 검사
```

`rules/`에 둔 이유: 입출력이 없고 외부 상태를 읽지 않는 **결정론적 규칙**이다.
Application의 `validate_monthly_plan.py`는 Plan Aggregate와 Repository를 다루는
다른 층이다.

문자열 정책을 분리한 이유: 금지 패턴은 **제품 정책 데이터**라 앞으로 조정된다.
오탐 테스트도 그쪽에 몰려 있어야 한다.

---

## 4. L4 reconcile 재사용 (§4)

중복 구현하지 않았다.

```python
try:
    reconcile_monthly_proposal(...)      # L4 계약: theme/week/REFERENCE/grounding 유무
except MonthlyProposalError as exc:
    fail(BASIC_CONTRACT_VIOLATION, detail=exc.violation.value)
    return                                # 구조가 깨졌으면 여기서 멈춘다
```

L4 위반 11종을 L5 코드로 옮겨 적지 않고 `BASIC_CONTRACT_VIOLATION` 하나로 감싸
`detail`에 원래 식별자를 남긴다. 기존 의미를 바꾸지 않았다.

**구조 위반이면 조기 반환한다.** 주차가 빠진 상태에서 주차별 검사를 계속하면
잡음만 늘고 진짜 원인이 묻힌다.

---

## 5. 핵심 Gate — CONTEXT_ONLY Exact Copy

### 5.1 정규화 (§6)

단순 문자열 비교를 쓰지 않는다.

```python
NFKC 정규화 → 문장부호 제거 → 연속 공백 정규화 → strip → casefold
```

같은 값이 되는 것:

```text
여름 과일 신체 놀이하기
여름 과일  신체 놀이하기
 여름 과일 신체 놀이하기
여름 과일 신체 놀이하기.
여름 과일 신체 놀이하기!
「여름 과일 신체 놀이하기」
```

다른 값으로 남는 것:

```text
여름 과일로 몸을 움직여요
여름 과일 신체 놀이
과일 신체 놀이하기
```

**의미 유사도를 추측하지 않는다.** semantic plagiarism detector를 만들지 않았다
(§6). 코드가 할 수 없는 판단을 하는 척하면 정상 계획안을 막는다.

### 5.2 비교 범위 (§7)

`grounding_refs`에 적힌 근거만 보지 않는다. **Packet이 준 모든 CONTEXT_ONLY
텍스트**와 비교한다.

```text
institution_evidence · other_outdoor_evidence ·
week_experience_candidates · age_contrast_evidence
```

이유: 모델이 `value는 E06을 복사하고 grounding_ref는 E09를 적는` 경우에도
놓치면 안 된다. 테스트가 이 경우를 고정한다
(`test_copy_detection_does_not_depend_on_the_declared_grounding_ref`).

### 5.3 REFERENCE는 대상이 아니다 (§8)

`origin = REFERENCE`이면 승인 Catalog label을 글자 그대로 쓰는 것이 정상이다.
exact-copy 규칙을 적용하지 않는다. 5 Case의 REFERENCE 전량이 오탐 없이 통과한다.

### 5.4 중복 Evidence는 Violation 하나 (§32)

L2가 같은 문장을 여러 record로 담을 수 있다(L4 §14.4의 `E25`/`E26`).
`PacketIndex`가 `정규화 텍스트 → ref 목록`으로 묶으므로 Violation은 하나만
나오고 `detail`에 일치한 ref들이 정렬되어 들어간다.

실측 중복:

| Case | ref 수 | 고유 CONTEXT_ONLY 텍스트 |
|---|---:|---:|
| 2026-03 만3세 | 35 | 30 |
| 2026-06 만4세 | 36 | 36 |
| 2026-07 만4세 | 34 | 31 |
| 2026-08 만4세 | 34 | 33 |
| 2027-02 만5세 | 34 | 32 |

**Evidence Store와 Retrieval을 고치지 않았다**(§32·§37). L2 dedup은 별도 이슈다.

---

## 6. L4 실측 결함 재검증 (§29)

L4 Live Smoke에서 GPT-4.1 mini가 **실제로 반환한 문자열**을 Fixture로 재구성해
검증했다. 지어낸 값이 아니다.

| Prompt | Case | 반환 value | 일치 근거 | 결과 |
|---|---|---|---|---|
| v0.1.0 | 2027-02 만5세 W4 | `내 키만큼 멀리 뛰기` | E14 (institution) | **REJECT** |
| v0.1.1 | 2026-07 만4세 W3 | `여름 과일 신체 놀이하기` | E06 (age contrast) | **REJECT** |

```text
synthesized_activity_copies_source_text_exactly [2026-07-W3]
  (activity.value) 일치한 근거 참조: E06

synthesized_activity_copies_source_text_exactly [2027-02-W4]
  (activity.value) 일치한 근거 참조: E14
```

Fixture가 실제 Packet에 근거하는지도 테스트로 고정했다 — `E06`·`E14`가 실제로
`CONTEXT_ONLY`이고, 해당 문자열이 승인 Catalog에 **없음**을 확인한다.

### 6.1 정상 Proposal은 통과한다 (§30)

Detector가 Synthesized를 통째로 막는 Guard가 되면 안 된다.

```text
2026-07 만4세  W3를 "제철 과일 흉내 내며 몸으로 표현하기"로 바꾼 동일 계획
  → VALID (violations 0)

2027-02 만5세  prompt v0.1.1 실제 결과(전부 REFERENCE)
  → VALID (violations 0, provenance 전량 완성)
```

---

## 7. Reference Integrity (§12)

```text
reference_activity_id가 이번 Packet의 후보 목록에 있는가   REFERENCE_NOT_IN_PACKET
요청 연령을 모두 지원하는가                                REFERENCE_AGE_UNSUPPORTED
value == 승인 label                                        (L4 reconcile이 담당)
```

Catalog에는 있지만 Packet에 주지 않은 Activity를 모델이 쓰면 거부한다.
연령 판정은 `supports_age_set`과 같은 의미(`요청 ⊆ supported_ages`)를 쓴다 —
새 기준을 만들지 않았다.

5 Case 실측에서 Packet의 Reference 후보가 모두 요청 연령을 지원한다(테스트 고정).
L2 hard filter가 이미 보장하지만 저장 직전 defense-in-depth로 다시 본다.

---

## 8. Grounding Integrity (§10·§11·§21)

| 검사 | 코드 |
|---|---|
| Packet에 없는 ref | `INVALID_GROUNDING_REF` |
| 추출 품질이 Grounding 조건 미달 | `INELIGIBLE_GROUNDING` |
| 요청 연령과 무관한 단일연령 근거만 참조 | `GROUNDING_AGE_MISMATCH` |

`INELIGIBLE_GROUNDING`은 Packet 생성 단계에서 이미 걸러지지만 저장 직전에 다시
본다(§11). 5 Case 실측에서 Packet의 근거가 전부 적격임을 테스트로 고정했다 —
평상시에 발동하지 않아야 하는 검사다.

### 8.1 연령 판정의 결정론적 한계

**모든** grounding ref가 요청 연령이 아닌 단일연령 면일 때만 잡는다.
혼합연령·연령 미상 근거가 하나라도 섞이면 판단하지 않는다.

```text
만4세 요청 + grounding 전부 만3세 단일연령 면    → REJECT
만4세 요청 + grounding에 만3~5세 면이 섞임       → 판단하지 않음
```

`age_match_kind`가 아니라 `age_scope`를 직접 본다. 대조 Block의 tier는 문서 안의
연령 기준으로 매겨져 요청 기준이 아니기 때문이다(L3 §6.4와 같은 이유).

---

## 9. 중복 (§13·§14)

```text
같은 reference_activity_id 두 번          DUPLICATE_ACTIVITY
정규화 value가 같음 (origin 무관)          DUPLICATE_ACTIVITY
정규화 experience가 같음                   DUPLICATE_EXPERIENCE
```

origin이 달라도 문구가 같으면 교사에게는 같은 활동이므로 중복으로 본다(§13).

**정규화 완전 일치만 본다.** `여름 자연을 탐색해요`와 `여름의 자연을 살펴봐요`를
같다고 추론하지 않는다(§14). 의미 중복은 후속 Quality Evaluation 영역이다.

---

## 10. 금지 Claim / Safety / 식별자 누출

검사 대상은 **교사에게 보이는 문자열**이다.

```text
activity.value · experience · month_flow_rationale
```

`grounding_refs=["E06"]` 같은 metadata는 대상이 아니다(§17).
`month_flow_rationale`도 빠뜨리지 않는다(§18).

### 10.1 금지 Claim (§15)

14개 패턴을 5개 범주로 둔다.

```text
legal_basis              법적으로 · 법령에 따라 · 법정 기준
mandatory                의무적으로 · 반드시 실시 · 하여야만 합니다
official_recommendation  공식 권장 · 공식적으로 권장 · 국가 기준 · 국가에서 정한
curriculum_authority     누리과정에서 반드시 · 누리과정 기준 순서
standard_order           표준 순서 · 표준 주차
assessment               평가제 통과 기준
```

**`반드시`·`권장`·`기준`·`표준` 한 단어로 막지 않는다.** 오탐 테스트 8건이
이를 고정한다.

```text
통과해야 하는 정상 문장
  아이들이 반드시 즐거워할 놀이입니다
  손을 반드시 씻고 놀이를 시작해요
  교사가 권장하는 방법으로 놀이를 안내합니다
  우리 반 아이들의 관심을 기준으로 배치했습니다
  표준 크기의 공을 사용해 놀이해요
```

### 10.2 Safety 누출 (§16)

Proposal Schema에 Safety 자리가 없어도 자유 문자열에 끼워 넣을 수 있다.

```text
safety_education      안전교육 · 안전 교육 · 법정 안전
statutory_category    (교통안전|생활안전|재난대비|실종·유괴|약물 오남용|
                       성폭력 예방|아동학대 예방|감염병 예방) + (예방|대비|관리)* + (교육|훈련)
drill                 소방/대피/비상대응/지진 훈련 · 심폐소생술
```

**`안전` 한 단어로 막지 않는다.** 오탐 테스트 7건이 고정한다.

```text
통과해야 하는 정상 문장
  안전 약속을 지키며 놀이터를 이용해요
  놀이 기구를 안전하게 사용하는 방법을 이야기 나눠요
  우리 동네 교통기관을 살펴봐요
  교육적인 놀이를 계획했습니다
```

구현 중 `실종·유괴 예방 교육`·`약물 오남용 예방 교육`이 패턴을 빠져나가는 것을
테스트가 잡아, 구분명과 `교육` 사이에 말이 끼는 실제 표기를 흡수하도록 고쳤다.

### 10.3 식별자 누출 (§17)

```text
evidence_ref      E01 형태 참조
source_group      S1 형태 익명 라벨
record_id         ev_<hex>
institution_name  Packet audit의 실제 기관명 (Planner에게 준 적 없는 값)
```

---

## 11. Packet Fingerprint (§23)

```python
if planner_request.packet_fingerprint != packet_fingerprint(packet):
    fail(PACKET_FINGERPRINT_MISMATCH); return
```

**가장 먼저 본다.** 다른 Packet의 Proposal이면 나머지 검사가 전부 무의미하다.
테스트가 조기 반환(violation 1건만)을 고정한다.

---

## 12. Provenance (§22)

저장 전에 필요한 값이 **모두 존재하는지** 확인한다. 저장하지는 않는다.

```text
결과 수준
  planner_model          호출자가 준 모델 문자열
  prompt_version         monthly-planner-prompt-v0.1.1
  packet_fingerprint     검증한 Packet의 값
  generation_method      RULE_LLM
  rule_id                monthly.llm.evidence_grounded_planner
  rule_version           v1
  week_order_basis       PLANNER_COMPOSED      ← OD-N14 확정값

주차 수준 (WeekProvenanceDraft)
  activity_origin
  reference_activity_id           REFERENCE면 필수
  grounding_source_ids            SYNTHESIZED면 필수.
                                  ref를 Packet audit으로 되짚은 실제 record_id
```

`week_order_basis`가 언제나 `PLANNER_COMPOSED`인 이유: Corpus에 주차 순서 근거가
없다(L1 실측 `week_position` 보유 0건). `SOURCE_OBSERVED`로 표기하지 않는다.

실측 확인: 합성 활동의 `grounding_refs`가 실제 record_id로 해석된다.

```text
grounding_source_ids = ('ev_07445576ea19_p01_r00411_c258_i01',
                        'ev_4cc8957046c4_p01_r00625_c01_i01')
```

---

## 13. 결과 Contract (§24)

boolean 하나로 돌려주지 않는다.

```python
MonthlyProposalValidationResult
    is_valid · violations[] · provenance[]
    planner_model · prompt_version · packet_fingerprint
    generation_method · rule_id · rule_version · week_order_basis
    codes · repairable_violations · is_repairable · repair_summary

ProposalViolation
    code · field · detail · week_id
    is_repairable · repair_hint
```

`detail`에 **원문 Evidence · 기관명 · 비밀정보를 넣지 않는다.** 걸린 범주와
참조 id만 남긴다. `find_official_claims()`가 매칭된 문장 조각이 아니라 **범주
이름**을 돌려주는 것이 그 지점이다. 테스트가 detail과 repair hint에 원문이
없음을 고정한다.

---

## 14. Reject 의미 (§26)

하나라도 걸리면 **Proposal 전체를 거부한다.** 일부 Week만 저장하지 않는다.
Monthly는 Planner 호출 하나의 결과이고, 절반만 맞는 계획안은 절반만 틀린
계획안이다.

---

## 15. Repairability (§27·§28)

15종 중 12종이 `repairable`이다.

```text
repairable — 모델이 다시 써서 고칠 수 있다
  BASIC_CONTRACT_VIOLATION · SYNTHESIZED_EXACT_SOURCE_COPY
  DUPLICATE_ACTIVITY · DUPLICATE_EXPERIENCE
  FORBIDDEN_OFFICIAL_CLAIM · SAFETY_CONTENT_LEAKAGE · SOURCE_IDENTIFIER_LEAKAGE
  ORIGIN_NOT_ALLOWED · REFERENCE_NOT_IN_PACKET · REFERENCE_AGE_UNSUPPORTED
  INVALID_GROUNDING_REF · GROUNDING_AGE_MISMATCH

NOT repairable — Context·Packet·설정 문제다. 다시 물어봐야 같은 답이 온다
  PACKET_FINGERPRINT_MISMATCH   다른 Packet의 Proposal이다
  INELIGIBLE_GROUNDING          Packet이 부적격 Evidence를 담고 있다
  PROVENANCE_INCOMPLETE         호출자가 model/prompt metadata를 안 줬다
```

`result.is_repairable`은 **모든** 위반이 고칠 수 있을 때만 True다. 하나라도
Context 문제가 섞이면 재요청이 무의미하다.

`repair_summary`는 범주 수준 문장이며 **원문을 다시 넣지 않는다**(§28).

```text
합성 활동의 이름이 참고 근거 문장과 글자 그대로 같습니다.
같은 놀이 아이디어를 유지하되 표현을 새로 쓰세요.
```

실제 repair orchestration은 L6이 한다. L5는 판정과 분류까지다.

---

## 16. 결정론적 한계 — 하지 않은 것 (§19·§20)

솔직히 기록한다. 코드가 판단할 수 없는 것을 판단하는 척하지 않았다.

| 항목 | L5가 하는 것 | L5가 하지 않는 것 |
|---|---|---|
| Theme 적합성 | `theme_id` 보존 검증 | 활동이 주제에 **의미적으로** 맞는가 |
| 연령 적합성 | REFERENCE의 Catalog 연령 지원, Synthesized의 근거 연령 | 만3세에게 어려운가 |
| 중복 | 정규화 완전 일치 | 의미가 비슷한 중복 |
| 원문 복사 | 정규화 완전 일치 | 바꿔 쓴 표절 |

semantic theme scorer · 일반상식 연령 판단 · similarity 표절 탐지를 만들지
않았다. 이것들은 Retrieval·Planner 품질 또는 후속 Quality Evaluation 영역이다.

---

## 17. Tests

```text
이전   2,080 passed, 4 deselected
현재   2,201 passed, 4 deselected      (+121 신규 · 기존 실패 0 · skip 0)
```

| 파일 | 건수 | 내용 |
|---|---:|---|
| `test_monthly_text_policy.py` | 65 | 정규화 13 · 금지 Claim 14 + **오탐 8** · Safety 11 + **오탐 7** · 식별자 누출 8 |
| `test_monthly_proposal_validator.py` | 42 | 정상 통과 3 · exact copy 9 · REFERENCE 3 · 중복 4 · Claim/Safety/누출 6 · Grounding 4 · fingerprint 2 · provenance 2 · repairability 6 · reject 의미 2 |
| `test_monthly_validator_l4_defects.py` | 14 | **L4 실측 결함 2건** · 정상 통과 · Fixture 근거 확인 · 실제 Packet 위생 |

구현 중 테스트가 두 가지를 잡았다.

1. `실종·유괴 예방 교육` · `약물 오남용 예방 교육`이 Safety 패턴을 빠져나갔다.
   구분명과 `교육` 사이에 `예방`이 끼는 실제 표기를 흡수하도록 고쳤다.
2. `GROUNDING_AGE_MISMATCH` 테스트가 **skip되고 있었다** — Fixture가 만3세 근거를
   Packet에 넣지 못해 규칙이 실제로 검증되지 않았다. 기본 Packet의 연령 대조
   Block에 만3세 근거가 있으므로 그것을 쓰도록 고치고, Fixture가 비면 skip이
   아니라 **실패**하도록 바꿨다. 조용히 넘어가는 검사는 없는 검사와 같다.

성능: `validate_monthly_proposal` 1건 **0.97ms**.

---

## 18. Open Issues

### 18.1 OD-N04 — 닫지 않았다 (§34)

L5는 판정과 `is_repairable` 분류까지만 한다. 실제 repair 루프는 L6이다.

`MAX_REPAIR_ATTEMPTS = 1`이 적절한지에 대한 이번 단계의 근거:

- L4 Live Smoke 3회에서 repair는 **0회** 발생했다. 평상시 경로가 아니다.
- L5가 잡는 12종 중 exact-copy는 **관찰된 Synthesized 2건 모두**에서 발생했다.
  Synthesized가 나오는 Case에서는 repair가 실제로 쓰일 가능성이 높다.
- 따라서 `1`이 충분한지는 **Synthesized 비율이 높은 Case를 L6에서 관측한 뒤**
  판단해야 한다. 지금 수치를 확정하지 않는다.

### 18.2 L2 중복 Evidence — 그대로 둔다 (§32)

2026-07에서 ref 34개 중 고유 CONTEXT_ONLY 텍스트가 31개다. L5는 Violation을
하나로 안정화했고 **Evidence Store·Retrieval을 고치지 않았다.**

### 18.3 Official Adapter 없음 (§33)

`official_claim_allowed = false`이므로 Claim 검사를 그대로 적용한다. Official
Context가 들어오더라도 이 정책 값이 바뀌지 않는 한 Claim을 자동 허용하지 않는다.

### 18.4 같은 월 연령 비교 (§31)

L4 Open Issue를 그대로 둔다. Validator fixture로 연령 계약은 확인했고
**새 Live 호출을 하지 않았다** — 비용을 쓸 이유가 없었다. 동월 만3/4/5세 실제
품질 비교는 L6 또는 Demo 전 별도 Quality Gate로 남긴다.

### 18.5 그대로 둔 것 (§40)

```text
OD-N17                          Age Strength enum 단계 수 (OPEN 유지)
L2 Contrast Pair precision      개선 후보로 기록만
Reference age differentiation   Catalog 성질
Activity v0.2.2                 미착수
```

---

## 19. L6 Readiness

| L6 요구 | L5 제공 |
|---|---|
| 저장해도 되는지 판정 | `is_valid` |
| 왜 안 되는지 | `violations[]` (code · field · week_id · detail) |
| 다시 물어볼 만한가 | `is_repairable` · `repair_summary` |
| Prompt에 붙일 수정 요청 | 범주 수준 문장. 원문 미포함 |
| Plan Item Evidence 재료 | `provenance[]` (origin · reference_id · record_id) |
| Generation Method | `RULE_LLM` · rule_id · rule_version |
| 주차 순서 근거 | `PLANNER_COMPOSED` |
| 재현 | `packet_fingerprint` · `prompt_version` · `planner_model` |

L6이 추가로 맡을 것: Generate 통합 · repair orchestration · DRAFT 저장 ·
Plan Item Evidence 기록 · 실패 시 사용자 노출 정책.

---

## 답변 — §40 필수 질문

**Q1. L4에서 실제 발생한 CONTEXT_ONLY exact-copy 2건을 Validator가 둘 다 잡는가?**
**둘 다 잡는다.** v0.1.0 `내 키만큼 멀리 뛰기`(=E14, 2027-02 W4)와
v0.1.1 `여름 과일 신체 놀이하기`(=E06, 2026-07 W3) 모두
`SYNTHESIZED_EXACT_SOURCE_COPY`로 REJECT된다. GPT-4.1 mini가 실제로 반환한
문자열을 Fixture로 쓰며, `E06`·`E14`가 실제 `CONTEXT_ONLY`이고 승인 Catalog에
없음도 함께 고정했다.

**Q2. REFERENCE label 그대로 사용은 오탐 없이 통과하는가?**
**통과한다.** exact-copy 규칙을 `LLM_SYNTHESIZED`에만 적용한다(§8). 2027-02
v0.1.1의 전부-REFERENCE 계획이 violation 0으로 통과하고, 2026-07의 REFERENCE
4주도 복사·중복으로 걸리지 않는다.

**Q3. 공백·문장부호만 바꾼 Source Copy도 잡는가?**
**잡는다.** NFKC → 문장부호 제거 → 공백 정규화 → casefold를 거친다.
`여름 물놀이  하기` · ` 여름 물놀이 하기 ` · `여름 물놀이 하기.` ·
`「여름 물놀이 하기」` 전부 REJECT된다(테스트 5종).

**Q4. 실제로 새로운 표현의 Synthesized Activity는 통과하는가?**
**통과한다.** `제철 과일 흉내 내며 몸으로 표현하기`로 바꾼 동일 계획이
violation 0으로 통과한다. Detector가 Synthesized를 통째로 막는 Guard가 되지
않음을 별도 테스트로 고정했다(§30).

**Q5. Safety / Official Claim / Source Leakage를 deterministic하게 검출하는가?**
**검출한다.** 금지 Claim 14패턴 5범주, Safety 5패턴 3범주, 식별자 4종.
검사 대상은 `activity.value` · `experience` · `month_flow_rationale`이며
`grounding_refs` metadata는 제외한다. **오탐 테스트 15건**이
`안전 약속을 지키며 놀이터를 이용해요` · `손을 반드시 씻고 놀이를 시작해요` 같은
정상 표현이 막히지 않음을 고정한다.

**Q6. REFERENCE Activity의 age support를 검증하는가?**
**검증한다.** `요청 연령 ⊆ supported_ages`이며 `supports_age_set`과 같은 의미다.
어긋나면 `REFERENCE_AGE_UNSUPPORTED`. 더해 Packet이 준 후보가 아니면
`REFERENCE_NOT_IN_PACKET`으로 막는다 — Catalog에는 있지만 이번에 주지 않은
활동을 모델이 알고 쓰는 것을 거부한다.

**Q7. Synthesized grounding이 요청 연령과 완전히 무관한 경우를 어디까지 검출하는가?**
**모든 grounding ref가 요청 연령이 아닌 단일연령 면일 때만** 잡는다
(`GROUNDING_AGE_MISMATCH`). 혼합연령·연령 미상 근거가 하나라도 섞이면 판단하지
않는다 — 그 이상은 결정론적으로 판단할 수 없다(§21). `age_match_kind`가 아니라
`age_scope`를 직접 보는데, 대조 Block의 tier는 문서 기준이지 요청 기준이 아니기
때문이다.

**Q8. Packet fingerprint mismatch를 막는가?**
**막는다.** 가장 먼저 검사하고 어긋나면 **즉시 반환**한다. 다른 Packet의
Proposal이면 나머지 검사가 무의미하기 때문이며, 조기 반환을 테스트로 고정했다.
`PACKET_FINGERPRINT_MISMATCH`는 **repairable이 아니다.**

**Q9. 어떤 Violation이 repairable인가?**
15종 중 **12종**이 repairable이다(§15 표). 모델이 다시 써서 고칠 수 있는 것 —
exact-copy · 중복 · 금지 Claim · Safety 누출 · 식별자 누출 · 잘못된 ref/reference ·
연령 불일치 · L4 계약 위반. **3종은 아니다** — `PACKET_FINGERPRINT_MISMATCH`
(다른 Packet), `INELIGIBLE_GROUNDING`(Packet 결함),
`PROVENANCE_INCOMPLETE`(호출자 metadata 누락). `is_repairable`은 **모든** 위반이
고칠 수 있을 때만 True다.

**Q10. L6 Generate Integration에서 Validator를 연결할 준비가 되었는가?**
**되었다.** §19 표대로 판정·사유·재요청 가능 여부·Provenance 재료가 모두 구조화된
객체로 준비됐다. 1건 검증에 0.97ms이며 LLM을 호출하지 않는다.

---

```text
MONTHLY LLM PLANNER L5

Validator:
  src/ssuksak/planning/rules/monthly_llm_validation.py
  + monthly_llm_text_policy.py (정규화 · 금지 패턴 · 누출 검사)
  LLM 호출 없음 — LLM-as-a-judge · embedding · semantic grading 전부 미사용
  L4 reconcile을 호출해 재사용. 11종을 옮겨 적지 않았다
  15 violation code · 1건 검증 0.97ms

Exact Copy:
  LLM_SYNTHESIZED에만 적용. REFERENCE는 대상 아님 (§8)
  NFKC → 문장부호 제거 → 공백 정규화 → casefold
  grounding_refs가 아니라 **Packet의 모든 CONTEXT_ONLY 텍스트**와 비교 (§7)
  중복 수록 텍스트가 있어도 Violation은 하나 (§32)
  의미 유사도는 판정하지 않는다 — semantic detector 미구현

L4 Defects:
  v0.1.0  2027-02 W4  "내 키만큼 멀리 뛰기"      = E14  → REJECT
  v0.1.1  2026-07 W3  "여름 과일 신체 놀이하기"  = E06  → REJECT
  실제 GPT 반환 문자열로 Fixture 구성. 둘 다 repairable
  같은 계획을 새 표현으로 바꾸면 통과 (오탐 아님)

Reference Validation:
  이번 Packet의 후보인가 · 요청 연령을 모두 지원하는가
  value == label은 L4 reconcile이 담당 (중복 구현 없음)
  5 Case 실측: Packet 후보 전량이 요청 연령 지원

Grounding Validation:
  Packet 존재 · 추출 적격(defense-in-depth) · 연령 무관 판정
  ref → 실제 record_id 역추적 확인
  5 Case 실측: Packet 근거 전량 적격 · 전량 CONTEXT_ONLY

Duplicate Validation:
  reference_activity_id 중복 · 정규화 value 중복(origin 무관) · experience 중복
  정규화 완전 일치만. 의미 중복은 판정하지 않는다 (§14)

Official / Legal Claims:
  14패턴 5범주. `반드시`·`권장`·`기준`·`표준` 단독으로는 막지 않는다
  오탐 테스트 8건 통과

Safety Leakage:
  5패턴 3범주. `안전` 단독으로는 막지 않는다
  오탐 테스트 7건 통과 ("안전 약속을 지키며 놀이터를 이용해요" 등)
  구현 중 `실종·유괴 예방 교육`이 빠져나가는 것을 테스트가 잡아 수정

Source Leakage:
  evidence_ref(E01) · source_group(S1) · record_id(ev_) · 실제 기관명
  검사 대상은 activity.value · experience · month_flow_rationale
  grounding_refs metadata는 정상이므로 제외

Age Validation:
  REFERENCE  요청 연령 ⊆ supported_ages
  SYNTHESIZED 모든 ref가 요청 외 단일연령일 때만 REJECT
             혼합·연령 미상이 섞이면 판단하지 않는다 (결정론적 한계)

Fingerprint:
  가장 먼저 검사하고 어긋나면 즉시 반환. repairable 아님

Provenance:
  RULE_LLM · monthly.llm.evidence_grounded_planner · v1 · PLANNER_COMPOSED
  주차별 origin · reference_activity_id · grounding_source_ids(실제 record_id)
  값이 빠지면 PROVENANCE_INCOMPLETE. 저장은 하지 않는다

Repairable Violations:
  15종 중 12종. is_repairable은 **모든** 위반이 고칠 수 있을 때만 True
  NOT repairable: PACKET_FINGERPRINT_MISMATCH · INELIGIBLE_GROUNDING
                  · PROVENANCE_INCOMPLETE
  repair_summary는 범주 수준 문장. 원문을 다시 넣지 않는다 (§28)

Regression:
  2,080 → 2,201 passed, 4 deselected  (+121 신규 · 기존 실패 0 · skip 0)
  승인 Artifact 전부 불변 (SHA 확인)
  Prompt v0.1.1 · LLMPort · Elice Adapter · L2 · L3 · Demo · Golden 무변경
  Prompt를 고쳐 exact-copy 문제를 숨기지 않았다

Open Issues:
  OD-N04 미종료 — MAX_REPAIR_ATTEMPTS 근거는 L6 관측 후 판단
  L2 중복 Evidence — Violation만 안정화. Store/Retrieval 무수정
  동월 연령 비교 — 새 Live 호출 없이 남김 (L6 또는 Demo 전 Quality Gate)
  OD-N17 · L2 Contrast precision · Activity v0.2.2 그대로

L6 Readiness:
  READY_FOR_GENERATE_INTEGRATION
```

---

```text
MONTHLY_LLM_PLANNER_L5_COMPLETE
```
