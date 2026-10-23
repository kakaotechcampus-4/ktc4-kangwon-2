# ADR-034: 양식 설정(TemplateProfile)은 원이 소유하고, 생성은 화면이 보여 준 정확한 버전을 쓴다

- 2026-10-19 (결정은 2026-10-06 ~ 10-10 사용자 결정)
- 상태 — 채택 (옮겨 적기, PM-13 C · AP-06)
- 관련 — ADR-017 · ADR-027 · api-spec §9-1 · §9-2 · §9-4 · `backend/app/features/template_profiles/`

## 맥락

월간 생성은 반에 쓸 양식 설정(TemplateProfile)을 고르고, 그 설정의 칸 목록대로 계획안을 만든다. 누가 설정을 갖는지, 기본값을
어떻게 고르는지, 생성 요청이 무엇을 담는지는 개인 결정 문서의 「Contract 2」와 Part 12 에 있었다(저장소 밖, K-25).
api-spec §9-1 ~ §9-4 가 「결정 문서 Contract 2 · 12.8 · 12.12」를 인용했다. **이 ADR 은 원 ID 를 남기고 옮겨 적는다.** 새 결정은 없다.

## 결정

### 1. 소유와 버전 (Contract 2 C2.6)

- TemplateProfile 은 **원** 소유다(`centers.id`). 여러 반 · 여러 학년도가 같은 READY 버전을 같이 쓴다. 반별 복제 · 교사별 복사 · 상속 없음.
- (원, 문서 종류)마다 READY 버전이 여럿일 수 있다. **READY 는 바뀌지 않는다** — 구조를 바꾸려면 새 버전을 만든다.
- 버전 행은 지우지 않는다. ARCHIVED 는 새 포인터 대상이 될 수 없고 과거 계획안에는 영향이 없다.

### 2. 기본 포인터 · 반 override (C2.6)

- 원 기본: (원, 문서 종류)당 포인터 하나 → 정확한 `(profile_id, profile_version)`. **Profile 의 상태가 아니라 포인터다.**
- 반 override: (`classes.id`, 문서 종류)당 포인터 하나(선택).
- 포인터 대상 조건: 같은 원 · 같은 문서 종류 · READY · `classroom_ref = null`. 포인터는 사용자가 명시적으로 바꿀 때만 바뀐다.
  바꾼 계정(`changed_by`)과 시각을 남긴다.
- 새 READY 버전이 생겨도 포인터는 움직이지 않는다. 「최신 버전」을 자동으로 따라가지 않는다.
- 포인터가 가리키는 READY 는 보관할 수 없다. 대체 지정이나 해제를 먼저 한다(자동 해제 · 자동 이동 없음).

### 3. 고르는 순서 (C2.7)

```text
R1  반 override 가 있으면 → 그 버전             source = CLASSROOM_OVERRIDE
R2  없으면 원 기본이 있으면 → 그 버전           source = INSTITUTION_DEFAULT
R3  찾은 대상을 못 쓰면 → 다음 단계로 내려가지 않고 「선택 필요」
R4  둘 다 없으면 → 「선택 필요」 — READY 목록 + 「Reference 기반으로 시작」
```

- **R3 에서 원 기본으로 내려가지 않는다.** 한 단계를 건너뛰면 사용자가 고른 반 설정이 조용히 무시된다.
- **R5 — 생성 요청은 화면이 보여 준 정확한 `profile_ref` 를 담는다.** 서버는 그 버전이 READY · 같은 원 · 같은 문서 종류인지 검사하고,
  요청 사이에 포인터가 바뀌었다고 조용히 다시 고르지 않는다.
- **R6 — 생성 전에 어느 버전을 어디서(override / 원 기본 / 직접 선택) 가져왔는지 보여 준다.**

### 4. 권한 (C2.6 · TP-05 `RESOLVED_FOR_P0`)

- P0 는 원 단위 인가를 그대로 쓴다(ADR-017). 원 소속 계정 누구나 포인터를 바꿀 수 있다. 신규 역할 없음.
- 남의 원 Profile · 반은 **404** 다. 「없음 · READY 아님 · 남의 원」을 가르지 않는다.

### 5. 월간 생성 요청 (12.5 · D-M4-01, 2026-10-09)

- 생성 요청은 정확한 `profile_ref` + 반 + 대상 월. 부모 연간은 서버가 반으로 찾고 CONFIRMED 만 쓴다. 생성 모드는 서버 정책(`LLM_PLANNER`).
- 월간은 **반 · 월당 하나**다. 중복은 409 `ALREADY_EXISTS`(DB 부분 유일 인덱스가 최종 보장).
- LLM 이 실패하면 가짜 결과로 대체하지 않는다.

### 6. 관리 API (D-M4-02 · 12.12 ② ~ ⑤, 2026-10-10)

- 승인 전 Template 으로 READY Profile 을 시작하면 409 `GATE_BLOCKED` `["base_template_ref"]`.
- 생성 계약이 없는 기관 입력 칸(`event_schedule` · `drill`)을 고르면 422 `VALIDATION_FAILED`.
- 승인 대기 Template 도 목록에 `approved: false` 로 보인다. 보인다고 쓸 수 있는 것은 아니다.
- 원 기본 · 반 override 지정 / 해제는 PUT 하나(`profile_ref: null` 이면 해제). `expected_profile_ref` 로 비교하고 다르면 409 `STALE_WRITE`.
- DRAFT 만들기 · 편집 · READY 전환 · 보관 API 는 후속이다.

## 근거

- **[출처]** 사용자 결정: Contract 2 4판(C2.6 · C2.7), 2026-10-09 D-M4-01 · D-M4-02, 2026-10-10 BE-1 ② ~ ⑤. 원문은 개인 결정 문서에 있고
  이 ADR 이 원 ID 를 보존해 옮긴다(PM-13 C).
- **[실측]** 구현: `backend/app/features/template_profiles/` (`models.py` 의 버전 · 기본 · override 테이블, `service.py`
  `ready_profile_for_generation`), 테스트 `test_template_profile_management_api.py` · `test_monthly_plans_api.py`.

## 대안

결정 당시 대안(Profile 상태로 기본을 표시, 최신 버전 자동 추종, 교사별 복사 등)과 기각 이유는 원 결정 기록에 있다.

## 결과

- api-spec §9-1 · §9-2 · §9-4 의 「결정 문서 Contract 2 / 12.5 / 12.9 / 12.12」 인용은 이 ADR 을 가리킨다.
- **Template 승인과 Profile READY 는 다르다.** READY Profile 이 있다고 그 기반 Template 이 사람 승인을 받은 것이 아니다 — 생성 직전에
  승인을 다시 본다(ADR-027 §6).
- 기본 Section 삭제 정책과 「이번 달 한 줄 요청」은 P0 범위가 아니다. 후속 기능이다(ADR-030 PM-10).
- 남은 것: TemplateProfile 표시 이름(Core 에 이름 칸 없음), `classroom_ref` 필드 제거 여부(TP-25).
