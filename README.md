# 쓱싹요정

어린이집 교사의 보육 문서 초안을 만드는 AI. 만 3~5세 유아반 담임교사 대상.

카카오테크 캠퍼스 4기 2단계 팀 프로젝트 — 강원대 2팀

## 실행

```bash
docker compose up -d --build
curl -f http://localhost:8000/health     # {"status":"ok"}
```

프론트는 `http://localhost:3000`.
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
