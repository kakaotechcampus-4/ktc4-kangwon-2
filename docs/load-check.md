# 동시 생성 부하 측정 (#457)

**실제 LLM(엘리스 sol)으로, 운영과 같은 코드 · 같은 설정에서 생성 요청을 동시에 보냈을 때** 무엇이 먼저 막히는지 잰다.

```
① 생성 요청이 몇 개까지 동시에 버티나 — 응답 시간 · 실패 · 실패 원인 (LLM 대기 vs DB 연결 대기)
② 생성이 몰릴 때 다른 화면 요청이 받는 피해 — LLM 을 안 부르는 GET /api/auth/me 를 1초마다
```

결과 · 원값 · 다시 재는 방법을 여기 남긴다. **결과 표는 아직 비어 있다 (「측정 전」)** — 측정은 서버에서 사람이 한다.
도구: `backend/scripts/load_check.py` · `backend/scripts/compose.loadtest.yml` · 시험 `backend/tests/test_load_check.py`.

---

## 먼저 알고 있는 것 (코드, 이 브랜치 기준)

| | 값 | 어디 |
|---|---|---|
| DB 연결 풀 | **5 + 10 = 15개**, 빌릴 때 최대 30초 기다리고 못 빌리면 500 | `backend/app/db.py:26` (SQLAlchemy 기본값 — 컨테이너에서 확인: `QueuePool 5 10 30.0`) |
| 프로세스 | uvicorn 1개 | `backend/Dockerfile:50` |
| 동기 엔드포인트 스레드 | **anyio 기본 40개** (컨테이너에서 확인) | — |
| LLM 한 번 제한 시간 | 30초. 재시도는 502 · 503 · 504 · 연결 실패만 1회(1.5초 뒤) | `backend/app/shared/llm/client.py:46` · `:53` |
| S1 일지 초안 | 인증 의존성의 **첫 질의**(`shared/auth/dependency.py:42`)부터 commit(`documents/router.py:792`)까지 **한 연결을 쥔 채** LLM 1회(`:693`). commit 뒤 응답을 만들며 연결을 다시 빌린다 | |
| S2 주제형 연간 | LLM 2회(`plans/router.py:509` · `:550`)를 한 트랜잭션 안에서, commit 은 `:575` | |
| 놀이형 연간 | 생성 전에 commit 해서 연결을 놓는다 — **이번 측정에서 뺀다** | |
| 참조 자료 | 이미지 안 파일(`p0-planning/data`) — 마이그레이션만 한 빈 DB 에서 S1 · S2 가 돈다 | |
| 풀 대기 초과 | 500 `INTERNAL_ERROR` + 로그 `unexpected_error … error=sqlalchemy.exc.TimeoutError`. **「QueuePool」 문장은 로그에 안 찍힌다** | `backend/app/main.py` (예외 클래스 이름만 남긴다) |

**모형 (실측과 비교한다).** 요청 n 개가 한꺼번에 들어오면 15개가 먼저 연결을 쥐고 LLM 을 기다린다(걸리는 시간 H).
k 번째 물결은 ≈ (k−1)×H 뒤에 시작하고, 연결을 30초 안에 못 빌리면 실패한다. 그래서

```
성공 한도 ≈ 15 × ceil(30 / H)        실패 ≈ max(0, n − 성공 한도)
예)  H=10초 → 한도 45  /  H=15초 → 한도 30 (n=40 이면 10개 실패)  /  H=30초 → 한도 15
```

S1 의 H 는 LLM 1회, S2 의 H 는 LLM 2회 합이다. **LLM 호출이 몰릴 때 엘리스 쪽이 느려지면 H 자체가 커진다** — 그 변화도 같이 본다.

---

## 환경

**운영과 같은 EC2 에 격리된 `loadtest` 프로젝트**로 돌린다 (2026-11-10 사용자 결정. 안 C = 임시 EC2 는 안 쓴다).

```
운영     ~/ktc4-kangwon-2   프로젝트 ktc4-kangwon-2   db 5432 · backend 8000 열림   망 172.28.0.0/16
측정     ~/loadtest-457     프로젝트 loadtest          포트 안 엶                     망 172.29.0.0/16
```

- 운영 폴더 안에서는 아무것도 하지 않는다. 컨테이너 · 볼륨(`loadtest_pgdata`) · 망(`loadtest_default`) 이름이 전부 `loadtest` 로 시작한다.
- 이미지는 **빌드하지 않는다.** 지금 도는 운영 backend 이미지에 `ssample-loadtest-backend:457` 태그만 붙여 쓴다. 빌드는 메모리를 먹는다(`docs/deploy.md`).
- 메모리 상한: db 512m · backend 1g. 넘치면 운영 대신 loadtest 컨테이너가 죽는다. `restart: "no"`.
- **loadtest 는 새 DB 비밀번호 · 새 `SECRET_KEY` 를 쓴다.** 운영 `SECRET_KEY` 를 쓰면 loadtest 토큰이 운영에서 통한다.
- **엘리스 키는 운영과 같은 것이다.** 키 한도(429)에 걸리면 운영 교사도 503 을 본다 — 그래서 운영 감시와 시간대가 필요하다.
- 부하기는 같은 망의 일회용 컨테이너(`run --rm --no-deps`)이고 `http://backend:8000` 으로 보낸다. nginx · Next 층은 거치지 않는다.
- `load_check.py` 는 `--base` 가 `backend` · `localhost` · `127.0.0.1` 이 아니면, 그리고 환경에 `LOADTEST=1` 이 없으면 돌지 않는다
  (`compose.loadtest.yml` 이 loadtest backend 에만 넣는다). `ssample.duckdns.org` 는 어떤 플래그로도 거절한다.
  **이 스크립트는 LLM 을 부르지 않는다.** 돈이 나가는 곳은 loadtest backend 의 LLM 호출이다.

---

## 시작 전 — 비용 0

하나라도 못 채우면 미룬다.

- [ ] **팀 합의**: 시간대와 배포 정지. 배포(develop · main 머지 push, 수동 dispatch 모두)를 그 시간 막는다.
  ```bash
  # 로컬(gh 로그인된 곳)에서
  gh workflow disable Deploy -R kakaotechcampus-4/ktc4-kangwon-2     # .github/ 파일은 건드리지 않는다
  gh run list -R kakaotechcampus-4/ktc4-kangwon-2 --workflow Deploy --limit 3   # 도는 배포가 없어야 한다
  ```
  끝나면 `gh workflow enable Deploy …` 로 켜고, 그 사이 머지된 것이 있으면 한 번 올린다. **못 막으면 미룬다** (develop 머지 = 운영 배포다).
- [ ] **시간대**: 교사 사용이 없는 때, **백업 cron(03:15 KST = 18:15 UTC) 전에 정리까지** 끝낸다. 약 1시간 + 여유 → 02:00 KST 전에 시작.
- [ ] **어젯밤 백업이 있다**: `ls -t ~/backup | head -2` · `aws s3 ls s3://ktc4-kangwon-2-backup/backup/ | tail -2`. 없으면 `sudo scripts/backup.sh` 를 손으로.
- [ ] **메모리**: `free -m` 의 available 이 1.5GB 이상 (loadtest 상한 합 1.5GB + 일회용 부하기 컨테이너 수십 MB). 아니면 미룬다. swap 사용량도 적어 둔다.
- [ ] **CPU 크레딧** (t3.medium): 콘솔 / CloudWatch `CPUCreditBalance` 를 적어 둔다. 바닥이면 미룬다. (unlimited 모드면 바닥이어도 안 느려지고 초과 요금이 붙는다 — 모드도 적어 둔다.)
- [ ] **엘리스 이달 누적**: 콘솔(또는 담당자)에서 확인. 월 예산 ₩120,000 에 이번 상한 ₩30,000 을 더해도 넉넉한가.
  사용자가 「크레딧 넉넉」 확인으로 대신하면 그 사실을 아래 결과표에 적는다.
- [ ] 로컬에서 `pytest tests/test_load_check.py` 통과, 로컬 리허설(아래 「로컬 리허설」)을 한 번 돌렸다.

---

## 서버 명령 순서

Session Manager 로 들어가 사람이 친다. 터미널을 3개 쓴다: ① 작업 ② 운영 감시 ③ 자원 기록.

### A. 들어가기 · 운영 상태 적기

```bash
sudo -iu ubuntu
docker() { sudo docker "$@"; }        # sudo 가 필요한 환경일 때만 (docs/deploy.md 는 sudo docker compose)

env | grep -E '^COMPOSE_' || echo "COMPOSE_* 없음"   # 있으면 새 셸을 연다 — 셸 변수가 .env 보다 먼저다
cd ~/ktc4-kangwon-2
git log --oneline -1                                                                 # 운영 커밋
docker inspect ktc4-kangwon-2-backend-1 --format '{{.Image}} {{.HostConfig.LogConfig.Type}}'   # 이미지 ID · 로그 드라이버
free -m; df -h /
docker network inspect $(docker network ls -q) --format '{{range .IPAM.Config}}{{.Subnet}} {{end}}' | grep -c '172\.29\.'   # 0
docker volume ls | grep -c loadtest                                                  # 0
```

### B. loadtest 폴더 · .env · 이미지 태그

```bash
mkdir -p ~/loadtest-457/out && cd ~/loadtest-457 || exit 1      # 실패하면 셸을 닫는다 — 운영 폴더에서 이어가면 안 된다
git clone --depth 1 --branch feature/load-check https://github.com/kakaotechcampus-4/ktc4-kangwon-2.git src
cp src/backend/scripts/compose.loadtest.yml src/backend/scripts/load_check.py .
cp ~/ktc4-kangwon-2/docker-compose.yml .
git -C src log --oneline -1                                   # 부하 스크립트 커밋

[ ! -e .env ] || { echo ".env 가 이미 있다 — 멈춘다"; exit 1; }
umask 077
DBPW=$(openssl rand -hex 24); SECRET=$(openssl rand -hex 32)
cat > .env <<EOF
COMPOSE_PROJECT_NAME=loadtest
COMPOSE_FILE=docker-compose.yml:compose.loadtest.yml
POSTGRES_PASSWORD=$DBPW
DATABASE_URL=postgresql+psycopg://ssuksak:$DBPW@db:5432/ssuksak
SECRET_KEY=$SECRET
LLM_MODE=real
IS_SERVER=1
ALLOW_TEST_RESET=0
EOF
grep -E '^(ELICE_MLAPI_BASE_URL|ELICE_MLAPI_API_KEY)=' ~/ktc4-kangwon-2/.env >> .env   # 화면에 안 찍는다
unset DBPW SECRET
grep -c '^ELICE_MLAPI_' .env                                  # 2 여야 한다

IMG=$(docker inspect ktc4-kangwon-2-backend-1 --format '{{.Image}}')
docker tag "$IMG" ssample-loadtest-backend:457
docker image inspect ssample-loadtest-backend:457 --format '{{.Id}}'     # 위 IMG 와 같아야 한다
```

### C. 게이트 — 하나라도 FAIL 이면 여기서 멈춘다

`docker compose config` 출력에는 비밀번호가 들어 있다. 변수에만 담고 찍지 않는다.

```bash
cd ~/loadtest-457 || exit 1
CFG=$(docker compose config); bad=0
chk() { if grep -qE -- "$1" <<<"$CFG"; then echo "ok    있다: $1"; else echo "FAIL  있어야: $1"; bad=1; fi; }
no()  { if grep -qE -- "$1" <<<"$CFG"; then echo "FAIL  없어야: $1"; bad=1; else echo "ok    없다: $1"; fi; }
chk '^name: loadtest$'
chk 'subnet: 172\.29\.0\.0/16'
chk 'name: loadtest_default'
chk 'name: loadtest_pgdata'
chk 'image: ssample-loadtest-backend:457'
chk 'LOADTEST: "1"'
chk "LLM_MODE: ${WANT_MODE:-real}"
chk "IS_SERVER: \"${WANT_SERVER:-1}\""      # real 모드는 IS_SERVER=1 이 아니면 모든 요청이 실패한다
chk "restart: 'no'"
chk 'mem_limit: "?536870912'
chk 'mem_limit: "?1073741824'
no  'published:'
no  'build:'
no  'journald'
no  'ktc4-kangwon-2'
no  '172\.28\.'
[ "$(docker compose config --services | sort | tr '\n' ' ')" = "backend db " ] && echo "ok    서비스 backend db 만" || { echo "FAIL  서비스"; bad=1; }
unset CFG; [ "$bad" = 0 ] && echo "게이트 통과" || echo "게이트 실패 — 멈춘다"
```

### D. 띄우기

```bash
cd ~/loadtest-457 || exit 1
docker compose up -d --wait db
docker compose run --rm --no-deps backend alembic upgrade head      # loadtest DB 에만 (DATABASE_URL 이 @db = loadtest 망의 db)
docker compose up -d --no-build backend
docker compose ps
# backend 는 healthcheck 가 없어 up 이 바로 돌아온다. uvicorn 이 뜰 때까지 기다린다 (최대 60초)
for i in $(seq 30); do
  docker compose exec -T backend python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health/ready')" 2>/dev/null && break
  sleep 2
done
docker compose exec -T backend python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/health/ready').read())"   # {"status":"ok","db":"ok"}
docker ps --format '{{.Names}} {{.Status}}' | grep ktc4-kangwon-2     # 운영 컨테이너가 그대로 Up 인지
```

### E. 감시 — 측정 내내 켜 둔다

**② 운영 감시** (다른 터미널). 운영 backend 로그가 새로 이 줄을 내면 **측정을 멈춘다.** 운영 로그 드라이버가 json-file 이든 journald 든 `docker logs` 로 읽힌다.

```bash
docker logs -f --since 1m ktc4-kangwon-2-backend-1 2>&1 | grep --line-buffered -E 'outcome=(budget|timeout|failed|not_delivered)|unexpected_error|llm_cap_hit'
```

운영 상태도 같이 본다 (운영 backend 는 호스트 8000 을 연다):

```bash
while sleep 15; do date -u +%T | tr '\n' ' '; curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/health/ready; done
```

**③ 자원 기록** (프로세스 하나. 1초마다 `docker stats` 를 새로 부르는 반복은 그 자체가 CPU 를 쓴다):

```bash
cd ~/loadtest-457 || exit 1
docker stats --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}' \
  ktc4-kangwon-2-backend-1 ktc4-kangwon-2-db-1 loadtest-backend-1 loadtest-db-1 > out/docker-stats.log
```

### F. 단계 실행

```bash
cd ~/loadtest-457 || exit 1
lt() {      # 부하기. 키 · LLM 설정은 빼고(mock) 보낸다 — 이 컨테이너는 LLM 을 안 부른다
  docker compose run --rm --no-deps -T \
    -e LLM_MODE=mock -e IS_SERVER=0 -e ELICE_MLAPI_API_KEY= \
    -v "$PWD/load_check.py:/lt/load_check.py:ro" -v "$PWD/out:/lt/out" \
    backend python /lt/load_check.py "$@"
}
stage() {   # 로그를 덤프하고 마지막 단계를 분석한다. 인자 = 다음 단계의 동시 요청 수 (지출은 누적 전체)
  f=backend-$(date -u +%Y%m%dT%H%M%SZ).log
  docker compose logs -t --no-color backend > out/$f
  lt analyze --out /lt/out --backend-log /lt/out/$f --next-n "$1" --last-only | tee out/analysis-${f%.log}.txt
}
B=http://backend:8000
```

**요청마다 새 반이 든다** (같은 반 · 같은 날 일지는 409, 연간은 반당 하나, 같은 반이면 `FOR UPDATE` 로 저장이 줄을 선다).
필요한 반 수 = max(S1 총 요청 수, S2 총 요청 수) — 아래 계획이면 S1 214 · S2 144 이므로 220. 모자라면 `setup` 을 다시 돌리면 더해진다.

```bash
lt setup --base $B --classes 220 --out /lt/out
```

단계는 **한 번에 하나**, 끝날 때마다 `stage` 로 지출과 다음 단계 최악 비용을 보고 이어갈지 정한다.

```bash
# 1  기준선 — 첫 회차는 예열로 따로 센다. 비용(₩/건)을 보고 아래 반복 수를 정한다
lt burst --base $B --scenario s1 --n 1 --repeat 4 --warmup 1 --out /lt/out;  stage 10
lt burst --base $B --scenario s2 --n 1 --repeat 4 --warmup 1 --out /lt/out;  stage 10
# 2  동시 10
lt burst --base $B --scenario s1 --n 10 --repeat 3 --out /lt/out;  stage 10
lt burst --base $B --scenario s2 --n 10 --repeat 2 --out /lt/out;  stage 20
# 3  동시 20
lt burst --base $B --scenario s1 --n 20 --repeat 3 --out /lt/out;  stage 20
lt burst --base $B --scenario s2 --n 20 --repeat 2 --out /lt/out;  stage 40
# 4  동시 40
lt burst --base $B --scenario s1 --n 40 --repeat 3 --out /lt/out;  stage 40
lt burst --base $B --scenario s2 --n 40 --repeat 2 --out /lt/out;  stage 40
```

**한 줄씩 따로 친다** — 줄마다 `stage` 의 표 · 지출 · 운영 감시를 보고 다음 줄을 보낼지 정한다.

놀이형 연간은 기본 제외다(연결을 놓는 대조군). 기준선 비용을 보고 동시 1 · 10 만 넣을지 정한다.

전부 끝나면 **전체 표**를 한 번 뽑아 결과에 옮긴다 (`--last-only` 없이, 가장 마지막 덤프로):

```bash
lt analyze --out /lt/out --backend-log /lt/out/$(ls -t out | grep '^backend-.*Z\.log$' | head -1) | tee out/analysis-final.txt
```

`--repeat` 는 회차 사이에 `--pause`(기본 5초) 쉰다. 클라이언트 시간 초과가 생기면 서버가 끝나길 `--settle`(기본 60초) 기다린 뒤 행 수를 센다.
회차가 길어 터미널이 끊길 수 있으면 `tmux` 안에서 돌린다.

### G. 읽는 법

`stage` 가 단계마다 이 표를 낸다 (회차를 합친 값).

- **결과표 (상태, code, message)**: 실패를 이 셋으로 가른다.
  - 500 `INTERNAL_ERROR` + `unexpected_error … error=sqlalchemy.exc.TimeoutError` → **풀 대기 초과**
  - 500 `GENERATION_FAILED` — S1 은 문구가 갈린다: 「AI 초안을 만들지 못했습니다」(LLM 실패 · 시간 초과 — `llm_call outcome=` 으로 가른다) ·
    「AI 응답이 약속한 형식이 아닙니다」(형식 위반) · 「초안이 문서 규격을 통과하지 못했습니다」(게이트 2단 반려)
  - 503 `LLM_BUDGET_EXCEEDED` → 엘리스가 401 · 403 · 429 를 냈다 (**셋을 가를 수 없다**)
  - `CLIENT_TIMEOUT`(180초) · `CONN_ERROR` → 별도 분류
- **LLM 첫 시작 시각 히스토그램**: `llm_call` 로그 시각 − `ms` = LLM 시작. 요청 하나가 여러 번 부르면(S2 는 연달아 2번, 재시도) 처음 시작만 센다(`run=` 으로 묶는다).
  burst 시작 t0 기준으로 **0초 · H초 · 2H초에 15개씩 몰리면 풀이 병목**이라는 직접 증거다.
- **unexpected_error**: `경로 + 예외 클래스` 별 건수. `/api/auth/me` 쪽 풀 대기 초과(표본이 맞은 것)와 생성 경로의 것을 가른다.
- **요청 − plan_timing 줄 수** (S2): 핸들러에 못 닿은 수. `plan_timing` 은 인증 질의(= 풀 대기) 뒤에 시작해 풀 대기를 못 본다.
- **왕복 − total_ms** (S2): 스레드 대기 + 풀 대기 + 인증 질의 + 응답 직렬화.
- **/auth/me**: LLM 을 안 부르는 인증 GET 의 지연 · 실패. 생성이 몰릴 때 다른 화면이 받는 피해.
- **pg_stat 최대**: 붙잡힌 연결 · `idle in transaction`. 풀이 막히면 15 근처가 보인다.
- **행 수 대조**: 201 수와 DB 에 실제 저장된 행 수. 「저장됐는데 실패 응답」을 따로 센다(S1 은 commit 뒤 응답을 만들며 연결을 다시 빌린다).
- **원화 지출**: `llm_usage` 토큰 × 단가(`scripts/llm-usage.sh` 와 같은 sol 단가, 캐시 할인 없음). `outcome=timeout` 은 과금됐을 수 있어 관측된 최대 단가로 셈한다.
  끝의 **다음 단계 최악 비용**(요청 수 × 요청당 최대 호출 × 최대 단가; S1 2 · S2 4)이 「멈춘다」면 보내지 않는다.

### H. 중단 규칙

다음 중 하나라도 있으면 **다음 단계를 보내지 않는다** (이미 보낸 요청은 못 되돌린다).

1. 운영 감시 터미널에 새 줄이 떴다 (`outcome=(budget|timeout|failed|not_delivered)` · `unexpected_error`), 또는 운영 `/health/ready` 가 200 이 아니다.
2. `stage` 의 다음 단계 최악 비용이 「멈춘다」다 — 누적 지출 + 최악 > ₩30,000.
3. loadtest 에서 `LLM_BUDGET_EXCEEDED`(503)가 나왔다. **60초 뒤** S1 한 건(`lt burst … --scenario s1 --n 1`)을 보낸다.
   성공이면 429(한도)였다고 기록하고 끝낸다. 계속 503 이면 **키가 지워졌을 수 있다** — 즉시 팀에 알리고 엘리스 콘솔을 확인한다.
4. `free -m` available 이 600MB 아래이거나 swap 이 늘기 시작한다, 또는 `docker stats` 에서 loadtest 컨테이너가 OOM 으로 죽었다.
5. 시간이 02:45 KST(정리 전 여유 30분)를 넘겼다.

### I. 정리 — 이 폴더 안에서만

```bash
cd ~/loadtest-457 || exit 1                                            # 실패하면 셸을 닫는다 — 운영 폴더에서 down -v 가 돌면 안 된다
# 먼저 ② 운영 감시 · ③ 자원 기록 터미널에서 Ctrl-C 로 끈다
docker compose logs -t --no-color backend > out/backend-final.log
docker compose ls                                                      # loadtest 의 CONFIG FILES 가 ~/loadtest-457 아래여야 한다
docker compose -p loadtest down -v                                     # -p 로 한 번 더 못 박는다. -v 가 loadtest_pgdata 를 지운다
docker rmi ssample-loadtest-backend:457                                # 태그만 지운다. -f 는 쓰지 않는다 (서버에서는 Untagged 만 나온다)
docker volume ls | grep loadtest; docker network ls | grep loadtest    # 둘 다 비어야 한다
docker images | grep loadtest                                          # 비어야 한다
```

**`rm -rf ~/loadtest-457` 전에 `out/` 를 옮긴다.** `burst-*.json` · `backend-*.log` · `analysis-*.txt` · `docker-stats.log` 를
로컬 `docs/evaluation/runs/<날짜>-load-check/` 로 가져온다. **`state.json` 은 옮기지 않는다**(loadtest 토큰 · 비밀번호). 로그에는 프롬프트 · 응답 내용이 없다(숫자와 이름뿐).

```bash
rm -rf ~/loadtest-457
unset -f lt stage docker

# 운영 확인
docker ps --format '{{.Names}} {{.Status}}' | grep ktc4-kangwon-2        # 전부 Up, 재시작 흔적 없음
curl -sf localhost:8000/health/ready; echo
free -m; df -h /
```

그리고 `gh workflow enable Deploy -R kakaotechcampus-4/ktc4-kangwon-2`.

---

## 로컬 리허설

서버에서 하기 전에 같은 명령으로 한 번 돈다. **로컬에서 `LLM_MODE=real` 은 금지다** — mock 으로 배관(가입 · 반 · 일과 기록 · burst · 로그 덤프 · 분석 · 정리)만 본다.

- 작업 폴더를 저장소 밖에 만들고 `docker-compose.yml` · `backend/scripts/compose.loadtest.yml` · `backend/scripts/load_check.py` 를 복사한다. `out/` 도 만든다.
- 로컬 이미지를 `docker build -t ssample-loadtest-backend:457 -f backend/Dockerfile .` 로 만든다 (서버에서는 `docker tag` 다).
- `.env` 는 B 와 같되 `LLM_MODE=mock` · `IS_SERVER=0` 이고 엘리스 줄이 없다. 게이트는 `WANT_MODE=mock WANT_SERVER=0` 을 붙여 C 를 돈다.
- 나머지(D · F · I)는 그대로 — `~/loadtest-457` 만 그 작업 폴더로 바꿔 읽는다. 망 대역 172.29.0.0/16 이 로컬 도커 망과 겹치지 않는지 A 의 `docker network inspect …` 로 먼저 본다.
- **mock 에는 `llm_call` · `llm_usage` 줄이 없다** — LLM 시작 시각 · 원화 계산은 시험(`test_load_check.py`)과 합성 로그로만 확인했다. 실제 줄 모양은 서버 첫 단계(기준선)에서 처음 본다.

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
- 지출은 로그의 토큰 × 단가이고 캐시 할인이 없어 실제보다 조금 높다. 시간 초과분은 추정이다.

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
| 이번 측정 지출 (시간 초과 추정 포함) | 측정 전 |
| 서버 `free -m` available (전 → 후) | 측정 전 |
| 운영 감시에 걸린 것 | 측정 전 |

### S1 일지 초안 (LLM 1회)

| 동시 | 회차 | 요청 | 201 | 실패 (상태 · code) | p50 | p95 | max | LLM 시작 물결 | /auth/me p95 · max | pg 연결 최대 | 저장됐는데 201 아님 | 지출 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 (예열 제외) | 측정 전 | | | | | | | | | | | |
| 10 | 측정 전 | | | | | | | | | | | |
| 20 | 측정 전 | | | | | | | | | | | |
| 40 | 측정 전 | | | | | | | | | | | |

### S2 주제형 연간 (LLM 2회)

| 동시 | 회차 | 요청 | 201 | 실패 (상태 · code) | p50 | p95 | max | LLM 시작 물결 | 왕복 − total_ms | 요청 − plan_timing | /auth/me p95 · max | pg 연결 최대 | 저장됐는데 201 아님 | 지출 |
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
