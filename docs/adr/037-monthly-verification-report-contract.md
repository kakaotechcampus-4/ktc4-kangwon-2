# ADR-037: 월간 검증 결과는 「무엇을 돌렸나」와 「무엇을 찾았나」를 따로 준다 — 찾은 것만으로 확정을 막지 않는다

- 2026-10-19 (결정은 2026-09-23 · 2026-09-24 · 2026-09-26)
- 상태 — 채택 (옮겨 적기, PM-13 C · AP-06)
- 보충 — ADR-014 (대체하지 않는다)
- 관련 — `p0-planning/src/ssuksak/planning/domain/monthly_verification.py` · api-spec §9-1 「월간계획안 응답」

## 맥락

ADR-014 는 규칙 엔진의 출력을 「위반 목록」으로 정했고, 연간 Backend 검사기는 4필드(`month` · `rule` · `severity` · `detail`)와
`VIOLATION` · `UNVERIFIED` 를 쓴다. 월간 Core 는 그 뒤 더 자세한 결과 계약을 만들었는데(V1-5 · V1-7 · V1-8 · Structural Freeze),
그 기록은 개인 문서(`FULL-MONTHLY-VERIFICATION-POLICY.md` · `V1-5-SCOPE-CLOSURE.md`)에만 있었다. 연간과 월간의 이름이 달라
매핑이 미결로 남았다(K-30).

## 결정

### 1. 결과 모양

| 타입 | 필드 |
|---|---|
| `Violation` | `rule_id` · `rule_version` · `code` · `finding_kind` · `severity` · `location` · `message` · `evidence` |
| `FindingKind` | `VIOLATION` · `NOT_VERIFIED` |
| `Severity` | `ERROR` · `WARNING` |
| `ViolationLocation` | `section_key`(선택) · `week_id`(선택) |
| `ViolationEvidence` | `observed_value` · `source_refs` |
| `VerificationReport` | `target_plan_id` · `executed_rules` · `source_refs` · `findings` |

- **`executed_rules` 는 실제로 돌린 규칙만 적는다.** 돌리지 않은 규칙 · 아직 없는 규칙 · 실행 실패를 `NOT_VERIFIED` 로 꾸며 넣지 않는다.
  **finding 이 비었다고 전체가 통과한 것이 아니다** — 무엇을 돌렸는지와 함께 읽는다.
- `rule_version` 은 알고리즘 · 계약의 판이고, `source_refs` 의 version 은 승인된 입력 자료의 판이다. 둘은 다르다.

### 2. 저장 · 확정 정책

- 구조 · 근거가 유효하고 검사기가 돌았으면 **finding 이 있어도 DRAFT 와 결과를 저장한다.**
- **finding 만으로 확정을 막지 않는다.** `ACTIVITY_AGE_UNSUPPORTED` 는 `VIOLATION` · `ERROR` 지만 그것만으로 확정을 막지 않는다.
  severity 는 행동 정책이 아니다. 교사가 보고 판단한다.
- **예외 — 안전교육 배치의 근거 오류는 저장을 막는다.** `SAFETY_OFFICIAL_GROUNDING_MISSING` · `SAFETY_SUPPLEMENTAL_GROUNDING_INVALID`
  (배치 selector 가 있을 때만, ADR-033 §4).
- **검사 전에 막히는 것은 finding 이 아니다.** 모르는 Reference id, 그 칸에 쓸 수 없는 Reference, 바깥놀이 근거 연령 불일치, 수리 뒤에도
  남은 오류는 아무것도 저장하지 않고 결과에도 남지 않는다.
- 생성 · 편집 · 재생성은 저장 전에 검사하고, 확정은 확정 직전에 **새로** 검사한다. 내용이 바뀐 뒤 옛 결과를 다시 쓰지 않는다.
  **검사기가 돌지 못하면 저장 · 확정하지 않는다**(500 `GENERATION_FAILED`, api-spec §9-3).
- 이미 CONFIRMED 인 계획안에 확정이 다시 오면 검사를 다시 돌리지 않는다 — 첫 확정의 결과가 남는다(ADR-035 §2).
- 검사 결과로 자동 재생성 · 재시도하지 않는다.

### 3. 지금 돌리는 규칙

| 규칙 | 언제 |
|---|---|
| `monthly.activity.supported_ages / v2` | 생성 · 편집 · 재생성 · 확정마다. Activity Catalog 가 없어도 돈다 |
| `monthly.safety.placement / v1` | 안전교육 배치 selector 가 있을 때(지금 Backend 는 넘기지 않는다) |

- `legal_hours` · `safety`(위험 도구) · `domain_balance` 는 **DEFERRED** 다. `executed_rules` 에 넣지 않고 통과로도 표시하지 않는다.
  다시 시작할 조건(구조화된 시수 기록, 승인된 도구 분류, 활동 영역 매핑 등)은 원 결정 기록에 있다.

### 4. 연간 이름과의 관계

- 연간 Backend 검사기의 `UNVERIFIED` 는 뜻으로 월간 Core 의 `FindingKind.NOT_VERIFIED` 에 대응한다. Core 는 `Severity` 를 더 갖는다.
- 이름을 하나로 바꾸지 않는다. 두 쪽 응답은 각자의 계약(api-spec §4 · §9-1)을 따른다.

## 근거

- **[출처]** 사용자 승인: V1-5 범위 종료(2026-09-23), V1-7 · V1-8(2026-09-24), Structural Freeze(2026-09-26). 원 기록은 개인 문서에 있고
  이 ADR 이 옮겨 적는다(PM-13 C).
- **[실측]** `domain/monthly_verification.py` 의 `Violation` · `VerificationReport` 필드가 위 표와 같다(develop `abf97f0`).
- **[실측]** 최종 Golden(`p0-planning/tests/finalization/golden/`)이 결과 요약(`executed_rules` · `source_refs` · finding 의 rule · code · kind ·
  severity · location)을 고정한다. 메시지 · 관측값은 고정하지 않는다.

## 대안

- **finding 이 있으면 확정을 막는다.** 근거가 확인되지 않은 규칙으로 교사를 막게 된다(ADR-014 「없는 기준으로 막지 않는다」) — 고르지 않았다.
- **연간 4필드로 맞춘다.** 위치 · 근거 · 실행 범위를 표현하지 못한다 — 고르지 않았다.

## 결과

- 화면은 「무엇을 검사했나」와 「무엇을 찾았나」를 따로 보여 준다(api-spec §9-1 응답).
- 연간에도 같은 결과 계약을 쓸지는 정하지 않았다. 연간은 지금 api-spec §4 의 `checked_rules` · `checks` 를 쓴다.
