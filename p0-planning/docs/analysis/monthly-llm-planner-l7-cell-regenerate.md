# Monthly LLM Planner vNext — L7 Cell Regenerate Integration

- 작성일: 2026-09-13
- 선행: L6 Generate Integration · OD-N18 Week Experience Persistence 완료
- 산출물
  - `src/ssuksak/shared/llm/monthly_cell.py` — Cell Regeneration Contract
  - `src/ssuksak/planning/planner/cell_prompt.py` — Cell Prompt (focus / outdoor)
  - `src/ssuksak/planning/rules/monthly_llm_cell_validation.py` — Cell Validator
  - `src/ssuksak/planning/application/monthly_llm_cell_regeneration.py` — 오케스트레이션
  - `RegenerateMonthlyPlanItem` LLM 경로 · `LLMPort.regenerate_monthly_cell`
  - 테스트 `tests/application/test_regenerate_monthly_llm_cell.py` (33건)
  - Live Smoke `analysis/experiments/monthly_llm_vnext/live_regenerate_smoke_l7.py`
- 범위 밖: L8 Demo · L9 Golden/Freeze · Production default 전환 ·
  Official Adapter · Activity v0.2.2

---

## 1. Regenerate Targets

Product Decision **B**를 구현했다.

```text
focus          주차별 중심 경험      LLM 재생성
outdoor_play   주차별 바깥놀이 활동   LLM 재생성

theme          parent anchor에서 Rule로 재파생 (LLM 아님)
week_axis      축이므로 Cell이 없다
safety_education  배치 source 없음 (OD-M04). 계속 차단
```

`theme`을 LLM 대상에 넣지 않았다 — 확정 Yearly에서 파생하는 값이므로 LLM이
만들 것이 없다. 테스트가 LLM Plan에서도 `theme` 재생성이 `RULE_ONLY`로
동작하고 provider call이 0임을 고정한다.

---

## 2. 핵심 — Cell Only

**Target Cell 하나만 바뀐다.** 테스트가 Plan 전체 Cell의
`(값, cell_state, generation method, rule_id, evidence, audit 길이)`를 뜬 뒤
변경된 key 집합이 정확히 `{(section, week)}` 하나임을 확인한다.

```text
2026-06-W3 outdoor_play Regenerate
  바뀐 Cell  ['outdoor_play/2026-06-W3']

2026-06-W3 focus Regenerate
  바뀐 Cell  ['focus/2026-06-W3']
```

같은 주의 다른 Cell · 다른 주차 · Theme · Safety · Parent lineage ·
Template ref · Activity catalog pin · Plan status 전부 그대로다.

---

## 3. 발견 — `MonthlyGenerationRun`은 저장되지 않는다

L6 보고서 §12는 `generation_mode`를 Run에 기록했다고 적었고, L6 지시문 §30은
"나중에 Plan만 보고 어느 경로에서 나왔는지 확인할 수 있어야 한다"고 했다.

**그런데 Repository는 Plan만 저장한다.** `MonthlyPlanRepository.save(plan)`이
전부이고 Run은 호출자에게 반환되는 transient 값이다. 따라서 저장된 Plan에서
Run의 `generation_mode`를 다시 읽을 수 없다.

L6에서 이 점을 확인하지 못했다. 정정한다.

### 처리

Plan 안에 **이미 있는 값**에서 파생한다. LLM Planner가 남긴
`GenerationMethod.RULE_LLM` + planner `rule_id`가 Item에 그대로 있다.

```python
def plan_generation_mode(plan) -> MonthlyGenerationMode:
    for section in plan.sections:
        for item in section.items:
            if (item.generation.method is GenerationMethod.RULE_LLM
                    and item.generation.rule_id == PLANNER_RULE_ID):
                return MonthlyGenerationMode.LLM_PLANNER
    return MonthlyGenerationMode.RULE_ONLY
```

새 필드를 Plan에 추가하지 않았다 — 같은 사실을 두 곳에 저장하면 어긋날 수
있고, Provenance는 이미 그 정보를 정확히 담고 있다.

**Mode Source of Truth는 Plan의 Provenance다**(§26). 요청이 `generation_mode`를
명시하면 그것과 **일치해야** 하고, 다르면 `regenerate_mode_must_match_the_plan_generation_path`로
실패한다. 환경이나 LLM 가용성을 보고 바꾸지 않는다.

이것은 Run에 `generation_mode`를 둔 것이 쓸모없다는 뜻은 아니다 — 생성
직후의 관측·telemetry에는 여전히 쓰인다. 다만 **영속 조회의 근거는 아니다.**

---

## 4. Full-month Context, Target-only Output (§3·§4)

**한 달 전체를 다시 만든 뒤 Target만 꺼내 쓰지 않았다.** 새 Port method를
additive하게 추가했다.

```text
plan_monthly              한 달 전체 구성        (L4, 변경 없음)
regenerate_monthly_cell   Cell 하나만 다시 쓴다   (L7, 신규)
```

보여주는 범위와 바꾸는 범위를 분리했다.

```text
보여준다   모든 주차의 focus · outdoor_play + Theme + 연령 근거 + Evidence
바꾼다     Target Cell 하나
```

Prompt는 현재 계획 전체를 나열하고 Target 칸에 `★` 표시를 붙인다. 같은 주의
paired Cell은 `(고정)`으로 명시한다.

```text
# 지금 한 달 계획
아래가 현재 계획입니다. **★ 표시된 칸 하나만** 다시 씁니다.
- 2026-06-W3
    중심 경험: 우리 동네 지도를 보며 직접 산책하며 …
    바깥놀이: 우리 동네 지도 보며 산책하기 ★ 이 칸을 다시 씁니다
```

Output Schema에 **다른 주차·다른 Section을 담을 자리가 없다.** 자리를 만들면
모델이 채운다.

기존 `plan_monthly` · `polish_theme` · `polish_themes`의 의미는 바꾸지 않았다.

---

## 5. Output Contract

```text
MonthlyCellRegenerationProposal
  target_week_id           요청한 주차 그대로
  target_section_key       focus | outdoor_play
  value
  activity_origin          outdoor만. focus는 null
  reference_activity_id    REFERENCE만
  grounding_refs[]         SYNTHESIZED만
```

`reconcile_cell_proposal()`이 계약 형태를 본다 — 다른 주차/Section을 답했는지,
focus가 활동 필드를 달고 왔는지, REFERENCE label이 일치하는지,
SYNTHESIZED가 grounding을 가졌는지.

---

## 6. Cell Validator (§9~§12)

`validate_cell_proposal()`이 L5와 **같은 정책·같은 Violation 어휘**를 쓴다.
`ProposalViolationCode`를 새로 만들지 않았다 — 같은 위반을 다른 이름으로 부르면
repair 분류와 UI가 두 벌이 된다.

| 검사 | focus | outdoor |
|---|:---:|:---:|
| Packet fingerprint | ✓ | ✓ |
| 금지 Claim / Safety 누출 / 식별자 누출 | ✓ | ✓ |
| 같은 달 중복 (정규화 완전 일치) | ✓ | ✓ |
| 같은 달 `reference_activity_id` 중복 | — | ✓ |
| CONTEXT_ONLY exact copy | — | ✓ |
| grounding 존재·적격·연령 | — | ✓ |
| REFERENCE Packet 포함·연령 지원 | — | ✓ |
| Provenance 완결성 | ✓ | ✓ |

### 하지 않은 것 (§12·§36)

`focus`와 `outdoor`가 **의미적으로 잘 어울리는가**를 코드가 판단하지 않는다.
대신 Prompt에 paired Cell을 반드시 보여주고 연결을 요청한다. semantic coherence
scorer · embedding similarity · LLM-as-a-judge를 만들지 않았다.

### Target 자신의 기존 값 (§10)

Target이 기존과 같은 값으로 다시 나오는 것을 **막지 않았다.** 기존 Rule
Regenerate가 동일 값을 성공으로 다루므로(theme은 명시적으로, outdoor는
`current_activity_id` penalty로) 그 의미를 바꾸지 않는다. "재생성했는데 같은
결과"를 막으려면 새 Product Decision이 필요하다.

`siblings`에서 Target을 제외하는 것이 그 지점이다.

---

## 7. Provenance (§8·§19)

### focus

```text
cell_state         FILLED
generation_method  RULE_LLM
rule_id            monthly.llm.evidence_grounded_planner
rule_version       v1
evidence           []
week_order_basis   PLANNER_COMPOSED
```

빈 Evidence는 "근거가 없다"가 아니라 **"특정 EvidenceRecord를 이 문장의 직접
근거로 주장하지 않는다"**는 뜻이다(OD-N18과 같은 의미). Activity의
`grounding_refs`를 복사하지 않았다 — 테스트로 고정.

### outdoor REFERENCE

```text
ACTIVITY_REFERENCE + activity_id + pinned catalog_version
RULE_LLM / 같은 rule_id / v1
```

### outdoor LLM_SYNTHESIZED

```text
INSTITUTION_SAMPLE + 실제 record_id + Evidence Store SHA
RULE_LLM / 같은 rule_id / v1
```

Generate(L6)와 **같은 계약**이다. origin 전환(REFERENCE ↔ SYNTHESIZED)도
자연스럽게 동작한다 — Evidence가 통째로 교체되기 때문이다.

---

## 8. Exact Version Pin (§13·§14)

`outdoor_play` REFERENCE Evidence의 `source_version`은 **Plan이 pin한
catalog_version**이다. 기존 `_load_pinned_catalog()`를 그대로 쓴다 —
Production default로 대체하지 않고, 못 찾으면 실패한다.

Plan-level lineage(`template_ref` · `activity_catalog` · `parent_lineage`)를
현재 최신값으로 **바꾸지 않는다.** 테스트로 고정했다.

### 보고 — Evidence Store historical resolution은 없다 (§14)

Evidence Store는 현재 **단일 Artifact 하나**만 서빙한다
(`JsonInstitutionEvidenceRepository`). Plan 생성 시점의 Evidence Store SHA가
현재 것과 다르면 그것을 다시 찾을 방법이 없다.

L7에서 그 Infrastructure를 만들지 않았다. 지금은 Store가 하나뿐이라 문제가
드러나지 않지만, **Evidence Store v0.2가 나오면 실제 문제가 된다.** silent
fallback을 만들지 않았고 아래에 Open Issue로 남겼다(§14.1).

Template은 v0.1.0/v0.2.0 두 version을 이미 exact resolve한다(OD-N18).

---

## 9. Repair (§22)

L6와 **같은 정책**을 재사용했다. 새 정책을 만들지 않았다.

```text
transport retry        Adapter   LLM_MAX_RETRIES (1)
Cell contract repair   Adapter   MAX_REPAIR_ATTEMPTS (1)
Cell validation repair L7        MAX_CELL_VALIDATION_REPAIR_ATTEMPTS (1)
```

Repair 요청은 **같은 Packet·같은 snapshot**으로 다시 묻는다. Retrieval을
되풀이하지 않고, 원래 본문에 범주 수준 수정 요청만 덧붙인다. 위반한 Source
문장을 다시 노출하지 않는다(테스트 고정).

Non-repairable이면 재호출하지 않는다 — `PROVENANCE_INCOMPLETE`에서 provider
call이 1회에 멈추는 것을 고정했다.

---

## 10. Atomicity (§23·§24)

Mutation은 최종 Validation 이후에만 일어나고, Domain Validation이 실패하면
기존 `_CellSnapshot.restore()`가 값·상태·Audit를 되돌린다. Evidence와
Generation도 함께 복원한다.

테스트로 고정한 것:

| 상황 | Plan | save |
|---|---|---:|
| 성공 | Target 1 Cell만 변경 | +1 |
| LLM unavailable | 완전히 그대로 | +0 |
| L7 Validator 거부 | 완전히 그대로 | +0 |
| repair 후에도 거부 | 완전히 그대로 | +0 |
| Regenerator 미주입 | 완전히 그대로 | +0 |
| CONFIRMED | 완전히 그대로 | +0 |

"완전히 그대로"는 저장된 Plan의 전체 Cell snapshot이 byte 단위로 같음을 뜻한다.

---

## 11. Teacher Edit (§17)

```text
명시적으로 Regenerate를 누른 Target Cell   → AI 값으로 교체 가능
누르지 않은 Teacher-edited Cell            → 절대 바뀌지 않는다
```

Audit history는 지워지지 않는다.

```text
CREATED → TEACHER_EDITED → REGENERATED
```

세 event가 모두 남는 것을 테스트로 고정했다.

---

## 12. Audit (§18)

Target Cell에 `REGENERATED` event를 남긴다.

```text
event_type       REGENERATED
occurred_at      clock
actor_id         opaque ActorId
previous_value / new_value
previous_method / new_method
plan_id / item_id
```

기존 `AuditEvent` schema를 그대로 쓴다. 새 민감정보를 저장하지 않는다.

---

## 13. Confirmed Gate (§16·§32)

`plan.ensure_mutable()`이 Cell 해소보다 **먼저** 동작하므로 CONFIRMED Plan에서는
`focus`·`outdoor_play` 둘 다 provider call **0회**로 차단된다. 테스트로 고정.

---

## 14. RULE_ONLY 회귀 (§25)

기존 Rule 기반 Regenerate의 ranking·candidate semantics를 바꾸지 않았다.
historical exact catalog pin도 그대로다.

기존 테스트 `test_regenerate_uses_no_llm`은 "LLM 속성이 없다"를 검증했는데,
L7이 `llm_cell_regenerator` 주입 지점을 추가하므로 전제가 성립하지 않는다.
**삭제하지 않고 더 강한 불변으로 바꿨다**(L6 §3.1과 같은 판단) —
`test_rule_only_regenerate_never_uses_the_llm`은 호출하면 예외를 던지는
Regenerator를 주입한 뒤 RULE_ONLY 재생성이 정상 성공함을 확인한다.

계약 변경이므로 명시적으로 기록한다.

---

## 15. Live Regenerate Smoke (§34·§35)

```text
LIVE_GPT_4_1_MINI  (Cell Regenerate)
  model       openai/gpt-4.1-mini
  target      2026-06 만4세 · 우리 동네
  repository  InMemory (격리)

  GENERATE    OK (6,219ms)
    W1  focus 우리 동네 다양한 장소의 모습을 알고 친근함을 느껴요.
        outdoor 모래 위에 그리는 우리 동네
    W2  focus 우리 동네에서 일하는 분들과 그 역할을 알아가요.
        outdoor 우리 동네에서 일하는 분 찾아보기
    W3  focus 우리 동네 지도를 보며 직접 산책하며 자연과 삶터를 경험해요.
        outdoor 우리 동네 지도 보며 산책하기
    W4  focus 우리 동네를 자유롭게 표현하며 즐거운 동네 생활을 상상해요.
        outdoor 분필로 내가 되고 싶은 직업 그림 그리기
```

### outdoor_play 재생성 (2026-06-W3)

```text
RESULT           OK (1,748ms) · provider calls 1 · repairs 0
이전             우리 동네 지도 보며 산책하기
새 값            우리 동네 모습 탐색하며 걷기
origin           LLM_SYNTHESIZED   grounding ['E13']
paired focus     우리 동네 지도를 보며 직접 산책하며 …  (고정)

바뀐 Cell        ['outdoor_play/2026-06-W3']
```

### focus 재생성 (2026-06-W3)

```text
RESULT           OK (2,109ms) · provider calls 1 · repairs 0
이전             우리 동네 지도를 보며 직접 산책하며 자연과 삶터를 경험해요.
새 값            우리 동네 곳곳을 직접 걸으며 주변의 자연과 생활 모습을 느껴봐요.
paired outdoor   우리 동네 모습 탐색하며 걷기  (고정)

바뀐 Cell        ['focus/2026-06-W3']
```

### 품질 관찰 (PASS/FAIL 판정 아님)

- **Target만 바뀌었다.** 두 번 모두 기대 집합과 정확히 일치.
- **paired Cell과 연결된다.** outdoor를 `우리 동네 모습 탐색하며 걷기`로 바꾼
  뒤 focus 재생성이 그 새 값을 보고 `직접 걸으며 … 느껴봐요`로 맞췄다 —
  두 번째 요청이 갱신된 snapshot을 본다는 뜻이다.
- **다른 주차 보존.** W1·W2·W4 전부 그대로.
- origin: SYNTHESIZED 1건(grounding E13) · REFERENCE 0건. 이번 달은 승인 후보
  4개를 이미 다 쓰고 있어 중복 차단에 걸리므로 합성을 고른 것으로 보인다 —
  1회 관찰이며 일반화하지 않는다.
- repair 0회 · 총 provider call 3회(생성 1 + 재생성 2).

API Key · Base URL · Prompt 전문을 출력하거나 저장하지 않았다(스캔 확인).

---

## 16. Tests

```text
이전   2,248 passed, 4 deselected
현재   2,281 passed, 4 deselected      (+33 · 기존 실패 0)
```

| 영역 | 건수 |
|---|---:|
| Mode 파생 / 불일치 차단 | 3 |
| focus 재생성 (target-only · 값 · paired 보존 · provenance · 전체 Context) | 5 |
| outdoor 재생성 (SYNTHESIZED · REFERENCE · paired 보존 · Context) | 5 |
| 중복 / exact-copy / Safety 누출 | 4 |
| Atomicity (LLM 실패 · 검증 실패 · save 1회 · 미주입) | 4 |
| Repair (성공 · 실패 원자성 · non-repairable · 같은 Packet) | 4 |
| Gate / Audit / Teacher Edit | 5 |
| Lineage / theme / safety / snapshot 순서 | 3 |

Golden 파일을 수정하지 않았다. 실제 API를 호출하는 테스트는 없다.

---

## 17. Open Issues

### 17.1 Evidence Store historical resolution 없음 (§14)

Evidence Store Repository가 단일 Artifact만 서빙한다. Plan이 pin한 SHA와 현재
Store가 다를 때 과거 Store를 해소할 경로가 없다.

**지금은 Store가 하나뿐이라 드러나지 않는다.** silent fallback을 만들지
않았으므로 조용히 틀린 근거를 쓰는 일은 없지만, Evidence Store v0.2가 나오면
과거 Plan의 재생성이 새 Store로 Retrieval하게 된다. Template·Catalog와 달리
exact pin resolution이 없다.

→ Evidence Store 다음 version 발행 전에 결정해야 한다. **L7을 막지 않는다.**

### 17.2 동시 Teacher Edit 위험 (§33)

Domain에 revision도 `updated_at`도 optimistic concurrency도 없다. LLM 호출
(1.7~2.1초) 중에 다른 Teacher Edit가 들어오면 오래된 Context로 만든 값이
저장될 수 있다.

**새 동시성 제어 장치를 L7에서 만들지 않았다**(§33 지시). 대신 요청이 어떤 Plan
상태를 보고 만들어졌는지 `plan_snapshot_fingerprint`로 telemetry에 남겨
**관측 가능하게** 했다. 막지는 못하고 나중에 알아볼 수는 있다.

→ 실제 다중 사용자 편집이 생기기 전에 결정해야 한다.

### 17.3 OD-N04 — 닫지 않았다

L7 Live에서도 repair 0회였다. call budget은 확정됐다.

```text
정상 재생성        1 call
L5 repair          2 call
Cell contract repair  2 call
worst case (transport + contract + validation)  4 call
```

여전히 **repair 실제 발생 빈도 표본이 얇다.** L8 Demo에서 관측한 뒤 정한다.

### 17.4 계약 변경 1건

`test_regenerate_uses_no_llm` → `test_rule_only_regenerate_never_uses_the_llm`
(§14).

### 17.5 그대로 둔 것 (§36)

```text
Demo 전환 · Golden 갱신 · Production default 전환
Official Adapter · Activity v0.2.2
semantic coherence scorer · embedding similarity · LLM-as-a-judge
OD-N17 · L2 Contrast precision
```

---

## 18. L8 Readiness

| L8 요구 | L7 제공 |
|---|---|
| Cell 단위 재생성 UI | `focus` · `outdoor_play` 각각 독립 동작 |
| 무엇이 바뀌는지 예측 가능 | Target 1 Cell만. 테스트로 고정 |
| 실패 시 화면 상태 | 원 Plan 완전 보존 |
| 재생성 사유 표시 | `cell_regeneration` outcome (origin · repair · 위반 code) |
| 확정 후 차단 | provider call 0으로 차단 |
| 교사 수정 보호 | 누르지 않은 Cell은 불변 |

---

## 답변 — §39 필수 질문

**Q1. focus와 outdoor_play가 각각 Cell-only Regenerate 되는가?**
**된다.** 두 Section 모두 독립적으로 동작하고, Live Smoke에서 각각
`['focus/2026-06-W3']` · `['outdoor_play/2026-06-W3']` 하나만 바뀌었다.

**Q2. Target 외 Cell이 값·provenance 수준에서 모두 보존되는가?**
**보존된다.** 모든 Cell의 `(값, cell_state, generation method, rule_id,
evidence, audit 길이)`를 뜬 뒤 변경 key 집합이 정확히 하나임을 테스트가 고정한다.

**Q3. focus Regenerate가 paired outdoor를 Context로 보되 수정하지 않는가?**
**그렇다.** Prompt에 `같은 주의 바깥놀이(고정)`으로 들어가고, 재생성 후 그 Cell의
값과 Evidence가 그대로임을 테스트가 확인한다.

**Q4. outdoor Regenerate가 paired focus를 Context로 보되 수정하지 않는가?**
**그렇다.** 같은 방식으로 고정했다. Live에서 focus 문장이 Prompt에 실제로
포함됐음을 확인했다.

**Q5. REFERENCE / SYNTHESIZED Provenance가 Generate와 동일한 계약을 유지하는가?**
**유지한다.** REFERENCE는 `ACTIVITY_REFERENCE` + activity_id + **pin된**
catalog_version, SYNTHESIZED는 `INSTITUTION_SAMPLE` + 실제 record_id +
Evidence Store SHA. 둘 다 `RULE_LLM` + 같은 rule_id/version이다.

**Q6. focus는 RULE_LLM + evidence=[] + PLANNER_COMPOSED로 정직하게 저장되는가?**
**그렇다.** Activity의 `grounding_refs`를 복사하지 않고, 근거 없이
`INSTITUTION_SAMPLE`을 주장하지 않는다. 테스트로 고정.

**Q7. Teacher-edited Target을 명시적으로 Regenerate했을 때 Audit history가
보존되는가?**
**보존된다.** `CREATED → TEACHER_EDITED → REGENERATED` 세 event가 모두 남는다.
누르지 않은 Teacher-edited Cell은 값도 Audit도 변하지 않는다.

**Q8. CONFIRMED Plan에서는 Provider 호출 전에 차단되는가?**
**차단된다.** `ensure_mutable()`이 Cell 해소보다 먼저 동작해 `focus`·
`outdoor_play` 둘 다 provider call 0 · save 0이다.

**Q9. Exact pinned Template / Catalog / Evidence lineage를 유지하는가?**
Template과 Catalog는 **유지한다** — Plan이 pin한 version을 exact resolve하고
최신값으로 바꾸지 않는다(테스트 고정). **Evidence Store는 historical
resolution 자체가 없다** — §17.1에 Open Issue로 기록했다.

**Q10. Artifact version이 없을 때 latest로 fallback하지 않는가?**
**하지 않는다.** Catalog는 기존 `_load_pinned_catalog()`가 못 찾으면 실패하고,
Template Repository도 exact match가 아니면 `None`을 돌려준다. Evidence Store는
대체 경로 자체를 만들지 않았다.

**Q11. Repair 실패 시 원 Plan이 완전히 그대로인가?**
**그렇다.** provider call 2회 후 실패하고 save 0, 저장된 Plan의 전체 Cell
snapshot이 이전과 동일하다.

**Q12. Live Regenerate Smoke가 성공했는가?**
**성공했다.** outdoor 1건(1,748ms) · focus 1건(2,109ms), 각각 1 call · repair 0.
두 번 모두 Target Cell만 바뀌었고 paired Cell과 자연스럽게 이어졌다.

**Q13. L8 Demo에서 focus와 outdoor 각각 Regenerate UI를 노출해도 되는
상태인가?**
**된다.** §18 표대로 Cell 단위 동작·실패 시 원상 보존·확정 후 차단·교사 수정
보호가 모두 준비됐다. 다만 §17.2의 동시 편집 위험은 다중 사용자 편집을 붙이기
전에 결정해야 한다.

---

```text
MONTHLY LLM PLANNER L7

Regenerate Targets:
  focus · outdoor_play  (Product Decision B)
  theme은 Rule 재파생 · week_axis는 축 · safety는 계속 차단

Target-only Mutation:
  Plan 전체 Cell의 값·상태·Provenance·Audit를 비교해 변경 key가 정확히 1개
  Live 2건 모두 기대 집합과 일치

Focus:
  RULE_LLM / monthly.llm.evidence_grounded_planner / v1
  evidence = []  · PLANNER_COMPOSED
  Activity grounding 미복사 · INSTITUTION_SAMPLE 미주장

Outdoor REFERENCE:
  ACTIVITY_REFERENCE + activity_id + **pin된** catalog_version
  value == 승인 label (reconcile이 확인)

Outdoor SYNTHESIZED:
  INSTITUTION_SAMPLE + 실제 record_id + Evidence Store SHA
  exact-copy · grounding 적격 · 연령 검사 전부 L5와 같은 정책

Frozen Cells:
  같은 주의 paired Cell · 다른 모든 주차 · theme · safety
  parent lineage · template ref · activity catalog pin · plan status

Pinned Lineage:
  Template v0.1.0/v0.2.0 exact resolve · Catalog exact resolve
  latest fallback 없음
  **Evidence Store historical resolution은 없다** → Open Issue

Repair:
  L6와 같은 정책 재사용 (새 정책 없음)
  transport 1 · cell contract 1 · cell validation 1
  같은 Packet·같은 snapshot 재사용 · 원문 미노출 · non-repairable이면 재호출 없음

Atomicity:
  성공 save 1 · 실패 save 0 · 실패 시 Plan 전체 snapshot 동일
  부분 mutation 없음

Teacher Edit:
  누른 Target만 교체 가능 · CREATED → TEACHER_EDITED → REGENERATED 보존
  누르지 않은 Teacher-edited Cell은 불변

Confirmed Gate:
  focus · outdoor 둘 다 provider call 0 · save 0으로 차단

Audit:
  REGENERATED + actor + timestamp + old/new value + old/new method
  기존 schema 그대로. 새 민감정보 없음

Live Smoke:
  2026-06 만4세 · InMemory 격리
  outdoor 1,748ms (SYNTHESIZED, grounding E13) · focus 2,109ms
  각각 provider call 1 · repair 0 · Target Cell만 변경

Provider Calls:
  정상 1 · repair 2 · worst case 4

Regression:
  2,248 → 2,281 passed, 4 deselected  (+33 · 기존 실패 0)
  승인 Artifact 전부 불변 (SHA 확인) · Golden 무수정
  Demo · Prompt v0.1.1 · L2 · L3 · L5 · Generate 무변경

Open Issues:
  **MonthlyGenerationRun은 저장되지 않는다** — Mode를 Item Provenance에서 파생
    (L6 §12·§30 서술 정정)
  Evidence Store historical resolution 없음 — Store v0.2 발행 전 결정 필요
  동시 Teacher Edit 위험 — 새 동시성 장치를 만들지 않고 fingerprint로 관측만
  OD-N04 미종료 — call budget 확정, repair 발생 빈도 표본 부족
  계약 변경 1건 — RULE_ONLY LLM 격리 테스트를 더 강한 불변으로 대체

L8 Readiness:
  READY_FOR_DEMO_INTEGRATION
```

---

```text
MONTHLY_LLM_PLANNER_L7_COMPLETE
```
