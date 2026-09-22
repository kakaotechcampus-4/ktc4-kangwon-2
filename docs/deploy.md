# 배포

**지금은 손으로 한다.** 자동 배포는 카테캠 OIDC 가이드가 나오면 켠다.

## 왜 자동이 아닌가

2026-09-22 카테캠 안내 — **22 포트 외부 개방을 지양할 것.** 다른 팀이 공격을 받았다.

우리는 키 인증만 쓰고 비밀번호 로그인이 꺼져 있어(`passwordauthentication no`)
뚫릴 가능성은 낮았다. 그래도 닫았다 — 로그가 지저분해지고, 관리자는 24개 팀을 같은
기준으로 봐야 한다.

**22 를 닫으면 GitHub Actions 가 서버에 들어갈 길이 없다.**

```
SSH      GitHub  ──(22 로 들어옴)──▶  EC2      ← 닫았다
OIDC     GitHub  ──▶  AWS  ──(SSM)──▶  EC2     ← 인바운드 0개
```

OIDC 는 열쇠를 맡기지 않는다. GitHub 이 「나는 이 저장소의 이 브랜치 워크플로다」를
증명하면 AWS 가 **몇 분짜리 임시 권한**을 준다. 유출돼도 금방 만료된다.

**우리가 직접 못 만든다** — OIDC 공급자 등록과 IAM 역할 생성이 둘 다 IAM 이고,
우리 계정은 IAM 을 못 만진다(ADR-006). 카테캠이 가이드와 역할을 준비 중이다.

`deploy.yml` 은 지워두지 않았다. 트리거만 끄고 남겼다 — OIDC 로 옮길 때 `script` 안의
명령을 그대로 SSM 으로 보내면 된다.

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

EC2 → 인스턴스 → **연결** → **Session Manager** 탭 → 연결

```bash
sudo -iu ubuntu
cd ~/ktc4-kangwon-2

git fetch origin
git checkout main
git reset --hard origin/main

# 되감김 확인 — fetch 가 실패해도 reset 은 성공한다
git log --oneline -1
ls docker-compose.yml

docker compose build backend frontend
docker compose run --rm backend alembic upgrade head   # 앱보다 먼저
docker compose up -d
docker image prune -f

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

## OIDC 로 옮길 때

카테캠에서 역할 ARN 을 받으면 이렇게 바꾼다.

```
1  deploy.yml 의 `on:` 에 push: branches: [main] 을 되살린다
2  job 의 `if: false` 를 지운다
3  appleboy/ssh-action 자리를
     aws-actions/configure-aws-credentials  (role-to-assume: ARN)
     aws ssm send-command                   (script 내용을 그대로)
   로 바꾼다
4  permissions: id-token: write 를 job 에 추가한다
```

**Secret 이 필요 없어진다.** 역할 ARN 은 이름이라 공개돼도 상관없다.
`HEALTHCHECK_URL` 만 남는다.

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
