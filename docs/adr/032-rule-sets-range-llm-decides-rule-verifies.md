# ADR-032: Rule 이 범위를 정하고, LLM 이 그 안에서 정하고, Rule 이 검사한다 — `generation.method` 의 뜻

- 2026-10-19
- 상태 — 채택 (PM-02 B · PM-12 B, ADR-030)
- 보충 — ADR-014 (대체하지 않는다)

## 맥락

「계획안 내용을 누가 정하나」를 문서마다 다르게 적었다.

| 문서 | 적힌 것 |
|---|---|
| ADR-005 (2026-09-07, 대체됨) | 배치 · 선별은 규칙 엔진, LLM 은 문장화만 |
| ADR-014 (2026-09-19) · 루트 `CLAUDE.md` | LLM/RAG 가 만들고 규칙 엔진이 검사한다. 명시된 조건의 거르기는 규칙에 남는다 |
| 2026-09-26 Human Decision(`RULE_LLM` 정의) | Rule 이 허용한 후보 · 근거 · 제약 범위 안에서 LLM 이 현재 값의 의미 내용을 정한다 |
| 개인 P0 `CLAUDE.md` §5 · §6 | ADR-005 계열 문장이 남아 있었다 |

루트 `CLAUDE.md` 는 이 원칙을 「연간계획안」에만 적어, 월간 · 주간에도 같은지 팀 문서로는 확인되지 않았다(K-01).
`generation.method` 에 무엇을 적는지도 정해지지 않았다 — 연간 Core 는 mock 생성기를 써도 `RULE_LLM` 을 기록한다(K-37).

## 결정

### 1. 세 단계 — 연간 · 월간 · 주간 공통

```text
Rule   허용 범위를 정한다     승인된 후보 · 근거 · 제약 · 칸 구조 · 법정 기준
LLM    그 범위 안에서 정한다    값의 의미 내용을 고르고 구성하고 문장으로 쓴다
Rule   결과를 검사한다         계약 · 근거 · 연령 · 법정 기준을 어겼는지
```

- **LLM 은 문장만 다듬는 역할로 줄어들지 않는다.** 범위 안에서 무엇을 쓸지를 LLM 이 정한다.
- **LLM 은 범위 밖을 정하지 않는다.** 승인 목록에 없는 Reference id, 다른 칸 · 다른 주, 근거 없는 사실, 법정 기준, 연령 적합성,
  통과 여부는 LLM 이 정하지 않는다. 범위 밖 값은 검사 단계가 거절한다(fail closed).
- **「무엇이 더 좋은가」를 규칙이 판정하지 않는다**(ADR-014 그대로). 규칙의 거르기는 명시된 조건(연령 · 승인된 판 · 쓸 수 있는 달 ·
  혼합반 전 연령 지원)뿐이다. 범위가 후보 하나로 좁혀지는 것(연간 Theme)은 조건으로 거른 결과이지 규칙이 우열을 판정한 것이 아니다.
- 생성은 여전히 문서 단위 배치로 부른다(연간 12개월 · 월간 한 달 · 주간 한 주). 칸마다 부르지 않는다.

### 2. `generation.method` 의 뜻 (PM-12 B)

| 값 | 언제 |
|---|---|
| `RULE_LLM` | **LLM 경로로 설계된 칸.** Rule 이 허용한 범위 안에서 LLM 이 그 값의 의미 내용을 정했다 |
| `RULE_ONLY` | LLM 없이 Rule · Template 이 정한 칸 (예: 근거가 없어 비워 둔 안전교육, Template 기본값) |
| `IMPORTED` | 기존 계획안에서 가져온 칸 (Import 는 지금 비활성 — ADR-030 PM-11) |
| `MANUAL` | 사람이 처음부터 쓴 칸 |

- **mock 생성기를 썼는지는 `generation.method` 로 가르지 않는다.** `LLM_MODE=mock` 인지는 실행 기록(Generation Run · 서버 설정 ·
  `llm_usage` 로그 유무)으로 안다. Core 값과 Golden 기대값은 바꾸지 않는다.
- **교사가 고쳐도 바꾸지 않는다.** 교사 수정은 `TEACHER_EDITED` Audit 이벤트다(루트 `CLAUDE.md`). `GenerationMethod.TEACHER_EDIT`
  enum 값은 남아 있지만 쓰지 않는다 — 제거 여부는 미정.
- **`rule_version` 은 칸마다 지금 값을 만든 단계를 적는다.** 첫 생성 값은 첫 프롬프트 version, LLM 수리가 실제로 바꾼 값은 수리
  프롬프트 version 이다. 결정적인 이름 맞추기(`REFERENCE_VALUE_MISMATCH` 정규화)는 생성 단계가 아니라 계약 정규화라 첫 version 을
  유지한다(2026-09-26 Human Decision, ADR-033).

## 근거

- **[출처]** PM-02 = B · PM-12 = B (2026-10-19, ADR-030). 2026-09-26 `RULE_LLM` 정의를 공식 문장으로 삼는다.
- **[실측] 연간 Core 가 실제로 하는 일 (develop `abf97f0`).**
  - `rules/yearly_theme_selection.py` `select_theme_for_period` — 승인된 Theme Reference 에서 그 달 · 반 전 연령을 지원하는 후보만
    거른다. 후보가 여럿이면 그 달 근거가 강한 것, 같으면 id 순이다(우열 판정이 아니라 결정적 순서).
  - `application/yearly_support.py` `generate_theme_text` — LLM 이 Rule 이 고른 `theme_id` 마다 문장을 쓴다. 결과의 (달, `theme_id`)
    쌍이 요청과 다르면 `invalid_theme_text_result` 로 거절한다 — LLM 이 Theme 을 바꾸지 못한다.
  - `application/generate_yearly_plan.py` — 그 칸을 `RULE_LLM` 으로 기록한다.
  - **연간은 범위가 후보 하나까지 좁혀지는 경우다.** B 의 「범위 안에서 LLM 이 정한다」에 들어간다 — LLM 이 정하는 것은 그 Theme 의
    문장이다.
- **[실측] 월간 Core.** Rule 이 승인 참조자료 · 근거 분류 · 칸 구조(TemplateSnapshot) · 안전교육 배치 정책으로 Context Packet 을 만들고,
  LLM 이 칸 값을 정하고, Validator 가 근거 · Reference id · 연령을 검사한 뒤 Verifier 가 연령 · 안전 배치 규칙을 돌린다(ADR-033 · 037).
- **[판단]** 주간은 이 계약이 생기기 전이다. 주간 계약(W1)도 이 세 단계를 따른다.

## 대안

- **(A) ADR-014 문장을 연간 · 월간 · 주간 공식으로.** 「규칙이 범위를 정한다」가 빠져 Core 의 Theme 선택 · Context Packet 을 설명하지
  못한다 — 고르지 않았다.
- **(C) 연간과 월간을 따로 적는다.** 같은 원칙을 두 번 적게 된다 — 고르지 않았다.
- **mock 이면 `RULE_ONLY` 로 적는다(PM-12 A).** Core 수정과 Golden 기대값 변경이 필요하고, 운영(real)과 개발(mock)의 출처 기록이 갈린다 —
  고르지 않았다.

## 결과

- 루트 `CLAUDE.md` 「생성」의 Rule/LLM 문장을 이 세 단계로 바꾼다. ADR-014 · ADR-005 의 이력은 그대로 둔다.
- screen-spec S7 의 「RAG 로 생성하고 규칙 엔진이 검사한다」를 이 문장에 맞춘다.
- 개인 P0 `CLAUDE.md` §5 · §6 의 「LLM 은 문장화만」은 팀 규칙이 아니다. 개인 문서 정리 때 이 ADR 로 포인터를 단다.
