# Monthly LLM Planner vNext — Evidence-Grounded Monthly Planning Architecture

- 작성일: 2026-09-13
- 성격: **ANALYSIS + DESIGN + PROTOTYPE ONLY.** `src/` · `data/` · `demo-planning/` ·
  `CLAUDE.md` · Production Prompt/Adapter · Activity Reference · Theme Reference ·
  Selection Rule · Golden을 **수정하지 않았다.** 변경 파일 0개, `1644 passed, 4 deselected`.
- Prototype: `analysis/experiments/monthly_llm_vnext/`
  (`evidence_store.py` · `retriever.py` · `planner_contract.py` · `run_prototype.py`)
- 산출물: `analysis/tmp/evidence_store.json` · `analysis/tmp/monthly_llm_prototype.json`
- Evidence Source of Truth: `docs/analysis/new-reference-evidence-impact-2026-09.md`
  (과거 분석 수치와 충돌하면 이 문서를 우선한다)

---

## 1. Executive Summary

Monthly는 기능적으로 완결되어 있다. 막힌 것은 **Rule이 고를 수 있는 것의 한계**다.

Rule v2의 정렬 키 6개 중 실제로 결과를 가르는 것은 2개뿐이고
(`monthly-v0-2-1-demo-quality-verification.md` §3), 12 Case 중 **6 Case는 주차 배치가
`activity_id` 해시 정렬**이었다. 주차 번호는 정렬 키에 아예 들어가지 않는다.
즉 Rule을 더 깎아서 "주차 흐름"을 만들 수 없다 — **Rule에 그 개념이 없다.**

동시에 2026-09-13 Corpus 재감사로 Grounding 재료가 크게 달라졌다.
신규 기관 Sample 174건, 만4세 단일연령 + 바깥놀이 행 **5면/3기관 → 25면/6기관**,
Week Experience 문서 **33 → 88**, 그리고 **같은 기관·같은 월·연령만 다른 대조쌍 31문서**가
생겼다. 연령 차이를 LLM 일반상식이 아니라 **원문으로** 줄 수 있게 됐다.

따라서 제안하는 구조는 다음이다.

```text
Evidence Store (Corpus 관찰값)   Activity Reference v0.2.1 (승인 canonical)
              \                          /
               → Hybrid Retrieval (metadata filter + 어휘 rank + source diversity)
                            ↓
                   Monthly Context Packet   (≈5.4k자, 측정값)
                            ↓
                   GPT-4.1 mini  ·  1 request  ·  한 달 전체
                            ↓
                   Structured Output (week별 experience + activity + origin + source ids)
                            ↓
                   Deterministic Validator   (Rule = Guardrail)
                            ↓
                   Monthly DRAFT
```

핵심 판단 4개:

1. **Activity Reference v0.2.2는 선행조건이 아니다.** 신규 174건을 Catalog로 승격하지 않고
   Evidence Store로 직접 Grounding한다. Catalog는 canonical 축으로 그대로 둔다.
2. **1회 호출로 한 달 전체를 계획한다.** 주차 간 흐름·중복 회피가 같은 컨텍스트 안에서
   결정되어야 하기 때문이다. 측정된 Prompt는 평균 **5,407자**다.
3. **Reference 196개를 통째로 넣지 않는다.** hard filter + Rule v2 pre-ranking → Top-K(12).
   전체 나열 대비 **6% 규모**다.
4. **주차 순서는 Source 근거가 없다.** 그러므로 LLM이 구성하되, 그 사실을 Provenance에
   `week_order_basis = PLANNER_COMPOSED`로 **명시적으로 기록**한다.

판정: **`MONTHLY_LLM_PLANNER_VNEXT_READY_TO_IMPLEMENT`** (조건은 §26).

---

## 2. Why Rule-only Monthly Plateaued

`monthly-v0-2-1-demo-quality-verification.md`의 실측을 그대로 옮긴다.

| Ranking 축 | 12 Case에서의 실효성 |
|---|---|
| same-month repeat penalty | 작동. 단 **월 간 반복은 대상 아님** (`모래놀이` 3회, `사방치기` 3회) |
| parent theme mismatch penalty | 부분 작동. `theme_links` 미보유 **51/196(26%)** 에는 무력. 2026-06 만4세는 pool 7개 전부가 무력 |
| display quality penalty | 12 Case에서 penalty가 붙은 Cell **0건** |
| curriculum repeat penalty | **완전 미작동** — Catalog 196/196이 `curriculum_links = []` |
| negative monthly evidence strength | 작동. 사실상 이 축이 대부분을 결정 |
| stable activity_id | **6/12 Case에서 순서를 전부 결정** |

55칸 중 41칸(75%)의 선택 이유가 `AVOIDED_REPEAT_IN_MONTH` — "이번 달에 아직 안 썼다"다.

**구조적 이유**는 하나다. 정렬 키에 주차 번호가 없다.

```text
(repeat, theme, display_quality, curriculum, -evidence_strength, activity_id)
```

W1이 강한 근거를, W5가 약한 근거를 받는 것이 전부다. 2026-04 만4세에서
`벚꽃 비 흩날리기`(W3)가 `산책하며 새싹 찾기`(W4)보다 앞에 오는 계절 역행이 실제로 나왔다.

**결론: Rule을 더 정교화해도 주차 흐름은 나오지 않는다.** Rule은 "무엇을 어디에 넣을지"를
정하는 층이고(CLAUDE.md §5), "한 달을 어떤 이야기로 엮을지"는 그 층의 개념이 아니다.

---

## 3. Latest Evidence State

`new-reference-evidence-impact-2026-09.md` 기준 (2026-09-13).

| 축 | Before | After |
|---|---|---|
| 기관 Sample | 175건 | **349건** (신규 174, exact dup 0) |
| 신규 기관 | — | 55곳 |
| 만3세 단일연령 + 바깥놀이 행 | 52면/10기관 | 115면 |
| **만4세 단일연령 + 바깥놀이 행** | **5면/3기관** | **25면/6기관** |
| 만5세 단일연령 + 바깥놀이 행 | 11면/7기관 | 30면 |
| Week Experience 문서 | 33 / 9기관 | **88 / 17기관** |
| Week Experience 등급 | MODERATE 6 · WEAK 2 · VERY_WEAK 4 | **12개월 전부 MODERATE** |
| 월 × 연령 36칸 등급 | STRONG 14 · WEAK 13 | **STRONG 29 · WEAK 0** |
| 연령 대조 문서 | 사실상 없음 | **31문서** (monthly 21) |
| **신규 174건 중 Catalog ingest** | — | **0건** |

그리고 **변하지 않은 것**:

- `activity_reference_v0.2.1` 내부 만4세 단일연령 evidence = **4** (미반영)
- `curriculum_links` = 196/196 공백
- `theme_links` 미보유 = 51/196
- **주차 순서 근거 = 여전히 0.** position별 concept 분포가 평평하다

### 3.1 이번 Prototype에서 새로 측정한 것

`analysis/experiments/monthly_llm_vnext/evidence_store.py`로 Corpus 전체를
Evidence Record로 만들었다.

```text
Evidence Record  3,603건 / 기관 37곳
  indoor_play 804 · daily_routine 704 · safety_education 642 ·
  outdoor_play 628 · week_experience 421 · event 241 · indoor_alternative 163

setting            INDOOR 804 · OUTDOOR 616 · INDOOR_ALTERNATIVE 189 · UNKNOWN 1994
age_evidence_type  SINGLE_AGE_PAGE 1887 · MIXED_AGE_PAGE 1353 · AGE_UNKNOWN 363
week_position 보유  0     ← 원문에 주차가 명시된 줄만 세었고, 추정하지 않았다
```

**`week_position` 0**은 버그가 아니라 결과다. 줄 단위 원문에 "이 항목은 2주차"라고 적힌
근거가 없다. §10의 설계 근거가 된다.

### 3.2 추출 손실 — 설계에 직접 영향을 주는 실측

`pdftotext -layout` 줄 기반으로 바깥/실외 행을 읽으면:

```text
HAS_BODY                           210   83%
EMPTY_BODY (내용이 다음 줄로 넘어감)   41   16%
TOO_SHORT                            2    1%
합계                                253
```

실제 사례:

```text
2026_직장_부산광역시청어린이집_..._월간계획안(6월).pdf  page 2 (만4세)
  |             바깥          ← 내용이 다음 줄로 넘어가 손실
```

Prototype 패킷에서도 잘린 항목이 관찰된다 —
`우리 동네 표지판 찾으며`, `동생 나무 형님 나무를`, `여름 숲의 곤충을`,
alt 태그 누출 `대체] 손바닥으로 친구`, 전각 괄호 미처리 `［대체］내 키만큼 발차기해요`.

**→ Evidence Store Ingestion은 줄 기반이 아니라 `analysis/tools/cell_extract.py`의
셀 기하 추출을 써야 한다.** 이것이 `OD-ACTIVITY-INGESTION-01`과 만나는 지점이다(§22).

---

## 4. Current Monthly Architecture

읽기만 하고 확인한 현재 구조다.

```text
GenerateMonthlyPlan (application)
  ├ Gate        parent yearly CONFIRMED · template · safety rule · activity catalog
  ├ Rule        monthly_week_periods   canonical week 산출
  │             monthly_theme_derivation  상위 theme 계승
  │             monthly_activity_selection v2  cell별 Activity 선택
  │             monthly_cell_state        EMPTY_VALID / EMPTY_UNRESOLVED / FILLED
  ├ Domain      MonthlyPlan · MonthlySection · MonthlyPlanItem
  │             EvidenceSource · GenerationMethodDetail · AuditTrail
  └ Result      MonthlyPlanResult(plan, run, activity_regeneration)
```

Provenance 3축 (CLAUDE.md §13) — **이 구조를 바꾸지 않는다.**

```text
EvidenceSource        source_type · source_id · source_version · effective_date · display_name
GenerationMethodDetail method(RULE_ONLY|RULE_LLM|IMPORTED|MANUAL) · rule_id · rule_version · selection_reason
AuditTrail            CREATED / REGENERATED / TEACHER_EDITED / CONFIRMED
```

LLM 경계도 이미 있다 — `shared/llm/port.py`의 `LLMPort` Protocol, `LLMConfig`
(`LLM_MODEL=openai/gpt-4.1-mini`, Elice MLAPI OpenAI-compatible), `FakeLLM`,
`LLMUnavailableError` / `LLMConfigurationError`.
**새 공급자를 붙일 필요가 없다. Protocol에 method 하나를 더하면 된다.**

---

## 5. Evidence Store Design

### 5.1 Activity Reference와 역할을 나눈다

| | Activity Reference | Evidence Store |
|---|---|---|
| 지위 | `HUMAN_APPROVED` canonical | Corpus 관찰값 |
| 버전 | `catalog_version` + Plan pin | 재생성 가능, pin 대상 아님 |
| Plan Item Evidence가 되는가 | **된다** (`ACTIVITY_REFERENCE`) | §16에서 결정 필요 |
| 범위 | 엄선 196건 | 349파일 / 3,603 record |
| 품질 보증 | 사람 검증 | 없음. 잘림·중복·생활습관 문장 섞임 |
| 용도 | Rule 후보 · 최종 값 | **LLM Grounding Context** |

Evidence Store는 canonical일 필요가 없다. 잘린 항목이 있어도 **맥락으로는 쓸 수 있다.**
반대로 Catalog는 잘린 항목이 하나라도 들어가면 Patch 1 같은 사고가 난다.

### 5.2 EvidenceRecord Schema (Prototype에서 실제로 구현·검증)

```python
record_id            ev_<sha12>_<page>_<section>_<seq>   결정론적
source_type          INSTITUTION_SAMPLE | OFFICIAL_PLAY_CASE | OFFICIAL_TOPIC_SUPPORT
                     | PUBLIC_FIELD_CASE
source_path, sha12, page                 재현 가능한 원본 좌표
institution_id, institution_type         기관 · 설립유형
year, month                              월은 파일명 > 본문 순으로 결정
age_scope            (3,) | (4,) | (3,4,5) …
age_evidence_type    SINGLE_AGE_PAGE | MIXED_AGE_PAGE | AGE_UNKNOWN
monthly_theme        그 면의 주제 행 원문
source_section       canonical: outdoor_play | week_experience | indoor_play
                     | indoor_alternative | safety_education | daily_routine | event
source_label         **원문 label 그대로** (바깥놀이 / 실외놀이 / 소주제 / 교사의 기대 …)
week_position        원문에 주차가 명시된 경우만. 없으면 None. **추정 금지**
week_label           원문 주차 표기
experience_text      week_experience 계열 본문
activity_text        그 외 본문
setting              OUTDOOR | INDOOR | INDOOR_ALTERNATIVE | UNKNOWN
template_family      §13 Source Independence 보정용
machine_readability  TEXT_LAYER | IMAGE_ONLY
reuse_policy         CONTEXT_ONLY (P0 기본, §34)
```

**설계 원칙 3개**

1. **원문 label을 canonical로 덮어쓰지 않는다.** 둘 다 남긴다.
2. **`week_position`을 추정하지 않는다.** 없으면 None이다.
3. **`reuse_policy = CONTEXT_ONLY`가 기본이다.** license가 확인되기 전까지
   문장 직접 재사용을 허용하지 않는다.

### 5.3 Ingestion Pipeline (설계)

```text
PDF
 ↓  ① 셀 기하 추출  analysis/tools/cell_extract.py 승격
 ↓     — 줄 기반 16% 손실을 없앤다 (§3.2)
 ↓     — wrap 재결합 · 태그 열 레이아웃 · indoor_alternative 분리는 이미 구현·검증됨
 ↓  ② 페이지 단위 연령 판정 (범위/열거/혼합이면 단일연령 아님)
 ↓  ③ section canonical 매핑 + 원문 label 보존
 ↓  ④ setting 판정 (§ setting-audit의 5신호 우선순위 재사용)
 ↓  ⑤ EvidenceRecord 직렬화 + 결정론적 record_id
 ↓
Evidence Store (JSON → 이후 DB)
```

②④⑤는 이미 `analysis/tools/`에 검증된 구현이 있다. ①만 승격하면 된다.

---

## 6. Retrieval Strategy

### 6.1 Option 비교

| | Option A Metadata-only | Option B Embedding | **Option C Hybrid (권장)** |
|---|---|---|---|
| 적합성 | month/age는 정확하지만 theme 적합도를 못 본다 | theme 적합도는 좋지만 month/age hard filter를 보장 못 한다 | hard filter로 정확성, ranking으로 적합도 |
| 결정성 | 완전 결정론 | 모델·버전에 따라 흔들림 | **ranking만 교체 가능** |
| 인프라 | 없음 | Vector DB + embedding 호출 | **없음** |
| 현재 규모 | 3,603 record | 과잉 | 메모리 안에서 수 ms |

**Option C를 권장한다.** 그리고 **초기 P0에서는 Vector DB를 도입하지 않는다.**
3,603 record는 JSON 로드 + in-memory 필터로 충분하다. Prototype이 그렇게 동작한다.

Embedding이 필요해지는 조건을 미리 적어 둔다:

- Evidence Record가 5만 건을 넘고, 그리고
- 어휘 겹침 ranking이 명백히 놓치는 Case가 재현 가능하게 관찰될 때

그때 교체 지점은 **`retriever.rank()` 함수 하나**다. 나머지 구조는 그대로다.

### 6.2 Retrieval Priority (실제 Corpus를 보고 수정한 안)

지시서 §16의 초안을 Corpus에 대조해 **순서를 바꾸고 한 단계를 나눴다.**

| 순위 | 대상 | 이유 (실측) |
|---:|---|---|
| 1 | **동일 월 + 동일 단일연령 Institution Evidence** | 가장 직접적. 2026-07 만4세에서 tier1이 8건 잡힌다 |
| 2 | **동일 월 + 같은 문서의 연령 대조 면** ← 초안에 없던 단계 | 기관·양식 차이에 오염되지 않은 유일한 연령 근거. 31문서뿐이라 별도 블록으로 보장해야 한다 |
| 3 | 동일 월 + 연령을 포함하는 혼합 Evidence | tier2. 2026-07 만4세 38건 |
| 4 | **동일 월 Week Experience** (연령 무관) | 12개월 전부 MODERATE라 안정적. 연령보다 월 의존이 크다 |
| 5 | 승인 Activity Reference Top-K | canonical. hard filter 통과분만 |
| 6 | 동일 월 그 외 outdoor 관찰값 | scarcity 월의 보충 |
| 7 | Official Play Case (**case 단위**) | §25 정정 반영 |
| 8 | Official Topic Support | theme 맥락 |

**초안과 달라진 점**: "동일 Theme Institution Evidence"를 3순위에서 뺐다.
월과 theme는 Corpus에서 거의 1:1로 묶여 있어(월 = 주제 관행) 별도 축으로 두면
중복 검색이 된다. 대신 theme label을 ranking 신호로만 쓴다.

---

## 7. Source Diversity Strategy

`new-reference-evidence-impact-2026-09.md` §9의 편중이 그대로 위험이다.

> 만4세 근거의 5개월(1·2·10·11·12월)을 **부산광역시청어린이집 한 곳**이 채운다.

Retrieval이 이를 그대로 반영하면 Few-shot이 한 기관 문체를 재현한다.

**적용 규칙 (Prototype 구현)**

```text
기관당 상한       블록별 2건 (AGE-CONTRAST만 3건)
Template Family   {마성, 우리, 키즈로스쿨, 혜솔}을 **한 Source로 묶어 센다**
정렬              어휘 적합도 → 단일연령 우선 → record_id (결정론)
```

효과 확인 (2026-06 만4세): 상한이 없으면 혜솔·유림자연이 블록을 독점하지만,
상한 적용 후 **연제구연산더샵 · 부산광역시청 · 혜솔 · 서진 · 유림자연 · 한나 · 초읍소현
7기관**이 12건에 고르게 들어간다.

추가로 Packet에 **근거 편중 자체를 알린다**(§9의 `age_evidence_strength`).

---

## 8. Monthly Context Packet

### 8.1 블록 정의

| 블록 | Required | Top-K | Retrieval | 측정 Token 비중 |
|---|---|---:|---|---:|
| SYSTEM / ROLE + CONSTRAINTS | 필수 | — | 정적 | 24~27% |
| PLANNING REQUEST | 필수 | — | 입력 그대로 | <2% |
| CONFIRMED YEARLY THEME | 필수 | — | Rule 결과 | <2% |
| WEEK PERIODS | 필수 | — | `canonical_week_periods()` | <1% |
| **INSTITUTION MONTHLY EVIDENCE** | 필수 | 12 | metadata filter(month·section·setting) + 어휘 rank + 기관당 2 | 19~22% |
| **AGE-CONTRAST EVIDENCE** | Optional | 6 | 같은 문서·같은 월·연령만 다른 면 | 1~8% |
| **WEEK EXPERIENCE CANDIDATES** | 필수 | 10 | month filter + 어휘 rank + 기관당 2 | 17~21% |
| **REFERENCE ACTIVITIES** | 필수 | 12 | `eligible_candidates()` + Rule v2 pre-rank | 5~13% |
| OTHER RETRIEVED ACTIVITY EVIDENCE | Optional | 10 | month + outdoor + OUTDOOR setting | 15~17% |
| OFFICIAL PLAY CONTEXT | Optional | 3 | case 단위 age match (§25) | 미측정 |
| OFFICIAL TOPIC CONTEXT | Optional | 2 | theme match | 미측정 |
| PRODUCT CONSTRAINTS | 필수 | — | 정적 | (위에 포함) |
| SAFETY STATE | 필수 | — | Rule 결과 | <1% |
| OUTPUT SCHEMA | 필수 | — | 정적 | (위에 포함) |

### 8.2 실측 결과 (Prototype 5 Case)

```text
Case                 ≈Prompt 문자   Block 반환
2026-03 만3세              5,803   INST 12 · CONTRAST 5 · WEEK 10 · REF 12 · OTHER 10
2026-06 만4세              5,211   INST 12 · CONTRAST 0 · WEEK 10 · REF  7 · OTHER 10
2026-07 만4세              5,476   INST 12 · CONTRAST 4 · WEEK 10 · REF  8 · OTHER 10
2026-08 만4세              5,396   INST 12 · CONTRAST 4 · WEEK 10 · REF  7 · OTHER 10
2027-02 만5세              5,151   INST 12 · CONTRAST 2 · WEEK 10 · REF  4 · OTHER 10

평균 5,407자
```

한국어는 대략 글자당 0.7~1.0 token이므로 **입력 3,800~5,400 token 수준**이다.
GPT-4.1 mini의 컨텍스트에 여유가 크다.

> 2026-06은 AGE-CONTRAST가 0이다. 6월에는 연령 대조 문서가 없다.
> **없는 것을 만들어 넣지 않고, 블록을 비운 채 Optional로 표시한다.**

---

## 9. Age Differentiation

### 9.1 Context 우선순위

```text
1. same institution · same month · age contrast   ← 가장 강함. 31문서
2. single-age institution evidence                 ← 만4세 25면/6기관
3. official age-specific play case (case 단위)     ← 만4세 약 15 case
4. mixed-age evidence
5. general curriculum principles
```

### 9.2 실제로 패킷에 들어가는 것 (2026-07 만4세)

```text
AGE-CONTRAST EVIDENCE
  - 만3세 | 부산광역시청 | [바깥] 여름 맞이 대청소 (블록을 씻어주어요)
  - 만4세 | 부산광역시청 | [바깥] 여름 과일 신체 놀이하기
  - 만3세 | 연제구연산더샵 | [바깥놀이] …
  - 만4세 | 연제구연산더샵 | [바깥놀이] 물놀이 공원 만들기
```

같은 기관·같은 월·같은 양식이므로 **차이가 연령에서만 온다.** LLM 일반상식이 아니다.

### 9.3 근거가 약할 때 — 약함을 숨기지 않는다

Packet에 신호를 넣는다.

```text
AGE CONTEXT
  age_evidence_strength : LOW | MODERATE | STRONG
  single_age_institutions : N
  age_contrast_documents  : N
  note: 근거가 약하면 연령 차이를 과장하지 말고, 확인된 범위 안에서만 조정한다.
```

판정 기준은 §new-reference §4.1과 동일하게 둔다(독립기관 3 이상 = STRONG).
2026-06 만4세는 `age_contrast_documents = 0`이므로 `MODERATE`로 내려간다.

---

## 10. Week Experience Strategy

### 10.1 하지 않을 것

```text
7월 W1 = A
7월 W2 = B      ← 이런 고정 Reference를 Corpus에서 만들지 않는다
```

근거: Week Experience 문서가 33 → 88로 늘었는데도 position별 concept 분포가 평평하다.

```text
W1: 나/몸/마음(9) 날씨/계절변화(8) 친구/우리반(7) 환경/자원(6)
W2: 나/몸/마음(4) 물/여름놀이(4)  날씨/계절변화(4) 도구/기계/디지털(3)
W3: 가족(5) 친구/우리반(4) 전통/명절(4) 자연/동식물(4)
```

같은 concept가 여러 position에 고르게 나온다. **기관 간 순서 합의가 없다.**
Evidence Store의 `week_position` 보유 record도 0이다.

### 10.2 할 것

Source는 **그 달에 등장하는 경험의 범위**를 준다. 순서는 Planner가 구성한다.

```text
WEEK EXPERIENCE CANDIDATES   (주차 번호 없이 후보만)
  - [기대되는] 우리 동네에 있는 다양한 장소의 모습을 알아본다.   (만4세 · 연제구연산더샵)
  - [소주제]  궁금한 우리 동네 모습                             (만3세 · 한나)
  - [소주제]  고마운 우리 동네 기관                             (만3~5세 · 유림자연)
  - [교사의 기대] 놀이를 통해 우리 동네의 공동생활 모습을 경험한다. (만4~5세 · 서진)
```

**Week Experience Reference(고정 Catalog)는 만들지 않는다.** 근거가 없기 때문이다.

---

## 11. Activity Origin Strategy

| 안 | 내용 | 판정 |
|---|---|---|
| A | Reference Activity만 허용 | **불가.** 2027-02 만5세 pool = 4 = 주차 수. 선택이 아니라 나열이 된다 |
| **B** | Reference / Corpus Evidence 우선 + 필요 시 Synthesized | **권장** |
| C | LLM 자유 생성 | **불가.** CLAUDE.md §5 위반 |

### origin 3분류

```text
REFERENCE        승인 Catalog에서 그대로 선택. reference_activity_id 필수.
                 → Plan Item Evidence = ACTIVITY_REFERENCE (현행 그대로)
CORPUS_EVIDENCE  Evidence Store 관찰값에서 가져옴. grounding_source_ids 필수.
                 → Evidence 표현은 §16에서 결정 필요 (OD-N13)
LLM_SYNTHESIZED  위 둘로 채울 수 없어 패킷 근거를 조합해 구성.
                 → grounding_source_ids 필수 + LLM provenance 필수
```

**우선순위 (Q7)**: `REFERENCE > CORPUS_EVIDENCE > LLM_SYNTHESIZED`.
Prompt에 명시하고, Validator가 origin별 필수 필드를 강제한다.

**LLM이 만든 Activity를 Activity Reference에 자동 추가하지 않는다.**
Catalog 승격은 언제나 사람 승인 경로다.

---

## 12. GPT-4.1 mini Planner Contract

### 12.1 Port 확장 (additive)

`shared/llm/port.py`의 `LLMPort` Protocol에 method 하나를 더한다.
기존 `polish_theme` / `polish_themes`는 건드리지 않는다.

```python
class LLMPort(Protocol):
    def polish_theme(self, request): ...          # 기존
    def polish_themes(self, request): ...         # 기존
    def plan_monthly(self, request: MonthlyPlanRequest) -> MonthlyPlanProposal: ...  # 신규
```

`FakeLLM`에도 같은 method를 추가한다(테스트가 실제 호출 없이 돌아야 한다).

### 12.2 실패 계약

기존 예외를 그대로 쓴다 — **새 예외 타입을 만들지 않는다.**

```text
LLMUnavailableError     재시도 후 실패 → Generate 전체 실패
LLMConfigurationError   인증·권한·요청 형식 → 즉시 전파
ValueError              Structured Output 스키마 위반 → 재시도 1회 후 실패
```

---

## 13. Prompt Architecture

`prompt_version = monthly-planner-prompt-v0.1.0-draft` (Prototype 구현, 1,393자)

```text
SYSTEM / ROLE
  역할 경계 — Planner다. 법적/국가 필수 판정을 하지 않는다. 최종 확정은 교사다.

PLANNING GOAL
  한 달 전체를 함께 설계한다. 주차를 따로 뽑아 나열하지 않는다.

PLANNING INPUT
  target_month · ages · week_ids · confirmed theme

EVIDENCE PACKET
  §8의 블록들. id를 함께 준다.

AGE CONTEXT
  age_evidence_strength + 대조 근거

CONSTRAINTS
  주차 수·week_id 정확 일치 / theme_id 그대로 반환 / 길이 상한 /
  중복 금지 / origin별 필수 id

DO NOT
  "공식적으로 권장된다" · "누리과정에서 반드시 한다" · "법적으로 이 주에 해야 한다"
  안전교육 배치·언급
  패킷에 없는 기관명·시설명·행사명
  패킷 문장 그대로 옮겨 적기        ← §34 license

OUTPUT SCHEMA
  JSON only
```

**주차 순서에 대한 문구를 명시적으로 넣는다.**

> 주차 사이에 자연스러운 전개가 있어야 한다. 다만 **그 순서를 공식 규칙처럼 주장하지 않는다.**

---

## 14. Structured Output

Prototype에서 pydantic으로 구현·검증했다.

```json
{
  "theme_id": "yr_theme_summer",
  "month_flow_rationale": "…(300자 이내)",
  "weeks": [
    {
      "week_id": "2026-07-W1",
      "experience": "…(80자 이내)",
      "activity": {
        "value": "…(60자 이내)",
        "origin": "REFERENCE | CORPUS_EVIDENCE | LLM_SYNTHESIZED",
        "reference_activity_id": "act_outdoor_… | null",
        "grounding_source_ids": ["ev_…", "ev_…"]
      }
    }
  ]
}
```

`extra = "forbid"`. `theme_id`는 **검증용**이며 Plan Item에는 Rule이 고른 값이 들어간다 —
`shared/llm/port.py`가 이미 쓰는 4중 방어와 같은 원칙이다.

---

## 15. Deterministic Validation

Prototype `planner_contract.validate_proposal()`로 구현·검증했다.

| rule_id | 검증 | 결정론 |
|---|---|---|
| `monthly_llm.week_count` | 주차 수 일치 | ✔ |
| `monthly_llm.week_ids_exact` | week_id 순서·값 정확 일치 | ✔ |
| `monthly_llm.theme_preserved` | theme_id 불변 | ✔ |
| `monthly_llm.duplicate_activity` | 같은 달 activity 중복 | ✔ |
| `monthly_llm.duplicate_experience` | experience 중복 | ✔ |
| `monthly_llm.reference_id_exists` | REFERENCE id가 패킷·Catalog에 존재 | ✔ |
| `monthly_llm.grounding_required` | CORPUS/SYNTHESIZED는 source id 필수 | ✔ |
| `monthly_llm.grounding_source_exists` | source id가 패킷에 실제로 등장 | ✔ |
| `monthly_llm.no_official_claim` | 금지 표현 사전 매칭 | ✔ |
| `monthly_llm.safety_untouched` | 안전교육 칸 침범 금지 | ✔ |
| `monthly_llm.schema_valid` | pydantic strict | ✔ |

**위반 주입 테스트 결과 (5 Case 전부 동일)**

```text
주입: theme_id 변조 + REFERENCE→SYNTHESIZED 위조 + 없는 source id + 중복 activity + 금지 표현
잡힌 위반: 4  (theme_preserved · duplicate_activity · grounding_source_exists · no_official_claim)
```

**LLM에게 Validator 역할을 맡기지 않는다.**

### 15.1 Semantic Validation의 한계 (§30)

| 검증하고 싶은 것 | 어디서 | 이유 |
|---|---|---|
| 주차 수·id·theme·중복·id 존재·금지 표현 | **Rule (deterministic)** | 문자열·집합 연산으로 완전히 판정된다 |
| "Theme에서 너무 벗어났다" | **Evidence Matching (soft)** | theme label 토큰 겹침 0이면 `THEME_DRIFT_SUSPECTED` 경고. 차단은 하지 않는다 — Corpus의 theme_links가 26% 비어 있어 false positive가 확실하다 |
| "만3세에게 지나치게 어렵다" | **Planner responsibility** | Corpus에 난이도를 명시한 문장이 거의 없다(§new-reference §8.3 Case B). Rule로 판정할 근거가 없다 |
| "주차 흐름이 자연스럽다" | **Planner responsibility + 사람 확인** | 순서 근거가 Source에 0이다. 기계 판정 대상이 아니다 |

**판정 불가한 것을 판정하는 척하지 않는다.** 경고는 `MonthlyGenerationRun`에 남기고
교사가 보게 한다.

---

## 16. Provenance

### 16.1 3축 구조를 유지한다

| 축 | 값 |
|---|---|
| Generation Method | **`RULE_LLM`** — Rule이 후보·제약을 정하고 LLM이 구성한다. 새 enum을 만들지 않는다 |
| rule_id / rule_version | `monthly.llm.evidence_grounded_planner` / `v1` (신규 Rule id) |
| Audit | `CREATED` / `REGENERATED` / `TEACHER_EDITED` / `CONFIRMED` — 변경 없음 |

### 16.2 신규 metadata (GenerationMethodDetail 확장 또는 Run metadata)

```text
planner_model          openai/gpt-4.1-mini      ← 값은 config에서 읽는다
prompt_version         monthly-planner-prompt-v0.1.0-draft
activity_origin        REFERENCE | CORPUS_EVIDENCE | LLM_SYNTHESIZED
grounding_source_ids   [ev_…]
grounding_evidence_types [INSTITUTION_SAMPLE, OFFICIAL_PLAY_CASE]
generated_at
week_order_basis       PLANNER_COMPOSED        ← §Q10의 답
```

### 16.3 `week_order_basis = PLANNER_COMPOSED` — Q10의 답

Source에 주차 순서 근거가 **없다**. 그런데 결과물에는 순서가 있다.
이 간극을 숨기면 나중에 "왜 이 놀이가 2주차인가"에 답할 수 없다.

```text
SOURCE_OBSERVED     원문에 그 주차가 명시되어 있었다        ← 현재 0건
PLANNER_COMPOSED    Planner가 구성했다. Source 근거 아님   ← 현재 전부 이것
TEACHER_ORDERED     교사가 직접 배치했다
```

화면·내보내기에서 `PLANNER_COMPOSED`를 국가 기준처럼 표시하지 않는다
(CLAUDE.md §5.3.3의 "월 배정을 법정 요건처럼 표시하지 않는다"와 같은 성격).

### 16.4 미결 — Evidence Source Type (OD-N13 제안)

`CORPUS_EVIDENCE` / `LLM_SYNTHESIZED` Activity의 Plan Item Evidence를 무엇으로 쓸 것인가.

| 안 | 문제 |
|---|---|
| (a) Evidence를 남기지 않는다 | CLAUDE.md §14 "필요한 Provenance 누락" 검증에 걸린다 |
| (b) `EXTERNAL_CONTEXT` 재사용 | 의미가 다르다. 그 타입은 Trend/Weather 같은 Optional Context용이다 |
| (c) **`INSTITUTION_SAMPLE` 신규 추가** | CLAUDE.md §13.1의 Source Type 목록을 넓히는 변경 → **사람 승인 필요** |

**(c)를 권장하되 임의로 확정하지 않는다.** `OD-N13`으로 등록하고 L0에서 닫는다.
이것이 CLAUDE.md §24가 말하는 "모호함을 숨기지 않는다"에 해당한다.

---

## 17. Generate Flow

```text
GenerateMonthlyPlan.execute(command)
 1  Gate          parent yearly CONFIRMED · template · safety · activity catalog   [현행]
 2  Rule          canonical week periods 산출                                      [현행]
 3  Rule          theme 계승 + theme_id 확정                                       [현행]
 4  Rule          ActivityCatalog.eligible_candidates()  hard filter               [현행]
 5  Rule v2       위 후보를 **pre-ranking** → Top-K                                 [역할 변경]
 6  Retriever     Evidence Store에서 블록 조립 + source diversity                   [신규]
 7  Packet        MonthlyContextPacket 조립 + token budget 확인                     [신규]
 8  LLM           plan_monthly() 1 request                                          [신규]
 9  Validator     §15 deterministic 검증                                            [신규]
10  Domain        MonthlyPlanItem 생성 · Evidence · GenerationMethodDetail          [현행 구조]
11  Rule          cell_state 판정 · safety unresolved 유지                          [현행]
12  Save          DRAFT                                                             [현행]
```

**1~4·10~12는 그대로다.** 5는 역할이 바뀌고 6~9가 새로 들어간다.

---

## 18. Regenerate Flow

P0 원칙 유지 — **cell-only**.

```text
RegenerateMonthlyPlanItem(W3 outdoor)
 1  Gate       DRAFT · CONFIRMED 차단 · catalog lineage exact pin      [현행]
 2  Context    현재 Monthly 전체 + W3의 현재 experience
               + 다른 주차의 activity(중복 회피용) + 그 주차의 Evidence
 3  Retrieval  W3 대상 블록만 다시 조립
 4  LLM        plan_monthly_cell() — **W3 하나만 반환**
 5  Validator  §15 + "다른 주차 불변" 검증
 6  Domain     선택 Cell만 갱신. item_id · semantic_key 보존           [현행]
```

**전체 Monthly 자동 재생성을 기본 동작으로 만들지 않는다.**
Cell 하나의 재생성이 다른 칸을 바꾸면 Validator가 막는다.

---

## 19. Failure Semantics

```text
LLM 호출 실패 (재시도 후)
  → LLMUnavailableError
  → Generate 전체 실패. Plan을 저장하지 않는다.

Structured Output 스키마 위반
  → 1회 repair 재요청 → 그래도 실패하면 Generate 실패

Validator 위반
  → Generate 실패. 위반 목록을 그대로 반환한다.
  → **LLM 출력을 부분 채택하지 않는다.**

금지
  LLM 실패 → 조용히 Rule-only로 되돌아가 성공한 것처럼 저장
```

Rule-only 경로가 필요하다면 **명시적 Product Mode**로만 둔다
(`generation_mode = RULE_ONLY | LLM_PLANNER`). 기본값은 제품 결정 사항이다.

> 참고: 이것은 CLAUDE.md §7의 Optional Dependency Fallback과 **다른 경로**다.
> Trend/Weather 실패는 Core가 성공해야 하지만, Planner LLM은 필수 단계다.
> `shared/llm/port.py`가 이미 이 구분을 문서화하고 있다.

---

## 20. Token / Cost Strategy

측정값 (§8.2): **평균 5,407자 / Case**. 블록별 상대 Budget:

```text
SYSTEM + CONSTRAINTS                 24~27%   정적. 압축 여지 있음
INSTITUTION MONTHLY EVIDENCE         19~22%   Top-12
WEEK EXPERIENCE CANDIDATES           17~21%   Top-10
OTHER RETRIEVED ACTIVITY EVIDENCE    15~17%   Top-10 · Optional
REFERENCE ACTIVITIES                  5~13%   Top-12
AGE-CONTRAST EVIDENCE                  1~8%   Top-6 · Optional
```

### Top-K 근거 (Q4)

```text
Reference 196개 전체 나열   ≈ 7,020자   (id + label만)
Top-K(12)만                ≈   429자   →  6% 규모
```

**196개를 매 호출에 넣지 않는다.** hard filter가 이미 월·연령·slot·setting으로
7~37개까지 줄이고, Rule v2 pre-ranking이 그중 Top-12를 고른다.
실측에서 hard filter 통과가 12 미만인 Case가 4/5였다(7·8·7·4) — **대부분 전량이 들어간다.**

### 비용 절감 수단

1. Raw PDF 텍스트를 넣지 않는다. Evidence Record의 정규화된 한 줄만 넣는다.
2. Optional 블록은 근거가 없으면 비운다(2026-06 AGE-CONTRAST = 0).
3. SYSTEM Prompt는 정적이므로 **prompt caching 대상**이다(공급자 지원 시).
4. 1 request / Monthly. Week-by-week이면 4~5배가 된다(§Q2).

---

## 21. Prototype

`analysis/experiments/monthly_llm_vnext/` — Production을 import하되 **수정하지 않는다.**

| 파일 | 구현 |
|---|---|
| `evidence_store.py` | `EvidenceRecord` dataclass + Corpus → 3,603 record 빌드 |
| `retriever.py` | `MonthlyRetriever` (5 블록) · `diversity_limit()` · `rank()` · `reference_activities()` |
| `planner_contract.py` | SYSTEM Prompt · `MonthlyPlanProposal` pydantic · `render_packet()` · `validate_proposal()` |
| `run_prototype.py` | 5 Case 실행 · token budget 측정 · Validator PASS/위반주입 테스트 |

### 21.1 결과

```text
Case                 ≈Prompt   Validator(정상)   Validator(위반주입)
2026-03 만3세          5,803        PASS              4 위반 검출
2026-06 만4세          5,211        PASS              4 위반 검출
2026-07 만4세          5,476        PASS              4 위반 검출
2026-08 만4세          5,396        PASS              4 위반 검출
2027-02 만5세          5,151        PASS              4 위반 검출
```

### 21.2 2026-06 만4세 — 문제 Case의 Packet 개선

**Production 결과 (Rule-only, 실측)**

```text
Theme 우리 동네   theme_matched 0/4   pool 7개 전부 theme_links=[]
W1 우리 동네에서 일하는 분 찾아보기
W2 분필로 내가 되고 싶은 직업 그림 그리기
W3 꿈을 실은 종이비행기 날리기
W4 병원에서 사용하는 물건 그림 찾기      ← 「직업과 꿈」처럼 읽힌다
```

**새 Packet이 담는 것 (실제 출력)**

```text
INSTITUTION MONTHLY EVIDENCE  (7기관, 기관당 2건 상한 적용)
  만4세 | 연제구연산더샵 | [바깥놀이] 모래로 동네 공원만들기
  만4세 | 연제구연산더샵 | [기대되는] 우리 동네에 있는 다양한 장소의 모습을 알아본다.
  만3~5 | 혜솔          | [바깥놀이] 우리 동네 표지판 찾으며
  만3~5 | 유림자연      | [실외놀이] 우리 동네를 둘러보아요 / 우리 동네 마트에 가요
  만4~5 | 한나          | [실외놀이] 모래로 만드는 우리 동네
  만4~5 | 초읍소현      | [실외] 쓰레기를 분리수거해요(보물찾기)

WEEK EXPERIENCE CANDIDATES
  [소주제] 궁금한 우리 동네 모습 / 재밌는 우리 동네 생활      (한나)
  [소주제] 우리 동네 전통과 문화 / 고마운 우리 동네 기관      (유림자연)
  [기대되는] 우리 동네의 이름과 위치에 관심을 가진다.          (연제구연산더샵)

REFERENCE ACTIVITIES  (7건 = hard filter 전량)
  우리 동네 지도 보며 산책하기 / 모래 위에 그리는 우리 동네 ← Rule이 id 순서로 탈락시켰던 항목
  우리 동네에서 일하는 분 찾아보기 / 분필로… / 꿈을 실은… / 병원에서… / 나의 꿈…

AGE-CONTRAST EVIDENCE
  (해당 근거 없음)   ← 6월에는 연령 대조 문서가 없다. 비운 채로 둔다.
```

Rule이 `activity_id` 해시 순서로 탈락시켰던 `우리 동네 지도 보며 산책하기`와
`모래 위에 그리는 우리 동네`가 **Reference 블록에 그대로 들어간다.** 순서가 아니라
적합도로 고를 수 있는 상태가 됐다.

### 21.3 2027-02 만5세 — Scarcity Case

```text
REFERENCE ACTIVITIES   4건 (= 주차 수. Rule만으로는 선택이 아니라 나열)
OTHER RETRIEVED         10건  ← Evidence Store가 보충
  만5세 | 부산광역시청 | [바깥] 초등학교 탐방
  만4~5 | 연제구연산더샵 | [바깥놀이] 높이 높이 점프 놀이 / 동생과 함께 산책해요
  만4~5 | 서진 | [바깥놀이] 즐거웠던 바깥 놀이를 함께 해요
```

**CORPUS_EVIDENCE origin이 필요한 이유가 여기서 실증된다.**

### 21.4 DESIGN_SIMULATION 표기

**§39 준수.** 위 Validator PASS는 사람이 규칙적으로 만든 예시 Output에 대한 것이다.
GPT-4.1 mini를 호출한 결과가 **아니다.** Prototype은 Context Packet 조립과
Validator 동작을 검증했을 뿐, 생성 품질을 검증하지 않았다.

### 21.5 실제 API 호출을 하지 않은 이유

환경에는 `LLM_MODEL=openai/gpt-4.1-mini`와 Elice MLAPI 설정이 존재한다(키 값은 출력하지 않음).
그러나 **Monthly Planner용 호출 경로(`plan_monthly`)가 Production Adapter에 없다.**
그것을 추가하는 것은 §46 Production Freeze 위반이므로 이번 단계에서 호출하지 않았다.
§37이 허용한 Optional 호출이며, **미호출이 Blocker가 아니다.**

실호출은 L4에서 한다.

---

## 22. Activity Reference v0.2.2 Decision

### 결론: **v0.2.2는 LLM Planner의 선행조건이 아니다.**

| 질문 | 답 |
|---|---|
| 신규 150 Activity Candidate를 전부 v0.2.2로 승격해야 하는가 | **아니다** |
| v0.2.1 + Evidence Store로 먼저 구현할 수 있는가 | **가능하다** |

근거:

1. **신규 150건은 아직 Product Data 품질이 아니다.** 줄 기반 추출이라
   indoor alternative(`대체] 손바닥으로 친구`), 잘림(`우리 동네 표지판 찾으며`),
   생활습관 문장(`정리정돈을 해요`), 전각 괄호 미처리(`［대체］…`)가 섞여 있다.
   Catalog에 넣으면 Patch 1이 고친 유형의 사고가 재발한다.
2. **Evidence Store는 그 품질에서도 유효하다.** 맥락으로 쓰는 것이지 최종 값이 아니다.
   LLM은 잘린 항목을 "이 반을 위한 표현"으로 다시 쓴다(§13 DO NOT: 그대로 옮겨 적기 금지).
3. **두 축을 분리하면 승격 판단을 미룰 수 있다.** 어떤 후보가 실제로 자주 선택되는지
   Planner 운영 데이터를 본 뒤 v0.2.2 승격 대상을 정하는 편이 낫다.

### 권장 순서

```text
지금       v0.2.1 (canonical, 변경 없음)  +  Evidence Store (신규 174건 포함)
↓
L1~L6      LLM Planner 구현. CORPUS_EVIDENCE origin으로 신규 근거 활용
↓
운영 관찰   어떤 CORPUS_EVIDENCE가 반복 선택되는지 수집
↓
v0.2.2     셀 기하 재추출 + 사람 검증 후 **선별 승격**
           동시에 age_scope=[4] evidence 보강 (4 → 대폭 상승)
```

**단 하나의 예외**: `age_support_basis`가 `MIXED_AGE_INFERRED`인 만4세 Activity 95건은
신규 단일연령 근거로 `SINGLE_AGE_EVIDENCE`로 올릴 수 있다. 이것은 Activity를 추가하지 않고
기존 record의 evidence만 보강하는 **순수 additive patch**이므로 v0.2.2에서 먼저 해도 된다.
다만 **Planner를 막지 않는다.**

---

## 23. Production Impact

| 대상 | 분류 | 내용 |
|---|---|---|
| `MonthlyPlan` (domain) | **NO_CHANGE** | Section/Item/week_periods/lineage 구조 그대로 |
| `MonthlyPlanItem` | **NO_CHANGE** | value · evidence · generation · audit 그대로 |
| `EvidenceSource` | **ADDITIVE_CHANGE** | source_type enum 1개 추가 필요 (OD-N13) |
| `GenerationMethodDetail` | **ADDITIVE_CHANGE** | planner metadata 필드 추가. 기존 필드 불변 |
| `GenerationMethod` enum | **NO_CHANGE** | `RULE_LLM` 재사용 |
| `GenerateMonthlyPlan` | **REPLACE_INTERNAL_BEHAVIOR** | Gate/week/theme/cell_state는 그대로, Activity 값 결정 경로만 교체 |
| `EditMonthlyPlanItem` | **NO_CHANGE** | 교사 수정 우선 그대로 |
| `RegenerateMonthlyPlanItem` | **REPLACE_INTERNAL_BEHAVIOR** | cell-only 계약 유지, 내부 선택 경로 교체 |
| `ConfirmMonthlyPlan` | **NO_CHANGE** | |
| Activity Reference | **NO_CHANGE** | v0.2.1 그대로. pin 호환 유지 |
| Theme Reference | **NO_CHANGE** | |
| `LLMPort` | **ADDITIVE_CHANGE** | `plan_monthly` method 추가 |
| Elice Adapter / FakeLLM | **ADDITIVE_CHANGE** | 같은 method 구현 |
| Retriever / Evidence Store | **신규 모듈** | `planning/retrieval/` |
| Prompt | **ADDITIVE_CHANGE** | Monthly Planner prompt 신규. Yearly prompt 불변 |
| Audit / Provenance | **ADDITIVE_CHANGE** | 이벤트 타입 변경 없음 |
| Demo | **ADDITIVE_CHANGE** | 같은 Use Case를 쓰므로 자동 반영. origin 배지 표시만 추가 |
| Golden (`monthly_cases.json`) | **주의 필요** | Rule-only 기대값을 담고 있다. §24 L9에서 별도 처리 |

**BREAKING_CHANGE 없음.** 단 Golden이 기존 Rule 결과를 고정하고 있으므로
`generation_mode`로 두 경로를 분리해 기존 Golden을 살린다.

---

## 24. Implementation Plan

| 단계 | Goal | Files affected | Tests | Completion criteria | Dependencies |
|---|---|---|---|---|---|
| **L0** Contract | Provenance·Evidence Type·generation_mode 결정 | `docs/open-decisions.md` | — | OD-N13 승인. `week_order_basis` 승인 | 사람 승인 |
| **L1** Evidence Ingestion | 셀 기하 추출 승격 + EvidenceRecord 생성 | `src/ssuksak/ingestion/` (신규) · `analysis/tools/cell_extract.py` 승격 | 추출 회귀(조각/alt/wrap) · record schema strict | 349파일 → record, 바깥놀이 행 손실 <2% | L0 |
| **L2** Retrieval | Retriever + source diversity | `planning/retrieval/` (신규) | 결정론 · 기관 상한 · tier 순서 · 빈 블록 | 같은 입력 → 같은 출력. 기관당 ≤2 | L1 |
| **L3** Context Packet | Packet 조립 + token budget | `planning/retrieval/packet.py` | 블록 필수/선택 · budget 상한 | 5 Case 모두 상한 내 | L2 |
| **L4** Planner | `plan_monthly` Port + Adapter + Prompt | `shared/llm/port.py` · `elice_mlapi_adapter.py` · `fake.py` · `prompts/` | FakeLLM 단위 + **live smoke 1건** | 실제 GPT-4.1 mini 1회 성공. 스키마 통과 | L3 |
| **L5** Validator | deterministic 검증 | `planning/rules/monthly_llm_validation.py` | 11개 rule 각각 + 위반 주입 | 위반 주입 전부 검출 | L4 |
| **L6** Generate 통합 | Use Case 배선 + generation_mode | `generate_monthly_plan.py` | 기존 Monthly 테스트 전량 + 신규 | 기존 1644 유지 + LLM 경로 통과 | L5 |
| **L7** Regenerate | cell-only 재생성 | `regenerate_monthly_plan_item.py` | 비대상 Cell 보존 · pin 유지 | 기존 Regenerate 계약 전부 통과 | L6 |
| **L8** Demo | origin 배지 · evidence 보기 | `demo-planning/` | 수동 | 실제 LLM 경로로 화면 동작 | L6 |
| **L9** Golden / Freeze | Golden 분리 + 최종 동결 | `tests/golden/` | 전체 회귀 | Rule-only Golden 불변 + LLM Golden 신규 | L7 |

각 단계는 **이전 단계 없이 시작하지 않는다.** L1이 가장 무겁고(OD-ACTIVITY-INGESTION-01
해소와 겹친다), L4가 가장 위험하다(외부 의존).

---

## 25. Risks

| # | Risk | 근거 | 완화 |
|---|---|---|---|
| 1 | **Hallucination** — 패킷에 없는 놀이·기관·행사 생성 | LLM 일반 위험 | origin 3분류 강제 + `grounding_source_ids` 존재 검증 + 금지 표현 사전 + 패킷 밖 사실 금지 문구. **Validator가 실제로 4/4 검출 확인** |
| 2 | **단일 Source 문체 고착** | 만4세 5개월을 부산광역시청 1곳이 채움 | 기관당 2건 상한 + Template Family 묶기 + `age_evidence_strength` 신호 |
| 3 | **추출 손실이 Grounding 품질을 떨어뜨림** | 바깥놀이 행 16% EMPTY_BODY (실측) | L1에서 셀 기하 추출 승격. 손실률 <2% 완료 기준 |
| 4 | **주차 순서를 규범처럼 오해** | Source 근거 0인데 결과엔 순서가 있음 | `week_order_basis = PLANNER_COMPOSED` 기록 + 화면/내보내기 표시 금지 |
| 5 | **LLM 실패 = Generate 실패** | Planner가 필수 단계가 됨 | 명시적 실패 계약 + `generation_mode`로 Rule-only 경로 보존(조용한 fallback 금지) |
| 6 | **Golden 붕괴** | 기존 Golden이 Rule 결과 고정 | `generation_mode`로 경로 분리. 기존 Golden 불변 유지 |
| 7 | **License** | Official/Public Source 라이선스 미확인 | `reuse_policy = CONTEXT_ONLY`. 문장 복사 금지를 Prompt와 Validator 양쪽에 |
| 8 | **비용/지연** | 매 Generate마다 외부 호출 | 1 request/Monthly · 평균 5.4k자 · 정적 Prompt 캐싱 · Optional 블록 비우기 |
| 9 | **curriculum 축 여전히 공백** | 196/196 `curriculum_links = []` | 이번 설계 범위 밖. 누리과정 균형은 Validation 대상에서 제외하고 명시 |

---

## 26. Open Decisions

| ID | 내용 | 차단 | 결정 시점 |
|---|---|---|---|
| **OD-N13 (신규)** | `CORPUS_EVIDENCE` / `LLM_SYNTHESIZED` Activity의 `EvidenceSourceType`. `INSTITUTION_SAMPLE` 추가 권장 — CLAUDE.md §13.1 목록 확장이므로 사람 승인 필요 | **예** | L0 |
| **OD-N14 (신규)** | `week_order_basis` enum 도입과 화면 표시 정책 | **예** | L0 |
| **OD-N15 (신규)** | `generation_mode`(`RULE_ONLY` / `LLM_PLANNER`) 도입 여부와 기본값 | **예** | L0 |
| `OD-ACTIVITY-INGESTION-01` | 재현 가능한 ingestion pipeline. **L1이 이것의 해소 경로다** | L1을 차단 | L1 |
| OD-N03 | Activity taxonomy (`curriculum_links` 공백 포함) | 아니오 | v0.3 |
| OD-N04 | LLM 공급자·모델·retry 상세 | 아니오 | L4 |
| OD-N11 | Theme/Template/Safety Adapter 승인 우회 입력 제거 | 아니오 | Production Integration |
| 신규 | Activity v0.2.2 승격 범위와 시점 | 아니오 (§22) | Planner 운영 관찰 후 |

---

## 답변 — §42 필수 질문

**Q1. Rule 중심 → Evidence-Grounded LLM Planner 전환이 적절한가?**
**`YES_WITH_LIMITATIONS`.** Rule에는 주차 흐름이라는 개념 자체가 없고(정렬 키에 주차가 없다),
6/12 Case가 해시 정렬이었다. 동시에 Grounding 재료가 질적으로 달라졌다(연령 대조 31문서,
Week Experience 12개월 MODERATE). 제한: 주차 순서 근거가 여전히 0이라 그 부분은
**Planner 책임**으로 남고 Provenance에 그렇게 기록해야 한다.

**Q2. 기본 1회 호출이 적절한가?** **적절하다.** 주차 간 중복 회피·전개 설계가 같은
컨텍스트 안에서 결정되어야 한다. Week-by-week은 4~5배 비용에 더해 "이전 주에 뭘 했는지"를
매번 다시 넣어야 하므로 컨텍스트가 오히려 커진다. 측정된 1회 Prompt는 평균 5,407자다.

**Q3. Runtime에 무엇을 Retrieval하는가?** §6.2의 8단계. 초안과 달리
**연령 대조 블록을 2순위로 승격**하고 "동일 Theme" 축은 제거했다(월과 중복).

**Q4. 196개를 어떻게 줄이는가?** `eligible_candidates()` hard filter(월·연령·slot·setting)로
7~37개 → Rule v2 pre-ranking → **Top-12**. 전체 나열 대비 6%. 실측 5 Case 중 4개는
hard filter 통과가 12 미만이라 전량이 들어간다.

**Q5. 신규 174건을 ingest 없이 Evidence Store로 쓸 수 있는가?** **쓸 수 있다.**
Prototype이 3,603 record로 실제 Packet을 만들었다. Catalog 승격은 별도 경로다.

**Q6. LLM Synthesized Activity를 허용해야 하는가?** **허용한다(Option B).**
2027-02 만5세는 Reference가 4개 = 주차 수여서 선택이 성립하지 않는다. 단 반드시
`origin = LLM_SYNTHESIZED` + `grounding_source_ids` + planner provenance를 남긴다.

**Q7. 우선순위는?** `REFERENCE > CORPUS_EVIDENCE > LLM_SYNTHESIZED`.
Prompt에 명시하고 Validator가 origin별 필수 필드를 강제한다.

**Q8. 연령 차이를 어떤 Context로?** §9.1의 5단계. 1순위는 **같은 문서·같은 월·연령만 다른 면**
(31문서). 근거가 약하면 `age_evidence_strength`로 약함 자체를 전달한다.

**Q9. Week Experience는 고정 Reference보다 Runtime Planning이 적절한가?**
**적절하다.** 순서 근거가 Source에 없으므로 고정 Reference를 만들면 근거 없는 규범을
데이터로 굳히는 것이 된다(CLAUDE.md §8 "샘플 관행을 국가 의무로 해석 금지"와 같은 성격).

**Q10. 순서 근거가 없는데 LLM이 만든 W1→W5를 어떤 Provenance로?**
`week_order_basis = PLANNER_COMPOSED`. `SOURCE_OBSERVED`와 명확히 구분하고,
화면·내보내기에서 국가 기준처럼 표시하지 않는다.

**Q11. Rule v2의 미래 역할?** **B + C + D.**
`B` Retrieval pre-ranking · `C` LLM Context candidate ranking · `D` Validator 지원.
**A(제거) 하지 않는다** — hard filter와 결정론적 순위는 여전히 필요하고,
`generation_mode = RULE_ONLY` 경로도 이 Rule로 유지된다. `E`(Regenerate support)도 남는다.

**Q12. v0.2.2가 선행조건인가?** **아니다.** §22.

**Q13. Hallucination을 무엇으로 막는가?** 5중이다.
① 패킷 밖 사실 금지를 Prompt에 명시 ② origin 3분류 강제 ③ `reference_activity_id` /
`grounding_source_ids`가 **패킷에 실제로 등장한 id**인지 검증 ④ 금지 표현 사전 매칭
⑤ 안전교육 침범 차단. **위반 주입 테스트에서 4/4 검출을 확인했다.**

**Q14. 기존 Monthly Domain을 유지하며 구현 가능한가?** **가능하다.**
`MonthlyPlan` · `MonthlyPlanItem` · `GenerationMethod` · Audit은 NO_CHANGE이고,
`EvidenceSource` · `GenerationMethodDetail` · `LLMPort`가 ADDITIVE다.
BREAKING_CHANGE 없음.

---

## Production Freeze 확인

| 항목 | 상태 |
|---|---|
| `src/` · `data/` · `demo-planning/` · `CLAUDE.md` | **변경 파일 0개** |
| `activity_reference_v0_2_1.json` | `ddbbe43f570cf64ef86db44e7de04e127aec4e663cdb41c26a8fe3c1002dc2ac` |
| `theme_reference_v0.json` | `c12999fa141d5c5fdecf39110adfb2227fc0ab98725991e8bdbca098b3ff4197` |
| `CLAUDE.md` | `a723a7ee488eacdb9b8a95efd07e2516bf247a16fb9f4cc51dfb054867ef78f2` |
| Selection Rule v2 · Production Prompt · Adapter · Golden | 무변경 |
| 테스트 | **`1644 passed, 4 deselected`** — 이전과 동일 |
| Monthly Generate LLM 연결 · Production Retriever · Activity v0.2.2 · Week Experience Reference · Demo 변경 · Weekly | **하지 않음** |

추가된 것은 `analysis/experiments/monthly_llm_vnext/` 4개 Prototype 모듈,
`analysis/tmp/` 산출물, 이 보고서뿐이다.

---

```text
MONTHLY LLM PLANNER VNEXT

Architecture:
  Evidence Store(Corpus 3,603 record) + Activity Reference v0.2.1(canonical 196)
    → Hybrid Retrieval (metadata hard filter + 어휘 ranking + source diversity)
    → Monthly Context Packet (평균 5,407자 측정)
    → GPT-4.1 mini · 1 request · 한 달 전체
    → Structured Output (week별 experience + activity + origin + source ids)
    → Deterministic Validator (11 rule)
    → Monthly DRAFT

LLM Role:
  한 달 Flow 설계 · Week Experience 생성 · 주차 간 전개 · 연령 반영 ·
  Activity 선택 및 Grounded 합성 · 교사 문체.
  법적 판정 · 안전교육 배치 · 국가 필수 주장 · 최종 확정은 하지 않는다.

Rule Role:
  Guardrail + Validator + Pre-ranking.
  Yearly CONFIRMED Gate · week 계산 · theme 계승 · hard filter · cell_state ·
  safety semantics · catalog pin · schema/duplicate/id 검증 · teacher edit 우선 ·
  CONFIRMED read-only. Rule v2는 제거하지 않고 B(pre-ranking)+C(context ranking)+D(validator).

Evidence Store:
  349파일 → 3,603 EvidenceRecord (outdoor_play 628 · week_experience 421).
  Activity Reference와 분리된 retrieval 전용 층. canonical 아님. Plan Item 값이 되지 않는다.
  week_position 보유 0건 — 원문에 주차 근거가 없다는 사실을 그대로 기록.

Retrieval:
  Option C Hybrid. Vector DB 도입하지 않는다(3.6k record는 in-memory로 충분).
  우선순위: 동월·동단일연령 → 동월 연령대조면 → 동월 혼합 → 동월 Week Experience →
            Reference Top-K → 동월 기타 outdoor → Official Play Case(case 단위) → Topic Support.
  기관당 2건 상한 + Template Family 묶음.

Age Differentiation:
  1순위는 같은 문서·같은 월·연령만 다른 면(31문서).
  예) 7월 만3 여름 맞이 대청소 / 만4 여름 과일 신체 놀이하기
  근거가 약하면 age_evidence_strength = LOW 로 약함 자체를 Packet에 전달한다.

Week Experience:
  고정 Reference를 만들지 않는다. Source는 "그 달에 등장하는 경험 범위"만 주고
  순서는 Runtime Planner가 구성한다. 근거: position별 concept 분포가 평평하고
  week_position 보유 record가 0이다.

Activity Origin:
  REFERENCE / CORPUS_EVIDENCE / SYNTHESIZED
  우선순위 REFERENCE > CORPUS_EVIDENCE > LLM_SYNTHESIZED.
  Synthesized는 grounding_source_ids + planner provenance 필수.
  LLM 생성 Activity를 Catalog에 자동 추가하지 않는다.

LLM Calls Per Generate:
  1 (한 달 전체를 한 번에). Regenerate는 대상 Cell 1개당 1.

Activity v0.2.2 Required First:
  NO

Existing Monthly Domain:
  ADDITIVE
  (MonthlyPlan · MonthlyPlanItem · GenerationMethod · Audit = NO_CHANGE.
   EvidenceSource · GenerationMethodDetail · LLMPort = ADDITIVE.
   GenerateMonthlyPlan · RegenerateMonthlyPlanItem = REPLACE_INTERNAL_BEHAVIOR.
   BREAKING_CHANGE 없음.)


TOP RISKS:
1. Hallucination — 패킷 밖 놀이·기관·행사 생성.
   완화 5중(origin 강제 · id 존재 검증 · 금지 표현 · 안전교육 차단 · 패킷 밖 금지 문구).
   위반 주입 테스트 4/4 검출 확인.
2. 단일 Source 문체 고착 — 만4세 5개월을 부산광역시청 1곳이 채운다.
   기관당 2건 상한 + Template Family 묶기 + age_evidence_strength 신호로 완화.
3. 추출 손실 — 바깥놀이 행의 16%가 줄 기반 추출에서 내용을 잃는다(실측 41/253).
   L1에서 셀 기하 추출을 승격해야 하며, 이것이 OD-ACTIVITY-INGESTION-01 해소 경로다.


OPEN DECISIONS:
1. OD-N13  CORPUS_EVIDENCE / LLM_SYNTHESIZED Activity의 EvidenceSourceType.
           INSTITUTION_SAMPLE 추가 권장 — CLAUDE.md §13.1 확장이라 사람 승인 필요. L0 차단.
2. OD-N14  week_order_basis (SOURCE_OBSERVED / PLANNER_COMPOSED / TEACHER_ORDERED)
           도입과 화면 표시 정책. L0 차단.
3. OD-N15  generation_mode (RULE_ONLY / LLM_PLANNER) 도입 여부와 기본값.
           조용한 fallback 금지를 전제로 한다. L0 차단.


IMPLEMENTATION READINESS:

READY_TO_IMPLEMENT
```

---

```text
MONTHLY_LLM_PLANNER_VNEXT_READY_TO_IMPLEMENT
```
