# Monthly Content Model vNext — Evidence-Grounded Design

> **ANALYSIS + DESIGN ONLY.** Production(`src/`, `data/`, `demo-planning/`, Golden,
> `CLAUDE.md`)을 수정하지 않았다. 여기의 모든 제안은 설계일 뿐이며 구현하지 않았다.
>
> 근거 표기: `[실측]` 직접 계산 · `[출처]` 문서 원문 · `[판단]` 분석적 해석

재현:

```bash
python analysis/experiments/monthly_vnext/reproduce_current.py   # §2, §15
python analysis/tools/week_experience.py                         # §6, Q3
python analysis/tools/trace_label_sources.py                     # §7, Q6
python analysis/tools/report_activity.py                         # §7, §8
```

---

## 1. Executive Summary

현재 Monthly는 **기능적으로 정상이고 Rule도 의도대로 동작한다.** 품질 문제의
원인은 Rule의 결함이 아니라 세 가지다.

1. **월 Theme와 Activity 사이에 주차 의미 축이 없다.** Corpus의 실제 문서 96%는
   주차 축을 갖고, 45%는 주차별 경험 행을 별도로 둔다. Production에는 그 층이 없다.
2. **Theme 축이 Ranking에서 사실상 작동하지 않는다.** 재현한 52개 Cell 전부
   `theme_matched=True`였다 `[실측]`. 만4·5세에서는 후보의 100%가 theme에 연결되어
   있어 변별력이 0이고, 6월은 반대로 0/7이라 축이 붕괴한다.
3. **어색한 Label의 주원인은 Reference 품질이 아니라 파서 결함이다.** `건너기`는
   원문 `장화 신고 물웅덩이 / 건너기`가 줄바꿈에서 잘린 절반이며, **양쪽 절반이 모두
   별개 Catalog 항목으로 등재되어 있다** `[출처]`.

따라서 vNext는 **재작성이 아니라 Additive 확장 + 데이터 수리**다.

---

## 2. Current Monthly Production Behavior (코드 역추적)

### 2.1 Activity Hard Filter `[출처]`

`ActivityCatalog.eligible_candidates()` (`domain/activity_reference.py:421`)

```python
if not self.is_active: return ()                    # ① 승인 Gate
if section_key in FORBIDDEN_PLACEMENT_SLOTS: return ()   # ② safety_education 차단
... a.supports_slot(section_key)                    # ③ placement_slots 포함 여부
and a.supports_setting(section_key)                 # ④ outdoor_play는 OUTDOOR|EITHER
and a.supports_month(calendar_month)                # ⑤ applicable_months 포함
and a.supports_age_set(ages)                        # ⑥ 선택 연령 전부 지원 + 혼합 규칙
```

Hard filter는 **정확히 이 6개뿐**이다. 정렬은 `activity_id` 기준이며 우선순위가 아니다.

### 2.2 Ranking Rule `[출처]`

`rules/monthly_activity_selection.py:_sort_key`

```python
(_repeat_penalty,      # ① 같은 달 재사용 + 현재 Activity (합산)
 _theme_penalty,       # ② parent theme_id 미연결이면 1
 _curriculum_penalty,  # ③ 이미 쓰인 누리영역 사용 횟수 합
 -evidence_strength_for_month,   # ④ 해당 월 evidence 개수 (많을수록 우선)
 activity_id)          # ⑤ 안정 tie-break
```

지시서에 적힌 5단 순위와 **정확히 일치한다.** `evidence_strength_for_month`는
`sum(1 for e in evidence if e.observed_month == calendar_month)` — 단순 개수이며
기관 독립성·연령 가중이 없다 `[출처]`.

### 2.3 현재 Selection이 사용하지 **않는** Context `[실측]`

| Context | 사용 여부 | 코드 근거 |
|---|---|---|
| Week Sub-theme / Week Experience | **미사용** | `select_activity_for_cell` 인자에 없음. `week_id`는 trace 기록용 |
| Official Play Evidence | **미사용** | Catalog schema에 필드 없음 |
| Official Topic Support | **미사용** | 동일 |
| Display Label Quality | **미사용** | `label` 단일 필드 |
| Single-age vs Mixed-age Evidence Strength | **미사용** | `evidence_strength_for_month`가 `age_scope`를 보지 않음 (docstring이 명시적으로 "연령별 가중은 하지 않는다") |
| Source Independence | **미사용** | `observed_institution_count` property는 존재하나 Rule이 호출하지 않음 |
| Activity Type Diversity | **미사용** | 필드 없음 |
| Institution-specific Penalty | **미사용** | D3 결정으로 ingest 단계에서 제외, Rule에는 없음 |
| Play Flow | **미사용** | 개념 자체가 없음 |

---

## 3. Evidence Inventory `[실측]`

| Source Type | 경로 | 파일 | 비고 |
|---|---|---:|---|
| OFFICIAL_CURRICULUM | `00_curriculum_core/` | 5 | 고시문(교육부/복지부), 해설서, 놀이이해/실행자료 |
| OFFICIAL_PLAY_CASE | `10_play_cases/` | 4 | general 2, outdoor_ecology 1, picturebook 1 |
| OFFICIAL_AGE_SPECIFIC | `20_age_specific/` | **2** | **age5_transition만 2건. `age3/`와 `age4/`는 빈 디렉터리** |
| OFFICIAL_TOPIC_SUPPORT | `30_topic_support/` | 7 | community 1, cultural_diversity 1, digital 1, economy_finance 1, environment 2, social_emotional 1 |
| OBSERVATION_EVALUATION | `40_observation_evaluation/` | 4 | KICCE 관찰척도, 평가 매뉴얼 등 |
| LEGAL_SAFETY | `50_legal_safety/` | 5 | 아동복지법 계열, 교통안전 |
| OPERATION_GUIDE | `60_operation_guides/` | 3 | 보육사업안내 |
| PUBLIC_FIELD_CASE | `public_field_cases/` | 1 | 서울센터 놀이기록 공모전 사례집 |
| INSTITUTION_SAMPLE | `references/samples/` | 175 | yearly 55 / monthly 99 / weekly 2 (본문 기준) |

**결정적 사실** `[실측]`: `20_age_specific/age3/`와 `age4/`가 **비어 있다.** Official
Age Evidence는 만5세에만 존재한다. 이것이 Q7의 답을 직접 규정한다.

---

## 4. Institution Monthly Pattern Analysis

### 4.1 §4 재현 결과 — Monthly 12 Case `[실측]`

현재 Production 경로(`eligible_candidates` → `select_activity_for_cell`)로 재현.
총 52 Cell 생성.

| Flag | 건수 | 비율 |
|---|---:|---:|
| AGE_EVIDENCE_WEAK | 37 | 71% |
| MONTH_EVIDENCE_THIN | 31 | 60% |
| CONTEXT_DEPENDENT_LABEL | 6 | 12% |
| REPETITIVE_ACTIVITY_TYPE | 3 case | 25% |
| INSTITUTION_SPECIFIC | 2 | 4% |
| TOO_SHORT | 2 | 4% |

사용자가 보고한 사례가 그대로 재현된다 `[실측]`.

```
2026-07  만3세  Theme: 여름   후보 16개
  W1 우리 동네 분수대 가 보기        ev月1/총1 기관1  [AGE_EVIDENCE_WEAK, MONTH_EVIDENCE_THIN]
  W2 셀로판지로 여름 하늘 바라보기    ev月1/총1 기관1  [동일]
  W3 건너기                      ev月1/총1 기관1  [TOO_SHORT, CONTEXT_DEPENDENT_LABEL, …]
  W4 산책하며 여름 곤충 찾기         ev月1/총1 기관1  [동일]
  W5 무인 아이스크림 매장 찾아가기    ev月1/총1 기관1  [동일]
  ! REPETITIVE_ACTIVITY_TYPE — 산책/나들이류 2/5
```

**후보 수 편차** `[실측]`: 9월 만3세 37개 ↔ 11월 만5세 4개, 2월 만5세 4개.
9월은 5주를 서로 다른 강한 evidence로 채우지만, 11·2월은 후보가 주차 수와 거의
같아 사실상 **선택이 아니라 나열**이 된다.

### 4.2 Theme 축 변별력 `[실측]` — 핵심 발견

각 월·연령에서 "후보 중 parent theme에 연결된 비율":

| 월 | Theme | 만3 | 만4 | 만5 |
|---|---|---|---|---|
| 3월 | 우리 원과 친구 | 12/15 | **7/8** | **11/11** |
| 4월 | 봄 | 11/16 | **9/9** | **9/9** |
| 5월 | 나와 가족 | 10/12 | **8/8** | **8/8** |
| **6월** | 우리 동네 | 2/13 | **0/7** | **0/7** |
| 7월 | 여름 | 9/16 | **9/9** | **9/9** |
| 8월 | 교통기관 | 8/12 | **7/7** | **7/7** |
| 9월 | 우리나라와 세계 | 25/37 | 25/31 | 20/27 |
| 10월 | (우리나라 우선 해소) | 3/15 | 3/8 | 3/8 |
| 11월 | 환경과 생활 | 8/11 | **4/4** | **4/4** |
| 12월 | 겨울 | 12/17 | **7/7** | **7/7** |
| 1월 | 생활도구 | 11/14 | **8/8** | **8/8** |
| 2월 | 성장한 우리 | 4/11 | **4/4** | **4/4** |

`[판단]` 만4·5세는 **9개월이 100% 연결**이라 theme 축이 완전한 no-op이고, **6월은
0% 연결**이라 축이 붕괴한다. 두 경우 모두 선택은 ④ evidence 개수와 ⑤ id로 떨어진다.
즉 **현재 Monthly 선택의 실질 기준은 "그 달 evidence가 가장 많은 것부터"**이다.

이것이 `전통놀이`(ev=11, 6기관)가 9월 W2에 오는 이유를 정확히 설명한다.

---

## 5. Official Evidence Crosswalk

### 5.1 Official Source는 월 배치를 규정하지 않는다 `[실측]`

30_topic_support 5개 문서 전수 검사:

| 문서 | `N월에 실시/배치/운영` 패턴 | `N월` 언급 | `놀이` 언급 |
|---|---:|---:|---:|
| 놀이 쏙 경제금융 톡 | **0** | 4 | 291 |
| 유아의 균형 있는 디지털 역량 | **0** | 0 | 235 |
| 지속가능발전 기반 유아환경교육 | **0** | 0 | 61 |
| 2025 문화다양성 이음교육 | **0** | 1 | 251 |
| 따뜻한 말 한마디 따뜻한 행동 하나 | **0** | 1 | 339 |

**월별 필수 배치 규정이 단 한 건도 없다.** 따라서 `OFFICIAL_MONTH_PLACEMENT`
판정은 어떤 Theme에도 부여할 수 없다.

반면 놀이 사례와 교사 지원 서술은 풍부하다 `[출처]` (지속가능발전 환경교육 지도서
p.40 발췌: 텃밭의 벌레를 둘러싼 유아 발화와 교사 질문 전개가 그대로 기록되어 있다).

### 5.2 Theme × Official Crosswalk `[판단]`

| # | Theme | Relevant Official Source | Type | Age Scope | Usable As | Not Usable As |
|---|---|---|---|---|---|---|
| 3월 | 우리 원과 친구 | `social_emotional/따뜻한 말 한마디` | TOPIC_SUPPORT | 유아 일반 | 관계·정서 경험 방향, 놀이 후보 검증 | 3월 필수 Theme 근거 |
| 4월 | 봄 | `outdoor_ecology/생태놀이` | PLAY_CASE | 유아 일반 | 자연 탐색 놀이 방향 | 4월 배치 근거 |
| 5월 | 나와 가족 | `social_emotional` | TOPIC_SUPPORT | 유아 일반 | 정서·관계 맥락 | 5월 배치 근거 |
| 6월 | 우리 동네 | `community/소규모 유치원 공동교육과정`, `economy_finance` | TOPIC_SUPPORT | 유아 일반 | 지역사회·경제경험 방향 | 6월 필수 Theme 근거 |
| 7월 | 여름 | `outdoor_ecology` | PLAY_CASE | 유아 일반 | 자연·물 놀이 방향 | 7월 배치 근거 |
| 8월 | 교통기관 | **없음** | — | — | — | — |
| 9월 | 우리나라와 세계 | `cultural_diversity/2025 문화다양성 이음교육` | TOPIC_SUPPORT | **이음교육(만5 인접)** | 문화다양성 경험 방향 | 9월 배치 근거, 만3·4 자동 적용 |
| 10월 | 가을과 자연 | `outdoor_ecology` | PLAY_CASE | 유아 일반 | 자연 탐색 | 10월 배치 근거 |
| 11월 | 환경과 생활 | `environment` 2건 | TOPIC_SUPPORT | 유아 일반 | 환경·지속가능 경험 방향 | 11월 배치 근거 |
| 12월 | 겨울 | `outdoor_ecology` | PLAY_CASE | 유아 일반 | 자연 변화 탐색 | 12월 배치 근거 |
| 1월 | 생활 도구 | `digital/유아의 균형 있는 디지털 역량` | TOPIC_SUPPORT | 유아 일반 | 도구·미디어 경험 방향 | 1월 배치 근거 |
| 2월 | 성장한 우리 | `age5_transition` 2건 | AGE_SPECIFIC | **만5세 전용** | 만5 전이 경험 | **만3·4 적용 금지** |

`[실측]` **8월(교통기관)만 대응 Official Source가 없다.**

---

## 6. Week Experience Analysis

### 6.1 추출 결과 `[실측]`

| 항목 | 값 |
|---|---:|
| Week Experience 행 보유 Monthly 문서 | 33건 (기간 행 제외 후) |
| 기관 | 9곳 |
| Template Family 소속 문서 | 12건 |
| 원문 Label 어휘 | `소주제` · `예상놀이` · `예상 놀이` · `놀이흐름` |

**원문 Label이 4종뿐이고 `WEEK_SUBTHEME`라는 표현은 Corpus에 존재하지 않는다** `[실측]`.

### 6.2 월별 Concept Cluster `[실측]`

독립 source는 Template Family 4곳을 1개로 축약해 계산했다.

| 월 | 최다 Concept | obs | 기관 | 독립 source |
|---|---|---:|---:|---:|
| 3월 | 친구/우리반 | 2 | 2 | 2 |
| 4월 | 자연/동식물 | 5 | 2 | 2 |
| 5월 | 나/몸/마음 | 6 | 2 | 2 |
| 5월 | 가족 | 5 | 3 | **3** |
| 6월 | 동네/기관 | 1 | 1 | 1 |
| 8월 | 이동/교통 | 1 | 1 | 1 |
| 9월 | 전통/명절 | 4 | 3 | **3** |
| 10월 | 자연/동식물 | 2 | 2 | 2 |
| 11월 | 환경/자원 | 3 | 3 | 2 |
| 12월 | 날씨/계절변화 | 2 | 2 | 2 |
| 1월 | 도구/기계/디지털 | 2 | 1 | 1 |
| 2월 | 성장/전이 | 1 | 1 | 1 |

### 6.3 순서 지지도 `[실측]`

| 주차 | 상위 concept |
|---|---|
| W1 | 나/몸/마음(6), 친구/우리반(5), 환경/자원(3) |
| W2 | 물/여름놀이(3), 나/몸/마음(2), 자연/동식물(2) |
| W3 | 나/몸/마음(2), 전통/명절(2) |
| W4 | 가족(2), 자연/동식물(1) |
| W5 | 자연/동식물(1), 친구/우리반(1) |

`[판단]` W1에 `나/몸/마음`·`친구/우리반`이 몰리는 경향은 보이지만, 같은 concept가
W2·W3에도 반복 등장한다. **고정 순서 패턴의 근거로는 부족하다.**

다만 **개별 문서 안의 전개**는 명확하다 `[출처]`.

```
[키즈로스쿨] 5월  나의 몸 → 나의 마음 → 생일 → 우리 가족        (좁음 → 넓음)
[키즈로스쿨] 5월  소중한 나 → 소중한 나의 몸 → 나의 마음 → 우리 가족
[혜솔]      5월  들으며 느껴요 → 맡으며 느껴요 → 만지며 느껴요1 → 만지며 느껴요2  (감각 축 누적)
[키즈로스쿨] 4월  따뜻한 봄 → 봄에 볼 수 있는 식물 → 봄 소풍 → 개구리 → 동물 친구들
```

**`OBSERVED_WEEK_PATTERN` = YES / `ORDER_SUPPORT` = WEAK** 로 분리해 기록한다.

### 6.4 §8 판정 요약

| Evidence 축 | 판정 |
|---|---|
| OBSERVED_WEEK_PATTERN | **YES** — 9기관 33문서 12개월 |
| CANDIDATE_WEEK_EXPERIENCE | **YES** — 원문 보존 형태로 추출 가능 |
| SOURCE_SUPPORT | 월별 독립 source 1~3 |
| ORDER_SUPPORT | **WEAK** — 문서 내 전개는 있으나 교차 반복 불충분 |
| AGE_SUPPORT | **거의 없음** — 아래 6.5 |
| INDEPENDENT_SOURCE_SUPPORT | 최대 3, Template Family 보정 후 |

### 6.5 연령 차이 `[실측]`

Q3 Coverage Matrix에서 **만3/만4/만5 열의 값이 거의 동일하다.** Week Experience를
가진 문서 대부분이 `만3-5세` 혼합 표기 문서이기 때문이다. 즉 **주차 경험의 연령별
차이를 뒷받침할 데이터가 사실상 없다.**

---

## 7. Activity Quality Analysis

### 7.1 §11/Q6 — 문제 Label 원본 역추적 `[출처]`

**① `건너기` → PARSER_PROBLEM (확정)**

우리어린이집 2026-07 원문:

```
    셀로판지로 여름     장화 신고 물웅덩이      자연물로 여름 디저트     우리 동네 분수대
    하늘 바라보기                                          가 보기
                          건너기                만들기
```

원 셀은 **`장화 신고 물웅덩이 건너기`** 한 개이며 줄바꿈으로 wrap된 것이다.
**Catalog에는 `장화 신고 물웅덩이`(ev=1, month 7)와 `건너기`(ev=1, month 7)가
각각 별도 항목으로 등재되어 있다** — 한 활동이 두 개의 반쪽으로 쪼개졌다.
같은 줄의 `자연물로 여름 디저트` + `만들기`도 동일 구조다.

**② `놀이를 해요.` → PARSER_PROBLEM (확정)**

서진 2026-05 원문:

```
 바깥놀이   우리집에 왜 왔니? 놀이를 해요.           내 몸을 꼭꼭 숨겨요.
```

원 셀은 `우리집에 왜 왔니? 놀이를 해요.`이며 `?` 뒤에서 잘렸다.

**③ `가을담기` → PARSER_PROBLEM (부분) / AMBIGUOUS**

서진 2025-10 원문:

```
              자연물 물감 [실내대체활동] 가을열매를 맞춰라!
               가을담기 [실내대체활동] 잠자리 멀리 날리기
```

바깥놀이 열이 `자연물 물감 / 가을담기` 2줄이다. 한 활동의 wrap인지 2개 활동인지
**원문만으로 확정 불가** → 사람 확인 필요. `자연물 물감`도 별도 항목으로 등재되어 있다.

**④ `전통놀이` → REFERENCE_PROBLEM + DISPLAY_PROBLEM (확정)**

원문 관찰 표현 `[출처]`:

```
♥바깥놀이 -전통놀이를 해요        (아이사랑 9월)
-전통놀이                        (괴산하나 9월)
<추석>명절전통놀이                (큰빛 9월)
-전통놀이체험                    (해찬솔 9월)
전통놀이를 해요                  (서진 2025-10)
전통놀이 한마당을 열어요.          (서진 2026-09)
```

서로 다른 6개 표현이 공통 어간 `전통놀이`로 정규화되었다. 그 결과 **개별 활동이
아니라 활동 묶음(category)이 evidence 11건·6기관으로 Catalog 최강 항목이 되었고**,
Ranking ④축이 이를 상위로 올린다.

**자동 파서 분할 탐색은 결론이 아니다** `[판단]`: 인접 짧은 줄을 자동 탐색했더니
시립새봄 9월의 `투호놀이 / 줄다리기 / 동대문 놀이`처럼 **세로로 나열된 별개 활동**을
대량 오탐했다. wrap과 list를 자동으로 구분할 수 없으므로, 위 4건은 **수동 확인으로만**
확정했다.

### 7.2 §11 분류 체계의 유용성 검증 `[판단]`

| 분류 | Corpus에서 유용한가 | 근거 |
|---|---|---|
| `GOOD_STANDALONE` | 유용 | 174/198 |
| `POSSIBLE_FRAGMENT` | **자동 판정 불가** | 조사 종결 규칙이 `…놀이`, `무궁화꽃이` 같은 정상 명사를 오탐. 길이 기준도 `강강술래`를 오탐 |
| `CONTEXT_DEPENDENT` | 부분 유용 | `사방치기`·`비석치기`(완결 놀이명)와 `건너기`(절편)를 자동 구분 불가 |
| `TOO_SHORT` | 유용 | 2건 (`줄넘기`, `건너기`) |
| `SECTION_LABEL_LIKE` | **유용** | `전통놀이`·`모래놀이`·`대문놀이` 등 6건. **evidence가 강한 항목과 겹쳐 영향이 크다** |
| `INSTITUTION_SPECIFIC` | 유용 | 6건 |
| `TOO_GENERIC` | 신규 제안 | `SECTION_LABEL_LIKE`와 상당 부분 중복 → 통합 권장 |
| `NEEDS_HUMAN_REVIEW` | 유용 | 위 자동 판정 불가 항목의 귀착지 |

`[판단]` **결론: Label 품질은 자동 분류로 확정할 수 없다.** 후보 추출까지만 자동화하고
판정은 사람이 해야 한다.

### 7.3 §18 Activity Type Diversity `[실측]`

198개 label에 9개 type을 규칙 기반으로 태깅한 결과:

```
태그 0개(미분류) : 62 (31%)
태그 1개         : 85 (43%)
태그 2개 이상    : 51 (26%)
```

미분류 예 `[출처]`: `몸으로 글자를 만들어요`, `대문놀이`, `행운의 막대기`,
`꼭꼭 숨어라`, `신발을 던져요`.

`[판단]` **31% 미분류 + 26% 다중 태그 → 현재 label만으로는 안정적 분류가 불가능하다.**
§18의 지시("Corpus에서 안정적으로 분류 가능할 경우에만 vNext Feature 후보로 제안")에
따라 **Ranking Feature로 제안하지 않는다.** 단 §4 재현에서 `산책/나들이류 2/5` 같은
편중이 3개 Case에서 관찰되었으므로 **문제 자체는 실재한다** — 사람 태깅이 선행되어야
한다.

---

## 8. Age Evidence Analysis

### 8.1 현황 `[실측]`

| 연령 | supported item | single-age evidence 有 | mixed-only | Official Age Source |
|---|---:|---:|---:|---|
| 만 3세 | 179 | 102 | 77 | **없음** (`age3/` 빈 디렉터리) |
| 만 4세 | 100 | **4** | 96 | **없음** (`age4/` 빈 디렉터리) |
| 만 5세 | 100 | 20 | 80 | **2건** (이음교육 표준안·사례집) |

재현 52 Cell 중 **37건(71%)이 `AGE_EVIDENCE_WEAK`** 이다.

### 8.2 §13 독립축 설계 제안 `[판단]`

Official Evidence를 Institution Evidence에 **합산하지 않는다.** 서로 다른 축으로 둔다.

```
institution_single_age_support   : int   해당 연령 단일 age_scope evidence 수
institution_mixed_age_support    : int   해당 연령 포함 혼합 age_scope evidence 수
official_age_specific_support    : enum  PRESENT | ABSENT   (현재 만5만 PRESENT)
official_play_case_age_support   : enum  동일
official_topic_age_guidance      : enum  동일
```

표시 예시 (Product 표현 제안, Rule 변경 아님):

| 조합 | Age Fit Strength 표시 |
|---|---|
| single ≥ 2 | **직접 근거** |
| single = 1 | 직접 근거(제한적) |
| single = 0, mixed ≥ 1 | **혼합연령 문서 근거** — 해당 연령 단독 관찰 아님 |
| single = 0, mixed = 0 | 근거 없음 (현재 hard filter가 이미 배제) |
| + `official_age_specific_support = PRESENT` | 별도 배지로 병기. **합산하지 않음** |

`[판단]` 만4세는 거의 전부 "혼합연령 문서 근거"에 떨어진다. 이는 **데이터의 사실이며
숨기면 안 된다.** vNext는 이 사실을 사용자에게 드러내는 쪽이 맞다.

---

## 9. Topic Support Analysis

§5.1대로 Official Topic Support는 월 배치를 규정하지 않는다. 따라서 사용처는 셋 중
하나로 제한된다.

| 사용처 | 가능 여부 | 이유 |
|---|---|---|
| Ranking Feature (점수 가산) | **부적합** | Topic↔Activity 연결이 Source에 명시되어 있지 않다. 연결을 만들려면 LLM/상식 추론이 필요한데 §19가 금지한다 |
| Validation (선택 결과 검증) | **부분 가능** | "이 Theme에 이런 방향의 경험이 교육적으로 뒷받침되는가"를 사람이 검토할 때 유용 |
| Context (화면/문서 맥락 제공) | **가장 적합** | Theme 단위로 "관련 공식 자료" 링크 제공. Selection에 영향 없음 |

---

## 10. Monthly Content Model vNext Options

### 10.1 §15 명명 후보 비교 `[실측]` 기반

Corpus 원문 Label은 `소주제`·`예상놀이`·`예상 놀이`·`놀이흐름` 4종이다.

| 후보 | Corpus 지지 | 평가 |
|---|---|---|
| `WEEK_SUBTHEME` | `소주제` 1종만 대응 | Corpus 용어가 아님 |
| `WEEK_EXPERIENCE` | 직접 대응 원문 없음 | 의미는 넓으나 자료 어휘와 거리 |
| `EXPECTED_PLAY` | `예상놀이` 직접 대응 (최다) | Corpus 어휘에 가장 근접 |
| `PLAY_CONTEXT` | 없음 | 추상적 |
| `WEEK_FOCUS` | 없음 | 기존 `focus` semantic_key와 충돌 |

**제안** `[판단]`: OD-M03이 이미 채택한 방식 — **canonical + source_label 분리**를
그대로 확장한다.

```
canonical_semantic_key : monthly.week.<week>.expected_play
source_label           : 소주제 | 예상놀이 | 예상 놀이 | 놀이흐름   (원문 보존)
```

`canonical_semantic_key`를 지금 확정하지 말고 Human Decision으로 넘긴다.

### 10.2 §16 Week Experience 생성 방식 비교

| Option | 설명 | 장점 | 단점 / 위험 | 판정 |
|---|---|---|---|---|
| **A. Institution Rule Only** | 기관 Sample 관찰 Pattern만 사용 | Provenance 최강, CLAUDE.md §4 완전 부합 | Coverage가 6개월 MODERATE / 4개월 VERY_WEAK. 후보 0인 달 발생 | 채택 가능하나 단독으론 부족 |
| **B. Institution + Official 보강** | 관찰 Pattern이 후보의 핵심 근거, Official은 **검증·맥락** | A의 Provenance 유지 + 교육적 타당성 확인 | Official↔후보 연결을 사람이 해야 함 | **추천** |
| **C. Rule 선택 + LLM Wording** | Concept은 Rule이 결정, GPT-4.1 mini는 표현만 정리 | 표현 품질 개선 | Concept 자체는 여전히 A/B 필요. LLM 경계 관리 비용 | B의 **선택적 후단**으로만 |
| **D. Free LLM Generation** | 월 Theme만 보고 W1~W5 자유 생성 | 즉시 그럴듯한 결과 | **CLAUDE.md §4 정면 위반** — "Theme Reference 밖 자유 생성", "Rule이 선택한 내용의 최종 정책적 선택" 금지. Evidence·Provenance 소멸 | **금지** |

**추천: Option B** (필요 시 C를 표현층에만 한정 적용)

---

## 11. Recommended Model

```
MonthlyPlan
├── Theme                      (변경 없음 — 상위 Yearly anchor)
├── WeekPeriods                (변경 없음)
├── WeekExperience  [신규·Optional]   ← 주차별 경험/소주제. Evidence 없으면 비움
├── Outdoor                    (Week Context를 Ranking 입력으로 추가)
└── Safety                     (변경 없음 — §20)
```

**핵심 설계 원칙** `[판단]`

1. `WeekExperience`는 **Optional**이다. Coverage가 VERY_WEAK인 달(6·7·8·1월)에는
   후보가 없으므로 **비워 두고** `EMPTY_VALID`로 남긴다. 억지로 채우지 않는다.
2. Week Experience가 **있으면** Activity Ranking의 입력이 되고, **없으면** 현재
   M2-B Rule이 그대로 동작한다 → 완전한 Additive.
3. 고정 순서표(`7월 W1=여름 날씨…`)를 만들지 않는다. ORDER_SUPPORT가 WEAK이므로
   **월별 후보 집합**만 두고 주차 배정은 Rule이 한다.

---

## 12. Selection Rule vNext Proposal (§17)

| Feature | Corpus 근거 | 계산 가능 | 현재 데이터 有 | 분류 | 판정 |
|---|---|---|---|---|---|
| `parent_theme_match` | 강함 | ✅ | ✅ | Soft Rank | **MODIFY** — 만4·5세 9개월에서 변별력 0, 6월은 0/7로 붕괴. 유지하되 **Week Experience 뒤로 강등** |
| `week_experience_match` | 33문서 9기관 12개월 | ✅ | ❌ (Reference 없음) | Soft Rank | **ADD** — 단 Week Experience가 있을 때만 |
| `same_month_repeat` | — (제품 정책) | ✅ | ✅ | Soft Rank | **KEEP** — 정상 동작 확인 |
| `monthly_evidence_strength` | 강함 | ✅ | ✅ | Soft Rank | **MODIFY** — 현재 단순 개수. `SECTION_LABEL_LIKE` 항목이 최다 evidence를 갖는 왜곡이 실재(`전통놀이` ev=11) |
| `single_age_evidence_strength` | 만4세 4건 | ✅ | ✅ (`age_scope`) | Soft Rank | **ADD (낮은 가중)** — 만4세에서 거의 전부 0이라 축이 붕괴할 위험. 우선 **표시용**으로만 |
| `mixed_age_only_penalty` | 만4 96/100 | ✅ | ✅ | — | **DO NOT USE** — 만4세 후보의 96%를 벌주면 사실상 만4세 생성이 불가능해진다 |
| `official_play_case_support` | 연결이 Source에 없음 | ❌ | ❌ | — | **DO NOT USE** (§19) |
| `official_topic_support` | 월 배치 규정 0건 | ❌ | ❌ | Context only | **DO NOT USE as ranking** |
| `display_quality` | flag 24/198 | ✅ (사람 판정 후) | ❌ | Soft Rank | **ADD (사람 판정 선행)** — `SECTION_LABEL_LIKE` 강등이 가장 효과 큼 |
| `institution_specific_penalty` | 6건 잔존 | ✅ (사람 판정 후) | ❌ | Soft Rank | **ADD (낮은 가중)** |
| `activity_type_diversity` | 31% 미분류 | ❌ | ❌ | — | **보류** — 사람 태깅 선행 필요 |
| `source_independence` | Template Family 4곳 | ✅ | ✅ (origin_id) | Soft Rank | **ADD** — `evidence_strength`를 기관 독립성으로 보정 |

**제안 정렬 키 (설계만)**

```
① repeat_penalty                (KEEP)
② week_experience_penalty       (ADD — Week Experience 있을 때만)
③ display_quality_penalty       (ADD — 사람 판정 선행)
④ parent_theme_penalty          (MODIFY — 순위 강등)
⑤ curriculum_penalty            (KEEP — 여전히 중립)
⑥ -independent_evidence_strength (MODIFY — 기관 독립성 보정)
⑦ activity_id                   (KEEP)
```

---

## 13. Reference Changes Required (§24)

### Theme Reference → **`NO_CHANGE`**

전 세션 Full Corpus 재분석에서 12개월 전부 SUPPORTED, CONFLICTING 0. 본 분석에서도
변경 근거가 추가되지 않았다.

### Activity Reference → **`ADDITIVE_METADATA_REQUIRED`** (+ 데이터 수리)

`REBUILD_REQUIRED`가 아니다. 198개 중 174개는 `GOOD_STANDALONE`이고 evidence
lineage는 정상이다. 필요한 것은 필드 추가와 **국소 수리**다.

제안 필드 (설계만, JSON 생성 안 함):

```
display_label            : str | null    셀 표시용. null이면 label 사용
display_label_status     : RAW_ONLY | HUMAN_APPROVED
display_quality          : GOOD_STANDALONE | SECTION_LABEL_LIKE | CONTEXT_DEPENDENT
                         | TOO_SHORT | INSTITUTION_SPECIFIC | NEEDS_HUMAN_REVIEW
age_evidence_strength    : { age3: {single, mixed}, age4: {...}, age5: {...} }
source_independence      : { observed_institutions, possible_independent_sources }
official_support         : { play_case, topic, age_specific }  각 PRESENT|ABSENT
activity_type            : str | null    사람 태깅 전까지 null
merge_candidate_of       : activity_id | null   파서 분할 복원용
```

**국소 수리 대상** `[출처]` — 자동 수정 금지, 사람 판정 필요:

| 항목 | 문제 | 제안 |
|---|---|---|
| `건너기` + `장화 신고 물웅덩이` | wrap 분할 확정 | 병합 검토 → `장화 신고 물웅덩이 건너기` |
| `만들기` + `자연물로 여름 디저트` | 동일 줄 동일 구조 | 병합 검토 |
| `놀이를 해요.` | `?` 절단 확정 | `우리집에 왜 왔니? 놀이를 해요.` 복원 검토 |
| `가을담기` + `자연물 물감` | wrap 여부 불확실 | AMBIGUOUS — 원문 재확인 |
| `전통놀이` | category label | `display_quality = SECTION_LABEL_LIKE` 부여, Ranking 강등 |

### Week Experience Reference → **신규 필요 (설계만)**

```
month                            : int
age_scope                        : int[]        현재 데이터로는 대부분 [3,4,5]
experience_candidate             : str          원문 보존
source_label                     : str          소주제|예상놀이|놀이흐름
normalized_concept_candidate     : str[]        분석 태그. canonical 아님
observed_source_count            : int
institution_count                : int
possible_independent_source_count: int          Template Family 보정
observed_week_positions          : int[]        [1,2,3,4,5] 중 관찰된 위치
order_support                    : STRONG|WEAK|NONE
official_play_support            : PRESENT|ABSENT
official_topic_support           : PRESENT|ABSENT
```

**단 발행 전제 조건**: 현재 Coverage는 MODERATE 6개월 / WEAK 2개월 / VERY_WEAK 4개월.
**VERY_WEAK 4개월(6·7·8·1월)은 독립 source 1곳뿐**이라 발행하면 한 기관의 관행이
Reference가 된다. 추가 Corpus 확보가 선행되어야 한다.

---

## 14. Contract Impact (§23)

| Component | 영향 | 근거 |
|---|---|---|
| MonthlyPlan Domain | **ADDITIVE_CHANGE** | Section 추가는 Template instance data가 결정(OD-M01). Domain은 Section 목록을 데이터로 받는다 |
| Monthly DTO | **ADDITIVE_CHANGE** | `MonthlyGenerationRun`에 week experience trace 추가. 기존 필드 불변 |
| GenerateMonthlyPlan | **ADDITIVE_CHANGE** | `_fill_section`에 분기 추가. Week Experience Repository는 Optional 주입(M2-C와 동일 패턴) |
| EditMonthlyPlanItem | **NO_CHANGE** | Cell 주소 체계가 그대로 |
| RegenerateMonthlyPlanItem | **ADDITIVE_CHANGE** | `REGENERATABLE_SECTION_KEYS`에 항목 추가 시 |
| ConfirmMonthlyPlan | **NO_CHANGE** | |
| Cell Address | **NO_CHANGE** | `MonthlyCellAddress(target_month, section_key, week_id)`가 새 Section도 그대로 주소화 |
| CellState | **NO_CHANGE** | Week Experience 후보 0 → `EMPTY_VALID` (Outdoor와 동일 의미) |
| AuditTrail / Provenance | **NO_CHANGE** | 3축 구조 그대로. 새 `EvidenceSourceType`이 필요하면 그때만 추가 |
| Activity Catalog Lineage | **NO_CHANGE** | Week Experience Catalog는 별도 lineage 필드로 추가(Activity와 동일 패턴) |
| Golden Tests | **NO_CHANGE** | M1-D 43 케이스는 Week Experience Repository 미주입 시 동일 동작 |
| Demo View | **ADDITIVE_CHANGE** | 행 하나 추가 |

**BREAKING_CHANGE 0건.** 기존 Core Architecture를 유지한 채 Additive하게 확장 가능하다.

---

## 15. Before / After Simulation (§22)

> **After는 창작하지 않았다.** 현재 Corpus·Official Evidence로 후보를 뒷받침할 수
> 없으면 `INSUFFICIENT_EVIDENCE`로 표시했다.

### Case 1 — 2026-07 / 만3세 (사용자 보고 사례)

```
BEFORE
  Theme: 여름
  W1 우리 동네 분수대 가 보기
  W2 셀로판지로 여름 하늘 바라보기
  W3 건너기                      ← 파서 분할 절편
  W4 산책하며 여름 곤충 찾기
  W5 무인 아이스크림 매장 찾아가기

PROPOSED AFTER
  Theme: 여름
  W1~W5 Experience : INSUFFICIENT_EVIDENCE
      7월 Week Experience 독립 source = 1 (VERY_WEAK). Reference 발행 불가
  W3 Activity      : '건너기' → '장화 신고 물웅덩이 건너기' (파서 수리 후)
      Evidence: sample.monthly.uri.2026.07 p1, 원문 wrap 복원 [출처]
  기타 Activity    : 변경 없음 (후보 16개, 전부 ev=1)
  → 이 Case에서 vNext가 실제로 고치는 것은 W3 Label 하나뿐이다.
```

### Case 2 — 2026-05 / 만3세

```
BEFORE
  W1 산책하며 내가 좋아하는 색깔 자연물 찾기
  W2 돌멩이에 얼굴 표정 그리기
  W3 바람개비 들고 시원하게 달리기
  W4 놀이를 해요.                 ← 파서 절단

PROPOSED AFTER
  W1 Experience: 나/몸/마음    Evidence: 키즈로스쿨·혜솔 5월 소주제 (독립source 2)
  W2 Experience: 나/몸/마음    Evidence: 동일
  W3 Experience: 가족          Evidence: 3기관 독립source 3 [실측]
  W4 Experience: 가족          Evidence: 동일
  Activity W4  : '놀이를 해요.' → '우리집에 왜 왔니? 놀이를 해요.' (파서 수리 후)
  → 5월은 Week Experience Coverage가 MODERATE라 실제 적용 가능한 유일한 사례군
```

### Case 3 — 2026-09 / 만4세

```
BEFORE
  W1 무궁화 꽃이 피었습니다   ev月11 기관6
  W2 전통놀이                ev月10 기관6   ← category label
  W3 가을 나들이             ev月5  기관3
  W4 사방치기                ev月5  기관3
  W5 모래 위에 옛 그림을 그려요 ev月4 기관2

PROPOSED AFTER
  W1~W5 Experience: 전통/명절  Evidence: 9월 독립source 3 [실측] — 단일 concept뿐
      → 주차별 차별화 INSUFFICIENT_EVIDENCE
  W2 Activity: '전통놀이' display_quality=SECTION_LABEL_LIKE → 강등
      대체 후보: 강강술래(ev7/4기관) 또는 투호놀이(ev4) — 둘 다 기존 Catalog 항목
  → 이 Case의 개선은 display_quality 강등 하나로 달성된다
```

### Case 4 — 2026-11 / 만5세

```
BEFORE  후보 4개 · 주차 4개 → 사실상 나열
  W1 숲속 동물 보호소   W2 모래 뭉쳐서 지구 만들기
  W3 분리수거장 찾으며 산책하기   W4 집게로 쓰레기 줍기

PROPOSED AFTER
  Experience: 환경/자원 (독립source 2)
  Activity  : 변경 없음 — 후보가 주차 수와 같아 Ranking이 개입할 여지가 없다
  → INSUFFICIENT_CANDIDATES. Reference 확충 외에 해결책 없음
```

### Case 5 — 2026-03 / 만4세

```
BEFORE
  W1 모래놀이  ← SECTION_LABEL_LIKE
  W2 우리 반 꽃이 피었습니다
  W3 안전 약속 지키며 놀이기구 타기  ← SAFETY_ADJACENT
  W4 모래 위에 쓰인 우리 반 이름 찾기

PROPOSED AFTER
  Experience: 친구/우리반 (3월 독립source 2, WEAK)
  W1 Activity: '모래놀이' 강등 → 후보 8개 중 대체 가능
  → 부분 개선. 3월 Coverage가 WEAK이라 Experience 적용은 조건부
```

### Case 6 — 2027-02 / 만5세

```
BEFORE
  W1 우리가 좋아했던 장소 산책하기   W2 사방치기
  W3 모래 위에 형님이 된 내 모습 그리기   W4 산책하며 동네 이웃에게 설날 인사드리기
  ! REPETITIVE_ACTIVITY_TYPE — 산책류 2/4

PROPOSED AFTER
  Experience: 성장/전이 — 독립source 1 (VERY_WEAK) → INSUFFICIENT_EVIDENCE
  Activity  : 후보 4개로 고갈. type diversity 개입 불가 (§7.3)
  Official  : age5_transition 2건 존재 → 만5세 한정 Context 제공 가능
  → 유일하게 Official Age Evidence를 쓸 수 있는 Case
```

**시뮬레이션 총평** `[판단]`: 6 Case 중 Week Experience를 **실제로 적용할 수 있는 것은
2개(5월·3월 조건부)** 뿐이다. 나머지는 Coverage 부족 또는 후보 고갈이다.
**반면 display_quality 수리는 6 Case 중 4개에서 즉시 효과가 있다.**

---

## 16. License / Provenance Constraints (§26)

Official Source 6종의 1~4p 및 전문에서 공공누리 유형 표기를 탐색한 결과
**표기를 찾지 못했다** `[실측]`.

| Source | license_type | commercial_use | modification | direct_text_reuse | analysis |
|---|---|---|---|---|---|
| 놀이 쏙 경제금융 톡 | 미확인 (발간등록번호 11-1342357-100006-01) | 미확인 | 미확인 | **NOT_CONFIRMED** | ALLOWED |
| 유아의 균형 있는 디지털 역량 | 미확인 | 미확인 | 미확인 | **NOT_CONFIRMED** | ALLOWED |
| 따뜻한 말 한마디 따뜻한 행동 하나 | 미확인 | 미확인 | 미확인 | **NOT_CONFIRMED** | ALLOWED |
| 지속가능발전 기반 유아환경교육 | 미확인 | 미확인 | 미확인 | **NOT_CONFIRMED** | ALLOWED |
| 2025 5세 이음교육 표준안 | 미확인 (JNE2025-100000001-001444) | 미확인 | 미확인 | **NOT_CONFIRMED** | ALLOWED |
| KICCE 유아관찰척도(2021) | 미확인 | 미확인 | 미확인 | **NOT_CONFIRMED** | ALLOWED |

**판정: 전 Official Source = `EVIDENCE_ANALYSIS_ALLOWED` + `PRODUCT_TEXT_REUSE_NOT_CONFIRMED`**

§26대로 License가 불확실하면 허용으로 추정하지 않는다. 따라서 **Official 문구를
Product Reference에 직접 복제하는 설계를 제안하지 않는다.** Official은 (a) 분석 근거,
(b) Theme 단위 "관련 자료" 링크 Context로만 쓴다.

Institution Sample은 기존 규칙 유지 — 원문 전체 복제 금지, evidence lineage로만 참조.

---

## 17. Open Decisions

| ID | 결정 필요 사항 | 차단 대상 |
|---|---|---|
| OD-V01 | Week Experience의 `canonical_semantic_key` 명칭 확정 | Week Experience Reference 발행 |
| OD-V02 | VERY_WEAK 4개월(6·7·8·1월)을 어떻게 처리할지 — 비워 둘 것인가 / Corpus 확충 대기 | 동일 |
| OD-V03 | `display_label` 도입 시 Provenance 표기 방식 (원문 보존 위치) | Activity Reference 확장 |
| OD-V04 | 파서 분할 4건의 병합/복원 판정 (사람 판정) | Activity Reference 수리 |
| OD-V05 | `전통놀이` 같은 category label의 처리 — 강등인가 제외인가 | Selection Rule vNext |
| OD-V06 | Official Source의 공공누리 유형 확인 (발행처 문의) | Product 내 문구 사용 여부 |
| OD-V07 | `activity_type` 사람 태깅 수행 여부와 범위 | Type Diversity Feature |
| OD-V08 | 만4세 단일연령 Corpus 확보 계획 | Age Fit 표시 신뢰도 |

---

## 18. Implementation Recommendation

**구현 순서 제안 (이번 작업에서 구현하지 않음)**

| 단계 | 내용 | 선행 조건 | 아키텍처 위험 |
|---|---|---|---|
| 1 | 파서 분할 4건 사람 판정 + Activity Reference 국소 수리 | OD-V04 | 없음 (데이터만) |
| 2 | `display_quality` / `display_label` 필드 추가 + 24건 사람 판정 | OD-V03, OD-V05 | 낮음 (Additive metadata) |
| 3 | Selection Rule에 `display_quality_penalty` 축 추가 | 2 완료 | 낮음 (Soft Rank 1축) |
| 4 | `source_independence` 보정을 `evidence_strength`에 반영 | — | 낮음 |
| 5 | Week Experience Reference 발행 (MODERATE 6개월 한정) | OD-V01, OD-V02 | 중간 (Template A Section 추가) |
| 6 | Week Experience를 Ranking 입력으로 연결 | 5 완료 | 중간 |

---

# 마지막 1페이지 요약

```
MONTHLY V1

잘 되어 있는 것:
- Generate → Edit → Regenerate → Confirm → Weekly Gate 전 구간이 실제로 동작한다
- Hard Filter 6조건이 코드에 명확하고 승인 Gate 우회 경로가 없다
- M2-B Ranking이 의도대로 동작한다 (repeat 회피는 52 Cell에서 정상 확인)
- Provenance 3축 / Audit / Catalog version pinning이 정확하다
- Safety EMPTY_UNRESOLVED 의미가 정확하고 임의로 채우지 않는다
- BREAKING_CHANGE 없이 확장 가능한 구조다

부족한 것:
- 월 Theme와 Activity 사이에 주차 의미 축이 없다 (Corpus 96% 문서는 주차 축 보유)
- theme 축이 만4·5세 9개월에서 변별력 0, 6월은 0/7로 붕괴 → 실질 기준이 evidence 개수뿐
- Activity label 일부가 파서 분할 절편이다 (건너기·놀이를 해요. 확정)
- category label(전통놀이 ev=11)이 최강 evidence로 상위에 온다
- 만4세 single-age evidence 4건, 재현 Cell 71%가 AGE_EVIDENCE_WEAK
- 11월·2월은 후보 4개 = 주차 4개로 선택 자체가 성립하지 않는다


MONTHLY vNEXT

추가해야 하는 것:
- Activity Reference: display_label / display_quality / age_evidence_strength /
  source_independence / merge_candidate_of  (ADDITIVE_METADATA)
- Selection Rule: display_quality_penalty, independent_evidence 보정
- Week Experience Section (Optional, Coverage MODERATE 월 한정)
- Week Experience Reference (설계만 완료, 발행은 Corpus 확충 후)

유지해야 하는 것:
- Hard Filter 6조건 전부
- repeat_penalty, curriculum_penalty, activity_id tie-break
- Provenance 3축, Audit, Catalog version pinning
- Theme Reference v0.1.2 (NO_CHANGE)
- Rule/LLM 경계 — Concept은 Rule, LLM은 표현만

건드리면 안 되는 것:
- Safety EMPTY_UNRESOLVED 의미 (§20)
- SafetyLegalRule
- Golden M1-D 43 / Yearly 22
- Cell Address / CellState 의미
- Official 문구의 Product 직접 복제 (License 미확인)
- mixed_age_only_penalty (만4세 96%를 벌주면 생성 불가)


TOP 3 CHANGES

1. 파서 분할 Activity 수리 + display_quality 도입
   Impact 높음 / Cost 낮음(데이터+필드) / Risk 낮음 / Evidence 확정(원문 대조)
   → 6 Case 중 4개에서 즉시 효과

2. Selection Rule에 display_quality_penalty 축 추가
   Impact 높음 / Cost 낮음(Soft Rank 1축) / Risk 낮음 / Evidence 강함
   → 전통놀이·모래놀이 같은 category label 상위 노출 제거

3. Week Experience Section 추가 (MODERATE 6개월 한정, Optional)
   Impact 매우 높음 / Cost 중간(Template A Section + Reference 발행) /
   Risk 중간 / Evidence 중간(6개월만 MODERATE)
   → 근본 원인 해결이나 4개월은 INSUFFICIENT_EVIDENCE로 남는다


REFERENCE CHANGES

Theme Reference:
- NO_CHANGE

Activity Reference:
- ADDITIVE_METADATA_REQUIRED (REBUILD 아님)
- 국소 수리 4건 (사람 판정 선행)

Week Experience Reference:
- 신규 필요, 설계만 완료
- 발행 전제: VERY_WEAK 4개월(6·7·8·1월) Corpus 확충


IMPLEMENTATION IMPACT

Domain:
- ADDITIVE_CHANGE (Section은 Template instance data가 결정)

Use Case:
- GenerateMonthlyPlan ADDITIVE / Regenerate ADDITIVE
- Edit·Confirm NO_CHANGE

Selection Rule:
- KEEP 3축 · MODIFY 2축 · ADD 2~3축 · DO_NOT_USE 3축

Demo:
- ADDITIVE_CHANGE (행 1개 추가)

Tests:
- Golden NO_CHANGE (Repository 미주입 시 동일 동작)
- 신규 Section용 테스트 추가 필요


READINESS

NEEDS_MORE_EVIDENCE

이유:
- Week Experience Coverage가 MODERATE 6개월 / WEAK 2개월 / VERY_WEAK 4개월이다.
  4개월은 독립 source 1곳뿐이라 지금 Reference로 발행하면 한 기관 관행이
  국가 표준처럼 굳는다.
- 연령별 Week Experience 차이를 뒷받침할 데이터가 사실상 없다
  (Coverage Matrix의 만3/4/5 열이 거의 동일).
- Official Source의 License 유형이 전부 미확인이다.
- activity_type 자동 분류가 31% 미분류 / 26% 다중태그로 불안정하다.

단, TOP 3 CHANGES의 1·2번(파서 수리 + display_quality)은
추가 Evidence 없이 지금 착수 가능하며 위험이 가장 낮다.
```

---

## 최종 질문 답변 (§27)

**Q1. 현재 Monthly가 어색한 가장 큰 원인 (우선순위 재산정)**

| 순위 | 원인 | 근거 |
|---|---|---|
| 1 | **주차 의미 축 부재** | Corpus 96% 주차 축 보유 / 45%가 별도 경험 행. Production에 층 자체가 없음 |
| 2 | **Ranking의 실질 기준이 evidence 개수뿐** | 52 Cell 전부 theme_matched=True. 만4·5세 9개월 변별력 0, 6월 0/7 붕괴 |
| 3 | **Activity label 파서 결함** | `건너기`·`놀이를 해요.` 원문 대조로 확정. 한 활동의 양쪽 절반이 모두 등재 |
| 4 | **후보 고갈** | 11월·2월 만5세 후보 4개 = 주차 4개 |
| 5 | **만4세 age evidence** | single 4건, 재현 Cell 71% WEAK |

전 세션 대비 변화: **②(Ranking 실질 기준)와 ③(파서 결함)이 새로 확정**되었다. 이전에는
"Ranking Rule NOT_SUPPORTED"로 판정했는데, 이번에 theme 축의 무력화를 실측으로 확인해
**Rule 자체가 아니라 축의 변별력 문제**임이 드러났다.

**Q2. Week Experience를 Monthly Contract에 추가할 근거 → `YES_WITH_LIMITATIONS`**

YES 근거: 9기관 33문서 12개월 관찰, 원문 Label 4종 존재, 문서 내 전개 확인 `[출처]`,
Additive 확장 가능(BREAKING 0).
LIMITATIONS: Coverage MODERATE 6개월뿐, ORDER_SUPPORT WEAK, 연령 차이 데이터 없음,
독립 source 최대 3.

**Q3. Coverage Matrix** — §6.5 표 참조. MODERATE 6 / WEAK 2 / VERY_WEAK 4.
**12개월 × 연령별 Rule Candidate를 만들 Coverage는 없다.** 월별 후보 집합까지만 가능.

**Q4. Activity Reference v0.2.0 → `ADDITIVE_METADATA_REQUIRED`**
174/198이 정상이고 lineage도 정상이다. REBUILD 불필요, V0_3도 지금은 불필요.
필드 추가 + 국소 수리 4건으로 충분하다.

**Q5. M2-B Selection Rule** — §12 표 참조.
KEEP 3 (`repeat`, `curriculum`, `id`) / MODIFY 2 (`theme` 강등, `evidence_strength`
독립성 보정) / ADD 2~3 (`week_experience`, `display_quality`, `institution_specific`) /
DO_NOT_USE 3 (`official_*`, `mixed_age_only_penalty`).
**폐기 대상 없음.**

**Q6. `건너기` 원인 → `PARSER_PROBLEM` (확정)**

| 사례 | 판정 | 원문 근거 |
|---|---|---|
| `건너기` | **PARSER_PROBLEM** | `장화 신고 물웅덩이` / `건너기` 2줄 wrap. 양쪽 절반이 모두 등재 |
| `놀이를 해요.` | **PARSER_PROBLEM** | `우리집에 왜 왔니? 놀이를 해요.`가 `?`에서 절단 |
| `전통놀이` | **MULTIPLE_CAUSES** (REFERENCE + DISPLAY) | 6개 표현이 공통 어간으로 정규화되어 category가 최강 evidence 획득 |
| `가을담기` | **AMBIGUOUS** | wrap 여부 원문만으로 확정 불가 |

**Q7. 만3·4·5 차별화 가능 수준**

| 연령 | Institution single-age | Official Age Source | 현재 가능한 차별화 |
|---|---:|---|---|
| 만3 | 102/179 | 없음 | **부분 가능** — 후보 pool이 만4·5보다 넓음(9월 37 vs 31/27) |
| **만4** | **4/100** | **없음** | **사실상 불가능** — 만3·5 사이에 낀 혼합 문서 근거뿐 |
| 만5 | 20/100 | **2건 (이음교육)** | **부분 가능** — 유일하게 Official Age Evidence 보유 |

만4세는 Institution도 Official도 근거가 없다. **현재 Evidence로는 만4세 전용
Monthly 차별화를 만들 수 없고, 만들면 근거 없는 창작이 된다.**

**Q8. Official Topic Support를 Ranking에 직접 사용해야 하는가 → `CONTEXT_ONLY`**

근거: (a) 5개 문서 전수에서 월 배치 규정 0건, (b) Topic↔Activity 연결이 Source에
명시되어 있지 않아 연결 자체가 추론이며 §19가 금지, (c) License 미확인으로 문구
사용 불가. `VALIDATION_ONLY`는 사람 검토 시 유용하므로 부차적으로 허용 가능하나,
`RANKING_FEATURE`는 부적합하다.

**Q9. 가장 적은 변경으로 가장 큰 효과 3가지**

| Change | Expected Impact | Implementation Cost | Architecture Risk | Evidence Strength |
|---|---|---|---|---|
| 1. 파서 분할 수리 + display_quality 필드 | **높음** (6 Case 중 4) | **낮음** (데이터 + 필드) | **낮음** | **확정** (원문 대조) |
| 2. display_quality_penalty 축 추가 | **높음** | 낮음 (Soft Rank 1축) | 낮음 | 강함 (24/198 후보) |
| 3. Week Experience Section (6개월 한정) | **매우 높음** | 중간 | 중간 | 중간 (MODERATE 6개월) |

**Q10. 추천 최종 Monthly Generation Flow**

```
Confirmed Yearly Theme
        ↓
Month + Age + WeekPeriods
        ↓
Week Experience Candidate Resolution        [신규 · Optional]
   ├─ Reference 있음 → Week Context 확보
   └─ 없음/후보 0   → Week Context 없음 (EMPTY_VALID, 실패 아님)
        ↓
Activity Candidate Hard Filter              [변경 없음 — 6조건]
        ↓
Activity Ranking                            [축 재구성]
   ① repeat_penalty
   ② week_experience_penalty   (Week Context 있을 때만 활성)
   ③ display_quality_penalty   (사람 판정 선행)
   ④ parent_theme_penalty      (강등)
   ⑤ curriculum_penalty
   ⑥ -independent_evidence_strength
   ⑦ activity_id
        ↓
Display Label Resolution                    [신규 · display_label 있으면 사용]
        ↓
Safety Cell                                 [변경 없음 — EMPTY_UNRESOLVED]
        ↓
Monthly DRAFT
```

Week Context가 없으면 ②가 전 후보에 중립이 되어 **현재 M2-B와 동일하게 동작한다** —
이것이 Additive를 보장하는 핵심이다.

---

## 부록. 방법과 한계

**사용** — Production 코드 직접 읽기 · `eligible_candidates`/`select_activity_for_cell`
직접 호출 재현 · `pdftotext -layout` 원문 대조 · regex · counting · 6-gram Jaccard
(전 세션 Template Family 결과 재사용).

**하지 않은 것** — Production 수정 · Reference 생성 · LLM 원문 보정 · Week Experience
추론 생성 · Activity semantic merge · 연령 추정 · Official 문구 복제.

**한계** `[판단]`
1. Week Experience 추출기는 `소주제` 계열 Label 행만 읽는다. 혜솔의 기간 행 혼입을
   날짜 패턴으로 걸렀으나, Label 없이 배치만으로 표현된 주차 경험은 놓친다.
2. 파서 분할 자동 탐색은 wrap과 세로 나열 목록을 구분하지 못해 대량 오탐했다.
   확정된 4건은 **수동 원문 대조**로만 판정했다.
3. `normalized_concept_candidate` 14종은 분석용 태그이며 Canonical이 아니다.
4. License는 PDF 내부 표기만 확인했다. 발행처 공식 고지는 확인하지 못했다.
5. `activity_type` 분류는 31% 미분류로 신뢰할 수 없다.
```
