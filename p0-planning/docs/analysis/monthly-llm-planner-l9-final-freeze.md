# Monthly LLM Planner vNext — L9 Golden / E2E / Final Freeze

- **작업일:** 2026-09-14
- **단계:** L9 (최종)
- **결과:** `MONTHLY_LLM_PLANNER_L9_COMPLETE` / `MONTHLY_PLAN_LLM_PLANNER_V1_FROZEN`
- **회귀:** 2,359 passed · 4 deselected (착수 시점 2,301 → +58)
- **Credential 없이:** 2,352 passed · 6 skipped · 0 failed

---

## 1. 이 단계가 한 일

L2~L8이 만든 것을 **고정**했다. 새 기능을 만들지 않았다.

고정한 것은 세 층이다.

```text
Application 계약    무엇이 저장되고 무엇이 차단되는가        Golden
Artifact            그 계약이 어떤 byte 위에서 성립했는가     SHA Freeze
구현 상수           지금 어떤 값으로 돌고 있는가             Freeze (결정 종결 아님)
```

세 층을 나눈 이유가 있다. **Artifact가 바뀌면 Golden이 여전히 통과하더라도 같은
계약이 아니다.** 승인 Template을 새로 발행하거나 Evidence Store를 다시 빌드하면
Golden은 아무 말도 하지 않는다 — 그래서 SHA를 따로 고정했다.

---

## 2. 추가한 것

| 파일 | 성격 | 규모 |
|---|---|---|
| `tests/golden/monthly_llm_cases.json` | LLM 경로 Contract Golden 선언 | 16 case |
| `tests/golden/monthly_llm_harness.py` | 결정론 조립 (FakeLLM) | — |
| `tests/golden/test_monthly_llm_cases.py` | Golden 실행 | 30 test |
| `tests/golden/test_monthly_llm_freeze.py` | Artifact SHA · 상수 · Secret 위생 | 21 test |
| `tests/dev/test_demo_route_e2e.py` | Demo route 결정론 E2E | 9 test |

수정한 것은 두 곳뿐이다.

- `demo-planning/backend/composition.py` — `llm=` 주입 seam 추가
- `demo-planning/backend/app.py` — `Session(llm=...)` 전달

둘 다 **Composition Root**다. Use Case·Domain·Rule·Validation은 L9에서 한 줄도
바뀌지 않았다.

---

## 3. Golden을 두 개로 나눈 결정 (§2·§3)

L8이 남긴 질문은 "Golden을 어느 경로 기준으로 고정할 것인가"였다. 답은 **둘 다,
단 서로 다른 파일로**다.

```text
monthly_cases.json       43 case   Rule 경로   LLM 0회 · 23ms · 완전 결정론
monthly_llm_cases.json   16 case   LLM 경로    FakeLLM 고정 Proposal
```

### 3.1 Rule-only Golden은 한 byte도 바뀌지 않았다

```text
monthly_cases.json   c605641232d91abd1d6d2babb52a45b81ff8ea9de4c9bb3190cd68b5c62c85a7
yearly_cases.json    7918e9f9cbe23580e7621e2f7c7ce40825a073afb8b0dc2038640a1291a6b384
```

이 두 SHA를 `test_the_rule_only_golden_suite_is_untouched`가 검사한다. LLM 작업이
기존 Golden expected를 덮어썼는지를 **테스트가** 감시하게 만든 것이지, 내가
"안 건드렸다"고 주장하는 것이 아니다.

### 3.2 LLM Golden이 고정하는 것과 하지 않는 것

**고정한다.** mode · template version · status · theme provenance · canonical
week id · focus/outdoor provenance · 안전교육 의미 · Evidence source type ·
저장 횟수 · provider 호출 횟수 · Audit chain · 차단 규칙 식별자.

**고정하지 않는다.** 실제 GPT가 만든 experience 문장, `LLM_SYNTHESIZED` 활동명,
`month_flow_rationale` 자연어.

이유는 하나다. 모델이 **정상적인 다른 문장**을 만들었을 때 회귀 실패가 되면
Golden은 품질 장치가 아니라 방해물이 된다. 자연어 품질은 §11의 Live Quality
Smoke가 사람 관찰로 다룬다.

### 3.3 Fake는 Planner를 흉내 내지 않는다

`FakeLLM.plan_monthly`는 테스트가 명시적으로 설정한 Proposal만 돌려준다. 한 달
흐름을 구성하는 로직을 Fake가 재현하면, 테스트는 계약이 아니라 **Fake를**
검증하게 된다.

대신 반환 전에 실제 Adapter와 **같은 `reconcile_monthly_proposal`**을 태운다.
그래서 Fake를 쓰는 Golden도 실제 계약과 같은 경계를 본다.

---

## 4. 고정 Fixture (§5)

| Case | 월 | 주차 | 구성 |
|---|---|---|---|
| A `case_a_reference_only` | 2026-06 | 4 | 전 주차 REFERENCE |
| B `case_b_mixed` | 2026-07 | 5 | REFERENCE / SYNTHESIZED / REFERENCE / SYNTHESIZED / REFERENCE |

Case B가 섞인 구성인 이유는 **한 Cell이 두 축을 동시에 주장하지 않는지**를 봐야
하기 때문이다. Golden은 모든 outdoor Cell에 대해 다음을 확인한다.

```text
ACTIVITY_REFERENCE 있음  XOR  INSTITUTION_SAMPLE 있음
```

승인 Catalog에서 **고른** 값과 Corpus를 근거로 **새로 쓴** 값은 다른 것이고,
Provenance가 그 차이를 잃으면 "이 값의 근거는 무엇인가"에 답할 수 없다.

새로 쓴 활동의 `source_version`은 Evidence Store의 content SHA
(`52b40955…`)이며 임의 문자열이 아님도 함께 확인한다.

---

## 5. Golden이 고정한 불변 (§4)

| 축 | 고정값 |
|---|---|
| `generation_mode` | `LLM_PLANNER` |
| Template | `monthly-template-a-v0.2.0` (exact resolve) |
| 생성 직후 status | `DRAFT` |
| `week_order_basis` | `PLANNER_COMPOSED` |
| Theme | `RULE_ONLY` + `THEME_REFERENCE` + `PARENT_PLAN` |
| focus | `FILLED` · `RULE_LLM` · `evidence=[]` |
| outdoor (REFERENCE) | `RULE_LLM` + `ACTIVITY_REFERENCE` |
| outdoor (새로 씀) | `RULE_LLM` + `INSTITUTION_SAMPLE` + Store SHA |
| 안전교육 | `EMPTY_UNRESOLVED` · `NOT_VERIFIED_SOURCE_REQUIRED` · `evidence=[]` |
| week id | canonical week period에서만 온다 |
| 금지 Evidence Source | `LLM_SYNTHESIZED` · `AI` · `TEACHER_EDIT` |

`focus`의 `evidence=[]`는 **"근거가 없다"가 아니라 "특정 record를 인용하지
않았다"**는 뜻이다(OD-N18). Golden 주석과 JSON 양쪽에 그 구분을 남겼다.

`LLM_SYNTHESIZED`가 Evidence Source Enum에 **없다**는 것도 함께 확인한다 —
이름만 안 쓰는 것과 애초에 없는 것은 다르다.

---

## 6. Failure Golden (§13)

실패 7종을 각각 고정했다. 공통 불변은 **어떤 실패도 Plan을 저장하지 않고, 어떤
실패도 RULE_ONLY 결과로 대체되지 않는다**이다.

| 실패 | 분류 | LLM 호출 | 저장 |
|---|---|---|---|
| Mode/Template 불일치 | `PREREQUISITE_GATE` | 0 | 0 |
| Planner 미주입 | `PREREQUISITE_GATE` | 0 | 0 |
| LLM 사용 불가 | Transport | 1 | 0 |
| LLM 설정 없음 | Configuration | 1 | 0 |
| Proposal 검증 실패 | `LLM_OUTPUT_VALIDATION` | 2 | 0 |
| 재생성 Mode 불일치 | `PREREQUISITE_GATE` | 0 | 0 |
| CONFIRMED read-only | `PREREQUISITE_GATE` | 0 | 0 |

두 가지가 특히 중요하다.

**Gate는 호출 전에 막는다.** Template이 안 맞거나 Plan이 CONFIRMED면 provider를
부르기 전에 실패한다. 비용을 쓰고 결과를 버리지 않는다.

**설정 없음과 일시 장애를 구분한다.** 둘을 하나로 묶으면 설정 오류에도 "잠시 후
다시 시도해 주세요"를 보여 주게 된다. Golden에 `MisconfiguredLLM`을 따로 둔
이유다.

또한 거부 메시지에 Source 원문이 들어가지 않는 것도 확인한다(L5 §24). 나가는
것은 위반 **식별자**뿐이다.

### 6.1 repair 경로도 고정했다

| Case | 첫 응답 | repair 응답 | 결과 |
|---|---|---|---|
| `llm_generate_rejected_proposal_saves_nothing` | exact copy | exact copy | 거부 · 호출 2 · 저장 0 |
| `llm_generate_repair_then_success` | exact copy | 정상 | 성공 · 호출 2 · repair 1 |

`SequencedFakeLLM`이 호출 순서대로 다른 Proposal을 돌려주므로 repair 경로가
결정론적으로 재현된다. 실제로 관측된 repaired violation code는
`synthesized_activity_copies_source_text_exactly`(2건) +
`activity_must_not_repeat_within_a_month`였다.

---

## 7. 최종 E2E (§11)

```text
Generate(LLM_PLANNER)
  → focus 재생성
  → outdoor 재생성 (다른 주차)
  → Teacher Edit (focus)
  → 같은 Cell 재생성
  → Confirm
  → Edit / Regenerate ×3 전부 차단
```

확인한 것 중 설명이 필요한 두 가지.

**교사 수정이 Generation Method를 바꾸지 않는다.** Edit 뒤에도 method는
`RULE_LLM`이다(CLAUDE.md §13.2). 교사가 고쳤다는 사실은 Audit History가 담는다.

**교사 값이 재생성 뒤에도 추적된다.** 같은 Cell을 다시 생성한 뒤에도
`REGENERATED` 이벤트의 `previous_value`에 교사가 쓴 문자열이 남아 있다. 남지
않으면 "무엇이 덮였는가"에 답할 수 없다.

최종 Audit chain: `CREATED → REGENERATED → TEACHER_EDITED → REGENERATED`.

확정 뒤에도 안전교육 verification은 `NOT_VERIFIED_SOURCE_REQUIRED` 그대로다.
**확정한다고 근거가 생기지 않는다.**

---

## 8. Demo route 결정론 E2E (§12)

L8이 남긴 `test_demo_llm_integration.py`는 조립과 문구를 **읽어서** 확인했다.
읽기 검사로는 잡히지 않는 것이 있어 route handler를 실제로 돌리는 E2E를 추가했다.

이를 위해 Composition Root에 `llm=` 주입 seam을 하나 만들었다. `build_wiring`이
이미 쓰던 것과 **같은 규약**이고, 기본값은 여전히 `None`(환경변수로 만든 실제
Adapter)이다. 실행 중 자동으로 선택되지 않는다.

실제로 돌려서 확인한 것.

- Composition이 정한 `LLM_PLANNER` / `v0.2.0`이 **정말 Command에 실린다**
- 행 순서가 중심 경험 → 바깥놀이 → 안전교육이고 `week_axis`는 행이 아니다
- 재생성이 Target 주차 하나만 바꾸고 새 Plan을 만들지 않는다
- Confirm 뒤 재생성이 **provider 호출 전에** 차단된다
- LLM 실패 뒤 `state["monthly"]`가 `None`이고 저장이 0 — Rule 결과가 대신 나오지 않는다
- 확정 Parent가 없으면 Gate 전에 막혀 비용이 0이다
- 화면 payload에 `system_prompt` · `user_content` · `ELICE_MLAPI` · `api_key` ·
  `Authorization` · `grounding_source_ids`가 없다

### 8.1 자기 수정 — 과했던 검사 하나

처음 쓴 `test_demo_state_does_not_leak_corpus_source_text`는 **화면에 나가는 모든
값**이 Corpus 원문과 같으면 실패하게 했다. 실제로 실패했는데, 걸린 값이
`사방치기`였다.

`사방치기`는 승인 Activity Catalog의 label(`act_outdoor_sabangchigi`)이다. 그
Catalog 자체가 기관 Sample을 사람이 검토해 만든 것이므로 Corpus 문장과 같을 수
있고, 그것은 **복사가 아니라 승인된 값을 고른 것**이다.

L5의 exact-copy 금지는 `LLM_SYNTHESIZED`에만 적용된다. 검사를 그 범위로 좁히고,
합성 Cell이 최소 1개는 존재하도록 Proposal을 강제했다 — 범위를 좁히면서 검사가
비어 버리면 아무것도 지키지 못한다.

---

## 9. Production Composition은 존재하지 않는다 (§19)

**전환이 일어났다고 말할 수 있는 대상이 없다.**

`src/ssuksak/` 아래는 `adapters` · `dev` · `ingestion` · `planning` · `shared`
뿐이다. Composition Root는 셋이다.

```text
src/ssuksak/dev/wiring.py                  dev harness (Yearly)
src/ssuksak/dev/monthly_wiring.py          dev harness (Monthly)
demo-planning/backend/composition.py       Demo
```

`pyproject.toml`에 `[project.scripts]` entry point가 없다. HTTP Adapter는
Demo용 `http.server` 하나뿐이고 Persistence는 전부 InMemory다.

따라서 정확한 서술은 이것이다.

```text
Application 기본값      GenerateMonthlyPlanCommand.generation_mode = RULE_ONLY
Demo Composition        LLM_PLANNER를 명시적으로 선택
Production Composition  존재하지 않음
```

L8이 바꾼 것은 **Demo Composition Decision**이지 Production global default가
아니다. 이 구분은 `test_rule_only_option_is_preserved`와
`test_the_two_modes_pick_different_templates`가 지킨다.

---

## 10. Artifact SHA Freeze (§15~§18)

| Artifact | SHA (앞 16자) |
|---|---|
| `templates/monthly_template_a.json` (v0.1.0) | `1f35322dd52f832b` |
| `templates/monthly_template_a_v0_2_0.json` | `cb3fa9d15ea5ad55` |
| `evidence/institution_evidence_v0_1_0.json` | `8479c0490a002d93` |
| `activities/activity_reference_v0_2_1.json` | `ddbbe43f570cf64e` |
| `rules/safety_education_legal_v1.json` | `5831809b19a28505` |
| `themes/theme_reference_v0.json` | `c12999fa141d5c5f` |

byte 동일성만으로는 부족해서 의미도 함께 고정했다.

**Template 두 version 공존 (§17).** `get_template`이 두 version을 각각 돌려주고,
없는 version에는 **최신을 대신 주지 않고 `None`**을 돌려준다. 그리고 v0.1.0과
v0.2.0의 차이가 `focus.activated` 하나뿐임을 Section 단위로 비교해 확인한다 —
다른 Section을 함께 바꿨다면 "focus만 켰다"는 설명이 사실이 아니게 된다.
`week_axis`의 `role`은 여전히 `AXIS`다.

**Evidence Store (§18).** `ingestion_version` · `content_sha256` ·
`record_count` 12,367 · `normative_status`를 고정하고, 12,367건 **전부**가
`CONTEXT_ONLY`임을 확인한다. 제품 출력으로 그대로 복사해도 되는 record는 0건이다.

**Activity Catalog (§18).** runtime default가 `activity_reference_v0_2_1.json`,
`draft: false`, 활동 196건.

**Contract version.** Packet `v0.1.0` · Retrieval `v0.1.0` · Planner prompt
`v0.1.1` · Cell prompt `v0.1.0` · Rule `monthly.llm.evidence_grounded_planner/v1`
· `week_order_basis = PLANNER_COMPOSED`.

---

## 11. Live Quality Gate (§7·§34)

Golden과 **분리**했다. Credential 없이 결정론 suite가 실패하지 않는다.

```text
Credential 있음   2,359 passed ·  0 skipped
Credential 없음   2,352 passed ·  6 skipped ·  0 failed
```

skip 6건은 전부 L8의 `test_demo_llm_integration.py` 조립 검사이고, 같은 내용을
새 `test_demo_route_e2e.py`가 **credential 없이** 실제 실행으로 덮는다.

### 11.1 최종 Live Smoke — 그리고 첫 repair 관측

동결된 코드로 2026-06 만4세 Generate 1회 + Cell Regenerate 2회를 두 번 돌렸다.

| 회차 | telemetry record | 논리 호출 | L5 repair | 결과 |
|---|---|---|---|---|
| 1 | **4** | 3 | 0 | 전부 성공 |
| 2 | 3 | 3 | 0 | 전부 성공 |

1회차의 record 4건은 **L4 contract repair가 1회 발생했다**는 뜻이다. Adapter는
`_send` 1회당 telemetry 1건을 남기고, 논리 호출 1회가 2건을 남길 수 있는 경로는
`plan_monthly`의 repair 루프뿐이다. 2회차가 3/3으로 나와 기준선이 3임을 확인했다.

**L4~L9를 통틀어 repair 발생을 관측한 것은 이번이 처음이다.** 그동안 "repair 0회"
라고 보고한 것은 Application의 `validation_repair_count`(L5 축)였고, 그 값은
지금도 live 발생 0회다. 두 축은 다른 층이다.

```text
L4 contract repair    Adapter 안   reconcile 실패 시   live 1회 관측 (2026-09-14)
L5 validation repair  Application  Validator 실패 시   live 0회
```

이 관측 때문에 `live_regenerate_smoke_l7.py`에 telemetry 축 요약 출력을
추가했다. 다음 실행부터는 추론이 아니라 출력으로 보인다.

**표본 1건으로 `MAX_REPAIR_ATTEMPTS`를 제품 정책으로 승격하지 않는다.** OD-N04는
열려 있다(§12).

Live 결과 품질(사람 관찰): 4주차가 `우리 동네` 주제 아래 산책 → 일하는 분 →
모래 그림 → 분리수거로 이어졌고, `focus`와 `outdoor`가 짝으로 붙었다. 재생성
2건 모두 Target Cell 하나만 바뀌고 짝 Cell은 그대로였다.

---

## 12. 닫지 않은 것 (§22·§23)

**`MAX_* = 1`은 구현 값으로 동결했을 뿐 OD-N04를 닫지 않았다.**

```text
MAX_REPAIR_ATTEMPTS                    = 1   (L4 · Adapter)
MAX_VALIDATION_REPAIR_ATTEMPTS         = 1   (L5 · Generate)
MAX_CELL_VALIDATION_REPAIR_ATTEMPTS    = 1   (L5 · Regenerate)
```

근거가 있어서 1을 고른 것이 아니라 **관측이 없어서** 1을 고른 것이다. §11.1이 첫
datapoint를 만들었지만 1건이다. `test_od_n04_is_still_open`이 문서에서 OD-N04가
닫히는 것을 막는다.

**Age Evidence Strength 4단계도 동결했을 뿐 OD-N17을 닫지 않았다.** 임계값은
`new-reference-evidence-impact-2026-09.md` §4.1을 그대로 쓰며, 새 기준을 만들지
않았다는 사실이 docstring에 남아 있는지까지 테스트가 확인한다.

---

## 13. Secret 위생 (§14)

코드·테스트·Demo·데이터 전체를 스캔해 credential 형태의 값이 없음을 확인한다.

세 개가 걸렸고 **모두 스스로 가짜임을 선언한 값**이었다.

```text
test-key-not-a-real-secret
elice-key-must-never-appear
elice-key-should-never-be-logged
```

셋 다 "Key가 로그·telemetry·화면에 새지 않는다"를 증명하려고 Key 자리에 넣은
값이다. 주석으로 예외를 만들지 않고 **값 자체가 선언하게** 했다 — 사람이 읽을
때도 grep이 걸릴 때도 오해가 없다.

함께 확인하는 것.

- Base URL이 코드에 하드코딩되지 않았다 (env에서만 읽는다)
- telemetry `extra`가 `system_prompt` · `user_prompt` · `api_key` · `messages` ·
  `input` 키를 거부한다
- 정상 telemetry의 `to_log_dict()`에 `prompt` · `key`가 들어간 키가 없다
- Live Smoke 스크립트가 credential을 출력하지 않는다
- Golden JSON에 Corpus 원문이 들어가지 않았다

Golden harness 자체도 `os.environ` · `getenv` · `LLMConfig.from_env` ·
`EliceMLAPIAdapter`를 쓰지 않는다.

### 13.1 자기 수정 — 여기서도 한 번

처음 쓴 검사는 harness에 `LLMConfig`라는 문자열이 있으면 실패하게 했다. 그런데
`LLMConfigurationError`(오류 **종류**)가 걸렸다. 금지 대상은 설정을 실제로
**읽는** 경로이지 오류 타입 이름이 아니므로 `LLMConfig.from_env`로 좁혔다.

---

## 14. 규칙 위반 없음 확인

| 금지 | 상태 |
|---|---|
| 기존 Golden expected를 LLM 결과로 갱신 | 하지 않음 — SHA로 증명 |
| 실제 GPT 문장을 Golden exact string으로 | 하지 않음 — suite 정책에 명시 |
| Credential을 코드·로그·Fixture에 | 없음 — 전체 스캔 |
| pytest에서 실제 API 호출 | 없음 — FakeLLM만 |
| 승인 JSON 수정 | 없음 — 6개 SHA 전부 동일 |
| Production/User data 수정 | 없음 — InMemory만 |
| OD-N04 / OD-N17 종결 | 하지 않음 — 테스트가 막는다 |
| Production 전환 주장 | 하지 않음 — 대상 자체가 없다(§9) |
| Use Case·Domain·Rule 수정 | 없음 — Composition Root 2곳만 |

---

## 15. Q&A (§36)

**Q1. Golden을 LLM 경로로 옮겼는가?**
아니다. Rule-only Golden 43 case를 그대로 두고 LLM 경로에 별도 Contract Golden
16 case를 새로 만들었다. 두 파일의 SHA가 이를 증명한다.

**Q2. LLM Golden이 자연어를 exact match하는가?**
하지 않는다. 고정하는 것은 mode·provenance·저장 여부·차단 규칙이고, GPT가 만든
문장은 고정하지 않는다. Fixture가 명시적으로 넣은 문자열만 exact다.

**Q3. Fake가 Planner를 흉내 내는가?**
아니다. 테스트가 설정한 Proposal만 돌려준다. 다만 반환 전에 실제 Adapter와 같은
`reconcile`을 태워 경계는 동일하다.

**Q4. Credential 없이 결정론 suite가 실패하는가?**
아니다. 2,352 passed · 6 skipped · 0 failed. skip 6건은 L8 조립 검사이고 같은
내용을 새 Demo route E2E가 credential 없이 덮는다.

**Q5. 실패 경로가 RULE_ONLY로 대체되는가?**
아니다. 7종 실패 전부 저장 0이고, Demo route E2E에서 실패 뒤 화면 monthly가
`None`임을 실제로 확인했다.

**Q6. 안전교육이 확정으로 해소되는가?**
아니다. Confirm 뒤에도 `EMPTY_UNRESOLVED` · `NOT_VERIFIED_SOURCE_REQUIRED`이고
`evidence=[]`다. 확정은 배치 Source를 만들지 않는다.

**Q7. Theme을 LLM이 만드는가?**
아니다. 확정 Yearly anchor에서 Rule이 파생하며 method는 `RULE_ONLY`다. LLM
Plan에서 theme을 재생성해도 provider 호출은 0이다.

**Q8. focus의 `evidence=[]`는 근거 없음인가?**
아니다. **특정 record를 인용하지 않았다**는 뜻이다(OD-N18). 근거 없음이었다면
`EMPTY_UNRESOLVED`여야 하는데 `FILLED`다.

**Q9. Cell 재생성이 다른 Cell을 바꾸는가?**
아니다. Golden과 Demo route E2E 양쪽에서 Target 하나만 바뀌고 짝 Cell·다른
Section이 그대로임을 확인했다. Live Smoke 2회도 같다.

**Q10. Template을 자동으로 바꾸는가?**
아니다. `LLM_PLANNER`인데 Template에 `focus`가 없으면 **호출 전에** 실패한다.
조용히 v0.2.0으로 바꾸면 주차별 경험이 버려지는 silent data loss가 된다.

**Q11. Artifact가 바뀌면 알 수 있는가?**
알 수 있다. 승인 Artifact 6개의 SHA를 고정했다. Golden이 통과하더라도 Artifact가
바뀌면 freeze 테스트가 먼저 실패한다.

**Q12. `MAX_* = 1`로 OD-N04를 닫았는가?**
닫지 않았다. 구현 값으로 동결했을 뿐이다. L9에서 처음으로 live repair 1건을
관측했지만(§11.1) 표본 1건이다. `test_od_n04_is_still_open`이 문서상 종결을
막는다.

**Q13. Production이 LLM Planner로 전환됐는가?**
전환됐다고 말할 수 없다. **Production Composition Root가 저장소에 존재하지
않는다.** Application 기본값은 여전히 `RULE_ONLY`이고 `LLM_PLANNER`는 Demo
Composition이 명시적으로 고른 값이다(§9).

---

## 16. 남긴 것

닫지 않고 다음 단계로 넘기는 항목이다. 전부 `docs/open-decisions.md`에 있다.

- **OD-N04** — repair 기본값. 첫 live 관측 1건이 생겼으나 표본이 얇다
- **OD-N17** — Age Strength 단계 수
- **Evidence Store historical resolution** — Store v0.2 발행 전 필수
- **동시 Teacher Edit** — Domain에 optimistic concurrency가 없다. L9는 새
  장치를 만들지 않았다
- **동월 만3/4/5세 품질 비교** — 사람 관찰 항목이다. Golden이 대신하지 않는다
- **Official Evidence Adapter** — "공식 자료 기반" 표시의 선행 조건

---

## 17. 결론

Monthly LLM Planner v1의 Application 계약과 그 계약이 성립한 Artifact를
동결했다. 계약을 바꾸려면 Golden이, Artifact를 바꾸려면 SHA freeze가, 상수를
정책으로 승격하려면 Open Decision이 각각 먼저 걸린다.

```text
MONTHLY_LLM_PLANNER_L9_COMPLETE
MONTHLY_PLAN_LLM_PLANNER_V1_FROZEN
```
