# 09 · 배포와 운영

**기준 원문** — (받은 기준 문장을 그대로 붙인다)

---

## 지금 어떻게 나가나

```
main 에 push  →  .github/workflows/deploy.yml
                 AWS 자격증명 → SSM 으로 배포 명령 → 끝날 때까지 대기
                 → Health check → 실패하면 Discord 알림
```

- `.github/workflows/deploy.yml` — `push: branches: [main]` (L14)
- **`develop` 머지는 운영 반영이 아니다.** 운영에 나가는 것은 `main` 뿐이다
- 배포 판정은 `/health` 가 아니라 `/health/ready`(DB 까지) — [CLAUDE.md](../../CLAUDE.md) §명령어
- 운영 <https://ssample.duckdns.org> · nginx + docker compose 3개(db · backend · frontend)
- DB 는 EC2 위 도커 postgres. 왜 RDS 가 아닌지 — ADR-006
- `postgres:15` 로 고정. `postgres:latest` 는 메이저가 올라가며 깨진다

## 안 깨지게 하려고 둔 것

- `.env` 의 `POSTGRES_PASSWORD` 는 **볼륨 최초 생성 때만** 쓰인다 — 볼륨이 이미 있으면 값을 바꿔도 DB 비밀번호는 안 바뀐다.
  이걸 모르면 배포가 조용히 붙지 않는다 — [CLAUDE.md](../../CLAUDE.md) §명령어
- `docker compose exec backend alembic ...` 을 금지했다 — 새 마이그레이션을 못 보고도 성공한 것처럼 끝난다
- `Base.metadata.create_all()` 금지 — 이미 있는 테이블의 컬럼 추가가 반영되지 않는다
- 백업 스크립트와 그 테스트 — `scripts/` · `test_backup_script.py`

## 아직 아닌 것 — **여기가 제일 약하다**

- **Health check 가 옛 IP 를 본다. 백업이 S3 로 안 간다** 외 2건 — 이슈 #185 (열린 채)
- 2026-10-21 점검 때 **운영 SSH 가 AWS SSO 토큰 만료로 실패**했다. 그래서 운영의 배포 커밋과 실제 AI 생성을 확인 못 했다 —
  [docs/mentor-pilot-guide-2026-10-21.md](../mentor-pilot-guide-2026-10-21.md)
- 롤백 절차가 문서로 없다
- 운영 로그를 모아 보는 곳이 없다

## 더 모을 근거

- [ ] 이슈 #185 닫고 그 PR 번호를 여기 적기
- [ ] 배포 1회 성공 로그 (시간 · 커밋 · health check 응답)
- [ ] 롤백 1회 연습
