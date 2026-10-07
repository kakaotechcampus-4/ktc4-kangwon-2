# 쌤플 · Ssample

어린이집 교사의 보육 문서 초안을 만드는 AI. 만 3~5세 유아반 담임교사 대상.

카카오테크 캠퍼스 4기 2단계 팀 프로젝트 — 강원대 2팀

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

| | 무엇 |
|---|---|
| [CLAUDE.md](CLAUDE.md) | **어기면 사고 나는 규칙.** 개발 전 필독 |
| [docs/structure.md](docs/structure.md) | 디렉터리 구조 · 어느 파일을 언제 만드나 |
| [docs/branch-strategy.md](docs/branch-strategy.md) | 브랜치 · PR · 머지 |
| [docs/adr/](docs/adr/) | 「왜 이렇게 정했나」. 결정 하나당 한 파일 |

## 스택

```
Frontend   Next.js (TypeScript, App Router)
Backend    FastAPI (Python 3.12)
Database   PostgreSQL 15
Infra      AWS EC2 · Docker · GitHub Actions
AI         엘리스 MLAPI
```
