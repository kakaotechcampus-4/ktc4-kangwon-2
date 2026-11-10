# 배포

**배포 브랜치에 머지되면 자동으로 올라간다.** 어느 브랜치인지는 `deploy.yml` 의 `on.push.branches` 가 정한다.
손으로도 같은 스크립트를 돌릴 수 있다.

```
주소      https://ssample.duckdns.org
서버      i-041ebb00937bd371f (ktc4-team-server) · t3.medium · ap-northeast-2
고정 IP    13.125.107.188     Elastic IP — 서버를 껐다 켜도 안 바뀐다
인증서     Let's Encrypt · 60일마다 certbot 이 자동 갱신
```

## 어떻게 들어가나

**SSH 가 아니다.** 22 포트를 열지 않고, GitHub 에 서버 열쇠를 맡기지도 않는다.

```
SSH      GitHub  ──(22 로 들어옴)──▶  EC2      ← 안 쓴다
OIDC     GitHub  ──▶  AWS  ──(SSM)──▶  EC2     ← 인바운드 0개
```

GitHub 이 「나는 이 저장소의 워크플로다」를 증명하면 AWS 가 **1시간짜리 임시 권한**을
준다. 저장해 두는 비밀이 없다. 유출될 것 자체가 없다.

2026-09-22 에 22 를 닫았다 — 카테캠 안내(다른 팀이 공격을 받았다). 같은 날
카테캠이 OIDC 가이드와 `ktc-github-deploy` 역할을 냈고, 그날 옮겼다.

**역할은 카테캠이 만든 것을 쓴다.** 우리 계정은 IAM 을 못 만진다(ADR-006).
우리가 한 건 repo Variable `AWS_ACCOUNT_ID` 등록 하나다.

```
AWS_ACCOUNT_ID   Variable    12자리 계정 ID.  비밀이 아니라 Variables 에 넣는다
HEALTHCHECK_URL  Secret      배포 후 확인할 주소
DISCORD_WEBHOOK  Secret      실패 알림.  없으면 알림만 건너뛴다
```

`EC2_HOST` · `EC2_USER` · `EC2_SSH_KEY` 는 **더 이상 쓰지 않는다.** 지워도 된다.

## 자동 배포가 하는 일

```
배포 브랜치에 push
  ↓
올릴 커밋을 SHA 하나로 고정         브랜치 이름을 서버에 넘기지 않는다
  ↓
OIDC 로 AWS 인증                  키 없음
  ↓
scripts/deploy.sh 를 통째로 보냄   scripts/ssm-deploy.sh → aws ssm send-command
  ↓
서버가 그 스크립트를 실행           잠금 → DB 리비전 읽기 → 마이그레이션 판정 → git checkout <SHA> → nginx -t → build → migrate → up -d → nginx reload → 서버 안 확인
  ↓                               교체(up -d) 뒤에 실패하면 서버가 직접 마지막 성공 커밋의 deploy.sh 로 되돌린다  (아래 「자동 롤백」)
끝날 때까지 기다림                  최대 약 47분(서버 한도 45분).  안 기다리면 실패해도 초록불이 뜬다
                                 (실측: 최근 성공 배포 60개의 서버 쪽 실행 시간 최소 14초 · 중앙값 80초 · 최대 209초 — 최악의 합이 약 1740초라 한도 안이다.  ADR-078)
  ↓
밖에서 /health/ready 200 확인       배포가 성공했거나(0) 서버가 되돌렸을 때(3)만.  실패해도 되돌리지 않고 알림만
```

**서버에서 도는 명령은 `scripts/deploy.sh` 한 곳에만 있다.** 워크플로가 그 파일을
보낼 뿐이라, 자동과 수동이 같은 명령을 돈다. 두 곳에 나눠 적으면
「손으로는 되는데 CI 는 안 된다」가 생긴다.

## 자동 롤백 (ADR-078)

**교체가 시작된 뒤에 실패하면, 서버 안의 `deploy.sh` 가 같은 실행 안에서 마지막 성공 커밋의 `deploy.sh` 를 꺼내 돌려 그 커밋으로 되돌린다.**
러너(워크플로)는 되돌리지 않고 종료 코드를 읽어 알림만 낸다. 판정도 러너가 아니라 서버가 한다 — 러너가 인터넷을 건너 도메인으로 묻는 확인은
DNS · 인증서 · secret 에 흔들린다(2026-10-11 에 서버는 멀쩡한데 옛 IP 때문에 확인만 실패했다).

```
기록       서버 안 확인을 통과할 때마다 그 커밋 SHA 를 /home/ubuntu/.ssuksak-last-good 에 적는다 (저장소 밖 — checkout 이 안 건드린다)
           **이 스크립트(v2)를 지난 성공만 기록된다** — 현재 워크플로의 배포(자동 · Run workflow) · 이 기능 이후 run 의 re-run ·
           서버에 v2 가 checkout 된 상태의 Session Manager 실행.  옛 run 의 re-run · 옛 체크아웃의 deploy.sh 는 기록되지 않는다.  없거나 깨졌으면 「직전 성공 없음」
판정       up -d · nginx reload 뒤, image prune 전에 서버 안 nginx 에 묻는다
           http://127.0.0.1/health/ready (backend · DB)  와  http://127.0.0.1/ (화면)  둘 다 200
           2초마다 30번 (빠른 실패는 약 60초)
되돌리기   up -d 실패 · nginx 상태 조회 실패 · 떠 있는 nginx 의 reload 가 끝내 실패 · 떠 있지 않던 nginx 의 restart 실패 · 서버 안 확인 실패 → 기록된 커밋의 scripts/deploy.sh 를 git show 로 꺼내
           DEPLOY_REF=<그 SHA> AUTO_ROLLBACK=0 으로 자식으로 돌린다.  F 의 deploy.sh 가 망가졌어도 되돌릴 수 있다.
           L 의 스크립트가 서버 잠금을 직접 잡는 것이면(이 기능 이후 스크립트) 돌리기 전에 잠금을 풀고 자식이 다시 잡는다.
           잠금을 모르는 옛 스크립트면 부모가 잠금을 쥔 채 돌린다.  자식의 stderr 는 stdout 으로 합쳐 흐른다 — stderr 에는 부모의 결과 줄만 남는다
           L 시절의 판정(ADR-073) · build · 교체 · 서버 안 확인을 L 의 코드가 한다
조건       AUTO_ROLLBACK=1 이고 · 기록이 있고 · 기록이 이번에 올린 커밋과 다를 때만.
           push 배포는 늘 1, 손 배포(Actions)는 auto_rollback 입력대로, Session Manager 에서 손수 돌리면 꺼져 있다
```

```
종료 코드   뜻                                                   알림
0          성공                                                   — (밖에서 /health/ready 를 확인한다)
3          교체 뒤 실패했고, L 의 deploy.sh 가 직전 성공 커밋으로 되돌렸다  🟠 자동 롤백 성공 — 기록된 SHA 로 돈다
4          교체 뒤 실패했고, 못 되돌렸다                            🔴 서버가 알린 이유 — 서비스 상태를 모른다.  서버를 직접 본다
1          교체 전에 멈췄다 (판정 거절 · 잠금 · build · 마이그레이션 …)  🔴 배포 실패 — 서비스 상태를 확인한다
124        기다린 시간 안에 안 끝났다 · 명령을 보낸 뒤 상태 조회가 연속 네 번 실패(처음 읽기 전 포함)   🔴 서버는 아직 돌 수 있다 — 직접 본다
125        서버 명령이 취소됐거나 시간 초과                          🔴 직접 본다
```

서버가 stderr 로 줄 맨 앞에 결과 줄을 찍고 알림이 그 중 마지막 하나를 읽는다 — `되돌렸다 → <SHA> (L 의 deploy.sh)` · `되돌리지 않는다 — <이유>` · `되돌리기도 실패 — <이유>`.
(SSM 이 stdout 은 앞 24000자만 돌려줘서 끝에 찍는 줄이 잘린다. stderr 는 한도가 따로다.) `직전 성공 <SHA 또는 없음>` 은 맨 앞 stdout 첫 줄이다.

**4 가 되는 경우** — 자동 롤백이 꺼져 있다 · 직전 성공 기록이 없다(이 기능이 머지된 뒤 첫 성공 배포 전, 또는 기록 파일이 지워졌다) · 기록이 이번에 올린 커밋과 같다 ·
되돌리려는 커밋을 그 커밋에 `scripts/deploy.sh` 가 없다 · L 의 `deploy.sh` 가 0 이 아니게 끝났다(L 시절의 마이그레이션 판정 거절 포함 — 자식의 3 도 4 다). 이때 서버는 컨테이너를 바꿔 놓은 채다.

- **되돌려도 run 은 실패로 끝난다.** 되돌렸어도 이번에 올리려던 배포는 실패다. run 이 초록이면 실패한 커밋이 나간 것처럼 보인다. 알림은 🟠 「자동 롤백 성공」이다.
- **서버는 되돌아갔지만 브랜치 끝은 그대로다.** 되돌리는 PR 을 올리지 않으면 다음 머지가 같은 실패를 되풀이한다.
- **밖에서 안 닿는 것(DNS · 인증서 · IP)은 알림만 간다.** 코드를 되감아도 안 고쳐진다.
- **못 잡는 것** — 화면이 뜨지만 내용이 깨진 경우, 기능 버그(`/health/ready` 가 200 이면 안 걸린다). 응답 코드만 본다.
- **느린 시작도 실패로 본다.** 2초 × 30번 안에 둘 다 200 이 안 되면 멀쩡하지만 느린 판도 실패로 보고 되돌린다.
  손잡이는 `deploy.sh` 위쪽의 `READY_TRIES` · `READY_INTERVAL` 이다.
- **옛 버전을 올릴 때는 현재 워크플로로 올린다.** Actions → Deploy → Run workflow → `ref=<과거 SHA>`. 옛 run 을 re-run 하거나 옛 체크아웃의 `deploy.sh` 를
  손으로 돌리면 그 성공이 기록되지 않아, 그 뒤 실패했을 때 실제로 돌던 버전이 아니라 기록에 남은 더 앞 버전으로 되돌아간다.
- **L 이 이 기능보다 옛 스크립트면 서버 안 확인이 없다.** 그 스크립트의 0 은 「배포는 끝남」까지만 뜻한다. 3 이면 도는 밖 확인(Health check)이 「되돌렸는데 밖에서 안 닿음」으로 대신 알린다.
  #445 보다 옛 스크립트면 마이그레이션 판정도 없다.
- **잠금을 푼 순간부터 L 의 스크립트가 다시 잡을 때까지 틈이 있다** — L 이 이 기능 이후 스크립트일 때만이다(잠금을 모르는 옛 L 은 쥔 채 돌려서 틈이 없다).
  Actions 배포끼리는 `concurrency` 가 막고, Session Manager 로 손수 돌린 배포와 겹칠 때만 열린다.
- **DB 는 안 되감긴다.** 자동 롤백도 「되감을 때 (롤백)」과 같은 판정을 받는다.
- 운영에서 실제로 돌려 본 적은 아직 없다(ADR-078 「한계」).

## 열려 있는 포트

```
443  HTTPS  0.0.0.0/0     nginx.  교사가 실제로 쓰는 입구
80   HTTP   0.0.0.0/0     인증서 갱신 확인(ACME) 과 443 으로 보내기, 두 가지만 한다
```

**나머지는 전부 닫았다.**

```
22     SSH        닫음.  서버 접속은 Session Manager 로만
8000   backend    닫음.  nginx 의 업로드 10MB 제한을 우회한다
3000   frontend   닫음
5432   postgres   닫음
```

**80 은 열어 두어야 한다.** 닫으면 Let's Encrypt 가 도메인 소유를 확인하지 못해
인증서 갱신이 멈춘다. 대신 `/.well-known/acme-challenge/` 말고는 전부 443 으로 보낸다
— 교사가 http 로 들어와도 아동 실명이 평문으로 나가지 않는다 (ADR-004 · ADR-013).

---

## 손으로 배포

자동 배포가 막혔을 때 쓴다. **명령은 같다** — 같은 스크립트를 부른다.
`main` 이 아닌 브랜치는 Actions 에서 올린다(아래 「main 이 아닌 브랜치를 올릴 때」).
여기서 올릴 때는 `DEPLOY_REF` 를 붙인다 — **안 붙이면 `main` 이 올라간다.**

EC2 → 인스턴스 → **연결** → **Session Manager** 탭 → 연결

```bash
sudo -iu ubuntu
DEPLOY_REF=develop bash ~/ktc4-kangwon-2/scripts/deploy.sh   # 올릴 브랜치 · 커밋. 안 붙이면 main

cd ~/ktc4-kangwon-2
docker compose ps
curl -s -o /dev/null -w "ready %{http_code}\n" localhost/health/ready
```

**컨테이너 5개가 떠야 한다** — `db` · `backend` · `frontend` · `nginx` · `certbot`.

**서버 잠금.** `deploy.sh` 는 시작할 때 `/tmp/ssuksak-deploy.lock` 을 `flock` 으로 잡는다. 다른 배포(자동 · 손)가 돌고 있으면
**최대 5분 기다리다 서버를 바꾸지 않고 멈춘다(1).** 두 배포가 서버에서 겹쳐 컨테이너가 반쯤 바뀌는 것을 막는다.
손 배포를 5분 넘게 쥐고 있으면 그 사이 들어온 자동 배포는 멈춘다 — 끝나면 다시 돌린다.

**Session Manager 에서 손수 돌리면 자동 롤백이 꺼져 있다.** 교체 뒤 실패하면 끝에 `종료 코드 4` 와 「되돌리지 않는다 — 자동 롤백이 꺼져 있다」가 나온다.
켜려면 `AUTO_ROLLBACK=1 DEPLOY_REF=… bash ~/ktc4-kangwon-2/scripts/deploy.sh`. 첫 줄 「직전 성공 …」이 되돌아갈 곳이다.
**이 경로의 `deploy.sh` 는 서버에 지금 checkout 된 커밋의 것이다.** v2 이전 커밋이 올라가 있으면 옛 스크립트가 돌아 성공해도 기록되지 않는다 —
그때는 Actions 의 Run workflow 로 올린다.

**밖에서도 확인한다.**

```bash
curl -m 5 -o /dev/null -w "443   %{http_code}\n" https://ssample.duckdns.org/health/ready  # 200
curl -m 5 -o /dev/null -w "80    %{http_code}\n" http://ssample.duckdns.org/               # 301
curl -m 5 -o /dev/null -w "8000  %{http_code}\n" http://13.125.107.188:8000/health         # 시간 초과
curl -m 5 -o /dev/null -w "5432  %{http_code}\n" http://13.125.107.188:5432                # 시간 초과
```

### main 이 아닌 브랜치를 올릴 때

**Actions 에서 한다.** 손으로 서버에 들어갈 필요가 없다.

```
Actions → Deploy → Run workflow → ref 에 브랜치 이름 (예: develop) → Run
```

**`auto_rollback`** 은 기본이 꺼짐이다. 켜면 교체 뒤 실패했을 때 서버가 마지막 성공 배포로 되돌린다(위 「자동 롤백」).
`push` 배포는 이 입력과 상관없이 늘 켜져 있다. 손으로 옛 SHA 를 올리는 롤백에 켜면, 그 SHA 마저 실패할 때 마지막 성공 배포로 한 번 더 간다.

`push` 로 들어온 배포는 push 된 그 커밋을 올린다. 고를 수 있는 건 손으로 돌릴 때뿐이다.
**브랜치 이름을 넣어도 배포가 시작될 때 그 브랜치의 끝 커밋 SHA 하나로 고정해서 올린다.**
**서버로 가는 `deploy.sh` 는 Run workflow 의 「Use workflow from」 브랜치 것이다(기본 develop). `ref` 는 올릴 커밋일 뿐이다.**

**전에는 브랜치 이름을 서버에 그대로 넘겼다.** 서버는 도는 순간의 브랜치 끝을 올려서, 앞 배포가
서버에 닿기 전에 머지가 또 들어오면 앞 run 이 뒤 커밋을 자기 이름으로 올렸다(2026-11-04 에 4번).
기록과 실제 운영이 달랐다.

**전에는 `deploy.sh` 가 `main` 을 박아 두었다.** 그래서 손으로 develop 을 올려 둔 서버에
자동 배포를 한 번 돌리면 조용히 main 으로 되돌아갔고, 무엇이 돌고 있는지 아무도 몰랐다.
2026-10-20 에 `DEPLOY_REF` 로 받게 고쳤다.

**치울 필요가 없다.** 다음 자동 배포가 돌면 그 커밋으로 돌아온다.
마이그레이션으로 생긴 표는 남지만 옛 코드는 그 표를 읽지 않아 문제가 없다 — **지우지 않는다.**
단, 올려 둔 브랜치에만 있는 마이그레이션이 DB 에 올라갔다면 `deploy.sh` 가 되돌아가기 전에 멈춘다
(그 마이그레이션을 들여온 PR 의 머지 직전 커밋이 아닌 한) — 다음의 「되감을 때 (롤백)」과 같은 판정이다.

### 되감을 때 (롤백)

나쁜 배포가 나가면 **직전 커밋 SHA 로 다시 배포한다.** 같은 길이다 — 롤백 전용 길을
따로 두지 않는다. 평소에 안 쓰는 길은 정작 급할 때 안 돈다.
교체 뒤 서버 안에서 안 살아난 배포는 위 「자동 롤백」이 이 길을 대신 간다.

**⚠️ `docker-compose.server.yml` 이 없는 커밋으로 되감기 전에는** 서버 `.env` 의
`COMPOSE_FILE` 줄을 지우고, 배포 디렉터리에서 `sudo docker compose config --quiet` 가
성공하는지 확인한 뒤 workflow_dispatch 를 돌린다. 다시 켤 때는 그 파일이 들어간 배포가
끝난 뒤 「서버 로그」의 켜는 순서를 따른다.

```
Actions → Deploy → Run workflow → ref 에 직전 커밋 SHA → Run
```

**서버로 가는 `deploy.sh` 는 Run workflow 의 「Use workflow from」 브랜치 것이다(기본 develop). `ref` 는 올릴 커밋일 뿐이다.**

직전에 무엇이 돌았는지는 두 군데서 본다.

```bash
# 1. Actions 의 배포 기록 — 「배포 <ref> <sha> — <제목>」이 찍혀 있다
# 2. 서버에서
sudo -u ubuntu git -C /home/ubuntu/ktc4-kangwon-2 log --oneline -5
```

**DB 는 안 되감긴다.** 마이그레이션은 앞으로만 간다. 그래서 `deploy.sh` 는 **checkout 하기 전에**
DB 가 서 있는 리비전을 읽고(지금 도는 backend 이미지로, 앱이 쓰는 `DATABASE_URL` 그대로) 이 커밋을 올려도 되는지 정한다 (ADR-073).

| 올리는 커밋 | `deploy.sh` 가 한다 |
|---|---|
| DB 리비전 파일을 가진 커밋 — 평소 배포 · 같은 SHA 다시 · 마이그레이션 없는 PR 만 건너는 되감기 | 평소대로 `alembic upgrade head` |
| DB 리비전을 **들여온 머지의 직전 커밋** — main 이면 그 develop→main 머지의 직전 main(main 배포 하나를 건너는 되감기), develop 이면 그 PR 머지의 직전 develop(마이그레이션이 든 PR **하나**를 건너는 되감기) | `alembic upgrade` 를 건너뛰고 올린다. 로그에 「마이그레이션을 건너뛴다 …」 |
| 그 밖 — 둘 이상을 건너뜀 · 다른 브랜치 · main 도 develop 도 모르는 리비전 · DB 리비전을 하나로 못 읽음 | **checkout 전에 멈춘다.** 서버 폴더 · 이미지 · 컨테이너는 그대로, 로그에 이유 한 줄 |

**머지 직전 커밋뿐인 이유.** CI `backend (rollback compat)` 가 마이그레이션이 든 PR 마다
(main · develop 으로 가는 PR 둘 다, ADR-094) 「머지 직전 코드가 이 PR 의 새 DB 에서 도는가」를 backend pytest 로 시험한다.
시험한 조합은 그 하나라서 건너뛰어도 되는 곳도 그 직전 커밋 하나다. main 규칙에는 필수 검사가 없어 main 쪽은 경고등이다 —
develop→main PR 을 머지하기 전에 이 검사를 본다. 옛 코드가 쓰는 열을 지우거나 제약을 거는 PR 은 이 검사가 빨개져
머지 전에 알고, 이미 있는 마이그레이션을 고치거나 지운 PR 도 같은 검사가 막는다.
**그래도 열을 지우거나 이름을 바꾸는 변경은 두 단계로 나눠 올린다**(먼저 안 쓰게 하고, 다음 판에서 지운다).

**건너뛴 로그가 보여도 `ready 200` 만으로는 모른다.** 이 검사는 빈 DB 에서 돈다 — 새 코드가 쓴 데이터를 옛 코드가
읽는지는 안 본다. 한계는 ADR-073 · `docs/evaluation/09-deployment.md`.

**멈췄을 때.** 예전에는 `Can't locate revision identified by '…'` 로 `alembic upgrade` 에서 죽었고(멘토 지적 #210)
그때는 작업 폴더가 이미 옛 코드였다. 지금은 checkout 전에 멈추므로 폴더도 이미지도 지금 도는 코드 그대로다.
이때는 둘 중 하나다.

```
① 현재 DB 리비전을 가진 커밋(그 마이그레이션이 들어간 뒤의 커밋)을 고르거나,
   멈춘 이유에 적힌 커밋 B 로 되감는다 — DB 리비전을 들여온 PR 의 머지 직전 커밋이다
② 그보다 더 이전 커밋이 꼭 필요하면, 아래 조건을 확인한 뒤 DB 를 목표 리비전까지 내리고 배포한다
```

②는 마지막 수단이고 **데이터가 지워질 수 있다.** 먼저 DB 를 백업하고, 목표 커밋의 마이그레이션 head 와
현재 DB 리비전을 확인한다. **현재 DB 리비전 파일을 포함한 코드의 이미지로** 실행해야 한다.
옛 코드를 checkout 한 서버(옛 `deploy.sh` 로 멈춘 뒤)의 이미지로 `downgrade` 를 실행하면
현재 리비전을 찾지 못한다.

```bash
# 현재 DB 리비전 파일을 포함한 코드에서 실행한다. 기존 컨테이너는 교체하지 않는다.
sudo docker compose build backend
sudo docker compose run --rm backend alembic current
sudo docker compose run --rm backend alembic history
```

그 코드의 `downgrade()` 를 모두 검토한 뒤 `alembic downgrade` 에 **목표 리비전 ID 를
명시**한다. 커밋 사이에 여러 마이그레이션이 있으면 `-1` 한 번으로는 부족하다.
주간계획안 마이그레이션은 주간 데이터가 남아 있으면 내려가지 않도록 막혀 있다.
검토 없이 데이터를 지워 우회하지 않는다. DB 를 내린 뒤에는 목표 커밋으로 다시 배포하고
`/health/ready` 와 핵심 문서 생성 경로를 확인한다.

### 순서에 이유가 있다

```
서버 잠금            배포가 서버에서 겹치지 않게 flock 을 먼저 잡는다.  ubuntu 로 도는 쪽에서만 잡는다.  5분
직전 성공 읽기        서버가 기억한 마지막 성공 커밋(자동 롤백이 돌아갈 곳)을 읽어 첫 줄에 찍는다
마이그레이션 판정    checkout 전에 DB 리비전을 읽고 이 커밋을 올려도 되는지 정한다.  안 되면 서버를 안 바꾸고 멈춘다 (ADR-073)
git reset --hard    서버에서 직접 고친 파일이 있어도 배포하는 ref 가 정답이다
파일 확인            fetch 가 실패해도 reset 은 성공한다.  옛 origin/main 이 남아 있어서
                    2026-09-22 에 13일 전 커밋으로 되감겼고, 그 커밋엔 docker-compose.yml 이 없었다
nginx -t            build · 교체 전에 nginx 설정을 검사한다.  깨졌으면 여기서 멈춘다
build               이미지를 먼저 만든다
alembic upgrade     마이그레이션이 앱보다 먼저.  반대면 새 코드가 없는 컬럼을 읽는다.  한 칸 롤백이면 건너뛴다
up -d               그다음에 교체
nginx reload        nginx 는 다시 만들지 않으면 새 설정을 안 읽는다.  배포 때 reload 로 읽힌다.  접속은 안 끊기고, 떠 있는 nginx 는 다시 시작하지 않는다
                    이 스크립트에서 그렇다.  직전 성공 커밋의 옛 deploy.sh 로 되돌릴 때는 그 스크립트가 restart 할 수 있다
서버 안 확인         127.0.0.1 로 /health/ready 와 / 를 물어 둘 다 200 이어야 넘어간다.  안 되면 직전 성공 커밋으로 되돌린다 (ADR-078)
기록                 서버 안 확인을 통과한 커밋을 「마지막 성공」으로 적는다
image prune         t3.medium 이 50GB 고정이라 옛 이미지가 쌓이면 디스크가 찬다.  살아난 판에서만 지운다.  실패해도 결과는 안 바뀐다
```

`/health` 가 아니라 `/health/ready` 를 본다. **`/health` 는 DB 를 안 보고 200 을 준다**(ADR-011).
DB 가 죽어도 배포 성공으로 읽힌다 — 5주차에 멘토가 지적한 부분이다.

---

## 서버에 한 번만 해둘 것

```bash
sudo -iu ubuntu
git clone https://github.com/kakaotechcampus-4/ktc4-kangwon-2.git
cd ktc4-kangwon-2
cp .env.example .env
```

**원격은 HTTPS 다.** 저장소가 공개라 읽기에 인증이 필요 없다.
SSH 원격이면 서버에 GitHub 키를 따로 관리해야 한다.

**DB 볼륨이 이미 있으면 비밀번호를 새로 정하면 안 된다.** `postgres` 는 볼륨을 처음
만들 때 비밀번호를 굳힌다. 나중에 `.env` 만 바꿔도 안 바뀐다.

```bash
PW=$(docker exec ktc4-kangwon-2-db-1 printenv POSTGRES_PASSWORD)
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${PW}|" .env
sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg://ssuksak:${PW}@db:5432/ssuksak|" .env
sed -i "s|^IS_SERVER=.*|IS_SERVER=1|" .env
```

`IS_SERVER=1` 이어야 한다. `CLAUDE.md` 의 「로컬에서 `real` 모드 금지」가 이 값으로 판정한다.

**`.env` 는 커밋하지 않으므로 서버에만 있다.**

### AWS CLI — 백업을 S3 로 보내려면

**`/usr/bin/aws` 에 둔다.** 백업은 root cron 이 돌리고, cron 의 PATH 는 `/usr/bin:/bin` 뿐이다.
`backup.sh` 는 PATH 를 따로 정하지 않는다 — 다른 자리에 깔면 손으로 돌릴 때는 되고 **새벽 cron 에서만**
`aws: command not found` 가 난다(2026-10-21 까지 실제로 그랬다).

- 공식 번들을 쓴다. **apt · snap 을 쓰지 않는다** — snap 은 `/snap/bin` 이라 cron 이 못 찾고,
  apt 는 운영 중에 다른 패키지 · 서비스 재시작을 건드릴 수 있다.
- 서버에 `unzip` 이 없다. `python3` 의 `zipfile` 로 풀되 **실행 권한을 지킨다**(기본 `extract` 는 권한을 버린다).
- 키를 넣지 않는다. EC2 역할(`ktc-ec2-ssm-role`)로 인증한다.

```bash
# root 로 (sudo -i). 2026-10-21 에 설치한 판은 2.38.3
d=$(mktemp -d) && cd "$d"
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o awscliv2.zip
python3 - <<'PY'
import os, stat, zipfile
with zipfile.ZipFile("awscliv2.zip") as z:
    for i in z.infolist():
        mode = i.external_attr >> 16
        if stat.S_ISLNK(mode):
            os.makedirs(os.path.dirname(i.filename) or ".", exist_ok=True)
            os.symlink(z.read(i).decode(), i.filename)
        else:
            p = z.extract(i, ".")
            if not i.is_dir() and mode & 0o777:
                os.chmod(p, mode & 0o7777)
PY
./aws/install --install-dir /usr/local/aws-cli --bin-dir /usr/bin
cd / && rm -rf "$d"

# cron 과 같은 조건으로 확인 — ktc-ec2-ssm-role 이 나와야 한다
env -i PATH=/usr/bin:/bin HOME=/root aws sts get-caller-identity --query Arn --output text
```

### 서버 로그 — 배포 뒤에도 남기려면

배포마다 backend 컨테이너를 새로 만들어 json-file 로그가 사라진다(2026-10-22 확인).
운영 서버는 journald 에 남긴다(ADR-058).

**켜는 순서 (한 번만)** — 이 변경이 들어간 배포가 **끝난 뒤에** 한다.

① 서버 `.env` 에 한 줄을 넣는다.

```text
COMPOSE_FILE=docker-compose.yml:docker-compose.server.yml
```

**⚠️ ① 을 배포 전에 넣지 않는다.** 서버에 아직 없는 파일을 가리켜 `docker compose` 명령이
전부 실패한다. 밤 백업(`scripts/backup.sh` 도 `docker compose` 를 쓴다)까지 멈춘다.

② backend 를 다시 만들고 ③ 로그 드라이버를 확인한다.

```bash
sudo docker compose up -d backend
sudo docker inspect "$(sudo docker compose ps -q backend)" --format '{{.HostConfig.LogConfig.Type}}'  # journald
```

바꾸는 순간 지금 컨테이너의 json-file 로그는 마지막으로 한 번 사라진다. 남기려면 ② 전에
`sudo docker compose logs backend --no-color > backend-before-journald.log` 로 떠 둔다.
사용자 ID 가 들어 있으니 서버 밖으로 옮기지 않는다.

**보존 30일 (한 번만).** 서버 전체 journal 에 걸린다. 용량 상한은 기본값(파일시스템 10%, 최대 4G)이다.
파일 단위로 지워서 30일보다 조금 더 남을 수 있다.

```bash
sudo mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nMaxRetentionSec=30day\n' | sudo tee /etc/systemd/journald.conf.d/ssample.conf
sudo systemctl restart systemd-journald
```

**읽는 법:**

```bash
sudo journalctl CONTAINER_TAG=ssample-backend --since -24h -o cat --no-pager | grep unexpected_error
bash scripts/llm-usage.sh
```

되돌리려면 ① 의 줄을 지우고 `sudo docker compose up -d backend` 를 돌린다.
파일이 없는 커밋으로 되감을 때는 「되감을 때 (롤백)」의 경고를 먼저 본다.
로컬에서는 켜지 않는다 — OrbStack · Docker Desktop 에는 journald 가 없다.

---

## HTTPS · 도메인

```
도메인     ssample.duckdns.org    DuckDNS 무료. 토큰으로 IP 를 갱신한다
인증서     Let's Encrypt          certbot 컨테이너가 12시간마다 보고 만료 30일 전부터 갱신
reload    nginx 가 6시간마다      갱신된 인증서를 읽으려면 다시 읽혀야 한다. 접속은 안 끊긴다
```

**처음 한 번은 `scripts/https-setup.sh` 가 발급한다.** 자체 서명 인증서를 먼저 만들어
nginx 를 띄우고(인증서가 없으면 nginx 가 아예 안 뜬다), 도메인이 이 서버를 가리키는지
확인한 뒤 진짜 인증서를 받는다. **Let's Encrypt 는 한 시간에 5번만 발급해 준다** —
확인 없이 돌리면 실패만 쌓이고 한 시간을 기다려야 한다.

**만료일 확인:**

```bash
echo | openssl s_client -connect ssample.duckdns.org:443 \
  -servername ssample.duckdns.org 2>/dev/null | openssl x509 -noout -dates
```

**내 컴퓨터에서는 인증서가 없다.** `nginx.conf` 가 가리키는 파일이 서버에만 있어서
`docker compose up` 이 통째로 막힌다. `scripts/local-cert.sh` 를 한 번 돌린다.
로컬은 80 에 `localhost` 전용 블록이 있어 평문으로 쓴다 — `http://localhost`.

---

## 배포가 실패하면

**먼저 어느 단계에서 멈췄는지 본다.** 원인이 다르다.

```
AWS 자격증명 설정 에서 실패     인증 문제.  AWS_ACCOUNT_ID Variable 을 본다
배포 스텝의 「배포 종료 코드」   이 스텝은 늘 초록이다 — 코드는 로그 끝줄과 「서버 출력」 · 「서버 오류」를 본다
                              1  교체 전에 멈췄다 (판정 거절 · 잠금 · build · 마이그레이션 …).  명령을 못 보냈거나 상태를 못 읽었을 때도 1
                              3  교체 뒤 실패했고 서버가 마지막 성공 커밋으로 되돌렸다 → 「서버 오류」 끝의 「되돌렸다 → SHA」
                              4  교체 뒤 실패했고 못 되돌렸다 → 「서버 오류」 끝의 「되돌리지 않는다 — 이유」 · 「되돌리기도 실패 — 이유」.  서버를 직접 본다
                              124 47분 안에 안 끝났다, 또는 명령을 보낸 뒤 상태 조회가 연속 네 번 실패했다(처음 읽기 전 포함, 세 번 다시 물어도 안 됨 — 네트워크 · throttling).
                                  「상태 InProgress」면 서버는 아직 돈다 — 끝나기 전에 다시 배포하지 않는다
                              125 서버 명령이 취소됐거나 시간 초과
Health check 에서 실패         서버 안은 deploy.sh 가 이미 살아난 것을 봤다 — 확인할 주소가 틀렸거나 DNS · 인증서 문제다.
                              로그의 「확인할 주소」 줄과 HEALTHCHECK_URL secret 을 본다.  이것만으로는 되돌리지 않는다
배포 판정 에서 실패            배포 코드가 0 이 아니다 — 되돌렸어도(3) run 은 일부러 실패로 남긴다
```

배포가 서버에서 겹쳤다면 `deploy.sh` 로그에 「잠금을 못 잡았다」가 찍힌다(1) — 앞 배포가 5분 넘게 돈 것이다. 서버를 바꾸지 않았다.

**서버가 SSM 에 붙어 있나 확인:**

```bash
aws ssm describe-instance-information --region ap-northeast-2 \
  --query 'InstanceInformationList[].{id:InstanceId,ping:PingStatus}' --output table
```

`Online` 이어야 한다.

**서버 출력은 stdout 앞 24000자, stderr 8000자까지만 온다.** 그래서 `docker compose build` 출력은 서버 파일(`/tmp/ssuksak-build.log`)로 돌리고
(실패하면 끝 40줄만 보인다), 결과 줄은 stderr 로 찍는다. 전문이 필요해지면 SSM 결과를 S3 로 내보내는 설정을 붙인다. 아직 필요한 적이 없어 안 붙였다.

**기다리는 동안 러너 로그에는** `대기 — 상태 InProgress (12/280)` 한 줄이 상태가 바뀔 때와 6번째 조회마다(약 1분) 찍힌다. 서버 출력 자체는 명령이 끝난 뒤 한 번에 온다.

---

## 서버 점검

`scripts/server-check.sh` — 배포 · 백업 · 인증서가 의도대로 걸려 있고 **실제로 돌았는지** 본다.
**읽기만 한다.** 서비스 · 설정 · DB · 인증서 · 백업을 바꾸지 않는다.

```bash
# Session Manager 로 들어가서
sudo -iu ubuntu
cd ~/ktc4-kangwon-2 && bash scripts/server-check.sh
```

```
OK     기계가 가를 수 있는 것 — 통과
FAIL   위와 같은데 실패. 하나라도 있으면 종료 코드 1
--     사람이 보고 판단할 것 (cron · certbot · nginx reload · 백업 로그)
```

**결과는 돌린 터미널에만 나온다.** 알림으로 가지 않는다. 이슈에 붙이기 쉽게 crontab 원문은 찍지 않는다 —
백업 cron 줄은 아래 「백업」의 줄과 **같은지만** 보여 주고(같으면 `s3://` 주소까지), 변수 줄은 이름만 찍는다.
**백업 로그 끝 6줄은 원문이다** — 붙이기 전에 한 번 본다.

**서버 소스는 main 이나 develop 끝과 같으면 통과다.** 배포는 브랜치 · 커밋을 고를 수 있어서(「main 이 아닌
브랜치를 올릴 때」) 둘 다 아니면 실패가 아니라 `--` 로 알린다 — 그 뒤 머지가 있었거나 커밋으로 되감은 것이다.
**보는 것은 git HEAD 지 도는 컨테이너가 아니다.** 빌드가 실패하면 옛 컨테이너가 돌아도 HEAD 는 새 커밋이다 —
그건 Actions 배포 기록이 알려 준다.

**언제 · 누가 돌리나 (제안)**

```
배포한 뒤                        배포한 사람
인증서 첫 실제 갱신 뒤 (약 12/05)   한 번 — 만료일이 늘었고 nginx 가 새 인증서를 내주는지
한 달에 한 번                    「백업이 살아 있는지 확인」과 같이
```

---

## 안 만든 것

**GHCR 이미지 푸시** — 서버에서 직접 빌드한다. 빌드 머신이 따로 없어 단계가 줄어든다.
`t3.medium`(4GB)에서 Next.js 빌드가 메모리로 실패하면 그때 옮긴다.
증상은 `docker compose build` 가 `Killed` 로 끝나는 것이다.

**무중단 배포** — `docker compose up -d` 가 컨테이너를 바꾸는 몇 초 동안 끊긴다.
파일럿 규모에서 문제가 아니다.

**마이그레이션만 성공하고 앱이 실패한 경우의 복구** — DB 는 새 구조인데 앱은 옛 버전이
된다. 코드는 되돌려도 DB 는 안 돌아간다. `alembic downgrade` 를 자동으로 걸지 않은 이유는
잘못 돌면 데이터가 날아가서다. 사람이 판단한다. 자동 롤백도 코드만 되돌린다.

---

## 백업

파일럿(10/19) 전에 걸어야 한다(ADR-006).

```bash
sudo crontab -e
15 18 * * * BACKUP_S3_URI=s3://ktc4-kangwon-2-backup/backup /home/ubuntu/ktc4-kangwon-2/scripts/backup.sh >> /var/log/ssuksak-backup.log 2>&1
```

**시각은 UTC 다.** 서버 cron 이 UTC 로 돌아서 `15 18` 이 한국 새벽 3시 15분이다(`scripts/backup.sh` 머리 주석).

**이 줄을 바꾸면 `scripts/server-check.sh` 의 `BACKUP_CRON_RE` 도 같이 바꾼다.** 점검이 서버 줄을 이 줄과 비교한다.

백업 파일은 root 소유로 쌓인다(cron 이 root 다). **손으로 돌릴 때도 `sudo` 를 붙인다.**

**`scripts/backup.sh` 를 쓴다.** cron 에 `pg_dump` 한 줄을 직접 적지 않는다 — 그 한 줄은
`pg_dump` 가 실패해도 `gzip` 이 성공해서 **빈 파일을 백업이라고 남긴다.** 스크립트는 그걸 본다.

**S3 로도 보낸다** — 버킷 `ktc4-kangwon-2-backup`(서울, 2026-10-21 만듦). 공개 차단 · SSE-S3 암호화 ·
HTTPS 전용 정책 · `backup/` 은 90일 뒤 지운다(수명 주기). EC2 역할에 `PowerUserAccess` 가 있어 키 없이 쓴다.
**같은 디스크에만 두면 디스크가 죽을 때 백업도 같이 죽는다.**

- 서버에 `aws` 가 `/usr/bin` 에 있어야 한다 — 「서버에 한 번만 해둘 것」의 AWS CLI.
- `BACKUP_S3_URI` 는 **한 곳에만** 둔다. 위처럼 cron 줄에 두면 `.env` 보다 먼저 읽힌다. `.env` 에 둬도 읽는다.
- **S3 가 실패하는 날은 로컬 백업은 남지만 14일 정리가 그날 안 돈다**(`aws` 에서 스크립트가 끝난다).
  로그에서 `backup ok` 다음 줄이 `s3 ok` 인지 본다 — `server-check.sh` 가 끝 6줄을 보여 준다.
- 옛 문서의 `ktc4-kangwon-2-rag` 는 계정에 없는 버킷이었다.

### 백업이 살아 있는지 확인 — 한 달에 한 번

```bash
scripts/restore-check.sh /home/ubuntu/backup/ssuksak_20261014_031500.sql.gz
```

버리는 DB 에 복구해 보고 지운다. **쓰던 DB 를 건드리지 않는다.** 표가 다 왔는지, alembic
head 가 운영과 같은지, 복구본에 **새 행이 들어가는지**(시퀀스)까지 본다.

```
restore-check ok  /home/ubuntu/backup/ssuksak_20261014_031500.sql.gz
  alembic  2652c5dee127 (운영 2652c5dee127)
  행       centers=3 users=3 plans=2 documents=1
```

### 진짜로 되돌려야 할 때

**쓰던 DB 에 백업을 그대로 붓지 않는다.** `CREATE TABLE` 이 「already exists」로 줄줄이
실패하는데 `psql` 은 그걸 넘기고 **0 으로 끝난다.** 2026-10-14 에 해 봤다 — 오류 105줄이
나면서 **아무것도 복구되지 않았는데 명령은 성공한 것처럼 끝났다.**

**두 경우가 다르다.** `ssuksak` 이 **살아 있는데 내용이 틀어진** 경우와, **아예 없는**
경우다. 1번과 5번이 갈린다.

```bash
# 0  어느 경우인지 먼저 본다
docker compose exec -T db psql -U ssuksak -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='ssuksak';"
#    1 이 나오면 → 1번부터.  아무것도 안 나오면 → 2번부터 (1번과 5번 앞줄을 건너뛴다)

# 1  [DB 가 살아 있을 때만] 지금 것부터 백업한다
#    복구가 틀렸을 때 돌아올 자리가 없으면 두 번 잃는다
#    **sudo 로 돈다.** cron 이 root 로 돌아서 /home/ubuntu/backup 이 root 소유다 —
#    ubuntu 로 그냥 돌리면 파일을 못 만들고 여기서 멈춘다
sudo scripts/backup.sh

# 2  받을 빈 DB 를 따로 만든다
docker compose exec -T db psql -U ssuksak -d postgres \
  -c 'CREATE DATABASE ssuksak_restore OWNER ssuksak;'

# 3  파일부터 성한지 본다. **잘린 gzip 도 앞부분은 멀쩡히 풀린다**
gzip -t <파일>

#    붓는다. ON_ERROR_STOP=1 과 pipefail 을 둘 다 붙인다
#    pipefail 이 없으면 gunzip 이 중간에 죽어도 psql 의 성공만 보고 넘어간다
#    **여기서 실패하면 멈춘다.** 덜 들어간 DB 를 끼우면 교사 기록이 조용히 사라진다
set -o pipefail
gunzip -c <파일> | docker compose exec -T db psql -U ssuksak -d ssuksak_restore \
  -v ON_ERROR_STOP=1

# 4  **끼울 그 DB 를 검사한다.** 파일만 검사하면 안 된다 —
#    파일은 멀쩡한데 3번이 덜 들어간 경우를 못 본다
scripts/restore-check.sh --db ssuksak_restore

# 5  바꿔 끼운다. **연결이 남아 있으면 RENAME 이 안 된다** — 백엔드를 먼저 멈춘다
docker compose stop backend

#    [DB 가 살아 있을 때만] 망가진 것을 옆으로 치운다. 없으면 이 줄을 건너뛴다
docker compose exec -T db psql -U ssuksak -d postgres \
  -c 'ALTER DATABASE ssuksak RENAME TO ssuksak_broken_'"$(date +%Y%m%d)"';'

docker compose exec -T db psql -U ssuksak -d postgres \
  -c 'ALTER DATABASE ssuksak_restore RENAME TO ssuksak;'
docker compose start backend
curl -f https://ssample.duckdns.org/health/ready

# 6  **망가진 DB 를 바로 지우지 않는다.** 며칠 두고 본 뒤에 지운다
```
