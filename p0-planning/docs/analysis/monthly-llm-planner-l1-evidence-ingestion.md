# Monthly LLM Planner vNext — L1 Evidence Ingestion

- 작성일: 2026-09-13
- 선행: L0 Contract 완료 (`OD-N13` / `OD-N14` / `OD-N15` CLOSED)
- 목적: `OD-ACTIVITY-INGESTION-01`(= OD-N12) 해소 — 재현 가능한 Evidence Ingestion
- 산출물
  - Production 코드 `src/ssuksak/ingestion/` · `src/ssuksak/adapters/pymupdf_source_reader.py`
  - 빌드 진입점 `src/ssuksak/dev/build_evidence_store.py`
  - Artifact `data/evidence/institution_evidence_v0_1_0.json`
  - 테스트 `tests/ingestion/` (122건 신규)
- 범위 밖: L2 Retrieval · L3 Context Packet · L4 LLM Planner · Generate/Regenerate 통합

---

## 1. Scope

### 1.1 대상 Corpus — 실측

```text
references/samples/
├── yearly/   125
├── monthly/  220
└── weekly/     4
합계         349 파일
```

지시서가 기준으로 제시한 349와 **일치한다.** 조정하지 않았다.

### 1.2 Official Source는 L1 범위 밖

`references/official/` 33건은 이번 Pipeline에 넣지 않았다. 월간계획안 표 구조를
전제로 한 셀 기하 추출이 보고서·지도서 레이아웃에 맞지 않고, case 단위 연령 추출
(`docs/analysis/new-reference-evidence-impact-2026-09.md` §3.5)은 다른 Adapter가
적합하다. **L1의 산출물은 `INSTITUTION_SAMPLE` Evidence Store다.**

### 1.3 Image-only 정책

읽을 수 없으면 추정하지 않는다. 존재는 Inventory에 남기고 record를 만들지 않는다.

```text
machine_readability = IMAGE_ONLY
→ record 0건
→ manifest에는 그대로 등재
```

23건이 여기에 해당한다.

---

## 2. Production Ingestion Architecture

```text
src/ssuksak/ingestion/
├── __init__.py            공개 표면
├── models.py              EvidenceRecord + enum 7종 (pydantic strict · frozen)
├── cells.py               표 셀 복원 — **PDF 라이브러리 없음**
├── classifiers.py         연령 · Section · Setting · 대체안 분리 (순수 함수)
├── evidence_builder.py    셀 → EvidenceRecord
├── ports.py               SourceDocument / SourceDocumentReader Protocol
└── pipeline.py            Corpus → IngestionResult → store_payload

src/ssuksak/adapters/pymupdf_source_reader.py   PDF 라이브러리를 여기에만 가둔다
src/ssuksak/dev/build_evidence_store.py         빌드 + Outdoor Loss 감사 진입점
```

### 2.1 PDF 라이브러리를 Port 뒤에 격리한 이유

CLAUDE.md §17 "Port 우선 원칙"을 따랐고, 실질 이유가 둘 있다.

1. **프로젝트 필수 dependency를 늘리지 않았다.** `pyproject.toml`을 건드리지 않았다.
   PDF 파싱은 Evidence Store **빌드 시점**에만 필요하고 Planning Core 런타임에는
   필요 없다. Adapter가 함수 안에서 lazy import하고, 없으면 `PdfSourceError`로
   명확히 실패한다.
2. **셀 복원 규칙을 PDF 없이 테스트한다.** `tests/ingestion/`은 좌표만 주입하는
   Fake Reader를 쓰므로 PDF 라이브러리 없이 전체 파이프라인이 돈다.

이 결정의 미결 부분은 `OD-N16`으로 등록했다(§13).

### 2.2 빌드 방법

```bash
PYTHONPATH="<pdftools 격리 설치 경로>;src" python -m ssuksak.dev.build_evidence_store
```

---

## 3. EvidenceRecord Contract

```text
record_id            ev_<sha12>_p<page>_r<row_top>_c<col>_i<index>   결정론적
source_type          INSTITUTION_SAMPLE                              (OD-N13)
source_path · source_sha256 · page                                   재현 좌표
institution_id · institution_type
year · month
age_scope · age_evidence_type   SINGLE_AGE_PAGE | MIXED_AGE_PAGE | AGE_UNKNOWN
monthly_theme
source_section       canonical (8종)
source_label         **원문 그대로**
week_position · week_label      원문에 있을 때만. 추정 금지
experience_text · activity_text
setting              OUTDOOR | INDOOR | INDOOR_ALTERNATIVE | UNKNOWN
template_family · machine_readability
reuse_policy         CONTEXT_ONLY | PRODUCT_OUTPUT_ALLOWED           (OD-N13 파생)
extraction_quality   VALID | NEEDS_REVIEW | INVALID                  (OD-N13 파생)
extraction_method    table_line_geometry_v1                          Audit
source_cell          row_top · row_bottom · column · item_index      Audit
```

`extra="forbid"` · `frozen=True`. 미지 필드·잘못된 enum·범위 밖 연령·잘못된 월은 거부한다.

### 3.1 파생값은 저장하지 않는다

```python
general_grounding_eligible == (machine_readability == TEXT_LAYER
                               and extraction_quality == VALID)

outdoor_activity_eligible  == (general_grounding_eligible
                               and source_section == outdoor_play
                               and setting == OUTDOOR)
```

CLAUDE.md §8의 `runtime_active == (domain_owner_approval == HUMAN_APPROVED)`와 같은
파생 원칙이다. 독립 writable 스위치를 만들지 않는다. 테스트가 이를 고정한다.

**일반 eligibility와 outdoor eligibility를 분리했다.** 실내대체 record는 일반 Context로는
유효하지만 outdoor 후보가 될 수 없다. 하나의 플래그로 합치면 그 구분이 사라진다.

### 3.2 Domain Enum과의 관계

`ingestion.EvidenceSourceType.INSTITUTION_SAMPLE`은 OD-N13이 승인해 CLAUDE.md §13.1과
`docs/screen-spec.md` §6.1에 등재된 값이다. **Domain `provenance.EvidenceSourceType`은
이번에 바꾸지 않았다** — Plan Item Evidence를 실제로 기록하는 것은 L4~L6의 일이고,
L1은 Evidence Store만 만든다. 두 enum의 문자열 값이 같은지는 테스트가 고정한다
(`test_source_type_value_matches_approved_contract`).

---

## 4. Cell Geometry Extraction

### 4.1 무엇이 달라졌는가

```text
줄 기반   `바깥` 행의 내용이 다음 visual line에 있으면 그 줄은 비어 보인다.
셀 기반   행 label과 내용은 **서로 다른 셀**이다. 같은 row band의 다른 열을
          읽으므로 줄바꿈 위치와 무관하다.
```

`build_cells()`는 표의 수직/수평 선분으로 row band와 column을 복원한 뒤 셀 안에서만
줄을 재결합한다. **표 선이 없으면 빈 결과를 돌려준다. 추측으로 셀을 만들지 않는다.**

### 4.2 wrap과 list를 가르는 기준

종결 형태다. 길이나 들여쓰기는 쓰지 않는다 — 이 Corpus의 표는 가운데 정렬이라
들여쓰기가 wrap 신호가 되지 못한다. `bare 이`를 종결로 보지 않는 예외
(`물웅덩이` · `무궁화꽃이`)도 그대로 승격했다.

### 4.3 회귀 Case (전부 실제 Corpus)

| 구분 | Case | 결과 |
|---|---|---|
| wrap 재결합 | `장화 신고 물웅덩이` + `건너기` | `장화 신고 물웅덩이 건너기` |
| wrap 재결합 | `자연물로 여름 디저트` + `만들기` | `자연물로 여름 디저트 만들기` |
| **합치면 안 됨** | `투호놀이` / `줄다리기를 해요` / `동대문 놀이` | 3개 유지 |
| 구두점 보존 | `우리집에 왜 왔니? 놀이를 해요.` | 하나로 유지 |
| 괄선 없는 하위 열 | `무궁화 꽃이 피었습니다   모래사막을 구성해요` | 2개로 분리 |
| 태그 열 레이아웃 | `우리 동네 마트 [바깥] 방문하기` | 본문 `우리 동네 마트 방문하기` + OUTDOOR |
| 인라인 태그 다중 항목 | `<추석> 명절전통놀이 <세계…> 볼리비아의…` | 항목별 분리 |
| 표 선 없음 | — | 빈 결과. record 0건 |

### 4.4 추출 과정에서 잡은 실제 결함 4건

전부 Prototype에는 없던 것이며, Production 전환 중 원문 대조로 찾아 고쳤다.

| # | 결함 | 원문 사례 | 처리 |
|---|---|---|---|
| 1 | 여는 괄호가 잘린 대체 표시 | `대체) 부채로 휴지떼기` (연제구연산더샵 7월) | `_LEADING_ALT`에 닫는 괄호만 있는 형태 추가 |
| 2 | 태그 전용 열 + wrap → 태그가 항목 **가운데**로 들어감 | `장바구니에 공 [대체] 넣기` (예일 6월) | `extract_position_tag()` — 태그를 떼고 setting 신호로 사용 |
| 3 | 한 셀에 여러 활동이 인라인 태그로 이어짐 | `<자랑스런우리나라> 동대문놀이… <추석> 명절전통놀이…` (큰빛 9월) | `<태그>` 앞에서 분할 |
| 4 | 본 항목과 대체안이 한 문자열에 붙음 | `무궁화 꽃이 피었습니다. 【대체활동 : 강강술래를 해요】` | `split_alternatives()` — 둘을 별도 record로 |

추가로 Section 분류에서 두 건을 더 고쳤다(§6.3).

---

## 5. Age Classification

**문서가 아니라 면(page) 단위로 판정한다.** 한 PDF 안에 만3세 면 / 만4세 면이 따로
있는 자료가 실제로 존재하기 때문이다(부산광역시청어린이집은 한 파일에 3개 연령 면).

단일연령이 **아닌** 조건:

```text
범위 표기   만3~5세
열거 표기   만4,5세 · 만4·5세
`혼합` 낱말
같은 면에 서로 다른 연령이 따로 적힌 경우
```

만0~2세는 P0 Target 밖이므로 `age_scope`에서 제외한다(schema가 거부).

결과:

```text
SINGLE_AGE_PAGE  6,795
MIXED_AGE_PAGE   4,306
AGE_UNKNOWN      1,266
```

---

## 6. Section / Setting Classification

### 6.1 원문 label을 덮어쓰지 않는다

`source_section`(canonical 8종)과 `source_label`(원문)을 둘 다 남긴다.

```text
outdoor_play · indoor_play · indoor_alternative · week_experience
safety_education · daily_routine · event · theme · unknown
```

### 6.2 Setting — setting audit의 5신호를 그대로 승격

`docs/analysis/activity-v0-2-1-setting-audit.md`가 196 Activity / 288 Evidence를
전수 재검증하며 10종의 오탐을 잡아 확정한 우선순위다. 구체적인 쪽이 이긴다.

```text
① 항목 자신이 대체 표시로 시작        [실내대체] 몸으로 자음 …
② 대체 표기가 있는 줄
     내용포함형 【대체활동 : X】     괄호 안이 대체안
     구분자형   A [실내대체] B       괄호 뒤가 대체안
③ 괄호 없는 접두 표기                ♥바깥놀이-비석치기
④ 셀 안 인라인 태그                  <바깥놀이> …
⑤ 행 label
```

`실내외 놀이`는 실내와 실외를 함께 가리키므로 **어느 쪽 근거도 아니다**(판정하지 않음).
`팽이 놀이`가 `실팽이 놀이` 안에서 매칭되던 Patch-1 오탐도 회귀 테스트로 고정했다.

### 6.3 Section 분류에서 고친 실제 오탐 2건

| # | 오탐 | 원문 | 수정 |
|---|---|---|---|
| 5 | `바깥놀이 (대체활동)` 병합 행 label을 실내대체로 읽어 **서진어린이집 5개 월간계획안의 바깥놀이 항목이 통째로 사라짐** | `바깥놀이 (대체활동)` · `바깥놀이 [대체활동]` | OUTDOOR를 INDOOR_ALTERNATIVE보다 **먼저** 본다. 어느 항목이 대체안인지는 항목 단위로 판정 |
| 6 | `텃밭` · `산책`이 다른 행 label 안에 섞여 **연간계획 목표 문장이 outdoor 후보가 됨** | `4월 m식목일 기념 모종심기/가족 과 함께 하는 텃밭 이야기` (경상남도청 연간) | 약한 토큰(산책·텃밭·나들이·숲)은 **label이 짧을 때만** 바깥놀이 행으로 본다 |

### 6.4 Setting 분포

```text
UNKNOWN               9,592   실내놀이·일상생활·행사 등 setting이 의미 없는 행
OUTDOOR               1,428
INDOOR                  774
INDOOR_ALTERNATIVE      573
```

---

## 7. Reuse Policy

L0 Contract(OD-N13 파생)를 그대로 구현했다.

```text
CONTEXT_ONLY             P0 기본. Grounding Context로만. 원문 문자열 직접 재사용 금지
PRODUCT_OUTPUT_ALLOWED   라이선스·계약 근거가 확인된 Record에만
```

**이번 Corpus에서 `PRODUCT_OUTPUT_ALLOWED`로 올린 Record는 0건이다.**
기관 계획안은 라이선스 근거가 없으므로 12,367건 전부 `CONTEXT_ONLY`다.

귀결: `CONTEXT_ONLY` Record를 근거로 만든 Activity의 origin은 `LLM_SYNTHESIZED`다.
`CORPUS_EVIDENCE` origin은 현재 사실상 비활성이며, 이 사실은 L0에서 이미 기록했다.

---

## 8. Extraction Quality

```text
VALID          셀 구조 복구 성공 · 내용 완결 · fragment 징후 없음
NEEDS_REVIEW   절단 가능성 · ambiguous section · 다항목 병합 의심
INVALID        empty body · 3자 미만 · 한글 없음 · section label 메아리
```

판정 규칙:

| 조건 | 등급 |
|---|---|
| 빈 값 · 한글 제외 3자 미만 · 한글 없음 | INVALID |
| 행 label이 내용 칸에 그대로 메아리 (`바깥놀이`, `주제`, `영역` …) | INVALID |
| 80자 초과 | NEEDS_REVIEW |
| **outdoor 항목이 40자 초과** (중앙값 12자) | NEEDS_REVIEW |
| 연결어미·조사로 끝남 (`…으로`, `…를`) | NEEDS_REVIEW |
| 그 자체로 활동명이 될 수 없는 꼬리말 (`놀이를 해요.`) | NEEDS_REVIEW |
| section 판정 불가 / outdoor인데 setting UNKNOWN | NEEDS_REVIEW |
| 그 외 | VALID |

**`놀이를 해요.` 처리에 대한 기록**: `친척집에 왜 왔니?` / `놀이를 해요.`처럼 한 활동이
두 줄로 나뉘었는데 앞줄이 물음표로 끝나 종결로 보이는 Case가 있다(연제구연산더샵 5월).
물음표를 무조건 비종결로 바꾸면 `우리집에 왜 왔니?`가 단독 활동명인 다른 Source가 깨진다.
**그래서 합치지 않고 꼬리말 쪽을 NEEDS_REVIEW로 내렸다.** 추측으로 붙이지 않는다.

---

## 9. Corpus Statistics

```text
files scanned              349
  text-readable            326
  image-only                23
  table 선 없음 (readable)    6      전부 연간계획안. §13 참조
  failed                     0

pages scanned              664
pages with cells           579

records total           12,367

by section
  indoor_play            3,353
  daily_routine          1,927
  safety_education       1,845
  event                  1,608
  outdoor_play           1,439
  week_experience        1,410
  indoor_alternative       785

by setting
  UNKNOWN                9,592
  OUTDOOR                1,428
  INDOOR                   774
  INDOOR_ALTERNATIVE       573

by age_evidence_type
  SINGLE_AGE_PAGE        6,795
  MIXED_AGE_PAGE         4,306
  AGE_UNKNOWN            1,266

by extraction_quality
  VALID                 11,268
  INVALID                  799
  NEEDS_REVIEW             300

general_grounding_eligible   11,268
outdoor_activity_eligible     1,335
week_experience eligible      1,234
week_position present             0
```

`week_position = 0`은 버그가 아니라 결과다. **줄 단위 원문에 "이 항목은 2주차"라고
적힌 근거가 없다.** 월간 표에서 위에서 두 번째라는 이유로 W2라고 추론하지 않는다
(OD-N14가 `PLANNER_COMPOSED`를 도입한 근거와 같다).

---

## 10. Outdoor Loss Audit

### 10.1 정의 — 분모를 바꿔 손실률을 낮추지 않았다

```text
분모  Source에 바깥놀이 행이 있고 그 행의 내용 칸에 글자가 있는 경우
분자  그 행에서 usable body(extraction_quality != INVALID)를 하나도 복원하지 못한 경우
```

행 label 어휘는 **줄 기반 baseline(16%)이 쓴 것과 같다** — `바깥` · `실외` 계열만.
`산책` · `텃밭` · `나들이`는 baseline 분모에 없었고 다른 행 label 안에도 흔히 나오므로
넣지 않았다. 이 정의는 `is_outdoor_row_label()`에 있고 테스트가 고정한다.

### 10.2 결과

```text
outdoor rows observed         286
outdoor rows recovered        286
outdoor rows lost               0
outdoor loss rate           0.00%       ← 목표 < 2%

indoor alternative leakage      0
false outdoor classification    0
```

분모가 253(줄 기반) → 286(셀 기반)으로 **늘었다.** 셀 기하가 바깥놀이 행을 더 많이
찾아냈다는 뜻이며, 분모를 줄여 손실률을 낮춘 것이 아니다.

### 10.3 독립 교차 검증

줄 기반에서 `바깥`/`실외` 행의 본문이 비어 있던 **41건 / 31개 파일**을 따로 추적했다.

```text
줄 기반 EMPTY_BODY 파일 31개 → 셀 기반에서 outdoor eligible record 복원 31개 (100%)
```

### 10.4 Precision — loss를 0으로 만들려고 억지로 결합하지 않았다

| 지표 | 값 |
|---|---|
| 실내대체 누출 (outdoor eligible인데 본문에 대체 표시가 남음) | **0** |
| false outdoor (행 label이 실내인데 outdoor로 분류) | **0** |
| outdoor 항목 길이 중앙값 | 12자 |
| 40자 초과 outdoor 항목 | VALID에서 제외(NEEDS_REVIEW) |

Precision을 위해 오히려 **VALID를 줄이는 방향**으로 판정을 조였다(§8). 그 결과
`outdoor_activity_eligible`이 1,341 → 1,335로 줄었지만 누출이 0이 되었다.

---

## 11. Regression Cases

### 11.1 Fragment (Patch 1이 고친 결함)

| 조각 | 단독 VALID record |
|---|---:|
| `건너기` | **0** |
| `장화 신고 물웅덩이` | **0** |
| `우리집에 왜 왔니?` | **0** |
| `놀이를 해요.` | **0** |

복원형 `장화 신고 물웅덩이 건너기`는 2건 존재한다
(`ev_1a6ef215aed9_p01_r00598_c02_i02`, `ev_6de3b1a4b668_p01_r00620_c04_i02`).

### 11.2 §21 Grounding Quality Audit

| Case | 결과 |
|---|---|
| 2026-06 만4세 | outdoor record 7 / 기관 2 (부산광역시청 · 연제구연산더샵) |
| 2026-07 만4세 | outdoor record 8 / 기관 2 |
| 2026-08 만4세 | outdoor record 7 / 기관 2 |
| `우리 동네` | 6월 만4세에 `우리동네를 둘러보아요` · `모래로 동네 공원만들기` · `깨끗한 우리 동네 만들기` 복원 |
| `여름` | 7월 만4세에 `물놀이 공원 만들기` · `물총놀이` · `칫솔 이어 달리기` 복원 |
| `교통기관` | 8월 만4세에 `움직이는 교통기관 관찰해요` · `우리동네 버스 정류장을 살펴봐요` 복원 |
| `팽이놀이` setting | `<바깥놀이> 팽이놀이(대체활동: …)` → OUTDOOR (회귀 테스트 고정) |
| 실내대체 누출 | 0 |

### 11.3 §22 신규 Corpus 주요 Activity — 원문 좌표와 함께

| Activity | record_id | 출처 | 판정 |
|---|---|---|---|
| 모래로 동네 공원만들기 | `ev_a83b8c06154a_p01_r00383_c515_i01` | 연제구연산더샵 6월 p1 | OUTDOOR / VALID |
| 물놀이 공원 만들기 | `ev_60038759cf41_p01_r00363_c258_i01` | 연제구연산더샵 7월 p1 | OUTDOOR / VALID |
| 물총놀이 | `ev_1338255e6c67_p01_r00596_c03_i02` | 한나 7월 p1 | OUTDOOR / VALID |
| 여름 과일 신체 놀이하기 | `ev_8e0b4da66d80_p02_r00369_c02_i03` | 부산광역시청 7월 p2 | OUTDOOR / VALID |
| 움직이는 교통기관 관찰해요 | `ev_682cdb9981af_p02_r00393_c258_i01` | 연제구연산더샵 8월 p2 | OUTDOOR / VALID |
| 우리동네 버스 정류장을 살펴봐요 | `ev_682cdb9981af_p02_r00393_c259_i01` | 연제구연산더샵 8월 p2 | OUTDOOR / VALID |
| 허수아비 놀이하기 | `ev_0891b1631dc5_p02_r00372_c02_i01` | 부산광역시청 2025-11 p2 | OUTDOOR / VALID |
| **초등학교 탐방** | — | 부산광역시청 2월 | **정확 일치 없음** (§13 잔여 한계) |

**이 Activity들을 Activity Reference에 추가하지 않았다.** Evidence Store 관찰값이다.

### 11.4 Test Suite

```text
기존   1,644 passed, 4 deselected
현재   1,766 passed, 4 deselected      (+122 신규, 기존 실패 0)
```

| 파일 | 건수 | 내용 |
|---|---:|---|
| `tests/ingestion/test_cells.py` | 40 | 종결 판정 · wrap 재결합 · false merge 방지 · 구두점 · 하위 열 · 셀 복원 · 결정론 |
| `tests/ingestion/test_classifiers.py` | 57 | 연령 5종 · Section · 행 label · Setting 4종 · 태그 열 · 대체안 분리 |
| `tests/ingestion/test_pipeline.py` | 25 | strict schema · 파생값 비writable · 결정론 · image-only · 표 선 없음 · Artifact |

**모든 테스트가 PDF 라이브러리 없이 돈다.** Fake Reader를 Port에 주입한다.

---

## 12. Artifact Version / SHA

```text
파일              data/evidence/institution_evidence_v0_1_0.json
schema_version    institution-evidence.schema.v0
ingestion_version institution-evidence-ingestion-v0.1.0
store_id          ssuksak.institution-evidence
normative_status  CORPUS_OBSERVATION_NON_NORMATIVE
record_count      12,367
크기              10,947,167 bytes

content_sha256    52b409557d3503422aa0109664298976bd7f831ed18304b818aaad936916e5ea
```

### 12.1 재현성 — build metadata를 content에서 분리했다

`generated_at`이 content에 섞이면 같은 내용을 다시 만들 때마다 전체 SHA가 달라져
재현성을 확인할 수 없다. 그래서 Artifact를 두 부분으로 나눴다.

```json
{ "schema_version": …, "records": [ … ],      ← content. content_sha256의 대상
  "build": { "generated_at": …, "content_sha256": … } }   ← build metadata
```

연속 2회 빌드에서 `content_sha256`이 동일함을 확인했고, 테스트가 이를 고정한다.

### 12.2 Versioning — 승인 의미를 자동 부여하지 않는다

`normative_status = CORPUS_OBSERVATION_NON_NORMATIVE`이고 `HUMAN_APPROVED`가 아니다.
Evidence Store는 **Corpus Observation Artifact**이지 canonical Activity Catalog가 아니다.
Artifact의 `disclaimer`가 이를 명시하고 테스트가 고정한다.

### 12.3 Freeze 확인 — 승인 Artifact 전부 불변

```text
activity_reference_v0_2_1.json   ddbbe43f570cf64ef86db44e7de04e127aec4e663cdb41c26a8fe3c1002dc2ac
activity_reference_v0_2.json     e27ebca3342a84327c6624c5ba258b9bc98aef37ba5362b61f283c47ece0bde6
theme_reference_v0.json          c12999fa141d5c5fdecf39110adfb2227fc0ab98725991e8bdbca098b3ff4197
monthly_template_a.json          1f35322dd52f832bffc3057953ecbd64d52c2d855ada964af68472ebba1a7c34
safety_education_legal_v1.json   5831809b19a28505844cf10363c95eeb09ec4641d5fe54a26afdb1891c3ddba5
tests/golden/monthly_cases.json  c605641232d91abd1d6d2babb52a45b81ff8ea9de4c9bb3190cd68b5c62c85a7
tests/golden/yearly_cases.json   7918e9f9cbe23580e7621e2f7c7ce40825a073afb8b0dc2038640a1291a6b384
```

Activity v0.2.2를 만들지 않았다. Selection Rule v2 · LLM Adapter · Prompt ·
GenerateMonthlyPlan · RegenerateMonthlyPlanItem · Demo를 수정하지 않았다.

---

## 13. Open Issues

### 13.1 표 선이 없는 readable 파일 6건

```text
2026_국공립_공립바른어린이집_만3,4,5세_연간보육계획안.pdf
2026_국공립_퇴계한숲어린이집_만3,4,5세_연간보육계획안.pdf
2026_민간_굿모닝어린이집_만3세,4세,5세_연간보육계획안.pdf
2026_민간_조은어린이집_만3세,만4세,만5세_연간계획안.pdf
2026_법인·단체_사포어린이집_만4-5세_연간계획안.pdf
2026_사회복지법인_사임당어린이집_만3-5세_연간보육계획안.pdf
```

전부 **연간계획안**이다. 표 선을 그리지 않는 레이아웃이라 셀을 복원할 수 없다.
추측으로 셀을 만들지 않았고 record 0건으로 남겼다. Outdoor Grounding에는 영향이 없다
(월간계획안이 아니다).

### 13.2 `초등학교 탐방` — 남은 wrap 병합 1건

```text
초등학교 탐방 젓가락으로 냠냠 - 꿈 실은 종이비행기 날리기
```

`초등학교 탐방`이 종결 형태가 아니어서 다음 줄과 결합했다. 40자 초과라
**NEEDS_REVIEW로 내려가 Grounding에서 빠진다.** 손실이 아니라 품질 하향이므로
loss 지표에는 잡히지 않고, 사람 검토 대기열에 남는다.

### 13.3 `column` 인덱스의 의미

`source_cell.column`은 그 row band의 수직 선분에서 만든 **격자 인덱스**이지 의미 있는
"몇 번째 열"이 아니다. 셀 경계를 여러 작은 선분으로 그리는 PDF에서는 값이 크게 나온다
(예: `c515`). 좌표 재현에는 충분하지만 열 번호로 해석하면 안 된다.

### 13.4 OD-N16 — PDF 라이브러리 의존성 (신규 OPEN)

`pymupdf`를 `pyproject.toml`에 넣을지 미결이다. 현재는 Port 뒤 lazy import이며
전체 테스트가 PDF 라이브러리 없이 돈다. 결정해야 할 것: Evidence Store 재빌드를
CI에 넣을지, 넣는다면 일반 dependency인지 optional extra인지, 그리고 PyMuPDF의
AGPL/상용 듀얼 라이선스 검토. **L2를 막지 않는다.**

### 13.5 여전히 OPEN

```text
OD-N03  Activity taxonomy (curriculum_links 공백 포함)
OD-N04  LLM 공급자·모델·retry 상세
OD-N11  Theme/Template/Safety Adapter 승인 우회 입력 제거
OD-N16  PDF 라이브러리 의존성 (신규)
Activity v0.2.2 승격 범위와 시점
```

---

## 14. OD-ACTIVITY-INGESTION-01 Status

```text
OD-N12 (= OD-ACTIVITY-INGESTION-01)   CLOSED — 2026-09-13
```

완료조건 전부 충족했다.

| 조건 | 결과 |
|---|---|
| cell geometry productionized | `ingestion/cells.py` + Port 뒤 Adapter |
| deterministic ingestion | 연속 2회 `content_sha256` 동일. 테스트 고정 |
| strict EvidenceRecord | pydantic `extra="forbid"` · frozen · 파생값 비writable |
| **outdoor loss < 2%** | **0.00%** (286행 중 0) |
| fragment regression | 조각 4종 단독 VALID 0건 |
| indoor alternative regression | 누출 0 · false outdoor 0 |
| full Corpus reproducible ingestion | 349 파일 · 664면 · 12,367 record |

**닫지 않은 것**: Activity Reference v0.2.2 승격 범위는 그대로 OPEN이다.
Evidence Store는 Corpus 관찰값이고 canonical Catalog가 아니다.

---

## 15. 반드시 답할 질문 (§31)

**Q1. Outdoor loss가 16%에서 얼마로 줄었는가?**
**16% → 0.00%.** 바깥놀이 행 286건 중 손실 0건이다. 분모는 줄 기반 baseline과 같은
어휘로 셌고 253 → 286으로 **늘었다**. 독립 교차 검증에서도 줄 기반 EMPTY_BODY였던
31개 파일 전부가 복원됐다.

**Q2. False merge 또는 잘못된 Activity 결합은 없는가?**
`초등학교 탐방 젓가락으로 냠냠 - 꿈 실은 종이비행기 날리기` **1건**을 확인했다.
40자 초과 규칙에 걸려 NEEDS_REVIEW로 내려가 Grounding에서 제외된다. 그 밖에
`투호놀이` / `줄다리기를 해요` / `동대문 놀이` 같은 세로 나열을 합치지 않는 것은
회귀 테스트로 고정했다. false outdoor 분류는 **0건**이다.

**Q3. Indoor Alternative가 Outdoor로 누출되는 Case는 몇 건인가?**
**0건.** 작업 중 38건을 발견해 전부 고쳤다 — 원인은 ① 여는 괄호가 잘린 `대체)` ②
태그 열 레이아웃에서 태그가 항목 가운데로 들어감 ③ 본 항목과 대체안이 한 문자열에
붙음. 세 가지를 각각 `_LEADING_ALT` 확장 · `extract_position_tag()` ·
`split_alternatives()`로 처리했다.

**Q4. VALID / NEEDS_REVIEW / INVALID는 각각 몇 건인가?**

```text
VALID         11,268   (91.1%)
INVALID          799   ( 6.5%)
NEEDS_REVIEW     300   ( 2.4%)
합계          12,367
```

**Q5. 실제로 Runtime Grounding 가능한 Record는 몇 건인가?**

```text
general_grounding_eligible    11,268
  그중 outdoor_activity_eligible  1,335
  그중 week_experience             1,234
```

**Q6. 만3 / 만4 / 만5별로 Grounding 가능한 Institution Evidence가 충분한가?**

| 연령 | 단일연령 eligible | 기관 | 그중 outdoor | 기관 | week_experience |
|---|---:|---:|---:|---:|---:|
| 만3세 | 4,101 | 28 | 463 | 19 | 470 |
| **만4세** | **908** | **11** | **87** | **9** | **39** |
| 만5세 | 1,102 | 21 | 89 | 14 | 46 |

**L2 Retrieval을 시작하기에는 충분하다.** 만4세 outdoor 87건 / 9기관은
Top-K 12 · 기관당 2건 상한 구조에서 모든 월을 채울 수 있는 규모다.
다만 **만4세 week_experience가 39건으로 가장 얇다** — 이는 Corpus 자체의 한계이며
(`new-reference-evidence-impact-2026-09.md` §5.3) Ingestion이 만들어낼 수 없다.

**Q7. 2026-06/07/08 만4세에서 새로운 Corpus Evidence가 정상 복원되는가?**
**복원된다.** 세 달 모두 outdoor record 7~8건 / 독립기관 2곳
(부산광역시청어린이집 · 연제구연산더샵어린이집). 특히 6월 만4세는 줄 기반에서
`바깥` 행이 통째로 비어 있던 Case인데, 셀 기반에서 `초록 블록으로 공공기관 만들기` ·
`줄을 다양한 방법으로 지나가 보기`가 복원되고 `［대체］달팽이 끈으로 …` ·
`［대체］실내에서 볼링하기`는 실내대체로 정확히 분리됐다.

**Q8. 같은 Input에서 Artifact가 재현 가능한가?**
**가능하다.** 연속 2회 빌드에서 `content_sha256 = 52b40955…`가 동일했다.
`record_id`는 순회 순번이 아니라 **셀의 원문 좌표**(sha12 · page · row_top · column ·
item_index)에서 만들어지므로 파서 순회 순서가 바뀌어도 같다. 테스트 4건이 고정한다.

**Q9. OD-ACTIVITY-INGESTION-01을 닫을 수 있는가?**
**닫을 수 있다.** §14의 7개 완료조건을 전부 충족했다. 단 Activity v0.2.2 승격 범위는
별개 사안으로 OPEN이다.

---

```text
MONTHLY LLM PLANNER L1

Sources:
  349 파일 (yearly 125 · monthly 220 · weekly 4)
  text-readable 326 · image-only 23 · 표 선 없는 readable 6 · 실패 0
  664면 스캔 · 579면에서 셀 복원

Evidence Records:
  12,367
  section  indoor_play 3,353 · daily_routine 1,927 · safety_education 1,845 ·
           event 1,608 · outdoor_play 1,439 · week_experience 1,410 ·
           indoor_alternative 785
  setting  UNKNOWN 9,592 · OUTDOOR 1,428 · INDOOR 774 · INDOOR_ALTERNATIVE 573
  age      SINGLE_AGE_PAGE 6,795 · MIXED_AGE_PAGE 4,306 · AGE_UNKNOWN 1,266
  week_position 보유 0  (원문에 주차 근거가 없다. 추정하지 않았다)

VALID:
  11,268  (91.1%)   → general_grounding_eligible 11,268
                    → outdoor_activity_eligible  1,335
                    → week_experience eligible   1,234

NEEDS_REVIEW:
  300  (2.4%)   절단 의심 · 40자 초과 outdoor · 꼬리말 · section 판정 불가

INVALID:
  799  (6.5%)   empty body · 3자 미만 · 한글 없음 · section label 메아리

Outdoor Loss:
  16% → 0.00%
  바깥놀이 행 286건 관찰 · 286건 복원 · 0건 손실
  분모는 줄 기반 baseline과 같은 어휘(바깥·실외 계열)로 셌고 253 → 286으로 늘었다.
  독립 교차 검증: 줄 기반 EMPTY_BODY 31개 파일 → 31개 전부 복원 (100%)

Indoor Alternative Leakage:
  0   (작업 중 38건 발견 → 3가지 원인 전부 수정)
  false outdoor classification 0

Fragment Regression:
  '건너기' 0 · '장화 신고 물웅덩이' 0 · '우리집에 왜 왔니?' 0 · '놀이를 해요.' 0
  복원형 '장화 신고 물웅덩이 건너기' 2건 존재
  잔여 false merge 1건 (초등학교 탐방) → NEEDS_REVIEW로 Grounding 제외

Age Classification:
  면(page) 단위 판정. 범위·열거·혼합 표기는 단일연령이 아니다.
  만3세 4,101 eligible / 28기관 (outdoor 463 / 19기관)
  만4세   908 eligible / 11기관 (outdoor  87 /  9기관)
  만5세 1,102 eligible / 21기관 (outdoor  89 / 14기관)

Artifact:
  version  institution-evidence-ingestion-v0.1.0
           schema institution-evidence.schema.v0
           normative_status CORPUS_OBSERVATION_NON_NORMATIVE (HUMAN_APPROVED 아님)
  path     data/evidence/institution_evidence_v0_1_0.json  (10,947,167 bytes)
  SHA      content_sha256 52b409557d3503422aa0109664298976bd7f831ed18304b818aaad936916e5ea
           (build metadata를 content에서 분리. 연속 2회 동일 확인)

Regression:
  1,644 passed → 1,766 passed, 4 deselected   (+122 신규 · 기존 실패 0)
  모든 테스트가 PDF 라이브러리 없이 돈다 (Port에 Fake Reader 주입)
  승인 Artifact 전부 불변 · Activity v0.2.2 미생성 · Rule v2 · LLM · Demo 무변경

OD-ACTIVITY-INGESTION-01:
  CLOSED
  (Activity v0.2.2 승격 범위는 별개 사안으로 OPEN 유지)

L2 Readiness:
  READY_FOR_EVIDENCE_RETRIEVAL
```

---

```text
MONTHLY_LLM_PLANNER_L1_COMPLETE
```
