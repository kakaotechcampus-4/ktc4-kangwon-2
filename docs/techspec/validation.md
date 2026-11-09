# 검증 — LLM 출력을 저장 전에 거른다

「검증」은 시스템이 **스스로** 거르는 장치와, 그 장치가 계속 그렇게 동작하도록 고정한 테스트다.
품질을 사람 · 판정 모델로 잰 것은 [evaluation.md](evaluation.md)에 있다.

## 1. 저장 전 검증 순서

```
1 스키마        출력 형식 · 필수 칸 · 칸 수 · 요청한 칸만 왔는가
2 Reference     id 가 활성 Catalog / 이번에 넘긴 근거 목록에 있는가, 판이 맞는가, 월 · 연령에 맞는가
3 계약 규칙     빈 칸 · 문장 정책 · 근거에 없는 사실 · 원문 베끼기 · 금지 장소 · 후보 형식 · 힌트 반영
   ↓ 어기면
4 수리 1회      어긴 곳(issue code)을 알려 주고 한 번만 고쳐 쓰게 한다 — 재시도가 아니라 수리
   ↓ 그래도 어기면
5 500 · 저장 안 함
```

- **수리 대상은 정해진 칸 안의 문제뿐이다.** 문장 정책 · 근거 선택 · 근거에 없는 사실 · 후보 형식이 여기에 든다. 칸이 빠지거나 요청하지 않은 칸 · 주차 불일치처럼 구조가 깨진 답은 고쳐 쓰게 하지 않는다 — `planner/weekly.py` `REPAIRABLE`
- 순서를 바꾸지 않는다. 형식이 깨진 출력은 뒤 단계에 넣지 않는다.
- 공통 검사는 한 곳에 둔다 — `backend/app/shared/gates/` · `p0-planning/src/ssuksak/planning/planner/`

## 2. 계획안별 검사 (issue code)

| 계획안 | 무엇을 막나 | code (일부) |
|---|---|---|
| 연간 · 월별 주제형 | 정확히 12개월 · 3월 → 2월 순서 · 빈 주제 · Catalog에 없는 `theme_id` · 판 불일치 · 그 달 · 연령에 안 맞는 주제 · LLM이 `theme_id`를 바꿈 | `golden/yearly.json`의 `failure_category` |
| 연간 · 놀이 프로젝트형 | 같은 이름 후보 · 힌트로 준 누리과정 내용을 배움 칸 근거에 안 씀 · 카탈로그에 없는 내용 id · 배움 개수 | `DUPLICATE_PLAY_NAME` · `SEED_CONTENT_MISSING` · `UNKNOWN_CONTENT_ID` · `DUPLICATE_CONTENT_ID` · `LEARNING_COUNT` |
| 월간 | 법정 안전교육 원문 대조 · 근거 id · 장소 · 안전 내용이 다른 칸에 샘 | `STATUTORY_SAFETY_EDUCATION` · `SAFETY_CONTENT_LEAKAGE` · `UNREQUESTED_VENUE` |
| 주간 | 넘기지 않은 근거 id · 다른 칸 근거 인용 · 근거에 없는 사실 · 원문 그대로 베낌 · 후보 형식(「활동명: 설명」 · 합니다체) · 요일 불일치 · 트렌드 비율 · 캐릭터 이름 | `UNKNOWN_GROUNDING_REF` · `WRONG_SOURCE_GROUNDING` · `UNSUPPORTED_FACT` · `SOURCE_TEXT_COPY` · `ACTIVITY_CANDIDATE_INVALID` · `DAY_MISMATCH` · `TREND_SHARE_EXCEEDED` · `TREND_NAME_IN_TEXT` |
| 기존 연간 가져오기 | LLM이 배정한 글자가 원문에 그대로 있는가(결정적 문자열 검사) | ADR-056 |

## 3. LLM을 부르기 전에 멈추는 것

- 상위 계획안이 확정 전이면 409 `GATE_BLOCKED`.
- 승인되지 않은 Reference(`PENDING_HUMAN_REVIEW`)는 성공 경로에 쓰지 않는다.
- 근거 묶음과 분류의 SHA가 안 맞으면 호출 · 저장 전에 중단한다 — `classification.require_bound_to(store.content_sha256)`
- 아동 이름 치환에 실패하면 호출하지 않는다(422).
- 주간 근거 창고에서 사람이 「활동을 알 수 없다」고 검토한 기록은 후보 근거에서 뺀다. 원본 id와 글이 모두 같을 때만 빼므로, 원본이 고쳐지면 다시 후보가 된다 — `REVIEWED_UNCLEAR_ACTIVITY_SOURCES`(ADR-054)

## 4. 테스트로 고정한 것

| 무엇 | 어디 | 고정하는 것 |
|---|---|---|
| Golden — 가짜 LLM | `p0-planning/tests/finalization/golden/` (`yearly` · `monthly_rule` · `monthly_llm` · `weekly_rule` · `weekly_llm` · `cell_regeneration` · `weekly_cell_regeneration` · `play_project_selection`) | 고정한 LLM 답에 대해 **Application이 무엇을 하나**. 통과 · 수리 · 반려 · 저장 안 함. 모델 문장은 기대값으로 굳히지 않는다(ADR-023) |
| 승인 자료 동결 | `p0-planning/tests/finalization/test_freeze.py` | Template · 근거 창고 · Catalog · 법정 Rule의 SHA. 자료가 바뀌면 Golden이 통과해도 여기서 먼저 실패한다 |
| 실패 시 저장 안 함 | `backend/tests/` (`test_create_document_saves_nothing_when_generation_fails` 등) | 생성이 실패하면 DB에 아무것도 남지 않는다 |
| 놀이 연간 재개 | `p0-planning/tests/application/test_play_project_generation.py` | 실패 구간만 한 번 · 겹친 후보만 한 번 · 같은 `row_key` · 요청 반영 후보는 안 바꿈 · 멈추면 저장 안 함 |
| 겹침 검사기의 한계 | `p0-planning/tests/planner/test_play_dup_pairs.py` | 사람이 라벨한 같은 놀이 24짝 · 다른 놀이 18짝. 지금 선이 못 잡는 짝은 xfail로 남겨, 검사기를 바꾸면 바로 보이게 했다 |
| 주간 근거 뽑기 | `p0-planning/tests/retrieval/test_weekly_retrieval.py` | 앞 주 근거는 뒤로 · seed가 없으면 고정 상위 10 · 같은 seed는 같은 결과 · 정확 연령 기록을 따로 먼저 채우지 않음 · 혼합연령 반은 요청 연령마다 1건 (PR 대기) |
| 주간 API | `backend/tests/test_weekly_plans_api.py` | 앞 주차만 넘김 (PR 대기) |
| 호출 기록 | `test_llm_usage_log.py` | 호출마다 숫자만 남고 프롬프트 · 응답은 없다 |

CI가 PR마다 backend + planning core pytest · ruff · alembic · docker build · e2e를 돌린다 — [08](../evaluation/08-code-tests.md)

## 5. 검증에서 고친 실패 (실제 사례)

| 날짜 | 무엇 | 어떻게 찾았나 | 고친 것 |
|---|---|---|---|
| 11-09 | 주간 5주차 500 — 「[절기놀이]」처럼 태그뿐인 제목이 후보 근거로 올라옴 | 앞 주 근거 빼기 실측. 풀 깊은 곳이 처음 드러남 | 태그뿐인 글은 활동 제목이 아니다(정규식) |
| 11-10 | 12월 5주차 500 `ACTIVITY_CANDIDATE_INVALID` — 추출이 잘린 기록 2건(「…퍼즐 -」 · 「…키보」) | 섞어 뽑기 실측 → 그 주의 풀을 호출 없이 다시 계산 | 검토 목록에 2건 추가. 다시 돌려 5주 모두 201 |
| 11-10 | seed 로그가 버려짐 — 그 주의 근거를 되살릴 수 없었음 | 위 실패를 재현하려다 발견 | logger 연결 (seed는 로그에만 둔다 — 본문 저장은 하지 않기로 함, 하민 11-10) |

## 6. 아직 아닌 것

- 「실패 구간만 다시」 · 「겹친 후보만 다시」는 가짜 LLM으로만 확인했다. 실제 모델 30회에서 실패 · 겹침이 0건이라 그 경로를 탄 적이 없다.
- LLM 재시도(ADR-076)는 실제 모델로 확인했다(11-10, 46원): 503 한 번 → 1.5초 뒤 재시도 → 201, 두 번 연속 → 폴백 없이 500. 시도 수는 `plan_timing llm_calls`로 남는다 — [runs/2026-11-10-retry](../evaluation/runs/2026-11-10-retry/README.md).
- 한글 숫자(「네 개」)는 추출 대조 밖이다.
- 근거에 없는 내용을 덧붙였는지는 검사(`UNSUPPORTED_FACT`)가 일부만 잡는다. 근거 대조 실측에서 ✗ 6개가 저장까지 갔다 — [evaluation.md](evaluation.md) §3
