# Monthly LLM Planner vNext — L6 GenerateMonthlyPlan Integration

- 작성일: 2026-09-13
- 선행: L5 Deterministic Proposal Validator 완료 (`MONTHLY_LLM_PLANNER_L5_COMPLETE`)
- 산출물
  - `src/ssuksak/planning/application/monthly_llm_planning.py` — Planner 오케스트레이션
  - `GenerateMonthlyPlan` LLM_PLANNER 경로 · `MonthlyGenerationMode`
  - `EvidenceSourceType.INSTITUTION_SAMPLE` Domain 반영
  - 테스트 `tests/application/test_generate_monthly_llm_planner.py` (26건)
  - Live Smoke `analysis/experiments/monthly_llm_vnext/live_application_smoke_l6.py`
- 범위 밖: L7 Regenerate · L8 Demo · L9 Golden/Freeze · Production default 전환 ·
  Activity v0.2.2 · Official Adapter

---

## 1. Scope

Application Use Case에서 처음으로 전 경로가 동작한다.

```text
Confirmed Yearly → Gate → canonical Week → Theme derivation
  → L2 Retrieval → L3 Context Packet → L4 GPT-4.1 mini
  → L5 Validator → (필요 시 repair) → Monthly DRAFT
```

Application Live Smoke 1건 성공(§13). RULE_ONLY 경로는 이전과 완전히 같다.

---

## 2. Generation Modes

```python
class MonthlyGenerationMode(str, Enum):
    RULE_ONLY = "RULE_ONLY"        # 기본값
    LLM_PLANNER = "LLM_PLANNER"
```

**Use Case가 Mode를 고르지 않는다.** `command.generation_mode`가 곧 결정이며,
환경 변수·협력자 유무·LLM 실패를 보고 바꾸지 않는다(§2).

**Production default를 바꾸지 않았다**(§3). `GenerateMonthlyPlanCommand`의
기본값은 `RULE_ONLY`이고, 기존 Demo/Harness Composition은 그대로다.

---

## 3. RULE_ONLY 경로 Freeze

Theme · Week · Outdoor selection · Safety semantics · Cell state · Evidence ·
Generation method · Catalog pin · Audit · Save 동작이 모두 이전과 같다.
Golden 파일을 수정하지 않았고 기존 2,202건이 그대로 통과한다.

### 3.1 Dependency 격리 (§31)

RULE_ONLY는 Evidence Store · Retriever · Context Builder · LLM · L5 Validator를
**한 번도 건드리지 않는다.** `llm_planner`가 주입돼 있어도 마찬가지다.

기존 테스트 `test_use_case_has_no_llm_dependency`는 "주입 지점 자체가 없다"를
검증했는데, L6에서 `llm_planner` 주입 지점이 생기므로 그 전제가 성립하지 않는다.
**테스트를 삭제하지 않고 더 강한 불변으로 바꿨다** —
`test_rule_only_never_uses_the_llm_planner`는 호출하면 예외를 던지는 Planner를
주입한 뒤 RULE_ONLY 생성이 정상 성공하고 `llm_call_count == 0`임을 확인한다.
"주입돼 있어도 쓰지 않는다"가 "주입 지점이 없다"보다 강한 보장이다.

이것은 계약 변경이므로 명시적으로 기록한다.

---

## 4. Preflight Provenance Gate (§4) — 조건부 통과

코드를 쓰기 전에 확인했고, **두 가지가 갈렸다.**

### 4.1 Provenance 자체는 정직하게 표현 가능하다 — 게이트 통과

`experience`에는 grounding ref가 없다. 그래도 과장 없이 표현할 수 있다.

```text
GenerationMethodDetail(RULE_LLM, rule_id, rule_version)   생성 방식
evidence = []                                             인용한 근거 없음
```

Domain은 FILLED Cell에 Evidence를 요구하지 않는다(`theme`만 THEME_REFERENCE +
PARENT_PLAN을 요구). 따라서 "LLM이 구성했고 특정 record를 인용하지 않았다"가
그대로 표현된다.

**금지된 두 가지를 하지 않았다.**

```text
Activity의 grounding_refs를 experience의 Evidence로 복사   하지 않음
Evidence가 없는데 INSTITUTION_SAMPLE이라고 주장             하지 않음
```

### 4.2 그런데 담을 Section이 없다 — §19를 실행할 수 없다

§19는 `week.experience`를 `week_axis`에 Mapping하라고 지시한다. **구조적으로
불가능하다.**

```text
week_axis    role = AXIS
             MonthlySection.__post_init__ → "AXIS Section은 Item을 갖지 않는다"
             ResolvedSection.cell_count_for() → 0
```

`week_axis`는 주차 머리(번호·날짜) 축이지 내용 행이 아니다. 승인 Template A의
활성 CONTENT Section은 `theme` · `outdoor_play` · `safety_education` 셋뿐이다.

의미상 맞는 자리는 `focus`(관측 label `소주제` · `예상 놀이`, WEEKLY_CELLS)지만
`activated: false` · `activation_basis: OPTIONAL_DEFAULT_INACTIVE`다.
활성화하면 ① 승인 Template A를 개정하게 되고 ② RULE_ONLY에도 주차마다 빈
`focus` Cell이 생겨 기존 Golden이 바뀐다(§6 freeze 위반). 구현자가 임의로
정할 사안이 아니다.

### 4.3 판단과 처리

§4의 게이트 조건은 **Provenance 표현 가능 여부**이고 그것은 통과한다. 막힌 것은
§19가 전제한 **Section 배치**이며 이는 Template Source of Truth 결정이다.

따라서 **L6 전체를 BLOCKED로 세우지 않고**, `week.experience`를 Plan Item으로
저장하지 않은 채 나머지를 완성했다. 가짜 Section을 만들지도, `week_axis`에
억지로 넣지도 않았다.

→ **OD-N18 (OPEN)** 등록. 결정 선택지 셋을 함께 기록했다.

이 판단을 뒤집어야 한다면 알려 주십시오. `focus` 활성화는 Template A 개정과
Golden 갱신을 수반하므로 L6에서 혼자 결정하지 않았다.

---

## 5. Generate Flow

```text
 1. Gate            기존과 동일 (설정·연령·Parent CONFIRMED·Template·Safety·Catalog)
 2. Duplicate Gate  기존과 동일
 3. run 생성        generation_mode 기록
 4. Optional Context
 5. canonical WeekPeriod
 6. Template Resolver
 7. lineage
 8. ★ LLM Planner   ← LLM_PLANNER일 때만. Cell을 만들기 전에 Proposal을 확정한다
 9. Cell 생성       outdoor_play만 Proposal에서, 나머지는 기존 Rule
10. Constraint 평가
11. Plan 조립
12. Domain Validation
13. save (한 번)
```

8단계가 실패하면 9단계 이후가 아예 돌지 않는다.

### 5.1 Planner 오케스트레이션

`MonthlyLlmPlanner`가 L2~L5를 순서대로 돈다. Use Case 안에 펼치지 않은 이유는
Generate가 이미 12단계이고 Gate 실패와 Planner 실패가 한 함수에서 섞이기
때문이다.

```text
Packet build → validate_packet → Planner Request
  → llm.plan_monthly() → validate_monthly_proposal()
  → repairable이면 1회 repair → 검증된 Proposal
```

---

## 6. Atomicity (§8)

Repository write는 **최종 Validation 이후 한 번**이다. 기존 구조가 이미
그랬고 LLM 경로도 같은 지점을 쓴다.

테스트로 고정한 것:

| 상황 | saved plans |
|---|---:|
| 성공 | 1 |
| LLM unavailable | 0 |
| schema 위반 | 0 |
| L5 거부 (non-repairable) | 0 |
| repair 후에도 거부 | 0 |
| Planner 미주입 | 0 |
| planner_model 누락 | 0 |

Theme만 먼저 저장되거나 일부 Week만 남는 경로는 없다.

---

## 7. Failure Semantics (§9)

```text
LLMUnavailableError      → 그대로 전파
LLMConfigurationError    → 그대로 전파
schema 위반 (ValueError) → 그대로 전파
Packet 모순              → STRUCTURE_VALIDATION
L5 거부                  → LLM_OUTPUT_VALIDATION
Planner 미주입           → PREREQUISITE_GATE
```

기존 Yearly의 오류 표현 convention을 그대로 따랐다. **내부 Violation code를
공개 오류 코드로 승격하지 않는다** — 사용자에게 나가는 것은 Application 실패
하나이고 어떤 위반이었는지는 detail에 식별자로만 남는다(§41).

**조용한 RULE_ONLY fallback이 없다.** `generation_mode=LLM_PLANNER`인데 Planner가
주입되지 않으면 RULE_ONLY로 내려가지 않고 명확히 실패한다(§32).

---

## 8. Repair Orchestration (§11~§14)

**두 층을 분리했다.**

| 층 | 대상 | 위치 | 상한 |
|---|---|---|---|
| transport retry | timeout · 5xx · rate limit | Adapter | `LLM_MAX_RETRIES`(1) |
| L4 contract repair | Theme/Week/origin 계약 | Adapter | `MAX_REPAIR_ATTEMPTS`(1) |
| **L5 validation repair** | 원문 복사 · 중복 · 금지 표현 | **L6** | `MAX_VALIDATION_REPAIR_ATTEMPTS`(1) |

Run에 따로 기록한다 — `llm_call_count`(총 호출), `planner_validation_repair_count`,
`planner_repaired_violations`. Adapter telemetry는 `repair_count`(L4)와
`retry_count`(transport)를 따로 남긴다.

### 8.1 Repair 요청 (§12)

**같은 Packet을 다시 쓴다. Retrieval을 되풀이하지 않는다.** Context가 바뀌면
무엇 때문에 고쳐졌는지 알 수 없고 비용도 두 번 든다.

원래 본문에 L5 `repair_summary`(범주 수준 문장)만 덧붙인다. **위반한 Source
문장을 다시 노출하지 않는다.** 테스트가 repair 본문에 원문이 없음을 고정한다.

### 8.2 Non-repairable (§14)

`is_repairable == False`면 **LLM을 다시 호출하지 않는다.** `PROVENANCE_INCOMPLETE`
케이스에서 provider call이 1회에 멈추는 것을 테스트로 고정했다.

---

## 9. Exact-copy Repair E2E (§15·§16)

L5가 잡은 실제 결함 유형을 Application 경로에서 그대로 태웠다.

```text
첫 Proposal   W1 = CONTEXT_ONLY 근거 문장 그대로
              → SYNTHESIZED_EXACT_SOURCE_COPY
둘째 Proposal  새 표현
              → VALID

provider calls  2
L5 repairs      1
saved plans     1
```

repair 실패 경로도 고정했다.

```text
첫·둘째 모두 복사  → provider calls 2 · saved 0 · Generate 실패
셋째 cycle          시작하지 않는다 (스크립트에 3개를 넣어도 호출은 2회)
```

---

## 10. Domain Mapping

### 10.1 Theme (§18)

**LLM 출력을 Theme의 Source of Truth로 쓰지 않는다.** Proposal의 `theme_id`는
검증 anchor일 뿐이고, Monthly Theme Cell은 기존 Rule(`derive_theme_value`)이
확정 Parent Yearly에서 만든다.

```text
theme  generation = RULE_ONLY
       evidence   = THEME_REFERENCE + PARENT_PLAN
```

LLM이 만든 것으로 표시하지 않는다. 테스트로 고정.

### 10.2 Week (§19)

**Week ID의 Source of Truth는 canonical WeekPeriod다.** Proposal의 `week_id`는
대조 anchor이며 L5가 이미 집합·순서 일치를 확인했다. 테스트가 저장된
`week_id`가 canonical 목록과 같음을 고정한다.

`week.experience`는 저장하지 않는다 — §4.2 / OD-N18.

### 10.3 Outdoor Activity (§20·§21)

```text
REFERENCE
  value            승인 Catalog label (L5가 label 일치를 이미 확인)
  evidence         ACTIVITY_REFERENCE + source_id=activity_id
                                      + source_version=catalog_version
  generation       RULE_LLM / monthly.llm.evidence_grounded_planner / v1

LLM_SYNTHESIZED
  value            LLM이 구성한 활동명
  evidence         INSTITUTION_SAMPLE + source_id=실제 record_id
                                      + source_version=Evidence Store SHA
  generation       RULE_LLM / 같은 rule_id / v1
```

`grounding_source_ids`는 L5가 Packet audit으로 되짚은 **실제 `record_id`**다.
`E01` 같은 Packet-local 참조가 아니다.

**`LLM_SYNTHESIZED`를 EvidenceSourceType으로 쓰지 않는다**(§21). 테스트가
저장된 모든 Evidence에 그 값이 없음을 고정한다.

### 10.4 Safety (§25) · Cell State (§26)

Safety는 Proposal에서 가져오지 않는다. 기존 semantics 그대로
`EMPTY_UNRESOLVED` + `NOT_VERIFIED_SOURCE_REQUIRED`이며 Evidence도 붙지 않는다.
새 CellState 의미를 만들지 않았다.

---

## 11. Domain Provenance 반영 (§22)

L0에서 Contract만 갱신하고 미뤘던 것을 실제 persistence 시점인 지금 반영했다.

```python
class EvidenceSourceType(str, Enum):
    ...
    ACTIVITY_REFERENCE = "ACTIVITY_REFERENCE"
    INSTITUTION_SAMPLE = "INSTITUTION_SAMPLE"   # 추가
    CALENDAR = "CALENDAR"
    ...
```

**Additive다.** 기존 11값의 의미를 바꾸지 않았다.
`test_evidence_source_types_match_screen_spec_list`를 갱신하고,
`test_llm_synthesized_is_not_an_evidence_source_type`을 새로 추가했다 —
생성 방식이 Evidence Source로 새는 것을 계속 막는다.

---

## 12. Lineage / Run 기록 (§28·§29·§30·§42)

### Plan Aggregate

```text
parent_lineage     기존 8-field 그대로 (§27)
activity_catalog   exact pin 유지 (§28)
item.evidence      ACTIVITY_REFERENCE / INSTITUTION_SAMPLE
item.generation    RULE_LLM + rule_id + rule_version + selection_reason
```

`activity_catalog` pin은 Synthesized만 쓰인 달에도 유지한다 — 그 Generate에
Reference 후보를 제공한 Catalog가 재현에 필요하고, L3 Source Lineage도 같은
값을 담기 때문이다.

### MonthlyGenerationRun

```text
generation_mode · planner_model · prompt_version · packet_fingerprint
evidence_store_version · evidence_store_sha256 · retrieval_version
context_packet_version · llm_call_count · planner_validation_repair_count
planner_repaired_violations
```

**중복 저장하지 않는다.** Plan Item은 값과 Evidence를, Run은 실행 metadata를
담는다. Prompt 전문 · API Key · Base URL · Source 원문은 **담지 않는다** —
테스트가 Run 문자열에 Prompt 문구·`ELICE`·Source 원문이 없음을 고정한다.

---

## 13. Live Application Smoke (§37·§38)

```text
LIVE_GPT_4_1_MINI  (Application Use Case)
  model            openai/gpt-4.1-mini
  target           2026-06 만4세 · 우리 동네      ← Rule-only 최악 Case
  repository       InMemory (격리)

  RESULT           OK
  status           DRAFT
  saved plans      1
  latency          6,923ms

  generation_mode  LLM_PLANNER
  packet_finger    b41e16d801417315ca5ca690bd44c3e035a714db904016cf92292cf509ee0ff4
  evidence_sha     52b409557d3503422aa0109664298976bd7f831ed18304b818aaad936916e5ea
  retrieval_ver    monthly-evidence-retrieval-v0.1.0
  packet_ver       monthly-context-packet-v0.1.0
  provider calls   1
  transport retry  0   l4 contract repair 0   l5 repair 0

  theme            우리 동네   [RULE_ONLY]        ← LLM이 만들지 않았다

  outdoor_play
    2026-06-W1  우리 동네 지도 보며 산책하기
                RULE_LLM / ACTIVITY_REFERENCE: act_outdoor_v2_a24c6b5b26
    2026-06-W2  우리 동네에서 일하는 분 찾아보기
                RULE_LLM / ACTIVITY_REFERENCE: act_outdoor_v2_069a02d595
    2026-06-W3  모래 위에 그리는 우리 동네
                RULE_LLM / ACTIVITY_REFERENCE: act_outdoor_v2_eff211d706
    2026-06-W4  분필로 내가 되고 싶은 직업 그림 그리기
                RULE_LLM / ACTIVITY_REFERENCE: act_outdoor_v2_0b2bfc3786

  safety           EMPTY_UNRESOLVED × 4
  constraint       NOT_VERIFIED_SOURCE_REQUIRED
```

`우리 동네 지도 보며 산책하기`와 `모래 위에 그리는 우리 동네`는 L2 보고서
§14.1이 기록한 **Rule-only가 `activity_id` 해시 순서로 탈락시켰던 후보**다.
Application 경로에서도 실제로 선택된다.

API Key · Base URL · Prompt 전문을 출력하지도 저장하지도 않았다(스캔 확인).

### 13.1 Live exact-copy (§39)

이번 Live 실행에서는 4주 전부 REFERENCE였고 **repairable violation이 발생하지
않았다.** repair orchestration은 FakeLLM E2E에서 실제 결함 유형으로 검증했다(§9).

---

## 14. Provider Call Budget (§40)

| 경우 | provider calls |
|---|---:|
| 정상 성공 | **1** |
| transport retry 1회 | 2 |
| L4 contract repair 1회 | 2 |
| L5 validation repair 1회 | **2** |
| L4 repair + L5 repair | 3 |
| transport retry + L4 repair + L5 repair (worst case) | **4** |

worst case 4회는 `LLM_MAX_RETRIES=1` · `MAX_REPAIR_ATTEMPTS=1` ·
`MAX_VALIDATION_REPAIR_ATTEMPTS=1` 기준이다.

실측: Live 1회 성공 = 1 call. FakeLLM repair E2E = 2 calls.

---

## 15. Tests

```text
이전   2,201 passed, 4 deselected
현재   2,228 passed, 4 deselected      (+27 · 기존 실패 0)
```

| 영역 | 건수 |
|---|---:|
| 성공 경로 (DRAFT · outdoor · week id · theme · safety) | 5 |
| Provenance (Synthesized · Reference · 누출 금지 · Run lineage · Catalog pin) | 6 |
| Atomicity / 실패 (7 시나리오) | 6 |
| Repair (성공 · 같은 Packet · 실패 · 2차 금지 · non-repairable) | 5 |
| 기존 Contract 회귀 (round trip · Edit · Confirm · Confirmed read-only) | 4 |
| RULE_ONLY 격리 (강화된 기존 테스트) | 1 |

Golden 파일을 수정하지 않았다. 실제 API를 호출하는 테스트는 없다.

---

## 16. Open Issues

### 16.1 OD-N18 — **2026-09-13 CLOSED** (후속 패치에서 해소)

§4.2가 제기한 문제는 별도 단계에서 닫혔다. Template A **v0.2.0**(`focus` 활성)을
새로 추가하고 `week.experience`를 `focus` Cell로 저장한다. v0.1.0은 수정하지
않았고 RULE_ONLY는 계속 v0.1.0을 쓴다.

근거: `docs/analysis/monthly-llm-planner-od-n18-week-experience.md`

**이 보고서의 §4·§10.2·Q8 서술은 L6 시점 상태다.** 현재는 `week.experience`가
저장된다.

### 16.2 OD-N04 — 닫지 않았다 (§34)

근거는 생겼다.

```text
정상 1 call · worst case 4 call
Live 3회(L4) + 1회(L6) 모두 repair 0회
FakeLLM E2E에서 L5 repair 1회로 복구 성공 확인
```

그러나 **repair가 실제로 얼마나 자주 필요한지의 표본이 아직 얇다.**
Synthesized 비율이 높은 달을 L7/L8에서 관측한 뒤 정하는 편이 옳다.
지금 `1`을 제품 정책으로 확정하지 않는다.

### 16.3 L2~L5 defect (§51)

**발견되지 않았다.** `L2_PATCH_REQUIRED` · `L3_PATCH_REQUIRED` ·
`L4_PATCH_REQUIRED` · `L5_PATCH_REQUIRED` 모두 해당 없음.

### 16.4 계약 변경 1건 (명시적 보고)

`test_use_case_has_no_llm_dependency` → `test_rule_only_never_uses_the_llm_planner`.
L6이 `llm_planner` 주입 지점을 추가하므로 "주입 지점이 없다"는 전제가 더 이상
성립하지 않는다. 더 강한 불변으로 대체했다(§3.1).

### 16.5 그대로 둔 것 (§50)

```text
RegenerateMonthlyPlanItem LLM 통합   L7
Demo                                 L8
Golden                               L9
Production/Demo default 전환          L9
Activity Reference · Evidence Store · Theme Reference · Safety Rule   불변(SHA 확인)
Official Adapter                     미구현
OD-N17 · L2 Contrast precision · Activity v0.2.2   그대로
```

---

## 17. L7 Readiness

| L7 요구 | L6 제공 |
|---|---|
| LLM Planner 경로 | `MonthlyLlmPlanner` (재사용 가능) |
| Mode 선택 | `MonthlyGenerationMode` |
| Proposal → Domain Mapping | `_fill_outdoor_from_proposal` |
| Provenance 기록 | `INSTITUTION_SAMPLE` · `RULE_LLM` · rule_id/version |
| repair orchestration | L5 `is_repairable` 기반, 1회 |
| 실행 metadata | `MonthlyGenerationRun` LLM 필드 11개 |
| 저장 원자성 | 최종 검증 후 단 1회 save |

L7이 추가로 맡을 것: Cell 하나만 재생성할 때의 Packet 범위 · 나머지 Cell 보존 ·
`REGENERATED` Audit · 재생성 시 Catalog/Packet 재현성.

---

## 답변 — §53 필수 질문

**Q1. RULE_ONLY 결과가 이전과 완전히 동일한가?**
**동일하다.** Golden 파일을 수정하지 않았고 기존 테스트가 전부 통과한다.
Evidence Store · Retriever · LLM · Validator를 한 번도 호출하지 않으며, 호출하면
예외를 던지는 Planner를 주입해도 RULE_ONLY 생성이 정상 성공하고
`llm_call_count == 0`임을 테스트로 고정했다.

**Q2. LLM_PLANNER 경로가 실제 Application Use Case에서 DRAFT를 만드는가?**
**만든다.** Live Application Smoke에서 2026-06 만4세 DRAFT가 생성됐고
`saved plans = 1`, `status = DRAFT`다. 4주 전부 승인 Activity로 채워졌고
Rule-only가 놓쳤던 두 후보가 실제로 선택됐다.

**Q3. Repository write는 최종 Validation 이후 한 번만 일어나는가?**
**한 번이다.** Planner는 Cell 생성 **전에** 끝나고, save는 Domain Validation
다음 단계에서 한 번만 호출된다. 7가지 실패 시나리오 모두 `saved == 0`을
테스트로 고정했다.

**Q4. Exact-copy가 발생했을 때 repair → 재검증 → 성공 흐름이 동작하는가?**
**동작한다.** 첫 Proposal이 `SYNTHESIZED_EXACT_SOURCE_COPY`로 거부되고,
같은 Packet에 범주 수준 수정 요청만 덧붙여 1회 재요청한 뒤 통과한다.
`provider calls = 2` · `l5 repairs = 1` · `saved = 1`.

**Q5. Repair 후에도 invalid면 어떤 Plan도 저장되지 않는가?**
**저장되지 않는다.** `provider calls = 2` · `saved = 0` · Generate 실패다.
세 번째 Proposal을 스크립트에 넣어도 호출은 2회에서 멈춘다 — 두 번째 cycle을
자동 시작하지 않는다.

**Q6. Non-repairable violation에서 불필요한 LLM 재호출이 없는가?**
**없다.** `is_repairable == False`면 repair를 시도하지 않고 즉시 실패한다.
`PROVENANCE_INCOMPLETE` 케이스에서 provider call이 1회에 멈추는 것을 고정했다.

**Q7. REFERENCE와 LLM_SYNTHESIZED가 각각 정확한 Evidence / Provenance로
저장되는가?**
**저장된다.** REFERENCE는 `ACTIVITY_REFERENCE` + activity_id + catalog_version,
SYNTHESIZED는 `INSTITUTION_SAMPLE` + 실제 record_id + Evidence Store SHA다.
둘 다 `GenerationMethod.RULE_LLM` + `monthly.llm.evidence_grounded_planner` / v1.
`LLM_SYNTHESIZED`가 EvidenceSourceType으로 새지 않음을 별도 테스트로 고정했다.

**Q8. week_axis의 Provenance는 과장 없이 어떻게 표현했는가?**
**표현하지 않았다 — 저장하지 않았기 때문이다.** Provenance 자체는
`RULE_LLM` + `evidence=[]`로 정직하게 표현 가능했지만(§4.1), 승인 Template A에
그것을 담을 **활성 CONTENT Section이 없다**(§4.2). `week_axis`는 `role=AXIS`라
Domain이 Item 보유를 금지한다. 가짜 Section을 만들거나 Activity의 grounding을
복사하지 않고 **OD-N18로 남겼다.**

**Q9. Safety unresolved semantics가 그대로인가?**
**그대로다.** LLM 경로에서도 `EMPTY_UNRESOLVED` + `NOT_VERIFIED_SOURCE_REQUIRED`
이고 Safety Cell에 Evidence가 붙지 않는다. Proposal Schema에 Safety 자리가 없고
Prompt도 생성을 금지한다. Live Smoke에서도 4주 전부 `EMPTY_UNRESOLVED`였다.

**Q10. Teacher Edit / Confirm / Weekly Gate가 LLM Plan에서도 그대로 동작하는가?**
**동작한다.** LLM 생성 DRAFT에 대해 Edit 성공 + `TEACHER_EDITED` Audit 기록 +
원래 생성 Evidence 보존, Safety unresolved 상태로 Confirm 성공, Confirmed 후
Edit 차단을 각각 테스트로 고정했다. Weekly Gate는 Monthly status에만 의존하고
생성 경로를 보지 않으므로 기존 회귀가 그대로 유효하다.

**Q11. Application-level Live Smoke가 성공했는가?**
**성공했다.** §13. 실제 GPT-4.1 mini · InMemory Repository 격리 · 1회 호출 ·
6,923ms · DRAFT 1건 저장.

**Q12. Normal / Repair / Worst-case provider call 수는?**
정상 **1**, L5 repair 발생 시 **2**, L4 contract repair 발생 시 2,
transport retry 포함 worst case **4**. 실측은 Live 1회, FakeLLM repair E2E 2회.

**Q13. OD-N04를 닫을 근거가 생겼는가?**
**부분적으로.** call budget은 확정됐고 repair 복구가 실제로 동작함을 확인했다.
그러나 Live 4회(L4 3 + L6 1) 모두 repair 0회라 **실제 발생 빈도 표본이 얇다.**
`MAX_*=1`을 제품 정책으로 확정하기에는 이르다. **닫지 않는다.**

**Q14. L7 Regenerate 통합으로 넘어갈 준비가 되었는가?**
**되었다.** §17 표대로 Planner · Mapping · Provenance · repair · 실행 metadata가
모두 재사용 가능한 형태로 준비됐다. OD-N18은 L7을 막지 않는다 —
Regenerate 대상도 현재는 `outdoor_play` Cell이다.

---

```text
MONTHLY LLM PLANNER L6

Generation Modes:
  MonthlyGenerationMode = RULE_ONLY | LLM_PLANNER
  Use Case가 Mode를 고르지 않는다. 환경·협력자 유무·LLM 실패로 바꾸지 않는다
  기본값 RULE_ONLY — Production/Demo default를 바꾸지 않았다

RULE_ONLY:
  Theme·Week·Outdoor·Safety·CellState·Evidence·Catalog pin·Audit·Save 전부 불변
  Golden 무수정 · Evidence Store/Retriever/LLM/Validator 미호출
  기존 "LLM 의존 없음" 테스트를 **더 강한 불변**으로 대체 (주입돼 있어도 미사용)

LLM_PLANNER:
  Gate → canonical Week → Theme derivation → L2 Retrieval → L3 Packet
  → L4 plan_monthly → L5 Validation → (1회 repair) → Mapping → DRAFT

Preflight Provenance Gate:
  Provenance 표현 가능 — RULE_LLM + evidence=[] 로 과장 없이 표현된다
  **그러나 담을 Section이 없다** — week_axis는 role=AXIS로 Item 보유 금지,
  focus는 CONTENT지만 activated=false (활성화 시 Template A 개정 + Golden 변경)
  → week.experience를 저장하지 않았다. OD-N18 OPEN

Generate Flow:
  Planner는 Cell 생성 **전에** 끝난다. 실패하면 Cell도 Plan도 만들지 않는다

Persistence:
  최종 Domain Validation 이후 save 1회
  실패 7종 전부 saved = 0 (테스트 고정)

REFERENCE Provenance:
  ACTIVITY_REFERENCE + activity_id + catalog_version
  RULE_LLM / monthly.llm.evidence_grounded_planner / v1

SYNTHESIZED Provenance:
  INSTITUTION_SAMPLE + 실제 record_id + Evidence Store SHA
  RULE_LLM / 같은 rule_id / v1
  LLM_SYNTHESIZED는 EvidenceSourceType이 아니다 (테스트 고정)

Week Axis Provenance:
  저장하지 않았다 (OD-N18). Activity grounding을 복사하지 않았고
  근거 없이 INSTITUTION_SAMPLE을 주장하지도 않았다

Repair:
  transport retry / L4 contract repair / L5 validation repair 세 층 분리
  L5 repair는 같은 Packet 재사용 · 범주 수준 요청만 · 원문 미노출 · 1회
  non-repairable이면 재호출 없음 · 2차 cycle 자동 시작 없음

Atomicity:
  성공 1건 저장 · 실패 0건 저장 · 부분 Plan 잔존 없음

Safety:
  EMPTY_UNRESOLVED + NOT_VERIFIED_SOURCE_REQUIRED 그대로
  Proposal에서 가져오지 않는다 · Schema에 자리 없음

Teacher Edit / Confirm:
  LLM DRAFT에서 Edit 성공 · TEACHER_EDITED Audit · 생성 Evidence 보존
  Safety unresolved 상태로 Confirm 성공 · Confirmed 후 read-only

Weekly Gate:
  Monthly status에만 의존하므로 생성 경로와 무관. 기존 회귀 유효

Live Application Smoke:
  LIVE_GPT_4_1_MINI · 2026-06 만4세 · InMemory 격리
  DRAFT 1건 · 6,923ms · provider call 1 · repair 0
  Rule-only가 해시 순서로 놓쳤던 두 후보를 실제로 선택

Provider Calls:
  정상 1 · L5 repair 2 · L4 repair 2 · worst case 4

Regression:
  2,201 → 2,228 passed, 4 deselected (+27 · 기존 실패 0)
  승인 Artifact 전부 불변 (SHA 확인) · Golden 무수정
  Demo · Regenerate · Prompt v0.1.1 · L2 · L3 · L5 무변경
  산출물에 API Key / Base URL / Prompt 전문 없음 (스캔 확인)

Open Issues:
  OD-N18 (신규) — Week Experience를 담을 Section이 없다
  OD-N04 미종료 — call budget은 확정됐으나 repair 발생 빈도 표본이 얇다
  계약 변경 1건 — RULE_ONLY LLM 격리 테스트를 더 강한 불변으로 대체
  L2~L5 defect 발견 없음

L7 Readiness:
  READY_FOR_REGENERATE_INTEGRATION
```

---

```text
MONTHLY_LLM_PLANNER_L6_COMPLETE
```
