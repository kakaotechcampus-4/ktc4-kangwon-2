# 09 · 배포와 운영

**멘토 심사 기준(기술·개발 중심) ⑨ 배포·운영 — 10점**

> URL 접속·CI/CD·환경 분리를 갖춰 운영 가능한 상태로 배포했는가

---

## 지금 어떻게 나가나

```
배포 브랜치에 push  →  .github/workflows/deploy.yml
                 올릴 커밋을 SHA 로 고정 → AWS 자격증명 → SSM 으로 배포 명령 → 끝날 때까지 대기
                 → Health check → 실패하면 Discord 알림
```

- `.github/workflows/deploy.yml` — 배포 브랜치는 `on.push.branches` 가 정한다
- **배포는 브랜치 이름이 아니라 커밋 SHA 로 나간다.** run 을 부른 커밋이 그대로 서버에 올라가고,
  그 SHA 가 Actions 기록 · 서버 로그 · 실패 알림에 똑같이 찍힌다
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
점검 결과를 이슈 하나로 묶고(#185 · #154 2순위) 넷을 찾아 넷 다 고쳤다. 2 · 4 는 서버에서 손으로 한 일이다.

| | 무엇 | 지금 |
|---|---|---|
| 1 | Health check 가 옛 IP 를 봤다 | **고침** — 기본값을 도메인으로(`deploy.yml` Health check), `curl -m 10` 으로 한 번에 10초 제한. 커밋 `1f56f25` |
| 3 | 덤프가 실패해도 백업 파일이 남았다 | **고침** — `.part` 로 받고 `pg_dump` 머리글과 **끝 표시**까지 확인한 뒤에야 이름을 준다. `scripts/backup.sh` |
| 2 | 백업이 S3 로 안 간다 | **고침** — 설정은 `.env` 가 아니라 서버 root crontab 줄 앞에 있었다. 서버에 AWS CLI 도 버킷도 없어 한 번도 올라가지 않았었다 → 2026-10-21 버킷 `ktc4-kangwon-2-backup` 과 서버 AWS CLI 를 갖췄고, 10-22 03:15 고친 뒤 첫 cron 실행이 `s3 ok`. #216 · `docs/deploy.md` 백업 절 |
| 4 | 백업이 한국 낮 12:15 에 돈다 | **고침** — 서버 root crontab 을 `15 18 * * *`(UTC = 한국 03:15)로 다시 걸었다(2026-10-21). 시각을 바꾼 뒤 10-22 03:15 첫 실행 확인. `docs/deploy.md` 백업 절 |

- **고친 것이 실제로 들었다** — 2026-10-23 `main` 배포가 `success`(`gh run list --workflow=deploy.yml`)
- **크기로는 백업을 못 가른다.** gzip 은 입력이 없어도 20바이트짜리 올바른 파일을 만든다 — `backup.sh` 주석
- **안 되는 백업은 없는 것보다 나쁘다.** 2026-10-14 에 복구를 해 봤고 오류 105줄이 나면서 아무것도 복구되지 않았다.
  그래서 `scripts/restore-check.sh` 가 생겼다 — `backup.sh` 머리말
- **운영 백업으로 실제로 되돌릴 수 있다.** 2026-11-03 운영 서버 안에서 전날 백업(`ssuksak_20261101_181501.sql.gz`)을 버리는 DB 에 복구했다 — `restore-check ok`:
  운영의 표가 전부 있고, alembic 이 운영과 같고(`c7a9e1b35d42`), 복구 DB 에 새 행을 넣는 게 성공한다(넣고 바로 되돌림). `scripts/restore-check.sh`

## 배포 기록이 실제와 달랐던 것을 고쳤다

배포 run 이 브랜치 이름을 서버에 넘기고 있었다. 서버는 도는 순간의 브랜치 끝을 올려서, 앞 배포가
서버에 닿기 전에 머지가 또 들어오면 **앞 run 이 뒤 커밋을 자기 이름으로 올렸다.** 2026-11-04 에 4번이다.
run 기록의 커밋과 서버 로그의 「배포 … <sha>」 줄을 맞춰 봐서 찾았다 — 예: run 41803579696 은
`9a8ebbb` 로 기록됐지만 서버는 `a0648f7` 을 올렸다. 실제로 올라간 커밋이 「cancelled」로 남은 경우도 있었다.

→ run 시작 때 올릴 커밋을 SHA 하나로 고정해 서버와 기록에 같이 쓴다(`deploy.yml` 「올릴 커밋 고정」). 손 배포에 브랜치 이름을 넣어도 같다.

## 아직 아닌 것

- 컨테이너는 살아 있는데 응답이 없는 경우를 **저장소 안에서 감시하지 않는다** — #185 「정해 주실 것」
- 배포 브랜치에 머지하면 **CI 가 실패해도 배포된다.** `ci.yml` 과 `deploy.yml` 이 따로 돈다
- 롤백은 Actions 에 있지만 한 번도 연습하지 않았다

## 더 모을 근거

- [x] 이슈 #185 닫음(2026-11-01) — 문서 · 점검 스크립트는 #216
- [x] 배포 1회 성공 로그 — 2026-10-31 18:26 KST `main` `43cb0fe` 자동 배포(run 41188715632), `health/ready 200 (1회째)`
- [ ] 롤백 1회 연습
- [ ] SHA 고정 뒤 첫 배포 — run 의 커밋과 서버 로그의 SHA 가 같다(run 링크)
