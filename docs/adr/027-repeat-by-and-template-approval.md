# ADR-027: 월간 Template 의 반복 단위는 `repeat_by` 다 — 승인 대기 Template 은 고정만 하고 생성에 쓰지 않는다

- 2026-10-10
- 상태 — 채택. **채택 범위는 「결정」 절뿐이다.** 「아직 정하지 않은 것」 절은 채택이 아니다
- 관련 — PR #122 · `p0-planning/data/templates/` · `p0-planning/tests/finalization/test_freeze.py`

## 맥락

월간 Template 의 `display_mode`(`MONTHLY_MERGED_SUMMARY` · `WEEKLY_CELLS`)는 이름과 달리 화면 표시 방식이
아니었다. **Section 이 시간 칸을 몇 개 갖고 어떤 주소로 생성 · 검증되는지**를 정했다.

이름을 바꾸려면 승인된 Template 파일(v0.1.0 · v0.2.0)을 고쳐야 하는데, 승인은 파일 내용에 대해 받은 것이다.
그래서 이름만 바꾼 새 version(v0.1.1 · v0.2.1)을 냈고, 이 둘은 아직 사람 승인을 받지 않았다.

PR #122 리뷰에서 세 가지가 나왔다.

1. 승인 대기 파일이 동결 목록(`FROZEN_ARTIFACTS`)에 있어 승인하는 순간 테스트가 깨진다.
2. Core 월간 생성 경로가 Template 승인을 확인하지 않는다. Core 를 직접 부르면 승인 대기 Template 으로
   계획안이 만들어진다.
3. 이 결정들의 기록이 저장소 밖에 있다.

원래 결정은 팀 계획 문서(저장소 밖)의 ID 로 관리됐다 — `TP-21`(이름 전환 방식), `C1.5`(`repeat_by` 정의),
`Part 12.1 · 12.7 · 12.8 · 12.12`(새 version · 승인 대기 · BE-1 계약), `OD-N10`(승인자 id 규칙), `OD-N11`(테스트용
승인 Fixture). **이 ADR 은 그 문서 없이 저장소만 보고 이유를 알 수 있게 내용을 옮겨 적는다.** 원 문서를 옮기거나
대체하지 않는다.

## 결정

### 1. 반복 단위의 이름과 값

- `display_mode` → `repeat_by`. 값은 `MONTHLY_MERGED_SUMMARY` → `NONE`(문서에 값 하나),
  `WEEKLY_CELLS` → `WEEK`(활성 주마다 값 하나). 대응이 1:1 이라 생성 결과는 바뀌지 않는다.
- `repeat_by` 는 **값이 반복되고 주소가 정해지는 시간 단위**다. 칸을 합쳐 그릴지는 화면 배치(Layout)의 일이다.
- **`NONE` 과 `null` 은 다르다.**

  | 값 | 뜻 | 어디에 |
  |---|---|---|
  | `NONE` | 반복하지 않는다 — 칸 하나 | CONTENT |
  | `WEEK` | 활성 주마다 칸 하나 | CONTENT |
  | `null` | 반복 단위가 없거나 아직 정해지지 않았다 | AXIS(`week_axis`, 칸 0개) · **활성화되지 않은 CONTENT** |

  활성화되지 않은 CONTENT 의 `null` 은 「단위를 아직 측정 · 결정하지 않았다」는 뜻이다(v0.1.1 의 `emergency_response` ·
  `drill` · `indoor_alternative` · `special_program` · `event_schedule`). **활성 CONTENT 는 `null` 일 수 없다** —
  파서가 거절하고(`monthly_template_schema.py` 「requires explicit repeat_by」), Section 해석도 거절한다.
  `structure_rules.global_repeat_by_default` 는 항상 `null` 이다 — 전국 공통 기본값을 두지 않는다.
- **월간은 `NONE` · `WEEK` 만 받는다.** `MONTH` · `DAY` 는 지금 지원하지 않는다.
- LLM 프롬프트의 `placement: "MONTH"`(`planner/prompt.py` · `planner/cell_prompt.py`)는 `repeat_by` 값이 아니다.
  월간 문서에서 `NONE` 인 Section 을 LLM 에게 「이 달 전체에 하나」로 알려 주는 LLM 용 단어다.

### 2. 옛 형식은 변환하지 않고 거절한다

- `display_mode` 로 쓴 Template(v0.1.0 · v0.2.0)은 파서가 거절한다. 읽을 때 번역하는 코드는 두지 않는다.
- 두 파일은 이력으로 남기고 동결한다. 실행 경로(`JsonMonthlyTemplateRepository`)는 읽지 않는다.

### 3. 승인은 새 version 에 물려주지 않는다

- v0.1.1 · v0.2.1 은 `PENDING_HUMAN_REVIEW` · `runtime_active: false` · `approved_by` / `approved_at`: `null` 이다.
- v0.1.0 · v0.2.0 의 승인은 계승되지 않는다. version 마다 자기 승인 기록을 갖는다.

### 4. 동결과 승인 대기 고정을 나눈다 (`test_freeze.py`)

| 목록 | 무엇 | 바뀔 수 있나 |
|---|---|---|
| `FROZEN_ARTIFACTS` | 다시는 바뀌지 않는 파일. `review` 승인 블록이 있으면 반드시 `HUMAN_APPROVED` | 아니다. SHA 가 바뀌면 다른 계약이다 |
| `PENDING_REVIEW_PINS` | 사람 승인 대기 파일. Golden 이 이 파일로 돈다 | 승인 커밋에서 한 번만 |
| `PENDING_REVIEW_CONTENT` | 승인 대기 파일에서 `APPROVAL_METADATA_KEYS` 를 뺀 내용의 SHA | 아니다. 승인 뒤에도 남긴다 |

- 두 목록은 겹치지 않는다. `data/templates/` 의 모든 파일은 둘 중 하나에 있다. 목록과 파일의 승인 상태가 다르면 실패한다.
- `FROZEN_ARTIFACTS` 의 `institution_evidence_v0_1_0.json` 은 승인 게이트가 없는 Corpus 관측 자료라 무결성 때문에만
  동결돼 있다(이번에 바꾸지 않았다).

### 5. 같은 version 의 승인 전환 절차

**실제 사람 승인이 있을 때만** 한다. 이 ADR 은 v0.1.1 · v0.2.1 을 승인하지 않는다.

1. `review` 의 `APPROVAL_METADATA_KEYS` 만 고친다 — `domain_owner_approval` → `HUMAN_APPROVED`, `approved_by`
   (OD-N10 규칙 `reviewer_<role>_<sequence>`), `approved_at`(오프셋 포함 ISO-8601), `runtime_active` → `true`,
   `runtime_active_note`. **그 밖의 내용은 한 글자도 바꾸지 않는다.**
2. 그 항목을 `PENDING_REVIEW_PINS` 에서 빼고 새 SHA 로 `FROZEN_ARTIFACTS` 에 넣는다.
3. `PENDING_REVIEW_CONTENT` 항목은 그대로 둔다. `test_reviewed_content_is_unchanged_apart_from_approval_metadata` 가
   승인 메타데이터 말고 바뀐 것이 없음을 확인한다.
4. 그 뒤에는 파일을 고치지 않는다. 내용을 바꾸려면 새 version 을 낸다.

경로 · 운영 코드는 바뀌지 않는다. 승인 상태는 파일 내용에서 파생되므로 BE-1 목록은 `approved: true` 로 바뀐다.

### 6. 승인 확인은 Core 생성 진입점이 최종으로 한다

- `GenerateMonthlyPlan` 은 기존 Port `MonthlyTemplateRepository` 를 **필수로** 받는다. 스냅샷 · LLM 호출 · 계획안 ·
  Audit · 저장 전에 `profile.base_template_ref` 를 **정확한 id · version** 으로 찾는다.
  - 없거나 다른 version 이 오면 → `monthly_template_not_found`
  - `HUMAN_APPROVED` 가 아니면 → `monthly_template_not_approved`
- Template 은 승인 여부를 보려고만 읽는다. **계획안 구조는 여전히 Profile 스냅샷에서 온다.**
  `resolve_snapshot_sections` 는 저장소를 읽지 않는 순수 함수로 둔다.
- Backend 검사(`approved_template` — Profile 시작 · DRAFT · READY 전환, `ready_profile_for_generation` — 생성 직전)는
  그대로 둔다. Backend 는 사용자에게 오류 코드를 일찍 주는 계층이고, Core 가 모든 호출자의 최종 보장이다.
- 편집 · 재생성 · 확정은 승인을 다시 보지 않는다. 계획안은 생성 때의 스냅샷에 묶여 있다.

### 7. 테스트는 격리된 승인 Fixture 만 쓴다

- 실제 승인 대기 파일을 승인 처리하지 않는다. 생성 성공이 필요한 테스트는 `ApprovedTemplates`(OD-N11 (A) —
  실제 Template 을 정확히 읽어 메모리에서만 `runtime_active=True`)를 쓴다. 운영 코드는 이 객체를 받지 않는다.
- Golden 기대값은 바뀌지 않는다. Golden 은 Template version 을 기록하고 승인 상태는 기록하지 않는다.

## 근거

- **[실측]** `display_mode` 는 칸 수를 정했다 — `cell_count_for` 가 `MONTHLY_MERGED_SUMMARY` → 1, `WEEKLY_CELLS` →
  활성 주 수, AXIS → 0 이다. 이름을 바꾼 뒤 Golden 값 · Evidence · fingerprint 가 그대로다(PR #122 리뷰에서 재현).
- 사용자 결정(2026-10-06, 원 ID `TP-21`): **승인은 파일 내용(SHA)에 대해 받은 것**이고, version 이름은 계획안이 어느
  Template 으로 만들어졌는지의 기준이다. 제자리에서 고치면 승인 기록과 version 의미가 깨진다.
- **[실측]** 결정 당시 월간 계획안을 저장하는 경로가 없어 옛 version 을 참조하는 데이터가 없었다 — 번역 코드가 지킬
  대상이 없다. **[판단]** 번역을 두면 두 어휘가 계속 살아 「어느 이름이 계약인가」가 모호해지고, 옛 파일이 다시
  들어오면 명시적인 이전 작업을 거치게 하는 편이 낫다.
- 사용자 결정(2026-10-08, 원 ID `Part 12.8`): 새 version 은 지금 승인하지 않고, 승인은 계승하지 않는다.
  version 마다 자기 승인 기록을 갖는 것이 기존 선례다(`OD-N10`).
- **[실측]** 승인 대기 Template 은 런타임이 읽을 수 있어야 한다 — BE-1 계약(후속 브랜치
  `feature/full-monthly-m6-be1-template-profile-management` 의 `docs/api-spec.md` §9-4, 사용자 결정 2026-10-10)이 목록에 `approved: false` 로 보이고 시작은 409 `GATE_BLOCKED` 로 거절하라고 정했다. 그래서 활동 자료처럼
  초안 파일을 런타임 밖에 두는 방식은 맞지 않는다. 승인 상태는 경로가 아니라 파일 내용(`review`)에서 파생된다.
- **[실측]** 이 ADR 전에는 승인 확인이 `resolve_sections` 에만 있었고 `src` 안에서 부르는 곳이 없었다. Core 를 직접
  부르는 harness · 테스트(후속 브랜치에서는 벤치 스크립트도)가 승인 대기 Template 으로 계획안을 만들어 확정까지 갔다.
- 사용자 결정(2026-10-10, PR #122 리뷰 D1 ~ D7): 위 4 · 5 · 6 · 7.

## 대안

- **`display_mode` 를 읽을 때 번역한다.** 처음 권장안이었으나 버렸다 — 승인 파일을 그대로 두면서 어휘를 하나로
  만들 수 없다.
- **`NONE` 대신 `ONCE` · `DOCUMENT`**(리뷰 제안). 고르지 않았다 — `NONE` 은 이미 정한 값이고, 헷갈리는 지점은
  `null` 과의 구분이라 위 표로 적었다.
- **월간 주제에 `MONTH`.** 고르지 않았다. 월간 문서에서 「달마다」는 「문서에 한 번」과 같아 단위가 모호하다.
  반복 단위는 문서 기준으로 센다.
- **승인 대기 파일을 고정 없이 동결 목록에서만 뺀다**(리뷰 제안 (a)). Golden 이 도는 파일 내용을 아무도 지키지 않게 된다.
- **초안 · 승인본 파일을 나눈다**(리뷰 제안 (b)). 위 BE-1 계약을 깨거나, 같은 version 파일 둘을 읽는 저장소가 필요하다.
  런타임 안전성은 나아지지 않는다.
- **`resolve_snapshot_sections` 에서 승인을 본다.** 순수 구조 함수가 저장소를 읽게 되고, 스냅샷의 의미(생성 당시
  구조)와 섞인다.
- **Backend 에서만 본다.** Core 를 직접 부르는 길이 열려 있다.

## 결과

- `GenerateMonthlyPlan` 의 모든 호출자가 Template 저장소를 넘겨야 한다. 이 브랜치에서는 테스트 harness 두 곳을 고쳤다.
  **M4 이후 브랜치(월간 Composition Root · backend 생성 API · 벤치)는 이 변경을 자동으로 받지 않는다** — 반영은 별도 단계다.
- Core 오류 코드 `monthly_template_not_found` · `monthly_template_not_approved` 가 생겼다. Backend 가 먼저 거절하므로
  HTTP 로는 보통 닿지 않지만, 공개 오류 코드로 어떻게 옮길지는 Backend 반영 때 정한다.
- 사람 승인 전까지 실제 파일로 Core 월간 생성은 항상 거절되고, Backend 「Reference 기반 시작」은 409 다.
- 동결된 옛 승인 파일(v0.1.0 · v0.2.0 등)은 저장소 밖 문서(`docs/open-decisions.md` · `docs/m0-human-review.md`)를
  인용한다. 동결 파일이라 인용만 고치려고 바꾸지 않는다.

## 아직 정하지 않은 것 (채택 아님)

- v0.1.1 · v0.2.1 의 실제 사람 승인, 승인자 id, 승인 시각.
- Template 승인 철회 정책 — 철회된 version 으로 만든 기존 계획안 · READY Profile 을 어떻게 할지.
- `MONTH` · `DAY` 지원(연간 · 주간 TemplateSection 계약이 생길 때).
- `OD-N11` 의 남은 항목(테스트 전용 승인 진입점을 어디에 둘지, 미승인 Golden case 의 Fixture 형태).
- Core 의 새 오류 코드를 Backend 공개 오류 코드로 어떻게 옮길지.
