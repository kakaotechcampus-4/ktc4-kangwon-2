# Monthly LLM Planner vNext — L3 Monthly Context Packet

- 작성일: 2026-09-13
- 선행: L2 Evidence Retrieval 완료 (`MONTHLY_LLM_PLANNER_L2_COMPLETE`)
- 입력 Artifact: `institution-evidence-ingestion-v0.1.0`
  `content_sha256 = 52b409557d3503422aa0109664298976bd7f831ed18304b818aaad936916e5ea`
- 산출물
  - Production 코드 `src/ssuksak/planning/context/`
  - 테스트 `tests/context/` (133건 신규)
  - 감사 도구 `analysis/experiments/monthly_llm_vnext/audit_l3_context_packet.py`
  - 감사 출력 `analysis/tmp/l3_audit.txt`
- 범위 밖: L4 `LLMPort.plan_monthly` · Prompt 구현 · GPT-4.1 mini 호출 ·
  Generate/Regenerate 통합 · Demo · Golden · Activity v0.2.2

---

## 1. Scope

L2는 "무엇이 근거인가"를 골랐다. L3는 그것을 **구조화된 Monthly Planning
Context**로 조립한다.

```text
Planning Request + 확정 Yearly Theme + canonical Week Periods
+ L2 Retrieval Result + 연령 근거 통계 + Safety 상태 + Product Constraints
        ↓
MonthlyContextPacket
```

**Prompt 문장을 만들지 않았다.** Rendering은 L4다. 사람이 눈으로 확인하는
`render_debug_packet()`은 이름 그대로 debug이며 Production Prompt로 승격하지
않는다.

---

## 2. Retrieval Architecture

```text
src/ssuksak/planning/context/
├── __init__.py
├── models.py       Packet Contract (pydantic strict · extra=forbid · frozen)
├── builder.py      MonthlyContextRequest · MonthlyContextPacketBuilder
│                   연령 근거 통계 · 중복 제거 · 출처 익명화
├── budget.py       planner_visible_payload · measure · trim_to_budget
│                   packet_fingerprint
├── validation.py   validate_packet (Packet 자체 검증. L5와 다르다)
└── debug.py        render_debug_packet (Prompt 아님)
```

`models / builder / budget` 세 책임에 `validation`과 `debug`를 더했다.
Validator를 builder에 넣지 않은 이유는 **직접 만들지 않은 Packet도 검증해야
하기** 때문이다(L4가 받은 Packet, 저장했다 다시 읽은 Packet).

---

## 3. Packet Contract

```text
MonthlyContextPacket
├─ packet_version              monthly-context-packet-v0.1.0
├─ planning_request            학년도 · 대상 월 · 연령 · age_mode
├─ parent_theme                확정 theme_id / theme_value (immutable)
├─ week_slots[]                canonical WeekPeriod
├─ age_context                 연령별 근거 강도 + 실제 단일연령 근거 수
├─ institution_evidence[]      기관 바깥놀이 관찰
├─ age_contrast_evidence[]     Group 구조 (Pair 관계 보존)
├─ week_experience_candidates[] 주차 번호 없음
├─ reference_activities[]      승인 Catalog canonical 후보
├─ other_outdoor_evidence[]    추가 Grounding (전부 CONTEXT_ONLY)
├─ official_play_context[]     비어 있음 (L2 Option A)
├─ official_topic_context[]    비어 있음
├─ safety_context              상태만. 내용 후보 없음
├─ constraints                 구조화된 Constraint
├─ source_lineage              재현에 필요한 version 전부
└─ trimmed_blocks[]            Budget으로 잘린 Block
```

`extra="forbid"` · `frozen=True`. 모르는 필드는 거부하고, 만든 뒤에는 바꾸지
못한다. 테스트가 두 성질을 고정한다.

---

## 4. Planner-visible / Audit-only 분리

L2의 `rank_score` · `retrieval_tier` · `source_diversity_group`은 Retrieval
내부 점수다. GPT가 이것으로 할 수 있는 일이 없고 Token만 먹는다.

각 Evidence 항목은 `audit` 하위 model을 갖고, `planner_visible_payload()`가
그것을 제거한다. 제거 대상:

| 필드 | 왜 빼는가 |
|---|---|
| `audit.*` | Retrieval 내부 점수 · 원문 좌표 · SHA |
| `evidence_id` | 35자 hex. 대신 짧은 `ref`를 준다 |
| `month` | Packet 전체가 한 달이다. `planning_request`에 이미 있다 |
| `source_section` | Block 이름이 곧 section이다 |
| `daycare_ref` / `classroom_ref` | 내부 식별자 |
| `parent_yearly_plan_id` 등 | lineage는 audit 쪽에서 본다 |

**`reuse_policy`는 절대 빼지 않는다.** 빼는 순간 `CONTEXT_ONLY` Contract가
Planner에 도달하지 않는다(§11).

### 4.1 짧은 참조 `ref`

Evidence 항목에 `E01` 형태의 Packet-local 참조를 붙였다. 이유는 둘이다.

1. `ev_a83b8c06154a_p01_r00123_c02_i01`을 그대로 주면 항목당 35자를 쓴다.
2. LLM이 그 hex를 정확히 되받아 적지 못한다. L5가 `grounding_source_ids`를
   기록하려면 **모델이 안정적으로 인용할 수 있는 id**가 필요하다.

실제 `record_id`는 `audit`에 그대로 있고 `ref`로 되짚는다.

### 4.2 기관 이름 익명화

Planner에게 필요한 것은 "서로 다른 곳에서 나왔다"는 사실이지 기관 이름이
아니다. 항목은 `S1` · `S2` 같은 등장 순서 라벨을 갖고, 실제 `institution_id`는
`audit`에만 남는다. 테스트가 Planner payload에 기관명이 없음을 고정한다.

---

## 5. Planning Request / Parent Theme / Week

- **Theme은 immutable planning input이다.** `theme_id`와 `theme_value`를
  확정 Yearly lineage에서 그대로 옮기고, `constraints.theme_locked = True`로
  구조화한다. LLM은 Theme을 고르지도 바꾸지도 않는다(CLAUDE.md §5).
- **Week은 `canonical_week_periods()` 결과를 그대로 쓴다.** LLM이 주차 수나
  날짜를 만들지 않는다. `expected_week_ids`가 Constraint에 함께 들어가므로
  L5가 제안된 주차 집합을 그대로 대조할 수 있다.

실측(2026-07은 5주, 나머지 4주):

```text
2026-07-W1  2026-06-29~2026-07-03   ← 전월에서 시작한다 (OD-M02대로 clip하지 않음)
2026-07-W2  2026-07-06~2026-07-10
2026-07-W3  2026-07-13~2026-07-17
2026-07-W4  2026-07-20~2026-07-24
2026-07-W5  2026-07-27~2026-07-31
```

---

## 6. Age Context

### 6.1 기준을 새로 만들지 않았다

`docs/analysis/new-reference-evidence-impact-2026-09.md` §4.1이 확정한 4단계와
임계값을 **그대로** 옮겼다.

```text
STRONG      단일연령 독립기관 >= 3
MODERATE    단일연령 독립기관 == 2, 또는 1이면서 그 면에 바깥놀이 행이 있음
WEAK        단일연령 독립기관 == 1 (바깥놀이 행 없음), 또는 혼합 근거 기관 >= 3
VERY_WEAK   그 외
```

Packet은 `criteria_id = "new-reference-evidence-impact-2026-09#4.1"`을 함께
들고 다닌다. 나중에 "이 등급은 어디서 왔나"를 물었을 때 답이 Packet 안에 있다.

### 6.2 §8·§9의 `LOW`를 채택하지 않았다 — 보고 대상

지시문 §8과 §9는 `LOW | MODERATE | STRONG` 3단계를 제시했다. 그런데 확정된
기준은 **`MODERATE` 아래에 서로 다른 두 단계**(`WEAK` / `VERY_WEAK`)를 갖는다.

- 둘을 `LOW`로 합치려면 "단일연령 기관 1곳"과 "연령 근거 전무"를 같은 값으로
  취급해야 한다. 그것은 확정 기준을 재해석하는 **새 임의 기준**이다.
- §9가 "기존 기준을 Context용 enum으로 그대로 옮길 수 없다면 Open Decision으로
  남기고 임의 확정하지 않는다"고 지시했으므로, 확정된 4단계를 그대로 쓰고
  합치지 않았다.

→ **OD-N17 (OPEN)**: Context enum을 3단계로 축약할 것인가.
축약한다면 `WEAK` / `VERY_WEAK` 구분을 버려도 되는지가 실질 쟁점이다.
현재 4단계로도 L4는 막히지 않는다.

### 6.3 세는 대상이 달라졌다 — 숨기지 않고 기록한다

임계값과 신호 정의는 같지만 **세는 substrate가 다르다.**

```text
재감사(2026-09)   inventory의 면 metadata
L3 (Runtime)      L1 Evidence Store의 실제 추출 record
```

Runtime이 가진 것이 Evidence Store뿐이기 때문이다. 대조 결과:

| 월·연령 | 재감사 AFTER | L3 실측 | 등급 |
|---|---|---|---|
| 6월 만4세 | STRONG (단3/전11/바2) | STRONG (단3/전11/바2) | 일치 |
| 6월 만5세 | MODERATE (단2/전10/바1) | MODERATE (단2/전10/바1) | 일치 |
| 7월 만4세 | STRONG (단3/전10/바2) | STRONG (단3/전10/바2) | 일치 |
| 2월 만4세 | MODERATE (단2/전11/바1) | MODERATE (단2/전11/바1) | 일치 |
| 8월 만5세 | STRONG (단4/전12/바3) | **MODERATE (단2/전10/바1)** | **불일치** |
| 3월 만3세 | STRONG (단12/전16/바12) | STRONG (단16/전21/바11) | 일치(값 차이) |

8월 만5세가 한 단계 낮게 나온다. 면 metadata에는 만5세 면이 4기관분 있지만,
그중 2기관은 그 면에서 **VALID한 바깥놀이 record가 추출되지 않았다**.
Runtime이 실제로 쓸 수 있는 것은 후자이므로 L3 값이 더 보수적이고 정확하다.
등급을 재감사표에 맞추려고 기준을 되돌리지 않았다.

### 6.4 등급과 Packet 내용이 어긋날 수 있다 — 사실로 노출한다

`strength`는 **그 달 Corpus 전체**를 보지만 Packet에는 Top-K만 담긴다.
2027-02 만5세가 그 예다.

```text
만5세  STRONG (단3/전11/바1)
Packet 내 요청연령 단일연령 근거   1건
Institution Block                 11건 전부 MIXED_AGE_COVERING
```

단일연령 만5세 면이 3기관에 있지만 **바깥놀이 행이 있는 면은 1건뿐**이다.
등급만 보면 L4가 연령 차이를 근거보다 강하게 말하게 된다.

그래서 `age_context.single_age_grounding_count`를 넣었다. 등급이 아니라
**사실**이며(요청 연령의 단일연령 면에서 온 근거가 Packet에 몇 건인가),
새 임계값을 만들지 않는다. 5 Case 실측: 7 / 7 / 7 / 7 / **1**.

---

## 7. Age Contrast — Pair 관계 보존

평탄화하면 의미가 사라진다. `만3세 A`와 `만4세 B`를 관계없는 두 줄로 주면
Planner는 그것이 같은 기관의 같은 달 기록인지 알 수 없다.

```text
AgeContrastGroup
├─ group_id · source_group · month · monthly_theme
├─ source_sha256 · source_path        (audit)
└─ observations[]
   ├─ age 3 → items[]
   └─ age 4 → items[]
```

실측 2026-07 만4세:

```text
contrast_60038759cf41 [S1] theme=여름
    만3세 | 여름 꽃을 찾아요.
    만4세 | 물놀이 공원 만들기
    만4세 | 물총놀이
contrast_8e0b4da66d80 [S2] theme=신나는 여름
    만3세 | 친구의 그림자를 잡아보아요
    만4세 | 다양한 여름날씨 몸으로 표현하기
    만4세 | 여름 과일 신체 놀이하기
```

Validator가 세 가지를 고정한다: ① Group에 연령이 2개 이상, ② 같은 연령이 두 번
들어가지 않음, ③ **모든 항목의 `source_sha256`이 Group과 같음**(다른 문서가
대조에 섞이지 않음).

---

## 8. 2026-06 Age Contrast 0 → 6 검증 (§12)

이번 L3 착수 전 반드시 확인해야 했던 항목이다. **결론: 실제 Source 복원이며
추론이 아니다.**

Prototype Evidence Store(3,603건)와 L1 Production Store(12,367건)를 같은 두
문서에 대해 직접 비교했다.

| 문서 | Prototype 2026-06 outdoor 단일연령 record | L1 Production |
|---|---|---|
| `a83b8c06…` 연제구연산더샵 | **1건** (p1 만4세 `모래로 동네 공원만들기`) | **8건** (p1 만4세 4건 / p2 만3세 4건) |
| `ad74578a4d…` 부산광역시청 | **1건** (p1 만3세 `우리 동네를 산책해요`) | **9건** (p1 만3세 3 / p2 만4세 3 / p3 만5세 3) |

Prototype은 각 문서에서 한 연령 면만 추출했으므로 `len(ages) >= 2` 조건을
통과하지 못했고 대조 후보가 0이 되었다. Cell geometry로 나머지 면이 복원되면서
대조가 성립했다.

**추론으로 만든 Pair가 아님을 확인한 근거:**

- 두 Pair 모두 `source_sha256`이 동일하다 — 같은 파일이다.
- 연령이 다른 항목은 **page가 다르다**(p1 만4세 / p2 만3세).
- 파일명이 `만3세,만4세`·`만3세,만4세,만5세`다. CLAUDE.md §11대로 이는
  "한 파일 안에 단일연령 계획안이 각각 존재"하는 표기이며 혼합연령반이 아니다.
- 다른 기관끼리 묶인 Pair는 없다(테스트로 고정).

→ **L2 defect가 아니다. L3를 강행하지 않았고 L2 Patch도 필요 없다.**

---

## 9. Week Experience

```text
WeekExperienceCandidate
  ref · evidence_id · text · age_scope · source_group
  source_label · monthly_theme · reuse_policy · audit
```

**week 필드가 아예 없다.** 값을 `None`으로 두는 것이 아니라 자리를 만들지
않았다. L1 실측에서 `week_position` 보유 record가 0건이므로, 자리를 만들면
누군가 반드시 추정해서 채운다. 테스트가 `"week"`를 포함한 필드가 하나도 없음을
고정한다.

타입 이름도 `WeekPlan`이 아니라 `WeekExperienceCandidate`다.

---

## 10. Reference Activities

승인 Catalog의 canonical 후보. **후속 Planner가 그대로 선택할 수 있는 유일한
Activity 축**이다.

```text
activity_id · label · supported_ages · theme_link_ids
evidence_strength · has_display_quality_issue · rank
```

Catalog 내부 metadata(`origin_id` · `label_derivation` · `aliases` ·
`curriculum_links` · 개별 `evidence[]`)는 넣지 않았다. Planner의 판단에 쓰이지
않고 Packet을 두 배로 만든다.

`activity_id`는 `act_outdoor_autumn_outing` 형태로 짧고 의미가 읽히므로
Evidence와 달리 축약하지 않았다 — 모델이 안정적으로 인용할 수 있다.

---

## 11. Reuse Policy — CONTEXT_ONLY가 사라지지 않는다

세 겹으로 보존한다.

1. **항목마다** `reuse_policy = CONTEXT_ONLY`가 붙어 있고 Planner payload에서
   제거되지 않는다.
2. **Constraint에** `source_text_copy_allowed = False` ·
   `corpus_direct_output_enabled = False`.
3. **Validator가** 모순을 막는다 — `CONTEXT_ONLY` 항목이 있는데
   `corpus_direct_output_enabled = True`면 예외다.

### 11.1 `CORPUS_EVIDENCE` origin (§19)

P0 Evidence Store 12,367건이 전부 `CONTEXT_ONLY`이고
`PRODUCT_OUTPUT_ALLOWED`는 0건이다. 따라서 Corpus record를 Product 값으로
직접 쓸 수 없다.

```text
allowed_activity_origins    REFERENCE, LLM_SYNTHESIZED
activity_origin_priority    REFERENCE > CORPUS_EVIDENCE > LLM_SYNTHESIZED
```

`allowed`에서는 제외하되 **`priority`에는 남겼고 Domain enum도 삭제하지
않았다.** 개념이 폐기된 것이 아니라 현재 Corpus의 reuse policy 때문에
비활성이기 때문이다. Validator가 두 값의 정합을 고정한다.

---

## 12. Safety Context

안전교육은 **LLM Planner가 배치하지 않는다**(CLAUDE.md §5). 그래서 이 Block에
**안전교육 내용 후보를 넣지 않았다.** 상태만 전달한다.

```text
safety_generation_allowed   False
verification                NOT_VERIFIED_SOURCE_REQUIRED
cell_state                  EMPTY_UNRESOLVED
required_source_kinds       INSTITUTION_ANNUAL_SAFETY_PLAN, TEACHER_INPUT
```

현재 Production `GenerateMonthlyPlan`이 내리는 판정과 같은 semantics다.
`SAFETY_REQUIRED_SOURCE_KINDS`는 Use Case를 import하지 않기 위해 값을
복제했고, **두 상수의 일치를 테스트로 고정**했다.

---

## 13. Product Constraints

자연어 금지 문구가 아니라 구조화 Constraint다. L4가 이것을 읽어 Prompt 문장을
만든다. 문장을 L3에 두면 Constraint가 바뀌었을 때 어디를 고쳐야 하는지 알 수
없게 된다.

```text
expected_week_ids · expected_week_count
theme_locked                  = True
safety_generation_allowed     = False
duplicate_activity_allowed    = False
official_claim_allowed        = False
source_text_copy_allowed      = False
corpus_direct_output_enabled  = False
allowed_activity_origins      = REFERENCE, LLM_SYNTHESIZED
activity_origin_priority      = REFERENCE > CORPUS_EVIDENCE > LLM_SYNTHESIZED
```

---

## 14. Block 간 중복 제거 (§28)

L2는 Institution ∩ Other Outdoor를 이미 제거한다(`used_ids`). 남은 중복은
**Age Contrast ∩ 나머지**다. 실측 1~4건.

우선순위:

```text
age_contrast > institution > other_outdoor
```

Age Contrast가 앞인 이유는 **정보가 더 많기 때문**이다. 같은 record라도 대조
Group 안에서는 "어느 연령 면에서 나왔는지"까지 함께 보인다. 평탄한 목록에서
빼도 잃는 것이 없고 Token은 절약된다.

Block 크기 변화:

| Case | L2 inst | L3 inst | 중복 제거 | L2 contrast | L3 contrast | Pair 미성립 |
|---|---:|---:|---:|---:|---:|---:|
| 2026-03 만3세 | 12 | 10 | 2 | 6 | 5 | 1 |
| 2026-06 만4세 | 12 | 10 | 2 | 6 | 6 | 0 |
| 2026-07 만4세 | 12 | 8 | 4 | 6 | 6 | 0 |
| 2026-08 만4세 | 12 | 11 | 1 | 6 | **3** | **3** |
| 2027-02 만5세 | 12 | 11 | 1 | 3 | 3 | 0 |

### 14.1 Pair 미성립 — L2 정밀도 문제로 보고한다

2026-08에서 L2 Age Contrast 6건 중 3건이 Packet에 들어가지 못했다.

```text
682cdb9981  ages=[4]     만4세 3건만 남음        → 대조가 아니다. 제외
de8b955dd2  ages=[3,4]   만3세 2 / 만4세 1       → 유지
```

원인은 L2가 대조 후보를 **평탄한 순위 목록에 기관당 3건 상한**으로 자르기
때문이다. 그 결과 한 문서에서 한 연령만 살아남아 대조가 성립하지 않는 경우가
생긴다. L3는 §11대로 **없는 대조쌍을 만들지 않으므로** 통째로 제외한다.

**Evidence가 사라지지는 않는다.** 제외된 `움직이는 교통기관 관찰해요` ·
`우리동네 버스 정류장을 살펴봐요`는 Institution Block에 그대로 있고 테스트가
이를 고정한다. 즉 손실이 아니라 **재분류**다.

L2 Contract 위반은 아니다 — L2 테스트는 "적어도 하나의 진짜 Pair가 있다"만
보장하지, 반환된 모든 행이 Pair의 일부라고 보장하지 않는다. 그래도 개선
여지이므로 기록한다.

→ **L2 정밀도 개선 후보 (BLOCKING 아님)**: 기관 상한을 평탄한 목록이 아니라
`(문서, 연령)` 단위로 적용하거나, 상한 적용 후 Pair가 깨진 행을 다시 거르는 것.
**이번 L3에서 L2를 고치지 않았다**(§43).

---

## 14.2 Theme Consistency (§29)

Evidence의 `monthly_theme`과 확정 Parent Theme을 **각각 보존한다.**

```text
parent_theme.theme_value   "우리 동네"          ← 확정 입력
group.monthly_theme        "우리동네/월드컵"     ← 원문 그대로
                           "북적북적 우리 동네"
```

Evidence를 조작해 Theme을 맞추지 않는다. 관계 판단은 후속 Planner가 하고,
관련 Evidence 선별은 L2 ranking이 이미 했다.

---

## 15. Budget

### 15.1 문자 수를 쓰고 tokenizer를 넣지 않았다

GPT-4.1 mini의 tokenizer가 프로젝트에 없고, `한글 1자 = X token` 같은 환산을
근거 없이 Contract로 만들지 않는다(CLAUDE.md §8). 새 dependency도 넣지 않았다.

세 수치를 **따로** 잰다. 하나로 합치면 비교가 틀린다.

```text
planner_visible_chars   canonical JSON 문자 수. Budget 판정 기준
content_chars           활동명·주제 등 자연어만. 표현과 무관
full_packet_chars       audit 포함 전체
```

### 15.2 실측

| Case | planner JSON | 내용 문자 | 주 | Block 합계 |
|---|---:|---:|---:|---|
| 2026-03 만3세 | 11,281 | 890 | 4 | inst 10 · ctr 5 · wk 10 · ref 12 · oth 10 |
| 2026-06 만4세 | 10,356 | 1,018 | 4 | inst 10 · ctr 6 · wk 10 · ref 7 · oth 10 |
| 2026-07 만4세 | 10,339 | 936 | 5 | inst 8 · ctr 6 · wk 10 · ref 8 · oth 10 |
| 2026-08 만4세 | 9,877 | 788 | 4 | inst 11 · ctr 3 · wk 10 · ref 7 · oth 10 |
| 2027-02 만5세 | 9,557 | 990 | 4 | inst 11 · ctr 3 · wk 10 · ref 4 · oth 10 |
| **평균** | **10,282** | **924** | | |

```text
평균 debug render   2,698자   ← Prototype 5,407자와 비교 가능한 쪽
JSON / 내용 배율    11.12x
render / 내용 배율   2.92x
```

### 15.3 Block별 점유 (평균, planner JSON 기준)

| Block | 문자 | 비중 |
|---|---:|---:|
| institution_evidence | 1,975 | 19.2% |
| other_outdoor_evidence | 1,948 | 18.9% |
| week_experience_candidates | 1,678 | 16.3% |
| reference_activities | 1,602 | 15.6% |
| age_contrast_evidence | 1,174 | 11.4% |
| 고정 Header (request·theme·weeks·age·safety·constraints) | 1,905 | 18.6% |

### 15.4 Trim 전략

```text
DEFAULT_CHAR_BUDGET = 20,000
```

실측 최대가 11,281이므로 **평상시에는 발동하지 않는다.** 그것이 의도다 —
Trim이 상시 동작하면 근거가 조용히 사라지고 아무도 눈치채지 못한다.
처음 12,000으로 잡았다가 2026-06 만4세에서 바로 발동하는 것을 보고 올렸다.
5 Case 전부 `trimmed_blocks == ()`임을 테스트가 고정한다.

줄이는 순서:

```text
1. other_outdoor_evidence     보조 Grounding. 가장 대체 가능하다
2. week_experience_candidates
3. institution_evidence        최소 4건 유지 (주차 수 하한)
4. age_contrast_evidence       Group 단위로만. Pair를 깨지 않는다

절대 자르지 않음
  reference_activities   canonical 후보. 2027-02은 4개뿐이라 자르면 남지 않는다
  planning_request · parent_theme · week_slots · age_context
  safety_context · constraints · source_lineage
```

`random`을 쓰지 않는다. L2 ranking 순서를 유지한 채 **tail부터** 한 건씩
지운다. 테스트가 ① 남은 것이 원본의 head prefix와 같음 ② 같은 입력이면 같은
fingerprint ③ Reference·Week·Constraint 불변 ④ institution 하한 유지를 고정한다.

---

## 16. Determinism / Fingerprint

`packet_fingerprint()`를 도입했다. **Planner-visible 내용 + Source Lineage**의
canonical JSON에 대한 SHA-256이다.

- `generated_at` 같은 volatile metadata는 애초에 Packet에 없다.
- Lineage를 포함하는 이유: 같은 문장이라도 다른 Evidence Store version에서
  나왔다면 다른 Context다. L6 재현 검증에서 이 구분이 필요해진다.

도입 판단: 값이 있다고 봤다. L4/L5가 "이 제안이 어느 Context에서 나왔는가"를
한 값으로 지목할 수 있고, 테스트에서 Packet 동등성을 비교하기 쉽다.

실측:

```text
2026-03 만3세  동일=True  a0c7266a7007459fbd46a1a0
2026-06 만4세  동일=True  b41e16d801417315ca5ca690
2026-07 만4세  동일=True  993c6d9cbd93098e6cb005bc
2026-08 만4세  동일=True  fb6805c7351cc87578b1bdc3
2027-02 만5세  동일=True  5c4226a7bf886a2cd69cb4ed
```

(2026-09-13 최종 코드 기준. 이 값들은 `age_context.single_age_grounding_count`를
추가하기 **전에** 한 번 기록했다가 최종 코드로 다시 측정해 갱신했다 — Packet 내용이
바뀌면 fingerprint도 바뀌는 것이 정상 동작이다.)

같은 Builder 2회 + 새 Store/Builder 1회가 모두 같다. Record 입력 순서를
뒤집어도 같다. Theme이나 Evidence Store가 달라지면 값이 달라진다(테스트 고정).

---

## 17. Performance

```text
store + catalog load    0.395s   (1회)
packet build (1건)      5.13ms
5-case batch           23.56ms   (case당 4.7ms)
serialization(measure)  0.79ms
```

L2가 2.1ms였으므로 L3가 더한 비용은 약 3ms다. §38이 경계한 "수백 ms 이상"과는
거리가 멀다.

처음 10.58ms였고 두 곳을 고쳤다. ① Trim loop가 매 반복마다 audit 포함 전체
`model_dump`를 돌던 것을 planner payload만 세도록 분리. ② 항목 payload
축소(4.1). 성능 최적화 자체가 목표는 아니므로 여기서 멈췄다.

---

## 18. Tests

```text
이전   1,876 passed, 4 deselected
현재   2,009 passed, 4 deselected      (+133 신규 · 기존 실패 0)
```

| 파일 | 건수 | 내용 |
|---|---:|---|
| `tests/context/test_context_packet.py` | 72 | Contract(frozen·unknown field) · 필수 요소 · 빈 Optional · Eligibility · 중복 제거 · Contrast Pair · Week 필드 부재 · License · Safety · Age 강도 4단계 · 익명화 · Budget · 결정론 · Debug |
| `tests/context/test_context_packet_quality.py` | 61 | 실제 Artifact 5 Case × 기본 성질 8 + §33~§37 지정 검증 + §12 Pair 출처 검증 |

실제 Artifact가 없으면 quality 테스트는 skip된다. 나머지는 Artifact 없이 돈다.

§40이 지정한 항목 대응:

| 요구 | 테스트 |
|---|---|
| strict / immutable / unknown field reject | `test_packet_is_frozen_and_rejects_unknown_fields` |
| theme · week · constraints · lineage required | `test_theme_is_carried_verbatim…` 외 4건 |
| contrast [] · official [] | `test_a_packet_with_no_contrast_is_still_valid` 외 2건 |
| no NEEDS_REVIEW / INVALID | `test_ineligible_records_never_reach_the_packet` (5 parametrize) |
| reuse policy preserved | `test_reuse_policy_is_never_stripped_from_the_planner_payload` |
| CONTEXT_ONLY direct output disabled | `test_corpus_direct_output_is_disabled_and_origin_list_agrees` |
| record id duplication policy | `test_a_record_never_appears_in_two_blocks` · `test_contrast_wins_over_the_flat_institution_list` |
| within budget unchanged / over budget deterministic trim | `test_a_packet_within_budget_is_returned_unchanged` 외 5건 |
| same retrieval → same fingerprint | `test_assemble_is_pure_given_a_retrieval_result` 외 4건 |
| age 3 / 4 / 5 / mixed | `test_single_age_requests_are_accepted` · `test_mixed_age_request_reports_both_ages` |

---

## 19. Open Issues

### 19.1 OD-N17 (신규, OPEN) — Age Strength enum 단계 수

§6.2 참조. 확정 기준의 4단계를 유지했고 `LOW`로 축약하지 않았다.
**L4를 막지 않는다.**

### 19.2 L2 minor gap — Retrieval version 상수 부재

L2가 자기 version 상수를 publish하지 않아 `RETRIEVAL_CONTRACT_VERSION`을
L3에 두었다(`monthly-evidence-retrieval-v0.1.0`). Lineage 재현성 관점에서는
L2 쪽에 있어야 옳다. **L2 코드를 고치지 않기 위해** 이번에는 L3에 두었다.

### 19.3 L2 정밀도 개선 후보 — Contrast Pair 미성립

§14.1 참조. 2026-08에서 L2 Contrast 6건 중 3건이 Pair를 이루지 못한다.
Evidence 손실은 없고(Institution Block에 남음) Contract 위반도 아니다.
**BLOCKING 아님.**

### 19.4 Reference Block의 연령 변별력

2026-07에서 만3/4/5세 Reference Block이 8/8 겹친다. Catalog `supported_ages`가
연령을 크게 구분하지 않기 때문이며 L2/L3가 고칠 수 있는 문제가 아니다.
Activity v0.2.2 범위(L2 보고서 §19.2에서 이미 기록).

### 19.5 Official Evidence — §39 답변은 §21에

### 19.6 여전히 OPEN

```text
OD-N16  PDF 라이브러리 의존성 — L3 비차단. Runtime은 여전히 PDF를 읽지 않는다
OD-N17  Age Strength enum 단계 수 (신규)
OD-N03  Activity taxonomy (curriculum_links 공백)
OD-N04  LLM 공급자·모델·retry 상세
OD-N11  Theme/Template/Safety Adapter 승인 우회 입력 제거
Activity v0.2.2 승격 범위
```

---

## 20. 수정하지 않은 것 (§43 확인)

```text
GenerateMonthlyPlan · RegenerateMonthlyPlanItem      무변경
LLMPort · Elice Adapter · Production Prompt          무변경
Demo · Golden                                        무변경
Activity Reference Artifact · Evidence Store         무변경 (SHA 확인)
Theme Reference · Safety Rule                        무변경 (SHA 확인)
L2 Retrieval (models · ranking · retriever · repo)   무변경
```

SHA 재확인:

```text
theme_reference_v0.json                 c12999fa141d5c5f…  OK
activity_reference_v0.json              b565254f6668aeea…  OK
activity_reference_v0_2.json            e27ebca3342a8432…  OK
activity_reference_v0_2_1.json          ddbbe43f570cf64e…  OK
monthly_template_a.json                 1f35322dd52f832b…  OK
safety_education_legal_v1.json          5831809b19a28505…  OK
tests/golden/monthly_cases.json         c605641232d91abd…  OK
tests/golden/yearly_cases.json          7918e9f9cbe23580…  OK
institution_evidence_v0_1_0.json        8479c0490a002d93…  OK
```

이번 작업에서 새로 만든 파일과 감사 스크립트 외에 변경된 Production 코드는
없다.

---

## 21. L4 Readiness / Official Evidence Gap (§39)

### 선택: **A — Institution + Activity Reference만으로 첫 L4 Smoke를 시작해도 된다.**

근거 넷.

1. **Packet이 비지 않는다.** 5 Case 전부에서 institution · week experience ·
   reference · other outdoor 네 Block이 모두 채워진다. 근거가 없어서 LLM이
   창작해야 하는 상태가 아니다.
2. **Official 없이도 Grounding이 24건 수준이다.** 가장 희소한 2027-02 만5세도
   canonical 4 + Institution 11 + Other 10 + Week 10이다.
3. **첫 Smoke의 목적이 다르다.** L4 Smoke가 확인할 것은 "Context를 준 대로
   읽고 Schema에 맞는 제안을 내는가"이지 "국가 공식 자료와 정합한가"가 아니다.
   후자는 L5 Validation과 Production 활성화의 요구다.
4. **`official_claim_allowed = False`가 이미 Constraint에 있다.** Official
   Block이 비어 있는 동안 Planner가 공식 근거를 주장하지 못하게 하는 장치는
   Packet 안에 있다.

**단, Production 최종 활성화의 조건은 다르다.** Official Context 없이
"공식 자료 기반"이라고 표시하는 것은 금지되며, Official Adapter가 붙기 전까지
그 표현을 쓰지 않는다. 첫 Smoke와 Production 활성화를 구분한다.

내부 설계 문서가 Official Context를 원칙적으로 포함한다는 이유만으로 Blocker
처리하지 않았다. **Raw Official PDF runtime parsing은 추가하지 않았다.**

---

## 답변 — §45 필수 질문

**Q1. 실제 Production Packet 크기는 5 Case 평균 얼마인가?**
Planner-visible canonical JSON **10,282자**, debug render **2,698자**,
내용 문자(활동명·주제 등 자연어만) **924자**. 범위는 JSON 9,557~11,281자다.

**Q2. Prototype의 약 5,407자와 비교해 왜 달라졌는가?**
**측정 대상이 다르다.** Prototype 5,407자는 조립된 **텍스트**였고, L3의 10,282자는
**canonical JSON**이다. 같은 기준(render)으로 재면 2,698자로 오히려 **절반**이다.
줄어든 이유 셋 — ① 기관 이름을 `S1`·`S2`로 익명화, ② Age Contrast 우선
중복 제거(Institution 12 → 8~11), ③ 항목에서 `evidence_id`·`month`·
`source_section` 제거(35자 hex → 3자 `ref`). 늘어난 요인은 Age Context와
Constraint Block이 새로 생긴 것이다.

**Q3. 어떤 Block이 가장 많은 Context를 차지하는가?**
`institution_evidence` **19.2%**(1,975자). 그 뒤가 `other_outdoor` 18.9%,
`week_experience` 16.3%, `reference_activities` 15.6%, `age_contrast` 11.4%,
고정 Header 18.6%다. 어느 한 Block이 지배하지 않는다.

**Q4. Budget 초과 시 어떤 Block부터 줄이는가?**
`other_outdoor → week_experience → institution(최소 4건) → age_contrast(Group 단위)`.
`reference_activities`는 자르지 않는다 — canonical 후보이고 2027-02은 4개뿐이다.
Request·Theme·Week·Age Context·Safety·Constraint·Lineage도 건드리지 않는다.
`random` 없이 ranking 순서를 유지한 채 tail부터 자른다.

**Q5. Age Contrast 관계가 Packet에서도 보존되는가?**
**보존된다.** `AgeContrastGroup(observations=[age→items])` 구조이며 평탄화하지
않는다. Validator가 ① 연령 2개 이상 ② 연령 중복 없음 ③ 모든 항목이 Group과
같은 `source_sha256`임을 고정한다.

**Q6. 2026-06 age contrast 0 → 6 변화는 실제 Source 복원 때문인가?**
**그렇다.** §8 참조. 두 문서 모두 Prototype에서는 outdoor 단일연령 record가
**1건씩**만 추출되어 대조가 성립하지 않았고, L1 cell geometry로 각각 8건·9건이
복원되면서 같은 파일의 다른 면(p1/p2/p3)에 다른 연령이 드러났다. 기관을 섞거나
추론으로 만든 Pair는 없다 — `source_sha256` 동일 · page 상이를 테스트로 고정했다.

**Q7. CONTEXT_ONLY Institution 문장을 직접 Product Output으로 쓸 수 없다는
Contract가 Packet에 보존되는가?**
**보존된다.** 세 겹이다 — 항목마다 `reuse_policy=CONTEXT_ONLY`(payload에서
제거 금지), Constraint의 `source_text_copy_allowed=False` ·
`corpus_direct_output_enabled=False`, 그리고 Validator가 이 둘의 모순을 거부한다.
`CORPUS_EVIDENCE`는 `allowed_activity_origins`에서 빠지되 enum과 priority에는
남는다.

**Q8. Optional Official Block이 비어도 Packet이 정상인가?**
**정상이다.** 5 Case 전부 `official_play_context == ()` ·
`official_topic_context == ()`이고 `validate_packet()`을 통과한다.
`"근거 없음"` 같은 가짜 Evidence 문자열로 채우지 않는다 — 구조적으로 빈 tuple이다.

**Q9. Age3/4/5 Packet이 실제로 차이를 가지는가?**
**가진다.** 2026-07 기준 institution · week experience · other outdoor 모두
만3세∩만4세 겹침 **0**이고 fingerprint가 셋 다 다르다. 만4세∩만5세 겹침 8은
두 연령을 모두 포함하는 혼합연령 면 때문이고, reference 8/8 겹침은 Catalog의
성질이다(§19.4). 연령 근거 강도도 달라진다 — 2027-02 만5세는 STRONG 등급이지만
Packet 내 단일연령 근거가 1건뿐이며, 그 사실을 `single_age_grounding_count`가
드러낸다.

**Q10. L4 GPT-4.1 mini Smoke를 시작할 준비가 되었는가?**
**되었다.** §21 참조. Option A — Official Adapter 없이 첫 Smoke를 시작할 수
있다. 단 Production 최종 활성화에서 "공식 자료 기반"을 표시하려면 Official
Adapter가 선행되어야 하며, 그 구분을 유지한다.

---

```text
MONTHLY LLM PLANNER L3

Packet Contract:
  monthly-context-packet-v0.1.0
  pydantic strict (extra=forbid · frozen=True)
  planning_request · parent_theme · week_slots · age_context
  institution / age_contrast / week_experience / reference / other_outdoor
  official_play · official_topic (빈 tuple)
  safety_context · constraints · source_lineage · trimmed_blocks
  Planner-visible과 Audit-only를 분리. Prompt 문자열은 만들지 않는다

Average Packet Size:
  planner-visible canonical JSON  10,282자  (9,557~11,281)
  debug render                     2,698자  (Prototype 5,407자와 같은 기준)
  내용 문자                          924자

Largest Block:
  institution_evidence 19.2% · other_outdoor 18.9% · week_experience 16.3%
  reference 15.6% · age_contrast 11.4% · 고정 Header 18.6%
  지배하는 Block 없음

Budget Strategy:
  DEFAULT_CHAR_BUDGET = 20,000  (5 Case 전부 미발동 — 그것이 의도다)
  other_outdoor → week_experience → institution(≥4) → age_contrast(Group 단위)
  reference / request / theme / weeks / age / safety / constraints 는 자르지 않는다
  random 없음. ranking 순서 유지 · tail trim · 같은 입력 같은 결과

Age Context:
  기준을 새로 만들지 않았다 — 재감사 §4.1의 4단계·임계값 그대로
  §8·§9의 LOW는 채택하지 않았다 (WEAK/VERY_WEAK를 합치면 새 임의 기준) → OD-N17 OPEN
  세는 대상은 inventory 면 → L1 Evidence Store record로 바뀌었다 (더 보수적)
  등급과 Packet 내용이 어긋날 수 있어 single_age_grounding_count를 사실로 노출
  2027-02 만5세: STRONG(단3)인데 Packet 내 단일연령 근거 1건

Age Contrast:
  Group 구조로 Pair 관계 보존. 평탄화하지 않는다
  2026-06 0 → 6은 실제 Source 복원 (같은 sha · 다른 page · 기관 미혼합, 테스트 고정)
  L2가 Pair를 이루지 못한 행을 반환할 수 있어 L3가 제외 (2026-08 6 → 3)
  Evidence 손실 아님 — Institution Block에 남는다. L2 정밀도 개선 후보로 보고

Week Experience:
  week 필드가 **아예 없다**. None이 아니라 자리를 두지 않았다
  타입 이름도 WeekExperienceCandidate (WeekPlan 아님)
  5 Case 전부 10건

Reference Activities:
  12 / 7 / 8 / 7 / 4  — 후보가 K보다 적으면 전부. 억지로 채우지 않는다
  Budget에서 절대 자르지 않는다

Institution Grounding:
  10 / 10 / 8 / 11 / 11  (L2 12에서 Age Contrast 우선 중복 제거)
  §33~§35 지정 문자열 전부 Packet에 존재 (테스트 고정)

Reuse Policy:
  항목마다 CONTEXT_ONLY 보존 · payload에서 제거 금지
  source_text_copy_allowed=False · corpus_direct_output_enabled=False
  allowed_activity_origins = REFERENCE, LLM_SYNTHESIZED
  CORPUS_EVIDENCE는 enum과 priority에 남긴다 (개념 폐기 아님)
  Validator가 셋의 정합을 고정

Official Context:
  official_play=[] · official_topic=[]  — 5 Case 전부
  가짜 Evidence로 채우지 않는다. Raw Official PDF runtime parsing 없음

Determinism:
  packet_fingerprint = SHA-256(planner-visible 내용 + source lineage)
  같은 Builder 2회 + 새 Store/Builder 1회 동일 · 입력 순서 반전에도 동일
  Theme·Evidence Store가 바뀌면 값이 바뀐다

Performance:
  store+catalog load 0.395s · packet build 5.13ms · 5-case 23.56ms
  L2(2.1ms) 대비 +3ms

Regression:
  1,876 → 2,009 passed, 4 deselected  (+133 신규 · 기존 실패 0)
  승인 Artifact 전부 불변 (SHA 확인) · Evidence Store 무수정
  L2 Retrieval · Generate/Regenerate · LLMPort · Elice Adapter · Prompt
  · Demo · Golden 무변경

L4 Readiness:
  READY_FOR_LLM_PLANNER
  Option A — Official Adapter 없이 첫 Smoke 가능
  단 Production 최종 활성화에서 "공식 자료 기반" 표시는 Official Adapter 선행
```

---

```text
MONTHLY_LLM_PLANNER_L3_COMPLETE
```
