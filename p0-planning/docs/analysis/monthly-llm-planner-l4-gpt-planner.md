# Monthly LLM Planner vNext — L4 GPT-4.1 mini Planner

- 작성일: 2026-09-13
- 선행: L3 Monthly Context Packet 완료 (`MONTHLY_LLM_PLANNER_L3_COMPLETE`)
- 산출물
  - `src/ssuksak/shared/llm/monthly.py` — Planner Request / Proposal Contract
  - `src/ssuksak/planning/planner/prompt.py` — Production Prompt
  - `LLMPort.plan_monthly` · `FakeLLM.plan_monthly` · Elice Adapter 지원
  - 테스트 `tests/planner/` (71건 신규)
  - Live Smoke `analysis/experiments/monthly_llm_vnext/live_smoke_l4.py`
  - Live 출력 `analysis/tmp/l4_live_smoke.txt`
- 범위 밖: Generate/Regenerate 통합 · Monthly DRAFT 저장 · Demo · Golden ·
  L5 Deterministic Proposal Validator

---

## 1. Scope

이번 단계에서 처음으로 실제 GPT-4.1 mini가 Monthly Planning을 수행했다.

```text
MonthlyContextPacket
  → Production Prompt Rendering      (planning/planner/prompt.py)
  → MonthlyPlannerRequest            (shared/llm/monthly.py)
  → LLMPort.plan_monthly()
  → Elice MLAPI / openai/gpt-4.1-mini
  → MonthlyPlanProposal (strict) + reconcile
```

Live Smoke 3건 모두 **1회 호출로 성공**했다. retry 0, repair 0.

---

## 2. LLM Port Extension

기존 method를 건드리지 않고 **additive**로 추가했다.

```python
class LLMPort(Protocol):
    def polish_theme(self, request) -> ThemePolishResponse: ...   # 기존
    def polish_themes(self, request): ...                          # 기존
    def plan_monthly(self, request): ...                           # 추가
```

`polish_*`와 역할이 다르다.

```text
polish_themes   Rule이 이미 고른 값의 표현만 바꾼다
plan_monthly    한 달 전체 흐름·주차 배치·활동 선택을 LLM이 구성한다
```

그래도 경계는 같다. `theme_id`와 `week_id`는 **입력**이며 LLM이 만들지 않는다.

새 Provider를 만들지 않았다. `EliceMLAPIAdapter` 하나를 그대로 쓴다.

---

## 3. Planner Request / Proposal Contract

### 3.1 Adapter는 Domain을 모른다

`MonthlyPlannerRequest`는 **이미 렌더링된 문자열과 검증 anchor**만 담는다.

```python
@dataclass(frozen=True, slots=True)
class MonthlyPlannerRequest:
    task, prompt_version
    system_prompt, user_content          # 렌더링 완료된 문자열
    expected_theme_id                    # 대조 anchor
    expected_week_ids
    reference_labels: Mapping[str, str]  # activity_id → label
    valid_grounding_refs: frozenset[str] # Packet에 실제로 있는 E.. 참조
    packet_fingerprint                   # 감사용. Prompt에 넣지 않는다
```

Adapter는 `MonthlyContextPacket` · Evidence Store · Activity Repository ·
PDF를 **직접 조회하지 않는다.** 테스트가 Adapter import 경로로 이를 고정한다.

### 3.2 Proposal

```text
MonthlyPlanProposal
├─ theme_id
├─ month_flow_rationale
└─ weeks[]  (1~6)
   ├─ week_id
   ├─ experience
   └─ activity
      ├─ value
      ├─ origin                  REFERENCE | LLM_SYNTHESIZED
      ├─ reference_activity_id   (nullable)
      └─ grounding_refs[]
```

`extra="forbid"` · 공백 문자열 거부.

**Safety field가 없다.** 안전교육은 Planner의 영역이 아니므로 담을 자리를 만들지
않았다 — 자리를 만들면 모델이 채운다. 테스트가 `"safety"`를 포함한 필드가 세
model 어디에도 없음을 고정한다.

`ProposedActivityOrigin`은 `planning.context.ActivityOrigin`의 **부분집합**이며
`CORPUS_EVIDENCE`가 없다. `shared`가 `planning`을 import하지 않으려고 값을
복제했고, 두 enum의 정합을 테스트로 고정했다.

---

## 4. Prompt Architecture

```text
monthly-planner-prompt-v0.1.1
```

Prompt 본문은 `planning/planner/prompt.py` **한 곳**에 있다. Adapter에 큰
문자열을 박아 넣지 않았다(§20).

```text
SYSTEM  하는 일 / 하지 않는 일 / 활동을 정하는 방법 /
        관찰 근거를 다루는 방법 / 연령을 다루는 방법

USER    계획 입력 · 연령 근거 · 연령 대조 근거 · 기관 관찰 근거 ·
        주차 경험 관찰 · 승인 활동 후보 · 그 밖의 바깥놀이 근거 ·
        지켜야 할 것 · 하지 말아야 할 것 · 반환 형식
```

### 4.1 v0.1.0 → v0.1.1 (§14에 근거)

첫 Smoke에서 2027-02 만5세가 `CONTEXT_ONLY` 근거 문장을 글자 그대로
`LLM_SYNTHESIZED` value로 반환했다. 금지 문구가 「하지 말아야 할 것」 목록에만
있고 **판단하는 지점**에는 없었다. `LLM_SYNTHESIZED` 설명 안으로 옮겼다.

**효과는 확인되지 않았다** — §14.3 참조.

---

## 5. Context Rendering

L3 canonical JSON을 그대로 붓지 않았다. 같은 내용을 사람이 읽는 형태로 다시
렌더링하면 훨씬 짧다.

| Case | L3 canonical JSON | Prompt(system+context) |
|---|---:|---:|
| 2026-07 만4세 | 10,339자 | **5,479자** |
| 2026-06 만4세 | 10,356자 | **5,532자** |
| 2027-02 만5세 | 9,557자 | **5,307자** |

system 1,593자 + context 3,7xx~3,9xx자다.

**빠지지 않은 것** (테스트로 고정):

```text
theme_id · 모든 week_id · 연령 등급 + 실제 단일연령 근거 수
E.. 참조 전부 · "참고 전용 · 그대로 옮겨 적지 마세요" · allowed origins
```

**절대 들어가지 않는 것** (테스트로 고정):

```text
source_sha256 · source_path · rank_score · retrieval_tier ·
source_diversity_group · institution_id(기관 실명) ·
daycare_ref · classroom_ref · record_id · packet_fingerprint
```

기관은 L3에서 이미 `S1`·`S2`로 익명화돼 있고, Prompt는 그 라벨만 쓴다.

---

## 6. Activity Origin Rules

### REFERENCE

```text
origin = REFERENCE
reference_activity_id  필수 · Packet 후보에 존재해야 한다
value                  Packet label과 일치 (공백 차이만 허용)
grounding_refs         없어도 된다
```

`reference_activity_id`만 맞추고 문구를 바꾸는 것을 `REFERENCE_VALUE_MISMATCH`로
막는다. 승인 Catalog 값을 LLM이 다듬으면 그것은 더 이상 승인된 값이 아니다.

### LLM_SYNTHESIZED

```text
origin = LLM_SYNTHESIZED
reference_activity_id  반드시 null
grounding_refs         최소 1개 · Packet에 실제로 있는 E.. 참조만
```

Packet에 없는 ref를 만들면 `UNKNOWN_GROUNDING_REF`로 거부한다.

### CORPUS_EVIDENCE

Schema enum에 **없다.** P0 Corpus 12,367건이 전부 `CONTEXT_ONLY`이므로
원문을 Product 값으로 직접 쓸 수 없다. Domain enum(`context.ActivityOrigin`)에는
그대로 남아 있고 여기서만 제외했다.

---

## 7. Age Context Handling

Prompt가 세 가지를 함께 준다.

```text
- 만4세: STRONG (단일연령 면을 가진 독립기관 3곳, 연령을 언급한 기관 10곳,
                 단일연령 바깥놀이 면 2건)
- 이 자료에 담긴 요청 연령의 단일연령 근거: 7건
```

`single_age_grounding_count <= 2`이면 한 줄이 더 붙는다.

```text
→ 실제 단일연령 근거가 적습니다. 연령에 따른 차이를 크게 말하지 마세요.
```

L3 §6.4가 기록한 문제(2027-02 만5세가 `STRONG`인데 실제 단일연령 근거는 1건)를
Prompt 수준에서 완화하는 장치다. 등급만 보고 과장하지 않게 한다.

OD-N17은 그대로 OPEN이다. 4단계(`STRONG`/`MODERATE`/`WEAK`/`VERY_WEAK`)를
합치지 않고 Packet Contract를 그대로 소비했다.

---

## 8. Theme / Week Lock

`reconcile_monthly_proposal()`이 강제한다.

| 위반 | 식별자 |
|---|---|
| theme_id 교체 | `llm_must_not_select_or_replace_theme` |
| 주차 누락 | `llm_must_cover_every_week` |
| 주차 추가 | `llm_must_not_add_weeks` |
| 주차 중복 | `llm_must_not_duplicate_week` |
| 순서 변경 | `llm_must_keep_packet_week_order` |

부분 수용을 허용하지 않는다. 하나라도 어긋나면 전체 실패다.

이 식별자들은 Golden Set의 `failure_category`와 같은 성격의 **테스트 의미
식별자**이며 공개 HTTP 오류 코드로 자동 승격하지 않는다(CLAUDE.md §20).

---

## 9. Safety / Official Boundaries

**Safety** — Proposal Schema에 자리가 없고, Prompt가 세 가지를 명시한다.

```text
안전교육 내용을 만들지 않고, 주차에 배치하지 않고, 충족 여부를 판단하지 않습니다.
```

Packet의 `safety_context`는 "Planner가 건드리면 안 되는 영역"을 알려주는
용도이며 안전교육 **내용 후보를 담지 않는다**.

**Official** — `official_play_context = []` · `official_topic_context = []` ·
`official_claim_allowed = false`를 그대로 쓴다. Official Adapter를 구현하지
않았다. Prompt는 "법적 기준이나 공식 권장을 말하지 않습니다"를 명시한다.

---

## 10. Structured Output Parsing

### JSON Structured Output을 실제로 쓴다

기존 Adapter가 이미 pydantic model을 Provider에 넘긴다.

```python
RESPONSES          client.responses.parse(text_format=MonthlyPlanProposal)
CHAT_COMPLETIONS   client.chat.completions.parse(response_format=MonthlyPlanProposal)
```

Live Smoke(`api_style=responses`)에서 **정상 동작을 확인했다.** 지원 여부를
가정하지 않고 실제 호출로 확인했다.

따라서 **Markdown code fence를 걷어내는 permissive parser를 만들지 않았다.**
Provider가 구조화 출력을 보장하므로 필요가 없고, 만들면 실패를 가린다.

### 관대하지 않은 파싱

`extra="forbid"` · enum 위반 거부 · 공백 거부 · 주차 개수 1~6 제한.
Provider가 `parsed`를 돌려주지 않으면 그대로 `ValueError`다.

---

## 11. Retry / Failure Semantics

**두 축을 분리했다.**

| 축 | 대상 | 횟수 | 근거 |
|---|---|---|---|
| Transport retry | timeout · rate limit · 5xx | `LLM_MAX_RETRIES` (현재 1) | 기존 Adapter 정책 재사용 |
| Repair retry | Proposal이 Packet Contract 위반 | `MAX_REPAIR_ATTEMPTS = 1` | 이번에 추가 |

Repair 호출에는 **원래 Context 전체 + 위반 요약 한 줄**을 보낸다. 위반만 보내면
모델이 무엇을 고쳐야 하는지 알아도 근거가 없어 다시 쓸 수 없다. 요약에는
Prompt 본문도 Key도 담기지 않는다.

1회로 제한한 이유: 두 번째까지 같은 실수를 하면 Prompt나 Packet 쪽 문제이지
우연이 아니다. 무제한 재시도는 비용만 쓰고 원인을 가린다.

**Fallback을 만들지 않았다.** 실패하면 예외가 호출자에게 그대로 간다.

```text
transport 실패    → LLMUnavailableError
인증·권한·요청    → LLMConfigurationError
schema / contract → ValueError (MonthlyProposalError)
```

빈 Proposal이나 Rule-only 결과로 대신하지 않는다(OD-N15 silent fallback 금지).
테스트가 이를 고정한다.

### OD-N04

기존 Yearly 설정을 **그대로 재사용**했다. `LLM_MODEL` · `LLM_TIMEOUT_SECONDS` ·
`LLM_MAX_RETRIES` · `LLM_API_STYLE` · `LLM_REASONING_EFFORT` 모두 새 값이
필요 없었다.

새로 생긴 값은 `MAX_REPAIR_ATTEMPTS = 1` 하나이며 **코드 상수**다. 제품 정책으로
승격할지는 사람 결정이 필요하므로 **OD-N04를 닫지 않는다.** Monthly 전용
timeout이 필요한지도 실측이 더 필요하다(현재 30s 안에 4.4~7.4s로 들어온다).

---

## 12. FakeLLM

```python
FakeLLM(monthly_proposal=<MonthlyPlanProposal>)
fake.set_monthly_proposal(proposal)
```

**Planner algorithm을 흉내 내지 않는다.** 한 달 흐름 구성은 Fake가 할 수 있는
일이 아니고, 흉내 낸 결과를 테스트가 검증하면 실제 계약이 아니라 Fake를
검증하게 된다. 설정하지 않고 호출하면 명확한 메시지로 실패한다.

반환 전에 **실제 Adapter와 같은 reconcile**을 태운다. Fake를 쓰는 소비자
테스트가 실제와 같은 경계를 본다.

기존 mode도 그대로 동작한다 — `UNAVAILABLE` → `LLMUnavailableError`,
`SCHEMA_VIOLATION` → `ValueError`.

---

## 13. Live GPT-4.1 mini Smoke

```text
LIVE_GPT_4_1_MINI      ← Fake도 Simulation도 아니다

model            openai/gpt-4.1-mini
api_style        responses
timeout / retry  30.0s / 1
reasoning_effort None
prompt_version   monthly-planner-prompt-v0.1.1
```

API Key · Base URL · 전체 Prompt는 출력하지 않았고 어떤 산출물에도 저장하지
않았다(스캔으로 확인).

### 13.1 필수 Case — 2026-07 만4세 · 여름

```text
packet_fingerprint  993c6d9cbd93098e6cb005bc9a9505607fc421c13da1e2728359bce5f9a2e368
prompt              system 1,593 + context 3,886 = 5,479자
RESULT              OK · parse + reconcile PASSED
latency             7,023ms
call count          1      retry 0      repair 0
tokens              in 4,171 / out 481
theme lock          True   week lock True (5주, 순서 그대로)
```

```text
month_flow_rationale
  여름이라는 주제를 중심으로 자연과 날씨, 물의 특징을 차례로 탐색하며 아이들이
  여름의 다양한 모습을 온몸으로 느끼고 표현할 수 있도록 구성했습니다. …

W1  experience  산책하며 여름 곤충과 자연 풍경을 탐색하며 여름의 특징에 관심을 가져요.
    activity    산책하며 여름 곤충 찾기            REFERENCE  act_outdoor_v2_4bdba888a5
W2  experience  맑은 여름 하늘을 셀로판지로 관찰하며 날씨의 변화를 이해해요.
    activity    셀로판지로 여름 하늘 바라보기      REFERENCE  act_outdoor_v2_3766bbd12a
W3  experience  여름 제철 과일을 몸으로 표현하며 즐겨요.
    activity    여름 과일 신체 놀이하기            LLM_SYNTHESIZED  grounding [E06]
W4  experience  물총놀이로 여름의 시원함을 경험해요.
    activity    물총을 쏴 종이컵 무너뜨리기        REFERENCE  act_outdoor_v2_802c5d6473
W5  experience  그늘에서 쉬며 여름 더위를 건강하게 보내요.
    activity    그늘에서 휴식하기                  REFERENCE  act_outdoor_v2_a7e962fab0

REFERENCE 4 · LLM_SYNTHESIZED 1
```

### 13.2 추가 Case — 2026-06 만4세 · 우리 동네 (Rule-only 최악 Case)

```text
latency 4,737ms · call 1 · retry 0 · repair 0 · tokens in 4,148 / out 411
theme lock True · week lock True (4주)

W1  우리 동네에서 일하는 분 찾아보기        REFERENCE
W2  우리 동네 지도 보며 산책하기            REFERENCE   ← Rule-only가 놓쳤던 후보
W3  분필로 내가 되고 싶은 직업 그림 그리기  REFERENCE
W4  모래 위에 그리는 우리 동네              REFERENCE   ← Rule-only가 놓쳤던 후보

REFERENCE 4 · LLM_SYNTHESIZED 0
```

L2 보고서 §14.1이 기록한 두 후보(Rule의 최종 선택이 `activity_id` 해시 순서로
탈락시킨 것)를 **실제로 선택했다.**

### 13.3 추가 Case — 2027-02 만5세 · 성장한 우리 (scarcity)

```text
latency 4,856ms · call 1 · retry 0 · repair 0 · tokens in 4,036 / out 435
Reference 후보 4 · 주차 4

W1  모래 위에 형님이 된 내 모습 그리기      REFERENCE
W2  우리가 좋아했던 장소 산책하기           REFERENCE
W3  산책하며 동네 이웃에게 설날 인사드리기  REFERENCE
W4  사방치기                                REFERENCE

REFERENCE 4 · LLM_SYNTHESIZED 0
```

후보 4개로 4주를 정확히 채웠다. 「반드시 하나 이상 Synthesized」 같은 규칙을
만들지 않았고, 모델이 필요 없다고 판단했다.

---

## 14. Quality Observation

**PASS/FAIL 판정이 아니다.** Golden 판정도 하지 않는다. 사람 관찰 기록이다.

| 항목 | 관찰 |
|---|---|
| Theme 일관성 | 3 Case 모두 주제에서 벗어난 주차 없음 |
| W1→W5 흐름 | 독립 추출이 아님. 7월 관찰→날씨→표현→물놀이→휴식, 6월 사람→지도 산책→표현→모래 표현, 2월 회상→산책→명절→전통놀이 |
| Activity 자연스러움 | 교사가 읽고 바로 이해할 수 있는 수준 |
| 연령 반영 | §14.2 참조 |
| 중복 | 같은 활동이 두 주차에 쓰인 경우 없음 |
| Reference 사용 | 13주 중 12주 |
| Synthesized 사용 | 13주 중 1주 |
| **Corpus 원문 직접 복사** | **의심 아니라 확인됨. §14.3** |
| Official claim | 없음. "법적으로"·"공식 권장"·"표준 순서" 표현 0건 |
| Safety 언급 | 없음. 안전교육 내용·배치 0건 |
| 기관명 노출 | 없음 |

### 14.1 Reference 우선이 실제로 작동했다

13주 중 12주가 REFERENCE다. Synthesized를 남발하지 않았다. 2027-02처럼 후보가
정확히 주차 수만큼일 때도 전부 Reference로 채웠다.

### 14.2 연령 반영

2026-07 만4세에서 W3 `여름 과일 신체 놀이하기`는 Packet의 만4세 대조 항목
(E06)에서 왔고, 모델이 `grounding_refs=["E06"]`로 명시했다. 만3세 쪽 대조 항목
(`여름 꽃을 찾아요.` E01, `친구의 그림자를 잡아보아요` E04)은 쓰지 않았다.

다만 이것은 **1 Case 관찰**이며 연령 변별력의 증거로는 약하다. 만3/만5세 동월
비교는 이번 Smoke 범위에 넣지 않았다.

### 14.3 `CONTEXT_ONLY` 원문 직접 복사 — 확인된 문제

**두 번의 실행에서 나온 `LLM_SYNTHESIZED` 활동 2개가 모두 근거 문장의
글자 그대로 복사였다.**

| 실행 | Case | 반환 value | 일치한 근거 | 승인 Catalog에 있나 |
|---|---|---|---|---|
| v0.1.0 | 2027-02 만5세 | `내 키만큼 멀리 뛰기` | E14 (institution) | 없음 |
| v0.1.1 | 2026-07 만4세 | `여름 과일 신체 놀이하기` | E06 (age contrast) | 없음 |

두 경우 모두 모델은 `grounding_refs`에 해당 ref를 **정직하게 적었다.** 출처를
숨긴 것이 아니라, "근거를 참고해 새로 구성한다"를 "근거를 그대로 가져온다"로
수행했다.

**Prompt 강화는 효과가 확인되지 않았다.** v0.1.1에서 금지 문구를 판단 지점으로
옮겼지만, 복사가 사라진 것이 아니라 **다른 Case로 옮겨 갔다**. 표본이
Synthesized 2건뿐이라 통계적 판단은 불가능하지만, 적어도 "Prompt로 해결됐다"고
말할 근거는 없다.

→ **L5의 exact-copy 검출은 선택이 아니라 필수다.** Prompt는 확률을 낮출 뿐
보장하지 않는다. §7과 §35대로 L4에서는 Prompt Contract만 구현하고 정교한
similarity Validation은 L5로 넘긴다. 이 관찰이 그 필요성의 실증이다.

### 14.4 관찰된 Corpus 품질 문제 (L4 범위 밖)

2026-07 Packet의 `E25`·`E26`이 같은 텍스트(`물놀이를 가요`)다. 같은 기관의
중복 record로 보인다. L2/L3가 중복 텍스트를 제거하지 않는다. Prompt Token을
약간 낭비하지만 계약 위반은 아니다. **이번에 고치지 않았다** — L2 Retrieval
의미를 바꾸지 않는다는 §38에 해당한다.

---

## 15. Tests

```text
이전   2,009 passed, 4 deselected
현재   2,080 passed, 4 deselected      (+71 신규 · 기존 실패 0)
```

| 파일 | 건수 | 내용 |
|---|---:|---|
| `tests/planner/test_monthly_planner_contract.py` | 31 | Port 확장·기존 method 불변 · Request 검증 · Proposal schema(unknown field·enum·공백·safety 자리 없음) · Theme/Week lock 5종 · REFERENCE 계약 4종 · SYNTHESIZED 계약 4종 · FakeLLM 6종 |
| `tests/planner/test_monthly_prompt.py` | 25 | 반드시 담는 것 10종 · 절대 담지 않는 것 9종 · Request 조립 5종 |
| `tests/planner/test_monthly_adapter.py` | 15 | 정상 경로 · repair 4종 · transport 실패 4종 · telemetry 3종 · Yearly 경로 불변 |

**실제 API를 호출하는 테스트는 없다.** Adapter 테스트는 client를 주입해
네트워크 없이 전 경로를 태운다. Live Smoke는 별도 스크립트이며 pytest가 아니다.

특기할 테스트 둘:

- `test_proposed_origin_is_a_subset_of_the_context_origin_enum` — shared/planning
  간 enum 복제가 어긋나면 즉시 실패한다.
- `test_telemetry_rejects_a_prompt_body_key` — `prompt_version`이 아니라
  `template_version`을 쓴 이유를 고정한다. telemetry가 키에 `"prompt"`가 들어간
  항목을 거부하는데, 그 가드는 Prompt 본문이 로그에 새는 것을 막는 장치이므로
  이름 편의로 완화하지 않았다.

---

## 16. Performance / Usage

| Case | latency | call | retry | repair | in | out |
|---|---:|---:|---:|---:|---:|---:|
| 2026-07 만4세 | 7,023ms | 1 | 0 | 0 | 4,171 | 481 |
| 2026-06 만4세 | 4,737ms | 1 | 0 | 0 | 4,148 | 411 |
| 2027-02 만5세 | 4,856ms | 1 | 0 | 0 | 4,036 | 435 |

한 달 계획이 **호출 1회**로 나온다. 입력 약 4.1k token, 출력 약 0.45k token.
현재 timeout 30s 안에 여유 있게 들어온다.

---

## 17. Open Issues

### 17.1 `CONTEXT_ONLY` 원문 복사 (L5 필수 항목)

§14.3. Synthesized 2건 중 2건이 근거 문장 그대로였다. L5 Deterministic
Validator가 exact-copy를 검출해야 한다. **L4를 막지 않는다** — 계약 형태의
Proposal은 안정적으로 반환된다.

### 17.2 OD-N04 — 닫지 않았다

기존 Yearly 설정을 그대로 재사용했으므로 새 Decision이 필요 없었다. 새로 생긴
`MAX_REPAIR_ATTEMPTS = 1`을 제품 정책으로 승격할지는 사람 결정이 필요하다.
Monthly 전용 timeout 필요 여부도 실측이 더 있어야 한다.

### 17.3 연령 변별력 실증 부족

Live Smoke 3건이 모두 서로 다른 월·연령이라 **같은 월의 연령 간 비교**가 없다.
L5 또는 L6에서 2026-07 만3/만4/만5세 동시 실행으로 확인하는 편이 좋다.

### 17.4 그대로 둔 것

```text
OD-N17                              Age Strength enum 단계 수 (OPEN 유지)
L2 Contrast Pair precision          개선 후보로 기록만
Reference age differentiation       Catalog 성질
Activity v0.2.2                     미착수
Official Adapter                    미구현. 첫 Smoke를 막지 않았다
Corpus 중복 텍스트 (E25/E26)        L2 의미를 바꾸지 않으므로 미수정
```

---

## 18. L5 Readiness

L5 Deterministic Proposal Validator가 필요로 하는 것이 준비되었다.

| L5 요구 | L4 제공 |
|---|---|
| 구조가 보장된 Proposal | `MonthlyPlanProposal` strict + reconcile 통과 |
| 어느 Packet에서 나왔는지 | `MonthlyPlannerRequest.packet_fingerprint` |
| 근거 추적 | `grounding_refs`(E..) → Packet `audit.record_id` |
| Reference 추적 | `reference_activity_id` → 승인 Catalog |
| 검출 대상이 실재한다는 증거 | §14.3 exact-copy 2건 |
| 실패 의미 식별자 | `MonthlyProposalViolation` 11종 |

L5가 추가로 맡을 것: 의미 중복 활동 검출 · **원문 복사 검출** · 금지 표현 검출 ·
Packet ref 전수 감사 · 완전한 Provenance 검증.

---

## 답변 — §43 필수 질문

**Q1. GPT-4.1 mini가 실제 Packet을 읽고 정상 Structured Proposal을 반환했는가?**
**했다.** 3 Case 모두 `LIVE_GPT_4_1_MINI` 경로에서 1회 호출로 strict schema를
통과했고 reconcile도 통과했다. parse 실패 0건.

**Q2. 한 번의 호출로 W1~W4/5 전체를 자연스럽게 구성했는가?**
**했다.** 호출 1회, retry 0, repair 0. `month_flow_rationale`이 한 달 흐름을
먼저 서술하고 주차가 그 흐름을 따른다(예: 7월 관찰→날씨→표현→물놀이→휴식).

**Q3. Theme ID와 Week IDs가 정확히 보존됐는가?**
**보존됐다.** 3 Case 모두 theme lock True · week lock True. 누락·추가·중복·
순서 변경 0건.

**Q4. REFERENCE Activity를 실제로 사용했는가? 몇 개?**
**사용했다. 13주 중 12주**(2026-07 4/5, 2026-06 4/4, 2027-02 4/4).
`value`가 승인 label과 모두 일치했다.

**Q5. LLM_SYNTHESIZED Activity를 사용했는가? 몇 개?**
**1개** — 2026-07 W3 `여름 과일 신체 놀이하기`. 2027-02은 후보가 주차 수와 같은
scarcity Case인데도 전부 Reference로 채웠다.

**Q6. Synthesized Activity에 유효한 grounding ref가 존재하는가?**
**존재한다.** `["E06"]`이며 Packet의 만4세 대조 항목을 정확히 가리킨다. Packet에
없는 ref는 0건이었다(reconcile이 거부했을 것이나 발생하지 않았다).

**Q7. CONTEXT_ONLY Source 문장을 그대로 복사한 의심 사례가 있는가?**
**의심이 아니라 확인됐다. 2건 — Synthesized 전체가 그렇다.**
v0.1.0에서 `내 키만큼 멀리 뛰기`(=E14), v0.1.1에서 `여름 과일 신체 놀이하기`
(=E06). 둘 다 승인 Catalog에 없는 문자열이고 근거 record와 글자가 같다.
Prompt를 강화했지만 복사가 사라지지 않고 다른 Case로 옮겨 갔다.
**L5의 exact-copy 검출이 필수다.**

**Q8. 안전교육 내용 또는 법적/공식 Claim을 생성했는가?**
**하지 않았다.** 3 Case 13주 전부에서 안전교육 내용·배치 0건, "법적으로"·
"공식 권장"·"표준 순서" 표현 0건, 기관명 0건. Schema에 Safety 자리 자체가 없다.

**Q9. 만4세 Context가 실제 결과에 반영된 흔적이 있는가?**
**있다.** 2026-07 W3가 만4세 대조 항목(E06)을 grounding으로 명시했고 만3세 쪽
대조 항목은 쓰지 않았다. 다만 **같은 월의 연령 간 비교를 하지 않았으므로 변별력의
증거로는 약하다**(§17.3).

**Q10. 실제 호출 latency / retry / call count는?**
`7,023ms / 4,737ms / 4,856ms`. 모두 **call 1 · retry 0 · repair 0**.
token은 in 4,036~4,171 / out 411~481.

**Q11. L5 Deterministic Validator로 넘어갈 준비가 되었는가?**
**되었다.** §18 표대로 필요한 것이 준비됐고, §14.3이 L5가 검출해야 할 대상이
실재함을 실증한다.

---

```text
MONTHLY LLM PLANNER L4

Model:
  openai/gpt-4.1-mini  (Elice MLAPI · OpenAI-compatible · api_style=responses)
  새 Provider를 만들지 않았다. 기존 EliceMLAPIAdapter 재사용

Prompt Version:
  monthly-planner-prompt-v0.1.1
  본문은 planning/planner/prompt.py 한 곳. Adapter에 박아 넣지 않았다
  Prompt 5,307~5,532자 (L3 canonical JSON 9.5k~10.4k 대비 약 절반)

Port:
  LLMPort.plan_monthly 추가 (additive). polish_theme / polish_themes 불변
  Adapter는 Packet·Store·Repository를 직접 조회하지 않는다

Structured Output:
  MonthlyPlanProposal (pydantic strict · extra=forbid · 공백 거부)
  Provider native structured output 실제 동작 확인 — permissive parser 없음
  Safety field는 자리 자체를 만들지 않았다
  origin = REFERENCE | LLM_SYNTHESIZED  (CORPUS_EVIDENCE 없음)

Live Smoke:
  SUCCESS   (LIVE_GPT_4_1_MINI — Fake도 Simulation도 아니다)

Case:
  필수  2026-07 만4세 여름        5주 · Reference 8 · refs 34
  추가  2026-06 만4세 우리 동네    4주  (Rule-only 최악 Case)
  추가  2027-02 만5세 성장한 우리  4주  (Reference 4 = 주차 4, scarcity)

Weeks:
  3 Case 모두 요청 주차 수·순서 정확히 일치. 누락·추가·중복 0

Reference Activities Used:
  13주 중 12주. value가 승인 label과 전부 일치
  2026-06은 Rule-only가 해시 순서로 탈락시켰던 두 후보를 실제로 선택

Synthesized Activities Used:
  13주 중 1주 (2026-07 W3). scarcity Case에서도 남발하지 않았다

Grounding:
  Synthesized의 grounding_refs = ["E06"] — Packet 만4세 대조 항목
  Packet에 없는 ref 0건

Theme Lock:
  3/3 통과

Week Lock:
  3/3 통과 (순서 포함)

Safety:
  생성 0 · 배치 0 · 판단 0. Schema에 자리 없음

Official Claims:
  0건. official_play/topic 빈 채로 진행. Official Adapter 미구현

Source Copy:
  **확인된 문제 2건.** Synthesized 2건 전부가 CONTEXT_ONLY 근거 문장의
  글자 그대로 복사였다 (v0.1.0 내 키만큼 멀리 뛰기=E14,
  v0.1.1 여름 과일 신체 놀이하기=E06)
  Prompt 강화는 복사를 없애지 못하고 다른 Case로 옮겼다
  → L5 exact-copy 검출은 선택이 아니라 필수

Latency:
  7,023ms / 4,737ms / 4,856ms   (token in 4.0k~4.2k, out 0.41k~0.48k)

Retries:
  transport retry 0 · repair retry 0 · call count 1 (3 Case 모두)
  repair는 최대 1회로 제한. fallback 없음 — 실패는 예외로 전파

Regression:
  2,009 → 2,080 passed, 4 deselected  (+71 신규 · 기존 실패 0)
  승인 Artifact 전부 불변 (SHA 확인)
  Generate/Regenerate · Monthly persistence · Demo · Golden · L2 · L3 무변경
  산출물에 API Key / Base URL / Prompt 본문 없음 (스캔 확인)

Open Issues:
  CONTEXT_ONLY 원문 복사 — L5 필수 (L4를 막지 않음)
  OD-N04 미종료 — MAX_REPAIR_ATTEMPTS 승격 여부는 사람 결정
  연령 변별력 실증 부족 — 같은 월 연령 간 비교 미실시
  OD-N17 · L2 Contrast precision · Activity v0.2.2 · Official Adapter 그대로

L5 Readiness:
  READY_FOR_PROPOSAL_VALIDATOR
```

---

```text
MONTHLY_LLM_PLANNER_L4_COMPLETE
```
