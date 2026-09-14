# Full Corpus 재분석 — 대구 신규 자료 포함 (2026-09-12)

> **분석 전용 문서다.** Production / Reference / Golden / Rule을 바꾸지 않았다.
> 여기의 Recommendation은 제안일 뿐이며 이번 작업에서 구현하지 않았다.
>
> 근거 표기: `[실측]` 본 분석에서 직접 계산한 수치 · `[출처]` 문서 원문 사실 ·
> `[판단]` 분석적 해석

**재현 방법**

```bash
python analysis/tools/extract_corpus.py     # 텍스트 추출 + 1차 inventory
python analysis/tools/reclassify.py         # 본문 기준 재분류 (분류기 v2)
python analysis/tools/report_inventory.py   # A
python analysis/tools/report_duplicates.py  # B
python analysis/tools/report_yearly.py      # C
python analysis/tools/report_monthly.py     # D, E
python analysis/tools/report_activity.py    # F, G 일부
```

중간 산출물은 `analysis/tmp/`에만 쓴다. `data/`에는 아무것도 넣지 않았다.

---

## A. Corpus Inventory

### A-1. 전체 규모와 Delta `[실측]`

| 항목 | 기존 | 신규(대구) | 전체 |
|---|---:|---:|---:|
| 전체 PDF | 129 | 46 | **175** |
| YEARLY_PLAN | 49 | 6 | 55 |
| MONTHLY_PLAN | 59 | 40 | 99 |
| WEEKLY_PLAN | 2 | 0 | 2 |
| UNKNOWN | 19 | 0 | 19 |
| └ 판독 가능 UNKNOWN | 2 | 0 | 2 |
| 판독 가능 (text layer 有) | 111 | 46 | 157 |
| image-only / OCR 필요 | 18 | 0 | 18 |
| 기관 수 | 49 | 4 | **53** |

신규 46건은 전부 판독 가능하다. image-only 18건은 전부 기존 자료다.

신규 기관 4곳 `[실측]`: 청운어린이집(13) · 혜솔어린이집(21) · 키즈로스쿨어린이집(10) ·
영재팡팡어린이집(2). 기존 기관에 추가된 파일은 없다 — 신규 46건은 **전부 새 기관**이다.

설립유형 Delta `[실측]`: 신규는 `가정` 33건 + `법인단체` 13건이다. 기존 Corpus에
`가정` 어린이집은 1건뿐이었으므로 **가정 어린이집 표본이 1 → 34로 늘었다.**

### A-2. 문서유형 분류 방법과 수정 이력 `[판단]`

1차 분류기는 표제어를 `월간보육계획안` 계열로만 봐서 112건이 UNKNOWN이었다.
실제 Corpus의 표제는 다양하다 `[출처]`.

```
5세 5월 교육계획안                      (영재팡팡)
솔잎향기반 10월 교육계획안                (키즈로스쿨)
2025년 10월 햇살반 놀이계획안 (3~5세)     (혜솔)
10월 놀이 안내                          (서진)
주 간 보 육 계 획 안                     (서충주 — 자간 분리)
2026년 만5세 연간 , 기본 , 생활안전 계획안  (is뽈리나 — 중간 삽입어)
```

분류기 v2는 (a) 표제 어휘를 `보육|교육|놀이|운영 + 계획`으로 넓히고, (b) 공백을
제거한 사본으로 자간 분리·삽입어 표제를 재시도한다. 결과 UNKNOWN이
112 → 19건(그중 17건은 image-only)으로 줄었다 `[실측]`.

남은 판독 가능 UNKNOWN 2건은 본문에 scope 표제가 아예 없다. 본문 **내용**으로는
확정 가능하다 `[출처]`.

| 파일 | 본문 근거 | 판정 |
|---|---|---|
| `2026_직장_금산군청직장어린이집_만3-5세_9월_월간계획안.pdf` | `9월 1주`~`9월 5주` 주차 축, 월 단위 목표 | MONTHLY_PLAN |
| `2026_직장_강원특별자치도청어린이집_만3,4,5세_연간보육계획안.pdf` | 계절 전체(봄/여름/가을/겨울) + 12개월 주제 개념망 | YEARLY_PLAN |

강원도청 자료는 **표 격자가 아니라 마인드맵형** 연간계획이다 `[출처]`. 기존 분석의
"구조 변이" 목록에 없던 형태이며, 월→주제 격자를 전제한 파서로는 추출되지 않는다.

### A-3. 연령 `[실측]`

본문에 연령 표기가 있는 파일 기준(중복 포함):

| 연령 | 전체 | 신규 |
|---|---:|---:|
| 만 0세 | 1 | 0 |
| 만 1세 | 2 | 1 |
| 만 2세 | 2 | 1 |
| 만 3세 | 64 | 15 |
| 만 4세 | 38 | 2 |
| 만 5세 | 37 | 2 |

**신규 자료는 만3세에 집중된다.** 만4·5세 표기는 각각 2건만 늘었다. 신규 40건의
Monthly 중 다수가 `3~5세` 혼합 표기이거나 만3세 단일이다.

본문에 `혼합` 단어가 명시된 파일은 16건, **신규는 0건**이다 `[실측]`.

### A-4. Multi-page / Multi-age PDF `[실측]`

페이지마다 연령 표기가 다른 PDF가 **22건**이다. PDF 전체를 한 연령으로 보면 안 된다.

| 파일 | 페이지별 연령 |
|---|---|
| `2025_법인단체_만3세_청운어린이집_월간보육계획안(9월).pdf` | p1 만1세 · p2 만2세 · **p3 만3세** |
| `2026_국공립_시립새봄어린이집_만3-5세_월간계획안.pdf` | 만3 · 만3 · 만4 · 만5 |
| `2026_국공립_공립바른어린이집_만3,4,5세_연간보육계획안.pdf` | 만3 · 만4 · 만5 |
| `2026_민간_is뽈리나어린이집_만3,4,5세_연간교육계획안.pdf` | 만5 · 만4 · 만3 |
| 서진어린이집 월간 9건 | p1 만3 · p2 만4·5 |

**중요** `[판단]`: 위 문서들은 만3/만4/만5가 **각각 별도 페이지**로 존재하는 것이며
`mixed age class`가 아니다. 실제 혼합반 표기(`만4.5세 혼합반` 등)가 있을 때만
mixed-age evidence로 취급해야 한다. 신규 청운 9월 자료는 **만1·2세 페이지를 포함**하므로
파일명(`만3세`)만 보고 만3세 자료로 다루면 Target 밖 연령이 섞인다.

### A-5. Filename ↔ Body Mismatch `[실측]`

- 파일명 연령이 본문 연령의 부분집합이 아닌 경우가 존재한다. 가장 뚜렷한 예:
  `2025_법인단체_만3세_청운어린이집_월간보육계획안(9월).pdf` — 파일명 `만3세`,
  본문 `만1·2·3세`(3개 페이지).
- 파일명 오타: `2026_가정_혜솔어린이집_만3-5세_**원간**보육계획안(8월/9월).pdf`
  — 본문은 정상 월간 계획이다 `[출처]`.
- 파일명 표기 흔들림: 키즈로스쿨은 같은 기관인데 `만3-5세`와 `3-5세`가 섞여 있다.

**규칙 확인**: 본문이 Truth다. 위 mismatch는 본문 값으로 집계했다.

### A-6. 부록 / 별첨 `[실측]`

부록 marker(동요·동시·속담·가정통신문·식단표 등)가 검출된 파일은 **69건**
(신규 30건)이다. 계획안 본문과 분리해야 하며, 본 분석의 Activity 추출은
`바깥놀이` 행 label로 시작하는 줄만 읽으므로 부록 텍스트를 Activity evidence로
쓰지 않는다 `[판단]`.

### A-7. 월 Coverage `[실측]`

| 월 | 기존 | 신규 | 전체 |
|---|---:|---:|---:|
| 3월 | 5 | 3 | 8 |
| 4월 | 4 | 4 | 8 |
| 5월 | 4 | 6 | 10 |
| 6월 | 4 | 4 | 8 |
| 7월 | 4 | 4 | 8 |
| 8월 | 4 | 3 | 7 |
| 9월 | 15 | 4 | 19 |
| 10월 | 3 | 3 | 6 |
| 11월 | 4 | 2 | 6 |
| 12월 | 4 | 2 | 6 |
| 1월 | 5 | 2 | 7 |
| 2월 | 3 | 3 | 6 |

12/12 coverage는 기존에도 충족되어 있었고 신규가 **비9월 월의 두께를 고르게 보강**했다.
9월 편중(19건)은 여전하다.

### A-8. 기관 × 월 Coverage `[실측]`

Monthly를 보유한 기관은 18곳이다. 12개월 전부를 가진 기관은 **4곳**
(청운 · 혜솔 · 키즈로스쿨 · 우리어린이집)이고, 이 중 **3곳이 신규 대구 자료**다.
나머지 14곳은 1~9개월만 보유한다.

---

## B. Source Independence / Template Family

### B-1. Exact Duplicate `[실측]`

고유 SHA-256 175개 / 파일 175개. **exact duplicate 0건.** 같은 파일이 다른 이름으로
들어온 사례는 없다.

### B-2. Normalized Near-Duplicate `[실측]`

연도·기관명·반이름·숫자를 제거한 본문에 6-gram Jaccard를 적용했다(판독 가능 157건).
임계 0.45 이상 쌍은 11개다.

| Jaccard | 등급 | 문서 A | 문서 B |
|---:|---|---|---|
| 0.848 | POSSIBLE_TEMPLATE_FAMILY | 키즈로스쿨 2025 연간 | 우리어린이집 2025 연간 |
| 0.807 | POSSIBLE_TEMPLATE_FAMILY | 우리어린이집 2025 연간 | 키즈로스쿨 2026 연간 |
| 0.775 | POSSIBLE_TEMPLATE_FAMILY | 키즈로스쿨 2026 월간(6월) | 우리어린이집 2026 월간(6월) |
| 0.769 | POSSIBLE_TEMPLATE_FAMILY | 키즈로스쿨 2025 월간(2월) | 우리어린이집 2025 월간(2월) |
| 0.643 | HIGH_SIMILARITY_CROSS_INSTITUTION | 키즈로스쿨 2026 월간(7월) | 우리어린이집 2026 월간(7월) |
| 0.536 | HIGH_SIMILARITY_CROSS_INSTITUTION | 혜솔 2025 연간 | 키즈로스쿨 2026 연간 |
| 0.489 | HIGH_SIMILARITY_CROSS_INSTITUTION | 키즈로스쿨 2025 연간 | 혜솔 2025 연간 |
| 0.471 | HIGH_SIMILARITY_CROSS_INSTITUTION | 마성 2026 연간 | 우리어린이집 2026 연간 |
| 0.450 | HIGH_SIMILARITY_CROSS_INSTITUTION | 혜솔 2025 연간 | 우리어린이집 2025 연간 |

같은 기관 연도 간 반복 2쌍은 `HIGH_SIMILARITY_SAME_INSTITUTION`이다.

원문 대조 `[출처]`: 혜솔 10월과 키즈로스쿨 10월은 놀이주제(`청명한 가을`)와 목표
문장이 **문자 단위로 동일**하다.

```
키즈로스쿨 10월: 놀이주제 '청명한 가을'  기간 2025년 9월 29일 ~ 2025년 11월 1일
혜솔      10월: 주제     '청명한 가을'  기간 2025년 9월 29일 ~ 2025년 11
목표: ⋅추석에 할 수 있는 다양한 것에 관심을 가진다.   (양쪽 동일)
      ⋅가을이 되어 달라진 주변 모습과 날씨를 느껴본다. (양쪽 동일)
```

### B-3. Template Family 후보 `[실측]` / `[판단]`

기관 간 고유사 연결의 연결 성분은 1개다.

```
POSSIBLE_TEMPLATE_FAMILY #1 = {마성어린이집, 우리어린이집, 키즈로스쿨어린이집, 혜솔어린이집}
```

이 중 **키즈로스쿨·혜솔이 신규 대구 자료**이고, 우리·마성은 기존 자료다.

| 축 | 값 |
|---|---:|
| observed institution count | **53** |
| possible independent source/template-family count (보수적) | **50** |

= 연결 없는 기관 49곳 + 군집 1개.

**해석 주의** `[판단]`: `institution_count = 2`를 곧바로 `independent evidence = 2`로
읽으면 안 된다. 위 4곳에서 같은 표현이 2~4회 관찰되어도 독립 관측이 1회일 수 있다.
다만 유사도만으로 동일 Source를 **확정하지 않는다** — 등급은 `POSSIBLE_TEMPLATE_FAMILY`
까지다. 공통 상용 커리큘럼 패키지 사용 가능성은 기존 분석에서도 지적된 바 있고
(예담 ↔ 금빛자이 12개월 문자 동일), 이번에 대구 자료로 **같은 현상이 재확인**되었다.

---

## C. Yearly 재분석

### C-1. 대상 `[실측]`

YEARLY_PLAN 55건(신규 6) · 판독 가능 54건 · 기관 45곳.

### C-2. 추출 방법과 보정 이력 `[판단]`

1차 추출은 줄 **시작**의 `N월` 토큰만 읽어 9~2월 관찰 수가 급감했다(9월 9건 vs 3월 29건).
원인은 기존 분석에서도 확인된 **반쪽표 좌우 병렬 레이아웃**(3~8월 왼쪽 / 9~2월 오른쪽)이다.
한 줄 안의 모든 월 토큰을 찾아 각 토큰 뒤~다음 토큰 앞을 해당 월 구간으로 보도록 고쳤다.
안전교육 배치 행(`연간 N시간 이상`, `실종·유괴`, `비상대응` 등)과 행사 일자 셀
(`23일(화)`, `불시`)은 Yearly broad theme가 아니므로 제외했다.

broad theme 매칭은 사전 등록 keyword로만 하고 매칭 실패는 `UNMATCHED`로 남긴다.
semantic merge·LLM 보정을 하지 않았다.

### C-3. Theme Reference v0.1.2 Delta 판정 `[실측]`

| 월 | Reference Theme | 최다 관찰 broad | 기관 | Reference 일치율 | 판정 |
|---|---|---|---:|---:|---|
| 3월 | 우리 원과 친구 | 새학기/우리반 | 10 | 67% | **SUPPORTED_STRONGLY** |
| 4월 | 봄 | 봄 | 8 | 48% | **SUPPORTED_STRONGLY** |
| 5월 | 나와 가족 | 나와 가족 | 8 | 52% | **SUPPORTED_STRONGLY** |
| 6월 | 우리 동네 | 우리 동네 | 8 | 54% | **SUPPORTED_STRONGLY** |
| 7월 | 여름 | 여름 | 10 | 67% | **SUPPORTED_STRONGLY** |
| 8월 | 교통기관 | 교통기관 | 8 | 62% | **SUPPORTED_STRONGLY** |
| 9월 | 우리나라와 세계 여러 나라 / 가을과 자연 | 우리나라/세계 | 11 | 81% | **SUPPORTED_STRONGLY** |
| 10월 | 우리나라와 세계 여러 나라 / 가을과 자연 | 가을 | 11 | 76% | **SUPPORTED_STRONGLY** |
| 11월 | 환경과 생활 | 환경과 생활 | 7 | 50% | SUPPORTED |
| 12월 | 겨울 | 겨울 | 9 | 68% | **SUPPORTED_STRONGLY** |
| 1월 | 생활도구 | 생활도구 | 8 | 58% | **SUPPORTED_STRONGLY** |
| 2월 | 성장한 우리 | 성장/전이 | 6 | 50% | SUPPORTED |

**SUPPORTED_STRONGLY 10개월 · SUPPORTED 2개월 · CONFLICTING 0 · NEW_CANDIDATE 0.**

### C-4. Theme Reference Delta 결론

| 확인 항목 | 결과 |
|---|---|
| 새로운 broad theme가 필요한가 | **아니오.** UNMATCHED 100건의 고유 표현 83개는 대부분 셀 분할 잔여물(`알아보기`, `탐구하기`, `3주`)이거나 하위 주제(`물과 우리 생활`, `바람, 공기와 우리 생활`)다. 12개 broad theme 밖의 반복 패턴이 아니다 `[판단]` |
| 기존 broad theme가 약화되었는가 | **아니오.** 12개월 모두 지지, CONFLICTING 0 |
| supported_ages 변경 근거가 생겼는가 | **아니오.** 신규 자료는 만4·5세 표기가 각 2건만 늘었고 혼합 명시는 0건이다 |
| ranking 변경 근거가 있는가 | **아니오.** 월별 최다 관찰이 Reference 후보 집합 안에 있다 |

**→ `NO_CONTENT_CHANGE_RECOMMENDED`** (Theme Reference v0.1.2)

신규 대구 자료는 기존 판단을 **뒤집지 않고 evidence를 두껍게** 했다.

---

## D. Monthly 구조 재분석

대상: MONTHLY_PLAN & 판독 가능 **99건**(신규 40) · 기관 18곳 `[실측]`.

### D-1. Section Coverage `[실측]`

원문 행 Label 기준. 파일/기관/월 커버리지와 Template A 상태를 함께 본다.

| semantic_key | 파일 | 기관 | 월 | 신규 | Template A |
|---|---:|---:|---:|---:|---|
| safety_education | 90 | 14 | 12 | 36 | **ACTIVE** |
| theme | 70 | 13 | 12 | 40 | **ACTIVE** |
| outdoor_play | 67 | 14 | 12 | 37 | **ACTIVE** |
| habits (기본생활습관) | 56 | 9 | 12 | 33 | inactive |
| **interest_area** (쌓기/역할/음률/언어…) | 50 | 10 | 12 | 23 | **Template에 없음** |
| **week_subtheme** (소주제/예상놀이/놀이흐름) | 45 | 9 | 12 | 25 | **Template에 없음** |
| goals | 42 | 7 | 12 | 8 | inactive |
| special_program | 36 | 8 | 12 | 17 | inactive |
| indoor_alternative | 35 | 5 | 12 | 23 | inactive |
| nutrition | 27 | 4 | 12 | 13 | inactive |
| event_schedule | 17 | 6 | 11 | 13 | inactive |
| parent (가정연계) | 14 | 2 | 10 | 2 | inactive |
| emergency_response | 7 | 1 | 6 | 0 | inactive |
| observation | 2 | 2 | 2 | 0 | inactive |

### D-2. Template A 재검증 `[판단]`

- ACTIVE 3종(theme / outdoor_play / safety_education)은 **관찰 상위 3위**와 정확히
  일치한다. Template A의 Active 선택은 Corpus로 지지된다.
- 반면 **`week_subtheme`(45파일·9기관·12개월)와 `interest_area`(50파일·10기관·12개월)는
  Template A에 semantic_key 자체가 없다.** `habits`(56파일)는 Optional로 정의되어 있으나
  inactive다.
- `emergency_response`는 1개 기관(금산군청)에만 나타난다 — 기관 고유 구조로 보인다.

**Template A Active/Inactive 상태는 이번 분석에서 변경하지 않았다.**

### D-3. 미매칭 원문 Label `[출처]`

`등원 및`, `단활`, `나누기`, `일정` 등은 셀 분할 잔여물이거나 일과 구분이다.
`신체활동`·`건강영양`·`원내체험 및`·`가정과의`는 각각 interest_area / nutrition /
special_program / parent로 묶었다. 원문 Label은 `analysis/tmp`에 보존되어 있다.

---

## E. Week Sub-theme 분석 — **이번 분석의 핵심**

### E-1. 주차 구조의 실재 `[실측]`

| 항목 | 값 |
|---|---:|
| 주차 축(1주 + 3~4주 동시 등장) 보유 | **95 / 99건 (96%)** |
| 주차별 Sub-theme **행** 보유 | **45 / 99건 (45%)** |
| Sub-theme 행을 가진 기관 | **9 / 18곳 (50%)** |

해당 기관 `[실측]`: 괴산하나 · 서진 · 아이들세상 · 예담 · 우리 · **청운** ·
**키즈로스쿨** · 해찬솔 · **혜솔** (굵게 = 신규 대구).

원문 Label은 기관마다 다르다 `[출처]`: `소주제` · `예상놀이` · `놀이흐름` ·
`기대되는 놀이` · `활동주제`. **semantic merge 전에 원문 Label을 보존했다.**

### E-2. 월 → 주차 전개 실측 표본 `[출처]`

```
[키즈로스쿨] 4월 · 예상놀이
   W1 따뜻한 봄 → W2 봄에 볼 수 있는 식물 → W3 봄 소풍 → W4 개구리 → W5 동물 친구들

[키즈로스쿨] 5월 · 예상놀이
   W1 나의 몸 → W2 나의 마음 → W3 생일 → W4 우리 가족

[키즈로스쿨] 5월(다른 해) · 예상놀이
   W1 소중한 나 → W2 소중한 나의 몸 → W3 나의 마음 → W4 우리 가족

[혜솔] 5월 · 예상놀이
   W1 들으며 느껴요 → W2 맡으며 느껴요 → W3 만지며 느껴요1 → W4 만지며 느껴요2

[청운] 4월 · 놀이흐름
   W1 싹 트네! 싹터요~ 케일 → W2 풀이랑 놀아요!

[서진] 3월 · 예상놀이
   W1 빨강반 친구와 선생님 얼굴을 표현해요.
[서진] 4월 · 예상놀이
   W1 봄에 볼 수 있는 동물을 표현해요.
```

**월 Theme 아래에 주차 단위의 의미 전개가 실제로 존재한다** `[출처]`. 예: 5월
`나와 가족` 아래 `나 → 나의 몸/마음 → 가족`으로 **좁은 것에서 넓은 것으로** 진행한다.

### E-3. 순서 패턴 `[판단]`

주차 위치별로 어휘 bucket(관심/관찰 · 탐구/실험 · 놀이/표현 · 확장/공유 · 정리)의
빈도를 세었으나, **bucket에 걸린 셀 수가 통계적 주장을 하기에 부족하다**. 표본이
9개 기관 · 45파일에 불과하고 Label 체계가 기관마다 달라 위치별 어휘 분포가 흩어진다.

- 의미 전개가 **존재한다**는 것: `[출처]`로 확인됨 (E-2)
- 전국적으로 반복되는 **고정 순서 패턴**이 있다는 것: **현재 Corpus로는 주장할 수 없음**

`[판단]` 개별 문서 안에서 좁음→넓음(5월 나→가족), 도입→심화(`만지며 느껴요1 → 2`) 같은
전개는 보이지만, 이를 12개월 × 5주차 Reference로 일반화할 근거는 아직 없다.
LLM으로 이상적인 순서를 만들어내지 않았다.

### E-4. 추출 한계 기록 `[판단]`

혜솔의 `소주제` 행 일부는 내용이 아니라 **기간(`3월 1일 ~ 3월 7일`)**이다. 이는
`소주제` Label 아래 실제로 기간 행이 오는 레이아웃 때문이며, 추출기가 label→행을
1:1로 본 결과다. 자동 보정하지 않고 그대로 남겼다.

---

## F. Activity 분석

### F-1. v0.2.0 Evidence 강도 실측 `[실측]`

| 지표 | 값 |
|---|---|
| 항목 수 | 198 |
| evidence 총계 | 288 |
| 월 coverage | 1~12 (12/12) |
| **evidence 1건뿐인 항목** | **152 / 198 (77%)** |
| **단일 기관에서만 관찰된 항목** | **178 / 198 (90%)** |
| evidence 6건 이상 항목 | 5 |

evidence 수 분포: 1건 152 · 2건 33 · 3건 4 · 4건 3 · 5건 1 · 6건 2 · 7건 1 · 11건 2.

**이것이 가장 중요한 약점이다** `[판단]`. 게다가 B-3에서 확인된 Template Family를
감안하면 "기관 2곳 관찰"의 일부는 독립 관측 1회일 수 있다.

### F-2. Activity Label 품질 — Human Review 후보 `[실측]`

자동 삭제·수정을 하지 않았다. **후보 목록만** 작성한다. 아래 분류기는 의도적으로
과포함(over-inclusive)이며, 최종 판정은 사람이 해야 한다.

| 분류 | 건수 |
|---|---:|
| GOOD_STANDALONE_LABEL | 174 |
| CONTEXT_DEPENDENT | 9 |
| POSSIBLE_SECTION_LABEL | 6 |
| INSTITUTION_SPECIFIC | 6 |
| SAFETY_ADJACENT | 3 |
| TOO_SHORT | 2 |

최소 1개 flag: **24 / 198 (12%)**

**CONTEXT_DEPENDENT 후보** `[출처]`

```
건너기          ev=1  months=[7]     ← 목적어 없음. 사용자가 지적한 사례
놀이를 해요.     ev=1  months=[5]     ← 무엇을 하는지 없음
가을담기        ev=1  months=[10]
줄넘기 / 비석치기 / 줄다리기 / 사방치기 / 딱지 치기 / 돌탑 쌓기
```

`[판단]` 뒤쪽 6개는 **그 자체로 완결된 전통놀이 이름**일 가능성이 높다. 자동 분류기가
"체언+기" 형태를 구분하지 못해 함께 걸린 것이다. 실제 검토 대상은
**`건너기` · `놀이를 해요.` · `가을담기`** 정도로 좁혀진다.

**INSTITUTION_SPECIFIC 후보** `[출처]`

```
전통 놀이 한마당 / 숲속 동물 보호소 / 비온 뒤 놀이터 탐험 /
놀이터를 탐색하며 놀이해요 / 바깥 놀이터 사진을 찍어요 /
바깥 놀이터에서 지켜야 할 약속을 정해요
```

**POSSIBLE_SECTION_LABEL 후보** `[출처]`: `대문놀이`(ev=2) · `모래놀이`(ev=6) ·
`전통놀이`(ev=11) · `투호놀이`(ev=4) · `팽이 놀이` · `물길 놀이`.
`[판단]` `전통놀이`(ev=11)는 **개별 활동이 아니라 활동 묶음 이름**일 수 있는데도
evidence가 가장 많아 Selection Rule에서 자주 뽑힌다. 실제 Demo 2026-09 W2가
`전통놀이`로 채워진 것이 이 문제의 실물이다.

### F-3. Corpus 재현 / 신규 후보 `[실측]`

`바깥놀이`/`실외놀이` 행 label로 시작하는 줄에서만 추출했다(부록 오염 방지).

| 분류 | 값 |
|---|---:|
| 추출된 고유 표현 | 170개 / 221건 관찰 |
| EXACT_EXISTING | 34개 |
| POSSIBLE_ALIAS | 50개 |
| NEW_RAW_CANDIDATE | 86개 |
| v0.2.0 198개 중 재현된 항목 | 33 (하한) |

재현율이 낮게 보이는 것은 추출기가 `바깥놀이` 행 **한 줄**만 읽어 wrap된 셀과
geometry 기반 분리가 필요한 문서를 놓치기 때문이다 — **재현율 자체의 하한**이며
Catalog 품질 지표가 아니다 `[판단]`.

**신규 자료에서만 관찰된 표현(원문 그대로 보존)** `[출처]`

```
NEW_RAW_CANDIDATE:
  자연물로 생일상 차리기 / 가족 수만큼 자연물 쌓기 / 문화재 돌탑 쌓기 /
  한복 입고 산책하기 / 제기차기 / 내 몸으로 숫자 만들기 /
  모래에 그린 내 마음 / 바닥에 분필로 가족 그림 차리기 /
  우리 동네 표지판 찾으며 / 공공기관 위치 알기 / 우리 동네 다양한 직업
AMBIGUOUS (셀 분할 잔여물로 의심):
  크리스마스트리를 / 우리 동네에서 들을 수 / 산책하며 궁금한 점 /
  모래 위에 형님이 된 내 / 공원에서 사진
EXCLUDE (주차 헤더가 섞임):
  1주 / 2주 / 3주 / 4주 / 5주
EXACT_EXISTING:
  모래로 전통음식 만들기 / 집게로 쓰레기 줍기
```

**fuzzy/semantic/embedding/LLM merge를 하지 않았고 canonical label을 만들지 않았다.**

### F-4. Age Evidence 재집계 `[실측]`

| 연령 | supported item | single-age evidence 有 | mixed-only | 관련 기관 |
|---|---:|---:|---:|---:|
| 만 3세 | 179 | **102** | 77 | 14 |
| 만 4세 | 100 | **4** | 96 | 14 |
| 만 5세 | 100 | **20** | 80 | 14 |

**만4세 단일연령 evidence는 여전히 4건뿐이다.** 신규 대구 자료는 만3세 중심이어서
(A-3: 만4세 표기 +2건, 혼합 명시 +0건) **이 약점을 보강하지 못했다** `[실측]`.

### F-5. Target 밖 연령 `[실측]`

본문에 만0~2세 표기가 있는 파일 11건. 대표 사례는 청운 9월(p1 만1세 · p2 만2세 ·
p3 만3세)이다. **Corpus에는 보존하되** supported age `{3,4,5}` 자동 확장 금지,
만2 evidence를 만3 evidence와 합치지 않는다는 규칙을 그대로 지켰다 — 본 분석에서
만0~2세 페이지를 Activity evidence로 집계하지 않았다.

### F-6. Curriculum Link `[실측]`

누리과정 5영역 명칭이 본문에 등장하는 파일은 **157건 중 4건**, 기관 3곳
(KOSPO빛사랑 · 두루미 · 서충주)뿐이다. 영역별로는 의사소통 2 · 신체운동 1 ·
사회관계 1 · 예술경험 0 · 자연탐구 0.

| 판정 | 내용 |
|---|---|
| **NOT_EXPLICIT** (지배적) | 153/157 파일에 누리과정 영역 표기가 없다 |
| AMBIGUOUS | 4건은 등장하지만 Activity 단위 연결인지 문서 머리말인지 확인 필요 |
| EXPLICITLY_OBSERVED | **Activity 단위로는 0건** |

`[판단]` **Activity Reference v0.2.0의 `curriculum_links`가 비어 있는 것은 결함이
아니라 Corpus를 정확히 반영한 결과다.** 문서에 없는 연결을 LLM·상식으로 생성하지
않았다. 이는 기존 분석(§3.5 "누리과정 5개 영역은 실측 양식에 표기되지 않는다")의
재확인이다.

---

## G. Safety

`[실측]` Monthly 99건 중 **34건**이 안전교육 행에 `[태그]`를 붙인다.

| 태그 | 건수 | 기관 |
|---|---:|---:|
| 실종∙유괴의 예방∙방지 | 9 | 1 |
| 교통안전 | 7 | 3 |
| 소방대피훈련 | 6 | 2 |
| 생활안전 | 4 | 2 |
| 아동학대예방안전 | 3 | 1 |
| 성폭력예방안전 / 재난대비 / 미세먼지 / 식중독 예방 … | 1~2 | 1~2 |

`[판단]` 태그 어휘가 기관마다 다르고(`생활안전`·`미세먼지`·`식중독 예방`은 아동복지법
시행령 별표6의 법정 6구분에 **없다**), 인성 덕목(`정직`·`존중`·`배려`·`책임`·`절제`)이
같은 행에 섞여 있는 기관도 있다.

**분리 확인**

1. `SafetyLegalRule` (법령/검증 기준) — `data/rules/safety_education_legal_v1.json`.
   이번 분석에서 **읽지도 수정하지도 않았다**.
2. Institution Monthly/Annual Safety Placement — 위 태그는 **기관이 실제로 배치한
   Sample Evidence**다. 최신 법률 근거도, 법정 월별 필수 배치도, 국가 표준 월 배치도
   아니다.

Yearly broad theme 집계에서도 안전교육 배치 행을 명시적으로 제외했다(C-2).

---

## H. Monthly 품질 저하 원인 진단

사용자가 관찰한 증상: (1) Activity 간 연결감 약함 (2) 주차별 흐름 없음
(3) 일부 label이 독립 셀에서 어색함 (4) curriculum diversity 정보 없음.

| 축 | 판정 | Corpus 근거 |
|---|---|---|
| **Week Sub-theme 부재** | **SUPPORTED_BY_CORPUS** | 주차 축은 96% 문서에 있고, 주차별 Sub-theme 행이 45%·9기관·12개월에 존재한다(E-1). 실제 전개도 확인된다(E-2). Production Template A에는 `week_subtheme` semantic_key가 **없고**, Monthly는 월 Theme 바로 아래 Activity를 배치한다 |
| **Reference Coverage 문제** | **SUPPORTED_BY_CORPUS** | 198항목 중 77%가 evidence 1건, 90%가 단일 기관 관찰(F-1). 2026-09/만4세 후보는 31개지만 다른 월·연령은 4~9개(월×연령 조합 실측) |
| **Age Evidence 문제** | **SUPPORTED_BY_CORPUS** | 만4세 single-age evidence 4건(F-4). 신규 자료로도 개선되지 않음 |
| **Activity Label Quality** | **PARTIALLY_SUPPORTED** | 후보 24/198(12%). 그중 실제로 어색한 것은 `건너기`·`놀이를 해요.`·`가을담기`와 묶음 이름 성격의 `전통놀이`(ev=11) 정도. **비율은 낮지만 evidence가 많은 항목이 걸려 Selection에 자주 노출된다** |
| **Corpus correlation** | **SUPPORTED_BY_CORPUS** | Template Family 4기관 확인(B-3). institution_count를 독립 근거 수로 읽으면 evidence strength를 과대평가한다 |
| **Curriculum diversity 정보 부재** | **SUPPORTED_BY_CORPUS (원인은 Corpus)** | 157건 중 Activity 단위 누리과정 연결 0건(F-6). Rule의 결함이 아니라 **원천 자료에 없다** |
| **Template Structure 문제** | **PARTIALLY_SUPPORTED** | `week_subtheme`(45파일)·`interest_area`(50파일)·`habits`(56파일)가 Template A에 없거나 inactive. 다만 ACTIVE 3종 선택 자체는 관찰 상위 3위와 일치 |
| **Ranking Rule 문제** | **NOT_SUPPORTED** | Rule은 5단 우선순위로 동작하고 Demo에서 `MATCHED_PARENT_THEME` → `AVOIDED_REPEAT_IN_MONTH`로 중복 없이 5주를 채웠다. **입력 후보 집합과 셀 의미의 문제이지 순위 계산의 문제라는 근거가 없다** |
| **Institution-specific Source** | **PARTIALLY_SUPPORTED** | INSTITUTION_SPECIFIC 후보 6건 잔존(F-2). D3 결정으로 대부분 제외되었으나 `숲속 동물 보호소` 등이 남아 있다 |

### 진단 요약 `[판단]`

Demo 2026-09 결과를 다시 보면 원인이 드러난다.

```
주제: 우리나라와 세계 여러 나라
W1 무궁화 꽃이 피었습니다   W2 전통놀이   W3 가을 나들이
W4 사방치기                W5 모래 위에 옛 그림을 그려요
```

개별 Activity는 모두 9월 주제와 관련이 있다. 문제는 **W1→W5 사이에 교육적 진행이
없다**는 것이다. Corpus의 실제 문서는 그 자리에 `따뜻한 봄 → 봄에 볼 수 있는 식물 →
봄 소풍` 같은 **주차 Sub-theme 축**을 두고, Activity는 그 아래에 놓인다.
현재 Production은 그 중간 층이 통째로 없다.

또한 `전통놀이`(W2)는 묶음 성격 label인데 evidence 11건으로 가장 강해 상위에 뽑힌다.

---

## I. Recommendations

> **전부 제안이며 이번 작업에서 구현하지 않았다.** Reference JSON 생성·Production
> 연결·Rule 변경을 하지 않았다.

| # | 제안 | 판정 | 근거 |
|---|---|---|---|
| 1 | Week Sub-theme Reference 신설 | **`WEEK_SUB_THEME_REFERENCE_RECOMMENDED`** | E-1/E-2. 다만 12개월 × 5주차 고정 순서는 **아직 근거 부족**(E-3). 먼저 원문 Label 보존형 관찰 데이터셋으로 시작할 것 |
| 2 | Activity display label layer 도입 | **RECOMMENDED** | F-2. 원문 provenance(`전통놀이`)를 보존하면서 셀 표시용 layer를 분리하면 Catalog를 다시 만들지 않고 개선 가능 |
| 3 | Activity Reference v0.3 | **`ACTIVITY_REFERENCE_V0_3_RECOMMENDED` (조건부)** | F-1. 필요하지만 **신규 전사 없이는 효과가 제한적**이다. 지금 필요한 것은 항목 수가 아니라 evidence 두께와 만4세 단일연령 근거 |
| 4 | Theme Reference vNext | **NOT_RECOMMENDED** | C-4. `NO_CONTENT_CHANGE_RECOMMENDED` |
| 5 | Selection Rule 개선 | **NOT_RECOMMENDED (현재로선)** | H. Rule 자체의 결함 근거 없음. 단 `POSSIBLE_SECTION_LABEL` 항목의 evidence 가중치는 label layer 도입 후 재검토 |
| 6 | `institution_count` 해석 보정 | **RECOMMENDED** | B-3. `observed institution count`와 `possible independent source count`를 분리 기록 |
| 7 | 추가 Corpus 수집 우선순위 | — | ① **만4세 단일연령 Monthly** ② 비9월(10·11·12·2월) ③ Template Family 밖 기관 ④ image-only 18건 OCR |

---

## 24. 최종 질문 답변

### Q1. 신규 대구 자료를 포함해도 Theme Reference v0.1.2의 12개월 Broad Theme는 여전히 타당한가?

**예. 타당하다.** `[실측]`

12개월 전부 지지된다 — SUPPORTED_STRONGLY 10개월, SUPPORTED 2개월, **CONFLICTING 0,
NEW_CANDIDATE 0**. 45개 기관 · 54개 판독 가능 Yearly 문서 기준이다. 월별 Reference
일치율은 48~81%이고 기관 수는 6~11곳이다. 신규 자료는 판단을 뒤집지 않고 evidence를
두껍게 했다. → `NO_CONTENT_CHANGE_RECOMMENDED`

### Q2. Activity Reference v0.2.0의 Evidence strength는 얼마나 개선됐는가?

**거의 개선되지 않았다.** `[실측]`

- Catalog 자체는 v0.2.0 그대로다(198항목 / evidence 288 / 월 12/12). 이번 분석은
  Catalog를 수정하지 않았으므로 숫자 변화가 없는 것이 정상이다.
- 신규 Corpus가 **Catalog에 반영된다고 가정했을 때의 잠재적 개선**: 신규 자료에서
  `EXACT_EXISTING` 2건, `NEW_RAW_CANDIDATE` 후보 약 11건(AMBIGUOUS/EXCLUDE 제외).
- **개선되지 않은 핵심 약점**
  - evidence 1건뿐 **152/198 (77%)**
  - 단일 기관 관찰 **178/198 (90%)**
  - 만4세 single-age evidence **4건** — 신규 자료의 만4세 표기가 +2건에 그쳐 보강 실패
  - 게다가 신규 2기관(혜솔·키즈로스쿨)이 기존 2기관과 **Template Family**여서
    기관 수 증가분이 독립 근거 증가분보다 작다

`[판단]` 신규 대구 자료는 **월 coverage 균형**과 **가정 어린이집 표본**(1→34)을
보강했지만 **evidence 독립성과 만4세 근거는 보강하지 못했다.**

### Q3. 현재 Monthly Demo가 어색한 가장 큰 원인은? (우선순위)

| 순위 | 원인 | 판정 | 비중 근거 |
|---|---|---|---|
| **1** | **주차별 Sub-theme 부재** | SUPPORTED_BY_CORPUS | 주차 축은 96% 문서에 있는데 Production에는 월 Theme→Activity 2층뿐. Corpus의 실제 문서는 그 사이에 주차 의미 축을 둔다(E-2). 증상 "연결감 없음 / 주차 흐름 없음"을 직접 설명한다 |
| **2** | **Activity 데이터 부족(evidence 두께)** | SUPPORTED_BY_CORPUS | 77% evidence 1건 · 90% 단일 기관. 9월 만4세는 후보 31개지만 11월·2월은 4개. 월·연령을 바꾸면 급격히 얇아진다 |
| **3** | **Activity 표현 품질** | PARTIALLY_SUPPORTED | flag 12%로 비율은 낮지만 `전통놀이`(ev=11)처럼 **evidence가 강한 항목이 묶음 이름**이라 노출 빈도가 높다 |
| **4** | **Selection Rule** | NOT_SUPPORTED | Rule은 의도대로 동작한다. 입력과 표시층 문제이지 순위 계산 문제라는 근거가 없다 |

### Q4. 가장 적은 구조 변경으로 Monthly 품질을 개선하려면 무엇부터?

`[판단]` 구조 변경 비용 순으로.

1. **Activity display label layer** — Catalog 재발행 없이 표시 문자열만 분리한다.
   `전통놀이`·`건너기` 같은 항목의 셀 표시를 개선하면서 원문 provenance는 그대로 둔다.
   Domain/Rule/Template 변경 없음. **가장 싸다.**
2. **`POSSIBLE_SECTION_LABEL` 6건 + `CONTEXT_DEPENDENT` 3건 Human Review** — 데이터
   변경만으로 체감 품질이 올라간다. 자동 수정 금지, 사람 판정 필요.
3. **Week Sub-theme Reference (관찰 보존형)** — 효과는 가장 크지만 Template A에
   semantic_key 추가 + Monthly Generate 흐름 변경이 필요하다. E-3대로 **고정 순서를
   규정하지 말고** 월별 관찰 Sub-theme 후보 집합으로 시작할 것.
4. Activity Reference v0.3 — 신규 전사 corpus 확보 후.

### Q5. Weekly 구현 전 반드시 해결 vs 나중에 개선해도 되는 것

**Weekly 착수 전 반드시 해결** `[판단]`

| # | 항목 | 이유 |
|---|---|---|
| 1 | **Monthly → Weekly 계승 단위 결정** | Weekly는 Monthly의 어느 축을 상속받는가? 지금은 월 Theme와 Activity만 있고 주차 의미 축이 없다. 이 결정 없이 Weekly를 만들면 Monthly와 같은 "연결감 없음" 문제가 그대로 복제된다. **E의 Week Sub-theme 결정이 Weekly의 선행 조건이다** |
| 2 | **Weekly Corpus 부족** | 현재 WEEKLY_PLAN은 **2건**(그중 1건은 image-only). Yearly 55 / Monthly 99와 비교가 안 된다. Reference 없이 Weekly를 설계하면 Rule이 고를 후보가 없다 |
| 3 | **`institution_count` 해석 보정** | B-3. Weekly에서도 같은 Template Family 문제가 재현된다. evidence strength 계산 규칙을 먼저 정해야 한다 |

**나중에 개선해도 되는 것**

| 항목 | 이유 |
|---|---|
| Activity Reference v0.3 | Monthly가 이미 동작한다. 추가 corpus 확보 후 일괄 처리가 효율적 |
| Activity display label layer | 바람직하지만 Weekly의 선행 조건은 아니다 |
| curriculum_links 채우기 | **Corpus에 없다.** 외부 근거 확보 전까지는 미룰 수밖에 없다 |
| image-only 18건 OCR | 전부 기존 자료이고 월 coverage는 이미 12/12 |
| Theme Reference vNext | 불필요 (Q1) |

---

## 부록. 분석 방법과 한계

**사용한 방법** — deterministic parser · `pdftotext -layout/-raw` · PyMuPDF 페이지
단위 텍스트 · regex · counting · normalization · 6-gram Jaccard · 직접 원문 확인.

**하지 않은 것** — LLM 원문 보정 · 잘린 Activity 복원 · Sub-theme 추론 생성 ·
Theme semantic merge · 연령 추정 · fuzzy/embedding merge · canonical label 생성.

**알려진 한계** `[판단]`

1. Activity 추출기는 `바깥놀이` 행 **한 줄**만 읽으므로 wrap된 셀과 geometry 분리가
   필요한 문서를 놓친다. F-3의 재현율 33은 **하한**이다.
2. Yearly 주제 추출은 2칸 이상 공백을 셀 경계로 가정한다. 마인드맵형 문서
   (강원도청)는 추출되지 않는다.
3. Label 품질 분류기는 의도적으로 과포함이며 `사방치기` 같은 완결 놀이 이름을
   오탐한다. **후보 목록이지 판정이 아니다.**
4. image-only 18건은 분석에서 빠져 있다. OCR 없이는 접근 불가.
5. Template Family 판정은 `POSSIBLE_*`까지이며 동일 Source 확정이 아니다.
