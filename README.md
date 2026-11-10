# 쌤플 (Ssample)

어린이집 교사의 보육 문서 초안을 만드는 AI. 만 3~5세 유아반 담임교사 대상.

카카오테크 캠퍼스 4기 2단계 팀 프로젝트, 강원대 2팀

**[운영 주소](https://ssample.duckdns.org)** | [실행](#실행) | [CLAUDE.md](CLAUDE.md) | [ADR](docs/adr/) | [평가 근거](docs/evaluation/)

목차: [무엇을 푸나](#무엇을-푸나) | [무엇을 하나](#무엇을-하나) | [화면](#화면) | [AI 를 어떻게 믿을 만하게 쓰나](#ai-를-어떻게-믿을-만하게-쓰나) | [구조](#구조) | [실행](#실행) | [테스트](#테스트) | [평가 기록](#평가-기록) | [알려진 제한](#알려진-제한) | [문서](#문서) | [팀](#팀)

> 이 문서는 **2026년 11월 10일 `develop`** 기준이다. 운영 서버에는 `main` 에 머지될 때 배포된다([deploy.yml](.github/workflows/deploy.yml)).
>
> 코드 안의 `ssuksak` 은 예전 이름(쓱싹요정)이다. import 경로가 전부 바뀌어야 해서 그대로 둔다.

| 표시 | 뜻 |
|---|---|
| (표시 없음) | `develop` 에 있다. 운영에는 `main` 에 머지된 뒤 나간다 |
| **기본 꺼짐** | 코드는 있지만 원이 켜야 돈다 |
| **머지 전** | 열린 PR 이나 브랜치에만 있다. [곧 들어올 것](#곧-들어올-것)에만 적는다 |

![쌤플 홈 화면](frontend/public/landing/v2/hero-pc.webp)

## 무엇을 푸나

어린이집 교사는 계획안, 보육일지, 관찰일지, 평가제 서류를 손으로 쓴다.
아이들이 있는 동안에는 못 쓰고, 낮잠 시간과 퇴근 뒤에 몰아 쓴다([페르소나](docs/페르소나.md)).
빈 칸 앞에서 첫 문장이 안 나오는 것이 제일 큰 벽이다.

**쌤플은 첫 문장을 대신 써 주고, 그 문장이 어디서 나왔는지를 붙여 준다.**
완성된 문서를 대신 제출하지는 않는다. 교사가 내용을 검토하고 확정해야 원에 낼 문서가 된다.

## 무엇을 하나

| 기능 | 하는 일 |
|---|---|
| 관찰 기록, 일과 기록 | 아이와 영역을 고르고 본 대로 한 줄씩 적는다. 일과는 날짜별로 시간 순서대로 적고, PC 에서는 시간순으로 모아 본다 |
| 보육일지, 관찰일지 | 교사가 적은 기록을 근거로 초안을 만든다. 사실 칸은 적은 그대로 들어간다. 편집기의 「AI 검토」가 문장마다 기록과 다른 곳을 짚는다 |
| 계획안 | 연간 → 월간 → 주간. 확정한 상위 계획안을 이어받아 만든다 |
| 문서 보관함 | 계획안과 일지를 종류별로 모아 본다. 확정 뒤 근거 기록이 바뀐 일지는 「다시 검토」로 표시한다 |
| 평가 점검 | 평가제 지표별로 확정된 서류를 종류, 개수, 기간으로 세고 모자란 것을 보여 준다. 충족 여부는 판정하지 않는다 |
| 내보내기 | HWPX, HWP, PDF. 화면의 근거 표시는 제출 파일에 넣지 않는다 |
| 트렌드봇 **기본 꺼짐** | 매주 월요일 새벽 승인된 채널의 놀이 자료를 모아 PR 로 올리고, 사람이 읽고 승인한다. 승인된 자료는 놀이 중심 월간과 주간의 활동 후보로 들어간다. 원마다 켠다 |

**알림장, 사고보고서, 투약의뢰서는 만들지 않는다.** 식사, 배변, 수면, 투약은 사실이고,
AI 가 없는 사실을 쓰면 문서 조작이다([ADR-007](docs/adr/007-spec-out-notice-and-assessment.md)).

### 곧 들어올 것

아래는 **머지 전**이다. 위 표와 아래 사진에는 넣지 않았다.

- 관찰일지: 기록이 있는 아이 전부의 초안을 한 번에 만들고, 초안마다 AI 검토 결과를 붙인다.
- 관찰 기록: 적을 때 영역을 제안하고, 저장한 뒤 빠진 것(예: 아이 반응)을 한 줄로 알린다.
- 일과 기록: 저장 단추 없이 쓰는 대로 저장한다. 반의 기본 일과표로 새 날을 깔고, 주간계획안의 활동을 후보로 띄운다.
- 보육일지 날씨: 기상청과 에어코리아 값으로 채운다. 교사가 고른 값이 우선한다.
- 확정본 입력 사본: 날씨, 활동 이름, 일과 줄까지 확정할 때 문서에 함께 남긴다.
- 일지 AI 검토 v3, v4 ([평가 기록](#평가-기록)).
- 생성 요청 하나의 LLM 호출 횟수 상한(#466).

## 화면

사진은 11월 4~5일 운영 화면을 시험 계정(지어낸 원, 아이, 기록)으로 찍었다. 아이 이름이 보이는 곳은 흐리게 가렸다.

**기록은 휴대폰으로, 그날그날.** 아이와 영역을 고르고 본 대로 한 줄 적는다. 일과는 달력에서 날을 골라 적고,
한 주를 펼쳐 비어 있는 날을 확인한다. 쌓인 기록으로 보육일지를 만든다.

<table>
<tr>
<td align="center"><img src="frontend/public/landing/v2/phone-records.webp" width="240" alt="관찰 기록"/><br/><sub>관찰 기록</sub></td>
<td align="center"><img src="frontend/public/landing/v2/phone-routines.webp" width="240" alt="보육일지 · 일일"/><br/><sub>보육일지 · 일일</sub></td>
<td align="center"><img src="frontend/public/landing/v2/phone-weekly.webp" width="240" alt="보육일지 · 주간"/><br/><sub>보육일지 · 주간</sub></td>
</tr>
</table>

**계획안은 PC 에서, 위에서 아래로.** 연간을 확정하면 그걸 바탕으로 월간을, 월간을 확정하면 주간을 만든다.
AI 가 채운 칸은 눌러서 고치고, 교사가 써야 하는 칸은 비워 둔 채 표시한다.

<table>
<tr>
<td align="center"><img src="frontend/public/landing/v2/plan-annual.webp" alt="연간 보육계획안"/><br/><sub>연간 계획안. 확정 뒤 내보내기, 월간 만들기</sub></td>
<td align="center"><img src="frontend/public/landing/v2/plan-monthly.webp" alt="월간 계획안 편집"/><br/><sub>월간 계획안. 칸 편집</sub></td>
</tr>
</table>

<details>
<summary>화면 더 보기: 문서 보관함</summary>

11월 10일 `develop` 화면을 목업 데이터로 찍었다.

<a href="docs/images/documents.png"><img src="docs/images/documents.png" width="100%" alt="문서 보관함"/></a>

</details>

## AI 를 어떻게 믿을 만하게 쓰나

보육 문서는 교사가 직접 검토하고 자기 이름으로 내는 서류다. 교사가 관찰하지 않은 내용이 AI 를 통해 사실처럼 기록되지 않도록,
AI 가 만들 수 있는 범위와 검사 과정을 코드로 정해 두었다.

| 누가 | 하는 일 |
|---|---|
| AI | 계획안 칸의 내용을 고르고 쓴다. 일지의 해석과 지원 초안을 쓴다. 일지 문장마다 문제를 짚는다(jev) |
| 규칙(코드) | 쓸 수 있는 자료와 법정 기준을 정한다. 아이 이름을 가명으로 바꾼다. 형식, 사실 칸 원문, 숫자를 대조한다. 평가 서류를 센다 |
| 교사 | 기록을 적는다. 초안을 읽고 고친다. 사실, 해석, 지원을 확인하고 확정한다 |

**1. 아이 이름은 AI 에 가지 않는다.** 실명은 DB 에 두고, LLM 호출 직전에 가명으로 바꾼다.
가명 표는 우리 반이 아니라 원 전체 아이로 만든다. 옆 반 아이 이름이 글에 들어가도 가려진다.
한 글자 이름 아이(「민이가」)는 교사가 정한 부르는 이름으로 찾아 가린다(#470).
바꾸지 못하면 호출하지 않는다. 브라우저 저장소에도 실명을 두지 않는다.
`backend/app/shared/childCode/`, [ADR-004](docs/adr/004-child-name-storage.md), [ADR-013](docs/adr/013-no-child-name-in-browser.md)

**2. 일지는 사실, 해석, 지원 세 층으로 쓴다.** 해석은 교사가 적은 사실만 근거로 하고,
지원이 비면 반려한다. [ADR-024](docs/adr/024-journal-three-layers-merge-on-paper.md)

**3. 일지 출력은 3단 게이트를 순서대로 지난다.** [ADR-071](docs/adr/071-journal-judge-with-jev.md)

| 단계 | 하는 일 | 모델 |
|---|---|---|
| 1 형식 | 칸이 사실, 해석, 지원 셋인지, 비었거나 너무 짧지 않은지 | 안 부름 |
| 2 원문과 숫자 대조 | 사실 칸이 근거 기록 원문과 글자까지 같은지, 해석에 나온 숫자가 사실에 있는지 | 안 부름 |
| 3 jev 판정 | 문장마다 기록과 다름, 근거 없는 새 사실, 단정, 개인정보 등을 보기에서 고른다 | jev |

- 2단은 고유명사를 대조하지 않는다. 형태소 분석 없이 고르면 잘못 걸리는 것이 많아서, 3단 jev 가 본다. `backend/app/shared/gates/sections.py`
- 1, 2단에 걸리면 jev 를 부르지 않는다. jev 는 알려 주기만 하고, 확정 조건이 아니다.
- 문장이 36개를 넘으면 판정하지 않는다. 앞부분만 보고 통과처럼 보이지 않게 하려는 것이다.

**4. 계획안은 Rule → LLM → Rule.** 규칙이 쓸 수 있는 후보와 근거, 법정 기준을 정하고, LLM 이 그 범위 안에서 내용을 고른 뒤 쓴다.
마지막으로 규칙이 다시 검사한다. 법정 교육 시수처럼 틀리면 안 되는 값은 규칙 엔진이 원문과 대조한다.
[ADR-032](docs/adr/032-rule-sets-range-llm-decides-rule-verifies.md)

**5. 출처를 남긴다. 계획안은 칸 단위로, 일지는 근거 사본으로.**
계획안은 칸마다 근거, 생성 방법, 수정 이력을 따로 기록한다. 교사가 고치면 근거는 그대로 두고 수정 이력을 하나 더 남긴다.
일지는 만들 때 쓴 기록 원문을 사본으로 남긴다. 원본 기록이 바뀌면 사본과 글자로 비교해 「다시 검토」를 붙인다.
`backend/app/features/documents/stale.py`

**6. 확정한 일지는 바뀌지 않는다.** 확정본은 고치거나 지울 수 없다. 고치려면 확정을 먼저 취소한다(계획안에는 확정 취소가 없다).
근거 기록을 나중에 고쳐도 확정본 글은 그대로이고, 대신 「다시 검토」로 표시한다. 자동 제출과 자동 발송은 없다.

**7. 평가 점검은 세기만 한다.** 모델이 「통과」를 판정하지 않는다.
[ADR-019](docs/adr/019-evaluation-checklist-counts-only.md)

**8. 부가 기능이 죽어도 본 기능은 돈다.** 트렌드가 꺼졌거나 수집 파일을 못 읽으면 트렌드 없이 계획안을 만든다.
그 상태는 서버 로그에 한 줄로만 남는다. 생성 기록에는 아직 남지 않는다([알려진 제한](#알려진-제한)).

**9. 비용에 상한을 둔다.** 팀 예산은 월 12만 원이고, 넘으면 API 키가 자동으로 지워진다.

- 연간은 12개월, 월간은 한 달, 주간은 한 주를 한 번에 부른다. 칸마다 부르면 15배 넘게 든다.
- 기본값은 `LLM_MODE=mock` 이다. 로컬에서 실제 모델 호출은 코드가 막는다.
- LLM 호출은 `shared/llm` 한 곳으로만 나간다. 성공한 호출마다 모델과 토큰 수를 한 줄 남기고, 프롬프트와 응답 내용은 남기지 않는다.
  [ADR-023](docs/adr/023-llm-model-and-no-temperature.md), [ADR-036](docs/adr/036-monthly-llm-wiring-and-usage-log.md)
- 사용량은 카테캠 담당자가 보고 알려 준다. 파일럿 중에 서비스가 멈추지 않도록 우리 쪽 자동 차단은 두지 않았다.
- jev 판정은 문서 한 장에 약 0.5원이다.

## 구조

```mermaid
flowchart LR
  subgraph elice[엘리스 MLAPI]
    writer[글 쓰는 모델<br/>초안]
    jev[jev<br/>보기 중 하나와 확률만 답함]
  end
  user[브라우저] --> nginx[nginx<br/>80, 443]
  nginx -->|화면| next[Next.js]
  nginx -->|/api| api[FastAPI<br/>계획안 엔진 p0-planning 포함]
  next -.->|서버 쪽 요청| api
  api --> db[(PostgreSQL 15)]
  api -->|아이 이름을 가명으로 바꾼 글만| elice
```

- 서버는 AWS EC2 한 대에서 Docker Compose 로 돈다. 인터넷에 열린 것은 nginx 의 80, 443 뿐이고, 서버에는 SSH 대신 SSM 으로 들어간다([docs/deploy.md](docs/deploy.md)).
- 배포는 GitHub Actions 가 한다. 교체 뒤 확인에 실패하면 직전 성공 커밋으로 되돌린다([ADR-078](docs/adr/078-auto-rollback-on-failed-deploy.md), 운영 연습 전).
  되감기는 마이그레이션이 든 PR 하나까지만 하고, 그보다 멀면 서버를 건드리기 전에 멈춘다([ADR-073](docs/adr/073-one-step-rollback-across-migration.md)).

| 경로 | 하는 일 | 어떻게 돌아가나 |
|---|---|---|
| [`frontend/`](frontend/) | 화면. Next.js App Router, TypeScript | `frontend` 컨테이너, nginx 뒤 |
| [`backend/app/features/`](backend/app/features/) | 기능별 API. 계획안, 일지 문서, 관찰, 일과, 평가 점검, 트렌드 등 | `backend` 컨테이너(FastAPI) |
| [`backend/app/shared/`](backend/app/shared/) | 여러 기능이 같이 쓰는 한 곳. 가명 바꾸기(`childCode`), 3단 게이트(`gates`), LLM 호출(`llm`), 한글 파일(`hwpx.py`) | `backend` 안 |
| [`backend/alembic/`](backend/alembic/) | DB 마이그레이션 | `alembic upgrade head` |
| [`p0-planning/`](p0-planning/) | 계획안 엔진. 규칙, 근거 자료(`data/`). 이 안에서는 [p0-planning/CLAUDE.md](p0-planning/CLAUDE.md) 가 우선한다 | `backend` 이미지에 같이 설치 |
| [`nginx/`](nginx/) | 입구. `/api` 는 FastAPI 로, 나머지는 Next.js 로 보낸다 | `nginx` 컨테이너 |
| [`scripts/`](scripts/) | 서버 배포(`deploy.sh`), 백업, 로컬 인증서 | 서버 또는 손으로 |
| [`.github/workflows/`](.github/workflows/) | CI, 배포, 트렌드 수집 | GitHub Actions |

폴더마다 무엇을 두는지는 [docs/structure.md](docs/structure.md) 에 있다.

```
Frontend   Next.js (TypeScript, App Router)
Backend    FastAPI (Python 3.12)
Database   PostgreSQL 15
Infra      AWS EC2, Docker, nginx, GitHub Actions
AI         엘리스 MLAPI (글 쓰는 모델, 판정 전용 jev)
```

## 실행

필요한 것: Docker (Compose 포함)

```bash
cp .env.example .env                              # 처음 한 번만, 꼭 만든다
sh scripts/local-cert.sh --i-am-not-the-server   # 처음 한 번만
docker compose up -d --build
curl -f http://localhost/health                  # {"status":"ok"}
```

> [!WARNING]
> **`.env` 는 꼭 만든다.** `docker-compose.yml` 이 `POSTGRES_PASSWORD`, `DATABASE_URL`, `SECRET_KEY` 에 기본값을 두지 않아서, 없으면 기동 전에 멈춘다.
> 로컬은 `.env.example` 을 그대로 복사하면 뜬다. 나머지 값(LLM 키, `LLM_MODE` 등)은 비어 있으면 `docker-compose.yml` 의 기본값을 쓴다.

> [!IMPORTANT]
> 브라우저는 **`http://localhost`** 로 연다(3000 아님). nginx 를 거쳐야 `/api` 가 FastAPI 로 간다.
> 3000 으로 바로 열면 로그인부터 안 된다.

> [!NOTE]
> `local-cert.sh` 는 자체 서명 인증서를 만든다. `nginx.conf` 가 서버에만 있는 Let's Encrypt 인증서를 가리켜서, 없으면 nginx 가 뜨다가 죽는다.
> **서버에서는 돌리지 않는다.** 인증서가 이미 있으면 스크립트는 손대지 않고 끝난다.

`LLM_MODE` 기본값이 `mock` 이라 로컬에서는 모델을 부르지 않고 가짜 응답으로 초안 화면을 확인한다.

## 테스트

| 영역 | 명령 | 어디서 도나 |
|---|---|---|
| 백엔드 | `cd backend && DATABASE_URL=<테스트 DB> pytest` | 로컬, CI `backend (pytest)` |
| 계획안 엔진 | `cd p0-planning && pytest` | 로컬, CI `backend (pytest)` 안 |
| 백엔드 타입 | `cd backend && mypy` | 로컬, CI `backend (ruff)` 안 |
| 화면 | `cd frontend && npm run lint && npm test` | 로컬, CI `frontend (eslint · prettier · build)` |
| 화면 끝까지(E2E) | `cd frontend && npm run e2e` | CI `e2e (playwright)` |
| 마이그레이션 | `alembic check`, 직전 코드가 새 DB 에서 도는지 | CI `backend (alembic check)`, `backend (rollback compat)` |

백엔드 테스트는 받은 `DATABASE_URL` 에 마이그레이션과 시험 데이터를 올린다. **로컬 서비스 DB 를 주지 말고** 테스트용 DB 를 따로 띄운다.

```bash
docker run -d --name ssuksak-test-db -p 55433:5432 \
  -e POSTGRES_USER=ssuksak -e POSTGRES_PASSWORD=test-only-not-a-secret -e POSTGRES_DB=ssuksak postgres:15
cd backend && DATABASE_URL='postgresql+psycopg://ssuksak:test-only-not-a-secret@localhost:55433/ssuksak' pytest
```

**이 테스트가 확인하지 않는 것**

- 실제 모델이 쓴 문장의 품질. CI 는 가짜 LLM 으로 돈다. jev 판정도 가짜 응답으로 흐름만 본다. 품질은 사람 판정과 실측 기록([docs/evaluation/06-ai-quality.md](docs/evaluation/06-ai-quality.md))으로 본다.
- 내보낸 HWPX, HWP 를 한글 프로그램에서 연 모습. 사람이 열어 본다.
- 운영 서버의 상태. 배포 워크플로가 교체 뒤 따로 확인한다.

## 평가 기록

일지 AI 검토(jev)를 어떻게 쟀는지 적는다.

> 아래는 모두 **지어낸 문서 세트**로 잰 숫자다. 정답을 단 두 판정자도 **AI** 다. **사람 판정은 진행 중**이다.
> 실제 교사가 쓴 문장에서의 성능이 아니다.
>
> `develop` 에서 도는 jev 는 v1 이다. v3, v4 는 **머지 전**이다. 아래 근거 파일(사전 등록, 다시 센 기록)도 아직 저장소에 올리지 않았다.

### 예전 숫자를 다시 셌다

[ADR-071](docs/adr/071-journal-judge-with-jev.md) 과 [06-ai-quality.md](docs/evaluation/06-ai-quality.md) 에는 「문제 문장 279개 중 277개 표시」라고 적혀 있다.
확증편향을 점검해 보니 한 쪽이 문항을 쓰고, 정답을 달고, 질문을 고쳤고, 고칠 때 본 세트를 결과에 섞었다. 부풀려진 숫자였다.
처음 본 세트만 다시 세면 이렇다.

- 문제 문장을 맞는 이유로 잡은 것: 136개 중 133개
- 문제없는 문서에 아무것도 안 뜬 것: 48장 중 43장
- 틀린 표시가 하나라도 있는 문서: 120장 중 15장 (예전에는 세지 않던 지표)

### 그 뒤로 바꾼 방법

- **사전 등록**: 결과를 보기 전에 합격선을 글로 적고 해시로 묶었다.
- **독립 시험 세트**: 질문을 고치는 쪽은 개발 세트만 본다. 시험 세트의 문항과 문항별 결과는 보지 않고, 합계 숫자만 받는다.
- **두 판정자**: 정답은 두 판정자가 따로 달아 같은 것만 썼다. 일치도(카파)는 0.89 이상이었다. 두 판정자는 AI(Codex, Claude)라서 사람 판정을 대신하지 않는다.

### v1 → v3 → v4

| 지표 | 시험 A (v1) | 시험 B (v3) | 시험 C (v4) | v4 합격선 |
|---|---|---|---|---|
| 틀린 표시가 하나라도 있는 문서 (낮을수록 좋음) | 28% | 15% | 34% | 20% 이하 |
| 문제없는 문서에 아무것도 안 뜬 비율 | 50% | 86% | 74% | 80% 이상 |
| 기록과 다름, 반대를 기록 번호까지 맞게 잡음 | 60% | 83% | 92% | 80% 이상 |
| 근거 없는 새 사실을 잡음 | 80% | 63% | 79% | 75% 이상 |
| 개인정보를 잡음 | | | 83% | 90% 이상 |
| 단정 / 교사가 하지 않은 개입 / 근거 없는 변화 / 형식적 지원 | | | 100% / 94% / 89% / 87% | 각 85% 이상 |

- **v3 (시험 B)**: 사전 등록 합격선 10개 중 9개를 넘었다. 새 사실은 80% 에서 63% 로 떨어져 넘지 못했다.
- **v4**: 기록과 다르다는 표시가 뜬 문장에서 새 사실을 보지 않던 것이 원인이었다. 개발 세트에서 새 사실을 다시 잡게 고쳤다.
- **v4 (시험 C)**: 합격선 9개 중 6개를 넘었다. 넘지 못한 것은 틀린 표시가 있는 문서, 문제없는 문서에 아무것도 안 뜬 비율, 개인정보 셋이다.
  - 같은 시험 C 에서 「기록과 다름」과 「새 사실」이 한 문장에 겹친 경우, 새 사실을 잡은 수가 v3 의 8개 중 0개에서 v4 의 8개 중 7개로 올랐다. v4 가 고친 곳이 여기다.
  - 넘지 못한 세 가지는 v3 도 시험 C 에서 똑같이 넘지 못했다. v4 수정 때문에 생긴 실패는 아니다.

**시험 C 의 한계**

- 시험 C 는 문항을 쓴 쪽, 정답을 단 쪽, 질문을 고친 쪽이 모두 Claude 였다. 틀린 표시가 정말 jev 의 잘못인지는 사람 판정이 끝나야 가릴 수 있다.
- 사전 등록 파일에는 「Codex 가 쓴 세트」라고 적었지만, Codex 사용 한도 때문에 Claude 가 썼다.
- 사람 판정(하민, 성진)은 진행 중이다.

## 알려진 제한

| 무엇 | 지금 상태 |
|---|---|
| 일지 AI 검토(jev) 품질 | 지어낸 세트와 AI 판정자로만 쟀다. 실제 교사 문장으로 잰 적이 없다. 사람 판정 진행 중 |
| jev 판 | `develop` 은 v1 이다. v4 는 시험 C 에서 합격선 9개 중 6개만 넘었고 머지 전이다 |
| 2단 게이트와 고유명사 | 2단은 고유명사를 대조하지 않는다. 이름이 틀린 문장은 3단 jev 만 본다 |
| 트렌드 실패 기록 | 트렌드 없이 만든 사실이 서버 로그에만 남는다. 계획안 생성 기록에서는 볼 수 없다 |
| 트렌드봇 | 기본 꺼짐. 원이 켜야 계획안에 들어간다 |
| 로컬 실행 | `mock` 이라 실제 모델 문장과 jev 판정을 로컬에서 볼 수 없다. 실제 호출은 서버에서만 된다 |

## 문서

**[CLAUDE.md](CLAUDE.md) 부터 읽는다.** 어기면 사고가 나는 규칙과 문서 전체 색인이 거기 있다.
색인은 CLAUDE.md 한 곳에만 둔다. 두 군데 적으면 한쪽만 고쳐진다. 아래는 자주 찾는 것만 적었다.

| 알고 싶은 것 | 문서 |
|---|---|
| 무엇을 만드나, 어디까지 됐나 | [docs/요구사항명세서.md](docs/요구사항명세서.md) |
| 누가 쓰나 | [docs/페르소나.md](docs/페르소나.md) |
| 왜 이렇게 정했나 | [docs/adr/](docs/adr/) |
| 서버와 화면의 약속 | [docs/api-spec.md](docs/api-spec.md) |
| 화면이 어떻게 도나 | [docs/screen-spec.md](docs/screen-spec.md) |
| 폴더와 브랜치 규칙 | [docs/structure.md](docs/structure.md), [docs/branch-strategy.md](docs/branch-strategy.md) |
| 배포와 서버 | [docs/deploy.md](docs/deploy.md) |
| 평가 항목별 근거 | [docs/evaluation/](docs/evaluation/) |

문서끼리 다르면 `ADR > api-spec > 요구사항명세서 > screen-spec` 순서로 따른다([ADR-031](docs/adr/031-document-roles-and-conflict-order.md)).

## 팀

| 이름 | 팀 역할 | 프로젝트 역할 |
|---|---|---|
| 이승석 | PM | BE, FE, AI |
| 김수린 | 플래너 | BE, FE, AI |
| 김수민 | 메이커 | FE |
| 노덕철 | FE 리드 | FE |
| 박하민 | AI 리드 | BE, AI |
| 안성진 | BE 리드 | BE, AI |
