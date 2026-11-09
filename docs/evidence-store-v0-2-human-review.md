# Evidence Store v0.2.0 — 개인정보 정제와 기존 분류 재결합

- 승인일: 2026-11-02
- 승인자: `reviewer_ai_lead_001`
- 범위: 기존 처리 JSON에서 사람이 REMOVE로 판정한 기록 42개를 통째 제외. 남은 기록 12,325개와 출처 manifest는 그대로다. PDF 재추출은 없다.
- 제외 사유: `PII_BIRTHDAY_LIST` 3개, `PII_PERSON_NAME` 39개. 일반 활동 `GENERAL_ACTIVITY` 32개는 KEEP이다. 새 기록·연간 주제·주간 추출 자료는 추가하지 않는다.

## 승인한 파일

| 파일 (`p0-planning/data/evidence/`) | 기록 또는 판정 수 | 파일 SHA-256 |
|---|---:|---|
| institution_evidence_v0_2_0.json | 12,325 | `7c051742a4e74628b8c4e2497c58e61dfa4e8399e72847a77539bfe92eeb7c98` |
| monthly_evidence_semantic_classification_v0_2_0.json | 16 | `6d3702d82b2b64af6d69b7d9a0d80d51218653bc5bbf130f2a9fb13050b007a5` |
| weekly_evidence_semantic_classification_v0_2_0.json | 179 | `c5e38b82c8c15f21b0e58ea6a8a52c4d9f10d7dedfc3e4bb88070291b026e19a` |
| safety_evidence_classification_v0_3_0.json | 103 | `226be6158d9fca201dd1087f0de772d93ff0526d188526280c24720ba3881c18` |
| safety_reference_quality_v0_2_0.json | 32 | `69ed11dcd478b29fe93944e5f6c0080af0fba5faa55dfd33eb2d432b1a53e568` |

새 자료 content SHA는 `99260c65df0ba0d1c5d010c93a17762c3aa134ea93836e6b8e04348afe27b3ce`이다. 분류 4종의 판정 항목은 이전 판과 완전히 같고, 자료 결합과 판·검토 메타데이터만 새로 기록했다. 기존 승인을 승계하지 않고 이 파일별 승인을 반영했다. 승인 칸은 이번 승인 시점에 갱신했고, 나머지 초안 검토 메모는 보존했다.

> 2026-11-08 기관 가명화(ADR-079): 기관명 → `inst_NNN`, 기관 유형 칸 삭제, 원본 경로 → `references/samples/<kind>/<sha12>.pdf`, 다른 원 이름 3곳 → `○○어린이집`. 위 SHA는 가명화 뒤 값이다. record_id · 원문 · 연령 · 월 · 분류 판정은 그대로라 승인을 승계한다.

자료에는 승인 필드를 새로 만들지 않는다. corpus 관찰 자료의 비규범적 역할은 그대로이며, 사람의 개인정보 검토·제외 ID·사유·원본 SHA·파생 재현 정보는 `build`에 기록한다. 분류 4종의 승인은 각 `review` 필드에 기록하고, 기본 로더 경로와 놀이 월간 조립부의 판 상수를 함께 전환한다.

## 승인한 Golden 변경

문장·선택 ID가 같은 것은 아래 기존 가짜 LLM Golden 시나리오에 한정된다. 무료 12개월·5연령조합 검색 비교에서는 3월 5개 요청의 후보 일부가 바뀌었고, 이는 개인정보 제외에 따른 의도된 변화로 승인했다.

| Golden 파일 | 변경 수 | 범위 |
|---|---:|---|
| monthly_llm.json | 10 | source_version 9 + Context 지문 1 |
| cell_regeneration.json | 3 | source_version 2 + Context 지문 1 |
| cell_regeneration_goals.json | 3 | source_version 2 + Context 지문 1 |
| weekly_llm.json | 6 | source_version 6 |
| weekly_cell_regeneration.json | 2 | source_version 2 |

합계 **5개 파일·24필드(source_version 21 + Context 지문 3)**만 승인했다. 연간·월간 Rule·주간 Rule Golden은 변경하지 않았다. 이 밖의 Golden 값은 승인 대상이 아니다.

## 이번에 포함하지 않는 것

- 월간 미분류 5개 행 252개 기록은 별도 검토한다. 새 월간 분류는 기존 16개 판정만 가진다.
- 구판 자료·분류 파일과 기존 동결 SHA는 보존한다. 구판 제거와 git 이력 변경은 이번 작업이 아니다.
- 공개 API·DB·법정 기준·프롬프트 판·월/연령 필터·분류 의미는 바꾸지 않는다.
- 패턴 검사에서 남은 32개 일치는 모두 사람이 일반 활동으로 판정한 것이다. 개인정보 부재를 수학적으로 증명한 것은 아니다.

## 재현과 검증 범위

빌드에는 원본 파일·content SHA, 개인정보 판정 파일 SHA, 제외 ID·사유, 검토자·시각, 파생 스크립트와 helper SHA, Python 판, 직렬화 옵션·생성 시각을 기록했다. 실행 스크립트는 개인 보관이므로 제삼자가 실행 코드까지 갖춘 완전 재현이라고 말하지 않는다. 기록 보존 여부는 원본 SHA·제외 ID·남은 기록 해시로 대조할 수 있다.

`tests/evidence/test_evidence_store.py`는 제외 ID와 남은 기록 전체·출처 manifest의 동일성을 검증하며, `tests/finalization/test_freeze.py`는 신·구판 파일 SHA와 정체성을 함께 고정한다. 원문 개인정보가 assertion 출력에 섞이지 않도록 전체 기록 비교는 digest로 한다.
