# 배포

**`main` 에 머지되면 자동으로 올라간다.** 손으로도 같은 스크립트를 돌릴 수 있다.

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
80   HTTP   0.0.0.0/0     nginx.  유일한 입구
```

**나머지는 전부 닫았다.**

```
22     SSH        닫음.  서버 접속은 Session Manager 로만
8000   backend    닫음.  nginx 의 업로드 10MB 제한을 우회한다
3000   frontend   닫음
5432   postgres   닫음
```

---

## 손으로 배포

자동 배포가 막혔을 때만 쓴다. **명령은 같다** — 같은 스크립트를 부른다.

EC2 → 인스턴스 → **연결** → **Session Manager** 탭 → 연결

```bash
sudo -iu ubuntu
bash ~/ktc4-kangwon-2/scripts/deploy.sh

cd ~/ktc4-kangwon-2
docker compose ps
curl -s -o /dev/null -w "ready %{http_code}\n" localhost/health/ready
```

**컨테이너 4개가 떠야 한다** — `db` · `backend` · `frontend` · `nginx`.

**밖에서도 확인한다.**

```bash
curl -m 5 -o /dev/null -w "80    %{http_code}\n" http://15.165.19.41/health/ready   # 200
curl -m 5 -o /dev/null -w "8000  %{http_code}\n" http://15.165.19.41:8000/health    # 시간 초과
curl -m 5 -o /dev/null -w "5432  %{http_code}\n" http://15.165.19.41:5432           # 시간 초과
```

### 순서에 이유가 있다

```
git reset --hard    서버에서 직접 고친 파일이 있어도 main 이 정답이다
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

---

## 배포가 실패하면

**먼저 어느 단계에서 멈췄는지 본다.** 셋은 원인이 다르다.

```
AWS 자격증명 설정 에서 실패     인증 문제.  AWS_ACCOUNT_ID Variable 을 본다
배포 명령 보내기 에서 실패      권한·서버 문제.  서버가 SSM 에 붙어 있나
끝날 때까지 기다린다 에서 실패   서버에서 명령이 터졌다.  그 스텝의 「서버 출력」을 읽는다
Health check 에서 실패         배포는 됐는데 앱이 안 뜬다.  서버에서 docker compose ps
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

## 안 만든 것

**롤백 자동화** — `git reset --hard <이전 커밋>` 후 다시 돌리면 된다.

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

파일럿(10/19) 전에 걸어야 한다(ADR-006). 아직 안 걸었다.

```bash
0 3 * * * docker exec ktc4-kangwon-2-db-1 pg_dump -U ssuksak ssuksak | gzip \
  | aws s3 cp - s3://ktc4-kangwon-2-rag/backup/$(date +\%F).sql.gz
```

EC2 역할에 `PowerUserAccess` 가 있어 키 없이 S3 에 쓴다.
