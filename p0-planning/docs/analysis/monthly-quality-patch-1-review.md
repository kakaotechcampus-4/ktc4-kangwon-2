# Monthly Quality Patch 1 — Human Review

> Activity Extraction Repair + Display Quality Metadata + Selection Soft Penalty
>
> **v0.2.1은 `PENDING_HUMAN_REVIEW`다.** Production / Demo default는 v0.2.0 그대로다.
>
> 근거 표기: `[실측]` 직접 계산 · `[출처]` 원문 · `[판단]` 분석적 해석

재현:

```bash
python analysis/tools/cell_extract.py <pdf>              # 셀 인식 추출 (Root Fix)
python analysis/tools/scan_extraction_defects.py         # 전 Corpus 결함 탐색
python analysis/tools/build_v0_2_1_draft.py              # v0.2.1 Draft 생성
python analysis/experiments/monthly_vnext/before_after_patch1.py   # Before/After + Coverage
pytest tests/unit/test_cell_wrap_rejoin.py tests/unit/test_display_quality_penalty.py \
       tests/adapters/test_activity_v0_2_1_draft.py
```

---

## 1. Root Cause

### 1.1 파이프라인이 저장소에 없었다 `[실측]`

v0.2.0을 만든 추출 스크립트는 저장소에 없다. `src/`와 `analysis/` 어디에도
observation → normalization 파이프라인이 없고, `data/activities/`에는 결과 JSON만
있다. §3.1이 요구한 "Source → Extraction → … Root Cause 수정"을 **기존 코드를
고치는 방식으로는 할 수 없었다.**

따라서 **재현 가능한 추출 모듈을 새로 만들어 커밋하는 방식**으로 Root Fix를 했다.
최종 JSON에 `if label == "건너기"` 같은 Hotfix를 넣지 않았다.

```
analysis/tools/cell_extract.py            ← Root Fix. 규칙이 순수 함수로 분리됨
tests/unit/test_cell_wrap_rejoin.py       ← 28개 회귀 테스트
analysis/tools/scan_extraction_defects.py ← 같은 결함의 전 Corpus 탐색
```

### 1.2 결함 유형 2종 (원문 geometry로 확정) `[출처]`

**유형 1 — 셀 안 줄바꿈(wrap)을 Activity 구분자로 오판**

`references/samples/monthly/2026_민간_우리어린이집_만3-5세_월간보육계획안(7월).pdf`
p1, 행 밴드 y=[597.8, 645.5], 열 밴드 x=[207.2, 297.0]:

```
y=608.5  선캡 쓰고 공원
y=617.3  산책하기            ← wrap 이어짐
y=626.0  장화 신고 물웅덩이
y=636.5  건너기              ← wrap 이어짐
```

한 셀에 Activity 2개가 있고 **각각 두 줄로 감겨 있다.** 줄 단위 추출은 이것을
4개 Activity로 읽었다.

| source file | page | original table cell | extracted tokens | 현재 observation | 현재 canonical | root cause |
|---|---|---|---|---|---|---|
| 우리어린이집 2026-07 | 1 | col2 (x 207.2–297.0) | `선캡 쓰고 공원` / `산책하기` / `장화 신고 물웅덩이` / `건너기` | `건너기` | `건너기` | cell wrap |
| 키즈로스쿨 2026-07 | 1 | col4 (row 620–672) | 동일 | 동일 | 동일 | cell wrap |

**유형 2 — 괄선 없는 하위 열을 인식하지 못한 구두점 분절**

`2026_민간_서진어린이집_만3세,만4-5세_월간보육계획안(5월).pdf` p1,
행 밴드 y=[427.7, 485.2]. 이 행의 수직선은 `[17.0, 122.1, 578.0]` 3개뿐이라
좌/우 두 반이 **선 없이** 나뉘어 있다.

```
바깥놀이  우리집에 왜 왔니? 놀이를 해요.        내 몸을 꼭꼭 숨겨요.
          └─ x 199.3 ~ 299.4 ─┘   gap 24+   └─ 별개 셀 ─┘
```

`?`를 구분자로 본 결과 `우리집에 왜 왔니?`와 `놀이를 해요.`로 잘렸다.

| source file | page | original table cell | extracted tokens | root cause |
|---|---|---|---|---|
| 서진 2026-05 | 1 | row[428–485] col1 좌반 | `우리집에 왜 왔니?` / `놀이를 해요.` | 구두점 분절 + 하위 열 미인식 |

### 1.3 수정 규칙 — wrap과 list를 무엇으로 가르는가 `[판단]`

길이·들여쓰기를 쓰지 않았다. 이 Corpus의 표는 **가운데 정렬**이라 감긴 줄이
오히려 더 들여쓰여 보인다. 대신 **종결 형태**를 썼다.

```
종결      -기 / -요 -다 -까 -자 -래 / 명사(놀이·체험·한마당) / . ! ? …
비종결    연결어미·조사로 끝남 (-고 -며 -서 -으로 -을 -를 …)
          + 위 종결 목록에 없는 명사 말음
```

**bare `이`를 종결로 넣지 않았다.** `물웅덩이`·`무궁화꽃이`가 종결로 오판되면
wrap이 끊긴다(이전 Corpus 분석에서 확인된 실패). `놀이`만 예외다.

검증 `[실측]`:

| 입력 | 출력 | 판정 |
|---|---|---|
| `장화 신고 물웅덩이` / `건너기` | `장화 신고 물웅덩이 건너기` | 재결합 ✓ |
| `선캡 쓰고 공원` / `산책하기` / `장화…` / `건너기` | 2개 Activity | 재결합 ✓ |
| `투호놀이` / `줄다리기를 해요` / `동대문 놀이` | 3개 그대로 | **병합 안 함** ✓ |
| `무궁화 꽃이 피었습니다` / `장화…` / `건너기` / `강강술래` | 3개 | 혼합 ✓ |

---

## 2. Source-confirmed Corrections

### 2.1 전 Corpus 탐색 `[실측]`

Monthly 111개 중 **표 선이 있어 셀 복원이 가능한 100개**를 스캔했다.

판정 기준은 문자열 포함이 아니라 **완전 분해**다 — 복원된 문자열이 기존 Catalog
항목 2개 **이상으로 빈틈없이 나뉠 때만** 결함으로 본다. 세로 나열은 각 항목이
이미 Catalog에 통째로 있으므로 원리적으로 걸리지 않는다.

```
SOURCE_CONFIRMED_DEFECT : 2건 (고유)
LIKELY_DEFECT           : 0건
AMBIGUOUS               : 2건 (자연물 물감 / 가을담기 — AUTO_CANDIDATE로 남김)
VALID                   : 나머지
```

**v0.2.1에는 `SOURCE_CONFIRMED_DEFECT` 2건만 반영했다.**

### 2.2 지시서 Case B에 대한 정정 `[실측]`

§4 Case B(`자연물로 여름 디저트 만들기`)는 **실제 결함이 아니었다.**

```
v0.2.0에 '자연물로 여름 디저트 만들기'  → 존재 O  (통째로 정상 등재)
v0.2.0에 '자연물로 여름 디저트'          → 존재 X
v0.2.0에 '만들기'                      → 존재 X
```

설계 분석이 `-layout` 텍스트의 줄 모양만 보고 분리를 추정했으나, Catalog를 직접
대조하니 정상이었다. **수정하지 않았고 테스트로 고정했다**
(`test_false_positive_case_b_was_not_touched`).

같은 이유로 첫 스캔에서 `무궁화 꽃이 피었습니다 모래사막을 구성해요`가 오탐으로
잡혔다. 원인은 하위 열 간격 임계값 계산 오류(단어 폭을 첫 단어 길이로 나눔)였고,
**평균 글자 폭 기반으로 고친 뒤 사라졌다** `[실측]`.

---

## 3. Activity IDs Removed / Added / Changed

### Removed (fragment, 4건)

| label | activity_id | 사유 |
|---|---|---|
| `장화 신고 물웅덩이` | `act_outdoor_v2_…` | wrap 절편 |
| `건너기` | `act_outdoor_v2_4a8be58a2a` | wrap 절편 |
| `우리집에 왜 왔니?` | `act_outdoor_v2_…` | 구두점 분절 절편 |
| `놀이를 해요.` | `act_outdoor_v2_4bc63e9e39` | 구두점 분절 절편 |

### Added (corrected, 2건)

| label | activity_id | supersedes |
|---|---|---|
| `장화 신고 물웅덩이 건너기` | `act_outdoor_v021_f13eaab140` | 위 2건 |
| `우리집에 왜 왔니? 놀이를 해요.` | `act_outdoor_v021_d07f82337a` | 위 2건 |

새 id를 부여한 이유 `[판단]`: label과 evidence 집합이 달라졌으므로 기존 id를
재사용하면 v0.2.0으로 생성된 Plan의 `source_id`와 의미가 충돌한다. 기존 id는
`supersedes_activity_ids`로 추적된다. **정상 Activity 194개는 id를 그대로 유지했다.**

```
196 = 198 − 4(제거) + 2(복원)
```

---

## 4. Evidence Movement `[실측]`

Evidence lineage는 손실 없이 이동했다. 테스트로 고정했다
(`test_evidence_lineage_moved_without_loss`).

```
장화 신고 물웅덩이 건너기
  ← 장화 신고 물웅덩이 (evidence 1)
  ← 건너기             (evidence 1)
  = evidence 2건, (origin_id, page, observed_label) 집합 동일

우리집에 왜 왔니? 놀이를 해요.
  ← 우리집에 왜 왔니?   (evidence 1)
  ← 놀이를 해요.        (evidence 1)
  = evidence 2건, 집합 동일
```

파생 값은 추측하지 않고 evidence에서 다시 뽑았다 — `applicable_months`는 관찰 월
집합, `supported_ages`는 원래 지원 연령 ∩ evidence `age_scope`. 원래 label은
`aliases`로 보존했다.

---

## 5. Display Quality Metadata

### 5.1 분포 `[실측]`

| display_quality | review_status | 건수 |
|---|---|---:|
| GOOD_STANDALONE | UNREVIEWED | 179 |
| GOOD_STANDALONE | **HUMAN_CONFIRMED** | 7 |
| INSTITUTION_SPECIFIC | AUTO_CANDIDATE | 6 |
| POSSIBLE_FRAGMENT | AUTO_CANDIDATE | 2 |
| **TOO_GENERIC** | **HUMAN_CONFIRMED** | **1** |
| NEEDS_HUMAN_REVIEW | AUTO_CANDIDATE | 1 |

**Selection에 영향을 주는 항목은 `전통놀이` 하나뿐이다.**

### 5.2 HUMAN_CONFIRMED 8건 — 전부 원문 대조로 검증 `[출처]`

| label | quality | 원문 근거 |
|---|---|---|
| `전통놀이` | **TOO_GENERIC** | 4개 기관 원문이 모두 범주어다: `전통놀이 종류, 방법을 알아보고` / `전통 놀이를 경험해 본다` / `<추석> 명절 전통놀이(대체활동-전통놀이)` / `우리나라의 전통놀이를 알고 경험한다` |
| `모래놀이` | GOOD_STANDALONE | `- 조물조물 모래놀이를 해요` |
| `투호놀이` | GOOD_STANDALONE | `♥바깥놀이-투호놀이` |
| `대문놀이` | GOOD_STANDALONE | `대문놀이를 해요` |
| `물길 놀이` | GOOD_STANDALONE | 나열 목록 `모래놀이, 물길 놀이, 줄넘기 …` |
| `줄넘기` | GOOD_STANDALONE | 나열 목록 `롤러장 나들이, 줄넘기` |
| `장화 신고 물웅덩이 건너기` | GOOD_STANDALONE | 복원 결과 (§1.2) |
| `우리집에 왜 왔니? 놀이를 해요.` | GOOD_STANDALONE | 복원 결과 (§1.2) |

`[판단]` **설계 분석의 `SECTION_LABEL_LIKE` 후보 6건 중 5건이 오탐이었다.**
`투호놀이`·`대문놀이`·`모래놀이`·`물길 놀이`·`팽이 놀이`는 자동 분류기가
`…놀이` 접미사만 보고 찍은 것이고, 원문 확인 결과 구체 놀이명이거나 목록 항목이다.
이것이 §11의 안전장치(HUMAN_CONFIRMED만 penalty)가 필요한 이유의 실물이다.

### 5.3 AUTO_CANDIDATE 9건 — Selection 중립

```
INSTITUTION_SPECIFIC : 전통 놀이 한마당 / 숲속 동물 보호소 / 비온 뒤 놀이터 탐험 /
                       놀이터를 탐색하며 놀이해요 / 바깥 놀이터 사진을 찍어요 /
                       바깥 놀이터에서 지켜야 할 약속을 정해요
POSSIBLE_FRAGMENT    : 자연물 물감 / 가을담기      ← wrap 여부 미확정 (AMBIGUOUS)
NEEDS_HUMAN_REVIEW   : 팽이 놀이                  ← 원문이 '<실내놀이>' 맥락
```

---

## 6. Selection Rule Change

### 6.1 §7 `전통놀이` Normalization 판정 → **`TOO_GENERIC_BUT_VALID`** `[출처]`

원문 6개 표현을 추적했다.

```
♥바깥놀이 -전통놀이를 해요    (아이사랑 9월)
-전통놀이                   (괴산하나 9월)
<추석>명절전통놀이           (큰빛 9월)
-전통놀이체험               (해찬솔 9월)
전통놀이를 해요             (서진 2025-10)
전통놀이 한마당을 열어요.     (서진 2026-09)
```

- `MULTIPLE_DISTINCT_ACTIVITIES_COLLAPSED`가 **아니다** — 서로 다른 구체 놀이명이
  합쳐진 것이 아니다. 원문 문맥이 모두 `종류`, `경험해 본다`처럼 **범주**를 가리킨다.
- `OVER_NORMALIZED_CATEGORY`도 아니다 — 범주어를 만들어 낸 것이 아니라 **원문 자체가
  범주어**다.
- 따라서 **자동 Split하지 않았다**(§7 지시 준수). `display_quality = TOO_GENERIC`
  + Soft Penalty로 처리한다.

`[판단]` 다만 `sample.monthly.geumsan.2026.09` evidence의 `observed_label`이
`태극기 들고 달리기 전통놀이 전통놀이 한마당/ 군인처럼 장애물 움직이기`로, 다중
Activity 셀이 부분 문자열 매칭된 흔적이다. 확정할 수 없어 **수정하지 않고 Human
Review 항목으로 남긴다.**

### 6.2 Ranking tuple 변경

```
v1                                    v2
① same-month repeat penalty      →   ① same-month repeat penalty
② parent theme mismatch          →   ② parent theme mismatch
                                      ③ display quality penalty   ← 신규
③ curriculum repeat              →   ④ curriculum repeat
④ -monthly evidence strength     →   ⑤ -monthly evidence strength
⑤ stable activity_id             →   ⑥ stable activity_id
```

**위치 근거** `[판단]`: 지시서 추천 위치(theme 뒤 / curriculum 앞)와 일치한다.
theme은 상위 Plan이 내려준 의미 제약이라 표시 품질보다 우선해야 하고, curriculum과
evidence 개수는 표시 품질보다 약한 선호다.

**Binary penalty만 쓴다.** 품질 유형별 가중치(`TOO_SHORT=3` 등)는 유형 간 상대
심각도의 근거가 없어 도입하지 않았다.

### 6.3 Hard Exclusion 아님 `[실측]`

모든 후보가 품질 문제여도 후보 집합이 줄지 않는다
(`test_quality_issue_is_never_a_hard_exclusion`). 후보가 1개면 그것이 선택된다.

### 6.4 Rule Version → `v1` → **`v2`**

Ranking tuple이 실제로 바뀌었으므로 올렸다. `RULE_ID`는 유지한다.
정수 증분은 `yearly_theme_selection`(이미 `v2`)의 기존 관례를 따랐다 — 프로젝트에
`v1.1` 형태를 쓰는 Rule이 없다.

**legacy 호환** `[실측]`: v0.2.0에는 `display_quality` 필드가 없어 penalty가 항상
0이다. 따라서 **v2 Rule로 v0.2.0을 돌려도 v1과 동일한 순서가 나온다.**

---

## 7. Before / After

BEFORE = v0.2.0 + Ranking v2 / AFTER = v0.2.1 Draft(시뮬레이션 승인 사본) + Ranking v2

### 7.1 2026-07 / 만3세 — 기존 문제 사례

```
BEFORE                              AFTER
W1 우리 동네 분수대 가 보기          W1 장화 신고 물웅덩이 건너기
W2 셀로판지로 여름 하늘 바라보기      W2 우리 동네 분수대 가 보기
W3 건너기                    ←결함  W3 셀로판지로 여름 하늘 바라보기
W4 산책하며 여름 곤충 찾기           W4 산책하며 여름 곤충 찾기
W5 무인 아이스크림 매장 찾아가기      W5 무인 아이스크림 매장 찾아가기
```

| 항목 | W1 |
|---|---|
| previous activity_id | `act_outdoor_v2_30ad6621c8` |
| new activity_id | `act_outdoor_v021_f13eaab140` |
| previous value | 우리 동네 분수대 가 보기 |
| new value | 장화 신고 물웅덩이 건너기 |
| change reason | `MATCHED_PARENT_THEME` |
| quality penalty | 0 → 0 |
| evidence count(월) | 1 → 2 (절편 2개가 합쳐져 evidence가 모였다) |
| theme match | True → True |

**`건너기`가 사라졌고 원문 Activity가 들어왔다.**

### 7.2 2026-05 / 만3세

```
BEFORE                                   AFTER
W1 산책하며 내가 좋아하는 색깔 자연물 찾기   W1 우리집에 왜 왔니? 놀이를 해요.
W2 돌멩이에 얼굴 표정 그리기               W2 산책하며 내가 좋아하는 색깔 자연물 찾기
W3 바람개비 들고 시원하게 달리기            W3 돌멩이에 얼굴 표정 그리기
W4 놀이를 해요.                    ←결함   W4 바람개비 들고 시원하게 달리기
```

### 7.3 2026-09 / 만5세 — display quality penalty의 실제 효과

```
BEFORE                     AFTER
W1 무궁화 꽃이 피었습니다    W1 무궁화 꽃이 피었습니다
W2 전통놀이          ←범주  W2 강강술래
W3 강강술래                W3 가을 나들이
W4 가을 나들이             W4 사방치기
W5 사방치기                W5 동대문 놀이
```

| 항목 | W2 |
|---|---|
| previous activity_id | `act_outdoor_traditional_play` |
| new activity_id | `act_outdoor_ganggangsullae` |
| previous value | 전통놀이 (evidence 10, 6기관) |
| new value | 강강술래 (evidence 7, 4기관) |
| change reason | `AVOIDED_REPEAT_IN_MONTH` |
| quality penalty | 0 → 0 (선택된 후보는 penalty 없음) |
| evidence count(월) | 10 → 7 |

`[판단]` **evidence가 가장 강한 항목이 범주어라서 상위에 오던 문제가 해소된다.**
trace의 `reason`이 `AVOIDED_CONFIRMED_DISPLAY_QUALITY_ISSUE`가 아니라
`AVOIDED_REPEAT_IN_MONTH`인 것은, 반복 회피 축이 품질 축보다 앞서 분류되기
때문이다. 선택 결과는 품질 축이 만든 것이 맞다.

### 7.4 변경 없음

`2026-03/만4세`, `2027-02/만5세`는 전혀 변하지 않았다 — 해당 후보 집합에
correction 대상도 확정 품질 문제도 없다.

**총 변경 Cell : 12개 Case 중 3개 Case, 10 Cell** `[실측]`

---

## 8. Candidate Coverage `[실측]`

12개월 × 6개 연령 조합 = 72칸 전수.

| 월 | 만3 | 만4 | 만5 | 3/4 | 3/5 | 4/5 |
|---|---|---|---|---|---|---|
| 3월 | 15→15 | 8→8 | 11→11 | 8→8 | 7→7 | 7→7 |
| 4월 | 16→16 | 9→9 | 9→9 | 9→9 | 9→9 | 9→9 |
| 5월 | **12→11** | 8→8 | 8→8 | 8→8 | 8→8 | 8→8 |
| 6월 | 13→13 | 7→7 | 7→7 | 7→7 | 7→7 | 7→7 |
| 7월 | **16→15** | **9→8** | **9→8** | **9→8** | **9→8** | **9→8** |
| 8월 | 12→12 | 7→7 | 7→7 | 7→7 | 7→7 | 7→7 |
| 9월 | 37→37 | 31→31 | 27→27 | 22→22 | 15→15 | 20→20 |
| 10월 | 15→15 | 8→8 | 8→8 | 8→8 | 8→8 | 8→8 |
| 11월 | 11→11 | 4→4 | 4→4 | 4→4 | 4→4 | 4→4 |
| 12월 | 17→17 | 7→7 | 7→7 | 7→7 | 7→7 | 7→7 |
| 1월 | 14→14 | 8→8 | 8→8 | 8→8 | 8→8 | 8→8 |
| 2월 | 11→11 | 4→4 | 4→4 | 4→4 | 4→4 | 4→4 |

- 감소는 **병합된 2쌍 때문에 각 −1**뿐이다 (5월 만3세, 7월 전 조합).
- **새로 후보 0이 된 (월, 연령) 조합 없음.**
- BEFORE에서 0이던 조합도 없다.
- 임의 fallback을 추가하지 않았다.

---

## 9. Regression Results `[실측]`

```
기준선 : 1381 passed, 4 deselected
현재   : 1520 passed, 4 deselected     (+139, 기존 실패 0)
```

신규 테스트

| 파일 | 건수 | 범위 |
|---|---:|---|
| `tests/unit/test_cell_wrap_rejoin.py` | 28 | 종결 판정 / wrap 재결합 / list 비병합 / 구두점 보존 / 하위 열 분리 |
| `tests/unit/test_display_quality_penalty.py` | 13 | HUMAN_CONFIRMED만 penalty / Hard Exclusion 아님 / 기존 축 의미 보존 / tie-break |
| `tests/adapters/test_activity_v0_2_1_draft.py` | 98 | v0.2.0 불변 / strict schema / lineage 이동 / metadata / Coverage 72칸 |

갱신한 기존 테스트 3건 (의도된 계약 변경)

| 테스트 | 변경 | 사유 |
|---|---|---|
| `test_rule_identity_follows_existing_convention` | `v1` → `v2` | Ranking tuple 변경 |
| `test_trace_field_count_stays_small` | `≤18` → `≤19` | `display_quality_penalty` 추가 |
| `test_activity_allowlist_exactly_covers_the_artifact` | 이름·의미 조정 | v0.2.1 전용 correction 필드를 forward-looking 항목으로 명시 분리 |

Monthly 기존 Contract 회귀 `[실측]` — 전부 유지

```
Generate candidate 0      → EMPTY_VALID, save 성공
Regenerate candidate 0    → BLOCKED, 기존 값 보존, save 0
CONFIRMED                 → Edit / Regenerate 차단
Activity Catalog pinning  → exact catalog/version, default fallback 없음
Monthly LLM 호출          → 0
```

v0.2.1을 실제 `GenerateMonthlyPlan`에 명시 주입한 결과 `[실측]`:

```
plan lineage : ActivityCatalogLineage(… 'activity-reference-v0.2.1')
LLM 호출     : 0
rule         : monthly.activity.reference_candidate_selection v2
2026-09 W1~W5 전부 FILLED, '전통놀이' 미선택
```

---

## 10. v0.2.1 Draft SHA

```
path    : data/activities/activity_reference_v0_2_1_draft.json
version : activity-reference-v0.2.1
status  : PENDING_HUMAN_REVIEW
items   : 196
size    : 480,792 bytes
sha256  : a64af4331cd850031fbb99f8ae3f283e609b3623da68b8ea118afb94e92faa63
base    : activity-reference-v0.2.0
          e27ebca3342a84327c6624c5ba258b9bc98aef37ba5362b61f283c47ece0bde6
```

**Freeze 검증** `[실측]` — 승인 Artifact 전부 불변

```
OK  data/themes/theme_reference_v0.json         c12999fa…
OK  data/activities/activity_reference_v0_2.json e27ebca3…
OK  data/templates/monthly_template_a.json       1f35322d…
OK  data/rules/safety_education_legal_v1.json    5831809b…
OK  data/activities/activity_reference_v0.json   b565254f…
OK  data/activities/activity_reference_v0_2_draft.json c9c0e9da…
OK  tests/golden/monthly_cases.json              c6056412…
OK  tests/golden/yearly_cases.json               7918e9f9…
OK  CLAUDE.md                                    a723a7ee…
OK  demo-planning/                               변경 0건
```

`src/` 변경은 의도한 5개 파일뿐이며 줄바꿈 형식도 보존했다.

```
domain/activity_reference.py            LF   Enum 2개 + Optional 필드 2개 + property 1개
adapters/activity_reference_schema.py   LF   Optional 필드 2개 + validator 2개
adapters/activity_reference_projection.py LF correction 필드 4개를 review-only로
rules/monthly_activity_selection.py     LF   penalty 함수 + sort key + version v2
application/monthly_dto.py              CRLF trace 필드 1개
```

전부 **Additive**다. BREAKING_CHANGE 없음.

---

## 11. Human Approval Checklist

```
ACTIVITY_REFERENCE_V0_2_1_DRAFT

Version:
  activity-reference-v0.2.1
Item Count:
  196   (v0.2.0 198 − 4 fragment + 2 restored)
SHA-256:
  a64af4331cd850031fbb99f8ae3f283e609b3623da68b8ea118afb94e92faa63

Source-confirmed extraction corrections:
- 장화 신고 물웅덩이 + 건너기 → 장화 신고 물웅덩이 건너기
    cell wrap. 우리어린이집 2026-07 p1 row[598-646] col2 (키즈로스쿨 7월 동일)
- 우리집에 왜 왔니? + 놀이를 해요. → 우리집에 왜 왔니? 놀이를 해요.
    괄선 없는 하위 열 + 구두점 분절. 서진 2026-05 p1 row[428-485] col1

Normalization corrections:
- 없음. '전통놀이'는 TOO_GENERIC_BUT_VALID로 판정해 Split하지 않았다.
  원문 자체가 범주어이며 구체 놀이명이 합쳐진 증거가 없다.

Removed fragment activities:
- 건너기
- 장화 신고 물웅덩이
- 우리집에 왜 왔니?
- 놀이를 해요.

New corrected activities:
- 장화 신고 물웅덩이 건너기        (act_outdoor_v021_f13eaab140, evidence 2)
- 우리집에 왜 왔니? 놀이를 해요.    (act_outdoor_v021_d07f82337a, evidence 2)

HUMAN_CONFIRMED quality flags:
- 전통놀이                       TOO_GENERIC        ← 유일한 penalty 대상
- 모래놀이 / 투호놀이 / 대문놀이 / 물길 놀이 / 줄넘기   GOOD_STANDALONE (오탐 확인)
- 장화 신고 물웅덩이 건너기 / 우리집에 왜 왔니? 놀이를 해요.  GOOD_STANDALONE (복원분)

AUTO_CANDIDATE quality flags:   ← Selection 중립. 승인 전까지 영향 없음
- INSTITUTION_SPECIFIC : 전통 놀이 한마당 / 숲속 동물 보호소 / 비온 뒤 놀이터 탐험 /
                         놀이터를 탐색하며 놀이해요 / 바깥 놀이터 사진을 찍어요 /
                         바깥 놀이터에서 지켜야 할 약속을 정해요
- POSSIBLE_FRAGMENT    : 자연물 물감 / 가을담기   (wrap 여부 미확정, AMBIGUOUS)
- NEEDS_HUMAN_REVIEW   : 팽이 놀이                (원문이 <실내놀이> 맥락)

Selection Rule version:
- monthly.activity.reference_candidate_selection  v1 → v2
  display quality 축이 theme 뒤 / curriculum 앞에 추가됨. Binary penalty.
  legacy v0.2.0에서는 penalty가 항상 0이라 v1과 동일한 순서가 나온다.

Production default:
  STILL v0.2.0

Demo default:
  STILL v0.2.0


APPROVAL REQUIRED FOR:

1. v0.2.1 HUMAN_APPROVED 승격
2. Production default v0.2.1 전환
3. Demo default v0.2.1 전환


검토 시 특히 봐 주실 것:

a. '전통놀이'를 TOO_GENERIC으로 두는 것이 맞는지. 대안은 Catalog에서 제외하는
   것인데, 원문 4개 기관이 실제로 그렇게 적었으므로 제외는 Source와 충돌한다.
b. AMBIGUOUS 2건(자연물 물감 / 가을담기)의 wrap 여부. 원문만으로는 한 셀인지
   두 셀인지 확정되지 않아 손대지 않았다.
c. '팽이 놀이'가 실내 맥락에서 추출된 것으로 보인다. setting 정정이 필요한지.
d. UNREVIEWED 179건은 자동으로 GOOD_STANDALONE을 부여했을 뿐 검토된 것이 아니다.
```

---

## 부록. 알려진 한계 `[판단]`

1. 셀 복원은 **표 선이 있는 PDF에서만** 동작한다. Monthly 111개 중 100개가 대상이고
   나머지 11개(image-only 포함)는 스캔되지 않았다.
2. `analysis/tools/cell_extract.py`는 **분석 도구**다. v0.2.0을 만든 원래 파이프라인을
   대체한 것이지 Production 경로에 연결되어 있지 않다.
3. 자동 결함 탐색은 "기존 Catalog 항목으로의 완전 분해"를 요구하므로, **한쪽 절편만
   Catalog에 있는 경우는 잡지 못한다.** 그런 사례가 남아 있을 수 있다.
4. `display_quality`의 UNREVIEWED 179건은 미검토 상태이며 품질 판정이 아니다.
5. Rule v2의 `AVOIDED_CONFIRMED_DISPLAY_QUALITY_ISSUE` reason은 반복 회피가 먼저
   분류되면 나타나지 않는다. 선택 결과는 정확하지만 trace의 설명력이 그만큼 낮다.
