# Monthly LLM Planner vNext — L8 Demo Integration

- 작성일: 2026-09-14
- 선행: L7 Cell Regenerate Integration 완료 (`MONTHLY_LLM_PLANNER_L7_COMPLETE`)
- 산출물
  - `demo-planning/backend/composition.py` — LLM Planner · Cell Regenerator 조립
  - `demo-planning/backend/app.py` — mode/template 전달 · LLM 오류 분류
  - `demo-planning/backend/views.py` — `focus` 표시 · 행 순서
  - `demo-planning/frontend/app.js` — focus 재생성 · loading · 동시 요청 차단
  - `demo-planning/tools/smoke_flow.py` — L8 흐름 확장
  - 테스트 `tests/dev/test_demo_llm_integration.py` (20건)
  - Smoke 출력 `analysis/tmp/l8_demo_smoke.txt`
- 범위 밖: L9 Golden/Freeze · Production global default 전환 ·
  Evidence Store historical resolver · optimistic concurrency ·
  Official Adapter · Activity v0.2.2

---

## 1. Demo Architecture

```text
Frontend (app.js)            target_month · section_key · week_id · actor 만 보낸다
      ↓ HTTP
Demo Backend (app.py)        Session · 오류 분류 · view 변환
      ↓
Composition (composition.py) mode · template · Adapter · Repository 결정
      ↓
Production Use Case          GenerateMonthlyPlan / Edit / Regenerate / Confirm
```

Demo에 Business Logic을 새로 만들지 않았다. Composition은 "무엇을 어떤 순서로
부를지"만 정한다.

---

## 2. Composition

```text
Yearly    build_wiring(use_llm=True)              실제 Elice Adapter
Monthly   generation_mode = LLM_PLANNER           ← Demo Composition Decision
          template_ref    = monthly-template-a-v0.2.0
          llm_planner     = MonthlyLlmPlanner
          cell_regenerator= MonthlyLlmCellRegenerator
          evidence        = institution-evidence-ingestion-v0.1.0 (JSON Store)
```

**Production global default를 바꾸지 않았다.**
`GenerateMonthlyPlanCommand.generation_mode`의 기본값은 여전히 `RULE_ONLY`이고
Demo Composition이 명시적으로 `LLM_PLANNER`를 고른다. Use Case가 환경을 보고
mode를 자동 선택하지 않는다.

**Template도 Backend가 정한다(§36).** Frontend는
`monthly-template-a-v0.2.0` 문자열을 보내지 않는다 — 테스트가 Generate 요청
본문에 `generation_mode`·`template`이 없음을 고정한다.

**Runtime에 PDF를 읽지 않는다.** Evidence Store JSON만 쓴다(테스트 고정).

### 2.1 Rule-only 경로 보존 (§25)

```bash
python demo-planning/backend/app.py --monthly-rule-only
```

기존 Rule-only Demo를 삭제하지 않았다. 이 옵션은 Template v0.1.0 + `RULE_ONLY`로
돌며, `focus` Section 자체가 생기지 않는다. 실패 시 자동 전환되는 fallback이
아니라 운영자가 직접 켜는 스위치다.

---

## 3. Monthly UI

화면에 나오는 행:

```text
중심 경험      focus
바깥놀이      outdoor_play
안전교육      safety_education
```

`week_axis`는 주차 Header(번호·날짜)로 렌더링되고 내용 행이 되지 않는다.
inactive Section은 표시되지 않는다.

### 3.1 발견 — 행 순서를 고쳤다

첫 Smoke에서 행이 `바깥놀이 → 안전교육 → 중심 경험` 순으로 나왔다.
Template JSON에서 `focus`가 마지막에 정의돼 있고 `plan.sections`가 그 순서를
따르기 때문이다.

`views.ROW_DISPLAY_ORDER`로 **표시 순서만** 정했다. Template의 Section 정의도
Plan의 `sections` 순서도 바꾸지 않았다 — 그 주의 중심 경험이 먼저 오고 활동이
따라오는 편이 교사가 읽기 자연스럽다.

### 3.2 `focus` label (§5)

```text
내부 이름   focus
화면 표시   중심 경험
```

이전 Demo label은 "주간 중점"이었다. 담는 내용이 주차별 중심 경험이므로
그대로 "중심 경험"으로 바꿨다. `focus`·`week_axis` 같은 내부 이름은 화면에
노출되지 않는다(테스트 고정).

### 3.3 Safety 표시 (§6)

```text
cell_state        EMPTY_UNRESOLVED
화면 문구         "근거가 없어 비워 두었습니다"
constraint        NOT_VERIFIED_SOURCE_REQUIRED  (확정 후에도 그대로)
```

AI가 안전교육 내용을 만든 것처럼 보이지 않는다. 새 법적 Compliance claim을
만들지 않았다. 테스트가 안내 문구에 "AI"가 없음을 고정한다.

---

## 4. Generate UX

```text
버튼 클릭 → 즉시 disabled (중복 클릭 방지)
loading  "월간계획을 생성하고 있습니다… (몇 초 걸립니다)"
완료     서버가 저장한 Plan을 다시 받아 렌더링
```

**UI Source of Truth는 Repository에 저장된 MonthlyPlan이다.** LLM raw Proposal을
화면에 직접 그리지 않는다 — `post()`가 응답의 `state`로 전체를 다시 그린다.

---

## 5. Regenerate UX

재생성 액션은 **`focus`와 `outdoor_play` 두 Cell에만** 있다. `theme`과
`safety_education`에는 없다(테스트 고정).

```text
클릭 → 화면의 모든 재생성 버튼 잠금 (동시 요청 차단)
     → Target Cell에만 "이 항목을 다시 생성하고 있습니다…"
완료 → 서버가 저장한 Plan으로 다시 그린다
```

전체 화면을 덮는 overlay를 쓰지 않는다. 같은 Plan에 동시 mutation을 날리지
않도록 버튼을 잠근다(§12·§27).

**실패 시 이전 값이 그대로 남는다.** Client가 문자열을 임의로 치환하지 않고
서버 state로만 갱신하기 때문이다 — loading 중 임시 값을 확정하지 않는다.

**Same-value 재생성을 자동 재시도하지 않는다**(§15). 같은 값이 돌아와도 두 번째
LLM 호출을 하지 않는다. 필요하면 사용자가 다시 누른다.

---

## 6. Live Demo Smoke (§28·§33·§38)

실제 Demo Backend route를 HTTP로 호출했다. Use Case 직접 호출이 아니다.
저장은 InMemory이며 실제 사용자 데이터를 건드리지 않았다.

```text
[0] /api/state           Template monthly-template-a-v0.2.0 · LLM_PLANNER
[1] /api/yearly/generate     200   4,610ms   실제 LLM
[2] /api/monthly/generate    409   CONFIRMATION_GATE (DRAFT에서 차단) ✓
[3] /api/yearly/confirm      200       2ms
[4] /api/monthly/generate    200   4,038ms   LLM 1회 · repair 0
[4.o] /api/monthly/regenerate outdoor  200  1,950ms  LLM 1회 · repair 0
[4.f] /api/monthly/regenerate focus    200  1,591ms  LLM 1회 · repair 0
[4.e] /api/monthly/edit      200       5ms
[4.r] /api/monthly/regenerate focus    200  2,760ms  (교사 수정 후)
[5] /api/monthly/confirm     200   DRAFT → CONFIRMED
[6] CONFIRMED 이후 차단      409 × 4  confirmed_monthly_plan_is_read_only
```

### 6.1 생성 결과 — 2026-06 만4세 · 우리 동네

```text
        중심 경험                                   바깥놀이
W1  우리 동네를 지도와 함께 산책하며 주변을 탐색해요.        우리 동네 지도 보며 산책하기
W2  우리 동네에서 일하는 다양한 직업과 역할을 알아가요.      우리 동네에서 일하는 분 찾아보기
W3  직접 분필로 꿈꾸는 직업을 그림으로 표현하며 나눠요.      분필로 내가 되고 싶은 직업 그림 그리기
W4  모래 위에 우리 동네 모습을 자유롭게 그리고 표현해 봐요.   모래 위에 그리는 우리 동네
안전교육  4주 전부 빈 칸 (근거 없어 비워 둠)
```

### 6.2 Target-only 재생성

```text
바깥놀이 재생성  이전 분필로 내가 되고 싶은 직업 그림 그리기
                이후 꿈을 담은 종이비행기 함께 날리기   (LLM_SYNTHESIZED)
                바뀐 Cell [('outdoor_play', '2026-06-W3')]

중심 경험 재생성  이전 직접 분필로 꿈꾸는 직업을 그림으로 표현하며 나눠요.
                이후 자신이 꿈꾸는 직업을 종이비행기에 그려 마음껏 표현하며
                     친구들과 이야기 나누어요.
                바뀐 Cell [('focus', '2026-06-W3')]
```

**paired Cell 연결이 실제로 관찰된다.** 바깥놀이를 `종이비행기`로 바꾼 뒤
중심 경험을 재생성하니 그 **새 값**을 보고 종이비행기를 언급하도록 맞췄다.
두 번째 요청이 갱신된 snapshot을 본다는 뜻이다.

### 6.3 Teacher Edit → Regenerate (§16)

```text
교사 수정      focus W3 = "교사가 고친 중심 경험"
명시적 재생성  focus W3 = "아이들이 종이비행기에 자기 꿈을 담아
                         우리 동네 하늘을 날리며 희망을 나누어요."
audit         CREATED → REGENERATED → TEACHER_EDITED → REGENERATED
바뀐 Cell     [('focus', '2026-06-W3')]
```

Audit history가 지워지지 않는다. 누르지 않은 Cell은 변하지 않았다.

### 6.4 두 번째 Scenario — 2026-07 만4세 · 여름 (§29)

```text
5주 · LLM 1회 · repair 0 · 4,397ms

        중심 경험                              바깥놀이
W1  여름 자연과 곤충을 탐색하며 관심을 키워요.       산책하며 여름 곤충 찾기      [REFERENCE]
W2  여름 하늘의 아름다움을 오감으로 체험해요.        셀로판지로 여름 하늘 바라보기  [REFERENCE]
W3  물의 성질을 직접 체험하며 시원함을 느껴요.       물총을 쏴 종이컵 무너뜨리기   [REFERENCE]
W4  여름 햇볕과 바람의 변화를 몸으로 느끼며…        여름 햇볕과 바람 즐기기 놀이  [INSTITUTION_SAMPLE]
W5  그늘에서 편안하게 휴식을 즐기며 여름을 마무리해요.  그늘에서 휴식하기          [REFERENCE]
```

REFERENCE 4 + SYNTHESIZED 1. 합성 활동에 `INSTITUTION_SAMPLE` Evidence가 붙는다.

---

## 7. Rule-only 비교 (§31)

같은 **2026-06 만4세 · 우리 동네**를 두 경로로 생성했다.

| | RULE_ONLY | LLM_PLANNER |
|---|---|---|
| Template | v0.1.0 | v0.2.0 |
| 소요 | **23ms** | 4,038ms |
| LLM 호출 | 0 | 1 |
| 중심 경험 행 | **없음** | 4주 전부 |

```text
RULE_ONLY
  W1 우리 동네에서 일하는 분 찾아보기        TIE_BREAK_STABLE_ACTIVITY_ID
  W2 분필로 내가 되고 싶은 직업 그림 그리기    AVOIDED_REPEAT_IN_MONTH
  W3 꿈을 실은 종이비행기 날리기            AVOIDED_REPEAT_IN_MONTH
  W4 병원에서 사용하는 물건 그림 찾기        AVOIDED_REPEAT_IN_MONTH

LLM_PLANNER
  W1 우리 동네 지도 보며 산책하기
  W2 우리 동네에서 일하는 분 찾아보기
  W3 분필로 내가 되고 싶은 직업 그림 그리기
  W4 모래 위에 그리는 우리 동네
```

**사람 관찰 (점수를 만들지 않는다)**

- **주차 흐름**: Rule-only의 W1은 `TIE_BREAK_STABLE_ACTIVITY_ID` — 동점에서
  `activity_id` 문자열 순서로 갈렸다는 뜻이다. LLM은 산책으로 시작해
  탐색 → 직업 알기 → 직업 표현 → 동네 표현으로 이어진다.
- **주제 편중**: Rule-only는 4주 중 3주가 직업 소재다
  (일하는 분 / 되고 싶은 직업 / 병원 물건). LLM은 탐색·직업·표현으로 나뉜다.
- **반복**: 둘 다 같은 활동을 두 번 쓰지 않았다. Rule-only의
  `AVOIDED_REPEAT_IN_MONTH`가 그 역할을 한다.
- **focus**: Rule-only에는 주차별 중심 경험 행이 없다. 화면이 활동 이름만
  나열한다.
- **Rule-only가 나은 점**: 23ms · LLM 비용 0 · 완전 결정론. 재현이 필요한
  회귀 검증에는 이쪽이 적합하다.

---

## 8. Human Quality Observation (§30)

**Deterministic Validator가 아니라 사람 관찰이다.** PASS/FAIL 판정이 아니다.

| 항목 | 관찰 |
|---|---|
| 한 달 흐름 | 6월은 산책→직업→표현, 7월은 곤충→하늘→물→바람→휴식. 두 달 모두 뒤로 갈수록 표현·마무리로 간다 |
| focus–outdoor 연결 | 두 달 모두 중심 경험이 그 주 활동을 직접 가리킨다. 재생성 후에도 유지된다(§6.2) |
| 주차 반복 | 같은 활동·같은 문장 반복 없음 |
| 만4세 적합성 | 산책·분필 그리기·물총·모래놀이·그늘 휴식. 과하게 어렵거나 유치한 항목은 눈에 띄지 않았다 |
| 문장 자연스러움 | "~해요" 체로 일관. 교사가 그대로 읽을 수 있는 수준 |
| 재생성 전후 차이 | 의미 있게 달라졌고 paired Cell에 맞춰 조정됐다 |

**한계**: 2 Case · 1인 관찰이다. 일반화하지 않는다.

---

## 9. Latency (§43 Q7·Q8)

| 동작 | 실측 |
|---|---:|
| Yearly Generate (실제 LLM) | 4,610ms |
| **Monthly Generate (LLM)** | **4,038ms · 4,397ms** |
| Monthly Generate (Rule-only) | 23ms |
| **outdoor_play 재생성** | **1,950ms** |
| **focus 재생성** | **1,591ms · 2,760ms** |
| Teacher Edit | 5ms |
| Yearly Confirm | 2ms |

L4/L6 실측(4~7초)과 일치한다. Generate는 loading state가 필요하고, Cell
재생성은 2초 안팎이라 Target Cell 표시만으로 충분하다.

---

## 10. Repair / Retry 관측 (§32)

L8 Demo 세션 전체에서:

```text
transport retry          0
L4 contract repair       0
L5 validation repair     0
Cell contract repair     0
Cell validation repair   0
```

Generate 3회 + Cell 재생성 3회, 모두 provider call 1회로 끝났다.
**OD-N04 표본에 더할 값은 여전히 "0회"다.**

---

## 11. Failure UX (§39)

### 발견 — 분류되지 않은 500이 나왔다

`LLM_MODEL`을 없는 모델로 두고 Monthly Generate를 호출하니
**HTTP 500 `UNEXPECTED`**가 나왔다. Demo route가 `LLMConfigError`(설정 모듈)만
잡고 `LLMConfigurationError`·`LLMUnavailableError`(Port)는 잡지 않았기 때문이다.

§8이 요구한 "현재 Demo error convention에 따른 오류"가 아니었다. 고쳤다.

```text
LLMUnavailableError    → 503 LLM_UNAVAILABLE
                          "AI 생성에 실패했습니다. 잠시 후 다시 시도해 주세요."
LLMConfigurationError  → 503 LLM_CONFIG
                          "AI 설정에 문제가 있어 생성할 수 없습니다."
```

재확인:

```text
Monthly Generate 실패   HTTP 503  kind=LLM_CONFIG  failure_kind=BAD_REQUEST
  사용자 메시지  AI 설정에 문제가 있어 생성할 수 없습니다.
  monthly 상태   None   ← RULE_ONLY 결과로 대체되지 않았다
```

**비밀정보 노출 확인**: 응답과 서버 로그 3개 전부에서 실제 API Key 값 · Base URL ·
Prompt 본문 · `sk-` 패턴 **0건**. `hint`에 들어 있는 것은 환경변수 **이름**뿐이다.

Validation rejection 실패 UX는 L6/L7 통합 테스트가 이미 고정한다(저장 0건 ·
원 Plan 보존). Live로 유발하려면 모델이 위반을 내야 해서 재현이 불확실하므로
Demo에서 억지로 만들지 않았다.

---

## 12. Tests

```text
이전   2,281 passed, 4 deselected
현재   2,301 passed, 4 deselected      (+20 · 기존 실패 0)
```

| 영역 | 건수 |
|---|---:|
| Composition (mode · template · model · Rule-only 보존 · PDF 미사용) | 6 |
| 화면 표시 (label · 행 순서 · week_axis · safety 문구) | 4 |
| Backend route (mode 전달 · 오류 분류 · fallback 없음 · payload 위생) | 4 |
| Frontend (재생성 대상 · disabled · 동시 요청 · loading · 용어 · picker 없음) | 6 |

Golden 파일을 수정하지 않았다. 실제 API를 호출하는 테스트는 없다.

### 12.1 테스트를 두 번 고쳤다

처음 쓴 두 assertion이 **정상 코드를 잡았다.**

- `"provider" not in frontend` — `provider_call_count` 표시에 걸렸다.
  금지 대상은 "모델을 고르는 UI"이지 문자열 `provider`가 아니다.
- `"LLM_PLANNER" not in frontend` — 모드를 **표시**하는 코드에 걸렸다.
  금지 대상은 Frontend가 모드를 **보내는** 것이다.

둘 다 요청 본문과 입력 요소를 보도록 좁혔다. 넓은 금지어 검사는 오탐으로
정상 기능을 막는다.

---

## 13. Open Issues

### 13.1 Evidence Store historical resolution 없음 (§26)

L7에서 연 이슈다. **L8에서 해결하지 않았다.** 현재 Demo는 단일 Store
(`institution-evidence-ingestion-v0.1.0`)만 쓰므로 동작한다.
silent fallback을 추가하지 않았다.

→ **Evidence Store v0.2 발행 전에 해결해야 한다.**

### 13.2 동시 Teacher Edit 위험 (§27)

Demo는 single-user 로컬 시연이므로 L8 blocker가 아니다. UI에서 같은 Plan에
동시 mutation을 날리지 않도록 버튼을 잠갔다. **새 optimistic concurrency
system을 만들지 않았다.**

→ Production multi-user 전환 전에 결정 필요.

### 13.3 OD-N04 — 닫지 않았다

L8에서도 repair 0회. 표본이 계속 "0"이라 `MAX_*=1`이 충분한지 판단할 근거가
쌓이지 않는다. 실제 교사 사용 데이터가 필요하다.

### 13.4 Rule-only Demo와 Golden

Rule-only 경로는 `--monthly-rule-only`로 보존했지만, L9에서 Golden을 어느
경로 기준으로 고정할지는 정해지지 않았다.

### 13.5 그대로 둔 것 (§40)

```text
Official Adapter · Activity v0.2.2 · OD-N17 · L2 Contrast precision
Production global default · Golden final update
```

---

## 14. L9 Readiness

| L9 요구 | L8 상태 |
|---|---|
| 실제 Demo에서 전 흐름 동작 | 확인 — Generate·Edit·재생성·Confirm·차단 |
| 두 경로 공존 | LLM_PLANNER 기본 · Rule-only 옵션 보존 |
| 결정론 필요 영역 | Rule-only 23ms · LLM 0회로 회귀에 쓸 수 있다 |
| Artifact 불변 | 승인 Artifact 전부 SHA 확인 |
| 비밀정보 위생 | 응답·로그 전부 0건 |

---

## 답변 — §43 필수 질문

**Q1. 실제 Demo UI에서 LLM Monthly DRAFT가 생성되는가?**
**생성된다.** Demo Backend route(`/api/monthly/generate`)로 HTTP 200,
`status=DRAFT`, `generation_mode=LLM_PLANNER`, LLM 1회. 2026-06과 2026-07
두 Case 모두 성공했다.

**Q2. focus가 주차별로 화면에 정상 표시되는가?**
**표시된다.** "중심 경험" 행으로 주차 수만큼 나온다. 첫 Smoke에서 행 순서가
바깥놀이 뒤로 밀려 있던 것을 `ROW_DISPLAY_ORDER`로 고쳤다(§3.1).

**Q3. outdoor_play와 focus를 각각 독립적으로 재생성할 수 있는가?**
**가능하다.** 두 Cell에만 재생성 버튼이 있고 각각 1,950ms · 1,591ms로 동작했다.
`theme`·`safety_education`에는 버튼이 없다.

**Q4. 재생성 중 Target 외 Cell은 화면/Backend 모두 보존되는가?**
**보존된다.** 두 번 모두 바뀐 Cell이 정확히 `[(section, week)]` 하나였다.
UI는 서버가 저장한 Plan으로 다시 그리므로 화면과 Backend가 어긋나지 않는다.

**Q5. Teacher Edit → Regenerate → Confirm 흐름이 자연스럽게 동작하는가?**
**동작한다.** 수정 5ms → 명시적 재생성 2,760ms → Confirm.
audit `CREATED → REGENERATED → TEACHER_EDITED → REGENERATED`가 남고 다른 Cell은
변하지 않았다.

**Q6. CONFIRMED 후 Edit/Regenerate가 UI와 Backend 양쪽에서 막히는가?**
**막힌다.** Backend는 4가지 시도 전부 HTTP 409
`confirmed_monthly_plan_is_read_only`. UI는 `editable` 판정으로 버튼을
disabled로 두고 Confirm 버튼도 비활성화한다.

**Q7. 실제 Generate latency는?**
**4,038ms · 4,397ms** (2026-06 · 2026-07). Rule-only는 23ms.

**Q8. 실제 focus/outdoor Regenerate latency는?**
**outdoor 1,950ms · focus 1,591ms**(교사 수정 후 재생성은 2,760ms).

**Q9. repair/retry가 실제로 얼마나 발생했는가?**
**0회.** transport retry · L4/Cell contract repair · L5/Cell validation repair
전부 0. Generate 3회 + 재생성 3회 모두 provider call 1회로 끝났다.

**Q10. 2026-06 Rule-only와 비교해 어떤 차이가 관찰됐는가?**
§7. 요약하면 ① Rule-only W1이 `activity_id` 문자열 순서로 결정됐고
② Rule-only는 4주 중 3주가 직업 소재로 몰렸으며 ③ Rule-only에는 중심 경험 행이
없다. 반대로 Rule-only는 23ms·LLM 0회·완전 결정론이다.

**Q11. 사람이 화면으로 봤을 때 월간 흐름과 paired Cell 품질은 어떤가?**
§8. 두 달 모두 뒤로 갈수록 표현·마무리로 가는 흐름이 보이고, 중심 경험이 그 주
활동을 직접 가리킨다. 재생성 후에도 paired Cell에 맞춰 조정됐다.
**2 Case · 1인 관찰이므로 일반화하지 않는다.**

**Q12. 현재 Open Issue 중 L9 이전에 반드시 해결해야 하는 것은 무엇인가?**
**L9(Golden/Freeze) 자체를 막는 것은 없다.** 다만 §13.4가 L9에서 곧바로 결정
대상이 된다 — Golden을 어느 경로 기준으로 고정할 것인가. §13.1(Evidence Store
historical resolution)은 **Store v0.2 발행 전**, §13.2(동시 편집)는
**multi-user 전환 전**이며 둘 다 L9 시점 요구가 아니다.

**Q13. L9 Golden / Freeze로 넘어갈 준비가 되었는가?**
**되었다.** §14 표대로 전 흐름이 실제 Demo route에서 동작하고, 두 경로가
공존하며, 승인 Artifact가 전부 불변이고, 비밀정보 노출이 없다.

---

```text
MONTHLY LLM PLANNER L8

Demo Mode:
  LLM_PLANNER — Demo Composition Decision
  Production global default는 그대로 RULE_ONLY (L9에서 결정)
  --monthly-rule-only 로 기존 경로 보존

Template:
  monthly-template-a-v0.2.0 (LLM) / v0.1.0 (Rule-only)
  **Backend Composition이 정한다.** Frontend는 문자열을 보내지 않는다

Monthly Generate:
  /api/monthly/generate → 실제 Use Case → DRAFT 저장 → 저장본을 다시 읽어 렌더링
  LLM raw Proposal을 화면에 직접 그리지 않는다
  2026-06 4,038ms · 2026-07 4,397ms · 각 LLM 1회 · repair 0

Focus UI:
  "중심 경험" 행으로 주차별 표시 (내부 이름 미노출)
  행 순서를 중심 경험 → 바깥놀이 → 안전교육으로 고쳤다 (표시 전용)

Outdoor UI:
  "바깥놀이" 행. REFERENCE / SYNTHESIZED를 교사 화면에 기술 용어로 쓰지 않는다

Cell Regenerate:
  focus · outdoor_play 두 Cell에만. theme · safety에는 없다
  Target Cell만 loading · 동시 요청 차단 · 실패 시 이전 값 유지
  outdoor 1,950ms · focus 1,591ms · 각 LLM 1회 · repair 0
  바뀐 Cell이 정확히 하나임을 매번 확인

Teacher Edit:
  5ms · 수정 후 명시적 재생성 가능
  audit CREATED → REGENERATED → TEACHER_EDITED → REGENERATED 보존

Confirm:
  Safety EMPTY_UNRESOLVED여도 확정 가능 (UI가 잘못 막지 않는다)

Confirmed Read-only:
  regenerate/focus · regenerate/outdoor · edit/focus · edit/outdoor
  네 시도 전부 HTTP 409. UI도 버튼을 disabled로 둔다

Live Demo Smoke:
  실제 Demo Backend route 경유 · InMemory 저장 · 2 Case 성공
  Yearly Gate(DRAFT 차단) → Confirm → Monthly Generate → 재생성 ×2
  → Edit → 재생성 → Confirm → 차단 ×4

Rule-only Comparison:
  같은 2026-06 만4세로 두 경로 실행
  Rule-only 23ms · LLM 0회 · 중심 경험 행 없음 · 4주 중 3주 직업 소재
  LLM 4,038ms · 산책→직업→표현→표현 · 중심 경험 4주

Human Quality Observation:
  흐름·paired 연결·반복 없음·연령 적합성·문체 모두 사람 관찰로 기록
  2 Case · 1인 관찰이므로 일반화하지 않는다

Latency:
  Generate 4.0~4.4s · Cell 재생성 1.6~2.8s · Edit 5ms · Rule-only Generate 23ms

Repair / Retry:
  전 구간 0회 (transport · L4/Cell contract · L5/Cell validation)

Failure UX:
  **분류되지 않은 500을 발견해 고쳤다.**
  LLMUnavailableError → 503 LLM_UNAVAILABLE
  LLMConfigurationError → 503 LLM_CONFIG
  RULE_ONLY 대체 없음 · 기존 Plan 보존
  응답·서버 로그 전부에서 API Key / Base URL / Prompt 본문 0건

Regression:
  2,281 → 2,301 passed, 4 deselected  (+20 · 기존 실패 0)
  승인 Artifact 전부 불변 (SHA 확인) · Golden 무수정
  L2~L7 Production 코드 무변경

Open Issues:
  Evidence Store historical resolution — Store v0.2 발행 전 (L9 비차단)
  동시 Teacher Edit — multi-user 전환 전 (L9 비차단)
  OD-N04 — repair 표본이 계속 0회
  Golden을 어느 경로 기준으로 고정할지 — **L9에서 곧바로 결정 대상**
  테스트 assertion 2건을 스스로 정정 (넓은 금지어 검사가 정상 코드를 잡았다)

L9 Readiness:
  READY_FOR_GOLDEN_AND_FREEZE
```

---

```text
MONTHLY_LLM_PLANNER_L8_COMPLETE
```
