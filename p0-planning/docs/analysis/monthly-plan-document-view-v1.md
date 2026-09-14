# Monthly Plan Document View v1

- **작업일:** 2026-09-14
- **성격:** Presentation Layer 전용
- **결과:** `MONTHLY_PLAN_DOCUMENT_VIEW_V1_COMPLETE`
- **회귀:** 2,404 passed · 4 deselected (착수 시점 2,359 → +45)
- **Planner v1:** `MONTHLY_PLAN_LLM_PLANNER_V1_FROZEN` 유지 — Domain / Rule / LLM /
  Retrieval / Validator / Provenance / Artifact / Golden 전부 불변

---

## 1. 한 일

저장된 `MonthlyPlan`을 어린이집 실무에서 익숙한 **A4 가로 문서**로 보여 주는
화면을 추가했다. 기존 편집 화면은 그대로 두고 옆에 모드를 하나 더 뒀다.

```text
[ 편집하기 ]  [ 문서 미리보기 ]            [ 인쇄 / PDF 저장 ]
```

**새 Plan을 만들지 않고 LLM을 다시 호출하지 않는다.** 두 화면 모두 이미 받아 둔
같은 state로 그려 놓고, 토글은 어느 쪽을 보일지만 정한다. 실제 브라우저에서
토글을 눌렀을 때 fetch 호출이 **0회**임을 확인했다(§8).

---

## 2. 추가·수정한 파일

| 파일 | 성격 | 변경 |
|---|---|---|
| `demo-planning/frontend/document_view.js` | 신규 | 문서 model 변환 + 렌더링 |
| `demo-planning/frontend/index.html` | 수정 | 모드 toggle · 문서 container · script |
| `demo-planning/frontend/app.js` | 수정 | `setMonthlyViewMode()` · 문서 렌더 연결 · 인쇄 |
| `demo-planning/frontend/styles.css` | 수정 | 문서 스타일 · `@page` · 문서 모드 print |
| `demo-planning/backend/views.py` | 수정 | `month_start` / `month_end` 2개 추가 |
| `demo-planning/backend/app.py` | 수정 | 정적 파일 `no-store` (§12.5) |
| `tests/dev/test_demo_document_view.py` | 신규 | 33 test |

Backend 변경은 **필드 2개**뿐이다(§5). Domain·Use Case·Rule·Validator·Adapter는
한 줄도 건드리지 않았다.

---

## 3. 문서 구조

```text
                         2026년 9월 월간계획안

반: demo_class_e2e    연령: 만 4세    기간: 2026.09.01 ~ 2026.09.30    기관: demo_daycare_001
생활주제: 우리나라와 세계 여러 나라

┌──────────┬────────────┬────────────┬────────────┬────────────┬────────────┐
│   구분   │   9월 1주  │   9월 2주  │   9월 3주  │   9월 4주  │   9월 5주  │
│          │  8/31~9/4  │  9/7~9/11  │ 9/14~9/18  │ 9/21~9/25  │ 9/28~10/2  │
├──────────┼────────────┼────────────┼────────────┼────────────┼────────────┤
│ 중심 경험│                          …                                     │
│ 바깥놀이 │                          …                                     │
│ 안전교육 │  미확정    │  미확정    │  미확정    │  미확정    │  미확정    │
└──────────┴────────────┴────────────┴────────────┴────────────┴────────────┘

안전교육은 배치 근거가 확정되지 않아 미확정으로 두었습니다.
쓱싹요정 Demo 출력물입니다. 제출용 공식 문서가 아닙니다.
```

생활주제는 표 안에서 매주 반복하지 않고 머리말에 한 번만 쓴다(§7).

---

## 4. 데이터는 전부 저장된 Plan에서 온다

문서가 스스로 만들어 내는 값이 하나도 없다.

| 문서 요소 | 출처 |
|---|---|
| 주차 목록 · 주차 날짜 | Domain의 canonical `WeekPeriod` |
| 행 구성 · 행 순서 | Backend view의 `rows` (활성 Section만, `ROW_DISPLAY_ORDER` 적용) |
| Cell 값 | 저장된 `MonthlyPlanItem.value` |
| 생활주제 | `theme` Cell |
| 기간 | Backend view의 `month_start` / `month_end` |

**주차 날짜를 Frontend가 계산하지 않는다는 증거가 실제 출력에 있다.** 9월 1주가
`8/31 ~ 9/4`이고 5주가 `9/28 ~ 10/2`다. 달 경계로 계산했다면 9/1과 9/30이 됐을
것이다. 첫 주가 전월에 시작하고 마지막 주가 다음 달에 끝나는 것은 OD-M02의
canonical week policy 그대로다.

---

## 5. Backend에 추가한 것 — 필드 2개

```python
"month_start": "2026-09-01",
"month_end":   "2026-09-30",
```

문서 머리말의 `기간` 한 줄에만 쓴다. **주차 날짜가 아니라 달의 경계**이며
`calendar.monthrange`로 구하는 달력 산술이라 Domain 결정이 아니다. Domain field를
추가하지 않았고 `MonthlyPlan`도 그대로다.

이 값을 Frontend에서 계산할 수도 있었지만, 날짜를 만드는 코드가 화면에 생기면
"주차 날짜도 화면이 만들지 모른다"는 여지가 남는다. View가 대신 계산해서 화면은
**받은 문자열을 찍기만** 하게 뒀다.

---

## 6. 안전교육 — 비어 있는 것을 비어 있다고 쓴다

현재 v1에서 안전교육은 배치 Source가 없어 `EMPTY_UNRESOLVED` /
`NOT_VERIFIED_SOURCE_REQUIRED`다.

문서에는 **미확정**으로 표시하고 각주를 단다.

```text
안전교육은 배치 근거가 확정되지 않아 미확정으로 두었습니다.
```

AI가 내용을 지어내지 않는다. `법적 기준 충족` · `안전교육 완료` 같은 주장도 하지
않는다. 편집 화면의 "근거가 없어 비워 두었습니다"와 **같은 의미**를 문서 문구로
줄인 것이며, 개발 용어(`EMPTY_UNRESOLVED`)는 문서에 나가지 않는다.

---

## 7. 공식 양식이라고 하지 않는다

`표준 월간계획안` · `정부 공식 양식` · `누리과정 공식 양식` · `법정 양식` 중
어느 표현도 쓰지 않았고, 테스트가 이를 감시한다.

문서 하단에 한 줄을 남겼다.

```text
쓱싹요정 Demo 출력물입니다. 제출용 공식 문서가 아닙니다.
```

인쇄하면 화면 상단의 `DEMO · 제출용 문서 아님` 배지가 사라지기 때문에, 종이에만
남는 표시가 필요했다. DRAFT 워터마크는 **넣지 않았다**(§24 기본값).

---

## 8. 실제 브라우저 확인

결정론 FakeLLM으로 Demo 서버를 띄우고(Composition Root의 `llm=` seam) Chrome
DevTools Protocol로 실제 페이지를 조작했다. 실제 API는 호출하지 않았다.

| 시점 | editor | document | 인쇄 버튼 | doc-mode | fetch 호출 |
|---|---|---|---|---|---|
| 최초 | 보임 | 숨김 | 숨김 | off | — |
| 문서 미리보기 클릭 | 숨김 | 보임 | 보임 | on | **0** |
| 편집하기 복귀 | 보임 | 숨김 | 숨김 | off | **0** |

문서 모드에서 확인한 값.

```text
제목            2026년 9월 월간계획안
열              6 (구분 + 5주)
행              중심 경험 · 바깥놀이 · 안전교육
편집 control    0  (button / input / textarea / contenteditable)
```

편집하기로 돌아오면 재생성 버튼 **10개**(중심 경험 5 + 바깥놀이 5)가 그대로
살아 있다.

### 8.1 인쇄 결과

실제 Demo 페이지를 문서 모드에서 인쇄했다.

```text
MediaBox   841.92 × 594.96 pt  =  297mm × 210mm  =  A4 landscape
Pages      1
```

추출한 텍스트에 남은 것은 문서 본문뿐이다 — topbar, 1~3단계, toggle, 인쇄 버튼,
DRAFT badge, 개발 정보가 모두 빠졌다. 4주(2026-06)와 5주(2026-07) 모두 1페이지에
들어간다.

### 8.2 화면 폭 — 발견하고 고친 것

첫 스크린샷에서 5주 중 4주까지만 보이고 잘렸다. 원인은 Demo 본문 칼럼이
`max-width: 940px`인데 A4 가로가 297mm(≈1122px)라는 것이었다.

종이를 칼럼에 맞춰 줄이면 화면과 인쇄 결과가 달라진다. 그래서 **종이가 아니라
레이아웃을 넓혔다.**

```css
body.doc-mode .layout { max-width: 1220px; }
```

여기서도 좁은 화면이면 `.docview`가 가로 스크롤한다. 모바일 때문에 문서를 카드로
쪼개지 않는다(§21).

---

## 9. 긴 문장

`focus` 문장이 길어도 자르지 않는다. `text-overflow: ellipsis`와
`-webkit-line-clamp`를 CSS 전체에서 쓰지 않으며, 문서 model이 원래 값과 글자 단위로
같은지 테스트가 확인한다. 문장 품질은 Planner 영역이고 문서는 있는 그대로
렌더링한다(§29).

---

## 10. 테스트 (45건)

두 축으로 나눴다.

**Python (항상 실행)** — Backend view가 문서에 필요한 값을 주는가, JS·CSS·HTML이
규칙을 지키는가.

**Node (node 없으면 skip)** — `document_view.js`의 순수 변환
`buildDocumentModel()`을 **실제로 실행**해서, 저장된 MonthlyPlan으로 만든 문서
model을 검사한다. Fixture 문자열이 아니라 Use Case가 만들어 Repository에 저장한
Plan을 쓴다.

확인하는 것.

```text
4주 / 5주    주차 수만큼 열이 생기고 모든 행이 그 수만큼 Cell을 가진다
Cell 위치    각 값이 자기 week_id의 칸에 들어간다 (밀림 없음)
행 순서      중심 경험 → 바깥놀이 → 안전교육
안전교육     전부 `미확정`, has_unresolved = true
내부 용어    focus · week_axis · DRAFT · RULE_LLM · INSTITUTION_SAMPLE ·
             packet_fingerprint 등이 model에 없다
비활성 섹션  goals · habits · emergency_response … 행을 만들지 않는다
없는 값      반·기관이 없으면 항목을 빼고 ○○반을 지어내지 않는다
연령         만 4세 / 만 3·4세 혼합
긴 문장      원래 값과 글자 단위로 동일, `…` 없음
Preview      문서 renderer에 input·textarea·contenteditable·addEventListener 없음
             fetch·/api/ 호출 없음
semantic     table / thead / tbody / th / td / colgroup, scope=col·row
toggle       setMonthlyViewMode에 post·fetch·/api 없음
인쇄         @page A4 landscape, 문서 모드에서 control 전부 숨김
             break-inside: avoid, 종이 폭 297mm 고정
편집 보존    monthlyConfirm · 재생성 버튼 조건이 그대로 있다
```

### 10.1 자기 수정 2건

처음 쓴 검사 두 개가 **자기 설명에 걸려** 실패했다.

`document_view.js`의 머리말에 "input·textarea·contenteditable을 만들지 않는다"고
적어 뒀는데, 그 문장이 "금지어가 들어 있다"로 읽혔다. 확인하려는 것은 코드가
무엇을 하는가이므로 주석을 제거한 뒤 검사하도록 고쳤다.

인쇄 버튼 handler를 400자로 잘라 봤더니 옆의 세션 초기화 handler까지 들어와
`post(`가 걸렸다. handler 하나만 잘라 보도록 범위를 좁혔다.

---

## 11. 하지 않은 것

```text
새 LLM Prompt / Retrieval / Activity Reference / Evidence Store
Planner v1 · Regenerate 변경
Template version 추가
goals · habits 등 Section 추가
PDF 생성 Backend · DOCX
공식 양식 주장 · Official Adapter
React / Next.js 도입 (기존 Vanilla JS 유지)
```

승인 Artifact SHA도 그대로다.

```text
monthly_template_a.json            1f35322dd52f832b…
monthly_template_a_v0_2_0.json     cb3fa9d15ea5ad55…
activity_reference_v0_2_1.json     ddbbe43f570cf64e…
institution_evidence_v0_1_0.json   8479c0490a002d93…
monthly_cases.json                 c605641232d91abd…
yearly_cases.json                  7918e9f9cbe23580…
```

---

## 12. Q&A (§38)

**Q1. 기존 Monthly Editor는 그대로 동작하는가?**
그렇다. 편집 화면 markup·handler를 건드리지 않고 `#monthlyEditorView`로 감싸기만
했다. 실제 브라우저에서 편집하기로 돌아왔을 때 재생성 버튼 10개가 살아 있음을
확인했다.

**Q2. 저장된 MonthlyPlan이 실제 문서형 Table로 렌더링되는가?**
그렇다. `<table>` / `<thead>` / `<tbody>` / `<th scope>` semantic markup을 쓰고,
값은 전부 Repository에 저장된 Plan에서 온다. Frontend fixture도 별도 샘플 문자열도
쓰지 않는다.

**Q3. 4주 / 5주가 모두 정상 표시되는가?**
그렇다. 2026-06(4주)·2026-07(5주)·2026-09(5주)를 확인했고, 주차 수를 어디에도
하드코딩하지 않는다. 인쇄도 두 경우 모두 1페이지다.

**Q4. focus / outdoor / safety가 정확한 Week에 들어가는가?**
그렇다. `week_id`로 맞춰 넣고, 저장된 Cell과 문서 Cell을 주차별로 대조하는
테스트가 있다.

**Q5. week_axis가 내용 행이 아니라 Header 역할만 하는가?**
그렇다. `week_axis`는 `rows`에 들어오지 않으며 열 Header로만 쓰인다.

**Q6. Document View에서 기술 용어가 노출되지 않는가?**
노출되지 않는다. `focus` · `DRAFT` · `RULE_LLM` · `LLM_PLANNER` ·
`INSTITUTION_SAMPLE` · `ACTIVITY_REFERENCE` · `packet_fingerprint` ·
`EMPTY_UNRESOLVED` 등이 문서 model에 없음을 테스트가 확인한다.

**Q7. inactive Section을 임의로 만들지 않았는가?**
만들지 않았다. Backend `rows`가 활성 Section만 주고 문서는 그것을 그대로 쓴다.
빈 행을 미리 만들지도 않는다.

**Q8. A4 landscape Print Preview가 정상인가?**
정상이다. 실제 인쇄 결과 MediaBox가 841.92 × 594.96 pt(= A4 landscape)이고
1페이지다.

**Q9. Print/PDF에서 UI control이 숨겨지는가?**
숨겨진다. 인쇄한 PDF에서 추출한 텍스트에 topbar·1~3단계·toggle·인쇄 버튼·DRAFT
badge·개발 정보가 하나도 없다.

**Q10. Planner v1 / Domain / Artifact / Golden은 전부 불변인가?**
전부 불변이다. `src/ssuksak/` 아래는 한 줄도 바뀌지 않았고, 승인 Artifact 6개와
Golden 2개의 SHA가 그대로이며, L9 freeze 회귀가 전부 통과한다.

---

## 12.5 Frontend Runtime Regression — 조사와 수정 (2026-09-14 후속)

사용자가 실행 중 두 오류를 보고했다.

```text
Demo 서버에 연결하지 못했습니다: TypeError: Cannot read properties of null (reading 'classList')
Demo 서버에 연결하지 못했습니다: TypeError: Cannot read properties of undefined (reading 'render')
```

**서버는 죽지 않았다.** 둘을 별개 증상으로 보지 않고 하나의 초기화/모듈/lifecycle
regression으로 조사했다.

### 12.5.1 무엇이 null이었고 무엇이 undefined였는가

캐시된 옛 `index.html`을 재구성해 실제 브라우저에서 receiver를 확정했다.

```text
document.getElementById("monthlyEditorView")    → null
document.getElementById("monthlyDocumentView")  → null
document.getElementById("printDocument")        → null
document.getElementById("tabDocument")          → null
globalThis.MonthlyDocument                      → undefined

.classList 시도 → "Cannot read properties of null (reading 'classList')"
.render  시도  → "Cannot read properties of undefined (reading 'render')"

document.scripts → ["app.js"]        ← document_view.js script 태그가 없다
```

보고된 두 문구가 **그대로 재현**됐다.

`.classList` receiver는 `show()`에 넘어온 노드이고, 그 중 Document View v1이
새로 추가한 것은 셋뿐이다 — `monthlyEditorView` · `monthlyDocumentView` ·
`printDocument`. 나머지(`busy` · `banner` · `stepYearly` · `stepMonthPick` ·
`stepMonthly`)는 이전부터 있던 id다.

`.render` receiver는 `documentRenderer()`가 돌려주는 `globalThis.MonthlyDocument`
하나뿐이며, 그 값은 `document_view.js`만 설정한다.

### 12.5.2 Case 판정

| 후보 | 판정 | 근거 |
|---|---|---|
| A. script 404 | **아니다** | `/document_view.js` → 200 `application/javascript` |
| B. load order | **아니다** | `document_view.js`가 `app.js`보다 먼저 |
| C. defer/async | **아니다** | 둘 다 없음 |
| D. module 혼용 | **아니다** | `export`/`import` 0건, 전부 일반 script |
| E. global 등록 누락 | **아니다** | `global.MonthlyDocument = {…}` (global = globalThis) |
| F. 이름 불일치 | **아니다** | 정의·사용 모두 `MonthlyDocument` |
| G. **stale cache** | **이것이다** | 옛 index.html + 새 app.js 조합에서 두 오류가 그대로 재현 |

**두 오류는 관련이 있다 — 원인이 하나다.** 캐시된 `index.html`에는 새 element도
새 script 태그도 없으므로 null과 undefined가 동시에 발생한다.

Demo 서버는 정적 파일에 캐시 헤더를 주지 않았고, 브라우저는 `Last-Modified`만
있는 응답을 heuristic freshness로 캐시한다. `index.html`은 캐시본을 쓰고 `app.js`는
새로 받는 조합이 그래서 만들어졌다.

### 12.5.3 Script dependency graph

```text
index.html
  ├─ <script src="document_view.js">   (defer/async/module 없음)
  │     └─ globalThis.MonthlyDocument = { UNRESOLVED_TEXT, buildDocumentModel, render }
  └─ <script src="app.js">
        └─ init()  ─ 전제 1: 필수 markup 확인   (missingMonthlyViewNodes)
                   ─ 전제 2: renderer 확인       (documentRenderer)
                   ─ handler binding
                   ─ setMonthlyViewMode("EDITOR")
                   ─ fetch /api/state → readJson → applySafely → renderMonthly
                                                                   └─ doc.render(...)
```

### 12.5.4 Lifecycle — 전후

```text
[before]
init → handler binding → setMonthlyViewMode("EDITOR")
                              └─ show($("monthlyEditorView"))  ← null이면 여기서 사망
     → fetch → apply → renderMonthly → globalThis.MonthlyDocument.render(...)
                                            └─ undefined면 여기서 사망
     → 두 예외 모두 fetch 체인의 .catch가 받아 "서버 연결 실패"로 표시

[after]
init → 전제 1 확인 (필수 markup)   없으면 무엇이 없는지 console.error + 사용자 안내
     → 전제 2 확인 (renderer)      없으면 console.error + 문서 탭 비활성 + 사유 tooltip
     → handler binding
     → setMonthlyViewMode("EDITOR")   MONTHLY_VIEW_READY가 false면 아무것도 만지지 않음
     → fetch ─ 거부      → "서버에 연결하지 못했습니다"
             ─ json 실패 → "서버 응답을 해석하지 못했습니다"
             ─ apply 실패 → "화면을 그리는 중 오류가 발생했습니다"
```

### 12.5.5 필수 DOM vs Optional DOM

모든 접근에 `?.`를 붙이는 대신 **전제를 한 번 명시적으로 확인**했다.

```text
필수    monthlyEditorView · monthlyDocumentView · tabEditor · tabDocument · printDocument
        → init에서 한 번 검사. 없으면 무엇이 없는지 말한다 (console.error + 배너)
        → show()는 null 가드를 두지 않는다. 숨기지 않기 위해서다

부가    globalThis.MonthlyDocument
        → 없으면 문서 탭만 비활성. 편집 기능은 그대로
```

`show()`에 `if (node)`를 넣었다가 되돌렸다. 그것이야말로 §6이 금지하는
"필수 DOM 누락을 optional chaining으로 숨기는" 패턴이었다.

### 12.5.6 Error UX — 3단계 분리

```text
Network   fetch 거부        → "Demo 서버에 연결하지 못했습니다: …"
HTTP      res.json() 실패   → "서버 응답을 해석하지 못했습니다."
Render    apply 실패        → "서버 응답은 받았지만 화면을 그리는 중 오류가
                               발생했습니다. … 강력 새로고침 해 보세요."
```

`post()`의 포괄 `.catch`를 없앴다. 그 catch가 셋을 하나로 뭉개던 자리다.
기술 stack trace는 `console.error`로만 남긴다.

### 12.5.7 Backend / Static asset 상태

```text
Backend          정상 — /api/state 200 application/json
document_view.js 200 application/javascript (index.html fallback 아님)
app.js           200 application/javascript
styles.css       200 text/css
Cache-Control    no-store, must-revalidate  (정적 파일, 신규)
```

근본 원인 대응으로 Demo Handler에 `end_headers`를 추가해 정적 파일을 캐시하지
않게 했다. 캐시 무효화 시스템을 새로 만들지는 않았다.

### 12.5.8 상태 행렬 — 실제 브라우저 검증

FakeLLM Demo 서버 + Chrome DevTools Protocol. 실제 API 호출 0.

| 상태 | 결과 | console error |
|---|---|---|
| Yearly 없음 / Monthly 없음 | PASS | 0 |
| Yearly DRAFT / Monthly 없음 | PASS | 0 |
| Yearly CONFIRMED / Monthly 없음 | PASS | 0 |
| Monthly DRAFT (5주) | PASS — 3행 · 재생성 10 · 열 6 | 0 |
| Editor → Document | PASS — API 호출 0 · 문서 내 control 0 | 0 |
| Document → Editor | PASS — API 호출 0 · 재생성 10 유지 | 0 |
| 재생성 후 재렌더 → Document | PASS — 새 값 반영, 새로고침 0회 | 0 |
| CONFIRMED | PASS — 확정 버튼 비활성 | 0 |
| CONFIRMED → Document | PASS | 0 |
| document_view.js 차단 | PASS — 문서 탭만 비활성, 편집 정상 | 0 |

재렌더 검증은 결정적으로 확인했다. 페이지 **새로고침 0회**로 편집 화면에서
2주차 중심 경험을 재생성한 뒤 문서로 넘어가면 그 칸만 새 값으로 바뀐다.

```text
재생성 전: ["1주차…", "2주차 중심 경험을 함께 나눠요.", "3주차…", "4주차…", "5주차…"]
재생성 후: ["1주차…", "재생성으로 다시 쓴 중심 경험입니다.", "3주차…", "4주차…", "5주차…"]
```

module 수준에 DOM을 캐싱한 곳이 없고(`$()`를 호출 시점에 조회), 문서는 매번
`clear(root)` 후 다시 만든다 — stale reference가 생길 구조가 아니다.

### 12.5.9 이 과정에서 내가 만든 버그

탭 비활성화 코드를 `init()`에 넣으려 했는데, 문자열 치환이 들여쓰기 때문에 먼저
매칭돼 **`renderMonthly`의 `if (!m)` 분기 안에** 들어갔다. 문법이 맞아
`node --check`를 통과했고, 첫 화면에서는 monthly가 없어 우연히 동작했다. 월간계획이
이미 있는 상태로 들어오면 영영 실행되지 않는 코드였다.

`init()`으로 옮기고 **위치까지 확인하는 테스트**를 추가한 뒤, 월간계획이 있는
상태로 정상·차단 두 경우를 다시 검증했다.

### 12.5.10 진단 중 만난 함정 — 서버 재시작이 먹지 않았다

상태 행렬을 돌리는 동안 "재시작한 서버가 옛 상태를 그대로 갖고 있는" 현상이
있었다. `ThreadingHTTPServer.allow_reuse_address = 1` 때문에 Windows에서 옛
프로세스가 포트를 쥔 채로 새 프로세스도 bind에 성공한다. `pkill`이 듣지 않아
PID로 죽인 뒤에야 진짜 새 서버가 떴다.

이것은 검증 환경 문제이며 제품 코드와 무관하다. 다만 §18 결과를 한 번 잘못 읽을
뻔했으므로 기록한다.

### 12.5.11 변경 파일

```text
demo-planning/frontend/app.js      필수 DOM 검사 · renderer 진단 · Error UX 3단계
demo-planning/backend/app.py       정적 파일 no-store
tests/dev/test_demo_document_view.py  회귀 테스트 16건 추가 (29 → 45)
```

`src/ssuksak/` · `data/` · `tests/golden/`은 변경 0이다.

---

## 13. 남은 것

- **반·기관 표시 이름이 없다.** Domain에 `classroom_ref` · `daycare_ref`라는
  opaque 식별자만 있어서 문서에 `demo_class_e2e`처럼 그대로 나온다. 지어내지 않는
  것이 맞지만 실제 문서로는 어색하다. 표시 이름 필드는 Profile Contract가 정해진
  뒤에 붙일 일이다.
- **display_group 병합 미지원.** `WeekPeriod.display_group`(두 주를 한 칸으로
  표시)은 Contract로만 열려 있고 Generate가 채우지 않는다. 채우기 시작하면 문서
  표에서도 열 병합을 다뤄야 한다.
- **DRAFT 워터마크 여부 미결정.** 기본은 넣지 않았다(§24).
- **`@page`가 전역이다.** `size: A4 landscape`를 scope 없이 선언해서 편집 화면을
  인쇄할 때도 가로가 된다. 월간 격자에는 맞지만 의도한 변경임을 남겨 둔다.

---

## 14. 결론

```text
MONTHLY_PLAN_DOCUMENT_VIEW_V1_COMPLETE
```
