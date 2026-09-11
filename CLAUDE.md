# ktc4-kangwon-2

**쓱싹요정** — 어린이집 교사의 보육 문서 초안을 만드는 AI. 만 3~5세 유아반 담임교사 대상.
카카오테크 캠퍼스 4기 2단계 팀 프로젝트 — 강원대 2팀

아래는 **어기면 사고가 나는 것**만 적었다.
디렉터리는 [docs/structure.md](docs/structure.md), 브랜치 상세는 [docs/branch-strategy.md](docs/branch-strategy.md), 결정 배경은 [docs/adr/](docs/adr/).

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
- **확정은 층마다 순차 게이트.** 연간이 `CONFIRMED`가 아니면 월간을 생성하지 않는다.
- 자동 제출·자동 발송을 만들지 않는다.
- 출처를 칸 단위로 기록한다: `source_type = TEMPLATE | TREND | AI`.
- **출처 표시는 화면에만.** hwp 내보내기에 마커가 섞이면 안 된다. 제출 문서다.
- **배치·선별에 LLM을 쓰지 않는다.** 규칙 엔진이 정하고 LLM은 문장화만 한다. (ADR-005)
- **부가 기능이 죽어도 본 기능은 돌아간다.** 트렌드봇·외부 API를 필수 의존으로 넣지 않는다.

---

## 개인정보 — P1부터 적용

계획안(P0)은 반 단위 문서라 아동 이름이 들어가지 않는다. 상세는 ADR-004.

- 아동 실명을 **DB에 저장한다.** 파일럿부터 법정대리인 동의서를 받는다.
- **LLM 호출 직전에 아동 코드로 치환한다.** 프롬프트·응답·로그에 실명이 남으면 안 된다.
- 치환은 `shared/childCode` 한 곳에서만.
- **치환 실패 시 호출하지 않고 에러를 낸다.**
- 치환 토큰은 **받침 있는 더미 한글 이름.** 영문 토큰이면 조사가 복원 후 틀어진다.
- 아동 명단 입력칸은 **동의 확인 체크박스 뒤에서만** 활성화한다.
- **아동에게서 이름만 받는다.** 생년월일·성별·건강정보를 받지 않는다.
- **개발 DB에 실제 아동 실명을 넣지 않는다.** 테스트는 가명으로.

---

## LLM 예산 — 초과하면 키가 삭제된다

엘리스 MLAPI. 팀 예산 ₩120,000/월, **초과 시 API Key 자동 삭제, 사용 내역 조회 불가.**

- `shared/llm`에 토큰 카운터를 둔다. **70% 경고 · 90% 차단.**
- `LLM_MODE=mock`이 기본값이다.
- **로컬에서 `real` 모드를 코드로 막는다.** 키가 팀 공유라 로컬 직접 호출은 카운터를 우회한다.

```python
if os.getenv("LLM_MODE") == "real" and not os.getenv("IS_SERVER"):
    raise RuntimeError("로컬에서 real 모드 금지. 배포된 서버 엔드포인트를 호출한다.")
```

- 프롬프트는 **월 단위 배치**로 설계한다. 칸 단위로 호출하면 시스템 프롬프트가 43번 반복돼 15배 이상 나간다.

---

## 양식 파싱

- **`hwp5txt`를 쓰지 않는다.** 표를 통째로 버리고 `<표>`라는 글자만 남긴다. 계획안은 거의 전부 표다.
- `hwp5html`로 변환하고 표를 추출한다. `rowspan`·`colspan`을 보존한다.
- **중첩 표가 실제로 나온다. 정규식으로 파싱하지 않는다.** HTMLParser 스택을 쓴다.
- `pip install pyhwp six olefile` — **`six`가 빠지면 import 에러.**
- 정보공개포털 계획안은 **PDF다.** `pdftotext -layout`으로 읽는다. `hwp5html`은 원이 업로드한 hwp에만.

---

## 보안

- API 키를 클라이언트 코드에 두지 않는다. 서버에서만 호출한다.
- `.env`는 커밋하지 않는다. `.env.example`만.
- Next.js의 `NEXT_PUBLIC_` 접두사를 키에 쓰지 않는다. 번들에 박힌다.
- 실수로 `.env`를 커밋했으면 **그 키를 즉시 재발급한다.** git 히스토리에 영구히 남는다.

---

## 명령어

```bash
# 로컬 실행
docker compose up -d --build
docker compose ps                  # 세 개 다 Up, db 는 healthy
docker compose logs -f backend
curl -f http://localhost:8000/health

# 마이그레이션 — 상세는 docs/structure.md
docker compose run --rm -v "$(pwd)/backend:/app" backend alembic upgrade head
docker compose run --rm -v "$(pwd)/backend:/app" backend alembic downgrade -1
docker compose run --rm -v "$(pwd)/backend:/app" backend alembic check

# 린트
cd backend  && ruff check . && ruff format .
cd frontend && npm run lint && npx prettier --write .

# 서버 배포 (5주차 · 수동)
ssh ktc-server
cd ~/ktc4-kangwon-2 && git pull && docker compose up -d --build
```

## 쓰지 않는 명령

```
Base.metadata.create_all()    이미 있는 테이블을 안 고친다. 컬럼 추가가 반영되지 않는다
hwp5txt                       표를 통째로 버린다
postgres:latest               메이저 버전이 올라가며 깨진다. postgres:15 로 고정
docker compose up (-d 없이)    터미널이 잡힌다. 로그는 logs -f 로 본다
docker compose exec backend alembic ...   새 마이그레이션을 못 보고도 성공한 것처럼 끝난다. run --rm -v 형태만 쓴다
```
