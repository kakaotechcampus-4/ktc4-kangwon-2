# 생활 문장 Reference v0.1.0 — Human Review 요청 자료

> **이 문서는 승인 요청 자료다. 승인 기록이 아니다.**
>
> ```text
> catalog_id            : ssuksak.daily-life
> catalog_version       : daily-life-v0.1.0
> domain_owner_approval : PENDING_HUMAN_REVIEW
> approved_by           : null
> approved_at           : null
> runtime_active        : false
> ```

- 대상 파일: `p0-planning/data/daily-life/daily_life_reference_v0_1_0_draft.json`
- 로더: `p0-planning/src/ssuksak/adapters/json_daily_life_reference_repository.py`
- 작성일: 2026-10-29
- 관련: ADR-046 (서버 질문 1 · 자료와 로더는 Core 쪽이 제공), ADR-027 §5 (승인 절차)
- 쓰는 곳: 놀이중심 월간(PLAY_MONTHLY)의 기본생활습관(주마다 하나) · 건강 · 영양(월마다 하나씩). LLM은 `entry_id`만 고르고 칸의 문장은 서버가 이 파일에서 그대로 복사한다. 칸의 Evidence는 `CURRICULUM(content_id, 누리과정 판)`이다.

## 1. 문장 15개

2026-10-27에 AI 리드(`reviewer_ai_lead_01`)가 채택한 문장을 그대로 옮겼다. 문장 · 표시 분류 · `content_id`는 채택 때와 같다(`tests/unit/test_daily_life_reference.py`가 글자 그대로 고정한다). 문장 채택은 이 Catalog 전체의 정식 승인이 아니다.

| entry_id | 종류 | 표시 분류 | 문장 | content_id | 출처 쪽 | 검토 주의 |
|---|---|---|---|---|---|---|
| `habit.01` | HABIT | 청결 | 놀이한 뒤 손을 깨끗이 씻어요 | `nuri2019.1.2.1` | 고시 p.10 · 해설 p.67 |  |
| `habit.02` | HABIT | 청결 | 사용한 놀잇감을 제자리에 정리해요 | `nuri2019.1.2.1` | 고시 p.10 · 해설 p.67 |  |
| `habit.04` | HABIT | 식습관 | 식사 자리에 앉아 즐겁게 먹어요 | `nuri2019.1.2.2` | 고시 p.10 · 해설 p.67 |  |
| `habit.06` | HABIT | 휴식 | 몸이 피곤하면 잠시 쉬어요 | `nuri2019.1.2.3` | 고시 p.10 · 해설 p.68 |  |
| `habit.10` | HABIT | 언어 예절 | 친구의 이야기를 듣고 말해요 | `nuri2019.2.1.5` | 고시 p.11 |  |
| `habit.15` | HABIT | 약속·질서 | 함께 정한 놀이 약속을 지켜요 | `nuri2019.3.2.6` | 고시 p.12 |  |
| `habit.17` | HABIT | 감정 표현 | 속상한 마음을 말이나 몸짓으로 전해요 | `nuri2019.3.1.2` | 고시 p.12 · 해설 p.85 |  |
| `health.01` | HEALTH | 손 씻기 | 손을 깨끗이 하는 방법을 알아봐요 | `nuri2019.1.2.1` | 고시 p.10 | 특정 세정 제품·효과·시간을 근거 없이 추가하지 않음 |
| `health.02` | HEALTH | 이 닦기 | 이를 깨끗이 하는 방법에 관심을 가져요 | `nuri2019.1.2.1` | 고시 p.10 · 해설 p.67 | 해설 p.67에서 이 닦기 설명 확인. 의학적 효과·용량 설명 추가 안 함 |
| `health.03` | HEALTH | 내 몸의 휴식 | 내 몸이 쉬고 싶을 때를 알아봐요 | `nuri2019.1.2.3` | 고시 p.10 | 같은 시간·같은 방법으로 쉬도록 강요하지 않음 |
| `health.04` | HEALTH | 날씨와 옷차림 | 날씨에 맞는 옷차림을 알아봐요 | `nuri2019.1.2.4` | 고시 p.10 · 해설 p.68 | 해설 p.68과 연결. 특정 옷차림이 질병을 치료한다고 쓰지 않음 |
| `nutrition.05` | NUTRITION | 음식에 관심 갖기 | 몸에 좋은 음식에 관심을 가져요 | `nuri2019.1.2.2` | 고시 p.10 | 특정 음식을 악역으로 분류하거나 영양소 효능을 창작하지 않음 |
| `nutrition.06` | NUTRITION | 즐거운 식사 | 편안하고 즐겁게 식사하는 방법을 알아봐요 | `nuri2019.1.2.2` | 고시 p.10 | 먹는 양·속도·남김을 통제하는 문장으로 바꾸지 않음 |
| `nutrition.07` | NUTRITION | 식사할 때의 자세 | 식사 자리에 앉아 즐겁게 먹어요 | `nuri2019.1.2.2` | 고시 p.10 | Reference 문장과 유사하나 출력 출처는 별도 추적. 기본생활습관과 중복될 수 있음 |
| `nutrition.08` | NUTRITION | 다양한 음식 경험 | 여러 음식에 관심을 가져요 | `nuri2019.1.2.2` | 고시 p.10 · 해설 p.67 | 해설 p.67의 식생활 설명과 연결. 강제 맛보기·정해진 양 먹기로 확대하지 않음 |

- **같은 문장 두 개:** `habit.04`와 `nutrition.07`은 「식사 자리에 앉아 즐겁게 먹어요」로 같다. 구역이 달라 각각 채택했고, 같은 달 기본생활습관 칸과 영양 칸에 함께 나올 수 있다. 중복을 자동으로 거절하지 않는다.
- **ID:** `ssuksak.daily-life.<종류>.<번호>`. 번호는 채택 때 검토 행 번호를 따라서 01 · 02 · 04처럼 비어 있다. 번호가 이어지지 않아도 계약 문제가 아니며, 발행한 뒤에는 같은 ID의 뜻을 바꾸지 않는다.

## 2. 출처

| origin_id | 자료 | sha256 | 쪽 |
|---|---|---|---|
| `nuri2019.notice.mohw` | 2019 개정 누리과정 (보건복지부 고시 제2019-152호) | `74b48934…` | PDF 쪽 = 인쇄 쪽. 영역별 「2. 내용」 표 |
| `nuri2019.commentary` | 2019 개정 누리과정 해설서 | `7e1b0017…` | 채택 검토 때 적은 쪽. PDF · 인쇄 구분은 다시 확인하지 않았다 |

- 해시는 누리과정 Reference의 출처 정보에서 옮겼다. 이번 작업에서 PDF를 다시 해시하지 않았다.
- `origins` · `origin_refs`는 검토용 출처 이력이다. 도메인 Catalog에는 실리지 않고, 로더가 `origin_refs`가 실제 `origins`를 가리키는지만 검사한다. 새 Evidence 종류가 아니다.
- 문장은 자체 작성한 제품 문장이다. 국가가 정한 예문 · 월별 배치표가 아니다.

## 3. 승인 때 볼 것

1. 15개 문장 · 표시 분류가 유아에게 쓸 수 있는 표현인지, `content_id`가 그 생활 장면과 이어지는지.
2. 위 「검토 주의」 경계(특정 제품 · 효과 · 양 · 속도 강요 금지)가 문장에서 지켜지는지.
3. 제품에 실을 문장 · 출처 표기의 이용 범위.

## 4. 승인 절차 (ADR-027 §5)

- 승인 커밋은 `review`의 승인 칸(`domain_owner_approval` · `approved_by` · `approved_at` · `runtime_active`)만 바꾼다. 판 · 파일 이름 · 문장은 그대로다.
- `tests/finalization/test_freeze.py`: `PENDING_REVIEW_PINS`의 이 파일 항목을 빼고 새 SHA를 `FROZEN_ARTIFACTS`에 넣는다. `PENDING_REVIEW_CONTENT`의 항목은 그대로 두어 승인 칸 밖이 바뀌지 않았음을 증명한다.
- 승인해도 놀이중심 월간 생성은 훈련 주제 자료 승인과 서버의 AI 호출 연결이 남아 있으면 계속 503이다.
