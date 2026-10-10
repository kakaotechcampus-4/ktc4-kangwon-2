# Frontend 인수인계 — 연간 · 월간 계획안 API 와 화면 연결 현황

> 작성: 2026-10-11 · 작성자: 하민(Claude Code 조사)
> 기준 코드: `feature/p0-integration-contract-handoff` = 2차 통합 `d45c61a`(월간 BE-2 + Frontend FE-Y2 + 연간 BE-Y3)
> \+ FE-Y2 `de69cce`(연간 재생성 목업 정정). **develop 이 아니다.** 줄 번호는 이 기준이다.
>
> **이 문서는 화면을 정하지 않는다.** 무엇이 서버 · Client 에 있고 무엇이 화면에 없는지, 무엇을 PM · 디자인이
> 정해야 하는지만 적는다. 버튼 · 화면 · 문구의 모양은 승인된 디자인이 정한다.

## 0. 한눈에

| 구분 | 기능 |
|---|---|
| 화면까지 연결됨 | 연간 생성 · 조회 · 목록 · 월 수정 · 확정 · hwpx 내려받기 |
| 서버 · Client · 목업은 있고 **화면이 없음** | 연간 선택 월 재생성 · 연간 변경 이력 · 월간 전부(양식 설정 · 생성 · 조회 · 칸 수정 · 칸 재생성 · 확정 · 변경 이력) |
| **화면이 다른 길로 감** | 월간 · 주간 · 일간 생성 → `/api/assistant`(Next 서버가 OpenAI 를 직접 부름) 또는 로컬 기본 양식. 서버 월간 API 를 쓰지 않는다 |
| 계약이 어긋남 | 연간 「AI 초안」 배지가 서버에 없는 `source_type` 을 읽는다 |

## 1. 상태 표기

| 상태 | 뜻 |
|---|---|
| `IMPLEMENTED` | 서버 API 가 있다 |
| `VERIFIED` | 실제 서버에 Frontend Client 코드로 요청해 확인했다(격리 DB · mock LLM, 2차 통합 PASS 42) |
| `NOT_CONNECTED` | Client 는 있는데 화면이 부르지 않는다 |
| `UI_MISSING` | 그 기능을 실행할 화면 · 진입점이 없다 |
| `CONTRACT_MISMATCH` | 화면 · Client 가 서버와 다른 것을 기대한다 |
| `POLICY_PENDING` | PM 결정 전이라 화면 동작을 정할 수 없다 |
| `UNKNOWN` | 이번 조사에서 확인하지 못했다(「없음」이 아니다) |

**Client 가 있다는 것은 화면 기능이 끝났다는 뜻이 아니다.** 「Client 존재」와 「UI 존재」를 따로 본다.

## 2. 연간 계획안

경로 앞부분: 서버 `backend/app/features/plans/router.py`, Client `frontend/lib/api/plans.ts`.

| ID | 기능 | 서버 | Client | MSW | 화면 · 호출 위치 | 상태 |
|---|---|---|---|---|---|---|
| Y-01 | 생성 `POST /api/plans/annual` | `router.py:244` | `createAnnualPlan` `plans.ts:12` | 있음 | `PlanGeneratorPage.tsx:218` | IMPLEMENTED · VERIFIED |
| Y-02 | 단건 `GET /api/plans/annual/{id}` · 목록 `GET /api/plans/annual` | `router.py:348` · `:321` | `getAnnualPlan` `plans.ts:25` · `listAnnualPlans` `:20` | 있음 | `AnnualResult.tsx:31` · `DocumentEditor.tsx:63` · `PlanNotebookPage.tsx:40` | IMPLEMENTED · VERIFIED |
| Y-03 | 월 수정 `PUT …/months/{month}` | `router.py:354` | `putAnnualMonth` `plans.ts:28` | 있음 | `GenerationFlow.tsx:106` · `DocumentEditor.tsx:187` | IMPLEMENTED · VERIFIED |
| Y-04 | 확정 `POST …/confirm` (재호출 200 · 같은 값) | `router.py:392` | `confirmAnnualPlan` `plans.ts:48` | 있음 | `GenerationFlow.tsx:139` · `DocumentEditor.tsx:194` | IMPLEMENTED · VERIFIED · POLICY_PENDING(§2-1) |
| Y-05 | 선택 월 재생성 `POST …/months/{month}/regenerate` | `router.py:492` (잠정 계약) | `regenerateAnnualMonth` `plans.ts:40` | 있음 | **없음** | IMPLEMENTED · VERIFIED · NOT_CONNECTED · UI_MISSING · POLICY_PENDING |
| Y-06 | 변경 이력 `GET …/audit` (7키) | `router.py:573` | `getAnnualPlanAudit` `plans.ts:46` | 있음 | **없음** | IMPLEMENTED · VERIFIED · NOT_CONNECTED · UI_MISSING |
| Y-07 | 생성 방식 배지(「AI 초안」 · 「기본 양식 초안」) | `source_type` **없음** | `source_type?` 는 `@deprecated` | — | `AnnualResult.tsx:87` · `PlanGeneratorPage.tsx:224` → 표시 `GenerationFlow.tsx:413` | CONTRACT_MISMATCH · POLICY_PENDING |

### 2-1. 확인된 동작 · 남은 결정

- **Y-03 · Y-04 오류 표시는 서버 문구를 그대로 쓴다.** 월 저장 실패는 그 행 아래(`GenerationFlow.tsx:117-122`),
  확정 실패는 알림(`GenerationFlow.tsx:144`), 문서 편집기는 메시지(`DocumentEditor.tsx:195-197`). 실패한 입력은
  남는다. 오류 코드별로 다른 안내는 없다.
- **Y-01 같은 반 두 번째 생성은 409 `ALREADY_EXISTS` `["class_id"]` 다.** 화면이 이 코드를 따로 다루는지 —
  기존 계획안으로 안내할지 — `UNKNOWN`(코드별 처리 없음까지만 확인).
- **Y-04 빈 달 확정:** `docs/api-spec.md` §7(`api-spec.md:708`)은 「빈 칸이 남으면 422 `months.N`」이라 적지만
  서버는 이 검사를 하지 않는다. 소주제가 비어도 확정된다. **PM 결정 전**이다 — 화면이 어느 쪽에도 기대지 않는다.
- **Y-05 재생성은 잠정 계약이다**(`docs/provisional-policy-decisions.md` PROV-Y-A · B · C · E, PM 확인 전).
  - 교사가 고친 주제도 바뀐다(PROV-Y-B). 이전 값은 Y-06 `value_change.before` 에 남지만 **되돌리는 API 는 없다.**
  - 그 달에 공백 아닌 소주제가 있으면 422 `["sub_themes"]`(PROV-Y-E) — 소주제를 비워야 다시 만들 수 있다.
  - 확정 뒤 409 `ALREADY_CONFIRMED`, 그 사이 다른 저장이 있었으면 409 `STALE_WRITE`(다시 불러온 뒤 재시도),
    503 `DEPENDENCY_UNAVAILABLE` · `LLM_BUDGET_EXCEEDED`(운영 문의), 500 `GENERATION_FAILED`(재시도 가능).
    없는 달 404 `["month"]` · 없는 계획안 404 `["id"]`.
  - 횟수 제한 없음(PROV-Y-C, 출시 정책 미정).
- **Y-05 같은 주제가 다시 나올 수 있다 — 실패가 아니다.** 서버 Core 는 지금 주제를 빼지 않고 뒤로 미룰
  뿐이다(`p0-planning/src/ssuksak/planning/rules/yearly_theme_selection.py:51-56`). 지금 Theme Reference 로는 만 3~4세
  반의 3 · 4 · 5 · 8월이 후보 하나뿐이고, 9 · 10월은 둘이지만 하나가 이웃 달과 겹친다. 그래도 200 이고 이력에
  `REGENERATED` 가 남는다(값이 같아도). 실제 LLM 은 같은 주제라도 문구를 바꿔 쓸 수 있다. **화면은 「다시 만들면
  다른 주제가 나온다」고 가정하면 안 된다.** 같은 주제가 왔을 때 어떻게 알릴지는 PM · 디자인 결정이다.
  MSW 도 이 동작을 따른다(9월만 후보가 둘, 나머지는 같은 주제) — `frontend/msw/data/annual-plans.ts`.
- **Y-06 이력에 없는 것:** 소주제 변경 전후, 이전 근거(evidence), 사람 이름. 소주제만 고친 PUT 은
  `before` 와 `after` 가 같은 `TEACHER_EDITED` 로 보인다(`api-spec.md` §7-1).
- **Y-07 배지:** 서버는 칸마다 `evidence`(근거) · `generation`(만든 방법)을 주고 단일 `source_type` 을 주지 않는다.
  그래서 서버 계획안은 지금 **항상 「기본 양식 초안」** 으로 보인다 — 실제로는 RULE_LLM 으로 만들었는데도.
  `generation.method` 로 `source_type` 을 지어내지 않는다. 배지가 무엇을 뜻할지(LLM 사용 여부? 근거 종류? 교사
  수정 여부 — 이것은 Y-06 Audit 이 말한다)를 PM · Frontend 가 정해야 한다.

## 3. 월간 계획안 · 양식 설정

경로 앞부분: 서버 `backend/app/features/plans/monthly_router.py` · `backend/app/features/template_profiles/router.py`,
Client `frontend/lib/api/monthly.ts` · `frontend/lib/api/templateProfiles.ts`. **이 Client 들을 부르는 화면은 없다**
(`frontend/app` · `frontend/components` 전체 검색).

| ID | 기능 | 서버 | Client | MSW | 화면 | 상태 |
|---|---|---|---|---|---|---|
| M-01 | 기반 Template 목록 `GET /api/monthly-templates` | `template_profiles/router.py:222` | `listMonthlyTemplates` `templateProfiles.ts:28` | 있음 | 없음 | IMPLEMENTED · VERIFIED · UI_MISSING |
| M-02 | 「Reference 기반 시작」 `POST /api/centers/{id}/template-profiles` | `template_profiles/router.py:274` | `createTemplateProfile` `templateProfiles.ts:34` | 있음 | 없음 | IMPLEMENTED · VERIFIED(409) · UI_MISSING · POLICY_PENDING |
| M-03 | 원 기본 `GET · PUT /api/centers/{id}/template-profile-default` | `:364` · `:373` | `getCenterDefaultProfile` `:43` · `putCenterDefaultProfile` `:46` | 있음 | 없음 | IMPLEMENTED · VERIFIED · UI_MISSING |
| M-04 | 반 override `GET · PUT /api/classes/{id}/template-profile-override` | `:383` · `:391` | `getClassProfileOverride` `:56` · `putClassProfileOverride` `:59` | 있음 | 없음 | IMPLEMENTED · VERIFIED · UI_MISSING |
| M-05 | READY 목록 · 반에 적용될 설정 | `:201` · `:187` | `listReadyTemplateProfiles` `:23` · `getClassTemplateProfile` `:20` | 있음 | 없음 | IMPLEMENTED · VERIFIED · UI_MISSING |
| M-06 | 월간 생성 `POST /api/plans/monthly` | `monthly_router.py:200` | `createMonthlyPlan` `monthly.ts:15` | 있음 | **다른 흐름(§3-1)** | IMPLEMENTED · NOT_CONNECTED · POLICY_PENDING |
| M-07 | 단건 · 목록 | `monthly_router.py:318` · `:290` | `getMonthlyPlan` `monthly.ts:17` · `listMonthlyPlans` `:20` | 있음 | 없음 | IMPLEMENTED · VERIFIED(404 · 빈 목록) · UI_MISSING |
| M-08 | 칸 수정 `PUT …/cells/{item_id}` (`expected_revision`) | `:536` | `editMonthlyCell` `monthly.ts:26` | 있음 | 없음 | IMPLEMENTED · UI_MISSING |
| M-09 | 칸 재생성 `POST …/cells/{item_id}/regenerate` | `:551` | `regenerateMonthlyCell` `monthly.ts:38` | 있음 | 없음 | IMPLEMENTED · UI_MISSING |
| M-10 | 확정 `POST …/confirm` | `:581` | `confirmMonthlyPlan` `monthly.ts:61` | 있음 | 없음 | IMPLEMENTED · UI_MISSING |
| M-11 | 변경 이력 `GET …/audit?item_id=` | `:324` | `getMonthlyPlanAudit` `monthly.ts:52` | 있음 | 없음 | IMPLEMENTED · UI_MISSING |

M-08 ~ M-11 의 성공 경로는 실제 서버에서 **확인하지 못했다(BLOCKED)** — READY 양식 설정이 있어야 만들 수 있는데
실제 Template 이 사람 승인 전이다. 서버 테스트(`backend/tests/test_monthly_plans_api.py` ·
`test_monthly_lifecycle_api.py` · `test_monthly_audit_api.py`)가 **테스트 전용 승인 Fixture** 로만 확인한다. 운영 승인
뒤의 E2E 와 같지 않다.

### 3-1. 최우선 — 월간 생성 화면이 서버 월간 API 를 쓰지 않는다

1. **기존 화면은 있다.** 계획안 만들기 화면에서 월간 · 주간 · 일간을 고를 수 있다
   (`PlanGeneratorPage.tsx:531-535` 월 선택).
2. **지금 부르는 것:** 연간만 서버(`PlanGeneratorPage.tsx:211-218` → Y-01)다. 나머지는 AI 가 켜져 있으면
   `requestAI("plan")`(`PlanGeneratorPage.tsx:235`) → `fetch("/api/assistant")`(`frontend/lib/workspace/ai-client.ts:6`)
   → Next 서버 라우트가 **OpenAI 를 직접** 부른다(`frontend/app/api/assistant/route.ts:117`, 환경변수
   `OPENAI_API_KEY` · `OPENAI_MODEL`). AI 가 꺼져 있으면 로컬 기본 양식(`PlanGeneratorPage.tsx:260` `templatePlan`).
   결과는 브라우저 문서 보관함에 저장된다(`GenerationFlow.tsx:234` `updateWorkspace`) — 서버 `plans` 에 저장되지 않는다.
3. **정식 Client:** `createMonthlyPlan` (`monthly.ts:15`) — 요청 `{ class_id, month, profile_ref }`.
4. **두 흐름이 다른 이유:** 화면은 Planning Core 의 월간 API 가 생기기 전에 만들어졌다. 월간 Client · MSW 는
   M6 에서 만들었지만, 승인된 디자인이 없어 화면 연결(FE-2 ~ FE-5)은 하지 않았다.
5. **지금 흐름에 적용되지 않는 것:** 연간 확정 Gate(서버는 확정된 연간이 없으면 409 `GATE_BLOCKED`
   `["class_id"]`, `monthly_router.py:196` · `:217` · `:223`), Template 사람 승인 Gate, 양식 설정(Profile) 기반 칸 구조,
   근거 · 생성 방식 · 변경 이력, revision 충돌 보호, 서버 저장 · 확정. 그리고 **모델이 다르다** — 서버는 엘리스
   `gpt-6-luna`(ADR-023), `/api/assistant` 는 `OPENAI_MODEL`.
6. **Frontend 팀과 정할 것:** 월간을 서버 API 로 바꿀지 · 언제, 주간 · 일간은 서버 API 가 아직 없다(P0 범위 밖)는
   점을 감안한 분기, 생성 전에 양식 설정(M-01 ~ M-05)을 어디서 고르게 할지, 결과 화면이 서버의 「주 · Section ·
   칸」 구조(칸 수 고정 아님)를 어떻게 그릴지.
7. **재사용 후보(확정 아님):** 기간 선택(`PlanGeneratorPage.tsx:531-535`), 생성 진행 화면 · 결과 편집 틀
   (`GenerationFlow.tsx` — 연간이 서버 계획안을 편집하는 방식), 문서 보관함. 디자인 승인 뒤 정한다.

### 3-2. 월간 오류 안내가 필요한 곳

| 응답 | 언제 | 정할 것 |
|---|---|---|
| 409 `GATE_BLOCKED` `["class_id"]` | 연간이 없거나 확정 전 | 연간 확정으로 안내할지 |
| 404 `NOT_FOUND` `["profile_ref"]` | 고른 양식 설정이 없거나 READY 가 아니거나 남의 원 것 | 다시 고르게 할지 |
| **422 `VALIDATION_FAILED` `["profile_ref"]`** | 그 양식 설정으로 만들 수 없음 — **기반 Template 승인 전 · 없음**(조기 검사와 Core 최종 검사 모두), 생성 정책이 없는 Section 등. 재시도해도 같다 | **사용자 문구 필요** — 원인을 나눠 보여줄지 |
| 409 `ALREADY_EXISTS` `["class_id","month"]` | 그 반 그 달이 이미 있음 | 기존 것으로 이동할지 |
| 409 `STALE_WRITE` | 칸 수정 · 재생성 · 확정 때 `expected_revision` 이 지금과 다름 | 다시 불러오기 안내 |
| 409 `ALREADY_CONFIRMED` | 확정 뒤 수정 · 재생성 | 읽기 전용 표시 |
| 503 `DEPENDENCY_UNAVAILABLE` · `LLM_BUDGET_EXCEEDED` | 서버 설정 · 한도 | 운영 문의(재시도 버튼 아님) |
| 500 `GENERATION_FAILED` | LLM 실패 | 재시도 가능 |

M-02 「Reference 기반 시작」은 **기반 Template 이 사람 승인 전이면 409 `GATE_BLOCKED` `["base_template_ref"]`**
(`template_profiles/router.py:142` · `:306`). 지금 실제 Template v0.1.1 · v0.2.1 은 둘 다 승인 대기라 운영에서는
**항상 409** 다. M-01 목록에는 `approved: false` 로 보인다 — 「보이지만 고를 수 없음」을 어떻게 그릴지 정해야 한다.

## 4. 공통

| ID | 항목 | 현황 | 상태 |
|---|---|---|---|
| C-01 | 연간 CONFIRMED Gate(월간 생성 전) | 서버 409 `GATE_BLOCKED` `["class_id"]`(§3-1 ⑤). 화면 없음 | IMPLEMENTED · UI_MISSING |
| C-02 | Template 승인 Gate | 시작 409 · 생성 422(§3-2). 화면 없음 | IMPLEMENTED · VERIFIED(409) · POLICY_PENDING |
| C-03 | 오류 안내 | 연간은 서버 문구 표시(§2-1). 월간은 화면 없음 | 연간 IMPLEMENTED · 월간 UI_MISSING |
| C-04 | 접근 권한 · 원 격리 | 서버가 막는다 — 남의 원 404, 로그인 안 하면 401(실제 서버 확인) | VERIFIED |
| C-05 | 수정 전후 값 | 서버 이력(Y-06 · M-11)에 있다. 보는 화면 없음 | UI_MISSING |
| C-06 | 로딩 상태 | 연간 저장 · 확정은 진행 상태가 있다(`GenerationFlow.tsx` `savingRows` · `confirming`). 월간은 화면 없음. LLM 대기(월간 생성은 동기, 수십 초 가능)를 어떻게 보일지 | 연간 IMPLEMENTED · 월간 UI_MISSING |
| C-07 | 생성 실패 재시도 안내 | 500 은 재시도 가능, 503 은 운영 문의 — 연간 화면이 이 둘을 나누는지 | UNKNOWN |

## 5. Frontend 팀 요청 사항 (우선순위는 제안)

| 순위 | ID | 요청 | PM 결정 | 디자인 승인 |
|---|---|---|---|---|
| 1 | A · M-06 | 월간 생성을 서버 API(`createMonthlyPlan`)로 연결하는 방식 결정 — §3-1 | 필요(모델 · 주간/일간 분기) | 필요 |
| 1 | J · Y-07 | 배지 의미 결정 전까지 `source_type` 에 기대지 않기. 지금 서버 계획안은 항상 「기본 양식 초안」으로 보임 | 필요 | 필요 |
| 2 | B · M-01/02 | 양식 설정 시작 화면과 승인 대기 Template(409) 표시 | 필요(Template 승인 일정) | 필요 |
| 2 | C · M-06 | 월간 생성 422 `["profile_ref"]` 안내 문구 | 필요 | 문구 |
| 2 | D · Y-05 | 연간 선택 월 재생성 진입점 · 확인 흐름 | 필요(PROV-Y-A · B · C · E) | 필요 |
| 2 | E · Y-05 | 교사가 고친 주제가 바뀐다는 확인 절차(PROV-Y-B) | 필요 | 필요 |
| 2 | F · Y-05 | 같은 주제가 다시 나와도 성공 — 다르다고 가정하지 않기, 알리는 방식 | 필요 | 필요 |
| 3 | G · Y-06 | 연간 변경 이력 진입점 · 전후 값 표시 | 아니오 | 필요 |
| 3 | H · M-11 | 월간 칸 변경 이력 화면 | 아니오 | 필요 |
| 3 | I · M-03/04/05 | 원 기본 · 반 override · READY 목록 관리 화면 | 아니오 | 필요 |
| 3 | M-07 ~ M-10 | 월간 조회 · 칸 수정 · 칸 재생성 · 확정 화면(`expected_revision` · 409 처리 포함) | 아니오 | 필요 |

## 6. 결정 대기 (이 문서는 어느 것도 확정하지 않는다)

- 월간 Template v0.1.1 · v0.2.1 사람 승인 · 승인자 · 시각, 승인 철회 정책 (ADR-027 「아직 정하지 않은 것」)
- PROV-Y-A(재생성 P0 포함) · B(교사 수정값 대체) · C(횟수 제한) · E(소주제 있는 달 거절)
- 연간 빈 달 확정 조건(api-spec §7 과 서버가 다름)
- 생성 방식 배지 기준
- 재생성 뒤 같은 주제 안내
- 월간 LLM 사용량 기록(연간 경로만 `llm_usage` 를 남긴다)
- `/api/assistant`(OpenAI 직접 호출)와 서버 LLM(엘리스 `gpt-6-luna`, ADR-023)의 관계

## 7. 검증 기록

- 줄 번호 · 함수명 · 경로: 이 브랜치의 파일에서 자동 대조했다(문서 커밋 전).
- 실제 서버 대조: 2차 통합 브랜치에서 실제 서버(격리 PostgreSQL · mock LLM)에 이 Client 코드로 요청 —
  PASS 42 · FAIL 0 · BLOCKED 1(월간 성공 경로).
- 조사하지 않은 것: 브라우저 화면 E2E, 배포 환경 인증, 실제 LLM.
