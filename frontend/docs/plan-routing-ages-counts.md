## 현재 계획안 흐름 (단일 화면 복원)

계획안은 `/plans/annual/new`(생성) → `/plans/annual/[id]`(결과·수정·확정) 두 화면입니다. 사이드바 「계획안」과 홈 카드도 바로 `/plans/annual/new`로 들어갑니다. 문서 구성(`/plans/setup`)·시작 방식(`/plans/start`) 단계는 사용자 흐름에서 뺐고, 이 두 주소와 `/plan-generator`, `/plans/create`(및 `?annual=<id>`)는 정식 주소로 redirect만 합니다. (2026-09-16 갱신)

# 계획안 라우팅 · 연령 · 인원 변경

## 변경 파일

- app/(app)/plans/setup/page.tsx (추가)
- app/(app)/plans/start/page.tsx (추가)
- app/(app)/plans/annual/new/page.tsx (추가)
- app/(app)/plans/annual/[id]/page.tsx (추가)
- app/(app)/plans/create/page.tsx
- app/plan-generator/page.tsx
- next.config.ts
- components/plan-generator/PlanSetup.tsx (추가)
- components/plan-generator/PlanStart.tsx (추가)
- components/plan-generator/AnnualResult.tsx (추가)
- components/plan-generator/PlanGeneratorPage.tsx
- components/plan-generator/GenerationFlow.tsx
- components/onboarding/AgeSelection.tsx (추가)
- components/onboarding/OnboardingPage.tsx
- components/app/AppSidebar.tsx
- components/dashboard/HomePage.tsx
- lib/plan-generator/context.ts (추가)
- lib/onboarding/types.ts
- lib/onboarding/settings.ts
- lib/api/age-adapter.ts (추가)
- lib/api/onboarding.ts
- lib/auth/local-account.ts (온보딩 연령 완료 검사만 변경)
- tests/auth-access.test.mjs
- tests/local-account.test.mjs
- tests/regressions.test.mjs
- tests/msw-p0.test.mjs
- tests/api-workspace.test.mjs

## 라우팅

setup(구성) → start(시작 방식) → annual/new(생성) → annual/{id}(조회/편집/확정).
/plans/setup, /plans/start, /plan-generator, /plans/create가 annual/new로 redirect하며 query를 보존한다. /plans/create?annual=<id>는 /plans/annual/<id>로 보낸다. PlanSetup·PlanStart 컴포넌트는 7주차 S6a·S6b용으로 남겨두되 라우팅에서 분리했다.
결과 UI는 GenerationFlow를 재사용하고 URL ID로 GET /api/plans/annual/{id}를 호출한다.
서버 plan 내용/상태와 별개로 표시용 연령·메모·기존 비연간 결과만 계정/환경별 context cache에 보관한다.

## 연령

SelectedAge = 3 | 4 | 5, selectedAges 배열이 FE의 정확한 선택값이다.
신규 복수 선택은 ageGroup=mixed만으로 저장하지 않는다. 과거 mixed는 [3,4,5], 과거 3/4/5는 단일 배열로 읽는다. 명시적 빈 배열은 빈 선택으로 유지한다.
API 요청/응답도 `selected_ages: number[]` 배열이다(2026-09-15 계약 변경). age_min/age_max 변환은 제거했고, [3,5]는 3세·5세만 뜻하는 값으로 전송·저장·복원된다. 예전에 저장된 age_min/age_max mock 레코드만 읽을 때 배열로 보정한다.

## 인원

children.length > 0 이면 실제 명단 수를 사용한다. 빈 명단이면 currentChildCount, 입력도 없으면 0.
아동 화면에서 두 수가 다르면 안내하지만 진행을 차단하지 않는다.

## 검증

테스트 46개 통과, skip 0. TypeScript 포함 build 통과.
기존 로그인/세션 테스트 유지. 새 연령 round-trip, 레거시 migration, API 범위 변환, 인원 11/10/12, 신규 URL 렌더링, 기존 URL 307/query 보존 검사 추가.
브라우저: setup → start → annual/new → annual/9, 만 3·5세반 표시, 확정 및 새로고침 후 동일 연령/확정 상태 확인.
