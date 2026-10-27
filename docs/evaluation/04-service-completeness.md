# 04 · 서비스 완성도

**기준 원문** — (받은 기준 문장을 그대로 붙인다)

---

## 핵심 기능 하나 — 아직 PM 이 안 골랐다

멘토 지적: 평가 기준이 **핵심 기능을 하나로** 보는 것 같다. 지금 우리는 두 덩어리를 같이 밀고 있다.

| 후보 | 무엇 | 지금 상태 |
|---|---|---|
| **A. 기록 한 줄 → 제출용 일지** | 관찰·일과 기록에서 일일/주간 보육일지 · 관찰일지 · 영유아 평가 | 4종 다 있음. 3층 규격 · 3단 게이트가 여기 걸린다 |
| **B. 계획안 3층** | 연간 → 월간 → 주간, 놀이 프로젝트형 포함 | 코드량 가장 큼. PR #223~#253 |

**추천 — A.** 이유 셋:

1. B 는 「AI 가 계획 써주기」로 다른 서비스와 겹친다. A 의 **「교사가 준 사실만 쓰고 없는 사실을 쓰면 반려」**는 우리 설계다
2. 우리가 쌓은 방어 장치(3층 규격 · 3단 게이트 · 아동 코드 치환 · 사실기록형 금지)가 전부 A 에 붙어 있다
3. 교사가 **매일** 쓰는 쪽이 A 다. 계획안은 분기·월 단위다

B 를 고르면 — 놀이 프로젝트형 연간이 「다른 데 없는 것」이라는 근거를 따로 대야 한다.

> PM 결정 칸: ___________ (정하면 여기 적고 날짜를 남긴다)

## 끝까지 도는가

| 기능 | 코드 | 확인 |
|---|---|---|
| 가입 · 로그인 · 비밀번호 변경 | `backend/app/features/auth/` | `tests/test_auth.py` |
| 원 · 반 · 아동 | `features/centers` · `children` | `test_centers.py` · `test_children.py` |
| 관찰 기록 · 일과 기록 | `features/observations` · `routines` | `test_observations_db.py` · e2e `routines.spec.ts` |
| 문서 4종 생성 · 확정 | `features/documents` | `test_documents.py` · `test_documents_reconfirm.py` |
| 계획안 연간 · 월간 · 주간 | `features/plans` · `p0-planning/` | `test_monthly_plans_api.py` 외 |
| 평가제 자체점검 | `features/evaluation` | `test_evaluation_auto.py` · `test_evaluation_judge.py` |
| 양식 업로드 · 파싱 | `features/forms` | `test_forms.py` |
| hwpx 내보내기 | `shared/hwpx.py` | `test_documents_export.py` · ADR-039 |

기능 폴더 13개 — `ls backend/app/features/`.

## 아직 아닌 것

- 영유아 평가는 실물 양식을 못 봐서 칸 배치가 미정 — [docs/미확정사항.md](../미확정사항.md) U-3
- 내보낸 hwpx 의 「문서 정보」 날짜가 비어 있다 — 이슈 #176
- 평가제 4-1 이 주간계획안을 세야 하는지 미정 — 이슈 #179

## 더 모을 근거

- [ ] 핵심 기능 하나를 정하고 그 경로만 처음부터 끝까지 영상 1회
