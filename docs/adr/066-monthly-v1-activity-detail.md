# ADR-066: 주제형 월간의 바깥놀이 · 실내 대체활동 칸에 주마다 숨은 설명을 붙인다

- 2026-11-06
- 상태 — 채택 (Human Decision 2026-11-06(하민) — 주제형 월간(Template A)의 `outdoor_play` · `indoor_alternative` 주 칸마다
  「유아가 무엇을 하는지」 1~2문장 설명을 같은 LLM 요청에서 함께 받고, 문서에는 찍지 않고 칸 편집에서만 보인다)
- 관련 — ADR-027(Template 승인 Gate) · ADR-060(요청 메모) · CLAUDE.md §5 · §13 · §19 · api-spec §9

## 맥락

주제형 월간의 바깥놀이 · 실내 대체활동 칸은 활동 이름 한 줄이다. 교사는 그 활동에서 유아가 무엇을 하는지 알려면
근거를 따로 찾아야 했다. 문서 양식(한 칸 한 줄)은 바꾸지 않고, 칸 편집에서만 볼 설명이 필요하다.

## 결정

1. **새 양식 판을 만들지 않는다.** Template 새 판은 사람 승인 Gate(ADR-027)를 다시 지나야 하고, 기존 원 프로필은 v0.2.3 에
   고정돼 있다. 대신 Core 가 생성 시 Template Snapshot 에 **동반 Section 두 개**를 덧붙인다
   (`TemplateSnapshot.with_activity_details()`).
   - `outdoor_play_detail`(「바깥놀이 설명」) · `indoor_alternative_detail`(「실내 대체활동 설명」)
   - `role = CONTENT` · `repeat_by = WEEK` · `visible = false` · `category` 는 부모와 같다 · `order` 는 맨 뒤(최대 order + 1, + 2)
   - 부모 Section 이 Snapshot 에 있을 때만 붙는다 — 실내 대체활동이 꺼진 계획안에는 `indoor_alternative_detail` 도 없다.
   - Snapshot 에 들어가므로 BE 의 `shown[section_key]` 조회 · 내보내기(`visible = false` 건너뜀)가 그대로 동작한다.
2. **칸은 부모의 주마다 하나다.** 주소는 다른 주 칸과 같은 `(section_key, week_id)` 이고 `item_id` 는 IdGenerator 가 준다.
3. **같은 한 번의 요청에서 받는다.** 맥락형(v1) 요청에서만 해당 부모 주 칸 객체에 `detail` 문자열을 더 받는다
   (structured output schema 확장, 미해결 칸은 `""` 만 허용). prompt version 에 `+activity-detail-v1` 이 붙는다.
   맥락이 없는 요청의 prompt 바이트는 바뀌지 않는다. 셀 재생성은 10번을 따른다.
4. **LLM 은 부모를 바꾸지 못한다.** 설명은 부모 칸 값 · 근거와 별개로 저장되고, 수리(repair)는 설명을 건드리지 않는다.
5. **설명은 실패 사유가 아니다.** 빠졌거나 · 형식이 틀렸거나 · 표시 문장 정책 위반 · 2문장 초과 · 근거 원문 복사 · 입력에 없는
   사실이면 서버가 `""` 로 버린다(내용 없는 로그 한 줄). 부모가 비었거나 미해결이어도 `""` 다.
6. **Provenance.**
   - 채워진 설명: `RULE_LLM` · `rule_version` = 그 칸의 prompt version · Evidence = 부모 칸 Evidence 복사(교사 메모 표시는 뺌).
   - 빈 설명(`RULE_ONLY` 생성 포함): `""` · `EMPTY_VALID` · `RULE_ONLY`(`monthly.template.section_resolution` v1) · Evidence 없음.
   - 모든 칸은 `CREATED` 이벤트로 시작하고, 기존 편집 경로로 고치면 `TEACHER_EDITED` 다.
7. **확정 조건이 아니다.** 빈 설명이 있어도 확정된다. 설명 칸 자체는 재생성 대상이 아니다(부모 칸을 재생성하면 함께
   바뀐다 — 10번). 연령 검증은 설명 칸을 건너뛴다(부모 칸이 검증된다).
8. **주간 생성은 설명을 읽지 않는다.** 주간은 월간 Section 을 key 로 골라 읽는다.
9. **옛 계획안은 그대로다.** Snapshot 에도 칸에도 설명이 없는 계획안은 그대로 읽고 · 고치고 · 재생성하고 · 확정한다.
   저장은 JSONB 라 마이그레이션이 없다.
10. **부모 칸을 재생성하면 같은 주의 설명도 함께 다시 만든다**(Human Decision 2026-11-06(하민)). 옛 활동 설명으로 남지 않는다.
    - 맥락형(v1) 셀 재생성 요청이 `outdoor_play` · `indoor_alternative` 주 칸을 대상으로 하고 Snapshot 에 그 설명 Section 이
      있으면, 같은 요청의 `section` 에 `detail` 하나를 더 받는다(`MonthlyCellPlanningRequest.detail_requested`, prompt version 에
      `+activity-detail-v1`). 그 밖의 셀 재생성 요청(맥락 없음 · 다른 Section · 설명 없는 옛 계획안)의 prompt 바이트는 바뀌지 않는다.
    - 검증은 생성 때와 같다(5번). 버려지면 `""` 이고 재생성은 실패하지 않는다. `RULE_ONLY` 재생성(바깥놀이)은 설명을 `""` 로 둔다.
    - Provenance 는 6번과 같다 — 채워지면 `RULE_LLM` · `rule_version` = 부모 칸의 새 prompt version · Evidence = 부모 칸의 새
      Evidence(교사 메모 표시는 뺌), 비면 `RULE_ONLY` · Evidence 없음. 설명 칸에도 같은 actor · 시각의 `REGENERATED` 이벤트
      (값 · 생성 방식 변화)가 남는다. 교사가 고친 설명도 덮어쓴다(부모 칸과 같다).
    - 원래 비어 있었고 새 설명도 비면 바꿀 것이 없으므로 이벤트도 남기지 않는다.
    - 같은 주의 다른 칸 · 다른 주의 설명은 그대로다. HTTP 응답은 계획안 전체라 공개 계약은 바뀌지 않는다
      (감사 이력에는 설명 칸의 `REGENERATED` 가 하나 더 보인다). 화면에는 이 이력을 따로 띄우지 않는다 — 지금 월간 화면에
      이력을 보이는 곳이 없다(Human Decision 2026-11-06(하민), 기록 화면을 만들 때 다시 정한다).

## 근거

- 무엇을 하는 활동인지는 Rule · 근거가 이미 정했다. LLM 은 그 범위 안에서 설명 문장만 쓴다(CLAUDE.md §5).
- Template 판을 올리지 않으므로 승인 Artifact SHA(test_freeze)가 바뀌지 않는다.

## Golden 계약 변경

`p0-planning/tests/finalization/golden/` 의 `monthly_rule.json` · `monthly_llm.json` 에 `outdoor_play_detail`
(W1~W5, `""` · `EMPTY_VALID` · `RULE_ONLY`) Section 이 더해졌고, `cell_regeneration.json` · `cell_regeneration_goals.json` 의
형제 칸 수가 5 늘었다(15→20, 21→26). 이 Golden 들은 맥락 없는 요청이라 설명이 비는 것이 계약이다. 그 밖의 값은 같다.
10번(설명 함께 재생성)은 Golden 을 바꾸지 않는다 — 셀 재생성 Golden 의 대상은 `focus` · `goals` 라 설명의 부모가 아니다.

## 해결된 문제

- ~~부모 칸을 재생성하면 설명은 옛 활동 설명으로 남는다.~~ → 결정 10번(Human Decision 2026-11-06(하민)).
  비선택 Item 보존(CLAUDE.md §19)은 그대로다 — 설명은 선택한 칸에 딸린 칸으로 함께 바뀌고, 그 밖의 칸은 보존된다.
