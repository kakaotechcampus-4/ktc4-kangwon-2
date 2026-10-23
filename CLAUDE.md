# ktc4-kangwon-2

**쌤플 · Ssample** — 어린이집 교사의 보육 문서 초안을 만드는 AI. 만 3~5세 유아반 담임교사 대상.
카카오테크 캠퍼스 4기 2단계 팀 프로젝트 — 강원대 2팀
운영 <https://ssample.duckdns.org>

> 코드 안의 `ssuksak` 패키지 이름은 옛 이름(쓱싹요정)이다. **바꾸지 않는다** — import 경로가
> 전부 딸려 온다. 사람이 읽는 글에만 「쌤플」을 쓴다.

아래는 **어기면 사고가 나는 것**만 적었다.

| 찾는 것 | 어디 |
|---|---|
| 무엇을 만드나 | [docs/요구사항명세서.md](docs/요구사항명세서.md) — FR · NFR · 진행도 |
| 누가 쓰나 | [docs/페르소나.md](docs/페르소나.md) |
| 이번 주 범위 | [docs/PRD.md](docs/PRD.md) §6 |
| 화면이 어떻게 도나 | [docs/screen-spec.md](docs/screen-spec.md) — 일지 S-J1~7 · 계획안 S1~11 |
| 서버와 무슨 약속을 했나 | [docs/api-spec.md](docs/api-spec.md) |
| 아직 안 정한 것 | [docs/미확정사항.md](docs/미확정사항.md) |
| 왜 이렇게 했나 | [docs/adr/](docs/adr/) |
| 디렉터리 · 브랜치 | [docs/structure.md](docs/structure.md) · [docs/branch-strategy.md](docs/branch-strategy.md) |

**`p0-planning/` 안에는 더 좁은 규칙이 따로 있다** — [p0-planning/CLAUDE.md](p0-planning/CLAUDE.md).
`p0-planning/` 안에서는 거기 적힌 것이 이 파일보다 우선한다. 그 밖에서는 이 파일이 팀 공통 규칙이다.

**문서끼리 다르면 이 순서로 따른다** — `ADR > api-spec > 요구사항명세서 > screen-spec`. 같은 단계면 늦은 결정이 이긴다.
저장소 밖 문서(개인 문서 · 브랜치에만 있는 문서)는 근거로 인용하지 않는다. [ADR-031](docs/adr/031-document-roles-and-conflict-order.md)

---

## 일하는 방식

**① 짐작하지 말고 묻는다.** 요청이 두 가지로 읽히면 둘 다 적어 되묻는다.
말없이 하나를 고르고 진행하면, 틀렸을 때 어디서 갈렸는지 아무도 못 찾는다.

**② 적게 만든다.** 시킨 문제만 푼다. 나중에 쓸 것 같은 추상화·설정값·인터페이스를 미리 두지 않는다.
구현이 하나뿐인 인터페이스는 인터페이스가 아니다.

**③ 건드린 것만 건드린다.** 주변 코드를 「고쳐 두지」 않는다. 기존 문체와 이름을 따른다.
리뷰어가 diff 에서 본론을 찾을 수 있어야 한다.

**④ 「됐다」를 눈으로 확인한다.** 끝내기 전에 **무엇이 참이면 끝인지**를 먼저 적고 그걸 확인한다.
「구현했다」가 아니라 「돌아간다」다 — PRD 의 완료 조건을 그렇게 쓰는 이유와 같다.

---

## 브랜치

- 기능 개발은 `develop`에서 `feature/*` → `develop` PR.
- 멘토 피드백 반영은 `develop`에서 `refactor/*` → `develop` PR. `feature/*`에 이어서 하지 않는다.
- `main`·`develop`에 직접 커밋·push 하지 않는다. 변경은 항상 PR로만.
- `develop` → `main` PR은 멘토 리뷰 요청이다. base가 `main`인지 확인한다.
- `main` 머지는 팀장(PM)만.
- `.github/` 중 `assign-mentor.yml` · `notify-discord.yml` · `convention-check.yml` · `CODEOWNERS`는 수정·삭제하지 않는다. **지우면 멘토 배정과 알림이 죽는다.**

---

## 결정을 남긴다

**되돌리기 어려운 결정을 하면 `docs/adr/` 에 파일 하나를 쓴다.**
스택 선택 · 폴더 구조 · 데이터 모델 · 외부 의존 추가 · 기능 스펙아웃이 해당한다.

형식과 근거 라벨은 [docs/adr/README.md](docs/adr/README.md).
코드에는 결과만 남고 대안과 근거는 사라진다. 3주 뒤에 "이거 왜 이렇게 했지"를 묻는 사람은 우리 자신이다.

---

## 문서 5분류 — AI 개입 한계가 다르다

새 기능을 붙일 때 먼저 어느 분류인지 정한다.

| 분류 | 예 | AI 역할 |
|---|---|---|
| 계획형 | 연간·월간·주간 계획안 | 초안 생성 안전. 미래 예정이라 위조가 성립 안 함 |
| 해석형 | 관찰일지 · 보육일지 | 교사가 준 사실을 **해석·서술만** |
| 대조형 | 평가제 자체점검 | 누락 **탐지만** |
| 추적형 | 법정교육 이수기록 | **LLM 불필요.** 카운터·날짜 계산 |
| 사실기록형 | 알림장 · 사고보고서 · 투약의뢰서 | **AI가 쓰면 위조.** 손대지 않는다 |

**사실기록형에 생성 기능을 붙이지 않는다.** 식사·배변·수면·투약은 사실이고, 없는 사실을 쓰면 문서 조작이다.

## 3층 규격 — 해석형 문서의 통과 조건

```
① 사실   교사가 입력한 관찰 사실. AI가 추가 못 함
② 해석   ①에 있는 사실만 근거로
③ 지원   다음에 어떻게 지원할지
```

- **②가 ①에 없는 사실을 쓰면 반려.**
- **③이 비면 반려.**
- 검사는 `shared/gates`에서만. 기능별로 따로 만들지 않는다.

## 3단 게이트 — 순서 고정

```
1  스키마 게이트   출력 형식 강제. 칸 이름·개수 불일치면 반려
2  추출 대조      고유명사·수량·날짜를 원문과 문자열 비교. 모델 안 부름
3  LLM Judge      ①②③ 관계 검사
```

**2단을 건너뛰지 않는다.** 비용 0인데 숫자·이름 오류를 가장 많이 잡는다.
3단을 1단보다 먼저 돌리지 않는다. 형식이 깨진 출력을 Judge에 넣으면 비용만 나간다.

---

## 생성

- 결과는 `DRAFT`로 저장. 교사가 확정 버튼을 눌러야 `CONFIRMED`.
- **확정은 층마다 순차 게이트.** 연간이 `CONFIRMED`가 아니면 월간을, 월간이 `CONFIRMED`가 아니면 주간을 생성하지 않는다.
  **주간은 월간을 거쳐서만 만든다** — 연간에서 주간으로 바로 가는 길이 없다(ADR-030 PM-04).
- **계획안에는 확정 취소가 없다**(ADR-030 PM-03). 확정 취소는 일지(`/api/documents`)에만 있다.
- 자동 제출·자동 발송을 만들지 않는다.
- **출처를 칸 단위로 기록한다. 세 축을 한 값에 섞지 않는다** (PR #15 Planning Core).

```
Evidence     이 값이 어디서 왔나     CURRICULUM · THEME_REFERENCE · PARENT_PLAN
                                   DAYCARE_PROFILE · CLASSROOM_PROFILE · EVENT
                                   SAFETY_RULE · ACTIVITY_REFERENCE · INSTITUTION_SAMPLE
                                   CALENDAR · TREND · EXTERNAL_CONTEXT          (12개가 전부)
Generation   어떻게 만들어졌나       RULE_ONLY · RULE_LLM · IMPORTED · MANUAL     (쓰는 값은 4개)
Audit        나중에 무슨 일이 있었나  CREATED · REGENERATED · TEACHER_EDITED · CONFIRMED
```

  **상위 계획안을 근거로 썼으면 `PARENT_PLAN` Evidence 를 따로 적는다.** 상위 계획안 스냅샷
  (Parent Lineage)은 **네 번째 축이 아니다** — 그건 바뀌지 않는 사본이고, 근거는 근거다.

  **「AI」는 출처가 아니라 제조 방법이다.** 교사가 근거를 눌렀을 때 "AI 가 만들었습니다"는
  판단에 도움이 안 된다. AI 가 만든 값도 근거는 누리과정·주제·상위 계획안이다.
  **`AI` · `TEACHER_EDIT` 은 Evidence 가 아니다.** LLM 을 썼는지는 Generation 으로 적는다.

  **교사가 고쳐도 Evidence 와 Generation(`rule_id` · `rule_version` 포함)을 그대로 둔다.** `TEACHER_EDITED`
  **Audit 이벤트**를 하나 더한다(값 변화와 행위자를 담는다). 「이 값이 교사가 고친 것인가」는 Generation 이 아니라
  **Audit 이력을 보고 판단한다** — 되돌리기와 평가제 집계가 거기서 나온다. 교사가 고쳤다고 `MANUAL` 로 바꾸지 않는다 —
  **`MANUAL` 은 사람이 처음부터 쓴 칸**이다.
  `GenerationMethod.TEACHER_EDIT` enum 값은 남아 있지만 **운영 코드가 쓰지 않는다**
  (2026-09-26 Human Decision · 제거 여부는 미정). 새 코드에서 그 값을 쓰지 않는다.

  **`RULE_LLM` 은 LLM 경로로 설계된 칸이다.** mock 생성기를 썼는지는 Generation 이 아니라 실행 기록(설정 · 호출 로그)으로
  안다. 재생성하면 Generation 을 새 방식으로 바꾸고, 이전 값 · 방식은 `REGENERATED` 이벤트에 남는다(ADR-032).
- **부가 의존을 빼고 만들었으면 그 사실이 남아야 한다.** 트렌드 · 날씨 같은 선택 입력이 실패해 기본 자료로 만들었으면
  생성 기록(Generation Run)에서 확인할 수 있어야 한다.
- **출처 표시는 화면에만.** hwp 내보내기에 마커가 섞이면 안 된다. 제출 문서다.
- **Rule 이 범위를 정하고, LLM 이 그 안에서 정하고, Rule 이 검사한다** — 연간 · 월간 · 주간 공통(ADR-032).
  ```
  Rule   허용 범위   승인된 후보 · 근거 · 제약 · 칸 구조 · 법정 기준
  LLM    범위 안에서  값의 의미 내용을 고르고 구성하고 쓴다
  Rule   검사        계약 · 근거 · 연령 · 법정 기준을 어겼는지
  ```
  LLM 은 문장만 다듬는 역할이 아니고, 범위 밖(승인 목록에 없는 id · 근거 없는 사실 · 법정 기준 · 통과 여부)은 정하지 않는다.
  법정 시수처럼 틀리면 안 되는 값은 규칙 엔진이 원문과 대조한다. **ADR-014 가 ADR-005 를 대체하고, ADR-032 가 ADR-014 를 보충한다.**
  ADR-005 의 「배치·선별은 규칙 엔진, LLM 은 문장화만」은 더 이상 유효하지 않다.
  **ADR-003 의 「P0a 는 결정론적이라 golden set 이 성립한다」도 같이 깨졌다** — 분할 자체는 유효하고 결정론 전제만 무효다.
  **대체 검증은 가짜 LLM 위의 Golden 이다**(ADR-023 「CI 는 가짜 LLM 으로 돈다」). 고정한 응답에 대해 Application 이 무엇을 하는지를
  고정하고(`p0-planning/tests/finalization/golden/`), 모델이 쓰는 문장은 기대값으로 굳히지 않는다. 문장 품질은 사람이 보는 실측 점검이 다룬다.
- **부가 기능이 죽어도 본 기능은 돌아간다.** 트렌드봇·외부 API를 필수 의존으로 넣지 않는다.

---

## 개인정보 — P1부터 적용

계획안(P0)은 반 단위 문서라 아동 이름이 들어가지 않는다. 상세는 ADR-004.

- 아동 실명을 **DB에 저장한다.**
- **동의서를 우리가 받지 않는다.** 원이 보호자에게 받고, 우리는 확인 문구만 띄운다. 파일 업로드를 만들지 않는다.
- **LLM 호출 직전에 아동 코드로 치환한다.** 프롬프트·응답·로그에 실명이 남으면 안 된다.
- 치환은 `shared/childCode` 한 곳에서만.
- **치환 실패 시 호출하지 않고 에러를 낸다.**
- 치환 토큰은 **받침 있는 더미 한글 이름.** 영문 토큰이면 조사가 복원 후 틀어진다.
- 아동 명단 입력칸은 **확인 문구 체크박스 뒤에서만** 활성화한다.
- **아동에게서 이름만 받는다.** 생년월일·성별·건강정보를 받지 않는다.
- **개발 DB에 실제 아동 실명을 넣지 않는다.** 테스트는 가명으로.
- **브라우저에 아동 실명을 저장하지 않는다.** `localStorage` · `sessionStorage` ·
  IndexedDB. 거기 쌓인 데이터는 치환 장치를 지나지 않고, 삭제 요청이 와도 못 지운다. ADR-013.

---

## LLM 예산 — 초과하면 키가 삭제된다

엘리스 MLAPI. 팀 예산 ₩120,000/월, **초과 시 API Key 자동 삭제.**

- **사용량은 카테캠 담당자가 보고 알려준다.** 우리가 세서 막지 않는다.
  ~~`shared/llm`에 토큰 카운터를 둔다. 70% 경고 · 90% 차단.~~ **무효(2026-09-21)**
  담당자 노티가 있으니 카운터가 중복이고, 90%에서 자동 차단하면 파일럿 중에
  교사 앞에서 서비스가 멈춘다. 사람이 판단할 기회를 남긴다.
- **차단용 카운터와 호출 기록은 다르다.** 호출 기록은 남긴다 — `shared/llm` 의 `post_json` 이 성공한 호출마다
  `llm_usage` 한 줄(모델 · 토큰 숫자 넷)을 남긴다. 연간 · 월간 · 문서가 모두 이 한 곳을 지난다. 프롬프트 · 응답 내용은 찍지 않는다
  (ADR-036).
- `LLM_MODE=mock`이 기본값이다.
- **로컬에서 `real` 모드를 코드로 막는다.** 키가 팀 공유라, 6명이 각자 로컬에서 부르면 어디로 새는지 아무도 모른다.

```python
if os.getenv("LLM_MODE") == "real" and not os.getenv("IS_SERVER"):
    raise RuntimeError("로컬에서 real 모드 금지. 배포된 서버 엔드포인트를 호출한다.")
```

- 프롬프트는 **문서 단위 배치**로 설계한다 — 연간은 12개월, 월간은 한 달, 주간은 한 주를 한 번에. 칸 단위로 호출하면
  시스템 프롬프트가 칸 수만큼 반복돼 15배 이상 나간다.

---

## 양식 파싱

- **`hwp5txt`를 쓰지 않는다.** 표를 통째로 버리고 `<표>`라는 글자만 남긴다. 계획안은 거의 전부 표다.
- `hwp5html`로 변환하고 표를 추출한다. `rowspan`·`colspan`을 보존한다.
- **중첩 표가 실제로 나온다. 정규식으로 파싱하지 않는다.** HTMLParser 스택을 쓴다.
- `pip install pyhwp six olefile` — **`six`가 빠지면 import 에러.**
- 정보공개포털 계획안은 **PDF다.** `pdftotext -layout`으로 읽는다. `hwp5html`은 원이 업로드한 hwp에만.

---

## 서버 값은 타입 말고 실제 응답을 본다

타입에 칸이 있다고 그 안에 든 값의 모양까지 아는 것이 아니다.
**한 번 찍어보고 쓴다.** 2026-10 에 같은 실수를 세 번 했다.

```
칸 수정     목업이 PATCH 를 받아줘 테스트가 통과했다. 진짜 서버는 PUT 이라 405 였다
hwpx       curl 로 받아보고 된다고 했다. 화면 버튼은 txt 를 만들고 있었다
시각        타입에 created_at 이 있어 그대로 썼다. UTC 라 9시간 틀렸다
```

셋 다 **코드를 보고 짐작했고 값을 안 봤다.**

## 날짜 · 시각

- 서버의 `created_at` · `updated_at` 은 **UTC** 다 (끝에 `Z`).
  **문자열을 자르지 않는다.** `new Date(...)` 로 읽어 현지로 바꾼다.
  ```ts
  // ✗  .slice(11, 16)        Z 를 무시한다. 한국에서 9시간 전으로 보인다
  // ✓  new Date(v).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })
  ```
- `date`(`YYYY-MM-DD`)는 시간대가 없다. 그건 잘라 써도 된다.
- **「오늘」을 만들 때 `toISOString()` 을 쓰지 않는다.** 그건 UTC 날짜라 한국 아침 9시
  전에는 어제가 된다. `lib/workspace/model.ts` 의 `today()` 를 쓴다.

## 입력 검사 — 스키마에서 막는다

라우터에 `if` 를 쓰지 않는다. **타입에 적어두면 라우터에 들어오기 전에 걸린다.**

- 문자열 칸을 맨몸 `str` 로 두지 않는다.
  ```python
  # ✗  text: str     빈 값 · 공백만 · 10만 자가 다 들어온다
  # ✓  text: Annotated[str, StringConstraints(
  #        strip_whitespace=True, min_length=1, max_length=80)]
  ```
- `strip_whitespace` 가 먼저 털고 `min_length=1` 이 본다. 그래야 **공백만 든 값**이 막힌다.
- **빈 값을 허용하는 칸이면 `min_length` 를 걸지 않는다.** 대신 `strip_whitespace` 는 두어
  「공백만」과 「빈 값」이 같은 것으로 저장되게 한다. 허용한다는 사실은 계약(`api-spec.md`)에
  적혀 있어야 한다 — 코드만 보고 바꾸면 의도한 동작을 지운다.
- `max_length` 는 **DB 컬럼 길이에 맞춘다.** `JSONB` 처럼 맞출 컬럼이 없으면
  그 이유와 기준을 주석에 적는다 — 지어낸 숫자를 근거 없이 두지 않는다.
- 이미 있는 것들: `centers` 의 `Name` · `PersonName` · `RegionPart` · `GreetingText`,
  `children` 의 `ChildName`, `auth` 의 `TeacherName` · `Password`.
  **새 칸을 만들 때 거기 있는 걸 먼저 본다.**

---

## 보안

- API 키를 클라이언트 코드에 두지 않는다. 서버에서만 호출한다.
- `.env`는 커밋하지 않는다. `.env.example`만.
- Next.js의 `NEXT_PUBLIC_` 접두사를 키에 쓰지 않는다. 번들에 박힌다.
- 실수로 `.env`를 커밋했으면 **그 키를 즉시 재발급한다.** git 히스토리에 영구히 남는다.

---

## 명령어

```bash
# 최초 1회 — .env 가 없으면 docker compose 가 기동을 거부한다
cp .env.example .env               # 비밀번호를 바꾼다. .env 는 커밋하지 않는다

# 로컬 실행
docker compose up -d --build
docker compose ps                  # 세 개 다 Up, db 는 healthy
docker compose logs -f backend
curl -f http://localhost:8000/health          # 프로세스만
curl -f http://localhost:8000/health/ready    # DB 까지. 배포 판정은 이쪽

# 마이그레이션 — 상세는 docs/structure.md
docker compose run --rm -v "$(pwd)/backend:/app" backend alembic upgrade head
docker compose run --rm -v "$(pwd)/backend:/app" backend alembic downgrade -1
docker compose run --rm -v "$(pwd)/backend:/app" backend alembic check   # CI 도 이걸 돌린다

# 린트
cd backend  && ruff check . && ruff format .
cd frontend && npm run lint && npx prettier --write .

# 서버 배포 (5주차 · 수동)
ssh ktc-server
cd ~/ktc4-kangwon-2 && git pull && docker compose up -d --build
```

`.env` 의 `POSTGRES_PASSWORD` 와 `DATABASE_URL` 안의 비밀번호는 **같은 값**이어야 한다.
`POSTGRES_PASSWORD` 는 `pgdata` 볼륨 최초 생성 때만 쓰인다 — **볼륨이 이미 있으면 값을 바꿔도 DB 비밀번호는 안 바뀐다.**
서버 `.env` 는 지금 볼륨의 비밀번호와 맞춰야 한다.

## 쓰지 않는 명령

```
Base.metadata.create_all()    이미 있는 테이블을 안 고친다. 컬럼 추가가 반영되지 않는다
hwp5txt                       표를 통째로 버린다
postgres:latest               메이저 버전이 올라가며 깨진다. postgres:15 로 고정
docker compose up (-d 없이)    터미널이 잡힌다. 로그는 logs -f 로 본다
docker compose exec backend alembic ...   새 마이그레이션을 못 보고도 성공한 것처럼 끝난다. run --rm -v 형태만 쓴다
```
