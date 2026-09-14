# Newly Added Reference Evidence Re-audit

## 만3·4·5세 및 Monthly 품질 개선 가능성 재평가

- 작성일: 2026-09-13
- 성격: **분석 전용.** `src/` · `data/` · `demo-planning/` · `CLAUDE.md` ·
  Activity Reference · Theme Reference · Selection Rule · Prompt를 **수정하지 않았다.**
- 도구 (전부 읽기 전용, `analysis/` 안에서만 씀)
  - `analysis/tools/extract_corpus.py` → `analysis/tmp/inventory.json`
  - `analysis/tools/reclassify.py` → `analysis/tmp/inventory2.json`
  - `analysis/tools/new_reference_impact.py` → `analysis/tmp/new_reference_impact.json`
  - `analysis/tools/new_reference_yield.py` → `analysis/tmp/new_reference_yield.json`
  - `analysis/tools/new_reference_candidates.py`
  - `analysis/tools/week_experience.py` → `analysis/tmp/week_experience.json`
- 이전 Baseline 보존: `analysis/tmp/inventory_baseline_2026_09_12.json` (175건),
  `analysis/tmp/week_experience_baseline.json` (33문서)

전체 테스트 `1644 passed, 4 deselected` — 이번 작업 전후 동일.

---

## 1. 현재 Repository 상태와 신규 Source 식별

### 1.1 구조

```text
references/
├── official/                        33 파일
│   ├── 00_curriculum_core/           5
│   ├── 10_play_cases/                4   (general 2 · outdoor_ecology 1 · picturebook 1)
│   ├── 20_age_specific/              2   (5세 이음교육 사례집 · 표준안)
│   ├── 30_topic_support/             7   (environment 2 · community 1 · digital 1 ·
│   │                                      cultural_diversity 1 · economy_finance 1 ·
│   │                                      social_emotional 1)
│   ├── 40_observation_evaluation/    4
│   ├── 50_legal_safety/              5
│   ├── 60_operation_guides/          3
│   ├── public_field_cases/           1
│   └── _archive/                     1
└── samples/                         349 파일
    ├── monthly/                     220
    ├── yearly/                      125
    └── weekly/                        4
```

### 1.2 신규 판정 — 파일명이 아니라 SHA-256으로 대조했다

2026-09-12 시점 inventory(175건)와 현재(349건)를 대조했다.

| 분류 | 건수 | 근거 |
|---|---:|---|
| `EXISTING_SOURCE` | 175 | path + SHA-256 둘 다 일치 |
| **`NEW_SOURCE`** | **174** | SHA-256이 기존 어디에도 없음 |
| `DUPLICATE` | **0** | 기존과 내용 동일한데 경로만 다른 파일 없음 |
| `POSSIBLE_DUPLICATE` | **0** | 신규 174건 내부에서도 SHA 중복 없음 |

**신규 174건 = 고유 SHA 174개. exact duplicate 0건이다.**

| 축 | 내역 |
|---|---|
| 문서군 | monthly 109 · yearly 64 · weekly 1 |
| 본문 기준 doc_type | MONTHLY_PLAN 97 · YEARLY_PLAN 52 · WEEKLY_PLAN 1 · UNKNOWN 24 |
| 판독 | 판독 가능 164 · image-only 10 |
| 설립유형 | 국공립 70 · 직장 36 · 민간 34 · 사회복지법인 21 · 가정 2 · 법인단체 2 · 미상 9 |
| 기관 | 신규 파일이 속한 기관 57곳, **기존 Corpus에 없던 기관 55곳** |

`UNKNOWN` 24건은 오류가 아니다. `< 7월 4세 놀이 이야기 >`처럼 표제에 `계획안`이라는
낱말이 없는 양식이며, 본문에는 생활주제·시기·연령·주차 구조가 모두 있다.
**이 UNKNOWN 중 7건이 뒤에서 가장 중요한 만4세 단일연령 근거가 된다.**

### 1.3 Official 쪽은 이번 배치에 실질적 신규가 없다

`references/official/` 33건 중 최근 mtime을 가진 7건
(`소규모 유치원 공동교육과정` · `놀이 쏙 경제금융 톡` · `유아 환경교육 지원자료` ·
`지속가능발전 기반 유아환경교육` · `따뜻한 말 한마디` · `2025 문화다양성 이음교육` ·
`2025 5세 이음교육 표준안`)은 **전부 `docs/analysis/monthly-content-vnext-design.md`
(2026-09-13)에서 이미 분석 대상으로 다뤄졌다.** 그 문서의 §Theme Crosswalk와 License 표에
그대로 등재되어 있다.

**따라서 이번 배치의 실질 신규는 기관 Sample 174건이다.**

---

## 2. 신규 자료 Inventory (요약)

174건 전체를 파일 단위로 나열하는 대신, **Evidence 역할이 큰 기관** 순으로 정리한다.
전체 목록은 `analysis/tmp/new_reference_impact.json`에 있다.

| 기관 | 파일 | 설립 | 연도 | 문서군 | 월 커버 | 단일연령 면 | 주차 구조 | 바깥놀이 행 | Evidence 역할 |
|---|---:|---|---|---|---|---|---|---|---|
| **부산광역시청어린이집** | 14 | 직장 | 2025–26 | monthly 12 + yearly 2 | **3~2월 12개월 전부** | **만3·만4·만5 각각 별도 면** | 주차 번호 + `주제 선정 배경` | 있음 (`바깥` 행) | **INSTITUTION_SAMPLE — 만4세 단일연령 12개월 시리즈** |
| **연제구연산더샵어린이집** | 12 | 국공립 | 2025–26 | monthly | 3~9월 · 10~2월 | 만3 / 만4 별도 면 | `실내놀이`/`바깥놀이` 행 | 있음 | INSTITUTION_SAMPLE — 만4세 단일연령 7개월 |
| 연제구레이카운티1단지어린이집 | 13 | 국공립 | 2026 | monthly | 3~2월 | 혼합 위주 | `예상놀이주제`+놀이기간 | 있음 | INSTITUTION_SAMPLE |
| 무지개어린이집 | 13 | — | 2026 | monthly | 3~2월 | 혼합 | `생활주제` | 있음 | INSTITUTION_SAMPLE |
| 유림자연어린이집 | 13 | — | 2026 | monthly | 3~2월 | 혼합 | `생활주제`+주차 | 있음 | INSTITUTION_SAMPLE |
| 한나어린이집 | 13 | 민간 | 2025–26 | monthly | 3~2월 | 혼합(만3 / 만4-5) | `주제`+1~5주 | 있음 | INSTITUTION_SAMPLE |
| 정성어린이집 | 13 | — | 2026 | monthly | 3~2월 | 혼합 | 주차 | 있음 | INSTITUTION_SAMPLE |
| 공동직장어린이집 | 13 | 직장 | 2026 | monthly | 3~2월 | 만5 단일 다수 | `주제선정` | 있음 | INSTITUTION_SAMPLE |
| 초읍소현어린이집 | 8 | — | 2026 | monthly | 부분 | 복수 단일연령 면 | `생활주제` | 있음 | INSTITUTION_SAMPLE |
| **가야어린이집** | 6 | 국공립 | 2026 | monthly 3 + yearly 3 | 8~10월 | **만3 / 만4 / 만5 파일 분리** | 있음 | 있음 | INSTITUTION_SAMPLE — 연령별 파일 분리형 |
| 예지어린이집 | 3 | 사회복지법인 | 2026 | yearly·weekly | — | 만3/만4/만5 면 | 주간 구조 | 일부 | INSTITUTION_SAMPLE |
| 거제드림 · 서귀포하늘 · 그린 · 구산 · 굿키즈 | 각 1 | 혼합 | 2026 | yearly | 연간 | 만4세 면 포함 | 연간 | — | 연간 Theme Context |
| 나머지 34곳 | 각 1–2 | 혼합 | 2026 | yearly 중심 | 연간 | 대부분 혼합 | 연간 | — | Theme / 연간 구조 Context |

`machine readable`: 신규 174건 중 164건이 `pdftotext` 판독 가능, 10건은 image-only다.
**이 보고서의 모든 수치는 판독 가능 164건에서만 계산했다.**

---

## 3. 만4세 Evidence 재평가 — 이번 분석의 핵심

### 3.1 두 가지 "만4세 근거"를 구분한다

| 축 | 뜻 | Baseline |
|---|---|---|
| **(A) Catalog 내부 Evidence** | `activity_reference_v0.2.1`이 실제로 보유한 age4 단일연령 근거 | 문제의 **`4`** |
| **(B) Corpus 내 근거 가용량** | `references/samples/`에 존재하는 만4세 단일연령 면 | 아직 대부분 미ingest |

두 수치는 다르다. (A)는 61개 origin만 읽어 만든 것이고, (B)는 349개 파일 전체다.
**이번 배치가 바꾼 것은 (B)이며, (A)는 아직 그대로다.**

### 3.2 (A) Catalog 내부 — 변하지 않았다 (아직 반영 전)

`data/activities/activity_reference_v0_2_1.json`을 직접 집계한 결과다.

| 연령 | supported activities | 단일연령 evidence 보유 | 혼합 근거만 |
|---|---:|---:|---:|
| 만3세 | 177 | 101 | 76 |
| **만4세** | **99** | **4** | **95** |
| 만5세 | 99 | 20 | 79 |

Evidence 행 단위로는 288건 중 `age_scope == [4]`가 **7건 · 기관 2곳**
(공립아이사랑어린이집 · 시립새봄어린이집)뿐이다.

**지시서에 적힌 baseline(`age4 supported ≈ 100` / `single-age 4` / `mixed-only ≈ 96`)이
그대로 재현된다.**

### 3.3 (B) Corpus 가용량 — 페이지 단위로 다시 셌다

문서 단위 연령 판정은 틀린다. 한 PDF 안에 만3세 면과 만4세 면이 따로 있는 자료가
실제로 있기 때문이다. 그래서 `\f`로 페이지를 나눈 뒤 **면마다** 연령을 판정했다.

판정 규칙: 범위(`만3~5세`)·열거(`만4,5세`)·`혼합` 표기가 하나라도 있으면
그 면은 단일연령 근거가 아니다. 같은 면에 `3세`와 `5세`가 따로 적혀 있어도 아니다.

| 지표 | Before (175건) | After (349건) | 변화 |
|---|---:|---:|---:|
| age3 단일연령 면 | 88 | 180 | **+92** |
| age3 단일연령 기관 | 32 | 54 | +22 |
| **age4 단일연령 면** | **27** | **57** | **+30** |
| **age4 단일연령 기관** | **14** | **23** | **+9** |
| age4 혼합 근거만 있는 기관 | 22 | 50 | +28 |
| age5 단일연령 면 | 33 | 71 | **+38** |
| age5 단일연령 기관 | 18 | 35 | +17 |

**Activity로 쓸 수 있는가**가 더 중요하다. 바깥놀이 행을 가진 monthly 면만 세면:

| 조건 | Before | 신규분 | 합계 |
|---|---:|---:|---:|
| 만3세 단일연령 + 바깥놀이 행 | 52면 / 10기관 | +63면 / 9기관 | 115면 |
| **만4세 단일연령 + 바깥놀이 행** | **5면 / 3기관** | **+20면 / 3기관** | **25면 / 6기관** |
| 만5세 단일연령 + 바깥놀이 행 | 11면 / 7기관 | +19면 / 5기관 | 30면 |

**만4세는 5면 → 25면(5배), 3기관 → 6기관(2배)이 됐다.**

### 3.4 §4 분류

| 분류 | 신규분 내역 |
|---|---|
| **`AGE4_SINGLE_INSTITUTION_EVIDENCE`** | **9기관 30문서.** monthly는 부산광역시청(12개월) · 연제구연산더샵(3~9월 7개월) · 가야(8~10월). yearly는 거제드림 · 서귀포하늘 · 구산 · 그린 · 굿키즈 · 예지 |
| `AGE4_EXPLICIT_OFFICIAL_EVIDENCE` | **이번 배치에서 0건 추가** (§3.5 참조 — 기존 자료에 이미 있었다) |
| `AGE4_MIXED_AGE_EVIDENCE` | 신규 38기관에서 만4세가 언급되나 범위·열거 표기다 |
| `AGE4_INFERRED_ONLY` | 파일명에 `만4`가 있으나 본문에 단일연령 표기가 없는 건. **강한 근거로 계산하지 않았다** |

원문 확인 예 (추정 아님):

```text
2026_국공립_연제구연산더샵어린이집_만3세,만4세_월간계획안(7월).pdf  page 1
  < 7월 4세 놀이 이야기 >
  생활주제   여름   시기 2026.06.29.~2026.08.01.   연령   4세

2026_직장_부산광역시청어린이집_만3세,만4세,만5세_월간계획안(7월).pdf  page 2
  예상놀이주제 신나는 여름   - 만 4세 뱃고동반 -
  바깥   - 여름 과일 신체 놀이하기
```

### 3.5 Official / Public Field 축은 따로 센다 (§12)

합산하지 않는다. 그리고 **이번 배치의 증가분이 아니다.**

| Source | Type | age3 case | **age4 case** | age5 case | 근거 |
|---|---|---:|---:|---:|---|
| 놀이를 지원하는 교사의 역할_최종보고서 | OFFICIAL_PLAY_CASE | 6 | **5** | 5 | `연령 / 학급인원 4세 / 22명` 형태의 사례 헤더 |
| 놀이 유아가 세상을 만나고 살아가는 힘 | OFFICIAL_PLAY_CASE | 7 | **5** | 10 | 문서 자체 진술: `만3세 반(7사례), 만4세 반(5사례), 만5세 반(10사례), 만4,5세 혼합반(1사례)` |
| 자연과 아이다움을 살리는 생태놀이 | OFFICIAL_PLAY_CASE | ≥2 | **≥2** | ≥3 | `4세반 담임교사로…`, `4세반 유아 15명으로…` |
| 그림책 놀이로 교육·보육과정 실행하기 | OFFICIAL_PLAY_CASE | 1 | **3** | 1 | 사례 표의 연령 열 |
| 2025 5세 이음교육 사례집 / 표준안 | OFFICIAL_AGE_SPECIFIC | 0 | 0 | 다수 | 만5세 전용 |
| 서울센터 놀이기록 공모전 사례집 | PUBLIC_FIELD_CASE | 일부(만3세) | 0 | 0 | `구름반(만 3세)`, `연령:만3세` |

**축별 표기 (합산 금지)**

```text
institution_age4_single   : 23 기관 / 57 면   (신규 +9 기관 / +30 면)
official_age4_case        : 약 15 case        (신규 증가 0 — 기존 자료에 이미 존재)
public_field_age4_case    : 0
```

> **이전 분석의 정정**: `monthly-content-vnext-design.md`는 Official Age Evidence를
> "만5세 2건(이음교육)"만으로 집계했다. 위 표대로 `10_play_cases/` 안에 **case 단위
> 만4세 근거가 약 15건 이미 있었다.** 파일 단위로만 보고 case 단위를 보지 않은 탓이다.
> 이것은 신규 자료의 효과가 아니라 **기존 자료의 미집계분**이므로 분리해 기록한다.

---

## 4. 월별 Evidence 변화 (§6)

### 4.1 판정 기준

Monthly 문서의 **면** 단위로 세고, 같은 기관은 1로 센다.

```text
STRONG      단일연령 독립기관 >= 3
MODERATE    단일연령 독립기관 == 2, 또는 1이면서 그 면에 바깥놀이 행이 있음
WEAK        단일연령 독립기관 == 1 (바깥놀이 행 없음), 또는 혼합 근거 기관 >= 3
VERY_WEAK   그 외
```

표기 `(단N/전N/바N)` = 단일연령 독립기관 / 연령 언급 독립기관 / 단일연령+바깥놀이 행 면.

### 4.2 BEFORE — 기존 자료만

| 월 | 만3세 | 만4세 | 만5세 |
|---|---|---|---|
| 1월 | STRONG (단4/전6/바4) | **WEAK** (단1/전4/바0) | WEAK (단1/전4/바0) |
| 2월 | STRONG (단4/전6/바3) | **WEAK** (단1/전4/바0) | WEAK (단1/전4/바0) |
| 3월 | STRONG (단5/전7/바5) | MODERATE (단1/전4/바1) | MODERATE (단2/전5/바3) |
| 4월 | STRONG (단4/전6/바4) | **WEAK** (단1/전4/바0) | MODERATE (단1/전4/바1) |
| 5월 | STRONG (단4/전6/바3) | MODERATE (단1/전4/바1) | MODERATE (단2/전5/바1) |
| **6월** | STRONG (단4/전6/바4) | **WEAK** (단1/전4/바0) | **WEAK** (단1/전4/바0) |
| **7월** | STRONG (단4/전6/바3) | **WEAK** (단1/전4/바0) | **WEAK** (단1/전4/바0) |
| **8월** | STRONG (단5/전8/바6) | MODERATE (단1/전5/바1) | MODERATE (단2/전5/바1) |
| 9월 | STRONG (단8/전11/바8) | STRONG (단3/전8/바2) | STRONG (단4/전7/바3) |
| 10월 | STRONG (단4/전6/바4) | **WEAK** (단1/전4/바0) | MODERATE (단1/전4/바1) |
| 11월 | STRONG (단4/전6/바4) | **WEAK** (단1/전4/바0) | WEAK (단1/전4/바0) |
| **1월** | STRONG (단4/전6/바4) | **WEAK** (단1/전4/바0) | WEAK (단1/전4/바0) |
| 12월 | STRONG (단4/전5/바4) | **WEAK** (단1/전2/바0) | MODERATE (단1/전2/바1) |

### 4.3 AFTER — 신규 포함

| 월 | 만3세 | 만4세 | 만5세 |
|---|---|---|---|
| 1월 | STRONG (단7/전13/바6) | MODERATE (단2/전10/바1) | STRONG (단3/전10/바2) |
| 2월 | STRONG (단8/전14/바7) | MODERATE (단2/전11/바1) | STRONG (단3/전11/바2) |
| 3월 | STRONG (단12/전16/바12) | **STRONG** (단3/전11/바3) | STRONG (단5/전12/바6) |
| 4월 | STRONG (단11/전14/바11) | **STRONG** (단3/전11/바2) | MODERATE (단2/전10/바2) |
| 5월 | STRONG (단11/전15/바10) | **STRONG** (단3/전11/바3) | STRONG (단3/전11/바2) |
| **6월** | STRONG (단11/전14/바10) | **STRONG** (단3/전11/바2) | MODERATE (단2/전10/바1) |
| **7월** | STRONG (단11/전14/바10) | **STRONG** (단3/전10/바2) | STRONG (단3/전10/바2) |
| **8월** | STRONG (단13/전17/바13) | **STRONG** (단4/전13/바4) | STRONG (단4/전12/바3) |
| 9월 | STRONG (단15/전21/바13) | STRONG (단5/전17/바4) | STRONG (단6/전16/바5) |
| 10월 | STRONG (단8/전14/바7) | MODERATE (단2/전11/바1) | STRONG (단3/전11/바2) |
| 11월 | STRONG (단8/전14/바8) | MODERATE (단2/전11/바1) | STRONG (단3/전11/바1) |
| **1월** | STRONG (단7/전13/바6) | MODERATE (단2/전10/바1) | STRONG (단3/전10/바2) |
| 12월 | STRONG (단8/전13/바8) | MODERATE (단2/전9/바1) | STRONG (단3/전9/바2) |

### 4.4 등급 분포

| 등급 | Before | After |
|---|---:|---:|
| STRONG | 14 | **29** |
| MODERATE | 9 | 7 |
| WEAK | **13** | **0** |
| VERY_WEAK | 0 | 0 |

**WEAK 13칸이 전부 사라졌다.**

### 4.5 취약 4개월 상세

| 월 · 연령 | Before | After | 새로 들어온 단일연령 기관 |
|---|---|---|---|
| 6월 만4세 | WEAK (단1) | **STRONG (단3)** | 부산광역시청 · 연제구연산더샵 |
| 6월 만5세 | WEAK (단1) | MODERATE (단2) | 부산광역시청 |
| 7월 만4세 | WEAK (단1) | **STRONG (단3)** | 부산광역시청 · 연제구연산더샵 |
| 7월 만5세 | WEAK (단1) | **STRONG (단3)** | 공동직장 · 부산광역시청 |
| 8월 만4세 | MODERATE (단1) | **STRONG (단4)** | 가야 · 부산광역시청 · 연제구연산더샵 |
| 8월 만5세 | MODERATE (단2) | **STRONG (단4)** | 가야 · 부산광역시청 |
| 1월 만4세 | WEAK (단1) | MODERATE (단2) | 부산광역시청 |
| 1월 만5세 | WEAK (단1) | **STRONG (단3)** | 공동직장 · 부산광역시청 |
| 6·7·8·1월 만3세 | STRONG (단4~5) | STRONG (단7~13) | 8~9곳 추가 |

---

## 5. Week Experience / Sub-theme 재평가 (§7)

### 5.1 전체 변화

| 지표 | Before | After |
|---|---:|---:|
| Week Experience 행을 가진 Monthly 문서 | **33** | **88** |
| 기관 | **9** | **17** |
| 월 커버 | 12 | 12 |
| Template Family 소속 문서 | 12 | 12 |

Coverage 등급 (기준: MODERATE = 독립source 3+ & 문서 4+ / WEAK = 2 / VERY_WEAK = 1)

| 등급 | Before | After |
|---|---:|---:|
| MODERATE | 6개월 | **12개월** |
| WEAK | 2개월 | 0 |
| VERY_WEAK | **4개월 (6·7·8·1월)** | **0** |

월별 After (문서/독립source)

```text
 3월 8/8   8/8   8/8      6월 6/6   5/5   6/6      9월 8/8   8/8   9/9     12월 7/6  4/3  5/4
 4월 8/8   5/5   6/6      7월 6/6   5/5   6/6     10월 7/7   5/5   6/6      1월 5/5  4/4  5/5
 5월 10/9  7/6   8/7      8월 6/6   5/5   6/6     11월 8/7   6/5   7/6      2월 4/4  2/2  3/3
                                                                    (만3 / 만4 / 만5 순)
```

### 5.2 원문 label (보존)

Canonical화하지 않았다. 신규분에서 관찰된 빈도:

```text
관심 123 · 흥미 110 · 예상놀이 79 · 소주제 53 · 주제 선정 배경 36 ·
함께 하는 놀이 23 · 놀이 이야기 22
```

기존분에는 없던 label이 셋 새로 관찰된다 — `주제 선정 배경`(부산광역시청),
`함께 하는 놀이`(연제구연산더샵), `놀이 이야기`(연제구연산더샵).
앞의 둘은 **주차가 아니라 월 전체의 의도**를 적는 칸이라 주차 흐름 근거로는 쓸 수 없다.

### 5.3 Q7 답변

**Q7-1 — 이전 `VERY_WEAK`였던 6·7·8·1월에 새 독립 기관 Evidence가 추가되었는가?**
**그렇다.** 네 달 모두 `VERY_WEAK → MODERATE`다. 6·7·8월은 독립 source 5~6곳,
1월은 4~5곳이다.

**Q7-2 — 만4세 단일연령 Week Experience Evidence가 생겼는가?**
**생겼다.** Before 14면 / 3기관(공립아이사랑 · 두루미 · 시립새봄) →
신규 +20면 / 3기관(가야 · 부산광역시청 · 연제구연산더샵) = **34면 / 6기관.**

**Q7-3 — 동일 월에서 기관 간 반복되는 Week Concept가 증가했는가?**
**증가했다.** 예: 5월 `가족` 독립source 8 · `나/몸/마음` 5, 8월 `이동/교통` 5,
3월 `친구/우리반` 5, 4월 `자연/동식물` 5 · `물/여름놀이` 4, 1월 `도구/기계/디지털` 3.
이전에는 대부분 1~2였다.

**Q7-4 — 주차 순서까지 반복되는 Evidence가 증가했는가?**
**거의 증가하지 않았다.** position별 concept 분포는 여전히 평평하다.

```text
W1: 나/몸/마음(9), 날씨/계절변화(8), 친구/우리반(7), 환경/자원(6)
W2: 나/몸/마음(4), 물/여름놀이(4), 날씨/계절변화(4), 도구/기계/디지털(3)
W3: 가족(5), 친구/우리반(4), 전통/명절(4), 자연/동식물(4)
W4: 가족(4), 도구/기계/디지털(3), 안전(3), 자연/동식물(2)
W5: 친구/우리반(2), 환경/자원(2), 안전(1), 도구/기계/디지털(1)
```

같은 concept가 여러 position에 고르게 나타난다. **"어떤 경험이 몇 주차에 오는가"에 대한
기관 간 합의는 여전히 관찰되지 않는다.**

---

## 6. Activity Reference 개선 가능성 (§8)

### 6.1 관찰 결과

신규 단일연령 monthly 면에서 바깥놀이 행만 뽑았다.

```text
관찰된 바깥놀이 후보 줄 : 177
정규화 고유 label       : 160
v0.2.1에 없는 label     : 150  (94%)
```

> **주의**: 이 숫자는 **관찰값**이지 Catalog 반영 형태가 아니다. `pdftotext -layout` 줄
> 기반이라 v0.2.1을 만든 셀 기하 추출보다 거칠다. `[대체놀이]` 표기가 섞인 줄도
> 포함되어 있어 `indoor_alternative` 제외를 다시 적용해야 한다.

월 × 단일연령별 **v0.2.1 미보유** label 관찰 수:

| 월 | 만3세 | 만4세 | 만5세 |
|---|---:|---:|---:|
| 1월 | 3 | 1 | 2 |
| 2월 | 7 | 1 | 2 |
| 3월 | 10 | **5** | 6 |
| 4월 | 11 | 3 | 0 |
| 5월 | 7 | **4** | 0 |
| 6월 | 6 | 1 | 0 |
| 7월 | 11 | **5** | 1 |
| 8월 | 21 | **8** | 3 |
| 9월 | 19 | 0 | 4 |
| 10월 | 4 | 1 | 0 |
| 11월 | 2 | 1 | 0 |
| 12월 | 7 | 1 | 1 |

### 6.2 §8 분류 (관찰 기준)

| 분류 | 관찰 | 비고 |
|---|---|---|
| `NEW_ACTIVITY_CANDIDATE` | 150 label | 예: `물놀이 공원 만들기`, `물총놀이`, `여름 과일 신체 놀이하기`, `허수아비 놀이하기`, `떨어지는 낙엽을 잡아요`, `초등학교 탐방` |
| `EXISTING_ACTIVITY_NEW_EVIDENCE` | 10 label | 신규 Source에서 관찰됐고 v0.2.1에 이미 있음 → **evidence_strength / age_scope 보강분** |
| `POSSIBLE_DUPLICATE` | 다수 | `물놀이를 가요` ↔ `물놀이 공원 만들기` 등 정규화 필요 |
| `CONTEXT_DEPENDENT` | 다수 | `정리정돈을 해요`, `예절을 알아요`, `남의 물건을 가져오지` (가야 8월) — 바깥놀이 행에 있으나 생활습관 문장이다 |
| `NOT_OUTDOOR` | 확인됨 | `[대체놀이] 겨울 하키 놀이하기`, `[대체놀이] 종이비행기를 날려요` — 실내대체 표기 |
| `AMBIGUOUS` | 다수 | `<대근육> 우리들의 추억의 장소를` 처럼 줄이 잘린 것 |

**기존에 후보가 얇았던 Month/Age의 신규 관찰 예**

```text
 6월 만4세  1건  모래로 동네 공원만들기 (연제구연산더샵)
 7월 만4세  5건  물놀이 공원 만들기 · 물총놀이 · 물놀이를 가요 · 칫솔 이어 달리기 (연제구연산더샵)
                여름 과일 신체 놀이하기 (부산광역시청)
 8월 만4세  8건  움직이는 교통기관 관찰해요 · 우리동네 버스 정류장을 살펴봐요 (연제구연산더샵) 등
11월 만4세  1건  허수아비 놀이하기 (부산광역시청)
 2월 만5세  2건  우리들의 추억의 장소 · 초등학교 탐방 (공동직장 · 부산광역시청)
```

Production에서 후보가 4개(= 주차 수)뿐이던 **2월·11월 만4·만5세**에도 신규 관찰이
생겼지만 **각 1~2건에 그친다.** 이 두 달은 여전히 가장 얇다.

---

## 7. Theme Coverage 개선 여부 (§9)

`주제` 계열 줄에서만 매칭했다(본문 아무 데나 나온 낱말은 세지 않았다).

| Theme | Before | 신규 추가 | After 합계 | 평가 |
|---|---|---|---|---|
| **우리 동네** | 7면 / 3기관 | +9면 / 5기관 | 16면 / 8기관 | 가장 크게 개선. `우리 동네는 거제동`, `우리동네/월드컵` 등 실제 월 주제로 확인 |
| **여름** | 5면 / 4기관 | +11면 / 6기관 | 16면 / 10기관 | 크게 개선 |
| **교통기관** | 6면 / 4기관 | +7면 / 6기관 | 13면 / 10기관 | 개선. `교통기관 알아보기`(유림자연), `교통기관(자동차)`(무지개) |
| **성장한 우리** | 5면 / 5기관 | **+2면 / 2기관** | 7면 / 7기관 | **가장 적게 개선** |

```text
Theme: 우리 동네
Before:  candidate scarcity (2026-06 만4세 후보 pool 7, theme_links 0/7)
New Sources:
  - 연제구레이카운티1단지  `우리 동네는 거제동` (6월)
  - 연제구연산더샵         `우리동네/월드컵` (6월, 만4세 단일연령 면)
  - 무지개                 `우리동네`
  - 초읍소현 · 유림자연 · 한나
After Potential:
  - 6월 만4세 단일연령 기관 1 → 3 (STRONG)
  - 6월 만4세 바깥놀이 후보 신규 관찰 1건 (`모래로 동네 공원만들기`)
  - **다만 theme_links 자체는 Catalog 필드이므로 새 Source가 자동으로 채워주지 않는다.**
    v0.2.2 작업에서 사람이 연결해야 한다.

Theme: 성장한 우리
Before:  2027-02 만5세 후보 pool == 주차 수 (4/4), 선별 여지 0
New Sources:
  - 연제구연산더샵  `소중했던 우리반` (2월)
  - 공동직장        `새해를 맞이해 한 살 더 성장한 나의…`
  - 한나            `형님이 되어요/졸업`
After Potential:
  - 2월 만5세 바깥놀이 후보 신규 2건 관찰 (`초등학교 탐방`, `우리들의 추억의 장소`)
  - pool 4 → 6 정도. **여전히 얇다.**
```

---

## 8. 만3세와 만4세 차별화 가능성 (§10)

### 8.1 관찰

**한 문서 안에 서로 다른 단일연령 면이 2개 이상**인 자료가 59건이고, 그중 **31건이 신규**다
(monthly 21건). 기관: NPS국민연금 · 거제드림 · 공동직장 · 굿모닝 · 그린 ·
**부산광역시청** · 서귀포하늘 · **연제구연산더샵** · 예지 · 월드림 · 초읍소현.

이 구조가 결정적이다. **같은 기관 · 같은 월 · 같은 양식인데 연령만 다른 면**이 나란히
있으므로, 연령 차이가 기관 차이나 양식 차이에 오염되지 않는다.

### 8.2 원문 대조 (부산광역시청어린이집, `바깥` 행)

```text
2025_직장_부산광역시청어린이집_..._월간계획안(10월).pdf
  만3세  바깥  - 가을 날씨를 느껴요
  만4세  바깥  - 떨어지는 낙엽을 잡아요

2025_직장_부산광역시청어린이집_..._월간계획안(11월).pdf
  만3세  바깥  - 흙과 물이 만났어요
  만4세  바깥  - 허수아비 놀이하기

2025_직장_부산광역시청어린이집_..._월간계획안(12월).pdf
  만3세  바깥  - 동백반 트리를 꾸며요
  만3세         - 몸풀기 운동을 하고 바깥놀이를 해요
  만4세  바깥  [대체놀이] 방한용품 빙고 게임하기
  만5세  바깥  - 겨울 옷 입기 게임

2026_직장_부산광역시청어린이집_..._월간계획안(7월).pdf
  만3세  바깥  - 여름 맞이 대청소 (블록을 씻어주어요)
  만4세  바깥  - 여름 과일 신체 놀이하기
```

### 8.3 판정

| 경우 | 판정 | 근거 |
|---|---|---|
| **A. Activity 자체가 다름** | **확인됨** | 위 원문. 같은 기관·같은 월·같은 주제인데 연령별 바깥놀이 항목이 서로 다르다 |
| B. 같은 Activity지만 지원 방식·복잡도 근거가 다름 | **부분 확인** | 연제구연산더샵은 만3/만4 면의 `기대되는 모습` 문장이 다르다. 다만 **놀이 자체의 난이도를 명시한 문장은 없다** |
| C. 차이를 만들 근거가 여전히 없음 | 월에 따라 해당 | 2월·10월·11월·12월 만4세는 여전히 바깥놀이 행 보유 독립기관 1곳(부산광역시청)뿐이다 |

**LLM 일반상식으로 차이를 만들지 않았다.** 위는 전부 원문 인용이다.

---

## 9. Source Independence (§13)

| 점검 | 결과 |
|---|---|
| exact duplicate (SHA-256) | 신규 174건 / 고유 SHA 174 → **0건** |
| 기존 Template Family(마성·우리·키즈로스쿨·혜솔) 소속 신규 파일 | **0건** |
| 같은 기관 다수 파일 | 부산광역시청 14 · 무지개 13 · 연제구레이카운티1단지 13 · 유림자연 13 · 한나 13 · 정성 13 · 공동직장 13 · 연제구연산더샵 12 |
| 같은 접두어(지자체·운영주체) | 연제구 29(2기관) · 부산광역시청 14(1기관) · 근로복지공단 2(2기관) |
| 연제구 계열 본문 유사도 | 연제구레이카운티1단지 ↔ 연제구연산더샵 **6-gram Jaccard 0.007** → **별개 Source다** |

### 중대한 편중 — 반드시 함께 읽어야 한다

**부산광역시청어린이집 한 곳이 만4세·만5세 단일연령 근거의 12개월 전부를 혼자 채운다.**

| 월 | 만4세 단일연령 + 바깥놀이 행 보유 독립기관 |
|---|---|
| 1·2·10·11·12월 | **부산광역시청 1곳뿐** |
| 4·6·7월 | 부산광역시청 + 연제구연산더샵 (2곳) |
| 3·5월 | 두루미 + 부산광역시청 + 연제구연산더샵 (3곳) |
| 8월 | 가야 + 두루미 + 부산광역시청 + 연제구연산더샵 (4곳) |
| 9월 | 공립아이사랑 + 부산광역시청 + 시립새봄 + 연제구연산더샵 (4곳) |

즉 **§4의 등급 상승 중 상당 부분이 이 한 기관에 의존한다.** 이 기관을 빼면
만4세는 8개월이 다시 1곳 이하가 된다. 파일 수(14건)가 아니라 **독립 Source 수(1)**로
세어야 한다.

---

## 10. Monthly LLM Planner 관점 (§14)

```text
Evidence / Reference → Relevant Retrieval → LLM → Monthly Planning → Deterministic Validation
```

이 구조에서 신규 Source의 역할을 분류한다.

| 역할 | 신규 Source 기여 | 등급 |
|---|---|---|
| **Age Context** | 부산광역시청 12개월 × 3연령, 연제구연산더샵 7개월 × 2연령, 가야 3개월 × 3연령 — **같은 월·같은 기관·연령만 다른 대조쌍**이 생겼다. LLM에게 "만3세는 이렇게, 만4세는 이렇게"를 **실제 사례로** 보여줄 수 있다 | **가장 크게 기여** |
| **Few-shot examples** | 완결된 월간계획안 면이 188 → 403으로 늘었고, 주차 구조를 가진 면이 143 → 340이다. 양식 다양성(`놀이 이야기`형 · `예상놀이주제`형 · `주제 선정 배경`형)도 넓어졌다 | **크게 기여** |
| **Week Experience Context** | 문서 33 → 88, 기관 9 → 17, 12개월 전부 MODERATE. 다만 **주차 순서 근거는 여전히 없다**(Q7-4) | 중간 기여 |
| **Activity Candidates** | 미보유 label 150건 관찰. 다만 거친 추출이라 그대로 쓸 수 없고 셀 기하 재추출 + `indoor_alternative` 제외가 필요하다 | 중간 기여 (재추출 선행) |
| **Theme grounding** | 우리 동네 3→8기관, 여름 4→10, 교통기관 4→10. 단 **`theme_links`는 Catalog 필드**이며 Source가 자동으로 채우지 않는다 | 부분 기여 |
| Curriculum grounding | **기여 없음.** v0.2.1의 `curriculum_links`는 196/196이 빈 값이고 신규 Source도 누리과정 영역 태그를 달고 있지 않다 | **기여 없음** |

---

## 11. 중요한 질문에 대한 답 (§15)

### Q1 — 만4세 Evidence 부족 문제는 실제로 개선되었는가?

```text
SIGNIFICANTLY_IMPROVED
```

근거:

- 만4세 **단일연령 + 바깥놀이 행** 면: **5면 / 3기관 → 25면 / 6기관** (5배)
- 만4세 단일연령 면 전체: 27 → 57, 기관 14 → 23
- **만4세 단일연령 12개월 연속 monthly 시리즈가 처음 생겼다**(부산광역시청).
  이전에는 9월에만 3기관이 있었고 나머지 11개월은 1기관 이하였다.
- 월 × 만4세 등급: WEAK 7칸 → 0칸

**단, 다음을 함께 기록한다.**

- `activity_reference_v0.2.1` 내부 수치(**4**)는 **아직 그대로다.** 신규 174건 중
  ingest된 것은 **0건**이다. 개선된 것은 "가용량"이지 "반영분"이 아니다.
- 8개월(1·2·4·6·7·10·11·12월)은 여전히 독립기관 1~2곳이고, 그중 5개월은
  **부산광역시청 한 곳**뿐이다.

### Q2 — 만3세와 만4세를 다르게 구성할 근거가 생겼는가?

```text
YES_WITH_LIMITATIONS
```

- **YES 근거**: §8의 같은 기관·같은 월·연령별 바깥놀이 행 대조쌍이 실재한다.
  이런 문서가 신규 31건(monthly 21건)이다. 차이가 Case A(Activity 자체가 다름)로 확인된다.
- **LIMITATIONS**: 대조쌍을 monthly로 제공하는 기관은 **부산광역시청 · 연제구연산더샵 ·
  가야 3곳**뿐이고, 그중 12개월 전체를 커버하는 곳은 1곳이다.
  또 **난이도·지원 방식을 명시한 문장(Case B)은 거의 없다** — 대부분 활동명만 다르다.

### Q3 — 기존 VERY_WEAK 월(6·7·8·1월)은 각각 어느 정도 개선되었는가?

| 월 | Week Experience | 만4세 Monthly 등급 | 만4세 단일연령 독립기관 | 만4세 신규 바깥놀이 후보 |
|---|---|---|---|---|
| **6월** | VERY_WEAK → **MODERATE** (독립 5~6) | WEAK → **STRONG** | 1 → 3 | 1건 |
| **7월** | VERY_WEAK → **MODERATE** (독립 5~6) | WEAK → **STRONG** | 1 → 3 | 5건 |
| **8월** | VERY_WEAK → **MODERATE** (독립 5~6) | MODERATE → **STRONG** | 1 → 4 | 8건 |
| **1월** | VERY_WEAK → **MODERATE** (독립 4~5) | WEAK → **MODERATE** | 1 → 2 | 1건 |

6·7·8월은 확실히 개선됐다. **1월은 가장 덜 개선됐다** — 만4세 독립기관이 2곳이고
바깥놀이 행 보유 기관은 부산광역시청 1곳뿐이며, 신규 후보 관찰도 1건이다.

### Q4 — Week Experience Evidence는 충분해졌는가?

```text
PARTIALLY_READY
```

- 12개월 전부 `MODERATE`가 됐고 VERY_WEAK가 사라졌다(문서 33→88, 기관 9→17).
- 그러나 **어느 달도 그 이상 등급에 도달하지 못했고**, 무엇보다
  **주차 순서(W1→W5) 근거가 여전히 없다**(Q7-4). concept가 position 전반에 고르게 퍼진다.
- 즉 "그 달에 어떤 경험이 나오는가"는 말할 수 있게 됐지만,
  **"몇 주차에 오는가"는 여전히 Source가 답하지 않는다.**

### Q5 — Activity Candidate Scarcity는 줄어들 수 있는가?

**줄어들 수 있다. 개선되는 Month/Age는 다음과 같다.**

| 우선순위 | Month/Age | 현재 Production pool | 신규 관찰 후보 | 근거 |
|---|---|---:|---:|---|
| 1 | **8월 만4·만5세** | 7 | 만4 8건 · 만5 3건 | 단일연령 독립기관 4곳 |
| 2 | **7월 만4·만5세** | 8 | 만4 5건 · 만5 1건 | 독립기관 3곳 |
| 3 | **6월 만4세** | 7 | 1건 | 독립기관 3곳, `우리 동네` theme 5기관 추가 |
| 4 | **3·5월 만4세** | 8 | 5건 · 4건 | 독립기관 3곳 |
| 5 | 4·12월 만4세 | 9 · 7 | 3건 · 1건 | 독립기관 2~3곳 |
| — | **2·11월 만4·만5세** | **4 (= 주차 수)** | 1~2건 | **가장 덜 개선. 여전히 선별 여지 거의 없음** |
| — | 만3세 전 월 | 11~17 | 총 108건 | 이미 STRONG이었고 더 두꺼워짐 |

### Q6 — v0.2.2 Additive Patch로 가능한가?

**Activity / Evidence 축은 additive patch로 가능하다. 그러나 그것만으로는 부족하다.**

additive로 가능한 것:

- 신규 Source에서 `EXISTING_ACTIVITY_NEW_EVIDENCE` 추가 → `evidence_strength`,
  `observed_institution_count` 상승
- **`age_scope: [4]` evidence 추가 → `age_support_basis`가
  `MIXED_AGE_INFERRED` → `SINGLE_AGE_EVIDENCE`로 바뀌는 Activity 다수**
- `NEW_ACTIVITY_CANDIDATE` 추가 → 얇은 Month/Age pool 확대
- 기존 Activity 제거 없음 → v0.2.1 pin 호환 유지

additive로 **불가능한** 것:

- `curriculum_links` 196/196 공백 — 신규 Source에도 누리과정 영역 태그가 없다.
  **Reference 설계 결정이 필요하다.**
- `theme_links` 51/196 공백 — Source가 자동으로 채우지 않는다. 사람 연결 작업이다.
- 주차 순서 근거 부재 — Week Experience Reference를 새로 만들어야 하고, 그 근거도 아직 없다.
- **Ingestion 범위 결정** — 현재 미ingest monthly 면 중 바깥놀이 행 보유가 **214면**이다.
  v0.2.1이 읽은 것은 104면뿐이다. 어디까지 넣을지가 `OD-ACTIVITY-INGESTION-01`
  (재현 가능한 ingestion pipeline 부재)과 직결된다.

**결론: Activity/Evidence는 v0.2.2 additive, 나머지는 별도 설계 단계.**

### Q7 — Monthly LLM Planner 설계/구현을 진행해도 되는가?

```text
READY_WITH_EVIDENCE_GAPS
```

진행해도 되는 이유:

- Age Context와 Few-shot 예시가 **질적으로 달라졌다.** 같은 기관·같은 월·연령별 대조쌍이
  실재하므로 "연령 차이"를 LLM 일반상식이 아니라 **Source로** 줄 수 있다.
- 12개월 × 3연령 전부 최소 MODERATE 이상 Evidence가 확보됐다.
- Deterministic Validation 쪽(Rule v2, hard filter, pinning, gate)은 이미 동작하고
  회귀 방어선(1644 tests)이 있다.

그러나 다음 Gap을 안고 시작한다는 것을 명시해야 한다:

1. **주차 순서 근거 부재** — LLM이 W1~W5 흐름을 만들면 그 근거는 Source가 아니라
   LLM 일반상식이 된다. CLAUDE.md §5의 Rule/LLM 경계 관점에서 **어디까지 허용할지
   먼저 결정해야 한다.**
2. **단일 Source 편중** — 만4세 근거의 8개월이 부산광역시청 1~2곳에 의존한다.
   Few-shot이 그 기관 문체를 그대로 재현할 위험이 있다.
3. **curriculum_links 전무** — 누리과정 영역 균형을 Validation으로 검증할 수 없다.
4. **2·11월 pool 고갈** — 만4·만5세는 여전히 후보 4개다.

---

## 12. Before / After Summary (§16)

| 항목 | 이전 | 신규 자료 추가 후 | 개선도 |
|---|---|---|---|
| **만3세 Evidence** | 단일연령 88면 / 32기관 · 바깥놀이 52면 | 180면 / 54기관 · 바깥놀이 115면 | **대폭 개선** (이미 충분했고 더 두꺼워짐) |
| **만4세 Evidence** | 단일연령 27면 / 14기관 · **바깥놀이 5면 / 3기관** · Catalog 내부 `4` | 57면 / 23기관 · **바깥놀이 25면 / 6기관** · Catalog 내부 여전히 `4` (미반영) | **대폭 개선 (가용량)** / 반영 전 |
| **만5세 Evidence** | 단일연령 33면 / 18기관 · 바깥놀이 11면 | 71면 / 35기관 · 바깥놀이 30면 | **대폭 개선** |
| **6월** | WE `VERY_WEAK` · 만4 `WEAK`(1기관) | WE `MODERATE`(5~6) · 만4 `STRONG`(3기관) | **개선** |
| **7월** | WE `VERY_WEAK` · 만4 `WEAK`(1기관) | WE `MODERATE`(5~6) · 만4 `STRONG`(3기관) | **개선** |
| **8월** | WE `VERY_WEAK` · 만4 `MODERATE`(1기관) | WE `MODERATE`(5~6) · 만4 `STRONG`(4기관) | **가장 크게 개선** |
| **1월** | WE `VERY_WEAK` · 만4 `WEAK`(1기관) | WE `MODERATE`(4~5) · 만4 `MODERATE`(2기관) | **부분 개선** |
| **Week Experience** | 9기관 / 33문서 · MODERATE 6 · WEAK 2 · VERY_WEAK 4 | 17기관 / 88문서 · **MODERATE 12** | **개선** — 단 주차 순서 근거는 변화 없음 |
| **Activity Coverage** | 월×연령 36칸 중 WEAK 13 | **WEAK 0 · STRONG 29** · 미보유 label 150건 관찰 | **대폭 개선 (가용량)** |
| **Age Differentiation** | 근거 없음 (9월 3연령 결과 3/5 동일) | 같은 기관·같은 월·연령별 대조쌍 31문서 확보 | **질적 변화** — 단 3기관 의존 |

---

## 13. 여전히 필요한 추가 자료 (§17)

"자료가 더 필요하다"로 끝내지 않는다. 목표 수치의 근거는 **§4.1의 STRONG 기준(독립기관 3)**
이며, 이는 "한 기관의 관행을 전국 표준으로 일반화하지 않는다"(CLAUDE.md §8)를 만족하는
최소선으로 잡았다.

| # | Month | Age | Source Type | 현재 독립 Source | 목표 | 왜 필요한가 |
|---|---|---|---|---:|---:|---|
| 1 | **2월** | 만4·만5 | 단일연령 Monthly (바깥놀이 행 필수) | **1** (부산광역시청) | **3** | Production 후보 pool이 4개 = 주차 4개로 **선별층이 존재하지 않는다.** 후보가 하나만 빠져도 즉시 빈 칸이 된다 |
| 2 | **11월** | 만4·만5 | 단일연령 Monthly (바깥놀이 행 필수) | **1** (부산광역시청) | **3** | 위와 동일. pool 4/4 |
| 3 | **10·12월** | 만4 | 단일연령 Monthly | **1** (부산광역시청) | **3** | 등급이 MODERATE에 머물고 단일 기관 문체에 종속된다 |
| 4 | **1월** | 만4 | 단일연령 Monthly | **1** (바깥놀이 행 기준) | **3** | 4개 취약월 중 유일하게 STRONG에 못 미쳤다 |
| 5 | **4·6·7월** | 만4 | 단일연령 Monthly | 2 | **3** | 현재 STRONG 판정이 연제구연산더샵+부산광역시청 2곳에 의존한다 |
| 6 | 전 월 | 만4 | **부산광역시청 이외 기관의 12개월 시리즈** | 0 | **1 이상** | 만4세 12개월 연속 근거가 단 한 기관뿐이다. Few-shot·Age Context가 그 기관 문체에 고착될 위험 |
| 7 | 전 월 | 전 연령 | **주차 순서가 명시된 Monthly** (`1주 / 2주 / 3주 …` 칸에 서로 다른 경험) | 관찰되나 순서 합의 없음 | 기관 **5곳 이상**에서 같은 달 같은 순서 | Week Experience Layer 설계의 전제. 현재 position별 concept 분포가 평평해 순서를 주장할 근거가 없다 |
| 8 | 전 월 | 전 연령 | **누리과정 영역이 태깅된 Source** | **0** | — | `curriculum_links` 196/196 공백. 신규 Source에도 없다. **자료 수집이 아니라 Reference 설계 결정이 필요한 항목**이므로 수집 목표를 제시하지 않는다 |

---

## 14. 이번 작업에서 변경하지 않은 것 (§18)

| 항목 | 상태 |
|---|---|
| `src/` | 무변경 |
| `data/` | 무변경 — `activity_reference_v0_2_1.json` `ddbbe43f…`, `activity_reference_v0_2.json` `e27ebca3…`, `theme_reference_v0.json` `c12999fa…`, `monthly_template_a.json` `1f35322d…`, `safety_education_legal_v1.json` `5831809b…` |
| `demo-planning/` | 무변경 |
| `CLAUDE.md` | 무변경 `a723a7ee…` |
| Activity Reference / Theme Reference / Selection Rule / Prompt / LLM Planner | **무변경** |
| 테스트 | `1644 passed, 4 deselected` — 이전과 동일 |

추가된 것은 `analysis/tools/` 3개 도구와 `analysis/tmp/` 산출물, 그리고 이 보고서뿐이다.

```bash
python analysis/tools/extract_corpus.py
python analysis/tools/reclassify.py
python analysis/tools/new_reference_impact.py
python analysis/tools/new_reference_yield.py
python analysis/tools/new_reference_candidates.py
python analysis/tools/week_experience.py
```

---

```text
NEW REFERENCE EVIDENCE IMPACT

New Sources:
  기관 Sample 174건 (monthly 109 · yearly 64 · weekly 1), 전부 고유 SHA-256.
  exact duplicate 0 · possible duplicate 0 · 기존 Template Family 소속 0.
  신규 기관 55곳. 판독 가능 164 / image-only 10.
  Official 쪽 실질 신규 0건 — 최근 추가된 7건은 monthly-content-vnext-design.md가
  이미 분석 대상으로 다뤘다.
  신규 174건 중 Activity Reference에 ingest된 것: 0건 (가용량만 늘었다).

Age3:
  단일연령 88면/32기관 → 180면/54기관.  바깥놀이 행 보유 52면 → 115면.
  이미 STRONG이었고 더 두꺼워졌다. 12개월 전부 STRONG 유지.

Age4:
  단일연령 27면/14기관 → 57면/23기관.
  바깥놀이 행 보유 5면/3기관 → 25면/6기관 (5배).
  만4세 단일연령 12개월 연속 monthly 시리즈가 처음 확보됐다 (부산광역시청).
  월별 등급 WEAK 7칸 → 0칸.
  단, Catalog 내부 수치는 아직 4 그대로다 (미반영).
  단, 8개월이 독립기관 1~2곳이며 그중 5개월은 부산광역시청 한 곳뿐이다.

Age5:
  단일연령 33면/18기관 → 71면/35기관.  바깥놀이 행 보유 11면 → 30면.
  월별 등급 WEAK 5칸 → 0칸.

Weak Months:

6월:
  Week Experience VERY_WEAK → MODERATE (독립 source 5~6).
  만4세 Monthly WEAK(1기관) → STRONG(3기관: 두루미·부산광역시청·연제구연산더샵).
  신규 바깥놀이 후보 관찰 1건. Theme `우리 동네` 3기관 → 8기관.

7월:
  Week Experience VERY_WEAK → MODERATE (독립 source 5~6).
  만4세 Monthly WEAK(1기관) → STRONG(3기관). 만5세 WEAK → STRONG(3기관).
  신규 바깥놀이 후보 관찰 만4세 5건.

8월:
  Week Experience VERY_WEAK → MODERATE (독립 source 5~6).
  만4세 Monthly MODERATE(1기관) → STRONG(4기관). 만5세 MODERATE → STRONG(4기관).
  신규 바깥놀이 후보 관찰 만4세 8건 — 4개 취약월 중 가장 크게 개선.

1월:
  Week Experience VERY_WEAK → MODERATE (독립 source 4~5).
  만4세 Monthly WEAK(1기관) → MODERATE(2기관) — 유일하게 STRONG에 못 미쳤다.
  바깥놀이 행 보유 기관은 부산광역시청 1곳. 신규 후보 관찰 1건.

Week Experience:
  9기관 / 33문서 → 17기관 / 88문서. 12개월 전부 MODERATE, VERY_WEAK 0.
  만4세 단일연령 Week Evidence 14면/3기관 → 34면/6기관.
  그러나 주차 순서 근거는 변화 없음 — concept가 W1~W5에 고르게 분포한다.

Activity Coverage:
  월 × 연령 36칸 등급: STRONG 14 → 29 · MODERATE 9 → 7 · WEAK 13 → 0.
  신규 단일연령 면에서 바깥놀이 후보 줄 177개 관찰, 고유 label 160,
  v0.2.1 미보유 150 (94%). 단 거친 추출이라 셀 기하 재추출이 선행되어야 한다.
  미ingest monthly 면 중 바깥놀이 행 보유 214면 — v0.2.1이 읽은 104면의 2배.

Age Differentiation:
  같은 기관·같은 월·연령별 단일연령 면이 함께 있는 문서 31건 신규 확보.
  원문 대조로 Case A(Activity 자체가 다름) 확인:
    10월  만3 가을 날씨를 느껴요 / 만4 떨어지는 낙엽을 잡아요
    11월  만3 흙과 물이 만났어요 / 만4 허수아비 놀이하기
    12월  만3 동백반 트리를 꾸며요 / 만5 겨울 옷 입기 게임
     7월  만3 여름 맞이 대청소 / 만4 여름 과일 신체 놀이하기
  Case B(같은 Activity, 지원 방식 차이)를 명시한 문장은 거의 없다.
  제공 기관은 monthly 기준 3곳(부산광역시청·연제구연산더샵·가야)뿐이다.


MOST IMPORTANT IMPROVEMENT:
  만4세 단일연령 12개월 연속 Monthly 시리즈(부산광역시청)와,
  같은 기관·같은 월·연령만 다른 대조쌍 31문서의 확보.
  이전에는 만4세를 만3세와 다르게 구성할 Source 근거가 사실상 없었고
  9월에만 3기관이 있었다. 이제 12개월 전부에 단일연령 만4세 근거가 있고,
  연령 차이를 LLM 일반상식이 아니라 원문으로 보여줄 수 있다.

BIGGEST REMAINING GAP:
  주차 순서(W1→W5) 근거가 여전히 0이다.
  Week Experience 문서가 33 → 88로 늘고 12개월 전부 MODERATE가 됐는데도
  position별 concept 분포는 평평하다. 어떤 경험이 몇 주차에 오는지에 대한
  기관 간 합의가 관찰되지 않는다.
  이와 함께: 만4세 근거 8개월이 부산광역시청 1~2곳에 의존하고,
  2·11월 만4·만5세 후보는 여전히 주차 수와 같으며,
  curriculum_links는 196/196이 공백이고 신규 Source도 이를 채우지 못한다.


LLM PLANNER READINESS:

READY_WITH_EVIDENCE_GAPS


FINAL VERDICT:

NEW_REFERENCES_SIGNIFICANTLY_IMPROVED_EVIDENCE
```
