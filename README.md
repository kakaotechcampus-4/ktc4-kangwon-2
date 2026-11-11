<img src="docs/images/readme/banner.webp" width="100%" alt="쌤플 — 선생님은 기록 한 줄, 문서는 쌤플. 어린이집 교사 문서 자동 생성 AI 서비스"/>

# 쌤플 (Ssample)
카카오테크 캠퍼스 4기 2단계 팀 프로젝트 — 강원대 2팀

[쌤플 사용해 보기](https://ssample.duckdns.org) · [설계 결정(ADR)](docs/adr/) · [평가 근거](docs/evaluation/)

## 프로젝트 소개

만 3~5세 유아반 담임교사가 짧게 남긴 기록으로 보육 문서 초안을 만들어 주는 서비스 쌤플입니다.

- 관찰 기록과 일과 기록으로 **보육일지 · 관찰일지** 초안을 만듭니다.
- 확정한 상위 계획안으로 **연간 → 월간 → 주간 계획안** 초안을 만듭니다.
- 초안에는 어떤 기록과 자료로 썼는지 **근거**가 붙습니다.
- 문서는 교사가 검토하고 **확정**합니다. 자동 제출 · 자동 발송은 없습니다.

## 목적

어린이집 교사는 아이들을 돌보면서 계획안, 보육일지, 관찰일지, 평가제 서류를 써야 합니다.
아이들이 있는 동안에는 쓸 시간이 없어 낮잠 시간과 퇴근 뒤에 몰아 쓰고, 빈 칸 앞에서 첫 문장을 쓰는 데 가장 오래 걸립니다([페르소나](docs/페르소나.md)).

그래서 교사는 본 것을 한 줄씩 적기만 하고, 문장 정리는 AI가 하되 **교사가 적지 않은 사실은 문서에 들어가지 않도록** 하는 서비스를 기획했습니다.

## 기술 스택

| 구분 | 기술 |
|---|---|
| FE | ![Next.js](https://img.shields.io/badge/Next.js_16-000000?style=flat-square&logo=nextdotjs&logoColor=white) ![React](https://img.shields.io/badge/React_19-61DAFB?style=flat-square&logo=react&logoColor=black) ![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white) ![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white) ![MSW](https://img.shields.io/badge/MSW-FF6A33?style=flat-square&logo=mockserviceworker&logoColor=white) ![ESLint](https://img.shields.io/badge/ESLint-4B32C3?style=flat-square&logo=eslint&logoColor=white) ![Playwright](https://img.shields.io/badge/Playwright-2EAD33?style=flat-square&logo=playwright&logoColor=white) ![Node.js](https://img.shields.io/badge/Node.js_22-5FA04E?style=flat-square&logo=nodedotjs&logoColor=white) |
| BE | ![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=flat-square&logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white) ![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy_2-D71F00?style=flat-square&logo=sqlalchemy&logoColor=white) ![Alembic](https://img.shields.io/badge/Alembic-6BA81E?style=flat-square&logoColor=white) ![Pydantic](https://img.shields.io/badge/Pydantic-E92063?style=flat-square&logo=pydantic&logoColor=white) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL_15-4169E1?style=flat-square&logo=postgresql&logoColor=white) ![pytest](https://img.shields.io/badge/pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white) ![mypy](https://img.shields.io/badge/mypy-2A6DB2?style=flat-square&logoColor=white) ![Ruff](https://img.shields.io/badge/Ruff-D7FF64?style=flat-square&logo=ruff&logoColor=black) |
| AI | ![Elice MLAPI](https://img.shields.io/badge/Elice_MLAPI-5A3FD9?style=flat-square&logoColor=white) ![gpt-6.1-sol](https://img.shields.io/badge/gpt--6.1--sol_generation_model-412991?style=flat-square&logo=openai&logoColor=white) ![jev](https://img.shields.io/badge/jev_judge_model-5A3FD9?style=flat-square&logoColor=white) |
| Infra | ![Amazon EC2](https://img.shields.io/badge/Amazon_EC2-FF9900?style=flat-square&logo=amazonec2&logoColor=white) ![AWS SSM](https://img.shields.io/badge/AWS_SSM-FF9900?style=flat-square&logo=amazonwebservices&logoColor=white) ![Docker](https://img.shields.io/badge/Docker_Compose-2496ED?style=flat-square&logo=docker&logoColor=white) ![nginx](https://img.shields.io/badge/nginx-009639?style=flat-square&logo=nginx&logoColor=white) ![Let's Encrypt](https://img.shields.io/badge/Certbot-003A70?style=flat-square&logo=letsencrypt&logoColor=white) ![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=flat-square&logo=githubactions&logoColor=white) |

## 전체 핵심 기능

### 1. 관찰 기록 · 일과 기록
휴대폰에서 아이를 고르고 본 것을 한 줄씩 적습니다.
- **관찰 기록**: 아이와 영역을 고르고 본 대로 한 줄 적습니다. 영역은 AI가 제안만 합니다.
- **빠진 내용 알림**: 저장한 뒤 빠진 내용을 한 줄로 알려 줍니다.
- **일과 기록**: 쓰는 대로 자동 저장되고, 반 기본 일과표로 새 날을 채웁니다.

<table>
<tr>
<td align="center"><img src="docs/images/readme/usage-1-records.webp" width="260" alt="관찰 기록"/><br/><sub>관찰 기록</sub></td>
<td align="center"><img src="docs/images/readme/usage-1-routines.webp" width="260" alt="일과 기록"/><br/><sub>일과 기록</sub></td>
</tr>
</table>

### 2. 보육일지 · 관찰일지 초안
쌓인 기록을 근거로 일지 초안을 만듭니다.
- **세 칸 초안**: 사실 · 해석 · 지원 세 칸으로 씁니다. 사실 칸은 교사가 적은 그대로 들어갑니다.
- **반 전체 초안**: 관찰일지는 반 전체 초안을 한 번에 만듭니다.
- **AI 검토(jev)**: 문장마다 기록과 다른 곳을 표시합니다.
- **날씨**: 기상청 · 에어코리아 값으로 채우고, 교사가 고른 값이 우선합니다.

<img src="docs/images/readme/usage-2-draft.webp" width="100%" alt="관찰일지 초안 — 근거 쪽지, 해석 · 지원, AI 검토 결과"/>

### 3. 연간 · 월간 · 주간 계획안
확정한 상위 계획안을 이어받아 연간 → 월간 → 주간 순서로 만듭니다.
- **두 가지 형식**: 「월별 주제형」과 「놀이 중심형」을 지원합니다.
- **칸 단위 수정**: AI가 채운 칸은 눌러서 고치고, 교사가 써야 하는 칸은 따로 표시합니다.

#### 계획안 만드는 순서

<p align="center"><img src="docs/images/readme/usage-3-plan-type.png" width="100%" alt="계획안 방식 고르기 — 월별 주제형(연간 → 월간 → 주간)과 놀이 중심형(연간 → 월간)"/><br/><sub><b>방식 고르기</b> — 「월별 주제형」과 「놀이 중심형」 중 하나를 고릅니다. 한 반에서는 한 가지 방식만 씁니다.</sub></p>

**월별 주제형** · 연간 → 월간 → 주간

<table>
<tr>
<td align="center" valign="top"><img src="docs/images/readme/usage-3-theme-1-annual-create.png" width="520" alt="월별 주제형 연간계획안 만들기 — 반 정보, 양식, 요청 사항"/><br/><sub><b>① 연간 만들기</b><br/>반 정보를 확인하고 요청 사항을 적어 연간계획안을 만듭니다.</sub></td>
<td align="center" valign="top"><img src="docs/images/readme/usage-3-theme-2-annual-edit.png" width="520" alt="월별 주제형 연간계획안 다듬기 — 생활주제와 소주제 수정"/><br/><sub><b>② 연간 다듬기</b><br/>생활주제 · 소주제를 고치고 확정합니다.</sub></td>
</tr>
<tr>
<td align="center" valign="top"><img src="docs/images/readme/usage-3-theme-3-monthly-ai-candidates.png" width="520" alt="월별 주제형 월간계획안 — AI 후보로 안전교육 칸 채우기"/><br/><sub><b>③ 월간 · AI 후보로 채우기</b><br/>확정한 연간을 이어받아 월간을 만들고, 빈칸은 AI 후보에서 골라 채웁니다.</sub></td>
<td align="center" valign="top"><img src="docs/images/readme/usage-3-theme-4-weekly-play.png" width="520" alt="월별 주제형 주간계획안 — 이번 주 놀이 후보 넣기"/><br/><sub><b>④ 주간 · 놀이 넣기</b><br/>확정한 월간의 한 주로 주간을 만들고, 놀이 후보를 넣습니다.</sub></td>
</tr>
<tr>
<td align="center" colspan="2"><img src="docs/images/readme/usage-3-theme-5-confirm-export.png" width="600" alt="월별 주제형 주간계획안 확정 — PDF · HWPX · HWP 내보내기"/><br/><sub><b>⑤ 확정 · 내보내기</b><br/>확정한 계획안을 PDF · HWPX · HWP로 내려받습니다.</sub></td>
</tr>
</table>

**놀이 중심형** · 연간 → 월간 (주간계획안은 없습니다)

<table>
<tr>
<td align="center" valign="top"><img src="docs/images/readme/usage-3-play-1-annual-season-pick.png" width="520" alt="놀이 중심형 연간 — 계절별 놀이 후보 고르기"/><br/><sub><b>① 연간 · 계절별 놀이 고르기</b><br/>계절마다 놀이 후보를 고릅니다.</sub></td>
<td align="center" valign="top"><img src="docs/images/readme/usage-3-play-2-annual-edit.png" width="520" alt="놀이 중심형 연간 놀이계획안 — 칸 편집"/><br/><sub><b>② 연간 · 문서 다듬기</b><br/>고른 놀이로 연간 놀이계획안을 만들고, 칸을 눌러 고칩니다.</sub></td>
</tr>
<tr>
<td align="center" valign="top"><img src="docs/images/readme/usage-3-play-3-monthly-pick.png" width="520" alt="놀이 중심형 월간 — 함께 하는 활동 · 유아 예상 자유놀이 후보 고르기"/><br/><sub><b>③ 월간 · 활동 고르기</b><br/>「함께 하는 활동」과 「유아 예상 자유놀이」 후보를 고릅니다.</sub></td>
<td align="center" valign="top"><img src="docs/images/readme/usage-3-play-4-monthly-confirm-export.png" width="520" alt="놀이 중심형 월간계획안 확정 — PDF · HWPX · HWP 내보내기"/><br/><sub><b>④ 월간 · 확정 · 내보내기</b><br/>월간계획안을 확정하고 내려받습니다.</sub></td>
</tr>
</table>

### 4. 문서 보관함 · 내보내기
- **모아 보기**: 계획안과 일지를 종류 · 날짜별로 모아 봅니다.
- **다시 검토 표시**: 확정 뒤 근거 기록이 바뀐 일지에 「다시 검토」를 표시합니다. 확정한 문서는 「다시 수정」을 눌러야 고칠 수 있습니다.
- **내보내기**: HWPX · HWP · PDF로 내려받습니다. 화면의 근거 표시는 제출 파일에 넣지 않습니다.

<img src="docs/images/readme/usage-4-documents.webp" width="100%" alt="문서 보관함"/>

### 5. 평가 점검
평가제 지표별로 확정된 서류를 종류 · 개수 · 기간으로 셉니다. 충족 여부는 판정하지 않습니다.

<img src="docs/images/readme/usage-tip-evaluation.webp" width="100%" alt="평가 점검"/>

### 6. 트렌드봇 (기본 꺼짐)
승인된 채널의 놀이 자료를 매주 모아 사람이 승인하고, 원에서 켜면 계획안 활동 후보로 씁니다.

## 시스템 아키텍처 구조도

<img src="docs/images/readme/architecture.webp" width="100%" alt="시스템 아키텍처 — 브라우저 → nginx(80 · 443) → Next.js · FastAPI → PostgreSQL 15, FastAPI → 엘리스 MLAPI(가명 텍스트만), AWS EC2 한 대의 Docker Compose, AWS SSM 접근, main 자동 배포와 실패 시 롤백"/>

- EC2 한 대에서 Docker Compose로 돌아갑니다. 밖에 열린 포트는 nginx의 80 · 443뿐이고, 서버 접속은 SSH 대신 SSM을 씁니다.
- `main`에 머지되면 배포됩니다. 교체 뒤 확인에 실패하면 직전 성공 커밋으로 되돌립니다([docs/deploy.md](docs/deploy.md), [ADR-094](docs/adr/094-deploy-from-main-rollback-on-main-history.md)).

## AI 구조도

<img src="docs/images/readme/ai-structure.webp" width="100%" alt="AI 처리 구조도 — 일지: 교사 기록 → 이름 가명 처리 → AI 초안 생성 → 실명 복원 → 1·2단계 검증 → 교사 수정 → AI 검토(선택) → 교사 확정 / 계획안: 허용 범위 결정 → AI 계획안 생성 → 결과 검증 → 교사 검토 · 확정"/>

| 누가 | 하는 일 |
|---|---|
| AI | 계획안 칸 내용, 일지의 해석 · 지원 초안을 씁니다. 일지 문장마다 문제를 표시합니다(jev) |
| 규칙(코드) | 쓸 수 있는 자료와 법정 기준을 정하고, 아이 이름을 가명으로 바꾸고, 형식 · 원문 · 숫자를 대조합니다 |
| 교사 | 기록을 적고, 초안을 읽고 고친 뒤 확정합니다 |

- **아이 이름은 AI에 보내지 않습니다.** 실명은 DB에만 두고, 모델을 부르기 직전에 가명으로 바꿉니다. 바꾸지 못하면 부르지 않고, 브라우저 저장소에도 실명을 두지 않습니다([ADR-004](docs/adr/004-child-name-storage.md), [ADR-013](docs/adr/013-no-child-name-in-browser.md)).
- **일지는 3단계로 검사합니다.** 형식 → 원문 · 숫자 대조 → AI 검토(jev) 순서이고, 앞 단계에서 걸리면 AI 검토는 하지 않습니다. AI 검토 결과는 참고용이며 확정 조건이 아닙니다([ADR-071](docs/adr/071-journal-judge-with-jev.md)).
- **계획안은 규칙 → AI → 규칙 순서로 만듭니다.** 규칙이 쓸 수 있는 범위를 정하고, AI가 그 안에서 고르고 쓰면, 규칙이 다시 검사합니다. 법정 교육 시수처럼 틀리면 안 되는 값은 원문과 대조합니다([ADR-032](docs/adr/032-rule-sets-range-llm-decides-rule-verifies.md)).
- **근거를 남깁니다.** 일지는 만들 때 쓴 기록을 사본으로 남기고, 원본 기록이 바뀌면 「다시 검토」를 붙입니다.
- **비용에 상한을 둡니다.** 로컬 기본값은 `LLM_MODE=mock`이라 실제 모델을 부르지 않습니다. 호출 기록에는 모델 이름과 토큰 수만 남기고 프롬프트 · 응답 내용은 남기지 않습니다.

## 폴더 구조

```
ktc4-kangwon-2/
├── .github/              # PR 템플릿, CODEOWNERS, 워크플로 (CI · 배포 · 트렌드 수집)
├── frontend/
│   ├── app/              # 화면 (Next.js App Router)
│   ├── components/       # 화면 부품
│   ├── lib/              # API 호출 · 공용 함수
│   ├── public/           # 정적 파일
│   ├── tests/            # 단위 테스트
│   └── e2e/              # E2E 테스트 (Playwright)
├── backend/
│   ├── app/features/     # 기능별 API (계획안, 일지 문서, 관찰, 일과, 평가 점검, 트렌드 등)
│   ├── app/shared/       # 공용 모듈 (가명 처리, 3단계 검사, LLM 호출, 한글 파일)
│   ├── alembic/          # DB 마이그레이션
│   ├── resources/        # 서비스 자료 (그림책, 트렌드, 평가 지표, 어린이집 목록 등)
│   └── tests/            # 테스트
├── p0-planning/          # 계획안 엔진 (규칙 · 근거 자료 · 생성 로직)
├── docs/                 # 요구사항 · ADR · API · 화면 명세 · 평가 근거
├── nginx/                # nginx 설정
└── scripts/              # 배포 · 백업 · 로컬 인증서
```

코드의 `ssuksak`은 예전 프로젝트 이름(쓱싹요정)입니다. import 경로를 유지하려고 그대로 둡니다.

## 로컬 개발 환경 세팅

### 0. 공통 준비

| 도구 | 버전 | 비고 |
|---|---|---|
| Docker (Compose 포함) | — | 화면 · API · DB를 한 번에 띄웁니다 |
| Python | 3.12 | 테스트를 로컬에서 돌릴 때만 |
| Node | 22 | 프론트엔드 테스트를 로컬에서 돌릴 때만 |

저장소 루트에서 실행합니다. Windows는 Git Bash 또는 WSL을 씁니다.

#### 환경변수 파일 만들기

```bash
cp .env.example .env
```

#### 실행 순서

```
1. 로컬 인증서 (처음 한 번)  →  2. Docker Compose로 실행  →  3. http://localhost 접속
```

---

### 1. 로컬 인증서 (처음 한 번)

```bash
sh scripts/local-cert.sh --i-am-not-the-server
```

### 2. 실행

```bash
docker compose up -d --build
curl -f http://localhost/health                  # {"status":"ok"}
```

### 3. 테스트

```bash
# Python 3.12 가상환경에서
pip install -e ./p0-planning
pip install -e './backend[dev]'

# 프론트엔드
cd frontend && npm ci && npx playwright install chromium
```

| 영역 | 명령 |
|---|---|
| 백엔드 | `cd backend && DATABASE_URL=<테스트 DB> pytest` |
| 계획안 엔진 | `cd p0-planning && pytest` |
| 백엔드 타입 | `cd backend && mypy` |
| 프론트엔드 | `cd frontend && npm run lint && npm test` |
| E2E | 서버를 띄운 뒤 `cd frontend && E2E_BASE_URL=http://localhost npm run e2e` |

<details>
<summary>테스트 DB 띄우는 방법</summary>

```bash
docker run -d --name ssuksak-test-db -p 55433:5432 \
  -e POSTGRES_USER=ssuksak -e POSTGRES_PASSWORD=test-only-not-a-secret \
  -e POSTGRES_DB=ssuksak postgres:15
cd backend
DATABASE_URL='postgresql+psycopg://ssuksak:test-only-not-a-secret@localhost:55433/ssuksak' pytest
```

</details>

CI는 가짜 LLM으로 돕니다. 실제 모델의 문장 품질, 한글 프로그램에서 연 HWPX · HWP 모습은 사람이 따로 확인합니다.

## 역할 구성

<table>
  <tr>
    <td align="center"><img src="https://github.com/LEEseungseok-01.png" width="100" alt="이승석" /></td>
    <td align="center"><img src="https://github.com/ddufls.png" width="100" alt="김수린" /></td>
    <td align="center"><img src="https://github.com/errorweek.png" width="100" alt="김수민" /></td>
    <td align="center"><img src="https://github.com/NohDukCheol.png" width="100" alt="노덕철" /></td>
    <td align="center"><img src="https://github.com/Greatmin03.png" width="100" alt="박하민" /></td>
    <td align="center"><img src="https://github.com/pained-chicken.png" width="100" alt="안성진" /></td>
  </tr>
  <tr>
    <td align="center"><a href="https://github.com/LEEseungseok-01">@LEEseungseok-01</a></td>
    <td align="center"><a href="https://github.com/ddufls">@ddufls</a></td>
    <td align="center"><a href="https://github.com/errorweek">@errorweek</a></td>
    <td align="center"><a href="https://github.com/NohDukCheol">@NohDukCheol</a></td>
    <td align="center"><a href="https://github.com/Greatmin03">@Greatmin03</a></td>
    <td align="center"><a href="https://github.com/pained-chicken">@pained-chicken</a></td>
  </tr>
  <tr>
    <td align="center">이승석<br/><sub>PM · BE · FE · AI</sub></td>
    <td align="center">김수린<br/><sub>플래너 · BE · FE · AI</sub></td>
    <td align="center">김수민<br/><sub>메이커 · FE</sub></td>
    <td align="center">노덕철<br/><sub>FE 리드</sub></td>
    <td align="center">박하민<br/><sub>AI 리드 · BE</sub></td>
    <td align="center">안성진<br/><sub>BE 리드 · AI</sub></td>
  </tr>
</table>
