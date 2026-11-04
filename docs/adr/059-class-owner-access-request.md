# ADR-059: 반마다 주인을 두고, 같은 원 다른 반은 주인 승인 뒤에 본다

- 2026-11-04
- 상태 — 채택
- 관련 — ADR-017(§5 대체 · §6 좁힘) · ADR-034(§4 반 override 권한 좁힘) · ADR-004 · ADR-013 · ADR-029 · `docs/api-spec.md` §2-2

## 맥락

ADR-017 §5 는 같은 원 교사가 모든 반 자료를 읽고 쓰게 했다. 「자기 반만」은 원장 · 담임 교체
규칙을 먼저 정해야 해서 미뤘다. 지금 화면의 「우리 반」에는 같은 원 다른 교사의 반까지 들어온다.
서버 반 응답에 누가 주인인지 · 내가 읽을 수 있는지를 가를 정보가 없다.

## 결정

2026-11-04 성진 결정이다.

1. **같은 원 안에서만 요청한다.** 다른 원 · 없는 반은 지금처럼 404 다(ADR-017 §6).
2. **반을 만든 계정이 주인이다.** `POST /api/centers/{center_id}/classes` 를 부른 계정의 id 를
   기존 `classes.teacher_id` 에 넣고 `users.id` FK · 인덱스를 건다. request 로 받지 않는다.
3. **옛 반은 채우지 않는다.** `teacher_id` 가 NULL 이면 「주인 없는 반」이다. 같은 원 교사 모두
   지금처럼 읽고 쓴다. 새 계정만 쓸 예정이고, 누가 만들었는지 채울 기록이 없다.
4. **승인 단위는 반이다.** 다른 반 교사가 요청하고 그 반 주인이 승인한다. 그 반 자료 전부와
   앞으로 생길 자료를 본다. 주인이 승인을 취소할 수 있다.
5. **보관함 다섯 종류와 원재료를 함께 막는다.** 연간 · 월간(놀이 중심 월간 포함) · 주간 계획안,
   보육일지 · 관찰일지(`/api/documents`), 아이 명단(`/api/classes/{id}/children*`) ·
   관찰 기록(`/api/observations`) · 일과 기록(`/api/routines`)이 대상이다.
6. **승인 뒤에는 보기 · hwp/hwpx 내려받기만 된다.** 만들기 · 고치기 · 확정 · 확정 취소 ·
   재생성 · 재확정 · 삭제 · 가져오기 · 양식 override 변경은 주인만 한다.
7. **같은 원의 권한 없음은 403 이다.** 승인 필요는 `CLASS_ACCESS_REQUIRED`, 승인된 교사의
   쓰기는 `CLASS_READ_ONLY` 다. 둘 다 `fields: ["class_id"]`. 다른 원 · 없는 반의 404 는 유지한다.
8. **반 목록에 `my_access` 하나를 더한다.** `OWNER` · `OPEN` · `APPROVED` · `PENDING` ·
   `REJECTED` · `REVOKED` · `NONE` 이다. 읽기는 OWNER · OPEN · APPROVED, 쓰기는 OWNER · OPEN 이다.
   「내 요청 목록」 API 는 따로 두지 않는다.
9. **요약은 같은 원 모두 본다.** `archive-summary` 는 `kind` · `start` · `end` · `status` 만 준다.
   제목 · 아이 이름 · 문서 id 는 주지 않는다. 날짜 범위 · 정렬 · 실제 `kind` 값은 api-spec §2-2 에 둔다.
10. **다시 요청해도 같은 줄이다.** `class_access_requests` 는 `UNIQUE(class_id, requester_id)` 로
    한 줄만 둔다. REJECTED · REVOKED 뒤 요청은 PENDING 으로 되돌리고 같은 201 을 준다.
    마지막 상태 · 시각만 남는다. 거절 · 취소 이력이 필요해지면 이벤트 표를 따로 둔다.
11. **`class_id` 없는 자료 목록은 OWNER · OPEN 반 것만 준다.** 지정하면 그 반의 읽기 권한을
    본다. 승인된 남의 반을 내 보관함 · 홈에 섞지 않는다.
12. **받은 요청은 화면 안 목록으로만 알린다.** 메일 의존을 붙이지 않는다(ADR-029).
    문서는 지금처럼 DB 에 두고 내려받을 때 파일을 만든다. S3 파일 저장소를 두지 않는다(ADR-021 · ADR-039 · ADR-026).

## 근거

- **[실측]** `backend/app/shared/auth/ownership.py:33-37` 의 `require_own_class` 는 원만 비교한다.
  `backend/app/features/documents/router.py:128-144` 의 `_own_document` 도 반을 원에 조인해 확인한다.
- **[실측]** `backend/app/features/centers/models.py:104-106` 의 `teacher_id` 는 nullable 이고 FK 가 없다.
  `backend/app/features/centers/router.py:209-218` 의 반 생성은 그 값을 채우지 않는다.
- **[실측]** `frontend/lib/api/onboarding.ts:228-230` 은 같은 원 반을 받고, `:260-286` 은
  연결 · 버린 반 · 로컬 id 만 거른다. `backend/app/features/centers/schemas.py:153-171` 의 응답에
  소유 · 접근 정보가 없다. 「우리 반」 원본은 브라우저 저장소다(`onboarding.ts:202-211`).
- **[실측]** `frontend/components/workspace/DocumentsPage.tsx:168` · `:205` 는 반 지정 없이 문서 ·
  연간 목록을 부른다. **[판단]** 승인받은 반까지 섞으면 고치기 버튼이 보였다가 403 이 난다.
- **[실측]** 계획안 `kind` 는 `annual` · `monthly` · `weekly` 다(`backend/app/features/plans/models.py:32`).
  놀이 중심 월간도 `monthly` 다(`backend/app/features/plans/play_monthly_router.py:649-652`).
  문서는 `dailyLog` · `weeklyLog` · `observation` · `assessment` 다(`backend/app/features/documents/schemas.py:172` · `:211`).
- **[판단]** 같은 원 반은 반 목록에 이미 보인다. 404 로 숨길 것이 없고, 화면이 「요청하기」와
  「없는 문서」를 갈라야 한다. 403 은 `TRENDS_DISABLED` 선례가 있다(api-spec 「공통 에러 형식」).
- **[판단]** 문서만 막으면 관찰 화면에서 같은 아이 실명을 본다. 아이 명단 · 관찰 · 일과도 같이 막는다.
  요약 제목도 실명을 담을 수 있어 빼야 한다(api-spec §11 의 「박서준 관찰일지 (9월)」 예시).
- **[판단]** 같은 줄이면 「지금 상태」를 고를 규칙이 필요 없다. 지난 거절 · 취소 이력은 이번에 쓰지 않는다.
- **[판단]** ADR-017 이 걱정한 담임 교체는 `teacher_id` 한 칸을 바꾸는 구조로 남긴다.
  바꾸는 API 와 원장 역할은 이번에 만들지 않는다.

## 대안

- **원 등록 전 드롭다운으로 다른 원 반 열람 요청** — 보류. 승인자가 요청자 신원을 확인할 수 없다.
  ADR-004 는 원을 처리자, 쌤플을 수탁자로 두고 위탁 범위 안에서만 처리하게 한다.
  **[판단]** 원 밖 사람에게 실명을 보이는 것은 그 범위 밖이다. ADR-029 도 「원 이름 검색 후 가입 요청」을
  버렸다. 팀이 따로 정한다.
- **문서 파일을 S3 에 두고 링크** — **[판단]** 수정 · 확정 취소 · 재확정 뒤 사본이 낡고,
  실명 사본 저장소가 하나 더 생긴다. ADR-026 도 DB 와 파일의 백업 · 삭제를 따로 맞추는 길을 버렸다.
- **문서 단위로 만든 사람이 승인** — 작성자 칸이 없고 기존 문서는 작성자를 모른다. 요청도 문서 수만큼 는다.
- **일지만 승인하고 계획안은 같은 원 공개** — 「누가 만들었나」 기준이면 다섯 종류가 같다.
- **옛 반 주인 채우기** — 누가 만들었는지 기록이 없다. 새 계정만 쓸 예정이다.
- **같은 원도 404** — 화면이 「요청하기」와 「없음」을 못 가른다.
- **요청마다 새 줄** — 「지금 상태」 고르는 규칙 · 중복 대기를 막는 제약이 더 필요하다.

## 결과

- 마이그레이션은 `classes.teacher_id` FK · 인덱스와 `class_access_requests` 표다.
  반 단위 API 의 권한 검사가 원 → 반으로 바뀐다. **코드는 다음 PR 이다.**
- 화면 `adoptServerClasses` 는 `my_access` 가 OWNER · OPEN 인 반만 들이고 이미 들어온 남의 반은 뺀다(다음 PR).
- 남의 반을 대신 만들어 준 계정이 주인이 된다. 담임 바꾸기는 없다.
- 옛 반은 보호되지 않는다. 거절 · 취소 이력과 원장 역할도 없다.
- 「우리 반」 원본이 브라우저 저장소인 구조는 그대로다. 이번에 정리하지 않는다.
