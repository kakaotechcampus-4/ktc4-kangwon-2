# 쌤플 · Ssample

어린이집 교사의 보육 문서 초안을 만드는 AI. 만 3~5세 유아반 담임교사 대상.

카카오테크 캠퍼스 4기 2단계 팀 프로젝트 — 강원대 2팀 · 운영 <https://ssample.duckdns.org>

![쌤플 홈 화면](frontend/public/landing/v2/hero-pc.webp)

## 무엇을 푸나

어린이집 교사는 계획안, 보육일지, 관찰일지, 평가제 서류를 손으로 쓴다.
아이들이 있는 동안에는 못 쓰고, 낮잠 시간과 퇴근 뒤에 몰아 쓴다([페르소나](docs/페르소나.md)).
빈 칸 앞에서 첫 문장이 안 나오는 것이 제일 큰 벽이다.

**쌤플은 첫 문장을 대신 써 주고, 그 문장이 어디서 나왔는지를 칸마다 붙여 준다.**
완성된 문서를 대신 제출하지는 않는다. 교사가 내용을 검토하고 확정해야 비로소 원에 제출할 문서가 된다.

## 무엇을 하나

| 기능 | 하는 일 |
|---|---|
| 관찰 · 일과 기록 | 아이와 영역을 고르고 본 대로 한 줄씩 기록한다. 일과는 날짜별로 시간 순서대로 기록하고, PC에서는 시간순으로 모아 볼 수 있다. |
| 보육일지 · 관찰일지 | 교사가 적은 기록을 근거로 초안. 사실 칸은 적은 그대로 들어간다 |
| 계획안 | 연간 → 월간 → 주간. 확정한 상위 계획안을 이어받아 만든다 |
| 평가 점검 | 평가제 지표별로 확정된 서류를 종류 · 개수 · 기간으로 세고, 모자란 것을 보여 준다. 충족 여부는 판정하지 않는다 |
| 내보내기 | HWPX · HWP · PDF. 화면의 근거 표시는 제출 파일에 넣지 않는다 |

**알림장 · 사고보고서 · 투약의뢰서는 만들지 않는다.** 식사 · 배변 · 수면 · 투약은 사실이고,
AI 가 없는 사실을 쓰면 문서 조작이다([ADR-007](docs/adr/007-spec-out-notice-and-assessment.md)).

## 화면

**기록은 휴대폰으로, 그날그날.** 아이와 영역을 고르고 본 대로 한 줄 적는다. 일과는 달력에서 날을 골라 적고,
한 주를 펼쳐 비어 있는 날을 확인한다. 쌓인 기록으로 보육일지를 만든다.

<table>
<tr>
<td align="center"><img src="frontend/public/landing/v2/phone-records.webp" width="240" alt="관찰 기록"/><br/><sub>관찰 기록</sub></td>
<td align="center"><img src="frontend/public/landing/v2/phone-routines.webp" width="240" alt="일과 기록"/><br/><sub>일과 기록</sub></td>
<td align="center"><img src="frontend/public/landing/v2/phone-weekly.webp" width="240" alt="주간 기록"/><br/><sub>주간 기록</sub></td>
</tr>
</table>

**계획안은 PC 에서, 위에서 아래로.** 연간을 확정하면 그걸 바탕으로 월간을, 월간을 확정하면 주간을 만든다.
AI 가 채운 칸은 눌러서 고치고, 교사가 써야 하는 칸은 비워 둔 채 표시한다.

<table>
<tr>
<td align="center"><img src="frontend/public/landing/v2/plan-annual.webp" alt="연간 보육계획안"/><br/><sub>연간 계획안 — 확정 뒤 내보내기 · 월간 만들기</sub></td>
<td align="center"><img src="frontend/public/landing/v2/plan-monthly.webp" alt="월간 계획안 편집"/><br/><sub>월간 계획안 — 칸 편집</sub></td>
</tr>
</table>

## AI 를 어떻게 믿을 만하게 쓰나

보육 문서는 교사가 직접 검토하고 자기 이름으로 내는 서류다. 교사가 관찰하지 않은 내용이 AI를 통해 사실처럼 기록되지 않도록 AI가 만들 수 있는 범위와 검사 과정을 코드로 정해 두었다.

**1. 아이 이름은 AI 에 가지 않는다.** 실명은 DB 에 두고, LLM 호출 직전에 가명으로 바꾼다.
바꾸지 못하면 호출하지 않는다. 브라우저 저장소에도 실명을 두지 않는다.
`backend/app/shared/childCode/` · [ADR-004](docs/adr/004-child-name-storage.md) · [ADR-013](docs/adr/013-no-child-name-in-browser.md)

**2. 일지는 사실 · 해석 · 지원 세 층으로 쓴다.** 해석은 교사가 적은 사실만 근거로 하고,
지원이 비면 반려한다. [ADR-024](docs/adr/024-journal-three-layers-merge-on-paper.md)

**3. 출력은 3단 게이트를 순서대로 지난다.** 스키마 검사 → 고유명사 · 수량 · 날짜를 원문과
대조(모델 호출 없음) → 별도의 검증 모델이 문장별로 검사한다.
`backend/app/shared/gates/` · [ADR-071](docs/adr/071-journal-judge-with-jev.md)

**4. 계획안은 Rule → LLM → Rule.** 규칙이 사용할 수 있는 후보와 근거, 법정 기준을 정하고, LLM이 그 범위 안에서 내용을 고른 뒤 작성한다. 마지막으로 규칙이 다시 검사한다. 법정 교육 시수처럼 틀리면 안 되는 값은 규칙 엔진이 원문과 대조한다. [ADR-032](docs/adr/032-rule-sets-range-llm-decides-rule-verifies.md)

**5. 출처를 칸 단위로 남긴다.** 각 칸에 근거, 생성 방법, 수정 이력을 따로 기록한다.
교사가 내용을 고치면 근거는 그대로 두고 변경 이력을 하나 더 남긴다.

**6. 평가 점검은 세기만 한다.** 모델이 「통과」를 판정하지 않는다.
[ADR-019](docs/adr/019-evaluation-checklist-counts-only.md)

**7. 부가 기능이 죽어도 본 기능은 돈다.** 트렌드 · 외부 자료가 실패하면 기본 자료로 만들고,
그 사실을 생성 기록에 남긴다.

## 구조

```
브라우저 ─ nginx ─┬─ Next.js (화면)
                  └─ /api → FastAPI ─┬─ PostgreSQL 15
                                     └─ shared/llm → 엘리스 MLAPI
```

```
Frontend   Next.js (TypeScript, App Router)
Backend    FastAPI (Python 3.12)
Database   PostgreSQL 15
Infra      AWS EC2 · Docker · nginx · GitHub Actions
AI         엘리스 MLAPI
```

LLM 호출은 `shared/llm` 한 곳으로만 나가고, 성공한 호출마다 모델과 토큰 수를 한 줄 남긴다
(프롬프트 · 응답 내용은 남기지 않는다). CI 는 가짜 LLM 으로 돌고, 로컬에서는 실제 모델 호출을
코드로 막는다. [ADR-023](docs/adr/023-llm-model-and-no-temperature.md) · [ADR-036](docs/adr/036-monthly-llm-wiring-and-usage-log.md)

## 실행

```bash
sh scripts/local-cert.sh --i-am-not-the-server   # 처음 한 번만
docker compose up -d --build
curl -f http://localhost/health                  # {"status":"ok"}
```

**브라우저는 `http://localhost` 로 연다** (3000 아님). nginx 를 거쳐야 `/api` 가
FastAPI 로 간다 — 3000 으로 바로 열면 로그인부터 안 된다.

첫 줄이 필요한 이유: `nginx.conf` 가 Let's Encrypt 인증서를 가리키는데 그 파일은
서버에만 있다. 없으면 nginx 가 뜨다 죽어서 통째로 안 올라온다. 자체 서명 인증서를
한 번 만들어 두면 된다. **서버에서는 돌리지 않는다 — 진짜 인증서를 덮어쓴다.**

`.env` 는 만들지 않아도 된다 — `docker-compose.yml` 이 `.env.example` 과 같은 기본값을 채운다.

## 문서

**개발을 시작하기 전에 [CLAUDE.md](CLAUDE.md) 를 읽는다.** 프로젝트 작업 규칙과 **문서 전체 색인**이 정리되어 있다.

문서 색인은 CLAUDE.md에서 관리한다. 중복된 색인이 서로 달라지는 일을 막기 위해서다.

되돌리기 어려운 결정은 [docs/adr/](docs/adr/) 에 하나씩 남겼다(73건). 무엇을 골랐고,
무엇을 버렸고, 왜 그랬는지가 거기 있다.

## 팀

| 이름 | 팀 역할 | 프로젝트 역할 |
|---|---|---|
| 이승석 | PM | BE · FE · AI |
| 김수린 | 플래너 | BE · FE · AI |
| 김수민 | 메이커 | FE |
| 노덕철 | FE 리드 | FE |
| 박하민 | AI 리드 | BE · AI |
| 안성진 | BE 리드 | BE · AI |
