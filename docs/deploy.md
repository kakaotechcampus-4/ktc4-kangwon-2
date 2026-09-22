# 배포

`main` 에 머지하면 자동으로 올라간다. `.github/workflows/deploy.yml` 이 한다.

```
main 머지  →  GitHub Actions  →  SSH 로 EC2 접속
           →  git reset --hard origin/main
           →  docker compose build
           →  alembic upgrade head      마이그레이션이 앱보다 먼저
           →  docker compose up -d
           →  밖에서 /health/ready 200 확인
```

## 왜 SSH 인가

카테캠 AWS 계정은 **IAM 사용자·액세스 키 생성이 막혀 있다**(ADR-006).
GitHub Actions 가 AWS 를 부르려면 키가 있어야 하고, OIDC 는 IAM 역할을 새로
만들어야 해서 같은 벽에 막힌다. SSH 는 22 포트만 있으면 된다.

EC2 에는 `ktc-ec2-ssm-role`(PowerUserAccess)이 붙어 있어 **서버 안에서는** S3 등을
키 없이 쓴다. 밖에서 들어가는 길만 SSH 인 것이다.

## 필요한 Secret 5개

저장소 Settings → Secrets and variables → Actions → **New repository secret**

| 이름 | 값 | 얻는 법 |
|---|---|---|
| `EC2_HOST` | 서버 공인 IP | EC2 콘솔 → 인스턴스 → 퍼블릭 IPv4 |
| `EC2_USER` | `ubuntu` | Ubuntu AMI 의 기본 계정 |
| `EC2_SSH_KEY` | `.pem` 파일 **전체 내용** | 인스턴스 만들 때 받은 키. `-----BEGIN` 줄부터 `-----END` 줄까지 그대로 |
| `HEALTHCHECK_URL` | `http://<서버IP>` | 끝에 `/` 를 붙이지 않는다 |

`DEPLOY_PATH` 는 secret 이 아니다. 비밀이 아니라서 `deploy.yml` 의 `env` 에 있다.
서버에서 저장소 위치가 다르면 그 줄만 고친다.

## 서버에 한 번만 해둘 것

```bash
# Session Manager 로 들어간다 (EC2 → 인스턴스 → 연결 → Session Manager)
sudo -iu ubuntu

git clone git@github.com:kakaotechcampus-4/ktc4-kangwon-2.git
cd ktc4-kangwon-2
cp .env.example .env
nano .env            # POSTGRES_PASSWORD 와 DATABASE_URL 의 비밀번호를 같은 값으로
```

**`.env` 는 커밋하지 않으므로 서버에만 있다.** 없으면 배포가 그 자리에서 멈춘다 —
빈 비밀번호로 DB 가 뜨는 것보다 낫다.

## 보안그룹

```
22   SSH    0.0.0.0/0     GitHub Actions 러너 IP 가 고정이 아니라 열어둔다
80   HTTP   0.0.0.0/0     nginx
```

**8000 · 3000 · 5432 는 닫는다.** nginx 가 유일한 입구다 — 업로드 크기 제한이 거기 있다.

## 확인

```bash
curl -m 5 http://<서버IP>/health/ready     # 200
curl -m 5 http://<서버IP>:8000/health      # 시간 초과여야 정상
```

## 안 만든 것

**롤백 자동화** — `git reset --hard <이전 커밋>` 후 다시 돌리면 된다.
실패가 잦아지면 그때 만든다.

**GHCR 이미지 푸시** — 지금은 서버에서 직접 빌드한다.
빌드 머신이 따로 없어 단계가 하나 줄어든다.
`t3.medium`(4GB)에서 Next.js 빌드가 메모리로 실패하면 그때 GHCR 로 옮긴다.
증상은 `docker compose build` 가 `Killed` 로 끝나는 것이다.

**무중단 배포** — `docker compose up -d` 가 컨테이너를 바꾸는 몇 초 동안 끊긴다.
파일럿 규모에서 문제가 아니다.

## 백업

파일럿(10/19) 전에 걸어야 한다(ADR-006). 아직 안 걸었다.

```bash
0 3 * * * docker exec ktc4-kangwon-2-db-1 pg_dump -U ssuksak ssuksak | gzip \
  | aws s3 cp - s3://ktc4-kangwon-2-rag/backup/$(date +\%F).sql.gz
```

EC2 역할에 `PowerUserAccess` 가 있어 키 없이 S3 에 쓴다.
