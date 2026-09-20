# P0 MSW / FastAPI 전환

현재 원 생성, 반 생성/조회, 아동 생성/조회/삭제, 계획 설정, 연간 생성/조회/월 수정/확정 handler와 lib/api 함수를 제공합니다.
원본 계약: ../docs/api-spec.md. 사용자 보충 계약에 따라 TEACHER와 오류 코드를 구현했습니다.

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
mswTarget: center, class-create, classes, children, child-create, child-delete, plan-config, annual, annual-get, month, confirm
mswDelay=5000: loading. mswEmpty=true: 반/아동 GET만 empty.
mswError: VALIDATION_FAILED, NOT_FOUND, GATE_BLOCKED, NO_ACTIVITIES, GENERATION_FAILED.
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
