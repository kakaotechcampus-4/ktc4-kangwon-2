# Activity Reference v0.2.1 — Human Approval & Activation Report

- 작성일: 2026-09-13
- 선행 승인: `MONTHLY_QUALITY_PATCH_1_READY_FOR_HUMAN_APPROVAL`,
  `ACTIVITY_REFERENCE_V0_2_1_READY_FOR_APPROVAL`
- 선행 보고서: `docs/analysis/monthly-quality-patch-1-review.md`,
  `docs/analysis/activity-v0-2-1-setting-audit.md`
- 범위: 승인 · Production/Demo default 전환 · 실제 Use Case 검증까지.
  Week Experience 및 다른 Monthly vNext 기능은 **구현하지 않았다.**

---

## 1. Approval Metadata

새 승인 Artifact를 만들었다. Draft 파일은 그대로 보존한다.

| 항목 | 값 |
|---|---|
| 승인 파일 | `data/activities/activity_reference_v0_2_1.json` |
| `catalog_id` | `ssuksak.outdoor-activity-reference` |
| `catalog_version` | `activity-reference-v0.2.1` |
| `review.domain_owner_approval` | `HUMAN_APPROVED` |
| `review.approved_by` | `reviewer_ai_lead_001` |
| `review.approved_at` | `2026-09-13T11:32:20+09:00` |
| `review.pending_reason` | `null` |
| item count | 196 |
| **Approved SHA-256** | `ddbbe43f570cf64ef86db44e7de04e127aec4e663cdb41c26a8fe3c1002dc2ac` |
| 원본 Draft | `data/activities/activity_reference_v0_2_1_draft.json` |
| 원본 Draft SHA-256 | `a64af4331cd850031fbb99f8ae3f283e609b3623da68b8ea118afb94e92faa63` |

### 기존 승인 Convention 적용

v0.2.0 승인본(`activity_reference_v0_2.json`)과 같은 방식을 그대로 썼다.

- Reviewer는 `reviewer_ai_lead_001` — OD-N10의 opaque `reviewer_<role>_<sequence>` 형식이다.
  인증 provider의 login user_id가 아니고 테스트 fixture도 아니며 Plan Confirm의 교사
  `actor_id`와도 다른 개념이다.
- `approved_at`은 KST(`+09:00`) ISO-8601이다. Template A / Safety Rule / v0.2.0과 같다.
- 활성화는 파생값이다. 파일에 `runtime_active` / `activation_status` 필드를 두지 않았고
  `review.domain_owner_approval`에서만 읽는다. 승인 우회 입력 경로도 없다.
- 승인 근거 문서를 `review.review_document`에 남겼다.

추가로 v0.2.0에는 없던 `review.approved_from`을 넣어 **어떤 Draft 바이트를 승인했는지**
고정했다.

```json
"approved_from": {
  "draft_path": "data/activities/activity_reference_v0_2_1_draft.json",
  "draft_sha256": "a64af4331cd850031fbb99f8ae3f283e609b3623da68b8ea118afb94e92faa63"
}
```

> **2026-09-15 LF canonicalization 이후 주의.**
> 위 표와 이 코드 블록의 SHA는 **승인 당시(2026-09-13)의 값이며 그대로 둔다.**
> 그때 Repository의 JSON 워킹트리가 CRLF였기 때문이다.
>
> 이후 `*.json text eol=lf` 정책이 도입되어 정식 바이트 표현이 LF가 되었고,
> 실제 파일과 Freeze 기대값은 아래 값으로 옮겨졌다. **JSON 의미·승인 판단·
> reviewer·approved_at·catalog version은 바뀌지 않았다.**
>
> | 대상 | 승인 당시 (CRLF) | 현재 canonical (LF) |
> |---|---|---|
> | Draft | `a64af4331cd850031fbb99f8ae3f283e609b3623da68b8ea118afb94e92faa63` | `a3ec9f7956bf84fb6a510605dfff6064627de5482b1e56dc584e2ceb734f608a` |
> | Approved | `ddbbe43f570cf64ef86db44e7de04e127aec4e663cdb41c26a8fe3c1002dc2ac` | `fa9f3215c3af212ea727835c5ab06ef903b0d7ee5c1f0c615d5eaf4bc156da1a` |
>
> 근거: `docs/analysis/frozen-json-lf-canonicalization.md`

---

## 2. Draft → Approved Semantic Diff

검증 도구: `analysis/tools/diff_v0_2_1_approval.py`
고정 Test: `tests/adapters/test_activity_v0_2_1_approved.py` (§2 블록)

```text
  변경된 top-level 키 4개: ['$schema_note', 'approved_from_draft', 'draft_note', 'review']
  변경된 review 키 7개: ['approval_note', 'approved_at', 'approved_by', 'approved_from',
                        'base_catalog', 'domain_owner_approval', 'review_document']

  activities 블록: 바이트 단위로 동일 (196 items)

  IDENTICAL  activity IDs
  IDENTICAL  labels
  IDENTICAL  evidence
  IDENTICAL  ages
  IDENTICAL  months
  IDENTICAL  settings
  IDENTICAL  display_quality
  IDENTICAL  display_quality_review_status
  IDENTICAL  correction metadata
  IDENTICAL  source lineage

  DIFF OK — 승인 metadata 외 의미 변경 없음
```

### 바뀐 4개 top-level 키의 내용과 이유

| 키 | Draft | Approved | 성격 |
|---|---|---|---|
| `review` | `PENDING_HUMAN_REVIEW`, `approved_by=null` | `HUMAN_APPROVED`, reviewer/시각/근거 기록 | 승인 그 자체 |
| `approved_from_draft` | `activity-reference-v0.2.0-draft` (v0.2.0에서 물려받은 낡은 값) | `activity-reference-v0.2.1-draft` | 승인 provenance 교정 |
| `draft_note` | v0.2.0 Draft 파일을 가리킴 (물려받은 낡은 값) | v0.2.1 Draft 파일을 가리킴 | 승인 provenance 교정 |
| `$schema_note` | "Draft다 · runtime에 연결하지 않는다" | "승인본이다 · runtime default로 읽는다" | 사실 교정 |

뒤의 세 건은 v0.2.1 Draft가 v0.2.0에서 그대로 복사해 온 문장이라 **승인 전 상태에서 이미
사실과 달랐다.** 승인본에서 바로잡았고 Activity 의미에는 영향이 없다. Draft 파일 자체는
수정하지 않았다(SHA 불변).

`review` 안에서 바뀐 7개 키는 전부 승인 metadata다. `runtime_rule` / `pending_reason` /
`base_catalog.unchanged`는 값이 이미 같아 diff에 나타나지 않았고, `supersedes`
(`activity-reference-v0.2.0`)와 `patch` 블록은 **변경하지 않았다.**

---

## 3. Production Default Change

| | 변경 전 | 변경 후 |
|---|---|---|
| `DEFAULT_ACTIVITY_CATALOG_PATH` | `data/activities/activity_reference_v0_2.json` | `data/activities/activity_reference_v0_2_1.json` |
| 새 Monthly Generate가 pin하는 version | `activity-reference-v0.2.0` | `activity-reference-v0.2.1` |

### exact pin semantics를 유지하기 위해 필요했던 변경

Default만 바꾸면 **기존 v0.2.0 Plan의 Regenerate가 깨진다.** Regenerate는
`MonthlyPlan.activity_catalog` lineage가 가리키는 version을 Repository에 정확히 요청하는데,
파일 하나만 읽는 Repository는 v0.2.0을 더 이상 해소하지 못하기 때문이다.

그래서 `JsonActivityReferenceRepository`에 **명시적인 superseded 경로**를 추가했다.

```python
DEFAULT_ACTIVITY_CATALOG_PATH = _DATA / "activity_reference_v0_2_1.json"

SUPERSEDED_ACTIVITY_CATALOG_PATHS: tuple[Path, ...] = (
    _DATA / "activity_reference_v0_2.json",
)

def production_activity_reference_repository() -> JsonActivityReferenceRepository:
    return JsonActivityReferenceRepository(
        DEFAULT_ACTIVITY_CATALOG_PATH,
        superseded_paths=SUPERSEDED_ACTIVITY_CATALOG_PATHS,
    )
```

**이것은 fallback이 아니다.**

- `get_catalog`은 요청받은 `catalog_id` + `catalog_version`과 **정확히 일치할 때만** 반환한다.
- 어디에도 없으면 `None`이고, default로 대체하지 않는다.
- `superseded_paths`를 주지 않은 `JsonActivityReferenceRepository()`는 예전처럼
  파일 하나만 읽는다. v0.2.0은 거기서 해소되지 않는다.
- 기존 Monthly Plan Migration은 하지 않았다.

고정 Test:
`tests/adapters/test_activity_v0_2_1_approved.py::test_unknown_version_is_not_silently_upgraded_to_the_default`,
`::test_bare_repository_does_not_gain_superseded_resolution`

### 변경한 파일

| 파일 | 변경 |
|---|---|
| `src/ssuksak/adapters/json_activity_reference_repository.py` | default 경로 전환, `SUPERSEDED_ACTIVITY_CATALOG_PATHS`, `production_activity_reference_repository()` 추가, 캐시를 경로별로 변경 |
| `src/ssuksak/dev/monthly_wiring.py` | default 경로일 때 production factory 사용 |
| `demo-planning/backend/composition.py` | production factory 사용 |
| `src/ssuksak/adapters/activity_reference_projection.py` | docstring 경로 갱신 |

Use Case · Domain · Rule 코드는 **변경하지 않았다.**

---

## 4. Demo Default Change

Demo는 이미 `DEFAULT_ACTIVITY_CATALOG_PATH`를 쓰고 있었고, 이번에 production factory로
바꿔 superseded 해소까지 Production과 동일해졌다. **Demo 전용 Fake Catalog는 없다.**

```python
# demo-planning/backend/composition.py
# Production과 **같은 승인 Artifact**를 읽는다. Demo 전용 Fake Catalog는 없다.
activities = production_activity_reference_repository()
...
activity_selector=read_activity_catalog_selector(DEFAULT_ACTIVITY_CATALOG_PATH),
```

실제 Demo Composition을 조립해 확인했다.

```text
demo activity_selector : activity-reference-v0.2.1
  activity-reference-v0.2.1    -> resolved, active=True, items=196
  activity-reference-v0.2.0    -> resolved, active=True, items=198
  activity-reference-v0.1.0    -> None
```

Demo는 Production `GenerateMonthlyPlan` / `EditMonthlyPlanItem` /
`RegenerateMonthlyPlanItem` / `ConfirmMonthlyPlan` Use Case와 Production Loader를 그대로 쓴다.

고정 Test: `tests/adapters/test_activity_v0_2_1_approved.py::test_demo_uses_the_same_approved_artifact_as_production`

---

## 5. Exact Catalog Pinning Verification

실제 Use Case로 두 Scenario를 실행했다
(`analysis/experiments/monthly_vnext/verify_v0_2_1_activation.py` §11,
고정 Test `tests/dev/test_activity_v0_2_1_activation_e2e.py`).

### Scenario A — Legacy

```text
  generate pin      : activity-reference-v0.2.0
  regenerate loaded : activity-reference-v0.2.0
  W2 '전통놀이' → '동대문 놀이'
  PASS  generate pin == activity-reference-v0.2.0
  PASS  regenerate exact load == activity-reference-v0.2.0
  PASS  비대상 Cell 보존
```

Regenerate 후에도 Plan lineage는 `activity-reference-v0.2.0`이고, 모든 outdoor Cell의
`ACTIVITY_REFERENCE` Evidence `source_version`이 `activity-reference-v0.2.0` 하나다.
v0.2.1 Evidence가 섞이지 않는다.

### Scenario B — New

```text
  generate pin      : activity-reference-v0.2.1
  regenerate loaded : activity-reference-v0.2.1
  W2 '가을 나들이' → '한복 입고 나들이 가요'
  PASS  generate pin == activity-reference-v0.2.1
  PASS  regenerate exact load == activity-reference-v0.2.1
  PASS  비대상 Cell 보존
```

**Default fallback으로 기존 Plan의 version이 바뀌는 경로는 없다.**

---

## 6. 2026-07 만3세 Result

### BEFORE — v0.2.0 pin (지시서에 기록된 기존 결과와 일치)

```text
Theme: 여름
W1 우리 동네 분수대 가 보기
W2 셀로판지로 여름 하늘 바라보기
W3 건너기                       ← 조각
W4 산책하며 여름 곤충 찾기
W5 무인 아이스크림 매장 찾아가기
```

### AFTER — v0.2.1 default

```text
Theme: 여름
activity_catalog.version : activity-reference-v0.2.1
selection_rule           : monthly.activity.reference_candidate_selection v2
llm_invoked              : false

W1 장화 신고 물웅덩이 건너기     ← 복원 Activity
W2 우리 동네 분수대 가 보기
W3 셀로판지로 여름 하늘 바라보기
W4 산책하며 여름 곤충 찾기
W5 무인 아이스크림 매장 찾아가기
```

### 조각 Activity 부재 확인

| 조각 label | 선택 결과 | 7월 만3세 후보 pool | Catalog 전체 |
|---|---|---|---|
| `건너기` | 없음 | 없음 | 없음 |
| `장화 신고 물웅덩이` | 없음 | 없음 | 없음 |
| `우리집에 왜 왔니?` | 없음 | 없음 | 없음 |
| `놀이를 해요.` | 없음 | 없음 | 없음 |

| 복원 Activity | Catalog | 7월 만3세 후보 |
|---|---|---|
| `장화 신고 물웅덩이 건너기` | 있음 | 있음 |
| `우리집에 왜 왔니? 놀이를 해요.` | 있음 | 없음 (7월 만3세 조건 밖) |

### 주차가 한 칸씩 밀린 이유 — Trace

후보 pool을 순위 축 그대로 나열하면 원인이 드러난다.

```text
-- v0.2.0  7월 만3세  후보 16개 (evidence_strength 내림차순)
   2  act_outdoor_v2_66f4b0e7e5     물풍선 놀이를 해요.
   2  act_outdoor_v2_e8b508fcdd     여름 꽃을 찾아요.
   1  act_outdoor_v2_30ad6621c8     우리 동네 분수대 가 보기
   1  act_outdoor_v2_3766bbd12a     셀로판지로 여름 하늘 바라보기
   1  act_outdoor_v2_4798d73600     개미를 찾아라!
   1  act_outdoor_v2_4a8be58a2a     건너기                      ← 조각(근거 1)
   ...

-- v0.2.1  7월 만3세  후보 15개
   2  act_outdoor_v021_f13eaab140   장화 신고 물웅덩이 건너기    ← 근거 2로 합쳐짐
   2  act_outdoor_v2_66f4b0e7e5     물풍선 놀이를 해요.
   2  act_outdoor_v2_e8b508fcdd     여름 꽃을 찾아요.
   1  act_outdoor_v2_30ad6621c8     우리 동네 분수대 가 보기
   ...
```

조각 두 개(`건너기` 근거 1 + `장화 신고 물웅덩이` 근거 1)의 Evidence가 복원 Activity 하나로
합쳐지면서 `evidence_strength_for_month(7) = 2`가 되었다. Ranking 축 5번
`negative monthly evidence strength`에서 상위 tier로 올라가고, 같은 2점인 두 후보와는 축 6번
`stable id`로 갈린다(`act_outdoor_v021_…` < `act_outdoor_v2_…`). 그래서 W1을 차지하고 나머지가
한 칸씩 밀렸다. **Rule은 바뀌지 않았고 Catalog 근거가 바뀐 결과다.**

후보 수 16 → 15는 `조각 2개 제거 + 복원 1개 추가`의 순증감이다.

---

## 7. 2026-09 만5세 Result

### BEFORE — v0.2.0 pin

```text
Theme: 우리나라와 세계 여러 나라
W1 무궁화 꽃이 피었습니다
W2 전통놀이                      ← TOO_GENERIC
W3 강강술래
W4 가을 나들이
W5 사방치기
```

### AFTER — v0.2.1 default

```text
Theme: 우리나라와 세계 여러 나라
W1 무궁화 꽃이 피었습니다
W2 강강술래
W3 가을 나들이
W4 사방치기
W5 동대문 놀이
```

**Patch 1에서 예고한 `W2 전통놀이 → W2 강강술래`가 승인 Artifact에서도 그대로 재현된다.**

### 전통놀이 상태

```text
display_quality               : TOO_GENERIC
display_quality_review_status : HUMAN_CONFIRMED
has_confirmed_display_issue   : True

Hard Exclusion : false   ← 9월 만5세 후보 27개 안에 그대로 있다
Soft Penalty   : active
```

`전통놀이`는 Catalog에서 **제거하지 않았다.**

### Trace — 왜 W5까지 전부 밀렸는가

두 version의 후보 pool은 **27개로 동일하고 evidence_strength도 동일하다.** 차이는 하나뿐이다.

```text
-- v0.2.0  9월 만5세  후보 27개        -- v0.2.1  9월 만5세  후보 27개
   11  무궁화 꽃이 피었습니다             11  무궁화 꽃이 피었습니다
   10  전통놀이                          10  전통놀이  [display penalty]
    7  강강술래                           7  강강술래
    5  가을 나들이                        5  가을 나들이
    5  사방치기                           5  사방치기
    3  동대문 놀이                        3  동대문 놀이
```

Ranking v2의 정렬 키는

```text
(repeat, theme, display_quality, curriculum, -evidence_strength, activity_id)
```

이고 `display_quality`가 `-evidence_strength`보다 **앞**에 있다. 따라서 penalty 1을 받은
`전통놀이`는 근거가 10점이어도 penalty 0인 모든 후보 뒤로 간다. 매주 penalty 0 후보가 남아
있으므로 5주 내내 선택되지 않고, 빈 자리를 다음 순위인 `동대문 놀이`(근거 3)가 채운다.

Hard Exclusion이었다면 후보 수가 27 → 26으로 줄었을 것이다. **줄지 않았다.**

동일 Case를 v0.2.0으로 pin하면 `W2 전통놀이`가 그대로 나온다
(`tests/dev/test_activity_v0_2_1_activation_e2e.py::test_legacy_v0_2_0_still_reproduces_the_old_generic_selection`).
penalty가 Rule의 label 판단이 아니라 **Catalog metadata에서** 온다는 증거다.

---

## 8. Candidate Coverage

새 Production Default 상태에서 12개월 × 6 age combination을 전수 확인했다.
표기는 `v0.2.0 → v0.2.1`이다.

```text
  월           만3세         만4세         만5세       만3+4세       만3+5세       만4+5세
   1월    14→14        8→8         8→8         8→8         8→8         8→8
   2월    11→11        4→4         4→4         4→4         4→4         4→4
   3월    15→15        8→8        11→11        8→8         7→7         7→7
   4월    16→16        9→9         9→9         9→9         9→9         9→9
   5월    12→11        8→8         8→8         8→8         8→8         8→8
   6월    13→13        7→7         7→7         7→7         7→7         7→7
   7월    16→15        9→8         9→8         9→8         9→8         9→8
   8월    12→12        7→7         7→7         7→7         7→7         7→7
   9월    37→37       31→31       27→27       22→22       15→15       20→20
  10월    15→15        8→8         8→8         8→8         8→8         8→8
  11월    11→11        4→4         4→4         4→4         4→4         4→4
  12월    17→17        7→7         7→7         7→7         7→7         7→7

  newly introduced 0-candidate combos: 0
```

**newly introduced 0 Candidate 조합: 0건 → PASS.** 임의 Fallback을 추가하지 않았다.

감소한 곳은 7군데이고 전부 `-1`이며, 조각 제거/복원의 순증감으로 설명된다.

| 조합 | 변화 | 설명 |
|---|---|---|
| 5월 만3세 | 12 → 11 | 조각 `우리집에 왜 왔니?` / `놀이를 해요.` 제거 후 복원 1개 |
| 7월 만3세 | 16 → 15 | 조각 `건너기` / `장화 신고 물웅덩이` 제거 후 복원 1개 |
| 7월 만4·만5·혼합 4조합 | 9 → 8 | 위와 같은 원인. 복원 Activity가 해당 연령 조건 밖 |

고정 Test: `tests/adapters/test_activity_v0_2_1_approved.py::test_no_month_age_combination_lost_all_candidates_after_activation` (72 조합)

---

## 9. Regression

### 9.1 Selection Rule 유지 (§6)

```text
rule_id      : monthly.activity.reference_candidate_selection
rule_version : v2   (변경 없음)

Ranking:
  1. same-month repeat penalty
  2. parent theme mismatch penalty
  3. display quality penalty
  4. curriculum repeat penalty
  5. negative monthly evidence strength
  6. stable id
```

`src/ssuksak/planning/rules/monthly_activity_selection.py`는 **이번 작업에서 수정하지 않았다.**
추가 Weight 없음 · Hard Exclusion 추가 없음 · Official Topic Support Ranking 추가 없음.

### 9.2 Production Generate (§8)

```text
default catalog file : activity_reference_v0_2_1.json
superseded resolvable: ['activity_reference_v0_2.json']

만3세 2026-09  activity_catalog.version = activity-reference-v0.2.1  rule = v2  llm_invoked = False
만4세 2026-09  activity_catalog.version = activity-reference-v0.2.1  rule = v2  llm_invoked = False
만5세 2026-09  activity_catalog.version = activity-reference-v0.2.1  rule = v2  llm_invoked = False
```

세 Plan 모두 outdoor Cell 전부 `FILLED`이고, 모든 `ACTIVITY_REFERENCE` Evidence의
`source_version`이 `activity-reference-v0.2.1`이다.

### 9.3 Monthly Contract Semantics (§13)

| Semantics | 상태 | 확인 위치 |
|---|---|---|
| Generate candidate 0 → `EMPTY_VALID` → save success | 유지 | `tests/dev/test_monthly_e2e.py::test_generate_with_zero_candidates_yields_empty_valid` |
| Regenerate candidate 0 → `BLOCKED` → 기존 값 보존 → save 0 | 유지 | `tests/dev/test_monthly_e2e.py::test_regenerate_with_zero_candidates_is_blocked_and_preserves_the_cell` |
| `CONFIRMED` → edit blocked | 유지 | 실행 검증 PASS + `tests/dev/test_monthly_e2e.py` |
| `CONFIRMED` → regenerate blocked | 유지 | 실행 검증 PASS + `tests/dev/test_monthly_e2e.py` |
| Safety unresolved Semantics | 유지 | 실행 검증에서 outdoor 생성 후에도 `safety_education` 5칸 전부 `EMPTY_UNRESOLVED` |
| Monthly LLM 0 calls | 유지 | 모든 Generate에서 `run.llm_invoked == False` |

**candidate 0 Semantics에 대한 정직한 기록:** 승인본 v0.2.1에는 12×6 조합 중 후보가 0인
조합이 없다(§8). 따라서 이 Semantics는 실제 승인 Catalog로는 재현할 수 없고, In-Memory
Catalog를 쓰는 위 두 Test가 계속 고정한다. 그 Test들은 새 default 아래에서도 통과한다.

### 9.4 Full Test Suite (§14)

```text
이전 기준 : 1520 passed, 4 deselected
현재      : 1644 passed, 4 deselected
```

기존 Test 실패 **0건.** 증가분 124건의 내역:

| 파일 | 추가 | 내용 |
|---|---:|---|
| `tests/adapters/test_activity_v0_2_1_approved.py` (신규) | 112 | 승인 metadata, Draft→Approved diff, freeze, default 전환, superseded pin 해소, Demo 동일 Artifact, 품질 metadata, 72조합 coverage |
| `tests/dev/test_activity_v0_2_1_activation_e2e.py` (신규) | 12 | 실제 Use Case로 Generate/Regenerate pinning Scenario A·B, 7월 만3세 / 9월 만5세 품질 회귀 |

### 9.5 기존 Test 중 default version을 명시하고 있던 것들

Default 전환은 그 값을 직접 assert하던 기존 Test를 필연적으로 바꾼다. 실패를 덮은 것이
아니라 **바뀐 Contract에 맞춰 갱신**한 것이므로 전부 남긴다.

| 파일 | 변경 |
|---|---|
| `tests/adapters/test_activity_reference_projection.py` | default 경로 assert를 v0.2.1로. v0.2.0이 bare repository에서 해소되지 않음을 새로 고정 |
| `tests/adapters/test_activity_v0_2_approved.py` | "default가 v0.2.0"을 "default는 아니지만 superseded로 해소된다"로 |
| `tests/adapters/test_activity_v0_2_draft.py` | default 파일명 assert 갱신 |
| `tests/adapters/test_activity_v0_2_1_draft.py` | "production default는 아직 v0.2.0"을 "PENDING Draft 파일은 승인 경로가 아니다"로 |
| `tests/application/test_generate_monthly_activity.py` | 실제 승인 Catalog Case의 version 문자열 4곳 |
| `tests/application/test_regenerate_monthly_activity.py` | 같은 이유 4곳 |
| `tests/dev/test_monthly_e2e.py` | `APPROVED_CATALOG_VERSION` 및 docstring |
| `tests/dev/test_monthly_harness.py` | 출력 포맷 assert 1곳 |

---

## 10. Freeze Verification

```text
Theme Reference v0.1.2
  data/themes/theme_reference_v0.json
  c12999fa141d5c5fdecf39110adfb2227fc0ab98725991e8bdbca098b3ff4197   UNCHANGED

Activity Reference v0.2.0
  data/activities/activity_reference_v0_2.json
  e27ebca3342a84327c6624c5ba258b9bc98aef37ba5362b61f283c47ece0bde6   UNCHANGED

Monthly Template A
  data/templates/monthly_template_a.json
  1f35322dd52f832bffc3057953ecbd64d52c2d855ada964af68472ebba1a7c34   UNCHANGED

Safety Legal
  data/rules/safety_education_legal_v1.json
  5831809b19a28505844cf10363c95eeb09ec4641d5fe54a26afdb1891c3ddba5   UNCHANGED
```

참고로 함께 확인한 나머지 artifact도 전부 불변이다.

```text
activity_reference_v0.json            b565254f6668aeea04ef4ddce235ef51fd7af80d258d568e2f4d31fae6648b0d
activity_reference_v0_2_draft.json    c9c0e9da7e82bc73a6120551210983d786b4d6218fd6492c0727102cb6d29c5b
activity_reference_v0_2_1_draft.json  a64af4331cd850031fbb99f8ae3f283e609b3623da68b8ea118afb94e92faa63
tests/golden/monthly_cases.json       c605641232d91abd1d6d2babb52a45b81ff8ea9de4c9bb3190cd68b5c62c85a7
tests/golden/yearly_cases.json        7918e9f9cbe23580e7621e2f7c7ce40825a073afb8b0dc2038640a1291a6b384
CLAUDE.md                             a723a7ee488eacdb9b8a95efd07e2516bf247a16fb9f4cc51dfb054867ef78f2
```

신규 파일:

```text
activity_reference_v0_2_1.json        ddbbe43f570cf64ef86db44e7de04e127aec4e663cdb41c26a8fe3c1002dc2ac
```

기존 Monthly Plan Migration은 수행하지 않았다.

---

## 11. Remaining Technical Debt

### OD-N12 (= `OD-ACTIVITY-INGESTION-01`) — 재현 가능한 Activity Reference ingestion pipeline

`docs/open-decisions.md` §6에 `OPEN`으로 등록했다.

```text
현재 Repository에는
  Source PDF → observation → normalization → Activity Reference
전체를 재현하는 원래 Production-grade ingestion pipeline이 존재하지 않는다.
```

확인 방법과 근거는 `docs/analysis/activity-v0-2-1-setting-audit.md` §2에 있다.
`setting` 값을 **계산**하는 코드는 저장소에 없고 스키마 검증과 감사 도구만 있다.

Patch 1에서 만든 `analysis/tools/cell_extract.py` 계열 추출 모듈은 **문제 재현과 감사에
유효**하지만 Catalog 전체를 생성하지 않고 미복원 사례를 남기며 프로젝트 dependency가 아니다.
**이를 Production ingestion pipeline이라고 선언하지 않는다.**

이번 작업에서 해결하지 않는다. 결정 시점은 Activity Reference v0.3 착수 전 또는 Corpus 증분
수집 착수 전이다.

### 함께 남아 있는 항목

| 항목 | 출처 |
|---|---|
| `흙공 만들기`의 `EITHER` 승격 여부 | setting-audit §7 |
| 자기 자신을 대체안으로 적는 표기의 취급 (`indoor_alternative` Section 구현 시) | setting-audit §7 |
| 미복원 11건의 Evidence label 정규화 | setting-audit §7 |
| `AUTO_CANDIDATE` 9건 / `UNREVIEWED` 179건의 display quality 사람 검토 | patch-1-review |
| 만4세 single-age evidence 부족, single-institution 비율, 신규 Activity 다기관 재현율 | v0.2.0에서 승계, 승인 blocker 아님 |
| OD-N11 — Theme/Template/Safety Adapter의 승인 우회 입력 제거 | open-decisions §6 |

---

## 12. 재현 방법

```bash
# 승인 Diff
python analysis/tools/diff_v0_2_1_approval.py

# Activation 전 구간 (§8~§13) — 실제 Use Case 실행
python analysis/experiments/monthly_vnext/verify_v0_2_1_activation.py

# 전체 회귀
python -m pytest
```

```text
ACTIVATION VERIFY PASS — 전 항목 통과
1644 passed, 4 deselected
```
