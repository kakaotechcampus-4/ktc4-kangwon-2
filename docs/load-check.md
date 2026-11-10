# 동시 생성 부하 측정 (#457)

**실제 LLM(엘리스 sol)으로, 운영과 같은 코드 · 같은 설정에서 생성 요청을 동시에 보냈을 때** 무엇이 먼저 막히는지 잰다.

```
① 생성 요청이 몇 개까지 동시에 버티나 — 응답 시간 · 실패 · 실패 원인 (LLM 대기 vs DB 연결 대기)
② 생성이 몰릴 때 다른 화면 요청이 받는 피해 — LLM 을 안 부르는 GET /api/auth/me 를 1초마다
```

결과 · 원값 · 다시 재는 방법을 여기 남긴다. **결과 표는 아직 비어 있다 (「측정 전」)** — 측정은 서버에서 사람이 한다.
도구: `backend/scripts/load_check.py`(부하 · 분석 · 예산 판정) · `backend/scripts/loadtest.sh`(띄우기 · 점검 · 잠금 · 정리) ·
`backend/scripts/loadtest_gate.py`(설정 게이트) · `backend/scripts/compose.loadtest.yml`(격리 override) · 시험 `backend/tests/test_load_check.py`.

---

## 먼저 알고 있는 것 (코드, 이 브랜치 기준)

| | 값 | 어디 |
|---|---|---|
| DB 연결 풀 | **5 + 10 = 15개**, 빌릴 때 최대 30초 기다리고 못 빌리면 500 | `backend/app/db.py:26` (SQLAlchemy 기본값 — 컨테이너에서 확인: `QueuePool 5 10 30.0`) |
| 프로세스 | uvicorn 1개 | `backend/Dockerfile:50` |
| 동기 엔드포인트 스레드 | **anyio 기본 40개** (컨테이너에서 확인) | — |
| LLM 한 번 제한 시간 | 30초. 502 · 503 · 504 · 연결 실패만 호출마다 1회 더(1.5초 뒤) | `backend/app/shared/llm/client.py:46` · `:53` |
| S1 일지 초안 | 인증 의존성의 **첫 질의**(`shared/auth/dependency.py:42`)부터 commit(`documents/router.py:792`)까지 **한 연결을 쥔 채** LLM **1호출**(`:693`). commit 뒤 응답을 만들며 연결을 다시 빌린다. 요청당 전송 시도 최대 **2** | |
| S2 주제형 연간 | 한 트랜잭션 안에서 LLM 호출: 주제 1(`plans/router.py:509` → `plans/llm.py`) + 소주제 1(`:550` → `plans/annual_content.py:155`), **소주제 개수가 틀리면 수리 1 더**(`annual_content.py:191`). 보통 2호출, 최대 **3호출 × 전송 재시도 = 시도 6**. commit 은 `:575` | |
| 놀이형 연간 | 생성 전에 commit 해서 연결을 놓는다 — **이번 측정에서 뺀다** | |
| 참조 자료 | 이미지 안 파일(`p0-planning/data`) — 마이그레이션만 한 빈 DB 에서 S1 · S2 가 돈다 | |
| 풀 대기 초과 | 500 `INTERNAL_ERROR` + 로그 `unexpected_error … error=sqlalchemy.exc.TimeoutError`. **「QueuePool」 문장은 로그에 안 찍힌다** | `backend/app/main.py` (예외 클래스 이름만 남긴다) |

**모형 (실측과 비교한다).** 요청 n 개가 한꺼번에 들어오면 15개가 먼저 연결을 쥐고 LLM 을 기다린다(걸리는 시간 H).
k 번째 물결은 ≈ (k−1)×H 뒤에 시작하고, 연결을 30초 안에 못 빌리면 실패한다. 그래서

```
성공 한도 ≈ 15 × ceil(30 / H)        실패 ≈ max(0, n − 성공 한도)
예)  H=10초 → 한도 45  /  H=15초 → 한도 30 (n=40 이면 10개 실패)  /  H=30초 → 한도 15
```

S1 의 H 는 LLM 1호출, S2 의 H 는 보통 LLM 2호출의 합이다(수리가 끼면 3). **LLM 호출이 몰릴 때 엘리스 쪽이 느려지면 H 자체가 커진다** — 그 변화도 같이 본다.

---

## 환경

**운영과 같은 EC2 에 격리된 `loadtest` 프로젝트**로 돌린다 (2026-11-10 사용자 결정. 안 C = 임시 EC2 는 안 쓴다).

```
운영     ~/ktc4-kangwon-2   프로젝트 ktc4-kangwon-2   db 5432 · backend 8000 열림   망 172.28.0.0/16
측정     ~/loadtest-457     프로젝트 loadtest          포트 안 엶                     망 172.29.0.0/16
```

- **모든 작업은 `loadtest.sh` 를 지난다.** 그 안의 `lt()` 한 함수가 `docker compose --project-directory … --env-file … -f … -f … -p loadtest` 를
  명령줄로 못 박는다. **셸의 `COMPOSE_PROJECT_NAME` 은 override 파일의 `name:` 보다 우선한다** — 파일만 믿으면 운영 이름의 망 · 볼륨으로 렌더링된다.
  그래서 스크립트는 시작할 때 셸의 `COMPOSE_*` 를 지우고, 있었다면 거절한다.
- 스크립트는 `set -euo pipefail` 이고, **게이트(`loadtest_gate.py`)가 어긋나면 `exit 1`** 이다. 같은 게이트를 `up`(db · alembic · backend 각각 바로 앞) ·
  부하기 실행 · `stage` · `budget` · `final` · `down` 앞에서 다시 돈다. 손으로 붙여 넣는 코드 중 서버 상태를 바꾸는 것은 B(`bash -euo pipefail` 안)와 맨 끝의 `rm -rf` 뿐이다.
- **게이트가 보는 것**(`docker compose config --format json` — 비밀번호가 들어 있어 화면에 안 찍는다): 프로젝트 이름 `loadtest` · 서비스 `db backend loadgen` 만 ·
  세 서비스의 `mem_limit` · `memswap_limit`(512m · 1g · 256m) · 호스트 포트 없음 · `restart: "no"` · build 없음 · journald 아님 ·
  **모든 서비스의 연결 네트워크는 `default` 하나뿐 · `network_mode` 없음** · db 이미지 `postgres:15` · backend/loadgen 이미지 ·
  backend `LOADTEST=1` · `LLM_MODE` · `IS_SERVER` · `ALLOW_TEST_RESET=0` · DB 호스트 `db` · loadgen 환경변수는 `DATABASE_URL` · `LOADTEST` 뿐 ·
  **bind mount 는 loadgen 의 `load_check.py` · `out/` 둘뿐, 이름 있는 볼륨은 `loadtest_pgdata` 하나뿐 · 볼륨 `driver_opts` 없음** ·
  망 `loadtest_default` 172.29.0.0/16 하나 · 설정 어디에도 `ktc4-kangwon-2` · `172.28.` · `journald` 가 없다.
- 운영 폴더 안에서는 아무것도 하지 않는다. 컨테이너 · 볼륨(`loadtest_pgdata`) · 망(`loadtest_default`) 이름이 전부 `loadtest` 로 시작한다.
- 이미지는 **빌드하지 않는다.** 지금 도는 운영 backend 이미지에 `ssample-loadtest-backend:457` 태그만 붙여 쓴다. 빌드는 메모리를 먹는다(`docs/deploy.md`).
- **메모리 상한**: db 512m · backend 1g · **부하기 256m**(부하기는 별도 서비스 `loadgen` — `run backend` 로 돌리면 backend 의 1g 를 물려받아 합이 늘어난다).
  `memswap_limit` 도 같게 둬 스왑으로 새지 않는다. 합 1792MiB. **상한으로 줄일 뿐 보장은 아니다** — 호스트 메모리가 모자라면
  커널이 운영 컨테이너를 고를 수도 있다. 그래서 시작 조건을 둔다: `free -m` available ≥ 세 상한 합 + 운영 여유 500MB = **2292MB** (`preflight` 가 본다).
  `restart: "no"`.
- **loadtest 는 새 DB 비밀번호 · 새 `SECRET_KEY` 를 쓴다.** 운영 `SECRET_KEY` 를 쓰면 loadtest 토큰이 운영에서 통한다.
- **엘리스 키는 운영과 같은 것이다.** 키 한도(429)에 걸리면 운영 교사도 503 을 본다 — 그래서 운영 감시와 시간대가 필요하다.
- 부하기(`loadgen`)는 backend 와 같은 이미지의 일회용 컨테이너이고 `http://backend:8000` 으로 보낸다. **앱 설정(SECRET_KEY · 엘리스 키 · LLM_MODE)을 주지 않는다.**
  nginx · Next 층은 거치지 않는다.
- `load_check.py` 는 **풀 수 있는 플래그 없이** 이 조건이 모두 맞아야 돈다: 호스트가 `backend` 하나뿐(localhost · 127.0.0.1 도 거절 — 운영 8000 이 열려 있다),
  환경에 `LOADTEST=1`, `backend`(burst 에서는 DB 호스트도)를 이름 풀이한 주소가 모두 loadtest 망 172.29.0.0/16 안, 그리고 `DATABASE_URL` 에 `?` 쿼리 옵션이 없다
  (`?host=…` 가 호스트를 덮어쓸 수 있다). 운영 망에서 `backend` 는 운영 backend(172.28)라서 거기서 멈춘다. `ssample.duckdns.org` 는 어떤 경우에도 거절한다.
  **이 스크립트는 LLM 을 부르지 않는다.** 돈이 나가는 곳은 loadtest backend 의 LLM 호출이다.

### 배포 잠금 — 단계마다 감싼다

서버 DB 를 바꾸거나 LLM 을 부르는 단계(**`up` · `loadgen setup` · `loadgen burst` · `down`**)는 `loadtest.sh` 가
`scripts/deploy.sh` 와 **같은 파일 `/tmp/ssuksak-deploy.lock` 에 `flock -w 60`** 을 건 채로 돈다(`deploy.sh` 는 ubuntu 로 같은 파일을 `flock -w 300` 한다).

- **못 잡으면 그 단계를 돌리지 않고 `exit 1`** 이다. (`flock` 이 없어도 마찬가지.)
- 단계가 끝나거나 죽으면 fd 가 닫혀 **잠금이 저절로 풀린다**(그 단계가 띄운 자식 프로세스까지 끝나면 — `flock` 의 보통 규칙이다). 뒤에 남는 프로세스 · pid 파일이 없다.
- 읽기 단계(`preflight` · `gate` · `stage` · `budget` · `final`)와 `loadgen analyze`/`budget` 은 잠그지 않는다.
- **단계 사이는 잠금이 막지 못한다.** 그 사이는 Deploy 워크플로 비활성화가 막는다(아래 「시작 전」). 비활성화 전에 이미 서버로 간 배포는 `preflight` 가 본다.
- 단계 도중 배포가 오면: `deploy.sh` 가 300초 기다린 뒤 `die "잠금을 못 잡았다 … 서버는 바꾸지 않았다"` 로 **종료 코드 1**(교체 전 실패 — 서버는 그대로)로 끝난다.
  Actions 에는 실패로 남고 알림이 간다. 끝난 뒤 `gh workflow enable` → 필요하면 다시 올린다.
- 한계: 옛 `deploy.sh`(잠금이 없는 것)를 손으로 돌리면 이 잠금을 안 본다(`deploy.sh` 의 ADR-078 주석).

---

## 시작 전 — 비용 0

하나라도 못 채우면 미룬다.

- [ ] **팀 합의**: 시간대와 배포 정지.
- [ ] **배포를 끈다 · 이미 도는 것이 없는지 본다.** Deploy 를 꺼도 **이미 도는 run · 서버로 간 SSM 명령은 안 멈춘다.** 그래서 두 가지를 다 본다.
  ```bash
  # 로컬(gh 로그인된 곳)에서 — .github/ 파일은 건드리지 않는다
  gh workflow disable Deploy -R kakaotechcampus-4/ktc4-kangwon-2
  # 끝나지 않은 Deploy run 전체 (개수 제한 없이 페이지를 다 넘긴다). 출력이 비어야 한다
  gh api --paginate repos/kakaotechcampus-4/ktc4-kangwon-2/actions/workflows/deploy.yml/runs \
    --jq '.workflow_runs[] | select(.status != "completed") | [.id, .status, .head_branch, .created_at] | @tsv'
  ```
  도는 run 이 있으면 **끝나길 기다린다**(취소하지 않는다 — 서버가 반쯤 바뀐다). 서버 쪽(도는 `deploy.sh` · 배포 잠금 · SSM 에서
  `InProgress`/`Pending`/`Cancelling` 인 명령)은 `preflight` 가 본다(아래 C). 끝나면 `gh workflow enable Deploy …` 로 켜고,
  그 사이 머지된 것이 있으면 한 번 올린다. **못 막으면 미룬다** (develop 머지 = 운영 배포다).
- [ ] **서버 사전 조건** (한 번에 모았다. `preflight` 가 도구 존재와 SSM 조회를 확인한다):
  - `ubuntu` 로 들어간다. `docker`(+ compose v2, 5.5 에서 확인) 를 쓸 수 있다 — sudo 가 필요하면 `LT_SUDO=1`.
  - `python3`(게이트) · `flock`(잠금) · `aws`(SSM 조회) · `openssl`(비밀번호) · `pgrep` · `git` · `curl` 이 있다.
  - **ubuntu 의 AWS 역할에 `ssm:ListCommands` 권한**이 있다. 미리: `aws ssm list-commands --region ap-northeast-2 --instance-id i-041ebb00937bd371f --max-items 1`
    이 성공해야 한다. 실패하면 `preflight` 가 FAIL 이다(「없다」로 읽지 않는다).
  - 운영 backend 컨테이너 `ktc4-kangwon-2-backend-1` 이 Running 이다(`preflight` 가 본다).
- [ ] **시간대**: 교사 사용이 없는 때, **백업 cron(03:15 KST = 18:15 UTC) 전에 정리까지** 끝낸다. 약 1시간 + 여유 → 02:00 KST 전에 시작.
- [ ] **어젯밤 백업이 있다**: `ls -t ~/backup | head -2` · `aws s3 ls s3://ktc4-kangwon-2-backup/backup/ | tail -2`. 없으면 `sudo scripts/backup.sh` 를 손으로.
- [ ] **메모리**: `free -m` 의 available ≥ **2292MB**(세 상한 합 1792 + 운영 여유 500). 아니면 미룬다. swap 사용량도 적어 둔다.
- [ ] **CPU 크레딧** (t3.medium): 콘솔 / CloudWatch `CPUCreditBalance` 를 적어 둔다. 바닥이면 미룬다. (unlimited 모드면 바닥이어도 안 느려지고 초과 요금이 붙는다 — 모드도 적어 둔다.)
- [ ] **엘리스 이달 누적**: 콘솔(또는 담당자)에서 확인. 월 예산 ₩120,000 에 이번 상한 ₩30,000 을 더해도 넉넉한가.
  사용자가 「크레딧 넉넉」 확인으로 대신하면 그 사실을 아래 결과표에 적는다.
- [ ] 로컬에서 `pytest tests/test_load_check.py` 통과, 로컬 리허설(아래 「로컬 리허설」)을 한 번 돌렸다.

---

## 측정 계획 (고정)

**이 표 하나가 계획이다.** `load_check.py` 의 `PLAN` · `BASELINE_REQUESTS` 가 같은 값이고, `budget` 이 이 표 전체를 한 번 판정한다.

| 순서 | 시나리오 | 동시 | 반복 | 요청 수 | 비고 |
|---|---|---|---|---|---|
| 1 | S1 | 1 | 4 (첫 회 예열) | 4 | 기준선 |
| 2 | S2 | 1 | 4 (첫 회 예열) | 4 | 기준선 |
| — | **`budget`** | | | | 기준선 직후 **한 번**. 진행 가능이 아니면 여기서 끝 |
| 3 | S1 | 10 | 2 | 20 | |
| 4 | S2 | 10 | 1 | 10 | |
| 5 | S1 | 20 | 2 | 40 | |
| 6 | S2 | 20 | 1 | 20 | |
| 7 | S1 | 40 | 2 | 80 | |
| 8 | S2 | 40 | 1 | 40 | |

합계: S1 **144**건(기준선 4 + 140) · S2 **74**건(기준선 4 + 70) → 필요한 반 150개(요청마다 새 반이 든다).

**반복을 줄인 이유**: 이전 안(S1 10·20·40 × 3, S2 × 2)은 S1 214 · S2 144건이었다. 판정을 단계마다 다시 하지 않고 기준선 단가로 **한 번** 하므로
남은 요청 수가 곧 최악 비용이고 02:45 KST 전 종료 시간이다. S1 은 2회(회차 사이 흩어짐 확인), S2 는 요청당 비용이 커서 1회로 줄였다.
**회차가 적어 p95 는 참고일 뿐이고, 본 지표는 실패 수 · max · LLM 시작 물결이다.**

### 예산 판정 (`budget`) — 계산식

기준선이 끝나면 `bash $LT budget` 을 **한 번** 돌린다. 기준선 로그에서 요청 하나씩(동시 1 이라 요청 = 회차 = 로그 줄 묶음) 실제 원화를 계산한다.

```
요청당 원화(기준선)     = 그 요청의 llm_usage 줄들(입력 × ₩2.835/1K + 출력 × ₩14.175/1K)의 합
요청당 최악(시나리오)   = 기준선 요청당 최대 원화 × (요청당 최대 시도 ÷ 기준선 요청당 최소 시도)
                          요청당 최대 시도: S1 2 · S2 6    기준선 시도 = 그 요청의 llm_call 줄 수(성공 + not_delivered)
남은 계획 최악          = S1 140건 × 요청당 최악(S1) + S2 70건 × 요청당 최악(S2)
기준선 지출             = 기준선 요청 8건의 원화 합 (예열 회차 포함)
진행 가능               ⇔ 남은 계획 최악 ≤ ₩30,000 − 기준선 지출
```

- **S2 최대 시도 6** = 주제 1 + 소주제 1 + 소주제 개수 수리 1 = 3호출 × 전송 재시도 1회(`plans/llm.py`, `plans/annual_content.py:155` · `:191`). S1 은 초안 1호출 × 2.
- **기준선 요청 하나라도 이 중 하나면 「멈춤(단가 모름)」**: 201 이 아니다 · `llm_call` 줄이 없다 · `outcome` 이 `ok`/`not_delivered` 가 아니다(`failed` · `timeout` · `budget`) ·
  성공 호출이 모자란다(S1 1 · S2 2) · `llm_usage` 가 없거나 숫자가 아니거나 성공 호출 수와 안 맞는다 · 기준선 요청이 4건이 아니다.
  기준선을 다시 돌렸다면 시나리오마다 **가장 최근 기준선 파일만** 본다.
- 결과: `진행 가능`(종료 코드 0) / `멈춤(단가 모름)` / `멈춤(상한 초과 가능)`(종료 코드 1). **이 한 번의 판정이 표의 남은 burst 전부를 허용한다 — 단계마다 다시 판정하지 않는다.**
- 이 추정은 관측에 기댄 것이지 보장된 상한이 아니다(캐시 할인을 안 세서 조금 높고, 단가가 기준선보다 커지는 요청은 못 본다).
  사후 지출 집계(`stage`/`final` 끝)는 보고용이고 판정에 쓰지 않는다. 사람이 누적 지출이 ₩30,000 의 80% 를 넘는지 본다(중단 규칙 I-2).
- **mock 에서는 `llm_call` 줄이 없어 「멈춤(단가 모름)」이 정상이다.** 서버 real 에서만 의미가 있다.

---

## 서버 명령 순서

Session Manager 로 들어가 사람이 친다. 터미널을 3개 쓴다: ① 작업 ② 운영 감시 ③ 자원 기록.

### A. 들어가기

```bash
sudo -iu ubuntu
export LT_SUDO=1                           # docker 가 sudo 를 요구하는 환경일 때만 (docs/deploy.md 는 sudo docker compose)
export LT_SSM_INSTANCE=i-041ebb00937bd371f # preflight 가 SSM 에서 도는 배포 명령을 볼 인스턴스
LT=/home/ubuntu/loadtest-457/loadtest.sh
```

### B. 폴더 · 스크립트 받기

운영 폴더는 건드리지 않는다. 이 저장소 브랜치를 `~/loadtest-457/src` 에 얕게 받아 쓸 파일만 꺼낸다 (**push 되어 있어야 한다**).

```bash
bash -euo pipefail <<'SH'
mkdir -p /home/ubuntu/loadtest-457/out
cd /home/ubuntu/loadtest-457
git clone --depth 1 --branch feature/load-check https://github.com/kakaotechcampus-4/ktc4-kangwon-2.git src
cp src/backend/scripts/compose.loadtest.yml src/backend/scripts/load_check.py \
   src/backend/scripts/loadtest.sh src/backend/scripts/loadtest_gate.py .
cp /home/ubuntu/ktc4-kangwon-2/docker-compose.yml .
git -C src log --oneline -1                    # 부하 스크립트 커밋 → 결과표에 적는다
SH
```

### C. 점검 · .env · 이미지 태그 · 게이트

```bash
bash $LT preflight      # 읽기만. 하나라도 FAIL 이면 exit 1
bash $LT env            # 새 DB 비밀번호 · 새 SECRET_KEY · LLM_MODE=real · IS_SERVER=1 · 엘리스 두 줄(운영 .env 에서, 화면에 안 찍음). .env 가 있으면 거절
bash $LT tag            # 운영 backend 이미지에 ssample-loadtest-backend:457 태그
bash $LT gate -v        # 어긋나는 것이 하나라도 있으면 exit 1
```

`preflight` 가 보는 것 (**조회 명령이 실패하면 「없음」이 아니라 FAIL**):
- 도구: `python3` · `openssl` · `pgrep` · `flock` · `aws`
- 운영 backend 컨테이너 조회 성공 + **`State.Running` = true**, 이미지 · 로그 드라이버
- `free -m` available ≥ 2292MB
- 172.29 대역을 쓰는 망 · loadtest 볼륨 · 컨테이너가 없다 (docker 조회 실패는 FAIL)
- 도는 `deploy.sh` 없음(`pgrep` 종료 코드 0 = 있음 · 1 = 없음 · 그 밖 = 실패) · 배포 잠금을 아무도 안 쥐고 있음
- SSM 에서 `InProgress`/`Pending`/`Cancelling` 인 명령 없음(`LT_SSM_INSTANCE` 필수, 조회 실패 = FAIL)

### D. 띄우기

```bash
bash $LT up             # [잠금] gate → db → gate → alembic → gate → backend → 준비될 때까지(최대 60초) → /health/ready → ps
```

### E. 감시 — 측정 내내 켜 둔다

**② 운영 감시** (다른 터미널). 운영 backend 로그가 새로 이 줄을 내면 **측정을 멈춘다.** 운영 로그 드라이버가 json-file 이든 journald 든 `docker logs` 로 읽힌다.
(`LT_SUDO=1` 이면 `${LT_SUDO:+sudo}` 가 sudo 로 펼쳐진다.)

```bash
${LT_SUDO:+sudo} docker logs -f --since 1m ktc4-kangwon-2-backend-1 2>&1 | grep --line-buffered -E 'outcome=(budget|timeout|failed|not_delivered)|unexpected_error|llm_cap_hit'
```

운영 상태도 같이 본다 (운영 backend 는 호스트 8000 을 연다):

```bash
while sleep 15; do date -u +%T | tr '\n' ' '; curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/health/ready; done
```

**③ 자원 기록** (프로세스 하나. 1초마다 `docker stats` 를 새로 부르는 반복은 그 자체가 CPU 를 쓴다):

```bash
${LT_SUDO:+sudo} docker stats --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}' \
  ktc4-kangwon-2-backend-1 ktc4-kangwon-2-db-1 loadtest-backend-1 loadtest-db-1 > /home/ubuntu/loadtest-457/out/docker-stats.log
```

### F. 단계 실행 — 위의 측정 계획대로

```bash
L() { bash "$LT" loadgen "$@"; }     # 부하기(load_check.py)를 일회용 loadgen 컨테이너로. 매번 gate 를 먼저 돈다. setup · burst 는 [잠금]
S() { bash "$LT" stage; }            # 로그를 덤프하고 마지막 단계를 분석한다(읽기)
B=http://backend:8000
```

**요청마다 새 반이 든다** (같은 반 · 같은 날 일지는 409, 연간은 반당 하나, 같은 반이면 `FOR UPDATE` 로 저장이 줄을 선다).
필요한 반 수 = max(S1 총 요청 수, S2 총 요청 수) = 144 → 150. 모자라면 `setup` 을 다시 돌리면 더해진다.

```bash
L setup --base $B --classes 150 --out /lt/out
```

```bash
# 1~2  기준선 — 첫 회차는 예열로 따로 센다
L burst --base $B --scenario s1 --n 1 --repeat 4 --warmup 1 --out /lt/out;  S
L burst --base $B --scenario s2 --n 1 --repeat 4 --warmup 1 --out /lt/out;  S
bash $LT budget          # ★ 한 번. 「진행 가능」이 아니면(exit 1) 여기서 끝낸다. 진행 가능이면 아래 전부를 허용한다
# 3~4  동시 10
L burst --base $B --scenario s1 --n 10 --repeat 2 --out /lt/out;  S
L burst --base $B --scenario s2 --n 10 --repeat 1 --out /lt/out;  S
# 5~6  동시 20
L burst --base $B --scenario s1 --n 20 --repeat 2 --out /lt/out;  S
L burst --base $B --scenario s2 --n 20 --repeat 1 --out /lt/out;  S
# 7~8  동시 40
L burst --base $B --scenario s1 --n 40 --repeat 2 --out /lt/out;  S
L burst --base $B --scenario s2 --n 40 --repeat 1 --out /lt/out;  S
```

**한 줄씩 따로 친다** — 줄마다 `S` 의 표 · 운영 감시를 보고 다음 줄을 보낼지 정한다. 비용은 `budget` 이 이미 계획 전체를 허용했으므로 단계마다 다시 계산하지 않는다.
`L burst` 가 **0 이 아닌 코드**로 끝났으면 다음 줄을 보내지 않는다: 종료 코드 **3** 은 한도 오류(`LLM_BUDGET_EXCEEDED`)가 나와 남은 회차를 안 보냈다는 뜻이다(결과는 저장됐다).
`S` 는 읽기라 그래도 돌려 된다.

놀이형 연간은 기본 제외다(연결을 놓는 대조군). 기준선 비용을 보고 동시 1 · 10 만 넣을지 정한다(이 표 밖이면 `budget` 을 다시 계산해야 한다).

전부 끝나면 **전체 표**를 한 번 뽑아 결과에 옮긴다 (마지막 단계 하나가 아니라 전부):

```bash
bash $LT final          # 새로 로그를 덤프하고 analyze 를 --last-only 없이 → out/analysis-final.txt
```

`--repeat` 는 회차 사이에 `--pause`(기본 5초) 쉰다. 클라이언트 시간 초과가 생기면 서버가 끝나길 `--settle`(기본 60초) 기다린 뒤 행 수를 센다.
회차가 길어 터미널이 끊길 수 있으면 `tmux` 안에서 돌린다.

### G. 읽는 법

`S` 가 단계마다 이 표를 낸다 (회차를 합친 값).

- **결과표 (상태, code, message)**: 실패를 이 셋으로 가른다.
  - 500 `INTERNAL_ERROR` + `unexpected_error … error=sqlalchemy.exc.TimeoutError` → **풀 대기 초과**
  - 500 `GENERATION_FAILED` — S1 은 문구가 갈린다: 「AI 초안을 만들지 못했습니다」(LLM 실패 · 시간 초과 — `llm_call outcome=` 으로 가른다) ·
    「AI 응답이 약속한 형식이 아닙니다」(형식 위반) · 「초안이 문서 규격을 통과하지 못했습니다」(게이트 2단 반려)
  - 503 `LLM_BUDGET_EXCEEDED` → 엘리스가 401 · 403 · 429 를 냈다 (**셋을 가를 수 없다**)
  - `CLIENT_TIMEOUT`(180초) · `CONN_ERROR` → 별도 분류
- **LLM 시작 시각 히스토그램** (`llm_call` 로그 시각 − `ms` = LLM 시작, burst t0 기준):
  - **S2**: 요청 하나가 여러 번 부르므로(주제 · 소주제 · 수리, 재시도) `run=` 으로 묶어 **첫 호출의 시작만** 센다.
    **0초 · H초 · 2H초에 15개씩 몰리면 풀이 병목**이라는 직접 증거다.
  - **S1**: `run=-` 라 요청으로 묶을 수 없다. **LLM 호출 시도 시작**으로 센다 — 전송 재시도(1.5초 뒤)가 새 요청의 시작처럼 보일 수 있어 **참고용**이다. 직접 증거로 쓰지 않는다.
- **요청 − plan_timing 줄 수** (S2): 핸들러에 못 닿은 수. `plan_timing` 은 인증 질의(= 풀 대기) 뒤에 시작해 풀 대기를 못 본다.
- **서버 plan_timing total_ms 분포** (S2)와 클라이언트 **응답 시간** 분포를 **따로** 본다. 요청과 짝지어 빼지 않는다 — 요청에 번호가 없어 짝이 틀릴 수 있다.
- **/auth/me**: LLM 을 안 부르는 인증 GET 의 지연 · 실패. 생성이 몰릴 때 다른 화면이 받는 피해.
- **pg_stat 최대**: 붙잡힌 연결 · `idle in transaction`. 풀이 막히면 15 근처가 보인다.
- **unexpected_error**: `경로 + 예외 클래스` 별 건수. `/api/auth/me` 쪽 풀 대기 초과(표본이 맞은 것)와 생성 경로의 것을 가른다.
- **행 수 대조**: 201 수와 DB 에 실제 저장된 행 수. 「저장됐는데 실패 응답」을 따로 센다(S1 은 commit 뒤 응답을 만들며 연결을 다시 빌린다).
- **원화 지출 (끝에 붙는 사후 집계)**: `llm_usage` 토큰 × 단가. 시간 초과는 호출 최대 단가로 센 추정이다. **보고용이다 — 판정(`budget`)에 쓰지 않는다.**

### H. 중단 규칙

다음 중 하나라도 있으면 **다음 줄을 보내지 않는다** (이미 보낸 요청은 못 되돌린다).

1. 운영 감시 터미널에 새 줄이 떴다 (`outcome=(budget|timeout|failed|not_delivered)` · `unexpected_error`), 또는 운영 `/health/ready` 가 200 이 아니다.
2. `budget` 이 「진행 가능」이 아니다(`exit 1`). 또는 `S` 끝의 사후 누적 지출이 ₩30,000 의 80% 를 넘었다 — 사람이 보고 멈춘다.
3. `L burst` 가 종료 코드 3 으로 끝났다(`LLM_BUDGET_EXCEEDED`). 스크립트는 남은 회차를 이미 안 보냈다. **60초 뒤** 수동으로 S1 한 건을 보낸다:
   `L burst --base $B --scenario s1 --n 1 --out /lt/out`. 성공이면 429(한도)였다고 기록하고 끝낸다. 계속 503 이면 **키가 지워졌을 수 있다** — 즉시 팀에 알리고 엘리스 콘솔을 확인한다.
4. `free -m` available 이 600MB 아래이거나 swap 이 늘기 시작한다, 또는 `docker stats` 에서 loadtest 컨테이너가 OOM 으로 죽었다.
5. 시간이 02:45 KST(정리 전 여유 30분)를 넘겼다.
6. `L setup`/`L burst`/`up`/`down` 이 「배포 잠금을 … 못 잡았다」로 끝났다 — 배포가 돌고 있다. 그 단계는 돌지 않았다. 배포가 끝날 때까지 기다린다.

### I. 정리 — 이 폴더 안에서만

```bash
# 먼저 ② 운영 감시 · ③ 자원 기록 터미널에서 Ctrl-C 로 끈다
bash $LT final          # 아직 안 뽑았다면
bash $LT down           # [잠금] gate → out/backend-final.log 덤프 → down -v → 태그 삭제(-f 없음) → loadtest 볼륨 · 망 · 컨테이너 · 이미지 태그가 0인지, 남으면 exit 1
```

**`rm -rf ~/loadtest-457` 전에 `out/` 를 옮긴다.** `burst-*.json` · `backend-*.log` · `analysis-*.txt` · `budget.txt` · `docker-stats.log` 를
로컬 `docs/evaluation/runs/<날짜>-load-check/` 로 가져온다. **`state.json` 은 옮기지 않는다**(loadtest 토큰 · 비밀번호). 로그에는 프롬프트 · 응답 내용이 없다(숫자와 이름뿐).

```bash
rm -rf /home/ubuntu/loadtest-457

# 운영 확인 (LT_SUDO 를 지우기 전에 — 지운 뒤에는 sudo 없이 docker 를 부르게 된다)
${LT_SUDO:+sudo} docker ps --format '{{.Names}} {{.Status}}' | grep ktc4-kangwon-2        # 전부 Up, 재시작 흔적 없음
curl -sf localhost:8000/health/ready; echo
free -m; df -h /

unset LT LT_SUDO LT_SSM_INSTANCE B; unset -f L S
```

그리고 로컬에서 `gh workflow enable Deploy -R kakaotechcampus-4/ktc4-kangwon-2`.

---

## 로컬 리허설

서버에서 하기 전에 같은 스크립트로 한 번 돈다. **로컬에서 `LLM_MODE=real` 은 금지다** — mock 으로 배관(가입 · 반 · 일과 기록 · burst · 로그 덤프 · 분석 · 정리)만 본다.

- 작업 폴더를 저장소 밖에 만들고 `docker-compose.yml` · `backend/scripts/compose.loadtest.yml` · `load_check.py` · `loadtest.sh` · `loadtest_gate.py` 를 복사한다.
- 로컬 이미지를 `docker build -t ssample-loadtest-backend:457 -f backend/Dockerfile .` 로 만든다 (서버에서는 `bash $LT tag` 다).
- `export LT_DIR=<작업 폴더> LT_MODE=mock LT_SKIP_SSM=1 LT_LOCK=none` 을 주고 C~I 를 그대로 한다(`tag` 는 건너뛴다). 이 `LT_*` 변수들은 **`LT_MODE=mock` 일 때만 읽는다** — real 에서는 무시된다.
  - `LT_MODE=mock` 이면 `.env` 에 `IS_SERVER=0` · 엘리스 줄이 없고, 게이트도 `LLM_MODE=mock` · `IS_SERVER=0` 을 기대한다.
  - `LT_LOCK=none` 은 macOS 에 `flock` 이 없어서다. 잠금은 아래처럼 Linux 컨테이너에서 따로 본다.
  - preflight 의 운영 backend 조회는 `LT_PROD_BACKEND=<로컬에서 도는 컨테이너 이름>` 으로 바꿔야 통과한다(없으면 FAIL 이 정상이다).
    메모리는 `LT_AVAILABLE_MB=3000` 으로 준다.
- 부하기는 로컬에서도 같은 길이다: loadgen 컨테이너 → `http://backend:8000`. 그래서 가드(`backend` 호스트 · `LOADTEST=1` · 172.29 안)가 그대로 걸린다. 로컬 개발 스택(`localhost:8000`)에는 못 보낸다.
- **mock 에는 `llm_call` · `llm_usage` 줄이 없다** — `budget` 은 「멈춤(단가 모름)」이 정상이다. 판정식은 시험(`test_load_check.py`)과 합성 로그로만 확인했다.
  실제 줄 모양은 서버 첫 기준선에서 처음 본다.
- 배포 잠금: Linux 컨테이너 안에서 `LT_MODE=mock LT_LOCK=/tmp/lt-test.lock` 으로 「다른 프로세스가 쥐고 있으면 `up`/`loadgen burst`/`down`/`locked` 가 안 돈다 · 단계가 끝나면 풀린다」를 확인했다.
  서버의 `/tmp/ssuksak-deploy.lock` 자체는 실행하지 않았다.

---

## 한계

결과를 읽을 때 같이 적는다.

- **운영이 쉬는 시간**에 쟀다. 같은 상자라 CPU · 메모리는 운영 컨테이너와 나눠 쓴다(t3.medium, 크레딧).
- **burst 기준이다** — 흩어진 도착이 아니라 한꺼번에 도착한다. 실제 교사 트래픽보다 가혹하다.
- 빈 DB 라 질의가 실제보다 빠르다. 일과 기록이 1행이라 프롬프트가 실제 일지보다 짧다(더 빠르고 더 싸다). 아동이 없다.
- 운영은 다른 요청과 풀을 나눠 쓰므로 **더 일찍 포화한다.** 여기서는 생성 요청이 풀을 혼자 쓴다.
- nginx · Next 층을 거치지 않는다 (nginx 상한 120초 · 510초와는 숫자로만 비교한다).
- 결과는 **LLM 30초 · 풀 30초 상수에 묶여 있다**. 그 값이 바뀌면 다시 잰다.
- **스레드풀 40**: 동기 엔드포인트라 요청이 스레드를 하나씩 쥔다. n=40 에서는 스레드풀도 가득 차서 `/auth/me` 표본이 스레드를 기다릴 수 있다 —
  n=40 의 `/auth/me` 지연을 풀 대기와 스레드 대기로 가르지 못한다. n ≤ 20 은 풀이 먼저 찬다.
- 엘리스 쪽 처리량 · 한도가 결과에 섞인다 (키가 운영과 같다). LLM 시간 H 가 단계마다 달라질 수 있다.
- 놀이형 · 월간 · 주간 · 관찰일지는 측정하지 않았다.
- 401 · 403 · 429 는 서버가 `LLM_BUDGET_EXCEEDED` 하나로 묶는다 — 한도(429)와 키 삭제(401)를 구분하지 못한다.
- 표본은 1초 간격이라 순간 피크를 놓칠 수 있고, 응답이 느리면(예: `/auth/me` 가 풀 대기로 30초) 그동안 표본이 성기다. 로그 시각은 `docker logs -t` 수집 시각(UTC)이라 수 ms 오차가 있다.
- 지출은 로그의 토큰 × 단가이고 캐시 할인이 없어 실제보다 조금 높다. 시간 초과분은 추정이다. 계획 전체의 예산 판정(`budget`)은 **기준선 단가에 기댄 추정**이지 보장된 상한이 아니다 — 단가가 기준선보다 큰 요청은 못 본다.
- 메모리 상한은 컨테이너를 줄일 뿐 운영 컨테이너가 안 죽는다는 보장이 아니다.
- S1 의 LLM 시작 히스토그램은 전송 재시도와 섞여 참고용이다(풀 병목의 직접 증거는 S2).

---

## 결과

**측정 전.** 아래는 비어 있는 틀이다.

### 개요

| 항목 | 값 |
|---|---|
| 측정 날짜 · 시간대(KST) | 측정 전 |
| 부하 스크립트 커밋 | 측정 전 |
| 운영 커밋 · 이미지 ID | 측정 전 |
| 엘리스 이달 누적 (시작 전) | 측정 전 |
| 예산 판정 `budget` 결과 (기준선 지출 · 남은 계획 최악) | 측정 전 |
| 이번 측정 지출 (시간 초과 추정 포함) | 측정 전 |
| 서버 `free -m` available (전 → 후) | 측정 전 |
| 운영 감시에 걸린 것 | 측정 전 |

### S1 일지 초안 (LLM 1호출)

| 동시 | 회차 | 요청 | 201 | 실패 (상태 · code) | p50 | p95 | max | LLM 시도 시작 | /auth/me p95 · max | pg 연결 최대 | 저장됐는데 201 아님 | 지출 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 (예열 제외) | 측정 전 | | | | | | | | | | | |
| 10 | 측정 전 | | | | | | | | | | | |
| 20 | 측정 전 | | | | | | | | | | | |
| 40 | 측정 전 | | | | | | | | | | | |

### S2 주제형 연간 (LLM 보통 2호출, 수리 시 3)

| 동시 | 회차 | 요청 | 201 | 실패 (상태 · code) | p50 | p95 | max | LLM 첫 시작 물결 | 서버 total_ms p50 · p95 | 요청 − plan_timing | /auth/me p95 · max | pg 연결 최대 | 저장됐는데 201 아님 | 지출 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 (예열 제외) | 측정 전 | | | | | | | | | | | | | |
| 10 | 측정 전 | | | | | | | | | | | | | |
| 20 | 측정 전 | | | | | | | | | | | | | |
| 40 | 측정 전 | | | | | | | | | | | | | |

### 모형과 실측

| 시나리오 · 동시 | H (LLM 시간 p50) | 예측 성공 한도 15×⌈30/H⌉ | 예측 실패 | 실측 실패 | 실패 원인 (풀 대기 초과 · LLM · 기타) |
|---|---|---|---|---|---|
| 측정 전 | | | | | |

### 해석

측정 전.
