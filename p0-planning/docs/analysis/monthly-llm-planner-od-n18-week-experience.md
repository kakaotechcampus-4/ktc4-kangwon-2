# OD-N18 Resolution — Week Experience Persistence

- 작성일: 2026-09-13
- 선행: L6 GenerateMonthlyPlan Integration 완료 (`MONTHLY_LLM_PLANNER_L6_COMPLETE`)
- 결정: 2026-09-13 Human Decision
- 산출물
  - `data/templates/monthly_template_a_v0_2_0.json` (신규 artifact)
  - `production_monthly_template_repository()` — 두 version 동시 서빙
  - `GenerateMonthlyPlan._fill_focus_from_proposal` + Mode/Template 호환 Gate
  - 테스트 `tests/application/test_monthly_week_experience.py` (20건)
- 범위 밖: L7 Regenerate · Demo · Golden · Production default 전환

---

## 1. 문제

L6에서 확인한 것:

```text
week_axis   role = AXIS   → MonthlySection이 Item 보유를 금지한다
                            ResolvedSection.cell_count_for() = 0
focus       role = CONTENT / WEEKLY_CELLS   → 의미상 맞는 자리
            activated = false (OPTIONAL_DEFAULT_INACTIVE)
```

따라서 L4 Proposal의 `week.experience`를 저장할 곳이 없었다. L6 구현자가 `focus`를
임의 활성화하지 않은 판단은 **유지한다** — 승인 Template 개정은 제품 결정이다.

---

## 2. Decision

### 기존 Template을 수정하지 않는다

`monthly-template-a-v0.1.0`은 **RULE_ONLY 호환용으로 그대로 보존한다.**

```text
data/templates/monthly_template_a.json
SHA  1f35322dd52f832bffc3057953ecbd64d52c2d855ada964af68472ebba1a7c34   불변
```

### 새 version을 추가한다

```text
data/templates/monthly_template_a_v0_2_0.json
template_version   monthly-template-a-v0.2.0
supersedes         monthly-template-a-v0.1.0
SHA                cb3fa9d15ea5ad55…                                    신규
```

두 version이 **공존한다.** v0.2.0이 v0.1.0을 대체하지 않는다.

---

## 3. 무엇이 달라졌나

Section 정의 전수 비교 결과 **`focus` 하나만** 달라졌다.

```text
focus.activated          false → true
focus.activation_basis   OPTIONAL_DEFAULT_INACTIVE
                         → ACTIVATED_FOR_LLM_PLANNER_WEEK_EXPERIENCE
focus.activation_note    추가 (결정 근거)
```

그 밖의 Section은 `display_mode` · `empty_value_policy` · `evidence` ·
`observed_source_labels`까지 **바이트 단위로 같다.**

| version | 활성 Section |
|---|---|
| v0.1.0 | theme · week_axis · outdoor_play · safety_education |
| v0.2.0 | 위 4개 + **focus** |

함께 활성화하지 **않은** Section (§3):

```text
goals · habits · emergency_response · drill ·
indoor_alternative · special_program · event_schedule
```

### week_axis는 그대로다

```text
week_axis   role = AXIS   주차 번호 / 날짜 축
```

AXIS 의미를 바꾸지 않았다. 주차별 중심 경험 문장은 `week_axis`가 아니라 `focus`에
담긴다. `docs/template-a-validation.md` §6.1의 주차 축 판정과 모순되지 않는다.

### 실측 결론은 바뀌지 않았다

`focus`의 관측 근거(6/10)와 `display_mode`(WEEKLY_CELLS, 관측 6기관 중 5)는
v0.1.0 측정 그대로이며 **재측정하지 않았다.** 달라진 것은 "P0에서 이 Section을
기본 활성으로 둘 것인가"라는 제품 결정뿐이다.

---

## 4. Template 선택 (§5)

**Use Case가 Mode를 보고 Template을 몰래 바꾸지 않는다.** Template version은 계속
호출자의 `template_ref`가 정한다.

```text
RULE_ONLY     → monthly-template-a-v0.1.0
LLM_PLANNER   → monthly-template-a-v0.2.0 (focus 활성)
```

`production_monthly_template_repository()`가 두 version을 함께 서빙한다.
**fallback이 아니다** — 요청한 version과 정확히 일치할 때만 반환하고, 못 찾으면
default로 대체하지 않고 `None`을 돌려준다(테스트 고정).

### 부적합 조합은 명확히 실패한다

`LLM_PLANNER`인데 Template에 `focus`가 없으면 Proposal의 주차별 경험이 **조용히
버려진다.** 그것은 silent data loss이므로 막았다.

```text
llm_planner_mode_requires_a_week_experience_section
  generation_mode=LLM_PLANNER에는 `focus`가 활성화된 Template이 필요하다.
  현재 Template monthly-template-a-v0.1.0에는 없다.
  Template을 자동으로 바꾸지 않는다 — 요청의 template_ref를 고쳐라.
```

이 Gate는 **LLM 호출 전에** 동작한다. 비용을 쓰지 않는다(테스트 고정).

---

## 5. Mapping (§6)

```text
proposal.weeks[i].experience  →  focus[week_id]
```

**Week ID의 Source of Truth는 계속 canonical WeekPeriod다.** Proposal의 `week_id`는
검증 anchor이며 L5가 이미 집합·순서 일치를 확인했다.

실측(FakeLLM Proposal, 2026-09 만4세 5주):

```text
2026-09-W1  focus    1주차 가을 경험을 나눠요.        RULE_LLM / evidence 0건
            outdoor  가을 놀이 1                     RULE_LLM / INSTITUTION_SAMPLE
2026-09-W2  focus    2주차 가을 경험을 나눠요.        RULE_LLM / evidence 0건
            outdoor  가을 놀이 2                     RULE_LLM / INSTITUTION_SAMPLE
...
safety      EMPTY_UNRESOLVED × 5

cell 총계    16  (filled 11 / empty_valid 0 / unresolved 5)
```

---

## 6. Provenance (§7)

```text
value              proposal.week.experience
cell_state         FILLED
generation_method  RULE_LLM
rule_id            monthly.llm.evidence_grounded_planner
rule_version       v1
week_order_basis   PLANNER_COMPOSED
evidence           []
```

빈 Evidence의 뜻을 분명히 한다.

> LLM이 전체 Context를 참고해 구성했지만 **특정 EvidenceRecord를 이 문장의 직접
> 근거로 주장하지 않는다.**

"근거가 없다"가 아니다. 생성 방식은 2축(`RULE_LLM`)이 표현하고, Domain은 FILLED
Cell에 Evidence를 요구하지 않는다(`theme`만 예외).

### 하지 않은 것 셋 (테스트로 고정)

```text
Activity의 grounding_refs를 focus Evidence로 복사   하지 않았다
근거 없이 INSTITUTION_SAMPLE 부여                   하지 않았다
week_order_basis = SOURCE_OBSERVED                  하지 않았다
```

`SOURCE_OBSERVED`를 쓰지 않는 이유는 L1 실측이다 — Corpus에 `week_position` 보유
record가 **0건**이다(OD-N14).

---

## 7. RULE_ONLY Freeze (§4)

| 경로 | Template | focus |
|---|---|---|
| RULE_ONLY (기존) | v0.1.0 | Section 자체가 없다 |
| RULE_ONLY + 새 Template | v0.2.0 | `EMPTY_VALID` · `RULE_ONLY` · evidence 없음 |
| LLM_PLANNER | v0.2.0 | `FILLED` · `RULE_LLM` · evidence `[]` |

**RULE_ONLY에 빈 focus Cell을 추가하지 않았다.** 기존 경로는 v0.1.0을 쓰므로
Section이 생기지 않는다. Golden 파일을 수정하지 않았고 기존 결과가 그대로다.

새 Template을 RULE_ONLY로 써도 실패하지 않는다 — 그때는 `focus`가 빈 Cell이 된다.
이 조합을 금지하지 않은 이유: Template과 Mode는 독립 축이고, 빈 Cell은 정상
상태이지 손실이 아니다.

---

## 8. Teacher Edit / Confirm (§8)

`focus` Cell은 다른 CONTENT Cell과 똑같이 동작한다.

```text
DRAFT      교사 수정 가능 → TEACHER_EDITED Audit 기록
CONFIRMED  read-only
```

테스트로 고정했다.

---

## 9. Live Smoke (§11)

**새 Live 호출을 하지 않았다.** L6의 FakeLLM Proposal로 Mapping을 검증했고,
실제 API를 다시 부를 이유가 없었다 — 이번 변경은 Proposal의 이미 존재하는 필드를
어디에 저장하느냐이지 LLM 동작을 바꾸는 것이 아니다.

L6 Application Live Smoke(2026-06 만4세)는 그대로 유효하다. 그 실행이 반환한
Proposal에도 4주치 `experience`가 들어 있었고, 이제 저장된다.

---

## 10. L7 설계 입력 (§9)

**이번 단계에서 focus Regenerate를 구현하지 않았다.**

`focus`가 Generated Cell이 되었으므로 L7에서 Regenerate 대상 범위를 다시 판단해야
한다.

```text
A. outdoor_play만 P0 regenerate
B. focus와 outdoor_play 각각 cell regenerate
```

L7에서 명시적으로 결정한다. `docs/open-decisions.md` 체크리스트에 남겼다.

---

## 11. Tests

```text
이전   2,228 passed, 4 deselected
현재   2,248 passed, 4 deselected      (+20 · 기존 실패 0)
```

| 영역 | 건수 | 내용 |
|---|---:|---|
| Template 계약 | 4 | v0.1.0 불변 · focus만 활성 · week_axis AXIS 유지 · exact resolve(fallback 없음) |
| RULE_ONLY Freeze | 2 | 구 Template에 focus 없음 · 새 Template에서 EMPTY_VALID |
| Mapping | 3 | experience → focus · 주차 수 일치 · FILLED |
| Provenance | 5 | RULE_LLM · evidence `[]` · grounding 미복사 · INSTITUTION_SAMPLE 미주장 · PLANNER_COMPOSED · CREATED Audit |
| Mode/Template 조합 | 2 | 구 Template + LLM_PLANNER 실패 · LLM 미호출 |
| Teacher Edit / Confirm | 2 | DRAFT 수정 가능 · CONFIRMED read-only |
| Persistence | 1 | round trip 보존 |

기존 L6 테스트 26건도 새 Template으로 옮겨 전부 통과한다.

---

## 12. Source of Truth 갱신

```text
docs/open-decisions.md              OD-N18 CLOSED + 결정 내용 · L7 체크리스트
docs/template-a-validation.md       §13 Template version 추가 이력 (신규)
docs/analysis/...-l6-...md          §16.1에 해소 표시
data/templates/monthly_template_a_v0_2_0.json   신규 artifact
```

**기존 Template A artifact를 덮어쓰지 않았다.**

---

```text
OD-N18 RESOLUTION

Decision:
  기존 승인 Template을 수정하지 않고 새 version을 추가한다 (2026-09-13 Human Decision)

Old Template:
  UNCHANGED
  monthly-template-a-v0.1.0 · SHA 1f35322dd52f832b… 불변
  RULE_ONLY 호환용으로 계속 사용

New Template:
  monthly-template-a-v0.2.0  (data/templates/monthly_template_a_v0_2_0.json)
  supersedes v0.1.0 이지만 **대체하지 않는다** — 두 version 공존
  Section 전수 비교: focus 하나만 다르다
  goals·habits·emergency_response·drill·indoor_alternative·
  special_program·event_schedule 은 함께 켜지 않았다

focus:
  ACTIVE / WEEKLY_CELLS
  관측 근거 6/10 · display_mode 판정은 v0.1.0 측정 그대로 (재측정 없음)

week_axis:
  UNCHANGED / AXIS
  주차 번호·날짜 축. AXIS 의미를 바꾸지 않았다

Week Experience Mapping:
  proposal.weeks[i].experience → focus[week_id]
  Week ID Source of Truth는 canonical WeekPeriod · Proposal week_id는 검증 anchor

Provenance:
  RULE_LLM / monthly.llm.evidence_grounded_planner / v1
  evidence = []   ("근거 없음"이 아니라 "특정 record를 인용하지 않음")
  PLANNER_COMPOSED
  Activity grounding 미복사 · INSTITUTION_SAMPLE 미주장 · SOURCE_OBSERVED 미사용

Template 선택:
  호출자의 template_ref가 정한다. Use Case가 몰래 바꾸지 않는다
  LLM_PLANNER + focus 없는 Template → LLM 호출 전에 명확히 실패
  (silent data loss를 만들지 않는다)

RULE_ONLY:
  UNCHANGED
  v0.1.0에는 focus Section 자체가 없다 · Golden 무수정
  v0.2.0을 RULE_ONLY로 써도 실패하지 않으며 focus는 EMPTY_VALID

Teacher Edit / Confirm:
  DRAFT focus 수정 가능 → TEACHER_EDITED · CONFIRMED 후 read-only

Live Smoke:
  새 호출 없음 (§11). FakeLLM Proposal로 Mapping 검증
  L6 Application Live Smoke 결과는 그대로 유효

Regression:
  2,228 → 2,248 passed, 4 deselected  (+20 · 기존 실패 0)
  승인 Artifact 전부 불변 (SHA 확인) · Golden 무수정
  Demo · Regenerate · Prompt v0.1.1 · L2 · L3 · L5 무변경

L7 입력:
  focus가 Generated Cell이 되었으므로 Regenerate 대상 범위를 L7에서 결정한다
  (A. outdoor_play만 / B. focus·outdoor_play 각각) — 이번에 임의 구현하지 않았다

OD-N18:
  CLOSED

L7 Readiness:
  READY_FOR_REGENERATE_INTEGRATION
```

---

```text
MONTHLY_LLM_PLANNER_OD_N18_COMPLETE
```
