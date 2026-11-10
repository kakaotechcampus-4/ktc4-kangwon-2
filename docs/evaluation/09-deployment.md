# 09 · 배포와 운영

**멘토 심사 기준(기술·개발 중심) ⑨ 배포·운영 — 10점**

> URL 접속·CI/CD·환경 분리를 갖춰 운영 가능한 상태로 배포했는가

---

## 지금 어떻게 나가나

```
배포 브랜치에 push  →  .github/workflows/deploy.yml
                 같은 커밋의 CI 성공을 기다림(실패면 안 올림) → 올릴 커밋을 SHA 로 고정 → AWS 자격증명 → SSM 으로 배포 명령 → 끝날 때까지 대기
                 → (교체 뒤 실패하면 서버가 마지막 성공 배포로 자동 롤백) → Health check → 실패하면 Discord 알림
```

- `.github/workflows/deploy.yml` — 배포 브랜치는 `on.push.branches` 가 정한다. **지금은 `main` 하나다**(2026-11-10 #527, ADR-094) —
  develop 머지는 운영에 안 나가고, develop 을 main 에 머지할 때 나간다
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
- 교체 뒤 실패하면 서버 안의 `deploy.sh` 가 마지막 성공 커밋으로 되돌린다 — 서버 안 확인(`/health/ready` 와 화면)을 통과할 때마다 그 커밋을 서버가 기억하고(저장소 밖 파일),
  `up -d` 실패 · nginx 상태 조회 · reload · restart 실패 · 서버 안 확인 실패는 같은 실행 안에서 그 커밋의 `deploy.sh` 를 꺼내 돌려 되돌린다(실패한 커밋의 스크립트에 맡기지 않는다). 종료 코드 0 성공 · 3 되돌림 · 4 못 되돌림 · 1 교체 전에 멈춤.
  밖(도메인)에서 본 실패로는 되돌리지 않는다. 서버 잠금(`flock`)이 손 배포와 자동 배포의 겹침을 막는다 —
  `scripts/deploy.sh` · `scripts/ssm-deploy.sh` · `.github/workflows/deploy.yml` · ADR-078
- 백업 스크립트와 그 테스트 — `scripts/` · `test_backup_script.py`
- nginx 설정을 바꾼 배포는 `nginx -t` 로 먼저 검사하고 reload 로 반영한다. 전에는 파일 하나씩 연결해 둔 탓에 손으로 다시 만들 때까지
  옛 설정이 돌았다(놀이 연간 120초 504) — `scripts/deploy.sh` · `docker-compose.yml`
- 떠 있는 nginx 는 reload 가 거절돼도 다시 시작하지 않고 되돌린다(이 스크립트에서. 직전 성공 커밋의 옛 deploy.sh 로 되돌릴 때는 그 스크립트가 restart 할 수 있다) —
  upstream 이름을 못 찾을 때 restart 하면 /api 까지 죽었다(PR #502 리뷰) — `scripts/deploy.sh`

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

## 운영에서 롤백을 한 번 해 봤다

2026-11-07 02:45 KST, 운영 `8d4630a8`(#402)을 그 전 코드 `d59ceaf8`(#405)로 되돌렸다가 다시 올렸다.
손 배포(`workflow_dispatch`)를 develop 에서 돌리고 `ref` 에 전체 SHA 를 넣었다 — 롤백 전용 길이 아니라 평소 배포 길이다.
바로 앞 배포 `89185839` 가 아니라 하나 더 앞으로 간 것은, `89185839` 와 `8d4630a8` 이 e2e 파일 하나만 달라 되돌려도 코드가 그대로이기 때문이다.

- 되돌리기 [run 42264552753](https://github.com/kakaotechcampus-4/ktc4-kangwon-2/actions/runs/42264552753) —
  「올릴 커밋」 · 서버 로그 「배포 d59ceaf8…」, 40초, `health/ready 200 (1회째)`
- 다시 올리기 [run 42264741582](https://github.com/kakaotechcampus-4/ktc4-kangwon-2/actions/runs/42264741582) —
  「올릴 커밋」 · 서버 로그 「배포 8d4630a8…」, 41초, `health/ready 200 (1회째)`
- **끊긴 시간** — 밖에서 1초마다 물어 쟀다. 한 번 올릴 때마다 `/health/ready` 502 가 약 5초, 화면(`/`) 502 가 4초 이하.
  끊기는 건 빌드가 아니라 `up -d` 가 backend · frontend 를 바꾸는 동안뿐이다

알게 된 것:

- 두 run 의 기록상 커밋은 둘 다 `8d4630a8` 이다 — 워크플로를 develop 에서 돌려서다. **올라간 커밋은 「올릴 커밋」 줄과 서버 로그로만 안다** —
  밖에서 지금 도는 커밋을 알려 주는 주소가 없다
- 40초는 빌드 캐시가 남아 있어서다 — 빌드 단계 17개가 `CACHED`(평소 배포 run 42258128542 는 7개).
  서버에 캐시가 없는 커밋이면 평소 배포처럼 2분 남짓 걸린다
- ready 200 은 DB 연결만 본다. 옛 코드가 새 코드가 쓴 데이터를 읽는지는 보지 않는다 —
  이번엔 diff 를 읽어 확인했다. 읽기는 된다(새 코드가 더한 JSON 키를 옛 codec 은 건너뛴다).
  **쓰기는 잃는다** — 옛 코드가 저장한 계획안에서는 `teacher_subthemes` · `parent_teacher_venues` 가 빠진다.
  이번엔 옛 코드가 돈 약 70초(17:46:02 ~ 17:47:14Z) 사이에 저장된 계획안이 **없었다**
  (운영 DB `plans.updated_at` 17:45:30 ~ 17:47:30Z 0줄, SSM 으로 조회). JSONB 안의 키도 마이그레이션 없는 스키마 변경이다

## 운영에서 자동 롤백을 한 번 돌려 봤다

2026-11-10 17:43 KST, 서버가 기억한 마지막 성공 배포 L = `9c0984ba`(#505) 위에 `/health/ready` 가 늘 503 을 내는 세 줄만 더한
커밋 F = `5f67593c` 를 `auto_rollback=true` 로 손 배포했다(ADR-078). F 는 머지하지 않았고 브랜치는 끝나고 지웠다.

- [run 42784851442](https://github.com/kakaotechcampus-4/ktc4-kangwon-2/actions/runs/42784851442) — 약 2분 45초. 서버 로그:
  「서버 안 대기 30/30 — health/ready 503 · 화면 200」 → 「되돌린다 → 9c0984ba… (L 의 deploy.sh)」 →
  L 의 「배포 9c0984ba… 9c0984ba」(checkout 뒤 HEAD) · 「서버 안 확인 통과 — health/ready 200 · 화면 200 (3회째)」 → 「되돌렸다 → 9c0984ba…」, 서버 종료 코드 3
- 밖 Health check `health/ready 200 (1회째)` · 「배포 판정」 failure(되돌려도 이번 배포는 실패로 남긴다) ·
  「실패 알림」 단계 success(종료 코드 3 · 밖 확인 통과 갈래 = 🟠 「자동 롤백 성공」)
- **끊긴 시간** — 밖에서 `/health` · 화면(`/`) · `/health/ready` 를 차례로 물었다(한 바퀴 1~3초라 경계가 1~2초 흐리다). 화면은 내내 200.
  backend(`/health`) 502 는 F 로 바꿀 때 4~6초(마지막 200 08:44:35 → 첫 200 08:44:41Z, 502 를 본 것은 08:44:36 ~ 08:44:40Z),
  L 로 돌아올 때 3~5초(08:45:50 → 08:45:55Z, 502 는 08:45:51 ~ 08:45:54Z). 그 사이 약 70초는 F 가 돌며 `/health` 200 · `/health/ready` 503 —
  서버 안 확인 30번(약 60초) 몫이다. 감시 원본(08:43:04 ~ 08:46:29Z, 154줄)에서 두 구간 앞뒤만 옮긴다. 시각은 UTC 다

```text
08:44:33 health=200 front=200 ready=200
08:44:35 health=200 front=200 ready=200
08:44:36 health=502 front=200 ready=502
08:44:37 health=502 front=200 ready=502
08:44:40 health=502 front=200 ready=502
08:44:41 health=200 front=200 ready=503   ← F 가 돈다 (ready 만 503)
08:44:42 health=200 front=200 ready=503
   … 08:45:48 까지 같음 …
08:45:50 health=200 front=200 ready=503
08:45:51 health=502 front=200 ready=502
08:45:54 health=502 front=200 ready=502
08:45:55 health=200 front=200 ready=200   ← L 로 돌아왔다
08:45:57 health=200 front=200 ready=200
08:45:58 health=200 front=200 ready=200
```

알게 된 것:

- 되돌리기 안의 L 이 처음에 「직전 성공 9c0984ba」를 읽었고, 연습 뒤 첫 배포(run 42785670658, #502)도 같은 값을 읽고 성공했다 —
  실패한 F 는 기록을 덮지 않는다
- 계획을 세운 뒤 실행 전에 develop 에 머지가 두 번(#503 · #505) 들어와 L 이 바뀌었다. F 를 새 develop 위에 다시 합쳐 「L + 세 줄」을 지켰다 —
  옛 L 위의 F 를 올렸으면 F 가 도는 동안 그 두 PR 이 빠진다. **연습 직전에 배포 브랜치 끝(지금은 main, ADR-094) = 마지막 성공 배포인지 다시 본다**

## 아직 아닌 것

- **응답이 없는 경우는 밖에서 10분마다 본다 — 아직 운영에서 한 번도 안 돌았다.** `uptime.yml`(#458)이 `/` 와 `/health/ready` 가 둘 다 200 인지 보고, 실패하면 30초 뒤 한 번 더 본 뒤에도 실패일 때만 Discord 로 알린다.
  공개 주소의 응답 코드만 보고, GitHub 예약 실행이 늦거나 빠져 죽은 순간부터 알림까지 보통 최대 약 25분이고 더 걸릴 때도 있고, 배포 중에는 알리지 않는다 — `docs/deploy.md` 「업타임 확인」. 예약 실행은 기본 브랜치에 들어가야 돌기 시작한다
- **자동 롤백은 운영에서 한 갈래만 돌려 봤다** — ready 만 503 인 커밋 → 3(위). 되돌리기마저 실패하는 4 · `up -d` 실패 · reload · restart 실패 갈래는
  pytest 가 가짜 서버로만 보고, 알림 갈래는 워크플로 안이라 단위 테스트가 없다 — 가짜 스크립트로 손 시험만 했다.
  응답 코드만 봐서 화면 내용이 깨진 경우 · 기능 버그는 못 잡고, 이 기능이 머지된 뒤 첫 성공 배포 전에는 되돌아갈 기록이 없으며, 마이그레이션 판정(ADR-073)이 거절하는 롤백과
  롤백 뒤에도 브랜치 끝이 그대로인 것은 사람이 한다 — ADR-078 「한계」
- **CI 를 기다리는 배포는 아직 운영에서 한 번도 안 돌았다.** push 배포는 같은 커밋의 CI(push)가 성공해야 나가게 했다(`scripts/wait-ci.sh` ·
  `deploy.yml` 「CI 기다리기」) — 다음 develop→main 머지가 첫 회다. 손 배포(`workflow_dispatch`)는 CI 를 기다리지 않는다
- **마이그레이션을 건너는 롤백은 PR 하나까지만 된다.** `deploy.sh` 가 올리기 전에 DB 리비전을 읽어, 그 리비전을 들여온 PR 의
  머지 직전 커밋으로는 `alembic upgrade` 를 건너뛰어 되감고 그 밖은 checkout 전에 멈춘다 — `scripts/deploy.sh` · ADR-073.
  건너뛰어도 되는 근거는 CI `backend (rollback compat)` 다. 머지 직전 코드가 PR 의 새 DB 에서 도는지 pytest 로 시험한다 — `.github/workflows/ci.yml`.
  전에는 `upgrade head` 에서 `Can't locate revision` 으로 멈췄고, 건너뛰어도 옛 코드가 새 스키마에서 돈다는 보장이 없었다 —
  #383 의 CHECK 제약 아래서는 그 전 코드가 계획안을 확정하지 못하고, #415 가 지운 `center_invites` 표를 그 전 코드는
  초대 코드 만들기 · 받기에 쓴다. **아직 아닌 것** — 빈 DB 에서만 시험해서 기존 데이터 · 새 코드가 쓴 데이터(JSONB 안 새 키 포함)는 안 보고,
  PR 둘 이상을 건너는 되감기는 DB 를 손으로 내려야 하며, #383 · #415 이전 변경에는 소급되지 않고, develop 규칙에 필수 검사로
  켜기 전에는 경고등이다 — ADR-073 「한계」. 절차는 `docs/deploy.md` 「되감을 때 (롤백)」.
  배포가 main 으로 옮겨 간 뒤로는 main 이력에서도 찾는다 — 그 리비전을 들여온 develop→main 머지의 직전 main 커밋으로도 건너뛰고,
  CI 의 같은 검사가 main 으로 가는 PR 에서도 돈다. main 규칙에는 필수 검사가 없어서 main 쪽은 경고등이다 — ADR-094 「한계」

## 더 모을 근거

- HTTPS 재설정 시 관리 중인 인증서를 임시본으로 덮지 않고, 복원 파이프도 선택한 Docker 권한 경로를 쓴다. 갱신 실패·볼륨 내 인증서 유무·sudo 환경을 실제 자원 대신 스텁으로 확인한다 — `scripts/https-setup.sh` · `scripts/restore-check.sh` · `backend/tests/test_ops_script_regressions.py`

- [x] 이슈 #185 닫음(2026-11-01) — 문서 · 점검 스크립트는 #216
- [x] 배포 1회 성공 로그 — 2026-10-31 18:26 KST `main` `43cb0fe` 자동 배포(run 41188715632), `health/ready 200 (1회째)`
- [x] 롤백 1회 연습 — 2026-11-07 02:45 KST 운영 `8d4630a8` → `d59ceaf8` → `8d4630a8`(run 42264552753 · 42264741582), 둘 다 `health/ready 200 (1회째)`, 끊김 약 5초씩. 위 「운영에서 롤백을 한 번 해 봤다」
- [x] 마이그레이션 PR 하나를 건너는 롤백 판정 — 올림 · 건너뜀 · 거절 판정표 전부와 실제 리비전을 선언한 파일로 찾는 것을 pytest 가 본다(CI 에서 돈다). 2026-11-08 실제 이력 손 시험: #424 직전 `de04e2c0` 는 건너뜀, 그보다 앞 #383 직전은 거절, 최신은 평소대로 — `backend/tests/test_deploy_script.py` · ADR-073
- [ ] 운영에서 마이그레이션을 건너는 롤백 연습 — 머지 · 필수 검사를 켠 뒤, 그때 DB 리비전을 들여온 머지의 직전 커밋으로(main 배포면 develop→main 머지의 직전 main, 로그에 「마이그레이션을 건너뛴다」) → 최신,
  둘 다 `health/ready 200`. 커밋은 그때 다시 정한다 — 11/08 에 적은 `89e84790` → `de04e2c0` 은 그 뒤 #448 · #470 이 마이그레이션을 더해 지금은 거절된다
- [x] 자동 롤백의 서버 안 판정 · 되돌리기 · 종료 코드 — F 가 안 살아나면 L 의 `deploy.sh`(F 의 것이 아니다)가 `DEPLOY_REF=L` · `AUTO_ROLLBACK=0` · 잠금이 풀린 채로 돌아 3,
  그 스크립트가 0 이 아니게 끝나면 · 롤백이 꺼짐 · 기록 없음 · L = F · L 에 `deploy.sh` 가 없으면 4, 교체 전 실패는 1, `up -d` 실패와 reload · restart 실패도 되돌리고,
  root 로 시작해도 코드와 결과 줄이 그대로 나오고 잠금이 겹침을 막는 것을 pytest 가 가짜 서버로 본다(CI 에서 돈다) — `backend/tests/test_deploy_script.py` · `backend/tests/test_ssm_deploy_script.py` · ADR-078
- [x] 운영에서 자동 롤백 연습 — 2026-11-10 17:43 KST L `9c0984ba` 위 F `5f67593c`(ready 만 503)를 `auto_rollback=true` 로 손 배포(run 42784851442):
  서버 종료 코드 3 · L 의 「배포 9c0984ba… 9c0984ba」 · 서버 안 · 밖 `health/ready 200` · 「실패 알림」 단계 success, backend 끊김 4~6초 · 3~5초(화면은 내내 200).
  위 「운영에서 자동 롤백을 한 번 돌려 봤다」 · ADR-078 채택
- [x] SHA 고정 뒤 첫 배포 — 2026-11-07 00:07 KST `c8335b8` 자동 배포(run 42240152119): run 의 커밋 · 「올릴 커밋」 · 서버 로그 「배포 <SHA>」 가 모두 `c8335b8`, `health/ready 200 (1회째)`
- [x] 연달아 머지돼도 run 마다 자기 커밋만 올린다 — 2026-11-07 09:48~09:50 KST 3분에 develop push 13번: 성공 3번(run 42320437206 · 42320569221 · 42320703112)이
  각자 자기 커밋을 올렸고 10번은 cancelled. 2026-11-10 13:14~13:15 KST 7번도 성공 2 · cancelled 5. 2026-11-07 00:39 ~ 11-10 13:15 KST 배포 66회 중 성공 48회에서
  run 의 커밋과 서버 로그 「배포 <SHA>」 가 다른 것은 위 롤백 연습(입력한 `d59ceaf8` 를 그대로 올렸다) 하나뿐
- [x] 배포 브랜치를 main 으로 옮긴 뒤 develop 머지는 안 나간다 — 2026-11-10 23:26 KST #527 머지 커밋 `0e02a19c` 에는 CI 만 돌고 Deploy run 이 없었다. ADR-094
- [x] main 으로 가는 PR 의 rollback compat — #529 에서 그때 main 코드(`09c180a2`, 2026-11-08)를 그 PR 의 마이그레이션까지 올린 DB 에서
  backend pytest 전부 통과([run 42835264083](https://github.com/kakaotechcampus-4/ktc4-kangwon-2/actions/runs/42835264083)). 이 검사가 main PR 에서 돈 첫 번째다
- [x] 롤백 판정이 main 이력도 본다 — main 이 develop 을 머지로 받는 임시 저장소로 건너뜀 · 거절 · 못 읽음 거절을 pytest 가 본다(CI 에서 돈다).
  2026-11-10 실제 이력 손 시험(DB 를 `6cf1f5e3ba44` 로 치고): 그때 손 배포 `ref: main`(`09c180a2`)은 거절, develop→main 머지를 흉내 낸 뒤 `09c180a2` 는 건너뜀 —
  `backend/tests/test_deploy_script.py` · ADR-094
- [x] main 배포 첫 회 — 2026-11-11 00:20 KST #529 머지 `8fbeb0ea` push 배포([run 42843300103](https://github.com/kakaotechcampus-4/ktc4-kangwon-2/actions/runs/42843300103)):
  「올릴 커밋」 · 서버 로그 「배포 8fbeb0ea…」 가 같고, 직전 성공 `e5e5e883`, 서버 안 「health/ready 200 · 화면 200 (1회째)」 · 밖 `health/ready 200 (1회째)` · 서버 종료 코드 0
- [ ] CI 를 기다리는 배포 첫 회 — 다음 develop→main 머지에서 「CI 기다리기」가 CI 성공을 본 뒤에 배포가 시작되는지(run 의 두 job 시각).
  판정은 `backend/tests/test_wait_ci_script.py`(성공 · 실패 5종 · 더 새 push 가 취소 · 뒤따를 배포 없는 취소 · 조회 실패 · 시간 초과,
  그리고 잠금 안의 「아직 브랜치 끝인지」 — 성공했지만 대체된 커밋은 안 올림)와
  2026-11-11 실제 커밋 손 시험이 본다 — `8fbeb0ea`@main(CI 성공) 통과, `d07b8ada`@develop(CI 실패) 막음,
  `083d2848`@develop(CI 취소, 브랜치 끝은 이미 `4d5a5bed`) 건너뜀, `8fbeb0ea`@develop(그 브랜치의 CI 없음) · 없는 커밋은 시간 초과로 막음
- [ ] 업타임 알림 첫 확인 — 머지 뒤 수동 실행(test_alert)으로 시험 알림 1회
