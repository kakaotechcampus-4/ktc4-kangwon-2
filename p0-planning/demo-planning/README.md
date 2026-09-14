# Planning Integration Demo — 연간 → 월간

> **버려도 되는 코드입니다.** Production HTTP Adapter도 제품 Frontend도 아닙니다.
> `demo-planning/` 폴더를 통째로 지워도 기존 프로젝트의 동작과 테스트는 완전히
> 동일합니다.

브라우저에서 조건을 입력하고 버튼을 눌러 **실제 Planning Core**를 실행합니다.

```
조건 입력 → Yearly Generate(실제 LLM) → Yearly 표 → Yearly Confirm
        → 대상 월 선택 → Monthly Generate → Monthly 표 → Monthly Confirm
```

fixture도 mock도 없습니다. 버튼 하나하나가 실제 Use Case를 호출합니다.

## 실행

추가 패키지 설치가 필요 없습니다. 표준 라이브러리 `http.server`만 씁니다.

```bash
python demo-planning/backend/app.py
#   → http://127.0.0.1:8800/

python demo-planning/backend/app.py --port 8801   # 포트 변경
```

한 명령으로 Demo API와 정적 Frontend를 함께 띄웁니다.

## 실제 LLM

`연간계획 생성`은 **실제 `GenerateYearlyPlan(use_llm=True)`** 경로를 실행하며,
기존 프로젝트의 Elice MLAPI Adapter와 환경변수 설정을 그대로 재사용합니다.

- FakeLLM · mock · fixture · canned fallback이 **없습니다**
- 호출이 실패하면 가짜 결과로 대체하지 않고 **실제 오류를 화면에 표시**합니다
- API Key와 Prompt 전문은 응답·로그·화면 어디에도 싣지 않습니다
  (telemetry는 provider / model / token 수 / latency / 성공 여부만 기록)

필요한 환경변수(값이 아니라 이름만 적습니다):

```
ELICE_MLAPI_BASE_URL
ELICE_MLAPI_API_KEY
LLM_MODEL
```

프로젝트 루트 `.env` 또는 OS 환경변수에서 읽습니다. 설정이 없거나 잘못되면
Demo는 뜨되 `연간계획 생성` 시 실제 오류를 그대로 보여 줍니다.

Monthly는 현재 Contract대로 **LLM 호출 0회**입니다. Use Case가 LLMPort를 받지
않으므로 구조적으로 0입니다.

### `--yearly-rule-only` (개발용 스위치)

```bash
python demo-planning/backend/app.py --yearly-rule-only
```

Yearly를 Rule 전용 경로(`use_llm=False`)로 실행합니다. **실패했을 때 자동으로
전환되는 fallback이 아닙니다** — 운영자가 직접 켜야만 동작하고, 켜져 있으면
서버 배너와 화면 상단 배지에 그대로 표시됩니다. API Key가 만료되었거나 비용을
쓰고 싶지 않을 때 Yearly → Monthly 연결 자체를 확인하는 용도입니다.

이 플래그가 꺼져 있으면(기본값) LLM 실패는 언제나 실제 오류로 표시됩니다.

## 구성

```
demo-planning/
├── backend/
│   ├── app.py            HTTP 경계 + 세션. Business Logic 없음
│   ├── composition.py    실제 Use Case 조립만
│   └── views.py          Domain → 화면용 JSON
├── frontend/
│   ├── index.html        4단계 화면 1장
│   ├── app.js            렌더링. 의존성 0개
│   └── styles.css
├── tools/
│   └── smoke_flow.py     브라우저 없이 전체 흐름 점검
└── README.md
```

### Backend가 하는 일

Business Logic을 새로 구현하지 않습니다. Production 코드를 복사하지도 않습니다.

- **Yearly 절반**은 Production dev Composition `ssuksak.dev.wiring.build_wiring()`을
  그대로 씁니다.
- **Monthly 절반**은 Production Adapter와 Use Case를 조립하되, Yearly와 **같은**
  `InMemoryPlanRepository`에 붙입니다. `build_monthly_wiring()`은 자기 Yearly
  Repository를 따로 만들고 Parent Plan까지 스스로 생성하므로, 화면에서 직접 만든
  Yearly를 Parent로 쓰려면 여기서 조립해야 합니다.
- Catalog / Template / Safety Rule 버전은 하드코딩하지 않고 Production의 selector
  reader로 승인 파일에서 읽습니다.

Gate·Validation·선택 규칙은 전부 Production Rule이 판정합니다. Front는 status를
바꾸거나 Gate를 흉내 내지 않습니다. 월간 생성 버튼의 disabled는 편의 표시일 뿐이고,
눌러도 Backend의 실제 Gate가 다시 판정합니다.

### API

| 경로 | 실제 Use Case |
|---|---|
| `POST /api/yearly/generate` | `GenerateYearlyPlan` |
| `POST /api/yearly/confirm` | `ConfirmYearlyPlan` |
| `POST /api/yearly/edit` | `EditYearlyPlanItem` |
| `POST /api/yearly/regenerate` | `RegenerateYearlyPlanItem` |
| `POST /api/monthly/generate` | `GenerateMonthlyPlan` |
| `POST /api/monthly/confirm` | `ConfirmMonthlyPlan` |
| `POST /api/monthly/edit` | `EditMonthlyPlanItem` |
| `POST /api/monthly/regenerate` | `RegenerateMonthlyPlanItem` |
| `GET /api/state` · `POST /api/session/reset` | 세션 조회 / 초기화 |

Gate·Validation 실패는 HTTP 409에 `PlanningError`의 `outcome` /
`failure_category` / `violated_rule` / `detail`을 그대로 실어 보냅니다. 화면은
그 내용을 문구를 새로 만들지 않고 표시합니다.

## Persistence

InMemory입니다. 프로세스가 죽으면 사라집니다. DB도 마이그레이션도 없습니다.
`세션 초기화` 버튼이 새 세션을 만듭니다.

## 화면

| 단계 | 내용 |
|---|---|
| 1 조건 입력 | 학년도 · 연령 구성 · 연령 · 원 · 반 |
| 2 연간계획안 | 3월~2월 12행 문서 표 · DRAFT/CONFIRMED Badge · 확정 버튼 |
| 3 월간계획 생성 | Gate 상태 안내 · 대상 월 선택 |
| 4 월간보육계획안 | 주차 열(4주/5주 자동) · 바깥놀이 / 안전교육 행 · 확정 버튼 |

`개발 정보 보기`를 켜면 Theme Reference · Activity Reference · `activity_id` ·
catalog version · `rule_id`/`rule_version` · Selection Trace · 실제 LLM 호출
기록(토큰/latency)이 나타납니다. 꺼 두면 교사용 문서 화면만 보입니다.

Cell 상태는 색과 문구로 구분합니다 — 작성됨(흰색) / 비워 두는 것이 정상(회색) /
근거가 없어 비워 둠(연한 경고). 개발자용 enum은 hover(`title`)와 개발 정보에만
나옵니다.

확정(CONFIRMED)은 작성 결과를 확정했다는 뜻이며 법정 안전교육 검증 완료를
의미하지 않는다는 안내를 확정 버튼 옆에 표시합니다.

## 점검

서버를 띄운 뒤 다른 창에서:

```bash
python demo-planning/tools/smoke_flow.py --port 8800
```

화면과 같은 경로를 순서대로 호출해 Yearly 생성 → DRAFT Gate 차단 → Confirm →
Monthly 생성 → Monthly Confirm → CONFIRMED read-only 차단까지 확인합니다.
결과를 만들어 내지 않고 서버 응답을 그대로 보고합니다.

## 하지 않은 것

npm build · 프레임워크 · 상태관리 · 라우팅 · 인증 · DB · Production 코드 수정 —
전부 없습니다.
