# Monthly v1 + Activity Reference v0.2.1 — Demo Quality Verification

- 작성일: 2026-09-13
- 대상: Monthly v1 (Rule `monthly.activity.reference_candidate_selection` **v2**)
  + Activity Reference `activity-reference-v0.2.1` (`HUMAN_APPROVED`, Production/Demo default)
- 성격: **관찰 보고서.** 코드 · Reference · Rule을 **수정하지 않았다.**
  새 Rule / Week Experience / Reference를 만들지 않았고, 결과를 보기 좋게 고치지 않았다.
- 실행 도구: `analysis/experiments/monthly_vnext/observe_v0_2_1_quality.py` (읽기 전용)
- 원본 기록: `analysis/tmp/monthly_v0_2_1_quality.json`

실행 경로는 Production Composition(`build_monthly_wiring`)이 조립한 실제
`GenerateMonthlyPlan` Use Case다. Fake Catalog · Mock · Fixture 결과를 쓰지 않았다.
12 Case 전부 `llm_invoked = False`, `activity_catalog.version = activity-reference-v0.2.1`,
`rule_version = v2`다.

---

## 1. 12 Case 전체 결과

### 1.1 만3세

#### 2026-03 만3세 — Theme `우리 원과 친구` (`yr_theme_new_environment_friends`)

주차 4 · 후보 pool 15

| W | Activity | activity_id | ev | theme_match | display_quality | trace |
|---|---|---|---:|---|---|---|
| W1 | 엉덩이 씨름 | `act_outdoor_bottom_wrestling` | 2 | True | GOOD_STANDALONE / UNREVIEWED | `MATCHED_PARENT_THEME` |
| W2 | 바깥 놀이터 사진을 찍어요 | `act_outdoor_playground_photo` | 2 | True | **INSTITUTION_SPECIFIC** / AUTO_CANDIDATE | `AVOIDED_REPEAT_IN_MONTH` |
| W3 | 바깥 놀이터에서 지켜야 할 약속을 정해요 | `act_outdoor_playground_rules` | 2 | True | **INSTITUTION_SPECIFIC** / AUTO_CANDIDATE | `AVOIDED_REPEAT_IN_MONTH` |
| W4 | 모래놀이 | `act_outdoor_sand_play` | 2 | True | GOOD_STANDALONE / HUMAN_CONFIRMED | `AVOIDED_REPEAT_IN_MONTH` |

penalty는 4칸 모두 `repeat=0, display=0, curriculum=0`.

#### 2026-07 만3세 — Theme `여름` (`yr_theme_summer`)

주차 5 · 후보 pool 15

| W | Activity | activity_id | ev | theme_match | display_quality | trace |
|---|---|---|---:|---|---|---|
| W1 | 장화 신고 물웅덩이 건너기 | `act_outdoor_v021_f13eaab140` | 2 | True | GOOD_STANDALONE / HUMAN_CONFIRMED | `MATCHED_PARENT_THEME` |
| W2 | 우리 동네 분수대 가 보기 | `act_outdoor_v2_30ad6621c8` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W3 | 셀로판지로 여름 하늘 바라보기 | `act_outdoor_v2_3766bbd12a` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W4 | 산책하며 여름 곤충 찾기 | `act_outdoor_v2_4bdba888a5` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W5 | 무인 아이스크림 매장 찾아가기 | `act_outdoor_v2_5f623ffded` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |

#### 2026-09 만3세 — Theme `우리나라와 세계 여러 나라` (`yr_theme_korea_and_world_cultures`)

주차 5 · 후보 pool 37

| W | Activity | activity_id | ev | theme_match | display_quality | trace |
|---|---|---|---:|---|---|---|
| W1 | 무궁화 꽃이 피었습니다 | `act_outdoor_mugunghwa_flower_game` | 11 | True | GOOD_STANDALONE / UNREVIEWED | `MATCHED_PARENT_THEME` |
| W2 | 강강술래 | `act_outdoor_ganggangsullae` | 7 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W3 | 가을 나들이 | `act_outdoor_autumn_outing` | 5 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W4 | 사방치기 | `act_outdoor_sabangchigi` | 5 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W5 | 모래 위에 옛 그림을 그려요 | `act_outdoor_sand_old_painting` | 4 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |

#### 2026-11 만3세 — Theme `환경과 생활` (`yr_theme_environment_and_life`)

주차 4 · 후보 pool 11

| W | Activity | activity_id | ev | theme_match | display_quality | trace |
|---|---|---|---:|---|---|---|
| W1 | 스카프가 바람을 만났어요 | `act_outdoor_v2_cc6b7c4d1b` | 2 | True | GOOD_STANDALONE / UNREVIEWED | `MATCHED_PARENT_THEME` |
| W2 | 숲속 동물 보호소 | `act_outdoor_v2_084a5cf48c` | 1 | True | **INSTITUTION_SPECIFIC** / AUTO_CANDIDATE | `AVOIDED_REPEAT_IN_MONTH` |
| W3 | 모래 뭉쳐서 지구 만들기 | `act_outdoor_v2_13c475aec0` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W4 | 분리수거장 찾으며 산책하기 | `act_outdoor_v2_684f5c6064` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |

### 1.2 만4세

#### 2026-04 만4세 — Theme `봄` (`yr_theme_spring`)

주차 5 · 후보 pool 9

| W | Activity | activity_id | ev | theme_match | display_quality | trace |
|---|---|---|---:|---|---|---|
| W1 | 화단에 물주기 | `act_outdoor_v2_0552b9d114` | 1 | True | GOOD_STANDALONE / UNREVIEWED | **`TIE_BREAK_STABLE_ACTIVITY_ID`** |
| W2 | 모래로 개미집 만들기 | `act_outdoor_v2_0fa9b4fe28` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W3 | 벚꽃 비 흩날리기 | `act_outdoor_v2_484e9fa4f9` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W4 | 산책하며 새싹 찾기 | `act_outdoor_v2_5b4109a6c0` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W5 | 봄의 곤충 사진 찍기 | `act_outdoor_v2_5f439d4408` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |

#### 2026-06 만4세 — Theme `우리 동네` (`yr_theme_our_neighborhood`)

주차 4 · 후보 pool 7

| W | Activity | activity_id | ev | theme_match | display_quality | trace |
|---|---|---|---:|---|---|---|
| W1 | 우리 동네에서 일하는 분 찾아보기 | `act_outdoor_v2_069a02d595` | 1 | **False** | GOOD_STANDALONE / UNREVIEWED | **`TIE_BREAK_STABLE_ACTIVITY_ID`** |
| W2 | 분필로 내가 되고 싶은 직업 그림 그리기 | `act_outdoor_v2_0b2bfc3786` | 1 | **False** | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W3 | 꿈을 실은 종이비행기 날리기 | `act_outdoor_v2_4fa32af3ab` | 1 | **False** | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W4 | 병원에서 사용하는 물건 그림 찾기 | `act_outdoor_v2_58e5bfb861` | 1 | **False** | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |

#### 2026-08 만4세 — Theme `교통기관` (`yr_theme_transportation`)

주차 4 · 후보 pool 7

| W | Activity | activity_id | ev | theme_match | display_quality | trace |
|---|---|---|---:|---|---|---|
| W1 | 모래놀이 | `act_outdoor_sand_play` | 1 | True | GOOD_STANDALONE / HUMAN_CONFIRMED | **`TIE_BREAK_STABLE_ACTIVITY_ID`** |
| W2 | 내비게이션으로 길 찾기 | `act_outdoor_v2_04ebd8cb61` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W3 | 안전 관련 표지판 찾아보며 산책하기 | `act_outdoor_v2_1cffee74db` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W4 | 기찻길 만들기 | `act_outdoor_v2_405530e29b` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |

#### 2026-12 만4세 — Theme `겨울` (`yr_theme_winter`)

주차 5 · 후보 pool 7

| W | Activity | activity_id | ev | theme_match | display_quality | trace |
|---|---|---|---:|---|---|---|
| W1 | 눈으로 모양 만들기 | `act_outdoor_v2_1c25e6e384` | 1 | True | GOOD_STANDALONE / UNREVIEWED | **`TIE_BREAK_STABLE_ACTIVITY_ID`** |
| W2 | 산책하며 겨울바람 느끼기 | `act_outdoor_v2_2bc64cbc4c` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W3 | 우리 동네 겨울 음식 찾기 | `act_outdoor_v2_477a18a80f` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W4 | 겨울나무에 크리스마스 장식하기 | `act_outdoor_v2_47afb951a3` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W5 | 산타 굴뚝 통과하기 | `act_outdoor_v2_a9453d3d71` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |

### 1.3 만5세

#### 2026-05 만5세 — Theme `나와 가족` (`yr_theme_self_and_family`)

주차 4 · 후보 pool 8

| W | Activity | activity_id | ev | theme_match | display_quality | trace |
|---|---|---|---:|---|---|---|
| W1 | 산책하며 내가 좋아하는 색깔 자연물 찾기 | `act_outdoor_v2_30126d803b` | 2 | True | GOOD_STANDALONE / UNREVIEWED | **`TIE_BREAK_STABLE_ACTIVITY_ID`** |
| W2 | 돌멩이에 얼굴 표정 그리기 | `act_outdoor_v2_468020296d` | 2 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W3 | 바람개비 들고 시원하게 달리기 | `act_outdoor_pinwheel_running` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W4 | 다양한 가족 그림 보물찾기 | `act_outdoor_v2_73858de68d` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |

#### 2026-09 만5세 — Theme `우리나라와 세계 여러 나라` (`yr_theme_korea_and_world_cultures`)

주차 5 · 후보 pool 27

| W | Activity | activity_id | ev | theme_match | display_quality | trace |
|---|---|---|---:|---|---|---|
| W1 | 무궁화 꽃이 피었습니다 | `act_outdoor_mugunghwa_flower_game` | 11 | True | GOOD_STANDALONE / UNREVIEWED | `MATCHED_PARENT_THEME` |
| W2 | 강강술래 | `act_outdoor_ganggangsullae` | 7 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W3 | 가을 나들이 | `act_outdoor_autumn_outing` | 5 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W4 | 사방치기 | `act_outdoor_sabangchigi` | 5 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W5 | 동대문 놀이 | `act_outdoor_dongdaemun_nori` | 3 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |

#### 2027-01 만5세 — Theme `생활도구` (`yr_theme_living_tools`)

주차 4 · 후보 pool 8

| W | Activity | activity_id | ev | theme_match | display_quality | trace |
|---|---|---|---:|---|---|---|
| W1 | 모래놀이 | `act_outdoor_sand_play` | 1 | True | GOOD_STANDALONE / HUMAN_CONFIRMED | **`TIE_BREAK_STABLE_ACTIVITY_ID`** |
| W2 | 로봇 그림 보물찾기 | `act_outdoor_v2_05616c3afa` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W3 | 산책하며 궁금한 점 미디어로 알아보기 | `act_outdoor_v2_08bc8ae805` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W4 | 모래 위에 다양한 미디어 그림 그리기 | `act_outdoor_v2_1d042c27ef` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |

#### 2027-02 만5세 — Theme `성장한 우리` (`yr_theme_growth_and_transition`)

주차 4 · 후보 pool **4**

| W | Activity | activity_id | ev | theme_match | display_quality | trace |
|---|---|---|---:|---|---|---|
| W1 | 우리가 좋아했던 장소 산책하기 | `act_outdoor_v2_9d7e335dfc` | 2 | True | GOOD_STANDALONE / UNREVIEWED | `STRONGER_MONTH_EVIDENCE` |
| W2 | 사방치기 | `act_outdoor_sabangchigi` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W3 | 모래 위에 형님이 된 내 모습 그리기 | `act_outdoor_v2_8e63170058` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |
| W4 | 산책하며 동네 이웃에게 설날 인사드리기 | `act_outdoor_v2_8efc7cc703` | 1 | True | GOOD_STANDALONE / UNREVIEWED | `AVOIDED_REPEAT_IN_MONTH` |

### 1.4 요약표

| 월 | 연령 | 주차 | pool | theme_match | 중복 label | evidence_strength | 단일기관 | Fragment |
|---|---|---:|---:|---|---:|---|---:|---:|
| 2026-03 | 만3 | 4 | 15 | 4/4 | 0 | `[2,2,2,2]` | 3 | 0 |
| 2026-07 | 만3 | 5 | 15 | 5/5 | 0 | `[2,1,1,1,1]` | 5 | 0 |
| 2026-09 | 만3 | 5 | 37 | 5/5 | 0 | `[11,7,5,5,4]` | 0 | 0 |
| 2026-11 | 만3 | 4 | 11 | 4/4 | 0 | `[2,1,1,1]` | 3 | 0 |
| 2026-04 | 만4 | 5 | 9 | 5/5 | 0 | `[1,1,1,1,1]` | 5 | 0 |
| 2026-06 | 만4 | 4 | 7 | **0/4** | 0 | `[1,1,1,1]` | 4 | 0 |
| 2026-08 | 만4 | 4 | 7 | 4/4 | 0 | `[1,1,1,1]` | 3 | 0 |
| 2026-12 | 만4 | 5 | 7 | 5/5 | 0 | `[1,1,1,1,1]` | 5 | 0 |
| 2026-05 | 만5 | 4 | 8 | 4/4 | 0 | `[2,2,1,1]` | 1 | 0 |
| 2026-09 | 만5 | 5 | 27 | 5/5 | 0 | `[11,7,5,5,3]` | 0 | 0 |
| 2027-01 | 만5 | 4 | 8 | 4/4 | 0 | `[1,1,1,1]` | 3 | 0 |
| 2027-02 | 만5 | 4 | **4** | 4/4 | 0 | `[2,1,1,1]` | 2 | 0 |

---

## 2. 평가 기준별 관찰

### 2.1 Activity 자체가 자연스러운가 — **대체로 그렇다. 예외가 있다**

55개 Cell 중 조각·잘린 label은 **0건**이다. 대부분 `-기` / `-요` / 명사로 끝나는 완결된
활동명이다.

다만 세 종류가 눈에 띈다.

| 유형 | 사례 | 문제 |
|---|---|---|
| 지나치게 일반적 | `모래놀이` (3·8·1월에 각각 등장) | 활동명이 아니라 활동 범주다. 어느 달에 놓아도 말이 되므로 계획으로서 정보량이 없다 |
| 기관 고유 맥락 | `바깥 놀이터 사진을 찍어요`, `바깥 놀이터에서 지켜야 할 약속을 정해요`, `숲속 동물 보호소` | Catalog가 `INSTITUTION_SPECIFIC`으로 자동 표시한 항목이 그대로 출력에 나왔다 |
| 연령/시기 부적합 의심 | 2026-03 만3세 W1 `엉덩이 씨름` | 학년도 첫 주, 만 3세 첫 등원 주간의 바깥놀이로는 무리가 있어 보인다. 다만 이는 **주관적 판단**이며 Rule이 위반한 것은 없다 |

`INSTITUTION_SPECIFIC` 3건이 출력에 나온 것은 **설계대로 동작한 결과**다. Patch 1에서
`AUTO_CANDIDATE`는 runtime 중립으로 정했고 penalty는 `HUMAN_CONFIRMED`에만 적용된다.
자동 탐지 9건 중 사람 검토를 거친 것은 아직 `전통놀이` 하나뿐이다.

### 2.2 Theme와 관련 있는가 — **53칸 중 49칸 True. 그러나 축의 실효성은 낮다**

`theme_matched`는 49/53이고, 붕괴한 Case는 **2026-06 만4세 하나(0/4)**다.

그런데 이 수치는 실제보다 후하다. 이유가 두 가지다.

1. **`theme_links`가 없는 Activity가 196개 중 51개(26%)다.** 그 항목은 theme 축에서
   penalty를 받지도 가점을 받지도 않는다. 2026-06 만4세는 **후보 pool 7개 전부가
   `theme_links = []`**여서 축 전체가 무력화됐다.
2. **`theme_links`가 넓은 Activity는 어느 달에나 붙는다.** `모래놀이`는 theme_links 4개
   (`새 환경과 친구` / `가을과 자연` / `생활도구` / `교통기관`)를 갖고 있어 3월·8월·1월에
   모두 `theme_matched=True`로 통과했다. 「교통기관」 달의 `모래놀이`가 주제와 관련 있다고
   보기는 어렵다.

즉 `theme_matched=True`는 "주제에 맞다"가 아니라 "주제와 모순되지 않는다"에 가깝다.

### 2.3 W1~W5가 서로 지나치게 중복되는가 — **같은 달 안에서는 중복 0. 달을 넘으면 반복된다**

같은 달 안의 label 중복은 12 Case 모두 **0건**이다. `repeat penalty`가 의도대로 작동한다.

문제는 **월 간 반복**이다. repeat penalty는 같은 달 안에서만 계산되므로 축 자체가 없다.

| 반복 | Activity | 등장 Case |
|---:|---|---|
| 3회 | `모래놀이` | 2026-03/만3, 2026-08/만4, 2027-01/만5 |
| 3회 | `사방치기` | 2026-09/만3, 2026-09/만5, 2027-02/만5 |
| 2회 | `무궁화 꽃이 피었습니다` | 2026-09/만3, 2026-09/만5 |
| 2회 | `강강술래` | 2026-09/만3, 2026-09/만5 |
| 2회 | `가을 나들이` | 2026-09/만3, 2026-09/만5 |

같은 반의 연간 흐름으로 보면 `사방치기`가 9월과 2월에, `모래놀이`가 3월과 8월과 1월에
반복된다. 한 해 계획으로 읽으면 눈에 띄는 반복이다.

또한 **주제는 다른데 활동 형태가 겹치는** 경우가 있다. 2026-03 만3세 W2 `바깥 놀이터 사진을
찍어요`와 W3 `바깥 놀이터에서 지켜야 할 약속을 정해요`는 label은 다르지만 2주 연속
"바깥 놀이터"를 소재로 한다.

### 2.4 W1~W5 사이에 설명 가능한 흐름이 있는가 — **없다**

Rule에 흐름을 만드는 축이 없다. 정렬 키는 다음 6개뿐이다.

```text
(repeat penalty, theme penalty, display quality penalty,
 curriculum penalty, -evidence strength, stable activity_id)
```

주차 번호는 **정렬에 들어가지 않는다.** W1이 강한 근거를, W5가 약한 근거를 받는 것이
전부다. 실제 trace 분포가 이를 그대로 보여준다.

| trace reason | 건수 |
|---|---:|
| `AVOIDED_REPEAT_IN_MONTH` | 41 |
| `TIE_BREAK_STABLE_ACTIVITY_ID` | 6 |
| `MATCHED_PARENT_THEME` | 5 |
| `STRONGER_MONTH_EVIDENCE` | 1 |

55칸 중 41칸(75%)의 선택 이유가 "이번 달에 아직 안 썼다"이다. 그 이상의 의미가 없다.

관찰된 역행 사례: **2026-04 만4세**

```text
W1 화단에 물주기
W2 모래로 개미집 만들기
W3 벚꽃 비 흩날리기      ← 4월 중순 이후
W4 산책하며 새싹 찾기     ← 4월 초 소재
W5 봄의 곤충 사진 찍기
```

`새싹 찾기`가 `벚꽃 비`보다 뒤에 온다. 계절 진행과 반대다. 다섯 후보의
`evidence_strength`가 전부 1이라 정렬은 `activity_id` 사전순으로만 결정됐다.

### 2.5 주차 순서가 사실상 임의로 보이는가 — **12 Case 중 6 Case가 완전히 임의다**

같은 달 후보의 `evidence_strength`가 전부 같으면 남는 정렬 키는 `activity_id`뿐이다.
`activity_id`는 `act_outdoor_v2_<hash>` 형태의 **해시**이므로 그 정렬은 의미가 없다.

| Case | evidence_strength | 전부 동률 | 선택 순서 == activity_id 사전순 |
|---|---|---|---|
| 2026-03 만3 | `[2,2,2,2]` | **예** | 예 |
| 2026-04 만4 | `[1,1,1,1,1]` | **예** | 예 |
| 2026-06 만4 | `[1,1,1,1]` | **예** | 예 |
| 2026-08 만4 | `[1,1,1,1]` | **예** | 예 |
| 2026-12 만4 | `[1,1,1,1,1]` | **예** | 예 |
| 2027-01 만5 | `[1,1,1,1]` | **예** | 예 |
| 2026-07 만3 | `[2,1,1,1,1]` | 아니오 | 예 (우연히 일치) |
| 2026-09 만3 | `[11,7,5,5,4]` | 아니오 | 아니오 |
| 2026-11 만3 | `[2,1,1,1]` | 아니오 | 아니오 |
| 2026-05 만5 | `[2,2,1,1]` | 아니오 | 아니오 |
| 2026-09 만5 | `[11,7,5,5,3]` | 아니오 | 아니오 |
| 2027-02 만5 | `[2,1,1,1]` | 아니오 | 아니오 |

**6/12는 주차 배치가 해시 정렬이다.** 나머지 6개도 근거 수 내림차순일 뿐, 주차 의미에서
나온 순서가 아니다.

### 2.6 연령 차이가 체감되는가 — **약하다**

같은 2026-09를 세 연령으로 생성한 결과다.

```text
만3세 (후보 37): 무궁화 꽃이 피었습니다 / 강강술래 / 가을 나들이 / 사방치기 / 모래 위에 옛 그림을 그려요
만4세 (후보 31): 무궁화 꽃이 피었습니다 / 가을 나들이 / 사방치기 / 모래 위에 옛 그림을 그려요 / 동대문 놀이
만5세 (후보 27): 무궁화 꽃이 피었습니다 / 강강술래 / 가을 나들이 / 사방치기 / 동대문 놀이
```

- 세 연령 **공통 3/5** (`무궁화 꽃이 피었습니다`, `가을 나들이`, `사방치기`)
- 두 연령씩 비교하면 **4/5가 동일**

차이는 난이도 조정에서 오지 않는다. **후보 pool 크기(37 / 31 / 27)가 달라서 하위 순위가
밀려난 결과**다. 만4세에서 `강강술래`가 빠지고 `동대문 놀이`가 들어온 것도 연령 적합성
판단이 아니라 pool 구성 차이다. Rule에는 연령별 난이도 축이 없다.

### 2.7 기관 특이적 Activity가 튀는가 — **튄다**

- Catalog 196개 중 **176개(90%)가 단일 기관 근거**다.
- 55개 출력 Cell 중 **34개(64%)가 단일 기관 근거 Activity**다.
- **4개 Case는 전 주차가 단일 기관 근거**다: 2026-07 만3, 2026-04 만4, 2026-06 만4, 2026-12 만4.

즉 그 달의 계획안은 사실상 **어느 한 기관의 월간계획안을 그대로 옮긴 것**에 가깝다.

자동 탐지된 `INSTITUTION_SPECIFIC` 6건 중 3건이 실제로 출력에 등장했다.

```text
2026-03 만3세 W2  바깥 놀이터 사진을 찍어요          [INSTITUTION_SPECIFIC/AUTO_CANDIDATE]
2026-03 만3세 W3  바깥 놀이터에서 지켜야 할 약속을 정해요 [INSTITUTION_SPECIFIC/AUTO_CANDIDATE]
2026-11 만3세 W2  숲속 동물 보호소                   [INSTITUTION_SPECIFIC/AUTO_CANDIDATE]
```

`숲속 동물 보호소`는 기관 시설/프로그램 이름으로 읽히며, 다른 원에서 그대로 쓰기 어렵다.

### 2.8 Parser / Fragment 문제 재발 여부 — **재발 없음**

| 조각 label | 출력 55칸 | 후보 pool | Catalog 196개 |
|---|---|---|---|
| `건너기` | 없음 | 없음 | 없음 |
| `장화 신고 물웅덩이` | 없음 | 없음 | 없음 |
| `우리집에 왜 왔니?` | 없음 | 없음 | 없음 |
| `놀이를 해요.` | 없음 | 없음 | 없음 |

복원 Activity `장화 신고 물웅덩이 건너기`가 2026-07 만3세 W1에 정상 선택됐다.

**다만 관찰 중 Catalog metadata 불일치 2건을 발견했다.** 수정하지 않고 기록만 한다.

| Activity | `evidence_count` 필드 | 실제 `evidence` 길이 |
|---|---:|---:|
| `장화 신고 물웅덩이 건너기` | 1 | 2 |
| `우리집에 왜 왔니? 놀이를 해요.` | 1 | 2 |

Patch 1에서 조각 두 개의 Evidence를 합칠 때 `evidence_count` 요약 필드를 갱신하지 않은 것으로
보인다. **selection에는 영향이 없다** — Rule은 `evidence_count`를 읽지 않고
`evidence_strength_for_month()`가 실제 evidence 목록을 센다(그래서 위 Activity의
`evidence_strength`가 정상적으로 2다). 표시·감사용 요약값만 어긋나 있다.

---

## 3. Rule 축의 실효성 측정

Ranking v2의 6개 축 중 실제로 결과를 가른 것은 2개뿐이다.

| # | 축 | 12 Case에서의 기여 |
|---:|---|---|
| 1 | same-month repeat penalty | **작동** — 같은 달 중복 0건. 단 월 간 반복은 대상 아님 |
| 2 | parent theme mismatch penalty | **부분 작동** — 53칸 중 4칸 붕괴, `theme_links` 미보유 26%에는 무력 |
| 3 | display quality penalty | **거의 미작동** — `HUMAN_CONFIRMED` 8건뿐이고 그중 문제 판정은 `전통놀이` 1건. 12 Case에서 penalty가 붙은 Cell **0건** |
| 4 | curriculum repeat penalty | **완전 미작동** — Catalog 196개 **전부** `curriculum_links = []`. 12 Case 전 Cell의 `selected_curriculum_domains`가 빈 값 |
| 5 | negative monthly evidence strength | **작동** — 실질적으로 이 축이 대부분을 결정한다 |
| 6 | stable activity_id | **작동** — 6/12 Case에서 **이 축이 순서를 전부 결정했다** |

정리하면 현재 Monthly 선택은 실질적으로

```text
근거 수 내림차순 → 동률이면 activity_id 해시 순
```

이다. 나머지 4개 축은 데이터가 없거나 중립이라 개입하지 않는다.

### 후보 pool의 여유도

```text
   월   주차   만3         만4         만5
    1월   4    14(3.5x)    8(2.0x)    8(2.0x)
    2월   4    11(2.8x)    4(1.0x)    4(1.0x)   ← 선택 여지 없음
    3월   4    15(3.8x)    8(2.0x)   11(2.8x)
    4월   5    16(3.2x)    9(1.8x)    9(1.8x)
    5월   4    11(2.8x)    8(2.0x)    8(2.0x)
    6월   4    13(3.2x)    7(1.8x)    7(1.8x)
    7월   5    15(3.0x)    8(1.6x)    8(1.6x)
    8월   4    12(3.0x)    7(1.8x)    7(1.8x)
    9월   5    37(7.4x)   31(6.2x)   27(5.4x)   ← Corpus가 9월에 몰려 있다
   10월   4    15(3.8x)    8(2.0x)    8(2.0x)
   11월   4    11(2.8x)    4(1.0x)    4(1.0x)   ← 선택 여지 없음
   12월   5    17(3.4x)    7(1.4x)    7(1.4x)
```

**후보 수 == 주차 수인 조합이 4건**이다(2월·11월 × 만4·만5세). 그 달은 "선택"이 아니라
**후보 전부를 순서만 정해 배치**하는 것이다.

---

## 4. 가장 문제가 심한 실제 Case 3개

### Case 1 — 2026-06 만4세 「우리 동네」 : Theme 축이 완전히 죽고, 더 맞는 후보가 밀려났다

**생성 결과 (그대로)**

```text
Theme: 우리 동네   (yr_theme_our_neighborhood)
W1  우리 동네에서 일하는 분 찾아보기        theme_matched=False
W2  분필로 내가 되고 싶은 직업 그림 그리기   theme_matched=False
W3  꿈을 실은 종이비행기 날리기            theme_matched=False
W4  병원에서 사용하는 물건 그림 찾기        theme_matched=False
```

**후보 pool 7개 전부 (activity_id 사전순)**

```text
ev=1 inst=1 theme_links=[]  우리 동네에서 일하는 분 찾아보기        ◀ W1
ev=1 inst=1 theme_links=[]  분필로 내가 되고 싶은 직업 그림 그리기   ◀ W2
ev=1 inst=1 theme_links=[]  꿈을 실은 종이비행기 날리기            ◀ W3
ev=1 inst=1 theme_links=[]  병원에서 사용하는 물건 그림 찾기        ◀ W4
ev=1 inst=1 theme_links=[]  나의 꿈 열기구 날리기
ev=1 inst=1 theme_links=[]  우리 동네 지도 보며 산책하기            ← 선택 안 됨
ev=1 inst=1 theme_links=[]  모래 위에 그리는 우리 동네              ← 선택 안 됨
```

**무엇이 문제인가**

- pool 7개 **전부** `theme_links = []`라 theme 축이 통째로 무력화됐다(`theme_matched` 0/4).
- `evidence_strength`도 전부 1이라 5번 축도 무력하다.
- 남은 정렬 키는 `activity_id` 해시뿐이다. 그 결과 **주제에 가장 가까운 두 후보
  (`우리 동네 지도 보며 산책하기`, `모래 위에 그리는 우리 동네`)가 정확히 탈락**하고,
  주제와 먼 `꿈을 실은 종이비행기 날리기` · `병원에서 사용하는 물건 그림 찾기`가 선택됐다.
- 4칸 전부 단일 기관 근거다.

「우리 동네」 한 달 계획이 「직업과 꿈」처럼 읽힌다. Rule은 어떤 규칙도 위반하지 않았다.
**판단할 데이터가 없었을 뿐이다.**

### Case 2 — 2027-02 만5세 「성장한 우리」 : 선택이 존재하지 않는다

**생성 결과 (그대로)**

```text
Theme: 성장한 우리   (yr_theme_growth_and_transition)
W1  우리가 좋아했던 장소 산책하기          ev=2
W2  사방치기                            ev=1   ← 2026-09에도 배치된 활동
W3  모래 위에 형님이 된 내 모습 그리기      ev=1
W4  산책하며 동네 이웃에게 설날 인사드리기   ev=1
```

**후보 pool 4개 = 주차 4개**

```text
ev=1 inst=3 사방치기                        ◀ W2
ev=1 inst=1 모래 위에 형님이 된 내 모습 그리기  ◀ W3
ev=1 inst=1 산책하며 동네 이웃에게 설날 인사드리기 ◀ W4
ev=2 inst=2 우리가 좋아했던 장소 산책하기       ◀ W1
```

**무엇이 문제인가**

- **후보 수와 주차 수가 같다.** Rule이 고른 것이 아니라 pool 전체를 순서만 매겨 배치했다.
  "선별층"이 존재하지 않는 상태다. 같은 상황이 11월 만4·만5세, 2월 만4세에도 있다(총 4조합).
- `사방치기`는 같은 반의 2026-09에도 배치된다. **월 간 반복을 막는 축이 없다.**
- `산책하며 동네 이웃에게 설날 인사드리기`는 「성장한 우리」보다 **설 명절 소재**다. 설은
  음력이라 해마다 1월 또는 2월로 옮겨 다니는데, Rule에는 **달력·행사 축이 없다.** 즉 이
  활동이 그 해 2월과 맞는지 아닌지를 판정할 근거가 시스템에 없다(해당 연도의 실제 설
  날짜는 저장소 자료로 확인할 수 없어 단정하지 않는다). `applicable_months`에 2가 있다는
  이유만으로 배치된다.
- Activity 하나만 빠져도 그 달은 즉시 `EMPTY_VALID` 칸이 생기는 구조다.

### Case 3 — 2026-03 만3세 「우리 원과 친구」 : 기관 고유 활동 2주 연속 + 해시 정렬

**생성 결과 (그대로)**

```text
Theme: 우리 원과 친구   (yr_theme_new_environment_friends)
W1  엉덩이 씨름                            ev=2  GOOD_STANDALONE/UNREVIEWED
W2  바깥 놀이터 사진을 찍어요                ev=2  INSTITUTION_SPECIFIC/AUTO_CANDIDATE
W3  바깥 놀이터에서 지켜야 할 약속을 정해요    ev=2  INSTITUTION_SPECIFIC/AUTO_CANDIDATE
W4  모래놀이                               ev=2  GOOD_STANDALONE/HUMAN_CONFIRMED
```

**후보 pool 15개 중 `ev=2`인 것은 정확히 이 4개뿐이다.**

```text
ev=2 act_outdoor_bottom_wrestling  엉덩이 씨름                     ◀ W1
ev=2 act_outdoor_playground_photo  바깥 놀이터 사진을 찍어요         ◀ W2  [INSTITUTION_SPECIFIC]
ev=2 act_outdoor_playground_rules  바깥 놀이터에서 지켜야 할 약속을 정해요 ◀ W3  [INSTITUTION_SPECIFIC]
ev=2 act_outdoor_sand_play         모래놀이                        ◀ W4
--- 아래는 전부 ev=1이라 선택되지 않음 ---
ev=1 우리 반 꽃이 피었습니다
ev=1 친구와 손 잡고 산책하기
ev=1 모래 위에 쓰인 우리 반 이름 찾기
ev=1 자연물로 선생님 얼굴 꾸미기
ev=1 친구와 함께 공 주고받기
ev=1 원주변을 산책해요.
ev=1 차례대로 줄을 설 수 있어요.
ev=1 선생님과 숨바꼭질
ev=1 안전 약속 지키며 놀이기구 타기
ev=1 우리 반 하루 일과 그림 찾기
ev=1 우리나라 상징 보물찾기
```

**무엇이 문제인가**

- 자동 탐지된 `INSTITUTION_SPECIFIC` 2건이 **연속 2주**에 배치됐다. `AUTO_CANDIDATE`는
  runtime 중립이므로 penalty가 붙지 않는다(설계대로다). 사람 검토가 되지 않은 상태에서
  그대로 노출된다.
- W2와 W3이 둘 다 "바깥 놀이터" 소재다. label 중복은 아니지만 **소재 중복**이고, 이를
  감지하는 축이 없다.
- 4개 모두 `ev=2` 동률이므로 주차 순서는 `activity_id` 사전순이다.
- 학년도 첫 달인데 `친구와 손 잡고 산책하기`, `우리 반 꽃이 피었습니다`,
  `모래 위에 쓰인 우리 반 이름 찾기`처럼 **주제에 훨씬 가까운 후보들이 근거 1건이라는 이유로
  전부 탈락**했다. 근거 수는 "Corpus에 몇 번 나왔는가"이지 "이 달에 얼마나 적절한가"가 아니다.
- W1 `엉덩이 씨름`은 만 3세 3월 첫 주 활동으로 보기 어렵다.

---

## 5. 판정

```text
WEEK_EXPERIENCE_LAYER_STILL_REQUIRED
```

근거 요약:

1. **주차에 의미를 부여하는 축이 Rule에 없다.** 정렬 키 6개 중 주차 번호를 쓰는 것은 없고,
   55칸 중 41칸(75%)의 선택 이유가 `AVOIDED_REPEAT_IN_MONTH`다.
2. **12 Case 중 6 Case는 주차 배치가 `activity_id` 해시 정렬이다.** 계절 역행 사례
   (2026-04 `벚꽃 비` → `새싹 찾기`)가 실제로 관찰된다.
3. **주차 간 흐름·연결이 0건이다.** W1~W5는 서로 독립된 활동 나열이며 전개가 없다.
4. **연령 차이가 체감되지 않는다.** 같은 9월에서 세 연령 공통 3/5, 두 연령 비교 시 4/5 동일.
   차이는 난이도가 아니라 pool 크기에서만 온다.

### 다만 Week Experience Layer만으로는 해결되지 않는 문제를 분리해 기록한다

아래는 **주차 층이 아니라 Reference 데이터의 문제**다. 주차 층을 얹어도 그대로 남는다.

| 문제 | 수치 | 성격 |
|---|---|---|
| `curriculum_links`가 전무 | 196/196이 빈 값 | Ranking 4번 축이 죽어 있다 |
| `theme_links` 미보유 | 51/196 (26%) | Ranking 2번 축이 26%에 무력 |
| 단일 기관 근거 | 176/196 (90%), 출력의 64% | 선별이 아니라 전사에 가깝다 |
| 월별 pool 편중 | 9월 27~37 vs 그 외 4~17 | 9월만 선택이 가능하다 |
| pool == 주차 수 | 4조합 (2월·11월 × 만4·만5) | 선별층이 존재하지 않는다 |
| 월 간 반복 축 부재 | `모래놀이` 3회, `사방치기` 3회 | 연간으로 읽으면 반복이 보인다 |
| `AUTO_CANDIDATE` 미검토 | 9건 중 3건이 출력에 등장 | 사람 검토 대기열이 소진되지 않았다 |

**따라서 판정은 `WEEK_EXPERIENCE_LAYER_STILL_REQUIRED`이되, 그것만으로 충분하다는 뜻은
아니다.** Week Experience 층은 §4의 Case 1(theme_links 부재)과 Case 2(pool 고갈)를 고치지
못한다. 두 축을 같이 봐야 한다.

---

## 6. 이번 작업에서 변경하지 않은 것

| 항목 | 상태 |
|---|---|
| `data/activities/activity_reference_v0_2_1.json` | 무수정 — `ddbbe43f570cf64ef86db44e7de04e127aec4e663cdb41c26a8fe3c1002dc2ac` |
| `data/activities/activity_reference_v0_2.json` | 무수정 — `e27ebca3342a84327c6624c5ba258b9bc98aef37ba5362b61f283c47ece0bde6` |
| `data/themes/theme_reference_v0.json` | 무수정 — `c12999fa141d5c5fdecf39110adfb2227fc0ab98725991e8bdbca098b3ff4197` |
| `data/templates/monthly_template_a.json` | 무수정 — `1f35322dd52f832bffc3057953ecbd64d52c2d855ada964af68472ebba1a7c34` |
| `data/rules/safety_education_legal_v1.json` | 무수정 — `5831809b19a28505844cf10363c95eeb09ec4641d5fe54a26afdb1891c3ddba5` |
| Selection Rule v2 | 무수정 |
| Production / Demo default | `activity-reference-v0.2.1` 그대로 |
| Week Experience / 새 Rule / 새 Reference | **만들지 않음** |
| 발견한 `evidence_count` 불일치 2건 | **고치지 않고 §2.8에 기록만** |

추가된 파일은 읽기 전용 관찰 도구와 이 보고서뿐이다.

- `analysis/experiments/monthly_vnext/observe_v0_2_1_quality.py`
- `analysis/tmp/monthly_v0_2_1_quality.json`
- `docs/analysis/monthly-v0-2-1-demo-quality-verification.md`

테스트: `1644 passed, 4 deselected` (변동 없음)

### 재현

```bash
python analysis/experiments/monthly_vnext/observe_v0_2_1_quality.py
```
