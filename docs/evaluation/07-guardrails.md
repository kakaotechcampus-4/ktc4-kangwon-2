# 07 · 가드레일

**멘토 심사 기준(기술·개발 중심) ⑦ AI 안전성·예외 대응(가드레일) — 10점**

> 출력 가드레일·예외 처리·장애 대응·실패 시 사용자 안내를 갖춰 잘못된 출력·장애에 일관되게 대응하는가

---

**말로 적은 금지가 아니라 코드가 막는 것만 여기 적는다.**

## 아동 개인정보

| 막는 것 | 어떻게 | 근거 |
|---|---|---|
| 실명이 LLM 프롬프트·응답·로그에 남는 것 | 호출 직전 아동 코드로 치환. `backend/app/shared/childCode/` 한 곳에서만 | ADR-004 · `test_child_code.py` |
| 치환 실패한 채 호출 | **호출하지 않고 에러를 낸다** | [CLAUDE.md](../../CLAUDE.md) §개인정보 |
| 복원 후 조사가 틀어지는 것 | 치환 토큰을 **받침 있는 더미 한글 이름**으로 | 같은 곳 |
| 브라우저에 실명이 쌓이는 것 | `localStorage` · `sessionStorage` · IndexedDB 금지 — 거기 쌓이면 삭제 요청이 와도 못 지운다 | ADR-013 |
| 필요 없는 정보 수집 | **아동에게서 이름만 받는다.** 생년월일·성별·건강정보 안 받음 | [CLAUDE.md](../../CLAUDE.md) |
| 동의 없는 입력 | 아동 명단 입력칸은 확인 문구 체크박스 뒤에서만 열린다 | 같은 곳 |
| 개발 DB 에 실제 실명 | 테스트는 가명으로 | 같은 곳 |

- 이용약관 · 개인정보처리방침 화면 — 커밋 `2b77b4f` · `frontend/app/privacy/` · `frontend/app/terms/`

## AI 가 넘으면 안 되는 선

- **사실기록형(알림장 · 사고보고서 · 투약의뢰서)에 생성 기능을 안 붙였다.** 없는 사실을 쓰면 문서 조작이다 — [CLAUDE.md](../../CLAUDE.md) §문서 5분류
- 해석형은 3층 규격을 못 넘으면 반려 → [06](06-ai-quality.md)
- 자동 제출·자동 발송 없음 — §생성
- v1 월간은 안전 품질표의 자료 SHA·안전 분류 판이 맞지 않거나 분류가 없으면 LLM 호출·저장 전에 중단한다 — `p0-planning/src/ssuksak/planning/retrieval/retriever.py` · `p0-planning/tests/finalization/test_safety_placement_e2e.py`
- v1 월간 실내 대체활동은 주간 분류가 실내대체로 정한 기관 기록만 근거로 쓰고, 근거가 없으면 생성하지 않고 빈칸을 남긴다. 주간 분류가 자료 묶음과 맞지 않으면 LLM 호출 · 저장 전에 중단한다 — `p0-planning/src/ssuksak/planning/retrieval/retriever.py` · `p0-planning/tests/application/test_monthly_application.py` · `backend/tests/test_monthly_lifecycle_api.py`
- 월간 v1 실내대체는 LLM이 빈칸으로 응답한 경우 빈 값·unresolved=true·근거 없음 조합을 검사하며, 채워진 문장에 근거가 없으면 거절한다 — `p0-planning/src/ssuksak/planning/planner/parser.py` · `p0-planning/src/ssuksak/planning/planner/validation.py` · `p0-planning/tests/application/test_monthly_application.py`
- 교사 「요청 사항」이 안전교육 횟수 · 주차를 말해도 LLM 은 정해진 모양으로 뽑기만 하고 배치는 Rule 이 한다. 반영 못한 요청은 `memo_notices` 로 보인다 — PR #378 · ADR-060 · `p0-planning/src/ssuksak/planning/rules/safety_requests.py`
- 요청 사항에 반 아이 이름이 있으면 메모 글만 가명으로 바꿔 보내고, 못 바꾸면 LLM 을 부르지 않고 422 — PR #378 · `backend/app/features/plans/memo_privacy.py`

## 소방대피 · 재난대비 훈련 칸

놀이 중심 월간(`fire_disaster_drill`) · 주제형 월간 v1(`drill` Section)의 「소방대피/재난대비」 칸. 문서 칸은 빈칸으로 시작하고, 교사가 후보 하나를 골라 복사할 때만 채워진다(자동 배치 없음).

| 누가 정하나 | 무엇 | 코드 |
|---|---|---|
| Rule | 그 달 후보 주제 5개 — 승인된 훈련 주제 Reference(`emergency-drill-topics-v0.1.0`, 2026-10-29 `HUMAN_APPROVED` · `runtime_active: true`)에서만, 월 한정 주제 먼저 · 나머지는 목록 순서. Reference 가 없거나 승인 전 · 누리과정 판이 다르거나 · 내용 ID 가 없으면 LLM 호출 전에 중단 | `p0-planning/src/ssuksak/planning/application/drill_topics.py` |
| Rule | 후보의 누리과정 근거(`CURRICULUM` 하나, `nuri2019.1.3.4`) — LLM 이 근거를 달면 거절 | `planner/validation.py` `_drill_candidate_issues` · `domain/monthly_plan.py` `MonthlyDrillCandidate` · `domain/play_monthly_plan.py` `DrillCandidate` |
| LLM | 주제마다 유아가 알아듣는 말로 한 문장(문장화만). 응답의 `topic_id` 가 Rule 이 준 목록과 다르거나 · 겹치거나 · 빠지면 거절 | `planner/play_monthly.py` `UNKNOWN_DRILL_TOPIC` · `DUPLICATE_DRILL_TOPIC` · `MISSING_DRILL_TOPIC` |
| 검사 | 입력에 없는 날짜 · 시각 · 사람 이름(`UNSUPPORTED_FACT`), 내부 ID 노출, 두 문장 이상 · 주제끼리 같은 문장(v1) — 거절 | 같은 곳 · `planner/weekly.py` `unsupported_facts` |
| Rule | 복사: 칸 값은 「[주제]」 다음 줄에 그 후보 문장(안전교육 칸과 같은 모양), 근거는 후보 것 그대로, 생성 방식 `RULE_ONLY`(`play_monthly.drill_copy` · `monthly.drill_copy`), `CANDIDATE_COPIED` 이벤트에 원본 후보 | `application/play_monthly_lifecycle.py` · `application/copy_monthly_drill_candidate.py` · `domain/drill_topic_reference.py` `drill_cell_value` |

- 공식 근거: 주제 · 상황은 2026 보육사업안내 부록 8 「어린이집 비상대피훈련 표준 안내」(PDF 241-244)와 본문 Ⅱ 라. 안전교육(PDF 125-126) — Reference 의 `origins[]` 에 원본 SHA 와 함께 있다. `applicable_months` 는 제품 후보 조건이지 공식 월 배치가 아니고, 이 목록은 훈련 횟수 · 법정 충족을 정하지 않는다.
- 파일 이름의 `_draft` 와 `$schema_note` 의 「Draft · runtime 에 연결하지 않는다」는 승인 전 문구다. 실제 상태는 `review.domain_owner_approval` · `runtime_active` 가 정한다(ADR-027 §5 — 승인 뒤 파일을 고치지 않는다).
- **코드가 막지 않는 것(프롬프트에만 있다):** 대피 경로 · 집결 장소 · 담당자 · 절차 · 실시 결과를 쓰지 않는 것, 문장이 그 주제 상황에 맞는 것. 화면이 문장 옆에 주제 이름을 보이고 교사가 검토한다. 장소 · 절차 결정적 검사기는 「아직 아닌 것」.

## 키와 비용

- **로컬에서 `real` 모드를 코드가 막는다** — 키가 팀 공유라 6명이 각자 부르면 어디로 새는지 모른다.
  `backend/app/shared/llm/client.py` 의 `post_json`:
  ```python
  if not settings.is_server:
      raise LlmUnavailable("로컬에서 real 모드 금지. 배포된 서버 엔드포인트를 호출한다")
  ```
  **설정을 읽는 자리가 아니라 망을 타는 자리에 걸었다.** `require_config` 에 걸었더니 가짜 transport 를
  쓰는 테스트 47개가 같이 막혔다 — 그쪽은 망을 타지 않는다. 월간 어댑터도 이 함수를 쓰므로 같은 가드에 걸린다
- `LLM_MODE=mock` 이 기본값
- 예산 ₩120,000/월, **초과 시 키 자동 삭제.** 자동 차단은 일부러 안 만들었다 —
  90%에서 끊으면 파일럿 중 교사 앞에서 서비스가 멈춘다. 사람이 판단할 기회를 남겼다 (2026-09-21 결정)
- `.env` 는 커밋 안 함. `NEXT_PUBLIC_` 접두사를 키에 안 씀(번들에 박힌다)

## 입력과 권한

- **라우터에 `if` 를 안 쓴다.** 타입에 적어 라우터 들어오기 전에 걸린다 — [CLAUDE.md](../../CLAUDE.md) §입력 검사
  ```python
  # ✗  text: str     빈 값 · 공백만 · 10만 자가 다 들어온다
  # ✓  text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
  ```
- 서버 인증과 센터 범위 — ADR-017 · `test_auth.py` · `features/auth/`
- 비밀번호 scrypt · 원 초대 코드 — ADR-029

- 생성에 쓰는 기관 근거 자료에서 사람이 개인정보로 판정한 기록 42개를 통째 제외하고 분류 4종을 같은 SHA에 연결했다 — [검토·승인 기록](../evidence-store-v0-2-human-review.md) · `p0-planning/tests/evidence/test_evidence_store.py` · `p0-planning/tests/finalization/test_freeze.py`
- 그 42개가 남아 있던 옛 근거 본체 v0.1.0 을 저장소에서 지웠다(git 이력에는 남는다) — `p0-planning/data/evidence/` · `p0-planning/tests/unit/test_safety_evidence_classification.py`

- 계획안의 장소 경계: 검토된 특정 장소명·명시적 현장학습 근거를 맥락형 월간/주간 후보에서 제외한다. 생성의 장소 허용은 긍정 요청·교사가 입력/수정한 확정 부모 값에 한하며, 단순 확정·무변경 저장·거절 요청은 허용하지 않는다. 출처 전달·수리 거절은 `p0-planning/tests/planner/test_venue_policy.py`, 소주제 저장·재조회는 `backend/tests/test_plans_api.py`로 확인한다. 목록에 없는 새 장소명과 일반 외부 방문을 전부 감지하지는 않는다 — `p0-planning/CLAUDE.md`의 Named venue boundary.

## 아직 아닌 것

- 속도 제한(rate limit)이 없다
- 로그에서 개인정보를 거르는 검사가 자동이 아니다 — `test_error_logging.py` · `test_llm_logging.py` 가 일부만 본다
- 소방대피 · 재난대비 후보 문장의 대피 장소 · 절차 · 주제 적합성을 결정적으로 거르는 검사기가 없다 — 지금은 프롬프트와 교사 검토뿐(§소방대피 · 재난대비 훈련 칸)

## 더 모을 근거

- [ ] 치환 실패를 일부러 내서 호출이 안 나가는지 1회 시연
