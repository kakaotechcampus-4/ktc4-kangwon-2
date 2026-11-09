# ADR-079: 근거 자료의 기관 정보를 가명으로 덮어쓴다

- 날짜: 2026-11-08
- 상태: 채택 (2026-11-08 하민 Human Decision)
- 보완: ADR-027(승인 Artifact 동결). CLAUDE.md §8 「Reference 내용이 바뀌면 기존 version 을 덮어쓰지 말고 새 version 을 발행한다」의
  **한 번짜리 예외**다. CLAUDE.md 는 고치지 않는다.

## 맥락

[실측] `p0-planning/data/` 의 근거 창고 · 활동 Reference · Theme Reference · 월간 Template 에 실제 기관 이름, 기관 유형,
기관 이름이 든 원본 파일 경로(`references/samples/...`), 기관 slug 가 들어 있었다. 서버 이미지와 저장소에 실린다.

이유는 저작권 · 개인정보다. 특정 기관의 요청이나 문제가 있어서가 아니다. 계획안 생성은 기관이 **누구인지** 쓰지 않는다 —
`institution_id` 는 검색 다양성(같은 기관 최대 2건)과 Context 별칭(S1 · S2 …)의 묶음 키로만 쓰인다.

새 version 을 발행하면 실명이 든 옛 version 이 그대로 남아 목적을 이루지 못한다. 그래서 같은 version 을 덮어쓴다.

## 결정

1. **같은 파일 · 같은 version 을 덮어쓴다.** record_id · source_sha256 · 원문 · 연령 · 월 · Section · 판정 · 품질 값은 그대로다.
2. **기관 이름 → `inst_NNN`.** 원본 PDF sha256 으로 기관을 묶고, 기관마다 가장 작은 sha256 순으로 `inst_001` 부터 번호를 준다.
   한 기관은 모든 파일에서 같은 번호다. slug(`origin_id` 3번째 칸, `observed_institutions` · `origins_used` 값, 키 이름, 메모)와
   본문 속 이름 · 줄임말도 같은 번호로 바꾼다.
3. **기관 유형을 지운다.** `institution_type` 키와 Template 의 `institution_types` 집계를 뺀다.
4. **원본 경로 → `references/samples/<kind>/<sha12>.pdf`.** 파일 이름이 sha256 앞 12자리다. 로컬 원본은 sha256 으로 찾는다
   (`ssuksak.dev.verify_evidence_store`).
5. **근거 본문에 나온 기관 자기 이름의 줄임말 1곳 → `○○어린이집`.** 「열린어린이집 부모참여」의 「열린어린이집」은 기관 이름이 아니라
   열린어린이집 사업 이름이라 원문 그대로 둔다(2건).
6. **대응표를 남기지 않는다.** 실명 ↔ 가명 표는 어떤 파일 · 로그에도 쓰지 않았다. 덮어쓴 스크립트도 저장소에 넣지 않는다.
7. **git 이력은 그대로 둔다.** 이력 재작성은 하지 않는다. 이 ADR 이후 커밋부터 실명이 없다.
8. **해시를 한 번 다시 고정한다.** 바뀐 파일의 파일 SHA · content SHA, 근거 창고 `build.content_sha256`, 이를 참조하는
   분류 4종(`content_sha256`)과 `test_freeze.py` · 근거 창고 테스트 · 검토 문서의 값을 새 값으로 바꿨다. 이 한 번 말고는
   ADR-027 대로 SHA 를 고치지 않는다.
9. 문서 · 테스트 · 목업의 실제 기관 이름도 같은 가명이나 지어낸 이름(햇살어린이집 등)으로 바꿨다.
   `backend/resources/daycares/daycares.csv`(정부 공개 어린이집 목록, ADR-068)는 그대로다.

## 결과

- 검색 결과는 같다 — 월 6 × 연령 6 = 36개 경우의 월간 · 주간 근거 record_id 목록이 가명화 전후 똑같다.
- Context 별칭(S1 · S2 …)은 `sorted(institution_id)` 순이라 번호가 바뀔 수 있다. 의미는 같다.
- 승인은 승계한다. 바뀐 것은 기관 식별 정보뿐이다.
- 근거 본문 중 기관이 **자기 이름**을 행사명에 쓴 기록(2개 기관, 13건)도 `○○` 로 바꿨다(a77c6d6d).
