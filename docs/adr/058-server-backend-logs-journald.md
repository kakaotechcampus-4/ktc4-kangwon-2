# ADR-058: 운영 backend 로그는 서버 journald 에 30일 남긴다

- 2026-11-03
- 상태 — 채택
- 관련 — #100 · ADR-036 · `docs/deploy.md` 「서버 로그」

## 맥락

배포할 때 `scripts/deploy.sh` 의 `docker compose up -d` 가 backend 컨테이너를 새로 만든다.
지금 `json-file` 로그는 컨테이너와 같이 지워진다(2026-10-22 서버 확인). 예상 못 한 오류의
`unexpected_error`(#100)와 LLM 호출의 `llm_usage`(ADR-036)도 배포마다 사라진다.
`scripts/llm-usage.sh` 의 합계는 마지막 배포 뒤 것만 담는다.

## 결정

- **운영 서버의 backend 로그만 journald 로 보낸다.** `docker-compose.server.yml` 이
  `logging` 을 통째로 덮어쓰고, 서버 `.env` 의
  `COMPOSE_FILE=docker-compose.yml:docker-compose.server.yml` 이 두 파일을 붙인다.
  이름표는 `ssample-backend` 다. 로컬은 기존 `json-file` 을 쓴다.
- **서버 전체 journal 의 보존 기간을 30일로 둔다.** `MaxRetentionSec=30day` 를 쓰고
  용량 상한은 기본값(파일시스템 10%, 최대 4G)을 둔다. 파일 단위로 지워서 30일보다 조금 더 남을 수 있다.
- `scripts/llm-usage.sh` 는 `CONTAINER_TAG=ssample-backend` journal 을 읽어 배포를 넘어 합산한다.

## 근거

- **[실측]** 2026-11-03 SSM 으로 본 운영 서버에는 `/var/log/journal` 이 있고 journal 은 147.3M 이다.
  `journald.conf` 는 기본값에 `ForwardToSyslog=yes` 만 더했다. 디스크 48G 중 23G 가 남고 메모리 여유는
  2.8Gi 다. Docker 는 29.8.0, Compose 는 5.5.1 이다. backend LogConfig 는
  `{"Type":"json-file","Config":{"max-file":"5","max-size":"10m"}}` 다.
- **[실측]** 로컬 맥 OrbStack 29.8.2 에서 `docker run --log-driver journald ...` 는
  `failed to initialize logging driver: journald is not enabled on this host` 로 실패했다.
- **[실측]** 2026-10-28 ~ 11-01 닷새에 배포가 6번 있었다(`gh run list --workflow=deploy.yml`).
- **[실측]** 2026-11-03 코드에서 로그에 아동 실명이 들어갈 자리를 살폈다. 아동 · 일지 · 관찰 · 일과 기록
  (`backend/app/features/children` · `documents` · `observations` · `routines`)에는 logger 가 없다.
  backend 에서 logger 를 쓰는 곳은 `main.py` · `features/plans/*` · `shared/hwpx.py` ·
  `shared/gates/sections.py` · `shared/llm/client.py` 뿐이다.
- **[실측]** URL 경로 변수는 `plan_id` · `item_id` · `center_id` · `document_id` · `class_id` ·
  `week_id` · `observation_id` · `record_id` · `month` · `child_id` · `form_id` 다(모두 ID 또는 월).
  정의된 쿼리는 `class_id` · `child_id` · `item_id` · `month` · `from` · `to`(날짜) ·
  `kind` · `status`(열거형) · `stale` · `include_impact`(불리언) · `expected_revision`(수정 번호)이다.
  자유 글 칸은 없다. 다만 uvicorn 접근 로그는 요청이 실제로 보낸 쿼리 문자열 전체를 남기므로,
  정의되지 않은 쿼리에 이름을 넣은 요청까지 막아 주지는 않는다.
- **[실측]** `features/plans/router.py` 의 `detail=%s` 에 들어가는 Core 오류 값은 항목 ID · 칸 이름 ·
  양식 버전이다. 계획안에는 아동 이름이 없다. `features/plans/monthly_llm.py` 의 `_why` 는 예외 문장 앞
  200자인데, `shared/llm/client.py` · `elice_openai_monthly.py` 가 던지는 문장은 고정 글귀다.
- **[판단]** 30일이면 파일럿 11/2 ~ 8과 최종 제출 11/11 을 덮는다. 이 기간은 뒤집어도 된다.

로그에 남는 값은 예외 종류 · 위치 · method · path(ID) · user_id · center_id 와 `llm_usage` 의 모델 ·
토큰 숫자다.

## 대안

- **배포 직전 `docker logs` 떠 두기** — 교체 직전 몇 초가 빈다. `deploy.sh` 를 안 거친 재생성은 못 지키고
  파일 정리 규칙도 따로 필요하다.
- **CloudWatch Logs (`awslogs`)** — 로그가 서버 밖으로 복제되어 개인정보 판단이 늘어난다. 기본 blocking 모드에서는
  드라이버 초기화가 실패하면 backend 가 안 뜬다.
- **Sentry** — 오류만 모아 `llm_usage` 는 여전히 사라진다. 기본값이 요청 본문 · 프레임 변수까지 보내 실명 위험이
  가장 크고 새 외부 의존이 생긴다.
- **서버 Docker 기본값(`/etc/docker/daemon.json`)** — Docker 재시작으로 서비스가 잠깐 멈추고 설정이 저장소 밖에만 남는다.
- **공용 `docker-compose.yml` 에 직접 journald** — 위 OrbStack 실측처럼 로컬에서 backend 가 안 뜬다.

## 결과

- 서버 `.env` 한 줄과 journald 설정 파일은 저장소 밖에서 손으로 넣는다 — 순서와 확인은 `docs/deploy.md` 「서버 로그」.
  로컬은 그대로다. 바꾸는 배포에서 기존 컨테이너의 로그가 한 번 사라진다.
- 서버 전체 journal 이 30일로 줄어든다. 백업 로그는 `/var/log/ssuksak-backup.log` 파일이고 nginx · certbot 은
  json-file 이라 영향을 받지 않는다.
- 서버가 통째로 사라지면 로그도 사라진다. DB 는 별도의 S3 백업이 지킨다.
- 예상 못 한 버그의 예외 문장은 미리 알 수 없다 — 계획안 쪽에서는 앞 200자가 남을 수 있다.
- 정의되지 않은 쿼리에 이름을 넣어 보내면 uvicorn 접근 로그에 남는다.
