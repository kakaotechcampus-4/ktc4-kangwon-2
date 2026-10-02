# 금요일 서버 통합 및 개인정보 수정 검증

검증일: 2026-10-02 (Asia/Seoul).

## 통합 범위

- 통합 브랜치: `feature/server-integration-e2e-stabilization`
- base: `feature/documents-page-api`, `3033121572efe0f12336fde94dec0e470801c364`
- frontend 원본: `feature/server-integration-e2e`의 미커밋 변경. 이후 안정화에서 파일이 더 늘었다.
- backend 원본: `fix/child-pseudonym-collision`의 미커밋 변경 6개 파일.
- 기존 브랜치의 커밋을 이동하거나 rewrite하지 않았고, 기존 worktree의 파일을 수정하지 않았다.
- 최신 develop 전체, 개발 환경 파일, DB 데이터, 로그, 의존성, 자동 생성 파일은 제품 변경에 포함하지 않았다.
- 이 문서는 미커밋 통합 결과를 기록한다. `base...HEAD`는 비어 있으며 실제 변경은 working tree와 신규 파일에 있다. 변경은 추적 파일 21개 + 신규 파일 7개다.

## Backend

반 행을 잠근 뒤 반 전체 이름·가명 표를 검사한다. 신규 가명은 기존 및 신규 실명 variants를 피하고, 이미 발급된 가명은 바꾸지 않는다. 기존 가명과 새 실명이 충돌하는 역방향 충돌, 동일 실명, 모호한 이름 variants, 가명 고갈, 유효하지 않은 기존 명단은 저장 없이 422로 거절한다.

원본 테스트 중 최신 develop의 `documents.draft`를 직접 호출하는 테스트는 이 base에 해당 모듈이 없어 그대로 실행할 수 없다. 통합본에서는 실제 `NameTable`과 `mask`로 모든 등록 아동의 치환 안전성을 검증하도록 조정했다. 문서 생성 통합 성공으로 대체 주장하지 않는다.

## Frontend

반 설정 저장 시 children의 name/code 대신 아동 ID를 저장한다. Records/Documents의 명단은 서버에서 hydration하여 메모리에서 사용한다. 로그인 시 현재·다른 계정 및 구형 공통 classSettings의 children을 정리하고, 잘못된 JSON을 제거한다. 정리 실패는 로그인 완료로 취급하지 않는다.

계정 전환 방어는 `lib/api/client.ts`의 `apiRequest` 한 곳에 둔다. `/api/auth/*`를 뺀 모든 요청이 전송 직전 세션(토큰 세대·토큰·계정 이메일·데모 세션)을 기록하고, 응답을 돌려주기 전에 같은 세션인지 확인한다. 다르면 `SessionChangedError`를 던져 호출부의 저장소·state 갱신이 실행되지 않는다. `addServerChild`·`removeServerChild`·`hydrateClassChildren`을 포함한 모든 child mutation 경로가 이 방어를 지난다.

회귀 테스트는 응답을 성공(201·204·200)으로 돌려주되 응답 직전에 계정을 바꾼다. 방어를 제거하면 세 테스트 모두 실패한다 — 저장소가 전환된 계정 키로 바뀌기 때문이다.

### 확인된 범위 제한

- `saessak.workspace.v1`의 `childName` 칸은 읽기·쓰기 양쪽에서 비운다. **본문은 건드리지 않는다** — 교사가 쓴 `fact`·`context`·`sections[].body`·`sources[].text`와 자동 생성된 `title`에 실명이 남을 수 있다. 임의 삭제가 자료 손실이라 이번 범위에서 제외했다(아래 「남은 개인정보 경로」).
- 정리는 다른 계정 키와 구형 공통 키까지 함께 훑는다. 현재 계정만 정리하면 공용 PC에서 앞사람 명단이 남는다. 다른 계정 자료를 로그인·로그아웃이 고치는 것이 팀 정책으로 맞는지는 아직 합의되지 않았다.
- 개발용 MSW mock DB(`saessak.mswSS.v1:*`)는 서버 자료의 복구 원본이 아니라 통째로 지운다. `NEXT_PUBLIC_API_MOCKING=enabled`일 때만 쓰이는 키다.
- 서버 Documents API 경로는 이름/가명을 새로 workspace에 저장하지 않는다.

### 남은 개인정보 경로 (미해결)

| 위치                                                                                           | 내용                                                  | 왜 안 지웠나                                          |
| ---------------------------------------------------------------------------------------------- | ----------------------------------------------------- | ----------------------------------------------------- |
| `workspace.v1` `documents[].title`                                                             | `"박서준 관찰일지 (9월)"` 처럼 제목에 실명이 들어간다 | 제목은 문서 식별에 쓰여 비우면 목록이 구분되지 않는다 |
| `workspace.v1` `observations[].fact`·`context`, `documents[].sections[].body`·`sources[].text` | 교사가 직접 쓴 본문                                   | 교사 자료다. 자동 삭제·치환은 손실이다                |
| `annualContext.v1:*` `request.memo`                                                            | 교사 메모                                             | 같음                                                  |

세 경로 모두 ADR-013과 충돌할 수 있다. 처리 방식(저장 안 함 / 서버로 이전 / 경고 후 교사 선택)은 팀 결정이 필요하다.

## 검증 결과

| 검사                 | 결과                                                                                                                      |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Backend 전체 테스트  | base(`3033121`) 환경 244 passed. 검증용 혼합 환경(최신 develop + 이번 가명 수정) 319 passed. 반별 동시 등록 시나리오 포함 |
| Frontend 전체 테스트 | 192개 중 188 passed, 4 skipped(실제 Next 서버 URL 미설정), 실패 0                                                         |
| TypeScript           | `tsc --noEmit` 통과                                                                                                       |
| ESLint               | 오류 0, 기존 `public/mockServiceWorker.js`의 unused eslint-disable 경고 1 (이 PR이 건드리지 않은 생성 파일)               |
| Ruff                 | `ruff check` 통과, `ruff format --check` 72개 파일 통과                                                                   |
| Prettier             | 변경 파일 전부 기본 설정 통과. 남은 경고는 Windows checkout(CRLF)뿐이고 LF로 정규화하면 사라진다                          |
| Production build     | Turbopack `next build` 성공                                                                                               |

Prettier의 CRLF 경고는 Windows의 `core.autocrlf=true` checkout 때문이고 커밋되는 내용과 무관하다. `.gitattributes`로 저장소 전체 줄바꿈을 고정하는 일은 이 PR 범위가 아니다.

## 실제 서버 흐름

### 1차: base 단독 환경

기존 DB는 건드리지 않고 새 임시 PostgreSQL 클러스터를 만들어, 이 브랜치의 FastAPI와 MSW를 끈 Next.js로 HTTP 검증을 했다. 프런트 API 모듈이 Next rewrite를 거쳐 실제 FastAPI/PostgreSQL을 쓴다.

- 가입·로그인 성공.
- 박서준·김하윤·이태겸 등록 성공, 가명 충돌 회피 확인.
- 새 명단 저장 시 실명·가명 미저장, 서버 hydration 후 ID 연결 유지 확인.
- 관찰 기록 생성·목록 조회 성공.
- 문서 목록 조회 성공.
- **문서 생성 `POST /api/documents`는 405 Method Not Allowed.** 이 base의 documents backend에는 목록 GET과 수정 PUT만 있다. 이 base만으로는 Documents 생성·확정·삭제를 검증할 수 없다.

### 검증 전용 혼합 환경

base의 405 때문에, 제품 브랜치는 그대로 두고 **검증 전용 worktree**를 따로 만들어 전체 흐름을 다시 돌렸다. 구성은 최신 `origin/develop`(`6d87b7a`)의 documents backend + 이번 가명 수정 3개 파일이고, frontend는 이 브랜치 코드 그대로다. 제품 브랜치에는 develop을 merge·rebase·cherry-pick하지 않았다.

```text
이 브랜치 frontend → Next.js(rewrite) → FastAPI(develop + 가명 수정) → PostgreSQL 16
```

HTTP 40개 시나리오 전부 통과: 가입·로그인·오답 401·토큰 없음 401·중복 409, 원/반/아동 생성, 가명 정방향·역방향 충돌 422, 반 전체 양방향 비충돌, 명단 hydration, 관찰 생성·목록·수정·삭제·대상변경 422, 문서 생성·목록·상세·수정·확정·삭제, `STALE_WRITE` 409, 해석·지원 20자 게이트 422, 교사 확인 미체크 422, 확정 문서 PUT `ALREADY_CONFIRMED` 409, 근거 수정 시 stale 전파, 없는 문서 404, 다른 계정 404.

프런트 모듈을 실제 서버에 대고 돌린 계정 전환 race 7개도 통과했다. backend를 재시작한 뒤 아동·가명·문서 상태·stale·관찰이 모두 그대로였다.

최신 develop backend와 맞춰 본 계약 차이 2가지를 확인했다. 둘 다 이 브랜치 frontend가 이미 맞게 다루고 있다.

- 상태 문자열은 `DRAFT`/`CONFIRMED`(대문자)다. `lib/api/documents.ts`의 `STATUS` 표가 소문자로 바꾼다.
- `POST /{id}/confirm`은 멱등이다 — 이미 확정된 문서에도 200이다. `ALREADY_CONFIRMED` 409는 확정 문서 PUT에서 나온다. `isAlreadyConfirmed`를 쓰는 자리가 PUT 경로라 맞는다.

이 검증은 프런트 API 모듈을 Node에서 실행한 HTTP 검증이다. 브라우저 저장소는 메모리 테스트 객체이고 **브라우저 UI 클릭 E2E는 수행하지 않았다.**

## PR 판단

금요일의 backend 가명 수정과 frontend 명단 개인정보 수정을 하나의 PR로 올릴 수 있다. 전제 두 가지를 PR 본문에 적는다.

1. Documents 생성·확정·삭제는 최신 develop의 documents backend가 있어야 동작한다. 이 base에서는 405다. develop에 merge되면 해결된다.
2. workspace 본문·제목·메모의 실명은 이번 범위가 아니다. 위 「남은 개인정보 경로」가 그대로 남는다.
