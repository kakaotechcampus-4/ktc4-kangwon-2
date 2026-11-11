# ADR-002: 기능별 폴더 구조

- 2026-09-08
- 상태 — 채택 · 2026-11-11 개정(「결과」의 import 규칙을 실제 코드에 맞췄다 — 아래 「개정」)

## 맥락

멘토가 Vertical Slice Architecture 와 Service-Based Architecture 자료를 줬고,
둘을 혼용해도 되는지 물었다. 답은 이랬다.

> Service based 는 프로젝트보다 훨씬 큰 프로덕션 서비스를 염두한 아키텍처라
> 처음에는 단일 배포로 가도 무방하다.
> Vertical sliced 는 배포 단위에 대한 관심사보다는 디렉터리/모듈 분류에 가까운 개념이다.
> 섞어서 쓰시는 걸 오히려 권장한다.
> 결합된 걸 분리하는 게 분리된 걸 합치는 것보다 쉽다.

## 결정

```
backend/app/features/{activities,centers,forms,plans,trends}/
backend/app/shared/{llm,gates,citation,auth,audit,childCode}/
```

배포는 단일. 컨테이너 3개(db · backend · frontend)뿐이다.

## 근거

`[출처: 멘토]` — vertical slice 는 디렉터리 분류이고 배포 분리는 불편해질 때 한다.

레이어별(`controllers/` `services/` `repositories/`)로 잡으면
한 기능을 고칠 때 세 폴더를 왕복한다. 기능별로 잡으면 한 폴더에서 끝난다.

## 대안

**레이어별 구조** — 더 익숙한 관행이지만 멘토가 말한 vertical slice 가 아니다.

**service-based 분리 배포** — 트렌드봇·생성기·파싱기를 각각 배포.
지금 하면 배포·모니터링 대상이 3개가 되고 얻는 게 없다.
분리 시점은 "특정 서비스에만 트래픽이 몰리거나 공통 로직이 많아질 때"다.

## 결과

- **기능 폴더는 다른 기능 폴더의 내부 구현을 import 하지 않는다.** — 2026-11-11 개정으로 바뀜(아래)
  패키지 최상위(`__init__.py`)가 공개하는 함수만 부른다.

  ```python
  from app.features.centers import get_class            # 된다
  from app.features.centers.repository import ClassRepo  # 안 된다
  ```

- `Repository`·`Service` 를 `shared` 에 넣지 않는다. `[출처: 멘토]`
- 원·반·아동은 여러 기능이 쓰지만 `shared` 에 못 넣으므로 `features/centers` 로 분리했다.
  위 두 규칙이 충돌하는 지점이었고, 두 번째 규칙을 완화해서 해결했다.
- 상세는 [docs/structure.md](../structure.md).

## 개정 (2026-11-11) — import 규칙을 코드에 맞춘다

**사실.** 위 첫 규칙은 한 번도 지켜지지 않았다. 2026-11-11 develop 기준으로
기능 폴더가 다른 기능 폴더의 하위 모듈을 직접 부르는 곳이 **61곳**(28개 파일)이고,
`__init__.py` 로 함수를 공개한 기능 폴더는 **하나도 없다.** 검사하는 도구(lint · 테스트)도 없었다.

| 무엇을 부르나 | 곳 | 예 |
|---|---|---|
| 다른 기능의 `models`(ORM 테이블) | 44 | `centers.models` 21 · `auth.models` 10 · `observations.models` 6 · `routines.models` 4 |
| 다른 기능의 함수 모듈 | 17 | `documents.stale` 3 · `trends.planning` 2 · `routines.weather` 2 · `template_profiles.service` · `plans.queries` 등 |
| 다른 기능의 `router` · `schemas` | 0 | — |

`models` 를 부르는 것은 피할 수 없다. 외래키 · 조인 · 소유 확인(`center_id` 로 거르기)이
다른 기능의 테이블을 알아야 한다. 코드를 61곳 고쳐 `__init__` 뒤로 숨기면 같은 import 를
한 겹 더 감쌀 뿐이고 얻는 것이 없다. 그래서 **코드가 아니라 규칙을 고친다.**

**바뀐 규칙**

- 다른 기능의 `models` 와 함수 모듈(`service` · `planning` · `stale` · `queries` 등)은 직접 import 해도 된다.
- **다른 기능의 `router` · `schemas` 는 import 하지 않는다.** HTTP 경계(요청 · 응답 모양)는 기능마다 따로 둔다. 지금 0곳이다.
- `Repository` · `Service` 를 `shared` 에 넣지 않는 규칙(위 둘째 줄)은 그대로다.
- 기능 폴더를 실제로 떼어 배포할 때(위 「대안」의 분리 시점)는 그 기능을 부르는 곳을 먼저 공개 함수로 모은다. 그 전에는 하지 않는다.

**지금 폴더** — 결정 때의 5개에서 늘었다.

```
backend/app/features/{activities,auth,centers,children,class_access,documents,evaluation,
                      forms,notifications,observations,plans,routines,template_profiles,trends}/
backend/app/shared/{audit,auth,childCode,citation,gates,llm}/
```

배포는 여전히 단일이다. 컨테이너는 db · backend · frontend · nginx · certbot 5개다(`docker-compose.yml`).
