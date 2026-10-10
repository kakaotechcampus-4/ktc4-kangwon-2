# 잠정 정책 기록 — PM 확인 전 개발 방향

> **이 문서는 SoT 가 아니다.** 사용자(하민)가 개발을 진행하려고 **잠정**으로 정한 방향과, 그것이 기존
> SoT 와 어디서 부딪히는지를 빠짐없이 적는다. 여기 적힌 것은 AUTHORITATIVE 도 PM_APPROVED 도 아니다.
> **기존 문서의 문구는 바꾸지 않았다** — 고쳐야 할 문구는 각 항목의 「정정안」에만 적고, PM 확인 뒤에
> 원래 문서에서 고친다.
>
> 작성: 2026-10-10 · 연간 BE-Y2(선택 월 재생성) 준비 중 · 기준 코드 develop `5d04a2e` + BE-Y1 `bf8edd1`
> 갱신: 2026-10-10 · BE-Y2b 잠정 구현(`feature/yearly-be-y2b-month-regeneration-api`, Base BE-Y2a) —
> PROV-Y-E · F 와 부록(잠정 API 계약)을 더했다. **병합 · 배포 가능 상태가 아니다** — 아래 PM · 담당자
> 확인이 남아 있다.

## 상태 값

| 값 | 뜻 |
|---|---|
| `USER_PROVISIONAL` | 사용자가 개발용으로 잠정 결정했다. 병합 · 배포 전에 PM 확인이 필요하다 |
| `USER_CONFIRMED_FOR_DEVELOPMENT` | 사용자가 개발 · 테스트 단계에 한해 확정했다. 배포 정책은 따로 정한다 |
| `PM_CONFIRMATION_PENDING` | PM 확인을 기다린다 |
| `OWNER_COORDINATION_PENDING` | 그 코드의 기존 담당자와 조율을 기다린다 |
| `RELEASE_POLICY_PENDING` | 배포 전에 정해야 한다 |

SoT 위치 표기: `CLAUDE.md` · `demo-source-of-truth.md` · `screen-spec.md` 는 Planning 워크스페이스
(`C:\MAIN\P0\`)의 문서이고, `docs/api-spec.md` · 저장소 `CLAUDE.md` 는 이 저장소의 문서다. 줄 번호는 위
기준 코드 시점이다.

---

## A — 연간 P0 재생성 범위

| 필드 | 내용 |
|---|---|
| 결정 ID | PROV-Y-A |
| 관련 기능 | 연간계획안 선택 월 AI 재생성 (BE-Y2b `POST /api/plans/annual/{id}/months/{month}/regenerate`) |
| 기존 SoT · 위치 | ① 이 저장소 `docs/api-spec.md` §4 (601행) ② 워크스페이스 `CLAUDE.md` §4 (119행) · §19 (783 · 801 · 815행) ③ `demo-source-of-truth.md` §3 (96행) · §16 (469~471행) ④ `screen-spec.md` §5 ③ · §5.3 |
| 기존 문구 | ① 「**재생성·삭제는 P0 에 없다.** 마음에 안 드는 칸은 §6 으로 고친다.」 ② 「연간 계획안 생성 / 편집 / 선택 Item 재생성 / 확정」 · 「전체 Yearly 재생성은 P0에 포함하지 않는다.」 ③ 「연간 계획안 생성·편집·셀 단위 재생성·확정」 · 「전체 재생성은 P0에 포함하지 않는다.」 ④ 공통 7요소 「③ 이 칸만 다시 뽑기」 · 「P0에서는 전체 재생성 기능을 만들지 않는다」 |
| 사용자 잠정 결정 | 계획안 **전체** 재생성 · 삭제는 P0 제외. **선택 월** 재생성은 P0 포함 |
| 충돌 내용 | ①은 문맥(§4 연간 생성 「반당 하나 · ALREADY_EXISTS」 바로 뒤)상 전체 재생성 · 삭제를 뜻하는 것으로 보이지만 문구만으로는 선택 월 재생성까지 막는 것으로 읽힌다. ②~④(우선순위가 더 높은 Planning SoT)는 선택 Item 재생성을 P0 로 요구한다 |
| 정정안 (PM 확인 뒤) | ① → 「**계획안 전체 재생성 · 삭제는 P0 에 없다.** 마음에 안 드는 달은 §6 으로 고치거나 그 달만 다시 만든다(§4-1).」 |
| 코드 영향 | BE-Y2b 를 만든다. 전체 재생성 · 삭제 API 는 만들지 않는다 |
| PM 확인 필요 | 예 — 「api-spec §4 의 '재생성·삭제는 P0에 없다'는 계획안 **전체** 재생성 · 삭제만 뜻하고, 달 단위 '이 칸만 다시 생성'은 P0 에 포함되는 것이 맞습니까?」 |
| 담당자 확인 필요 | 예 — api-spec §4 작성자(성진) · 연간 라우터 담당(승석) |
| 배포 전 해결 필요 | 예 |
| 구현 상태 | BE-Y2b 에 잠정 구현. api-spec 601행은 **고치지 않았다** — 정정은 PM 확인 뒤 |
| 최종 상태 | `USER_PROVISIONAL` · `PM_CONFIRMATION_PENDING` |

## B — 교사가 고친 연간 주제를 재생성으로 대체

| 필드 | 내용 |
|---|---|
| 결정 ID | PROV-Y-B |
| 관련 기능 | BE-Y2b 재생성이 교사가 이미 고친 달의 theme 를 새 값으로 바꾸는 동작 |
| 기존 SoT · 위치 | ① `demo-source-of-truth.md` §16 (470행) ② 워크스페이스 `CLAUDE.md` §19 (812행) · §2 (71행) ③ (참고 · 월간) 결정 문서 `template-profile-decisions.md` 12.10 · api-spec §9-3 — 월간 브랜치에만 있고 develop 에는 아직 없다 |
| 기존 문구 | ① 「`이 칸만 다시 생성`은 선택한 Item만 변경한다. 다른 Item과 교사 편집값은 보존한다.」 ② 「선택하지 않은 Item의 `item_id`, 값, Evidence를 보존한다.」 · 「교사 확정값은 이후 생성에서 이전 AI 원본보다 우선한다.」 ③ 월간: 「교사가 고친 칸도 요청하면 다시 만든다 — 고친 값이 새 값으로 바뀐다. 덮어쓰기 확인은 화면이 한다」 |
| 사용자 잠정 결정 | 명시적 재생성 요청이면 교사가 고친 theme 도 새 값으로 대체한다. 이전 값은 Core Audit(`REGENERATED.value_change.before`)에 남는다. 화면의 덮어쓰기 확인은 별도 FE 작업. 이전 값을 보여 주는 연간 Audit API 확장은 후속 PR |
| 충돌 내용 | ①의 「교사 편집값은 보존한다」가 **선택하지 않은 Item 의** 편집값만 뜻하는지(②와 같은 뜻), **재생성 대상 Item 의** 편집값까지 뜻하는지 문구로 정해지지 않는다. 후자라면 우선순위 2 SoT 가 이 동작을 금지한다 — 그 경우 이 문서는 금지를 우회하는 근거가 되지 않는다 |
| 추가 위험 | 덮어쓴 교사 문구는 DB(`plans.body` 의 Audit)에만 있고 **지금 연간 Audit API(`GET /api/plans/annual/{id}/audit`)는 값을 내주지 않는다** — 교사가 화면에서 되찾을 길이 없다 |
| 정정안 (PM 확인 뒤) | ① → 「…선택한 Item만 변경한다. **선택하지 않은 Item**과 그 교사 편집값은 보존한다. 선택한 Item 의 교사 편집값은 명시적 재생성 요청으로 대체되고 이전 값은 Audit 에 남는다.」 (PM 이 반대로 정하면 BE-Y2b 는 교사가 고친 달의 재생성을 거절하도록 바꾼다) |
| 코드 영향 | BE-Y2b 는 Core `RegenerateYearlyPlanItem` 그대로(교사 수정 여부를 보지 않는다) 노출한다. 요청 플래그 없음 |
| PM 확인 필요 | 예 — 「연간 '이 칸만 다시 생성'에서 '교사 편집값은 보존한다'는 재생성 **대상 달**의 교사 수정도 지켜야 한다는 뜻입니까, 아니면 다른 달의 편집값만 뜻합니까?」 |
| 담당자 확인 필요 | 예 — 연간 FE(재생성 확인 창) 담당 |
| 배포 전 해결 필요 | 예 (FE 노출 전) |
| 구현 상태 | BE-Y2b 에 잠정 구현 — 교사가 고친 달도 다시 만들고, 이전 값은 `plans.body` 의 `REGENERATED.value_change.before` 에 남는다(PostgreSQL 테스트로 확인). **Core Audit 에 남는 것과 교사가 화면에서 되찾을 수 있는 것은 다르다** — 연간 Audit API 는 아직 값을 내주지 않고(후속 PR), 화면의 덮어쓰기 확인도 없다(별도 FE 작업) |
| 최종 상태 | `USER_PROVISIONAL` · `PM_CONFIRMATION_PENDING` |

## C — 재생성 횟수 상한

| 필드 | 내용 |
|---|---|
| 결정 ID | PROV-Y-C |
| 관련 기능 | 연간(BE-Y2b) · 월간(M5) 칸 재생성의 호출 횟수 · 속도 · 비용 제한 |
| 기존 SoT · 위치 | ① `docs/api-spec.md` 「채워야 할 곳」(1691행) ② 이 저장소 `CLAUDE.md` (120행) |
| 기존 문구 | ① 「□ 재생성 횟수 상한 — 하민 · 성진 (7주차 논의)」 ② 「사용량은 카테캠 담당자가 보고 알려준다. 우리가 세지 않는다.」 |
| 사용자 결정 | **개발 · 테스트 단계에서는 상한을 두지 않는다.** 사용자별 · 원별 · 계획안별 횟수 상한, 일일 사용량 제한, 버튼 횟수 제한을 새로 만들지 않는다. 기존 LLM 예산 게이트(공급자 401·403·429 → 503 `LLM_BUDGET_EXCEEDED`) · 인증 · Tenant 격리 · 오류 처리 · 30초 timeout · 자동 재시도 없음은 그대로다. 테스트는 mock 생성기, 유료 호출은 별도 승인 |
| 충돌 내용 | 충돌은 아니다 — ①은 미결이고 ②는 「우리가 세지 않는다」. 다만 ②가 횟수 상한까지 금지하는지는 정해지지 않았다 |
| 배포 전 정할 것 | 사용자별 횟수 제한 · 원별 횟수 제한 · 호출 속도 제한 · 동시 재생성 제한 · 비용 예산과 모니터링 · 과도한 호출의 오류 정책 |
| 코드 영향 | BE-Y2b 에 제한 코드를 넣지 않는다 |
| PM 확인 필요 | 배포 전에 예 |
| 담당자 확인 필요 | 예 — ① 의 담당(하민 · 성진) |
| 배포 전 해결 필요 | 예 |
| 구현 상태 | BE-Y2b 에 횟수 · 속도 · 동시 제한 코드를 넣지 않았다. 재생성 1회 = LLM 호출 1회(mock 기본), 자동 재시도 없음. 테스트는 mock 생성기만 썼다(유료 호출 0회) |
| 최종 상태 | `USER_CONFIRMED_FOR_DEVELOPMENT` · `RELEASE_POLICY_PENDING` |

## D — 연간 PUT · Confirm 쓰기 경로 행 잠금 (BE-Y2a)

| 필드 | 내용 |
|---|---|
| 결정 ID | PROV-Y-D |
| 관련 기능 | `PUT /api/plans/annual/{id}/months/{month}` · `POST /api/plans/annual/{id}/confirm` |
| 기존 SoT · 위치 | 결정 문서 `template-profile-decisions.md` 12.4 D-3 (2253행) · 12.10 (2389행) |
| 기존 문구 | 「연간 PUT에 같이 걸지는 그 PR에서 정한다(PR-LOCAL).」 · 「연간 PUT 에 revision 을 거는 것은 이번 범위가 아니다(D-3 PR-LOCAL, 연간 API 무변경).」 |
| 사용자 결정 | 연간 PUT · Confirm 이 계획안 행을 `SELECT … FOR UPDATE` 로 읽는다(짧은 transaction 안). **클라이언트 revision 은 넣지 않는다** — HTTP 계약 무변경 |
| 충돌 내용 | 충돌 아님 — D-3 이 보류한 것은 클라이언트가 보내는 revision 이고, 이것은 서버 안의 잠금이다. 다만 연간 쓰기 경로의 동작(동시 요청이 기다렸다가 최신 값을 읽는다)이 바뀐다 |
| 고치는 문제 | 지금은 확정과 PUT 이 겹치면 PUT 이 옛 DRAFT 본문을 저장해 **확정이 DRAFT 로 되돌아가고 CONFIRMED 이력이 사라질 수 있다.** 다른 달을 동시에 고친 PUT 둘도 한쪽이 사라진다 |
| 코드 영향 | `backend/app/features/plans/router.py` 의 `_row` 에 잠금 인자 · PUT · Confirm 에 적용. Migration · Core · 응답 계약 무변경 |
| PM 확인 필요 | 아니오 (계약 무변경). 공유를 권한다 |
| 담당자 확인 필요 | **예 — 연간 라우터 담당(승석).** 조율 전에는 병합하지 않는다 |
| 배포 전 해결 필요 | 담당자 확인 |
| 최종 상태 | `USER_CONFIRMED_FOR_DEVELOPMENT` · `OWNER_COORDINATION_PENDING` |

## E — 소주제가 있는 달의 재생성 거절 (BE-Y2b)

| 필드 | 내용 |
|---|---|
| 결정 ID | PROV-Y-E |
| 관련 기능 | BE-Y2b 선택 월 재생성 |
| 기존 SoT · 위치 | `docs/api-spec.md` §4 (477~482행 「`sub_themes` 는 P0 생성 시 항상 빈 배열이다 … 교사가 §6 으로 채운다」 · 503~515행 소주제 생성 방향). 재생성 때의 처리는 **정해져 있지 않다** |
| 사용자 결정 | 그 달 `sub_themes` 에 **앞뒤 공백을 뺀 값이 하나라도** 있으면 재생성을 거절한다 — 422 `VALIDATION_FAILED` `["sub_themes"]`. `[]` · `["", "   "]` · 키 없음은 「없음」. 자동 삭제 · 자동 교체 없음 |
| 이유 | 소주제는 Domain 밖(`plans.sub_themes`)이라 Audit 에 남지 않는다 — 지우면 흔적 없이 사라지고, 남기면 새 주제와 옛 소주제가 어긋난다 |
| 원자성 | 시작할 때 검사하고, **저장 문장의 조건에 소주제 비교(`sub_themes = 읽은 값`)를 넣었다** — LLM 을 기다리는 동안 소주제가 생기거나 바뀌면 저장하지 않고 409 `STALE_WRITE` (PostgreSQL 테스트 F · F2, 조건을 빼면 F 가 실패하는 음성 대조) |
| 코드 영향 | `backend/app/features/plans/router.py` `_has_sub_themes` · `regenerate_month` |
| PM 확인 필요 | 권장 (교사 흐름: 소주제를 비운 뒤 다시 만들어야 한다) |
| 담당자 확인 필요 | 예 — 연간 라우터 담당(승석) |
| 배포 전 해결 필요 | 예 |
| 최종 상태 | `USER_CONFIRMED_FOR_DEVELOPMENT` · `PM_CONFIRMATION_PENDING` · `OWNER_COORDINATION_PENDING` |

## F — 재생성 저장의 동시성 (BE-Y2b)

| 필드 | 내용 |
|---|---|
| 결정 ID | PROV-Y-F |
| 관련 기능 | BE-Y2b 선택 월 재생성 · BE-Y2a 행 잠금과의 관계 |
| 기존 SoT · 위치 | 결정 문서 12.4 D-3 · 12.10 (클라이언트 revision 보류) |
| 사용자 결정 | 3단계: ① 짧은 읽기(잠금 없음) → transaction 종료 ② Core 재생성(DB 없음, LLM 대기 중 **행 잠금 없음**) ③ 한 문장 조건부 UPDATE — `plan_ref · center_id · kind='annual' · status='DRAFT' · body = 읽은 body · sub_themes = 읽은 sub_themes`. `RETURNING` 으로 0 행이면 아무것도 쓰지 않고, 다시 읽어 CONFIRMED 면 409 `ALREADY_CONFIRMED`, 아니면 409 `STALE_WRITE` |
| BE-Y2a 와의 관계 | PUT · 확정은 행을 잠그고 읽으므로(Y2a) 재생성 저장이 그 잠금을 기다렸다가 조건을 다시 보고 실패한다(테스트 D · E). 재생성이 먼저 쓰면 PUT · 확정은 새 본문을 읽는다. 연간 PUT 은 같은 주제여도 본문에 `TEACHER_EDITED` 를 더하므로 본문 비교가 모든 PUT 을 잡는다 |
| 분류의 한계 | 409 를 고르려고 다시 읽는 사이에 상태가 또 바뀌면 코드가 어긋날 수 있다(예: STALE 이었는데 그 사이 확정돼 ALREADY_CONFIRMED). **DB 에 쓴 것은 없다** — 데이터 불변과 코드 정확성은 따로다 |
| 코드 영향 | `backend/app/features/plans/repository.py` `update_if_unchanged`(조건부 UPDATE) · `router.py` `regenerate_month`. Migration · Core 무변경 |
| 담당자 확인 필요 | 예 — 연간 라우터 담당(승석). `repository.py` 는 월간 M3(`update_if_revision`)도 고친다 — 병합 순서 확인 필요 |
| 배포 전 해결 필요 | 담당자 확인 |
| 최종 상태 | `USER_CONFIRMED_FOR_DEVELOPMENT` · `OWNER_COORDINATION_PENDING` |

---

## 부록 — BE-Y2b 잠정 API 계약 (비권위)

> **AUTHORITATIVE 가 아니다.** PROV-Y-A · B 의 PM 확인 뒤 `docs/api-spec.md` 에 정식으로 옮긴다. 그 전까지
> 화면은 이 계약에 기대지 않는다(FE 연결은 별도 작업).

`POST /api/plans/annual/{id}/months/{month}/regenerate` — 요청 본문 없음 · `200` 에 기존 `MonthOut`
(§6 PUT 응답과 같은 모양).

```
그 달 theme 하나만 다시 만든다(Core RegenerateYearlyPlanItem). 다른 11개월은 그대로다.
evidence    새 THEME_REFERENCE(theme_id · catalog_version) — 이전 THEME_REFERENCE 는 남지 않는다
generation  RULE_LLM · yearly.theme.sample_derived_candidate_selection · v2
audit       그 달 theme 에 REGENERATED(actor · 시각 · value_change · generation_change) — 연간 Audit API 는
            type · month · actor · 시각만 준다
```

| code | status | 언제 | `fields` |
|---|---|---|---|
| `UNAUTHENTICATED` | 401 | 로그인 안 함 | `[]` |
| `NOT_FOUND` | 404 | 없는 계획안 · 남의 원 · 연간이 아님 | `["id"]` |
| `NOT_FOUND` | 404 | 없는 달 | `["month"]` |
| `ALREADY_CONFIRMED` | 409 | 확정된 계획안 (시작 때 · 저장 때) | `[]` |
| `STALE_WRITE` | 409 | LLM 을 기다리는 동안 PUT · 다른 재생성 · 소주제 변경이 있었다 | `[]` |
| `VALIDATION_FAILED` | 422 | 그 달에 의미 있는 소주제가 있다 | `["sub_themes"]` |
| `VALIDATION_FAILED` | 422 | 그 달에 쓸 주제 후보가 없다 | `["month"]` |
| `DEPENDENCY_UNAVAILABLE` | 503 | 생성기 설정 없음 · Theme catalog 해석 실패 · 사람 승인 전 | `[]` |
| `LLM_BUDGET_EXCEEDED` | 503 | 공급자 한도 · 키 삭제(401 · 403 · 429) | `[]` |
| `GENERATION_FAILED` | 500 | LLM 호출 실패 · 결과가 계약을 어김 · 그 밖의 Core 거절. 아무것도 저장하지 않는다 | `[]` |

- 응답 message 는 고정 문구다 — Core 예외 문구를 내보내지 않는다.
- 횟수 · 속도 제한 없음(PROV-Y-C). 같은 요청을 다시 보내면 다시 만든다(멱등 아님).
