# Monthly 임시 시각화 Demo

> **버려도 되는 코드입니다.** Production Frontend가 아니고, 제품 디자인도 아니며,
> 실제 제출용 문서를 만들지도 않습니다. `demo-frontend/` 폴더를 통째로 지워도
> 기존 프로젝트의 동작과 테스트는 완전히 동일합니다.

`MonthlyPlan` 생성 결과를 교사가 보는 월간보육계획안 표처럼 브라우저에서
확인하기 위한 화면입니다.

## 실행

빌드도 설치도 필요 없습니다. 둘 중 아무 방법이나 씁니다.

```bash
# 1) 파일을 그대로 열기 (권장 — fetch를 쓰지 않으므로 file:// 에서도 동작한다)
start demo-frontend/index.html        # Windows
open  demo-frontend/index.html        # macOS

# 2) 정적 서버로 열기
python -m http.server 8000 --directory demo-frontend
#   → http://localhost:8000/
```

## 구성

```
demo-frontend/
├── index.html                    화면 1장. 표 구조와 범례
├── styles.css                    A4 문서풍 스타일 + 인쇄 CSS
├── app.js                        렌더링. 의존성 0개
├── fixtures/                     정적 스냅샷 (자동 생성물)
│   ├── monthly_2026_09_age4.js        2026-09 · 만4세 · DRAFT (5주)
│   ├── monthly_2026_09_confirmed.js   같은 Plan의 CONFIRMED
│   ├── monthly_2026_09_no_activity.js Activity Reference 미연결 (EMPTY_VALID)
│   └── monthly_2026_03_age4.js        2026-03 · 만4세 · DRAFT (4주)
├── tools/
│   ├── export_fixtures.py        fixture 생성기 (일회성, 화면과 무관)
│   └── check_render.js           브라우저 없이 렌더링 결과 점검
└── README.md
```

## 데이터 출처

화면은 **Backend를 호출하지도 import하지도 않습니다.** `fixtures/*.js`가
`window.SSUKSAK_DEMO_FIXTURES`에 넣어 둔 정적 스냅샷만 읽습니다.

그 스냅샷이 어디서 왔는지는 재현 가능합니다.

```bash
python demo-frontend/tools/export_fixtures.py
```

이 생성기는 실제 Composition(`build_monthly_wiring`)을 **읽기 전용으로** 실행해
결과를 JSON으로 덤프합니다. Production 코드를 수정하지 않고, LLM·네트워크를
사용하지 않습니다. 출력 구조는 Demo 표시용 view model이며 **Backend Contract가
아닙니다** — Backend DTO가 바뀌어도 이 생성기만 고치면 됩니다.

화면 상단에는 항상 `FIXTURE` 배너가 표시됩니다.

## 점검

```bash
node demo-frontend/tools/check_render.js
```

브라우저 없이 4개 fixture의 열 수(4주/5주), 셀 상태 분포, 값, Badge, 근거 토글을
확인합니다. `pytest`와 무관하며 프로젝트 테스트에 포함되지 않습니다.

## 화면 기능

| 기능 | 비고 |
|---|---|
| Monthly Plan 표 보기 | 행 = Section, 열 = 주차 |
| 4주 / 5주 자동 대응 | 주차 수를 고정하지 않고 `weeks` 길이로 렌더링 |
| DRAFT / CONFIRMED Badge | 상단 상태 칸 |
| Cell 상태 구분 | FILLED / EMPTY_VALID / EMPTY_UNRESOLVED |
| Activity provenance 보기 | 상단 체크박스로 토글. activity_id · catalog version · rule_id |
| 인쇄 미리보기 | `@page size: A4` + 도구 막대 숨김 |

`Edit` / `Regenerate` / `Confirm` 버튼은 만들지 않았습니다. 이번 Demo의 목적은
결과를 보여주는 것입니다.

## 셀 상태 표현

| 상태 | 표현 |
|---|---|
| `FILLED` | 흰 배경. 값 그대로 |
| `EMPTY_VALID` | 회색 배경 + "채울 근거가 없는 것이 정상" 주석 |
| `EMPTY_UNRESOLVED` | 연한 경고 배경 + "미검증 — 채워야 하는데 배치 source가 없음" |

인쇄 시 배경색이 꺼지는 브라우저 설정을 고려해 `EMPTY_UNRESOLVED`에는 테두리도
같이 줍니다.

확정(CONFIRMED)은 교사가 작성 결과를 확정했다는 뜻이며 **법정 안전교육 충족을
뜻하지 않습니다.** 화면 범례에도 같은 문구를 남겨 두었습니다.

## 하지 않은 것

프레임워크 · 빌드 도구 · 패키지 의존성 · 상태관리 · 라우팅 · 인증 · DB ·
Backend 변경 · 기존 Frontend 변경 — 전부 없습니다.
