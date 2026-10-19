# ADR-035: 동시 수정과 확정 재호출 — 월간은 revision 으로, 연간은 서버 행 잠금으로 막고, 확정 재호출은 200 이다

- 2026-10-19 (결정은 2026-10-06 · 2026-10-09 · 2026-10-14 · 2026-10-19)
- 상태 — 채택 (옮겨 적기 + PM-05 A · AP-03 추가, ADR-030)
- 관련 — api-spec §6 · §7 · §9-3 · `backend/app/features/plans/repository.py` · PR #171

## 맥락

두 화면이 같은 계획안을 열고 각자 저장하면 나중 저장이 본문 전체를 덮어써 먼저 고친 내용이 표시 없이 사라진다.
월간은 이를 revision 으로 막는다고 정했고(개인 결정 문서 12.4 D-3 · 12.10), 연간은 정해지지 않았다(K-12).
연간에는 확정과 PUT 이 겹치면 **확정이 DRAFT 로 되돌아가고 CONFIRMED 이력이 사라지는** 경로도 있다(PROV-Y-D).
연간 「선택 월 재생성」은 잠정으로 진행했다가 리뷰어가 도입하지 않기로 정했다(PROV-Y-A · B, #147).
이 결정들의 근거는 저장소 밖 문서와 Y2a 브랜치에만 있었다.

## 결정

### 1. 월간 — revision 비교 (12.4 D-3 · 12.10, 2026-10-06 · 10-09)

- `plans.revision` 은 저장할 때마다 +1 이다. 월간 편집 · 재생성 · 확정 요청은 읽을 때 받은 `expected_revision` 을 보낸다.
- 서버 값과 다르면 저장하지 않고 409 `STALE_WRITE` `["expected_revision"]`. 새 오류 코드를 만들지 않고 문서 PUT 과 같은 코드를 쓴다.
- 비교와 +1 은 조건부 UPDATE 한 문장이다(`id · center_id · kind · status='DRAFT' · revision = expected`). 0행이면 다시 읽어 404 /
  409 `ALREADY_CONFIRMED` / 409 `STALE_WRITE` / (확정이면) 200 으로 가른다.
- 생성 · 재생성은 짧은 읽기 → DB 없이 Core → 조건부 쓰기다. LLM 을 기다리는 동안 transaction 을 잡지 않는다.

### 2. 확정 재호출은 200 (D-M5-CONFIRM-01, 2026-10-09)

1. DRAFT + revision 일치 → CONFIRMED, revision +1, 200
2. DRAFT + revision 불일치 → 409 `STALE_WRITE`, 변경 없음
3. **이미 CONFIRMED → `expected_revision` 과 무관하게 200.** 저장된 그대로 — revision · `confirmed_at` · 확정자 · 확정 이벤트가 바뀌지 않는다
4. CONFIRMED 에 편집 · 재생성 → 409 `ALREADY_CONFIRMED`
5. 없거나 남의 원 계획안 → 404. **멱등이 소유 검사를 우회하지 않는다**

- 이유: 첫 확정이 revision 을 올리므로 더블클릭 · 재시도로 온 두 번째 요청은 늘 옛 revision 을 든다. 409 를 주면 정상 경로가 실패로 보인다.
- **연간도 같다**(api-spec §7 「재호출은 멱등」). develop 서버는 연간 재확정에 409 를 내고 있다 — PR #171 이 200 으로 고친다.

### 3. 연간 — 서버 행 잠금 (PM-05 A, 2026-10-19 · PROV-Y-D)

- 연간 PUT · 확정은 계획안 행을 `SELECT … FOR UPDATE` 로 읽는다(짧은 transaction 안).
- **연간 HTTP 계약은 바뀌지 않는다.** 연간에 `expected_revision` 을 새로 두지 않는다.
- 이것이 막는 것: 확정과 PUT 이 겹쳐 확정이 DRAFT 로 되돌아가는 경로, 다른 달을 동시에 고친 PUT 둘 중 하나가 사라지는 경로.
- 막지 않는 것: 두 교사가 서로 다른 시점에 읽고 쓰는 덮어쓰기. **다중 교사(#139 초대 코드) 이후 연간 `expected_revision` 을 다시 본다**
  (미확정사항 U-16).
- 구현은 연간 Backend Y2a(브랜치 `feature/yearly-be-y2a-write-lock`)다. **연간 라우터 담당 확인(PROV-Y-D 「담당자 조율」)이 남았다.**

### 4. 연간 선택 월 재생성은 도입하지 않는다 (PROV-Y-A · B — 리뷰어 결정 2026-10-14, PM 결정 2026-10-19)

- PROV-Y-A **도입하지 않음.** 연간 12개월 주제는 서로 이어져 있어 한 달만 다시 뽑으면 앞뒤가 깨진다. 교사는
  `PUT /api/plans/annual/{id}/months/{month}` 로 고친다. 월간 칸 재생성은 그대로다 — 월간 칸끼리는 독립이다.
- PROV-Y-B **해당 없음**(연간 재생성이 없으므로).
- AP-03 추가 승인으로 이 리뷰어 결정을 PM 결정으로도 기록한다.
- **Core 의 `RegenerateYearlyPlanItem` 은 남는다.** HTTP · 화면에 노출하지 않을 뿐이다 — 「Core 만, HTTP 미노출(2026-10-14)」.
- PROV-Y-C(재생성 횟수 상한)는 월간 칸 재생성에만 남는다: 개발 · 테스트 단계에서는 상한을 두지 않고, 배포 전에 사용자별 · 원별 횟수 ·
  속도 · 동시 실행 · 비용 정책을 정한다.

## 근거

- **[출처]** 사용자 결정 12.4 D-3(2026-10-06) · D-M5-CONFIRM-01(2026-10-09), 리뷰어 결정 PROV-Y-A · B(2026-10-14, #147),
  PM-05 = A · AP-03 추가 = 예(2026-10-19, ADR-030). 잠정 정책 원문은 Y2a 브랜치의 `docs/provisional-policy-decisions.md` 다.
- **[실측]** 월간: `backend/app/features/plans/repository.py` `update_if_revision`, `monthly_router.py` `_write`,
  테스트 `test_monthly_lifecycle_api.py` 의 동시 편집 · 확정 테스트.
- **[실측]** 연간 행 잠금 없이 PUT 과 확정이 겹치면 상태 칸은 CONFIRMED 인데 본문은 DRAFT 로 남는 행이 생긴다(Y2a 작업 중 재현).

## 대안

- **연간도 `expected_revision`(PM-05 B).** HTTP · FE · mock 이 함께 바뀐다. 지금은 반당 교사 1명이 기본이라 행 잠금이 먼저다 — 다중 교사 뒤 재검토.
- **보호하지 않는다(PM-05 C).** 확정이 되돌아가는 경로가 남는다 — 고르지 않았다.
- **이미 CONFIRMED 여도 revision 이 다르면 409(옛 A안).** 정상 재시도가 실패한다 — D-M5-CONFIRM-01 이 폐기했다.

## 결과

- api-spec §4 의 「재생성 · 삭제는 P0 에 없다」 옆에 이 ADR 근거를 단다. screen-spec S8 의 「이 칸만 다시 뽑기」를 지운다.
- ADR-016 의 「`RegenerateYearlyPlanItem` 이 칸 단위로 돈다」에 「Core 만, HTTP 미노출」 각주를 단다.
- 폐기 표시(삭제 승인 아님): 잠정 정책 문서 §E · §F · 부록(재생성 API), Y3 브랜치 api-spec §7-1 의 REGENERATED 예시와 `generation_change`,
  브랜치의 연간 재생성 라우터 · FE. Y2b · Y3 · handoff 브랜치는 그대로 머지하지 않는다. Y3 는 재생성을 뺀 새 commit 으로 옮긴다(Y3′).
- 잠정 정책 문서를 develop 의 어디에 둘지는 연간 라우터 담당과 정한다. 이 ADR 이 그 결정 내용을 대신 담는다.
