# Monthly LLM Planner vNext — L2 Evidence Retrieval

- 작성일: 2026-09-13
- 선행: L1 Evidence Ingestion 완료 (`OD-ACTIVITY-INGESTION-01` CLOSED)
- 입력 Artifact: `institution-evidence-ingestion-v0.1.0`
  `content_sha256 = 52b409557d3503422aa0109664298976bd7f831ed18304b818aaad936916e5ea`
- 산출물
  - Production 코드 `src/ssuksak/planning/retrieval/`
  - 테스트 `tests/retrieval/` (110건 신규)
  - 감사 도구 `analysis/experiments/monthly_llm_vnext/audit_l2_retrieval.py`
- 범위 밖: L3 Context Packet · L4 LLM Planner · Generate/Regenerate 통합 · Demo · Golden

---

## 1. Scope

L2가 푸는 문제는 "Evidence가 부족하다"가 아니다.

```text
Evidence Store   12,367 records  (VALID 11,268)
Activity Catalog    196 canonical activities
```

에서 **특정 요청에 필요한 소수만 결정론적이고 설명 가능하게** 고르는 것이다.

구현한 흐름:

```text
Planning Request (age + month + confirmed theme)
  → hard eligibility (L1 파생값)
  → 연령 tier
  → theme relevance ranking
  → 연령 균형 (혼합 요청)
  → source diversity
  → stable deterministic ordering
  → Retrieved Evidence Blocks
```

**LLM · Embedding API · Vector DB를 쓰지 않았다.**

---

## 2. Retrieval Architecture

```text
src/ssuksak/planning/retrieval/
├── __init__.py
├── models.py               RetrievalRequest · EvidenceBlock · RetrievalTrace
│                           MonthlyEvidenceRetrievalResult · AgeMatchKind · BlockName
├── evidence_repository.py  Strict Loader (Json / InMemory)
├── ranking.py              ngrams · theme_signals · age_match_kind
│                           balance_by_single_age · apply_source_diversity
└── retriever.py            MonthlyEvidenceRetriever · OfficialEvidencePort
```

### 2.1 Runtime은 PDF를 읽지 않는다

L2 Runtime이 읽는 것은 **Evidence Store Artifact 하나**뿐이다.
`pymupdf` · `SourceDocumentReader` · 셀 추출은 L2 Runtime dependency가 아니며,
`OD-N16`은 계속 L2 비차단 상태다.

### 2.2 Rule v2 재사용 — 의미를 바꾸지 않았다

`monthly_activity_selection.py`에 **읽기 전용 helper 하나**만 추가했다.

```python
def context_ranking_sort_key(candidate, *, calendar_month, parent_theme_id=None):
    """`select_activity_for_cell`이 쓰는 것과 정확히 같은 축을 노출한다."""
    return _sort_key(candidate, calendar_month=calendar_month,
                     used_activity_ids=frozenset(), current_activity_id=None,
                     parent_theme_id=parent_theme_id, used_curriculum_domains={})
```

Cell 단위 상태(같은 달에 이미 쓴 activity, 재생성 대상, 이미 쓴 누리과정 영역)는
Retrieval 시점에 없으므로 중립값이다. 테스트가 **내부 `_sort_key`와 값이 같음**을
고정한다(`test_context_ranking_reuses_rule_v2_axes_without_changing_them`).

Rule v2는 이제 두 역할을 가진다.

```text
기존  Monthly Cell 최종 결정          (generation_mode = RULE_ONLY)
추가  LLM Context 후보 pre-ranking     (L2)
```

---

## 3. Store Loader

`load_evidence_store_from_dict()`가 검증하는 것:

| 항목 | 실패 시 |
|---|---|
| `store_id` | `EvidenceStoreError` |
| `schema_version` | 동일 |
| `ingestion_version` | 동일 |
| `normative_status` | 동일 — **`HUMAN_APPROVED`로 둔갑한 Artifact를 로드하지 않는다** |
| `record_count` vs 실제 개수 | 동일 |
| `content_sha256` vs `build.content_sha256` | 동일 (Artifact 손상 탐지) |
| `expected_sha256` pin (선택) | 동일 |
| 각 record의 strict `EvidenceRecord` schema | 동일 |
| `record_id` 중복 | 동일 |

파일 없음 · JSON 파싱 실패도 같은 예외로 통일했다.
**조용히 무시하거나 기본값으로 보정하지 않는다**(CLAUDE.md §14).

---

## 4. Retrieval Request / Result Contract

```python
RetrievalRequest(
    target_month, calendar_month, ages, age_mode,
    confirmed_theme_id, confirmed_theme_value, week_count,
)
```

`school_year` · `daycare_ref` · `classroom_ref`는 **넣지 않았다.** Retrieval 결과를
바꾸지 않는 필드다. 필요해지면 그때 추가한다.

생성 시 검증: `calendar_month` 1~12, `ages` 비어 있지 않음, P0 Target(만3~5세),
`week_count >= 1`.

```python
MonthlyEvidenceRetrievalResult(
    request,
    blocks: dict[BlockName, EvidenceBlock],
    evidence_store_version, evidence_store_sha256,
    activity_catalog_id, activity_catalog_version,
)
```

**L2는 Prompt 문자열을 만들지 않는다.** `"[기관 근거]"` 같은 rendering은 L3다.

---

## 5. Eligibility

Ranking보다 **먼저** L1 파생값을 적용한다. L2에서 완화하지 않는다.

```text
general_grounding_eligible == (TEXT_LAYER and VALID)
outdoor_activity_eligible  == (general_grounding_eligible
                               and outdoor_play and OUTDOOR)
```

| Block | 조건 |
|---|---|
| institution_monthly_evidence | `outdoor_activity_eligible` |
| age_contrast_evidence | `outdoor_activity_eligible` + 단일연령 |
| other_outdoor_evidence | `outdoor_activity_eligible` |
| week_experience_candidates | `general_grounding_eligible` + `week_experience` |
| reference_activities | 승인 Catalog hard filter |

따라서 `NEEDS_REVIEW` · `INVALID` · `IMAGE_ONLY` · `INDOOR_ALTERNATIVE`는
후보에 들어올 수 없다. 5 Case 실측 **누출 0건**이다.

---

## 6. Institution Evidence Retrieval

### 6.1 Week Experience를 분리했다 — 구현 중 잡은 문제

처음에는 `outdoor_play + week_experience`를 함께 담았다. 2026-06 만4세에서 Block 12개가
**week_experience 문장으로 채워지고 실제 활동 근거가 밀려났다.**

```text
(수정 전) 우리 동네에 있는 다양한 장소의 모습을 알아본다.   ← week_experience
          놀이를 통해 즐거운 우리 동네 생활을 표현한다.      ← week_experience
          초록 블록으로 공공기관 만들기                     ← 활동
(수정 후) 우리동네를 둘러보아요
          깨끗한 우리 동네 만들기
          초록 블록으로 공공기관 만들기
          줄을 다양한 방법으로 지나가 보기
```

원인은 둘이다. ① week_experience 문장이 Theme 어휘를 더 많이 포함해 ranking 상위를
차지한다. ② Week Experience Block과 내용이 겹쳐 L3의 Token Budget을 두 번 쓴다.

**Institution Block은 바깥놀이 활동 근거만 담는다.**

### 6.2 연령 tier

```text
1. SINGLE_AGE_EXACT       단일 요청 + 그 연령의 단일연령 면
2. SINGLE_AGE_IN_REQUEST  혼합 요청 중 한 연령의 단일연령 면
3. MIXED_AGE_COVERING     혼합연령 면이 요청 연령을 포함
4. AGE_UNKNOWN            연령 근거 없음 — Institution Block에서는 쓰지 않는다
```

`AGE_UNKNOWN`을 쓸 필요가 있는지 실측했다. 5 Case 모두 exact/mixed만으로
Top-K 12가 채워졌으므로 **Institution Block에서 제외**했다.
Week Experience와 Other Outdoor는 목적이 연령 구분이 아니라 그 달의 범위이므로 허용한다.

---

## 7. Age Contrast

정의: **같은 문서 · 같은 월 · 서로 다른 단일연령 면.**
기관 차이·양식 차이에 오염되지 않은 순수 연령 대조다.

```text
2026-06 만4세 (대조 가능 문서 2건)
  만4세 | 연제구연산더샵 | 우리동네를 둘러보아요
  만4세 | 연제구연산더샵 | 깨끗한 우리 동네 만들기
  만3세 | 연제구연산더샵 | 우리 동네 사람들을 만나요.
  만3세 | 부산광역시청   | 우리 동네를 산책해요
  만5세 | 부산광역시청   | 어린이집 주변 우리 동네 산책하기
  만5세 | 부산광역시청   | 우리 동네 환경 캠페인
```

**없는 대조쌍을 만들지 않는다.** 요청 연령이 대조에 참여하지 않는 문서는 제외하고,
대조가 없으면 빈 Block을 돌려준다(테스트로 고정).

기관 상한은 여기만 `cap + 1 = 3`이다. 대조 자체가 같은 기관 안에서 의미를 갖기 때문이다.

---

## 8. Week Experience

```text
month hard filter + week_experience section + general_grounding_eligible
+ theme relevance + 기관당 2건
```

**주차 index를 붙이지 않는다.** L1 실측에서 `week_position` 보유 record가 0건이다.
이 Block의 의미는 "이 달에 관찰된 경험 후보"이지 W1/W2/W3가 아니다.
테스트가 `week_position is None`을 전 Case에서 고정한다.

---

## 9. Reference Candidate Pre-ranking

```text
ActivityCatalog.eligible_candidates(outdoor_play, month, ages)   ← hard filter
  → Rule v2 context_ranking_sort_key                              ← pre-ranking
  → Top-K
```

Rule의 의미를 바꾸지 않았다(§2.2). Catalog가 주입되지 않으면 **빈 Block**이며
추측으로 채우지 않는다.

### Top-K = 12 검증

| Case | hard filter 통과 | 반환 |
|---|---:|---:|
| 2026-03 만3세 | 15 | 12 |
| 2026-06 만4세 | **7** | **7** |
| 2026-07 만4세 | **8** | **8** |
| 2026-08 만4세 | **7** | **7** |
| 2027-02 만5세 | **4** | **4** |

**후보가 12보다 적으면 전부 반환하고 억지로 채우지 않는다.** 5 Case 중 4개가 여기 해당한다.
`size == min(pool, top_k)`를 테스트가 고정한다.

---

## 10. Other Outdoor Evidence

Institution Block에 쓰이지 않은 추가 outdoor Grounding. Reference scarcity를 보완한다.

**전부 `reuse_policy = CONTEXT_ONLY`다.** L0 Contract대로 이 문자열은 최종 Product 값
후보가 아니며, `reuse_policy`가 Record에 그대로 남아 L3/L4에 전달된다(테스트 고정).

---

## 11. Theme Ranking

### 11.1 신호를 고르기 전에 측정했다

| Theme | eligible pool | 공백 토큰 겹침 | 2-gram 겹침 |
|---|---:|---:|---:|
| 우리 원과 친구 | 75 | **1** | 66 |
| 우리 동네 | 51 | 31 | 42 |
| 여름 | 65 | 51 | 59 |
| 교통기관 | 51 | 43 | 43 |
| 성장한 우리 | 33 | **0** | 17 |

`성장한 우리`가 공백 토큰으로 **0건**인 것이 결정적이다. `우리`는 흔해서 stopword로
빠지고 `성장한`은 활동명에 그대로 나오지 않는다. → **2-gram을 쓴다.**
`우리 동네`와 `우리동네`도 같은 gram을 만든다.

**동의어 사전을 만들지 않았다.** `교통기관 → 자동차/버스/탈것` 같은 전국 표준 ontology는
근거가 없고(CLAUDE.md §8) 유지 비용도 크다. 2-gram이 놓치는 것은 L3/L4의 LLM이
Context 안에서 판단한다.

### 11.2 두 신호를 합치지 않았다

```text
theme_page_match   그 면의 monthly_theme이 확정 Theme과 겹치는가  (bool)
text_overlap       Record 본문과 확정 Theme의 2-gram 겹침 수       (int)
```

합치면 `과학자가 되어 곤충 식물 관찰하기`(면 주제만 일치)가
`우리 동네 지도 보며 산책하기`(둘 다 일치)와 같은 점수가 된다.

### 11.3 정렬 키

```text
(연령 tier, -면주제일치, -본문겹침, record_id)
```

연령 tier가 theme 신호보다 **앞선다**(테스트 고정). 동률은 `record_id`로 갈리며,
그 값은 원문 셀 좌표에서 나왔으므로 안정적이다.

---

## 12. Source Diversity

### 12.1 적용 순서

```text
eligible → relevance ranking → 연령 균형 → diversity selection → Top-K
```

`Top-K 먼저 → 중복 제거`가 아니다. 상한 때문에 Top-K를 못 채우면
**상한을 넘겨 억지로 채우지 않고** 적은 수를 그대로 돌려준다.
근거가 한 기관에 몰려 있다는 사실 자체가 정보다.

### 12.2 Template Family

`{마성 · 우리 · 키즈로스쿨 · 혜솔}`은 본문 6-gram Jaccard 0.848까지 겹치므로
**한 Source로 묶어 센다.** L1 ingestion과 같은 집합이다.

### 12.3 연령 균형 — 구현 중 잡은 문제

혼합 요청 `(4, 5)`에서 만4세 근거가 `record_id` 순으로 앞서면
**Top-K 6개가 전부 만4세**가 되었다. §10이 금지한 상황이다.

`balance_by_single_age()`를 추가했다. 연령별 상대 순서는 유지한 채 round-robin으로
번갈아 낸다. 단일 연령 요청에는 아무 영향이 없다.

```text
혼합 요청 (4,5) institution block 연령 분포: {만4: 3, 만5: 3, 혼합면: 6}
```

---

## 13. Determinism

```text
같은 Evidence Store SHA + 같은 Catalog version + 같은 Request
  → 같은 record_id · 같은 순서 · 같은 Block 내용
```

확인 방법 세 가지:

1. 같은 Retriever 2회 호출
2. **새 Store 인스턴스**로 만든 Retriever 1회
3. Record 입력 순서를 뒤집어도 결과 동일 (테스트)

`random` 없음. 동률 tie-breaker는 `record_id` / `activity_id`다.

감사 결과: **3회 fingerprint 동일 `True`.**

---

## 14. Quality Cases

```text
Case                  inst  기관  ctr   wk  기관  ref  pool  oth  기관
2026-03 만3세 우리 원과 친구   12    6    6   10    6   12    15   10    6
2026-06 만4세 우리 동네       12    6    6   10    5    7     7   10    7
2026-07 만4세 여름           12    7    6   10    5    8     8   10    7
2026-08 만4세 교통기관        12    6    6   10    5    7     7   10    7
2027-02 만5세 성장한 우리      12    8    3   10    5    4     4   10    5
```

### 14.1 2026-06 만4세 — Rule-only 최악 Case

**Institution Block (Top 8)**

```text
[SINGLE_AGE_EXACT] 만4세 | 연제구연산더샵 | 우리동네를 둘러보아요
[SINGLE_AGE_EXACT] 만4세 | 연제구연산더샵 | 깨끗한 우리 동네 만들기
[SINGLE_AGE_EXACT] 만4세 | 부산광역시청   | 초록 블록으로 공공기관 만들기
[SINGLE_AGE_EXACT] 만4세 | 부산광역시청   | 줄을 다양한 방법으로 지나가 보기
[MIXED_AGE_COVER ] 만3~5 | 혜솔          | 우리 동네 표지판 찾으며 산책하기
[MIXED_AGE_COVER ] 만3~5 | 혜솔          | 우리 동네 사진찍기
[MIXED_AGE_COVER ] 만4~5 | 서진          | 우리 동네 놀이터 안전 지킴이가 되어요
[MIXED_AGE_COVER ] 만4~5 | 서진          | 우리 동네의 숲으로 가요
```

§26이 지정한 세 문자열이 모두 검색된다.

```text
검색됨  우리동네를 둘러보아요
검색됨  모래로 동네 공원만들기
검색됨  깨끗한 우리 동네 만들기
```

**Reference Block** — Rule의 최종 선택이 `activity_id` 해시 순서로 탈락시켰던 후보가
Context에 들어온다.

```text
 0. 우리 동네에서 일하는 분 찾아보기
 1. 분필로 내가 되고 싶은 직업 그림 그리기
 2. 꿈을 실은 종이비행기 날리기
 3. 병원에서 사용하는 물건 그림 찾기
 4. 나의 꿈 열기구 날리기
 5. 우리 동네 지도 보며 산책하기      ← Rule-only가 놓쳤던 것
 6. 모래 위에 그리는 우리 동네        ← Rule-only가 놓쳤던 것
```

### 14.2 2026-07 / 08 만4세

```text
2026-07  검색됨  물놀이 공원 만들기 · 물총놀이 · 여름 과일 신체 놀이하기
2026-08  검색됨  움직이는 교통기관 관찰해요 · 우리동네 버스 정류장을 살펴봐요
```

### 14.3 2027-02 만5세 — scarcity

```text
Reference candidate   4  (pool 4 = 주차 수)
Other Outdoor        10  (기관 5)
Week Experience      10  (기관 5)

Other Outdoor 예
  [연제구연산더샵] 즐거웠던 바깥놀이
  [연제구연산더샵] 동생과 함께 산책해요
  [무지개]        친구와 함께 놀이터에서 약속을 지키며 놀아요
  [무지개]        초등학교 운동장에서 놀아요
  [유림자연]      동생 반을 위한 안전한 놀이터를 만들어요
```

**L2는 Activity를 합성하지 않는다.** 후속 LLM이 합성할 수 있을 만큼 Grounding이
존재하는지만 보고한다 — canonical 4 + Corpus 10 + 경험 10 = **24개 근거**다.

---

## 15. Age Differentiation Audit

2026-07을 만3 / 만4 / 만5로 각각 조회했다.

| Block | 만3 | 만4 | 만5 | 3연령 공통 | 3∩4 | 4∩5 | 3∩5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| institution_monthly_evidence | 12 | 12 | 12 | **0** | **0** | 8 | **0** |
| age_contrast_evidence | 6 | 6 | 6 | 3 | 6 | 3 | 3 |
| week_experience_candidates | 10 | 10 | 10 | **0** | **0** | 8 | **0** |
| reference_activities | 12 | 8 | 8 | 8 | 8 | 8 | 8 |
| other_outdoor_evidence | 10 | 10 | 10 | **0** | **0** | 7 | **0** |

**Retrieval 단계에서 이미 연령 신호가 생긴다.** 만3세와 만4세의 Institution Block은
겹침이 0이다.

```text
만4세  다양한 여름날씨 몸으로 표현하기 / 여름 과일 신체 놀이하기 / 물놀이 공원 만들기 / 물총놀이
만3세  여름 꽃을 찾아요. / 여름나무 관찰하기 / 여름꽃 찾아보기 / 비 내리는 날 하늘과 웅덩이를 관찰해요.
```

**숨기지 않고 기록하는 부분**: 만4∩만5 겹침 8은 두 연령을 모두 포함하는 혼합연령 면
(`MIXED_AGE_COVERING`) 때문이다. Reference Block은 Catalog의 `supported_ages`가
연령을 크게 구분하지 않아 8/8이 겹친다 — **Retrieval이 아니라 Catalog의 성질**이다.

---

## 16. Concentration Audit

기관 상한 ON / OFF 비교. 값은 **최다 기관이 차지한 비중 (참여 기관 수)**.

| Case | Block | cap OFF | cap ON |
|---|---|---|---|
| 2026-03 만3세 | institution | 33% (5기관) | **17% (6기관)** |
| 2026-03 만3세 | other_outdoor | 40% (3기관) | **20% (6기관)** |
| 2026-06 만4세 | institution | 33% (4기관) | **17% (6기관)** |
| 2026-06 만4세 | other_outdoor | 30% (4기관) | **20% (7기관)** |
| **2026-07 만4세** | **other_outdoor** | **80% (2기관)** | **20% (6기관)** |
| **2026-08 만4세** | **other_outdoor** | **90% (2기관)** | **20% (6기관)** |
| 2027-02 만5세 | institution | 33% (5기관) | **17% (7기관)** |
| 2027-02 만5세 | other_outdoor | 50% (3기관) | **20% (5기관)** |

**만4세 Other Outdoor에서 한 기관이 80~90%를 차지하던 것이 20%로 내려간다.**
`new-reference-evidence-impact-2026-09.md` §9가 경고한 부산광역시청 편중이 실제로
Retrieval에 나타났고, 상한이 그것을 막는다.

---

## 17. Performance

```text
store load           0.28s      12,367 records
single retrieval     2.1ms
5-case batch        12.3ms      (case당 2.5ms)
```

**Vector DB가 필요하지 않다.** Store를 한 번 로드하면 월 index(`by_month`)로
후보를 좁히고 나머지는 in-memory 정렬이다. 정확한 극한 벤치마크는 하지 않았다 —
현재 규모에서 판단하기에 충분한 차이다.

---

## 18. Tests

```text
이전   1,766 passed, 4 deselected
현재   1,876 passed, 4 deselected      (+110 신규 · 기존 실패 0)
```

| 파일 | 건수 | 내용 |
|---|---:|---|
| `tests/retrieval/test_evidence_store_loader.py` | 18 | valid · SHA mismatch · schema mismatch · record count mismatch · normative_status · 중복 id · 파일/JSON 오류 · 실제 Artifact pin |
| `tests/retrieval/test_retriever.py` | 47 | Request 검증 · eligibility 6종 · age 8종 · ranking 6종 · diversity 6종 · block 8종 · empty 3종 · 결정론 2종 · Rule v2 불변 2종 |
| `tests/retrieval/test_retrieval_quality.py` | 45 | 실제 Artifact 5 Case × 기본 성질 6 + §26~§29 지정 검증 |

실제 Artifact가 없으면 quality 테스트는 skip된다. 나머지는 Artifact 없이 돈다.

---

## 19. Open Issues

### 19.1 Official Evidence — Option A를 선택했다

`OfficialEvidencePort` **인터페이스만** 두고 구현체는 만들지 않았다.

이유:
- L1은 `INSTITUTION_SAMPLE`만 Production Evidence Store로 만들었다.
- 보고서·지도서 레이아웃은 월간계획안 표 기하와 다르므로 같은 Pipeline에 억지로
  넣을 수 없다(L1 §1.2).
- case 단위 연령 추출은 별도 Adapter가 적합하다
  (`new-reference-evidence-impact-2026-09.md` §3.5: 만4세 case 약 15건).
- **Raw Official PDF를 runtime에 파싱하지 않는다.**

Retriever는 이 Port를 주입받지 않으며 Official Block 없이 정상 동작한다.
L3/L4 전에 별도 Adapter 단계로 붙인다. **L2 완료를 막지 않았다.**

### 19.2 Reference Block의 연령 변별력이 낮다

2026-07에서 만3/4/5세의 Reference Block이 8/8 겹친다. Catalog의 `supported_ages`가
연령을 크게 구분하지 않기 때문이며 Retrieval의 문제가 아니다. Activity v0.2.2에서
`age_scope=[4]` evidence를 보강하면 자연히 개선된다(별도 OPEN).

### 19.3 L1 Ingestion defect는 발견되지 않았다

L2 작업 중 Evidence Store 내용을 수정하지 않았다. Artifact SHA는 입력 그대로
`52b40955…`이며 L1 Patch 필요성은 확인되지 않았다.

### 19.4 여전히 OPEN

```text
OD-N16  PDF 라이브러리 의존성 — L2 비차단. 이번에 결정하지 않았다
OD-N03  Activity taxonomy (curriculum_links 공백)
OD-N04  LLM 공급자·모델·retry 상세
OD-N11  Theme/Template/Safety Adapter 승인 우회 입력 제거
Activity v0.2.2 승격 범위
```

---

## 20. L3 Readiness

L3 Monthly Context Packet이 필요로 하는 것이 모두 준비되었다.

| L3 요구 | L2 제공 |
|---|---|
| 성격별로 나뉜 근거 | Block 5종 (Required/Optional은 L3가 결정) |
| 각 근거의 원문과 출처 | `EvidenceRecord` (source_path · sha · page · cell 좌표) |
| Token Budget 산정 근거 | Block별 `size` · `top_k` · `eligible_pool_size` |
| 근거 표시 정책 | `reuse_policy` 유지 (`CONTEXT_ONLY`) |
| 연령 대조 | `age_contrast_evidence` (없으면 빈 Block) |
| canonical 후보 | `reference_activities` + Rule v2 순위 |
| 재현성 | Store SHA + Catalog version + 결정론 |
| 설명 가능성 | `RetrievalTrace` (tier · score · theme 신호 · diversity group) |

---

## 답변 — §39 필수 질문

**Q1. 2026-06 만4세에서 Rule-only가 놓쳤던 Grounding이 들어오는가?**
**들어온다.** §26이 지정한 `우리동네를 둘러보아요` · `모래로 동네 공원만들기` ·
`깨끗한 우리 동네 만들기` 셋 다 검색된다. Reference Block에도 Rule의 최종 선택이
해시 순서로 탈락시켰던 `우리 동네 지도 보며 산책하기`(rank 5) ·
`모래 위에 그리는 우리 동네`(rank 6)가 Context 후보로 들어온다.

**Q2. 2026-07 / 08 만4세에서 신규 Corpus Evidence가 검색되는가?**
**검색된다.** 7월 `물놀이 공원 만들기` · `물총놀이` · `여름 과일 신체 놀이하기`,
8월 `움직이는 교통기관 관찰해요` · `우리동네 버스 정류장을 살펴봐요`. 테스트로 고정했다.

**Q3. 2027-02 만5세의 Reference scarcity를 Corpus Evidence가 얼마나 보완하는가?**
canonical 4(= 주차 수)에 **Other Outdoor 10(기관 5) + Week Experience 10(기관 5)**이
더해져 총 24개 Grounding이 된다. L2는 합성하지 않았고, 후속 LLM이 합성할 재료가
있는지만 보고한다.

**Q4. 기관당 2건 상한이 실제로 concentration을 낮추는가?**
**낮춘다.** 가장 심한 곳에서 최다 기관 비중이 **90% → 20%**, **80% → 20%**로 내려간다
(2026-08 / 2026-07 만4세 Other Outdoor). 참여 기관은 2곳 → 6곳이 된다.

**Q5. Age3 / Age4 / Age5 Retrieval이 실제로 달라지는가?**
**달라진다.** 2026-07 Institution Block에서 만3세와 만4세의 겹침이 **0**이다.
다만 Reference Block은 8/8 겹친다 — Catalog의 성질이며 §19.2에 기록했다.

**Q6. NEEDS_REVIEW / INVALID가 Runtime 후보에 0건인가?**
**0건이다.** 5 Case 전 Block 감사에서 누출 0. `INDOOR_ALTERNATIVE`의 outdoor Block
누출도 0이다. 테스트가 Case마다 고정한다.

**Q7. 같은 입력은 항상 같은 결과를 반환하는가?**
**반환한다.** 같은 Retriever 2회 + 새 Store 인스턴스 1회의 fingerprint가 동일했고,
Record 입력 순서를 뒤집어도 결과가 같다. `random` 없음, tie-break는 `record_id`.

**Q8. 12,367 record 규모에서 Vector DB 없이 충분히 빠른가?**
**충분하다.** store load 0.28s(1회), single retrieval 2.1ms, 5-case 12.3ms.

**Q9. Official Evidence Retrieval은 어디까지 구현했는가?**
**Option A — `OfficialEvidencePort` 인터페이스만.** 구현체 없음. 이유는 §19.1.
Raw Official PDF runtime parsing을 하지 않았고 L2 완료를 막지 않았다.

**Q10. L3 Context Packet을 만들 준비가 되었는가?**
**되었다.** §20 표대로 L3가 필요로 하는 것이 모두 구조화된 객체로 준비되었다.

---

```text
MONTHLY LLM PLANNER L2

Evidence Store:
  institution-evidence-ingestion-v0.1.0
  content_sha256 52b409557d3503422aa0109664298976bd7f831ed18304b818aaad936916e5ea
  12,367 records · strict loader 검증 8종 · L1 Artifact 무수정
  Runtime은 PDF를 읽지 않는다 (OD-N16 계속 비차단)

Retriever:
  src/ssuksak/planning/retrieval/  (models · evidence_repository · ranking · retriever)
  eligible → relevance ranking → 연령 균형 → source diversity → Top-K
  LLM · Embedding · Vector DB 없음
  Rule v2는 읽기 전용 helper 하나만 추가해 재사용 (의미 불변, 테스트 고정)

Institution Evidence:
  outdoor_activity_eligible만. week_experience는 별도 Block으로 분리
  (구현 중 2026-06 만4세에서 활동 근거가 밀려나는 문제를 잡아 수정)
  5 Case 전부 Top-K 12 충족 · 기관 6~8곳

Age Contrast:
  같은 문서·같은 월·다른 단일연령 면만. 없으면 빈 Block
  2026-03 6 · 2026-06 6 · 2026-07 6 · 2026-08 6 · 2027-02 3

Week Experience:
  5 Case 전부 10건 · 기관 5~6곳
  주차 index를 붙이지 않는다 (L1 week_position 보유 0건)

Reference Activities:
  hard filter + Rule v2 pre-ranking → Top-K
  pool 15 / 7 / 8 / 7 / 4 → 반환 12 / 7 / 8 / 7 / 4
  후보가 K보다 적으면 전부 반환. 억지로 채우지 않는다

Other Outdoor Evidence:
  5 Case 전부 10건 · 기관 5~7곳 · 전부 reuse_policy=CONTEXT_ONLY 유지

Source Diversity:
  기관당 2건 (Age Contrast만 3건) · Template Family는 한 Source
  최다 기관 비중 90% → 20% (2026-08 만4세 Other Outdoor)
                  80% → 20% (2026-07 만4세 Other Outdoor)
  혼합 요청은 연령 round-robin으로 균형 (구현 중 만4세 독점 문제를 잡아 수정)

Age Differentiation:
  2026-07 Institution Block 만3∩만4 겹침 0
  만4∩만5 겹침 8은 혼합연령 면 때문 · Reference Block 8/8 겹침은 Catalog 성질 (기록함)

Invalid Leakage:
  0건  (NEEDS_REVIEW · INVALID · IMAGE_ONLY · INDOOR_ALTERNATIVE 전부)

Determinism:
  같은 Retriever 2회 + 새 Store 1회 fingerprint 동일
  Record 입력 순서 반전에도 동일 · random 없음 · tie-break record_id

Performance:
  store load 0.28s · single retrieval 2.1ms · 5-case batch 12.3ms
  Vector DB 불필요

Regression:
  1,766 → 1,876 passed, 4 deselected  (+110 신규 · 기존 실패 0)
  승인 Artifact 전부 불변 · Evidence Store 무수정
  Generate/Regenerate · LLMPort · Elice Adapter · Prompt · Demo · Golden 무변경

Official Retrieval:
  Option A — OfficialEvidencePort 인터페이스만 정의. 구현체 없음
  Raw Official PDF runtime parsing 하지 않음. L2 완료를 막지 않음

L3 Readiness:
  READY_FOR_CONTEXT_PACKET
```

---

```text
MONTHLY_LLM_PLANNER_L2_COMPLETE
```
