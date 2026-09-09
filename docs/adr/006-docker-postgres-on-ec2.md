# ADR-006: DB 를 EC2 내 Docker Postgres 로 돌린다

- 2026-09-08
- 상태 — 채택 (RDS 는 별도 요청 중)

## 맥락

카테캠이 제공한 AWS 계정에 제한이 걸려 있다.

```
RDS 생성 불가 (요청 시 검토)
Elastic IP 불가
IAM 사용자·액세스 키 생성 불가
ALB · NAT Gateway · EKS · ElastiCache 차단
사양 · 디스크 변경 불가 (t3.medium / 50GB 고정)
```

관리형 DB 를 쓸 수 없다.

## 결정

`docker-compose.yml` 의 `postgres:15` 컨테이너를 EC2 안에서 돌린다.
RDS 는 Peter(카테캠 인프라 매니저)에게 별도 요청했고, 승인되면 이전한다.

## 근거

**로컬과 운영이 같은 구성이 된다** `[판단]`

같은 `docker-compose.yml` 이 로컬과 서버에서 돈다.
"제 로컬에선 되는데요" 가 줄어든다.

**이전 비용이 낮다**

RDS 가 승인되면 `DATABASE_URL` 한 줄만 바꾸면 된다. 어댑터처럼 격리돼 있다.

**DynamoDB 는 안 맞다**

관계형이 필요하고 `tags` 검색에 조인을 쓴다. BE 스키마를 다 버려야 한다.

## 대안

**RDS 승인을 기다림** — 검토에 시간이 걸리고 5주차가 막힌다. 병행 요청으로 처리.

**DynamoDB** — 기각. 위 참조.

## 결과

- **백업을 우리가 해야 한다.** RDS 자동 백업이 없다.
  **11주차 파일럿 시작 전에** cron 을 걸어야 한다.

  ```bash
  0 3 * * * docker exec <db컨테이너> pg_dump -U ssuk ssuksak | gzip \
    | aws s3 cp - s3://<버킷>/backup/$(date +\%F).sql.gz
  ```

  S3 는 카테캠이 허용했다.

- `pgdata` named volume 이 필수다. 없으면 `docker compose down` 한 번에 DB 가 초기화된다.
- `ports: 5432:5432` 는 로컬 개발에 필요하지만 서버에서는 불필요하다.
  서버용 override 파일로 덮는다.
- **서버를 「중지」하지 않는다. 재부팅만.** Elastic IP 가 불가해서 중지 후 시작하면 IP 가 바뀐다.
- 배포는 SSH agent forwarding + 수동(5주차) → GHCR pull(6주차).
  IAM 키와 Deploy key 가 둘 다 막혀서 나온 경로다.
