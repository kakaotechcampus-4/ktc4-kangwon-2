# Activity Reference v0.1.0 — Human Review 요청 자료

> **이 문서는 승인 요청 자료다. 승인 기록이 아니다.**
>
> ```text
> catalog_version       : activity-reference-v0.1.0
> domain_owner_approval : PENDING_HUMAN_REVIEW
> approved_by           : null
> approved_at           : null
> runtime active        : false
> ```
>
> 최종 판정: **`PENDING_HUMAN_REVIEW`** — 아래 §13의 이유로 이번 단계에서 승인하지
> 않는다. 승인은 사람이 별도로 수행한다.

- 대상 파일: `data/activities/activity_reference_v0.json`
- 작성일: 2026-09-11
- 관련 결정: OD-N03 (부분) / D1·D2·D3·D4 (2026-09-11)
- 사용 메모: `data/activities/README.md`

---

## 1. Source 목록

저장소 내부의 실측 Monthly Sample만 사용했다. 외부 네트워크 접근 0건이다.

| origin_id | 기관 유형 | 페이지 | 판독 페이지 |
|---|---|---:|---|
| `sample.monthly.aisarang.2026.09.age3` | 국공립 | 1 | 1 |
| `sample.monthly.aisarang.2026.09.age4` | 국공립 | 1 | 1 |
| `sample.monthly.aisarang.2026.09.age5` | 국공립 | 1 | 1 |
| `sample.monthly.goesanhana.2026.09` | 국공립 | 2 | 1, 2 |
| `sample.monthly.dolgorae.2026.09` | 국공립 | 1 | 1 |
| `sample.monthly.seobom.2026.09` | 국공립 | 4 | 1, 2, 3, 4 |
| `sample.monthly.eomji.2026.09` | 민간 | 1 | 1 |
| `sample.monthly.yedam.2026.09` | 민간 | 1 | 1 |
| `sample.monthly.keunbit.2026.09` | 민간 | 2 | 1 (p.2 근거 미사용) |
| `sample.monthly.haechansol.2026.09` | 민간 | 1 | 1 |
| `sample.monthly.geumsan.2026.09` | 직장 | 1 | 1 |
| `sample.monthly.hansolbit.2026.03` | 민간 | 3 | 1, 2, 3 |
| `sample.monthly.aideulsesang.2026.09` | 협동 | 2 | 1, 2 |
| `sample.monthly.byeolbitjai.2026` | 국공립 | 2 | **판독 불가** (이미지 전용) |

### 1.1 Source count

```text
source_count            : 14   (origin 항목 수)
readable_source_count   : 13
institution_count       : 12   (아이사랑 3파일을 1기관으로 세면 12)
readable_institution_count : 11
기관 유형               : 국공립 6 / 민간 5 / 직장 1 / 협동 1
evidence 총 개수        : 74
```

**검토 포인트 1**: 아이사랑어린이집은 연령별 3파일이라 `origin_id`를 3개로 분리했다.
Theme Reference는 한 파일 안의 연령별 페이지를 `evidence[].age_scope`로 구분했는데,
Activity에서는 파일 자체가 분리돼 있어 origin을 나눴다. 이 방식이 맞는지 확인이
필요하다.

### 1.2 SHA-256 검증

`origins[].sha256` 14건 전부를 저장소 실제 파일과 재계산해 대조했다.
→ **14/14 일치** (`test_real_catalog_origins_are_declared_and_hashes_match`가 고정)

---

## 2. Item count

```text
item_count : 49
```

기관 수별 분포:

| 관찰 기관 수 | 항목 수 |
|---:|---:|
| 5기관 | 1 |
| 4기관 | 2 |
| 3기관 | 1 |
| 2기관 | 6 |
| 1기관 | 39 |

**검토 포인트 2**: 49개 중 39개(80%)가 **1기관 관찰**이다. T.3 기준("한 활동의
`applicable_months`에 월을 넣으려면 그 월에서 관찰된 evidence가 최소 1건")은
만족하지만, 1기관 항목을 운영 후보로 쓸지에 대한 판단이 필요하다. ranking의
`evidence_strength_for_month`가 자동으로 후순위로 두므로 제거하지 않아도 되지만,
Human Review에서 명시적으로 확인해 주기를 요청한다.

### 2.1 다기관 관찰 항목 (근거가 가장 강한 10개)

| activity_id | label | 월 | 연령 | 기관 |
|---|---|---|---|---:|
| `act_outdoor_mugunghwa_flower_game` | 무궁화 꽃이 피었습니다 | 9 | 3,4,5 | 5 |
| `act_outdoor_ganggangsullae` | 강강술래 | 9 | **3,5** | 4 |
| `act_outdoor_traditional_play` | 전통놀이 | 9 | 3,4,5 | 4 |
| `act_outdoor_sabangchigi` | 사방치기 | 9 | 3,4,5 | 3 |
| `act_outdoor_autumn_outing` | 가을 나들이 | 9 | 3,4 | 2 |
| `act_outdoor_dongdaemun_nori` | 동대문 놀이 | 9 | 3,4,5 | 2 |
| `act_outdoor_sand_old_painting` | 모래 위에 옛 그림을 그려요 | 9 | 3,4 | 2 |
| `act_outdoor_sand_play` | 모래놀이 | **3, 9** | 3,4,5 | 2 |
| `act_outdoor_traditional_play_fair` | 전통 놀이 한마당 | 9 | 3,4 | 2 |
| `act_outdoor_tuho` | 투호놀이 | 9 | **3,5** | 2 |

---

## 3. Month coverage

```text
month_coverage : [3, 9]
```

| 월 | 후보 수 | 근거 |
|---|---:|---|
| 3월 | 8 | `hansolbit` 3페이지 (유일한 3월 표본) + `sand_play` |
| 9월 | 42 | 나머지 12 origin |
| 4·5·6·7·8·10·11·12·1·2월 | **0** | 표본 없음 |

`sand_play`(모래놀이)만 3월·9월 양쪽에서 관찰된 유일한 활동이다.

**Theme Reference의 `applicable_months`를 Activity 근거로 전용하지 않았다.**
추론으로 월을 확장하지 않았고, schema와 Domain이 `applicable_months ⊆ 관찰된 월`을
강제한다.

**검토 포인트 3 (가장 중요)**: 10개월에 후보가 0이다. 현재 Catalog를 승인하면
`outdoor_play` Cell이 2개월만 채워지고 나머지 10개월은 비게 된다. D1 결정에 따라
이번에는 승인하지 않는다.

---

## 4. Age coverage

```text
age_coverage : [3, 4, 5]
```

항목별 `supported_ages` 분포:

| supported_ages | 항목 수 |
|---|---:|
| `[3]` | 13 |
| `[3, 4]` | 10 |
| `[3, 4, 5]` | 9 |
| `[5]` | 8 |
| `[4, 5]` | 5 |
| `[3, 4]`(중복 제외) · `[4]` | 2 |
| **`[3, 5]`** | **2** |

### 4.1 연령 공백 — Human Decision 필요

`[3, 5]` 2건이 **만 4세를 지원하지 않는다.**

| activity_id | label | 관찰 | 결과 |
|---|---|---|---|
| `act_outdoor_ganggangsullae` | 강강술래 | 아이사랑 만3 / 아이사랑 만5 / 시립새봄 만3 / 아이들세상 만5 | `[3, 5]` |
| `act_outdoor_tuho` | 투호놀이 | 아이사랑 만5 / 시립새봄 만3 | `[3, 5]` |

`mixed_age_requires_all_supported: true`이므로 `{3,4}` 반과 `{4}` 반은 강강술래를
후보로 받지 못한다. 교육적으로는 부자연스럽지만, **근거보다 넓게 주장하지 않는다**는
원칙(T.2 기준 3)을 지킨 결과다.

**검토 포인트 4**: 두 선택지 중 하나가 필요하다.

1. 그대로 둔다 (근거 충실. 만4세 반에서 유명 전통놀이가 후보에서 빠진다)
2. 만4세 표본을 추가로 확보해 근거로 메운다 (권장. §13-3과 연결)

임의로 `[3,4,5]`로 넓히지 않았다.

### 4.2 연령 근거가 없어 제외한 문서 2건

| origin_id | 상태 |
|---|---|
| `sample.monthly.haechansol.2026.09` | 본문에 연령 표기 0건. `age_scope: []` |
| `sample.monthly.geumsan.2026.09` | 본문에 연령 표기 0건. `age_scope: []` |

파일명은 각각 `만3세, 만4-5세` / `만3-5세`이지만 **CLAUDE.md §11에 따라 파일명
표기로 추론하지 않았다.** 두 문서만을 근거로 하는 항목은 `supported_ages`를 만들 수
없어 후보에서 제외했다(§5의 제외 목록 6건).

---

## 5. 제외한 기관 고유 / 지역 항목

`exclusion_policy.excluded_items`에 **22건**을 원문·기관·페이지·사유로 보존했다.
runtime 후보에는 포함하지 않았다.

| 사유 | 건수 |
|---|---:|
| 지역 시설 (탄금공원·탄금대숲·능암늪생태공원·만수계곡·롤러장·민속박물관) | 5 |
| 연령 근거 없음 (본문 연령 미표기) | 6 |
| 기관 텃밭 | 2 |
| 기관 고유 (우리 원 사진·우리 원 자랑거리) | 2 |
| 지역 도로명 (무궁화길) | 1 |
| 지역 산 이름 (성불산) | 1 |
| 기관 특별프로그램 (3D러닝플레이) | 1 |
| 기관 주변 (`[지역]`우리 원 주변) | 1 |
| 활동명이 아니라 관찰 주제로 읽힘 (`맑고 푸른 가을 하늘`) | 1 |
| **안전 경계 우려** (`바깥놀이를 안전하게 해요`) | 1 |
| theme 귀속 미확정 (`교통기관의 특징과 이름 말하며 산책하기`) | 1 |

### 5.1 D3 준수 확인

**의미를 바꿔 일반화하지 않았다.** `만수계곡 자연관찰로` → `나들이` 같은 변환을
수행하지 않았다. 제외 항목은 그대로 원문으로 남아 있고 canonical Activity로
승격되지 않았다.

`test_real_catalog_excludes_named_facilities_from_labels`가 49개 label 전체에서
`만수계곡` / `탄금` / `능암늪` / `성불산` / `무궁화길` / `민속박물관` / `롤러장` /
`우리 원` 토큰이 없음을 고정한다.

### 5.2 일반 명사는 제외하지 않았다

| 포함한 label | 근거 |
|---|---|
| `바깥 놀이터 사진을 찍어요` | `바깥 놀이터`는 일반 명사이며 특정 시설명이 아니다 |
| `바깥 놀이터에서 지켜야 할 약속을 정해요` | 동일 |
| `가을 나설이`의 alias `공원으로 가을 나들이 가기` | `공원`은 일반 명사이며 고유명사가 아니다 |

**검토 포인트 5**: 위 3건의 판정이 적절한지 확인이 필요하다. 특히
`바깥 놀이터 사진을 찍어요`는 카메라가 필요한 활동이라 기관 자원 의존이 있을 수 있다.

### 5.3 `[실내대체]` 계열 제외

`[실내대체]` · `[대체]` · `(대체활동: …)` · `【대체활동 : …】` inline 태그가 붙은
항목은 `indoor_alternative` Section 소속이므로 outdoor 후보로 전사하지 않았다.

예: 시립새봄 p.3의 `(대체활동- · 사방치기 / · 제기차기)`에서 사방치기/제기차기는
실내대체다. 사방치기는 아이사랑·큰빛에서 **직접 바깥놀이 항목**으로 관찰돼 그 근거로
후보가 됐다. 제기차기는 직접 바깥놀이 근거가 없어 후보에 없다.

---

## 6. Duplicate canonicalization 내역

**자동 merge와 LLM merge를 수행하지 않았다.** 사람이 전사 시점에 판단했다.

### 6.1 `NORMALIZED` 4건 — 표현 변이를 canonical 하나로

| activity_id | canonical label | 통합한 원문 |
|---|---|---|
| `act_outdoor_ganggangsullae` | 강강술래 | `♥바깥놀이- 강강수월래해요` · `강강술래` · `*대동놀이 : 강강술래 (느리게 걷기, 뛰기)` |
| `act_outdoor_traditional_play` | 전통놀이 | `전통놀이를 해요` · `-전통놀이` · `<추석>명절전통놀이` · `-전통놀이체험` |
| `act_outdoor_sand_play` | 모래놀이 | `- 조물조물 모래놀이를 해요` · `모래놀이` |
| `act_outdoor_autumn_outing` | 가을 나들이 | `♥바깥놀이-가을 나들이를 가요` · `공원으로 가을 나들이 가기` |

`matched_via: RELATED_EXPRESSION` 7건에 각각 `match_note`로 판단 근거를 남겼다.

**검토 포인트 6**: `act_outdoor_traditional_play`가 가장 논쟁적이다. `전통놀이` /
`전통놀이 체험` / `명절전통놀이`를 하나로 합쳤는데, `명절전통놀이`는 추석 한정
의미가 있을 수 있다. 분리가 더 적절하다면 지적해 주기를 요청한다. 원문은 전부
`evidence[].observed_label`에 보존돼 있어 분리 시 정보 손실이 없다.

### 6.2 **분리**를 택한 3건 — "애매하면 분리"

| 분리한 쌍 | 이유 |
|---|---|
| `전통놀이` ↔ `전통 놀이 한마당` | 단일 놀이 vs 여러 전통놀이를 동시에 펼치는 행사형 구성 |
| `바람개비 들고 시원하게 달리기` ↔ `바람개비 돌리며 가을 느끼기` | 동작이 다르고 후자는 연령 근거 없음 |
| `모래로 전통음식 만들기` ↔ `젖은 모래로 떡을 만들어요` | 후자는 연령 근거 없음 |

후자 2쌍의 뒤쪽 항목은 연령 근거가 없어 후보로도 만들지 않았다.

### 6.3 원문 보존 확인

`aliases`와 `evidence[].observed_label`을 서로 대체하지 않는다.

```text
label           : 강강술래
aliases         : ["강강수월래해요", "대동놀이 : 강강술래"]
evidence[0]     : "♥바깥놀이- 강강수월래해요"   ← 접두 태그까지 원문 그대로
```

`test_aliases_do_not_replace_evidence_labels`가 이 분리를 고정한다.

---

## 7. Aliases 내역

`aliases`를 가진 항목 **14건**이다. 전부 사람이 같은 활동의 표현 변이로 판단해
승인한 표현이다.

| label | aliases |
|---|---|
| 무궁화 꽃이 피었습니다 | `무궁화꽃이 피었습니다` · `무궁화 꽃이 피었습니다.` |
| 강강술래 | `강강수월래해요` · `대동놀이 : 강강술래` |
| 전통놀이 | `전통놀이를 해요` · `전통놀이 체험` · `명절전통놀이` |
| 전통 놀이 한마당 | `전통 놀이 한마당을 열어요` · `전통놀이 한마당` |
| 가을 나들이 | `가을 나들이를 가요` · `공원으로 가을 나들이 가기` |
| 동대문 놀이 | `동대문놀이` |
| 모래놀이 | `조물조물 모래놀이를 해요` |
| 대문놀이 | `대문놀이를 해요` |
| 딱지 치기 | `딱지 치기 놀이를 해요` |
| 고무줄 놀이 | `고무줄 놀이를 해요` |
| 줄다리기 | `줄다리기를 해요` |
| 엉덩이 씨름 | `엉덩이 씨름을 해요` |
| 자연물로 탈 꾸미기 | `자연물로 탈꾸미기` |
| 친구와 함께 이어달리기 | `친구와 함께 이어달리기를 해요` |

대부분은 종결형(`~을 해요`) 유무와 공백 차이다.

---

## 8. Curriculum link 내역

```text
curriculum_links 총 개수 : 0   (49개 항목 전부 빈 배열)
```

**의도적으로 비웠다.** 근거가 없으면 빈 배열이 정답이라는 지시(§9)를 따랐다.

### 8.1 빈 배열의 근거

| 확인 항목 | 결과 |
|---|---|
| 월간 실측 샘플 14파일 전수에 누리과정 5개 영역 표기 | **0건** (`신체운동\|의사소통\|사회관계\|예술경험\|자연탐구` grep) |
| 연간 실측 샘플의 5영역 표기 (기존 분석) | **0/6** |
| `2019_개정_누리과정_놀이이해자료.pdf`의 활동별 영역 태깅 | 없음. 5영역 언급 13회이며 전부 산문 |
| `2019_개정_누리과정_놀이실행자료.pdf` | 서술형 지원자료. 구조화 태깅 없음 |
| `references/README.md §4.5` | "놀이 사례를 Activity Template의 고정 목록으로 사용하지 않는다" |
| `data/` 안의 curriculum machine-readable Reference | **없음** |
| LLM 초안 태깅 | 지시에 따라 **수행하지 않았다** |

즉 활동별 영역 귀속의 국가 ground truth가 존재하지 않는다. 사람 검토 가능한 근거가
없으므로 빈 배열로 두었다.

### 8.2 Contract는 구현돼 있다

값은 비었지만 Contract는 완전히 동작한다.

- 복수 0..N 허용 (`test_curriculum_links_allow_multiple_domains`)
- primary / secondary 없음, weight 없음
  (`test_curriculum_link_has_no_primary_or_weight_field`)
- 5개 영역 외 어휘 거부 (`test_curriculum_domain_rejects_invented_vocabulary`)
- `DOMAIN_LEVEL` + `EDUCATIONAL_ALIGNMENT`만 허용
- 공식 항목 ID 발명 금지 (`invented_official_item_ids: false`)

**검토 포인트 7**: 5영역 링크를 채울 근거를 사람이 제공할 수 있다면(예: 공식
해설서의 특정 페이지와 특정 활동의 연계 판단) 후속 version에서 추가할 수 있다.
현재는 빈 배열이 맞다고 판단했다.

---

## 9. Theme link 내역

```text
theme_links 총 개수 : 57
relation            : OBSERVED_TOGETHER (전부)
theme_catalog_version : theme-reference-v0.1.2 (전부)
```

| theme_id | 링크 수 |
|---|---:|
| `yr_theme_korea_and_world_cultures` | 34 |
| `yr_theme_autumn_and_nature` | 15 |
| `yr_theme_new_environment_friends` | 8 |

`theme_id` 3개 전부가 `theme-reference-v0.1.2`에서 resolve된다
(`test_real_catalog_theme_links_resolve_in_declared_theme_catalog`가 고정).

### 9.1 관찰된 페이지 주제 → theme_id 매핑

| 문서 원문 주제 | 매핑한 theme_id |
|---|---|
`자랑스러운 우리나라` / `우리나라` / `우리나라 알아보기` / `우리 나라` / `세계 속의 우리나라 살펴보기` / `지구촌 탐구하기` / `함께 가요, 세계 속으로!` / `얼쑤! 우리나라` / `우리들의 축제(우리나라)` | `yr_theme_korea_and_world_cultures` |
`풍성한 가을` / `랄랄라, 가을이 좋아!` / `가을1` / `다채로운 가을` / `맑고 밝은 가을` / `열매 맺는 달` | `yr_theme_autumn_and_nature` |
`우리 반 알아보기` / `우리 반` / `원과 친구` | `yr_theme_new_environment_friends` |

### 9.2 다대다 확인

한 활동이 2개 theme에 링크된 항목 **8건**이다. 같은 페이지가 두 주제 계열을 병기한
문서(아이사랑 만4·만5, 해찬솔)에서 나온다.

예: `무궁화 꽃이 피었습니다` → `korea_and_world_cultures` + `autumn_and_nature`
(해찬솔 p.1의 주제가 `얼쑤! 우리나라 / 랄랄라, 가을이 좋아!`이기 때문)

### 9.3 문자열 매칭을 사용하지 않았다

각 링크는 evidence 페이지의 **문서 머리글 주제**를 사람이 읽어 매핑했다. Activity
label과 theme label의 문자열 유사도를 쓰지 않았다.

**검토 포인트 8**: §9.1 매핑 중 다음 2건이 판단을 요한다.

1. `지구촌 탐구하기`(시립새봄 만5세)를 `korea_and_world_cultures`로 매핑했다. Theme
   Reference label이 `우리나라와 세계 여러 나라`이므로 "세계 여러 나라" 쪽 의미로
   대응한다고 보았다.
2. `열매 맺는 달`(아이들세상 만5세)을 `autumn_and_nature`로 매핑했다. 24절기 기반
   표기라 직접 대응이 아니다.

---

## 10. Unresolved / Ambiguous items

승인 전에 사람 판단이 필요한 항목이다.

| # | 항목 | 상태 |
|---|---|---|
| 1 | **10개월 후보 0** (4·5·6·7·8·10·11·12·1·2월) | 표본 부족. §13-3 |
| 2 | `강강술래` / `투호놀이`의 **만4세 공백** | §4.1 |
| 3 | 49개 중 **39개가 1기관 관찰** | §2 |
| 4 | `act_outdoor_traditional_play`의 4개 표현 통합 적절성 | §6.1 |
| 5 | `큰빛 p.2`(만3세) 바깥놀이 행 **미사용** | `오전자유놀이(바깥놀이포함)` 병합 라벨로 행 귀속이 확정되지 않았다. 셀 기하 추출에서도 8개 행이 한 band로 묶였다 |
| 6 | `해찬솔` / `금산군청` 본문 연령 미표기 | §4.2. 파일명 추론을 하지 않아 6개 항목을 제외했다 |
| 7 | `한솔빛 p.2` 머리글 연도가 **2025년** | 문서 내부 불일치. 월(3월)만 근거로 사용했고 evidence `match_note`에 기록했다 |
| 8 | `한솔빛` 파일명은 `만3,4,5세`인데 판독 페이지는 **3세·5세·5세** | 만4세 페이지가 없다 |
| 9 | `돌고래 월간`이 Template A `evidence_base`에 **미포함** | Template A는 `file_count: 13` / 11기관인데 디렉터리에 14파일이 있다. Activity에서는 본문 머리글로 월·연령을 확인해 포함했다 |
| 10 | `별빛자이` 이미지 전용 PDF | 판독 불가. origin으로 선언만 하고 evidence 0건 |
| 11 | `바깥 놀이터 사진을 찍어요` 등 일반 명사 판정 | §5.2 |
| 12 | `지구촌 탐구하기` / `열매 맺는 달` theme 매핑 | §9.3 |
| 13 | 아이사랑 3파일을 3개 origin으로 분리한 방식 | §1.1 |

---

## 11. Safety exclusion 확인

| 확인 항목 | 결과 |
|---|---|
| `placement_slots`에 `safety_education` | **0건.** Domain과 schema가 모두 거부 |
| `safety_flags` 필드 | **없음.** schema가 키 자체를 거부 |
| 법정 안전교육 구분명(`성폭력`/`아동학대`/`실종`/`유괴`/`약물`/`재난대비`)이 label에 | **0건** |
| 안전 경계가 모호한 항목 | `바깥놀이를 안전하게 해요` 1건 **제외** |
| `safety_exclusion_statement` 진술문 | 포함 |
| `data/rules/safety_education_legal_v1.json` 변경 | **0건.** SHA `5831809b…` 불변 |
| `SafetyEducationPlan` Aggregate | 만들지 않음 |
| 아이나무 연간 안전교육계획서 사용 | **0건.** `data/`·`docs/` 참조 0건 유지 |
| `eligible_candidates(section_key="safety_education", …)` | 승인 상태여도 `()` 반환 |

`test_real_catalog_has_no_safety_fields`,
`test_safety_education_placement_slot_is_rejected`,
`test_approved_fixture_still_rejects_safety_slot`가 고정한다.

---

## 12. 외부 source 0 확인

| 확인 항목 | 결과 |
|---|---|
| `origins[].kind` | 14건 전부 `MONTHLY_PLAN_SAMPLE` |
| `origins[].path` | 14건 전부 `references/samples/monthly/` 하위 |
| origin에 `url` / `retrieved_at` / `license` 필드 | **없음** |
| activities에 `source_url` / `http` / `www.` / `blog` | **0건** |
| 키드키즈 · 꼬망세 등 외부 사이트를 origin이나 evidence로 사용 | **0건** |
| 외부 네트워크 접근 | **0건** |
| scraping 코드 | **작성하지 않음** |

`exclusion_policy.external_sources` 진술문 안에는 "사용하지 않았다"는 문맥으로
사이트 이름이 등장한다. 따라서 테스트는 문서 전체 문자열이 아니라 **실제 데이터
경로**(origins / activities)에 외부 출처가 없는지를 검증한다
(`test_real_catalog_documents_external_source_exclusion`).

---

## 13. 최종 판정 — `PENDING_HUMAN_REVIEW`

### 13.1 Claude가 승인하지 않는다

`approved_by`와 `approved_at`을 `null`로 두었다. 승인된 값처럼 채우지 않았다.
`domain_owner_approval`은 `PENDING_HUMAN_REVIEW`이고 `runtime_active`는 그 값에서
파생돼 `false`다.

### 13.2 구조 검증은 통과했다

| 기준 | 결과 |
|---|---|
| 1. 모든 항목이 evidence ≥ 1개, origin이 선언되고 SHA 일치 | **49/49, 14/14 일치** |
| 2. `applicable_months`가 관찰 월을 넘지 않음 | **과장 0건** |
| 3. `supported_ages`가 관찰 age_scope를 넘지 않음 | **과장 0건** |
| 4. `theme_links[].theme_id`가 선언 version에서 resolve | **57/57 resolve** |
| 5. `month_coverage`가 실제 후보 월과 정확히 일치 | **일치** `[3, 9]` |
| 6. `normative_status` + disclaimer | **포함** |
| 7. `origins` ≥ 3기관, `institution_types` ≥ 2종 | **12기관 / 4종** (초과 충족) |

### 13.3 승인 보류 사유 — 추가 월간 표본 필요

D1 결정대로, 구조는 검증됐지만 **내용 커버리지가 부족하다.**

```text
현재 : 2개월 (3월 8개 / 9월 42개)
필요 : 12개월
```

승인을 위해 필요한 추가 표본:

| 필요 | 내용 |
|---|---|
| 월 | 4·5·6·7·8·10·11·12·1·2월 월간계획안 |
| 연령 | 만4세 표본 (강강술래·투호놀이의 연령 공백 해소, 한솔빛 만4세 페이지 부재) |
| 형식 | 바깥놀이 행이 텍스트로 판독 가능한 PDF (이미지 전용은 근거 불가) |
| 표기 | 본문에 연령이 표기된 문서 (해찬솔·금산군청 유형의 반복을 줄이기 위해) |

### 13.4 승인 절차

Theme Reference v0.1.2와 동일하다.

1. 사람이 이 문서의 검토 포인트 1~8과 §10 unresolved 13건을 확인한다.
2. 추가 월간 표본을 확보해 월 커버리지를 확장한다.
3. 새 `catalog_version`을 발행하고 `supersedes`로 연결한다.
4. 사람이 `review.domain_owner_approval`을 `HUMAN_APPROVED`로,
   `approved_by`를 `reviewer_<role>_<sequence>`(OD-N10), `approved_at`을 **실제 처리
   시각**으로 설정한다.
5. `runtime_active`는 그 값에서 자동 파생된다. 별도 activation 우회 경로는 없다.

승인 metadata 변경만으로는 새 `catalog_version`을 발행하지 않는다. 내용이 바뀌면 새
version을 발행한다.

### 13.5 현재 상태로 가능한 일

승인 없이도 다음은 가능하다.

- M2-A 구조 구현 및 독립 테스트 (**완료**)
- Activity Candidate 초안 보관 (**완료**, 49건)
- Domain / Schema / Loader 테스트 (**완료**, 191 테스트)
- M2-B Selection Rule 개발 준비 (테스트 fixture로 `activation_override`를 써서 승인
  상태 동작을 검증할 수 있다)

불가능한 일:

- runtime 후보 사용
- `GenerateMonthlyPlan`에서 실제 outdoor Cell 채우기 (M2-C이며 승인된 Catalog가
  선행 조건)
