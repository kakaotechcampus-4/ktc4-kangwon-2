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

## 아직 아닌 것

- 속도 제한(rate limit)이 없다
- 로그에서 개인정보를 거르는 검사가 자동이 아니다 — `test_error_logging.py` · `test_llm_logging.py` 가 일부만 본다

## 더 모을 근거

- [ ] 치환 실패를 일부러 내서 호출이 안 나가는지 1회 시연
