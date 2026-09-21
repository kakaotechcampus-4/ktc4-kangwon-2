# frontend

Next.js 16 (App Router) · TypeScript · Tailwind

아래는 **어기면 사고가 나거나 리뷰에서 반드시 걸리는 것**만 적었다.
디렉터리 규칙은 [../docs/structure.md](../docs/structure.md), 화면 명세는 [../docs/PRD.md](../docs/PRD.md),
API 계약은 [../docs/api-spec.md](../docs/api-spec.md).

---

## 계약을 다시 정의하지 않는다

- **API 모양은 `docs/api-spec.md` 가 정한다.** 화면에 필요한 게 없으면 스펙을 고치는 PR 을 먼저 올린다.
  화면 쪽에서 임의로 엔드포인트를 만들지 않는다.
- **MSW 목업도 그 계약대로 만든다.** 목업이 계약과 다르면 연동 시점에 한꺼번에 터진다.
- 스펙의 **`UI states` 4개를 다 만든다** — `loading` · `empty` · `success` · `error`.
  서버가 알려주는 상태를 화면이 안 그리면 교사는 멈춘 화면만 본다.

---

## 조건 분기

**「없을 때」는 먼저 빠져나간다.** JSX 안에서 삼항연산자로 가르지 않는다.

```tsx
// ✗ 화면 코드 한가운데에 갈림길이 생긴다
{!records.length ? <Empty … /> : <div>… 30줄 …</div>}

// ✓ 없을 때를 먼저 끝내고, 아래는 "있다"만 생각한다
if (!records.length) return <Empty … />;
return <div>… </div>;
```

**JSX 안의 삼항연산자는 한 줄짜리만.** 두 갈래가 각각 여러 줄이면 함수를 나눈다.

---

## 파일 크기

**줄 수 상한을 두지 않는다.** 아래에 걸리면 쪼갠다.

```
같은 JSX 덩어리가 map 안에서 20줄 넘게 반복된다      → 컴포넌트로
onClick · onChange 안에 5줄 넘는 로직이 있다         → 이름 붙인 함수로
한 파일에서 화면 3개 이상을 그린다                    → 파일 분리
```

**「몇 줄이라서」가 아니라 「한꺼번에 여러 가지를 읽어야 해서」 쪼갠다.**

```tsx
// ✗ 버튼 하나에 무슨 일이 일어나는지 10줄이 박혀 있다
<button onClick={() => { setEditId(r.id); setClassId(r.classId); … }}>

// ✓ 이름이 설명한다
<button onClick={() => startEdit(r)}>
```

**컴포넌트를 빼기 전에 핸들러부터 뺀다.** 순서가 반대면 부모의 `setState` 를 전부
prop 으로 넘겨야 해서, 자식이 부모 폼의 속사정을 알게 된다. 핸들러를 먼저 빼면
자식은 `onEdit` 하나만 받는다.

**기존 파일은 그 파일을 다른 이유로 열 때 같이 정리한다.** 정리만을 위해 열지 않는다.

**새 파일로 뺄지, 같은 파일 안 함수로 둘지** — 두 번째 사용처가 생길 때 파일로 뺀다.
`docs/structure.md` 의 `shared` 기준과 같다.

---

## React

- **`useEffect` 안에서 `setState` 를 바로 부르지 않는다.** 첫 렌더 직후 다시 렌더된다.
  초기값이 필요하면 `useState(() => …)` 로 한 번만 계산한다.
  React 19 에서 `react-hooks/set-state-in-effect` 가 에러로 격상됐다.
- **렌더 중에 `ref.current` 를 읽지 않는다.** 값이 바뀌어도 다시 안 그려진다.
  다시 그려져야 하는 값은 `useState` 로 둔다.
- **`children` 을 prop 이름으로 쓰지 않는다.** 여는 태그와 닫는 태그 사이에 넣는다.

---

## 서버 컴포넌트 · 클라이언트 컴포넌트

- **App Router 의 기본은 서버 컴포넌트다.** `useState` · `useEffect` · `onClick` 을 쓰면
  파일 맨 위에 `"use client"` 를 적는다.
- **MSW 는 브라우저에서만 돈다.** 서버 컴포넌트에서 `fetch` 하면 목업을 못 가로챈다.
  목업으로 데이터를 받는 화면은 클라이언트 컴포넌트여야 한다.

---

## 라우팅

- **한 주소를 두 파일이 갖지 않는다.** `(app)` 처럼 괄호가 붙은 폴더는 주소에 들어가지
  않는다. `app/page.tsx` 와 `app/(app)/page.tsx` 는 둘 다 `/` 다. Next 가 빌드를
  막지 않고 하나만 남기므로, 안 쓰이는 쪽이 조용히 죽는다.
- **리다이렉트로 되돌려 보내지 않는다.** `A → B`, `B → A` 를 두 파일에 나눠 적으면
  화면이 안 나오는데 에러도 안 난다.
- **로그인·온보딩 판정은 `(app)/layout.tsx` 의 `DemoSessionGate` 가 한다.** 개별
  페이지에서 같은 검사를 다시 하지 않는다.

---

## 서버 라우트 (`app/api/`)

- **같은 사이트에서 온 요청인지 먼저 본다.** `lib/workspace/api-validation.ts` 의
  `sameOriginGuard(request)` 를 쓴다. 직접 비교하지 않는다.
- **`Origin` 이 없으면 막는다.** 브라우저만 이 헤더를 붙인다 — curl · 스크립트 ·
  다른 서버는 안 붙인다. "없으면 통과"로 두면 검사가 사실상 없는 것과 같다.
- **`request.url` 을 기준으로 삼지 않는다.** Next 가 `--hostname` 이 IP 여도
  `localhost` 로 채울 때가 있어서 같은 사이트 요청까지 막힌다. `Host` 헤더와 비교한다.

---

## 브라우저 저장

- **아동 실명을 `localStorage` · `sessionStorage` 에 넣지 않는다.** (ADR-013)
  목업의 가명 데이터는 예외. 연동 시점에 서버로 옮긴다.
- 저장해도 되는 것 — 화면 설정, 접은 상태, 임시 입력값. **사람을 식별하지 않는 것만.**

---

## 폰트

- **한글 폰트를 한 파일로 넣지 않는다.** 한글 11,172자가 2MB 다. 유니코드 구간별로
  나눈 dynamic subset 을 쓴다.
- **`next/font/local` 은 `src` 별 `unicode-range` 를 못 준다.** 그래서 한글 폰트는
  `styles/*-dynamic-subset.css` 가 `@font-face` 와 CSS 변수를 직접 정의한다.
  `lib/fonts.ts` 에는 라틴 전용 폰트만 둔다.
- **웹에 올리는 폰트는 woff2 다.** ttf · otf 는 압축이 없다.

---

## 파일 이름

```
components/    PascalCase.tsx     RecordsPage.tsx · AgeSelection.tsx
lib/           camelCase.ts       ageAdapter.ts · settings.ts
app/           Next.js 규약        page.tsx · layout.tsx · route.ts
```

---

## 명령어

```bash
cd frontend
npm run dev                  # 개발 서버
npm run lint                 # eslint
npm run format:check         # prettier
npm test                     # node --test
npm run build                # next build

# PR 올리기 전에 넷을 다 돌린다
npm run lint && npm run format:check && npm test && npm run build
```

**통합 테스트는 `SAESSAK_TEST_URL` 이 있을 때만 돈다.** 없으면 조용히 건너뛴다.
CI 는 빌드 결과를 띄우고 이 값을 넣어서 돌린다 — **로컬에서 통과해도 CI 에서 떨어질 수 있다.**
서버 쪽을 만졌으면 직접 띄워서 돌려본다.

```bash
npm run build && npm run start -- --hostname 127.0.0.1 --port 3000 &
SAESSAK_TEST_URL=http://127.0.0.1:3000 npm test
```

## 쓰지 않는 명령

```
node --test tests/     폴더를 인자로 주면 실패한다.  인자 없이 node --test 로 쓴다
npm install            npm ci 를 쓴다.  lock 과 어긋나면 CI 와 결과가 달라진다
```
