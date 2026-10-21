# 배포

**`main` 에 머지되면 자동으로 올라간다.** 손으로도 같은 스크립트를 돌릴 수 있다.

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
main 에 push
  ↓
OIDC 로 AWS 인증                  키 없음
  ↓
scripts/deploy.sh 를 통째로 보냄   aws ssm send-command
  ↓
서버가 그 스크립트를 실행           git reset → build → migrate → up -d
  ↓
끝날 때까지 기다림                  최대 20분.  안 기다리면 실패해도 초록불이 뜬다
  ↓
/health/ready 200 확인
```

**서버에서 도는 명령은 `scripts/deploy.sh` 한 곳에만 있다.** 워크플로가 그 파일을
보낼 뿐이라, 자동과 수동이 같은 명령을 돈다. 두 곳에 나눠 적으면
「손으로는 되는데 CI 는 안 된다」가 생긴다.

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

`push` 로 들어온 배포는 늘 `main` 이다. 고를 수 있는 건 손으로 돌릴 때뿐이다.

**전에는 `deploy.sh` 가 `main` 을 박아 두었다.** 그래서 손으로 develop 을 올려 둔 서버에
자동 배포를 한 번 돌리면 조용히 main 으로 되돌아갔고, 무엇이 돌고 있는지 아무도 몰랐다.
2026-10-20 에 `DEPLOY_REF` 로 받게 고쳤다.

**치울 필요가 없다.** `main` 에 머지되는 순간 자동 배포가 돌아 `main` 으로 되돌아온다.
마이그레이션으로 생긴 표는 남지만 옛 코드는 그 표를 읽지 않아 문제가 없다 — **지우지 않는다.**

### 되감을 때 (롤백)

나쁜 배포가 나가면 **직전 커밋 SHA 로 다시 배포한다.** 같은 길이다 — 롤백 전용 길을
따로 두지 않는다. 평소에 안 쓰는 길은 정작 급할 때 안 돈다.

```
Actions → Deploy → Run workflow → ref 에 직전 커밋 SHA → Run
```

직전에 무엇이 돌았는지는 두 군데서 본다.

```bash
# 1. Actions 의 배포 기록 — 「배포 <ref> <sha> — <제목>」이 찍혀 있다
# 2. 서버에서
sudo -u ubuntu git -C /home/ubuntu/ktc4-kangwon-2 log --oneline -5
```

**DB 는 안 되감긴다.** 마이그레이션은 앞으로만 간다. 옛 코드가 새 표를 읽지 않으니
대개 문제가 없지만, **열을 지우거나 이름을 바꾼 마이그레이션이 섞여 있으면 되감아도
안 돈다.** 그런 변경은 두 단계로 나눠 올린다(먼저 안 쓰게 하고, 다음 판에서 지운다).

### 순서에 이유가 있다

```
git reset --hard    서버에서 직접 고친 파일이 있어도 배포하는 ref 가 정답이다
파일 확인            fetch 가 실패해도 reset 은 성공한다.  옛 origin/main 이 남아 있어서
                    2026-09-22 에 13일 전 커밋으로 되감겼고, 그 커밋엔 docker-compose.yml 이 없었다
build               이미지를 먼저 만든다
alembic upgrade     마이그레이션이 앱보다 먼저.  반대면 새 코드가 없는 컬럼을 읽는다
up -d               그다음에 교체
image prune         t3.medium 이 50GB 고정이라 옛 이미지가 쌓이면 디스크가 찬다
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

**먼저 어느 단계에서 멈췄는지 본다.** 넷은 원인이 다르다.

```
AWS 자격증명 설정 에서 실패     인증 문제.  AWS_ACCOUNT_ID Variable 을 본다
배포 명령 보내기 에서 실패      권한·서버 문제.  서버가 SSM 에 붙어 있나
끝날 때까지 기다린다 에서 실패   서버에서 명령이 터졌거나, 20분 안에 안 끝났다.  그 스텝의 「서버 출력」을 읽는다
                              「상태 InProgress」면 서버는 아직 돈다 — 끝나기 전에 다시 배포하지 않는다
Health check 에서 실패         앱이 안 뜨거나, 확인할 주소가 틀렸다.  서버에서 docker compose ps,
                              로그의 「확인할 주소」 줄과 HEALTHCHECK_URL secret 을 본다
```

**서버가 SSM 에 붙어 있나 확인:**

```bash
aws ssm describe-instance-information --region ap-northeast-2 \
  --query 'InstanceInformationList[].{id:InstanceId,ping:PingStatus}' --output table
```

`Online` 이어야 한다.

**서버 출력은 24000자에서 잘린다.** 전문이 필요해지면 SSM 결과를 S3 로 내보내는
설정을 붙인다. 아직 필요한 적이 없어 안 붙였다.

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

**결과는 돌린 터미널에만 나온다.** 알림으로 가지 않는다. 이슈에 붙이기 쉽게 crontab 원문은 찍지 않고
꼴을 확인한 조각(시각 · 사용자 · 변수 이름 · `BACKUP_S3_URI` 의 `s3://` 주소)만 찍는다.
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
잘못 돌면 데이터가 날아가서다. 사람이 판단한다.

**`nginx.conf` 만 바뀐 배포** — 이미지가 같아서 컨테이너가 교체되지 않을 수 있다.
`docker compose restart nginx` 를 친다.

---

## 백업

파일럿(10/19) 전에 걸어야 한다(ADR-006).

```bash
sudo crontab -e
15 18 * * * BACKUP_S3_URI=s3://ktc4-kangwon-2-backup/backup /home/ubuntu/ktc4-kangwon-2/scripts/backup.sh >> /var/log/ssuksak-backup.log 2>&1
```

**시각은 UTC 다.** 서버 cron 이 UTC 로 돌아서 `15 18` 이 한국 새벽 3시 15분이다(`scripts/backup.sh` 머리 주석).

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
