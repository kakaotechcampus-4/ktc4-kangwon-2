# ADR-033: 월간 Core 계약 동결 — 근거 출처 · 생성 모드 · 안전교육 배치 v2 · 수리 1회

- 2026-10-19 (결정은 2026-09-13 · 2026-09-26 Human Decision)
- 상태 — 채택 (옮겨 적기, PM-13 C · AP-06)
- 관련 — ADR-014 · ADR-032 · ADR-037 · `p0-planning/data/rules/` · `p0-planning/tests/finalization/`

## 맥락

월간 Core(Full Monthly Plan v1)의 구조 계약은 2026-09-26 「Structural Freeze」로 동결됐고, 그 근거 결정(OD-N13 · OD-N14 · OD-N15,
OD-M04 일부 대체)은 개인 결정 문서(`docs/open-decisions.md`, 저장소 밖)에만 있었다. api-spec §9-1 과 동결 데이터 파일이 이 결정을
전제로 하는데 리뷰어가 근거를 볼 수 없었다(K-25). **이 ADR 은 원 ID 를 그대로 두고 내용을 옮겨 적는다.** 새 결정은 없다.

## 결정

### 1. 근거 출처 `INSTITUTION_SAMPLE` (OD-N13, 2026-09-13)

- Evidence Source 에 `INSTITUTION_SAMPLE` 을 더했다. **실제 기관 계획안 Corpus 에서 관찰된 자료**를 칸의 근거로 인용할 때 쓴다.
- `ACTIVITY_REFERENCE` 를 대체하지 않는다. 승인 Catalog 에서 고른 값은 계속 `ACTIVITY_REFERENCE` 다.
- **세 축은 독립이다.** 「무엇을 근거로 했나」(Evidence) · 「어떻게 만들었나」(Generation) · 활동 값의 출처(`activity_origin`).
  `INSTITUTION_SAMPLE` + `RULE_LLM` + `LLM_SYNTHESIZED` 조합이 정상이다. **LLM 이 만들었다는 사실을 Evidence 로 적지 않는다.**
- Corpus 자료는 기본 `CONTEXT_ONLY` 다 — 근거로만 쓰고 원문 활동 문자열을 그대로 결과 값으로 옮기지 않는다.

### 2. 주차 순서의 출처 `week_order_basis` (OD-N14, 2026-09-13)

| 값 | 뜻 |
|---|---|
| `SOURCE_OBSERVED` | 원문이 실제로 몇째 주인지 적은 경우. 추정하지 않는다 |
| `PLANNER_COMPOSED` | 근거는 「그 달에 어떤 경험이 있나」만 말하고, 1주 → 5주 순서는 Planner 가 구성했다. **LLM 생성의 기본값** |
| `TEACHER_ORDERED` | 교사가 주 순서를 바꿨다 |

- 화면 · 내보내기에서 국가 기준이나 공식 순서처럼 보이게 하지 않는다. 「공식 권장 1주차」 · 「누리과정 기준 순서」 · 「표준 주차」를
  쓰지 않는다.

### 3. 생성 모드 `RULE_ONLY` · `LLM_PLANNER` (OD-N15, 2026-09-13)

- `RULE_ONLY` 는 기존 Rule 경로(회귀 · 호환 · 명시적 디버그), `LLM_PLANNER` 는 제품 경로다. 운영 조립은 `LLM_PLANNER` 를 명시적으로 고른다.
- **조용한 대체(fallback)가 없다.** `LLM_PLANNER` 에서 LLM 이 실패하면 생성이 실패한다 — `RULE_ONLY` 결과로 바꿔 내지 않는다.
  Trend · 날씨처럼 빠져도 되는 부가 의존과 다르다. Planner 의 LLM 은 필수 단계다.
- Use Case 안에서 모드를 몰래 바꾸지 않는다.

### 4. 안전교육 — 법정 기준과 배치 정책을 나눈다 (Structural Freeze 2026-09-26, OD-M04 일부 대체)

- **법정 기준(Legal Rule)과 제품의 월 · 주 배치 정책은 다른 판이다.** 법정 충족을 주장하지 않는다.
- 배치 selector 를 넘기면 승인된 제품 정책 `ssuksak-safety-placement-v2`(PRODUCT_POLICY, v1 대체)가 월 · 주 배치를 만든다.
  - 그 달 법정 영역이 하나면 2주, 둘이면 2주 · 4주. 공식 항목은 학년도마다 돌아가는 순서(기준 학년도 2026).
  - 보충 주는 승인 참조자료만 쓴다 — 분류 `safety-evidence-classification-v0.2.0`, 품질 `safety-reference-quality-v0.1.0` 에서
    USABLE 인 것만. NEEDS_REVIEW · EXCLUDED · PENDING 은 런타임에 닿지 않는다.
  - 배치가 선택됐는데 활성 안전 주를 비워 저장하지 않는다.
- **selector 가 없으면** 「근거 필요」 경로다 — 안전교육 칸은 `EMPTY_UNRESOLVED`, 제약 상태는 `NOT_VERIFIED_SOURCE_REQUIRED`.
  지금 Backend 월간 생성은 selector 를 넘기지 않는다(api-spec §9-1 「안전교육」).
- 연간 법정 시수는 평가하지 않는다 — `SAFETY_ANNUAL_HOURS_NOT_VERIFIED`(NOT_VERIFIED · WARNING). `legal_hours` 규칙 자체는 DEFERRED 다.
- 법정 6개 영역이 아닌 이름표(「생활안전」 등)를 6개 영역에 자동으로 맞추지 않는다. `emergency_response` · `drill` 은 따로 둔다.

### 5. Reference id 를 쓸 수 있는 칸 (Structural Freeze)

- `reference_id` 는 `theme` 과 `outdoor_play`(Catalog 후보가 주어졌을 때)에만 있다. `focus` · `goals` · `basic_habit` ·
  `safety_education` 은 늘 `null` 이다. 한 달 생성과 칸 재생성이 같은 규칙을 쓴다.

### 6. 수리는 한 번 (Structural Freeze)

- `REFERENCE_VALUE_MISMATCH`(id 는 맞는데 이름이 다름)는 **결정적으로** 고친다 — 같은 `reference_id` 의 정식 이름으로. LLM 수리가 아니다.
- **LLM 수리는 최대 한 번**(호출 합계 2회). 수리는 지적된 칸 · 필드만 바꿀 수 있고 그 밖의 변경은 버린다.
- 수리 뒤에도 남은 위반은 저장하지 않는다(fail closed).

### 7. 그 밖의 동결 항목

- `goals` 는 생성 안내 120 ~ 160자, 검증 상한 240자. 안내는 검증 규칙이 아니다.
- 바깥놀이 연령: 연령을 모르거나 다른 연령의 근거는 바깥놀이 근거에서 뺀다. `reference_id` 가 있으면 Activity Catalog
  `supported_ages` 로, 없으면 근거 연령을 저장 전에 확인하고 자유 문장은 `ACTIVITY_FREE_TEXT_AGE_NOT_VERIFIED`(NOT_VERIFIED · WARNING).
- 교사 수정은 Generation · `rule_id` · `rule_version` 을 바꾸지 않고 `TEACHER_EDITED` 를 더한다(루트 `CLAUDE.md`).
- `RULE_LLM` 의 정의와 칸별 `rule_version` 규칙은 ADR-032 §2 다.

## 근거

- **[출처]** 2026-09-13 Human Decision(OD-N13 · OD-N14 · OD-N15), 2026-09-26 Human Decision(Structural Freeze). 원문은 개인 결정
  문서에 있고, 이 ADR 이 그 원 ID 를 보존해 옮긴다(PM-13 C).
- **[실측]** `p0-planning/tests/finalization/test_freeze.py` 가 위 데이터 파일(배치 정책 v2 · 분류 · 품질 · 법정 Rule)의 SHA 를 고정한다.
- **[실측]** 근거 Corpus 에 몇째 주인지 적힌 기록이 0건이었다 — 그래서 순서의 출처를 따로 남긴다(OD-N14).

## 대안

결정 당시 대안(근거 미기록, `EXTERNAL_CONTEXT` 재사용, LLM 실패 시 `RULE_ONLY` 자동 대체 등)과 기각 이유는 원 결정 기록에 있다.
이 ADR 은 다시 고르지 않는다.

## 결과

- api-spec §9-1 · §9-3 의 「결정 문서」 인용 중 이 범위는 이 ADR 을 가리킨다.
- 미뤄 둔 것(동결을 막지 않음): 바깥놀이 칸 하나에 활동 여러 개 · 월 안 활동 반복(제품 결정), 교육 표현 품질 · 원문 복사 수리(품질 부채),
  `TEACHER_EDIT` enum · 안 쓰는 도우미 · 낡은 주석(정리 부채). `legal_hours` · `safety` · `domain_balance` 규칙은 DEFERRED 다(ADR-037).
