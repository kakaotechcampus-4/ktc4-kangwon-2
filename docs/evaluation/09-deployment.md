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

## 배포 사고 하나를 끝까지 추적했다

2026-10-11 배포(#119)가 **서버는 성공했는데 Health check 만 70분 돌다 실패**했다.
점검 결과를 이슈 하나로 묶고(#185 · #154 2순위) 넷을 찾아 둘을 고쳤다.

| | 무엇 | 지금 |
|---|---|---|
| 1 | Health check 가 옛 IP 를 봤다 | **고침** — 기본값을 도메인으로(`deploy.yml` Health check), `curl -m 10` 으로 한 번에 10초 제한. 커밋 `1f56f25` |
| 3 | 덤프가 실패해도 백업 파일이 남았다 | **고침** — `.part` 로 받고 `pg_dump` 머리글과 **끝 표시**까지 확인한 뒤에야 이름을 준다. `scripts/backup.sh` |
| 2 | 백업이 S3 로 안 간다 | 코드는 `.env` 를 읽게 됐다. **서버 `.env` 에 `BACKUP_S3_URI` 한 줄이 들어갔는지 확인 안 됨** |
| 4 | 백업이 한국 낮 12:15 에 돈다 | 문서·주석은 UTC 로 적게 고쳤다. **서버 cron 줄이 바뀌었는지 확인 안 됨** |

- **고친 것이 실제로 들었다** — 2026-10-23 `main` 배포가 `success`(`gh run list --workflow=deploy.yml`)
- **크기로는 백업을 못 가른다.** gzip 은 입력이 없어도 20바이트짜리 올바른 파일을 만든다 — `backup.sh` 주석
- **안 되는 백업은 없는 것보다 나쁘다.** 2026-10-14 에 복구를 해 봤고 오류 105줄이 나면서 아무것도 복구되지 않았다.
  그래서 `scripts/restore-check.sh` 가 생겼다 — `backup.sh` 머리말

## 아직 아닌 것

- **#185 가 반만 닫혔다.** 서버 쪽 손 작업 둘(`.env` 의 `BACKUP_S3_URI` · cron 시각)을 눈으로 확인해야 한다
- 컨테이너는 살아 있는데 응답이 없는 경우를 **저장소 안에서 감시하지 않는다** — #185 「정해 주실 것」
- main 에 머지하면 **CI 가 실패해도 배포된다.** `ci.yml` 과 `deploy.yml` 이 따로 돈다
- 롤백은 Actions 에 있지만 한 번도 연습하지 않았다

## 더 모을 근거

- [ ] 이슈 #185 닫고 그 PR 번호를 여기 적기
- [ ] 배포 1회 성공 로그 (시간 · 커밋 · health check 응답)
- [ ] 롤백 1회 연습
