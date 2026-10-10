# P0 MSW / FastAPI 전환

현재 원 생성, 반 생성/조회, 아동 생성/조회/삭제, 계획 설정, 연간 생성/조회/월 수정/확정 handler와 lib/api 함수를 제공합니다.
원본 계약: ../docs/api-spec.md.

## ON / OFF

.env.local:
NEXT_PUBLIC_API_MOCKING=enabled
enabled이면 NODE_ENV와 관계없이 MSW가 켜집니다. Vercel Production/Preview에서도 사용할 수 있습니다. disabled 또는 미설정이면 시작하지 않습니다. 로컬은 다시 시작하고 배포 환경은 환경변수 변경 후 재빌드/재배포해야 합니다.
FastAPI 연결 시:
NEXT_PUBLIC_API_MOCKING=disabled
FASTAPI_BASE_URL=http://localhost:8000
Next 서버 재시작/재빌드가 필요합니다. /api/... 상대 경로는 그대로이며 Next rewrite가 프록시합니다. 기존 assistant/templates/extract Route Handler는 유지합니다.
공식 worker 재생성: npx msw init public --save
참고: https://mswjs.io/docs/integrations/browser/

## 재현

API 직접 요청: ?mockError=GENERATION_FAILED&mockDelay=2000
기존 화면 URL: ?mswTarget=annual&mswError=NO_ACTIVITIES
mswTarget: center, class-create, classes, children, child-create, child-delete, plan-config, annual, annual-get, month, confirm, annual-regenerate, annual-audit, monthly, monthly-list, monthly-get, monthly-cell, monthly-regenerate, monthly-confirm, template-profile, template-profiles
mswDelay=5000: loading. mswEmpty=true: 반/아동 GET만 empty.
mswError: VALIDATION_FAILED, NOT_FOUND, GATE_BLOCKED, NO_ACTIVITIES, GENERATION_FAILED. 월간은 LLM_BUDGET_EXCEEDED, DEPENDENCY_UNAVAILABLE, STALE_WRITE, ALREADY_CONFIRMED 도 쓴다.
mswField=selected_ages: 오류 field 지정.
기본 연간 지연 1200ms. 0~10000ms로 제한합니다. 실패는 mutation 전에 반환하여 부분 생성 결과를 남기지 않습니다.
월 PATCH 특정 월 오류: API URL에 mockError를 직접 붙이거나 mswMonth=3 사용.
시나리오는 MSW가 enabled인 환경에서만 읽습니다. Production/Preview 데모에서도 동일하게 사용할 수 있습니다.

## 기존 UI 연결

- 온보딩 다음: 원/반 POST 성공 후 기존 설정 cache 저장/페이지 이동.
- 아동 GET/POST/DELETE, 입력 실패 시 이름 유지, 성공한 서버 코드 표시. 동의는 서버 payload에 없음.
- 기존 연간 생성 UI에서 POST /plans/annual. 수정 완료에서 월 PATCH. 연간 확정에서 confirm.
- 보관함 문서는 서버 annual ID를 참조하는 기존 로컬 목록/cache. 문서 편집 시 GET/PATCH/confirm.
- 월간/주간/일간, 로그인/세션/성품/관찰/양식은 기존 방식 유지.
- plan-config는 기존 입력 화면이 없어 함수/handler만 제공. 임의로 44시간 설정을 저장하지 않음.
- FROM_UPLOAD는 업로드 ID 발급 API 연결이 아직 없어 UI에서는 FROM_SCRATCH만 호출. 기관 양식의 서버 전달과 생성 메모는 P0 계약에 없음.

## 데이터 / 호환 한계

기존 계정과 설정은 삭제하지 않습니다. 계정별 apiLinks는 로컬 ID와 서버 ID 대응 및 전송된 snapshot 서명만 저장합니다. MSW mock DB도 별도 계정별 키입니다. mock/backend ID namespace를 분리하여 mock ID를 실서버에 보내지 않습니다.
원/반 수정·삭제 API가 없는 P0에서는 수정한 설정을 새 서버 snapshot으로 생성하고 현재 연결만 바꿉니다. 삭제된 반의 과거 서버 snapshot은 유지합니다. 이를 실서비스 수정/삭제로 확장하려면 BE 계약이 필요합니다.
기존 캐시는 홈/접근 guard 및 아직 계약 없는 기록 기능과 호환되도록 유지합니다. center GET, 계획안 목록 GET이 없어 기관/문서 목록은 캐시를 사용합니다. 여러 기기 동기화나 서버 인증을 제공하지 않습니다.
반 연령은 selected_ages 배열로 전송합니다(예: [3,5] = 만 3세·만 5세). 범위 변환은 하지 않습니다.
mock/backend를 전환하면 기존 mock 연간 문서는 로컬 보관본으로 유지하고 실제 서버 ID로 간주하지 않습니다.
mock 생성 데이터는 localStorage의 saessak.mswSS.v1:<계정>에서 새로고침 후 복원됩니다.

## BE TODO

- 반 response: mock 임시 id, center_id와 요청 필드. 실제 response 확정 필요.
- plan-config response: mock 임시 204. FE는 response body에 의존하지 않음.
- citation nullable와 상세 schema, 실제 더미 code 풀/중복 방지 정책.
- 확정 후 409의 상세 code: mock GATE_BLOCKED. 실제 계약 확정 필요.
- FROM_UPLOAD 검증/업로드 ID 조회 및 실제 활동 풀.
- 원/반 수정/삭제, 계정 인증 및 서버 권한(P1), API pagination/list 복원.

## 계획안 페이지 주소 (2026-09-15 갱신)

- 정식 주소: /plans/setup → /plans/start → /plans/annual/new(생성) → /plans/annual/{id}(결과·수정·확정). 새로고침은 GET /api/plans/annual/{id}로 복원합니다.
- 레거시 /plans/create, /plans/create?annual=<ID>, /plan-generator는 위 주소로 redirect만 합니다.
- 계획안의 대상 연령은 표시 조건이며 저장된 반을 수정하지 않습니다. 생성은 온보딩에 저장된 반 ID를 사용합니다.
- TODO(BE): 대상 연령 override, 기관 양식, 추가 메모를 annual 생성 요청에 전달할 필드가 없습니다. 계약에 없는 필드를 추가하거나 반 정보를 덮어쓰지 않습니다. 표시용 정보는 계정별 annualContext에 보존합니다.
- 월 PATCH 실패 시 편집 중인 입력을 유지합니다. 재시도 성공 후 서버 데이터가 갱신됩니다.
- 재시도 테스트: /plans/annual/new?mswTarget=month&mswMonth=3&mswError=GENERATION_FAILED&mswFailures=1
  생성 후 3월 수정 완료를 누르면 처음에는 실패하고 두 번째에는 성공합니다. API 직접 호출은 mockFailures=1을 사용합니다. 카운터는 요청 URL/메서드와 페이지 쿼리별이며 전체 새로고침 시 초기화됩니다.
- 월간/주간/일간 서버 API는 계약이 없어 기존 생성 방식 유지. 별도 setup/start 페이지를 사용하거나 plan-config 기본값을 자동 저장하지 않습니다.

### 검증 결과

2026-09-15: 기존 포함 47개 테스트 통과, TypeScript 검사 및 production build 성공.
브라우저 QA: /plans/annual/17에서 3월 PATCH 500 후 입력 유지 → 재시도 200 → 새로고침 GET으로 제목 복원 → confirm 200 확인.
저장된 3세 반을 계획안에서 5세로 표시하여 생성한 문서 18: POST annual / GET annual만 발생했고 원·반·아동 POST는 발생하지 않음.

## Vercel 데모 배포 확인

Vercel 프로젝트의 Settings → Environment Variables에서 NEXT_PUBLIC_API_MOCKING=enabled를 Production/Preview에 설정한 뒤 재배포합니다. NEXT_PUBLIC 값은 빌드 시점에 고정됩니다.
실제 FastAPI 사용 시 disabled로 바꾸고 FASTAPI_BASE_URL을 실제 서버 주소로 설정한 뒤 재배포합니다.
검증: 2026-09-15 enabled로 production build 성공, next start에서 브라우저 [MSW] Mocking enabled / worker started 확인. 실제 Vercel 배포 설정은 이 로컬 검증에 포함하지 않음.

## 연간계획안 목업 (docs/api-spec.md §4 ~ §7)

- 응답 모양은 서버와 같다: months[] 에 evidence(THEME_REFERENCE 하나) · generation · safety_education([]) · safety_education_state(SOURCE_REQUIRED), 계획안에 checked_rules · checks. 단일 source_type · citation 은 없다.
- 생성 직후 sub_themes 는 []. 근거 id · rule 은 mock_theme_<달> · mock.yearly.theme 고정값이다 — 실제 Theme Reference 가 아니다. checks 는 법정 6구분 × (주기 · 시수) UNVERIFIED 12건이고 문구는 목업이다(법령 값은 서버 원본만).
- 서버와 같은 규칙: 반 하나에 연간 하나(ALREADY_EXISTS), PUT 은 evidence · generation 을 바꾸지 않음, 확정 뒤 PUT 은 409 ALREADY_CONFIRMED, 확정 재호출은 200 · 같은 confirmed_at · 상태 변화 없음, 빈 소주제로 확정을 막지 않음.
- 서버와 다른 점: 연간 목업은 「지금 원」 소유 검사를 하지 않는다. 이 변경 전에 저장된 연간 목업 데이터(localStorage)는 옛 모양 그대로다 — 새 모양이 필요하면 새 계정 · 새 반으로 만든다.
- 선택 월 재생성(잠정 계약, provisional-policy-decisions 부록): 서버 Core 와 같은 규칙으로 후보를 고른다 — 지금 주제는 뒤로 미룰 뿐 빼지 않으므로 **후보가 하나뿐인 달(목업은 9월 말고 전부)은 같은 주제가 다시 나온다.** 그래도 200 이고 REGENERATED(값이 같아도)를 남긴다. 9월은 후보가 둘이라 번갈아 바뀐다. 그 달 theme · evidence · generation 만 다시 쓴다. 확정 409 ALREADY_CONFIRMED, 공백 아닌 소주제 422 ["sub_themes"]. STALE_WRITE · 503 · 500 은 mockError 로만 재현한다(목업에 LLM 대기 · 동시 저장이 없다). 실패는 저장 전에 돌려준다.
- 변경 이력(§7-1): 생성 CREATED(계획안 + 12개월) · PUT TEACHER_EDITED(주제가 같아도) · 재생성 REGENERATED · 최초 확정 CONFIRMED. 재확정은 이벤트를 더하지 않는다. 소주제 · 이전 근거는 이력에 없다.
- 옛 목업 계획안(FE-Y1 이전 저장본): 이력은 빈 목록, 재생성은 422 ["id"](목업 전용 — 생성 방식이 없어 이력을 만들 수 없다). 데이터는 지우거나 고쳐 쓰지 않는다.

## 월간계획안 목업 (docs/api-spec.md §9-1 ~ §9-3)

- 생성 · 단건 · 목록 · 칸 편집 · 칸 재생성 · 확정, 양식 설정 조회 2개. 데이터는 data/monthly-plans.ts.
- 서버와 같은 규칙: revision 일치 시 +1 · 다르면 STALE_WRITE, 확정 뒤 편집 · 재생성은 ALREADY_CONFIRMED, 확정 재호출은 revision 과 상관없이 200(D-M5-CONFIRM-01), 재생성은 focus · outdoor_play · basic_habit · goals 만.
- LLM 을 부르지 않는다. 칸 값은 개발용 고정 문장이고 안전교육은 「근거 필요」(EMPTY_UNRESOLVED) 칸이다.
- 소유 범위는 첫 원(currentCenterId)이다. 다른 원의 반 · 계획안 · 양식 설정은 404.
- 양식 설정은 data/template-profiles.ts 다(§9-4). 관리 API(기반 Template 목록 · 시작 · 원 기본 · 반 override)와 §9-2 조회, 월간 생성이 **같은 저장소**를 쓴다. 고정 READY 는 없다 — 시작 API 로 만든다.
- 기반 Template v0.1.1 · v0.2.1 은 서버처럼 **승인 대기**(approved: false)라 시작이 409 GATE_BLOCKED 다. 승인된 경로는 테스트 · 개발 전용 Fixture `approveTemplateForTest(template_ref)` 로만 연다(화면 코드는 부르지 않는다).
- 포인터 지정 · 해제는 expected_profile_ref 비교(CAS)를 서버와 같은 순서로 본다. 목업은 한 흐름에서 돌아 DB 수준 동시성은 보여 주지 못한다(BE-1 PostgreSQL 테스트가 본다).
- mswTarget 추가: monthly-templates, template-profile-create, template-profile-default, template-profile-override.
- 변경 이력(§9-5, `GET /api/plans/monthly/:id/audit[?item_id=]`)은 생성 · 칸 편집 · 칸 재생성 · 첫 확정이 **성공할 때 같은 commit 에서** `monthlyAudit[planId]` 에 쌓는다(계획안 단위 / 칸 단위). 거절 · 실패 · 확정 재호출은 쌓지 않고, 조회는 아무것도 바꾸지 않는다. 행위자는 `user_1`(목업 계정), 생성은 `system_actor: monthly_application`. 재생성 전 근거 · 이벤트별 revision 은 서버처럼 없다.
- 목업은 토큰을 검증하지 않는다. 이력 401 은 `?mockError=UNAUTHENTICATED`(mswTarget: monthly-audit)로 재현한다.
