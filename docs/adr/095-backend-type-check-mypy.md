# ADR-095: 백엔드 타입을 mypy 로 검사하고, 기존 `backend (ruff)` 안에서 돈다

- 날짜: 2026-11-11
- 상태: 채택
- 관련: ADR-011(CI 가 검증하는 범위 — 보충) · `backend/pyproject.toml` `[tool.mypy]` · `.github/workflows/ci.yml` `backend (ruff)`

## 맥락

[실측] 백엔드 코드에는 타입 표기가 이미 많다(`PostgresPlanRepository[TPlan]`, `Annotated[...]`, 함수 시그니처). 그런데 CI 는 ruff(형식) 와 pytest(동작) 만 본다.
표기가 코드와 어긋나도 아무도 모른다. 도입 때 mypy 를 처음 돌렸더니 `backend/app` 에서 None 때문이 아닌 오류만 101개(30개 파일)였다.
예: `_log_usage(...) -> None` 인데 두 값을 돌려주고 호출하는 쪽이 그 값을 쓴다(`shared/llm/client.py`), `latest_week() -> RawItem | None` 인데 `Path` 를 돌려준다(`trends/router.py`),
한 함수 안에서 같은 변수 이름에 서로 다른 종류의 값을 담는다(`documents/router.py` 의 `by_id`, `source`).

표기가 맞는지는 읽는 사람이 눈으로 확인할 수밖에 없다.

## 결정

1. **mypy 를 `backend/app` 에만 돌린다.** 테스트(`tests/`)와 `p0-planning/` 은 범위 밖이다.
   Core(`ssuksak`)는 `py.typed` 가 없어 설치본으로는 타입을 읽지 못한다 — `mypy_path` 로 원본 폴더를 읽고, `follow_imports = "silent"` 로 Core 안의 오류는 보고하지 않는다.
2. **`mypy==2.4.1` · `types-lxml==2026.2.16` 을 `backend[dev]` 에 고정한다.** `pydantic.mypy` 플러그인을 켠다(alias `from_` · Settings 필수값을 읽게). `check_untyped_defs` · `warn_unused_ignores` 를 켠다.
   `yaml` · `reportlab` 은 `ignore_missing_imports` 로 둔다(stub 을 깔지 않는다).
3. **새 job 을 만들지 않고 기존 `backend (ruff)` job 에 단계를 붙인다.** job 이름과 기존 단계(Install ruff · ruff check · ruff format --check)는 그대로다.
   타입을 읽으려면 앱 의존이 깔려 있어야 하므로 `Install planning core` → `Install`(`pip install -e ".[dev]"`) → `mypy` 세 단계를 더한다.
   세 단계는 `!cancelled()` 로 돈다 — ruff 가 실패해도 타입 결과가 함께 보인다(ADR-011 이 같은 job 에 합치지 않은 이유가 이것이었다). mypy 단계는 설치가 성공했을 때만 돈다.
4. **도입 때 오류는 0 으로 맞췄다.** 동작은 바꾸지 않았다.
   - None 이 아닌 오류 101개는 **표기만** 고쳤다 — 타입 표기, `cast`, 읽기 전용 Protocol(`SectionLike`), 제네릭 한도(`PostgresPlanRepository[TPlan: _PlanKeys]`), 한 함수 안 지역 변수 이름 나누기.
     assert · 새 분기 · 기본값 · 공개 API 는 건드리지 않았다.
   - 도구 한계로 표기만으로 못 고치는 11줄(`Result.rowcount` · `Literal[튜플변수]` · `__args__` · `@computed_field` 등)은 그 줄에 `# type: ignore[코드]` 를 달고 **바로 윗줄에 이유**를 적었다.
   - None 오류(도입 때 있던 None 진단 — 대부분은 앞에서 `if` 로 이미 확인한 값이지만, 양식 구조를 믿고 바로 쓰는 곳(hwpx 의 `find()` 결과 등)도 섞여 있다)는 동작을 바꾸지 않고 265줄에 `# type: ignore[코드]` 로 묶었다. 이유는 줄마다 쓰지 않고 `[tool.mypy]` 위 주석에 한 번 적었다.
5. **새 코드에는 `# type: ignore` 를 붙이지 말고 고친다.** 오류를 고치면 `warn_unused_ignores` 가 남은 표시를 알려 표시가 줄어들기만 한다.
6. 로컬은 `cd backend && mypy` 다.

## 근거

- [실측] 0e02a19c 에서 설정 없이 돌리면 436개다. None 검사를 끄고 Core 타입을 읽게 한 상태에서 `pydantic.mypy` 를 켜면 128 → 96 으로 줄어 alias(`from_`) · Settings 필수값 오탐이 사라진다.
- [실측] e0ba5de3 에서 `check_untyped_defs` 를 켠 채 None 검사를 켜면 317개, 끄면 101개다. 101개가 앞 절의 그 숫자이고, 차이 216개가 None 오류다.
- [실측] `types-lxml` 은 오탐이 0 이고 None 오류를 85개 더 찾는다(317 → 402). 그래서 stub 중 이것만 둔다. `yaml` 은 stub 을 깔아도 `safe_load` 가 `Any` 를 돌려줘 얻는 것이 없고, `reportlab` stub 은 오탐만 늘었다.
- [실측] `backend (ruff)` job 은 9초이고, 앱 의존 설치가 약 22초 더 든다. mypy 자체는 캐시 없이 로컬에서 131개 파일에 약 3초다. 셋을 더해도 1분이 안 된다.
- [판단] None 오류를 줄 단위로 묶는 쪽이 낫다고 봤다. 파일 단위로 끄면 그 파일에 새로 들어오는 None 오류까지 숨는다. 줄 단위 표시는 새 줄에는 없으므로 새 오류는 CI 가 막는다.
- [판단] 기존 job 이름을 지키면 develop 의 필수 검사 목록을 바꾸지 않고도 바로 막는다(ADR-011 결과 절: 새 job 은 필수 검사에 이름을 더하는 별도 작업이 필요했다).

## 대안

- **pyright** — [실측] 기본(standard) 설정으로 `backend/app` 341개. `None` 을 `int` 자리에 넘기는 오류를 다른 인자 오류와 따로 다룰 수 없어 줄이기 어렵다. 속도는 둘 다 수 초라 차이가 안 된다.
- **새 job `backend (type check)`** — develop 필수 검사에 이름을 더하기 전까지는 막지 못한다. 필수 검사 설정은 저장소 설정(브랜치 보호) 작업이다.
- **파일 단위로 None 검사 끄기**(`[[tool.mypy.overrides]]`) — 위 근거대로 새 None 오류도 숨는다.
- **stub 을 셋 다 깔기**(`types-PyYAML` · `types-reportlab` 포함) — 위 근거대로 얻는 것 없이 오탐만 는다.
- **None 오류까지 전부 고치기** — 265줄을 한 PR 에서 고치면 `assert` · 새 분기가 섞여 동작이 바뀌고, 리뷰어가 diff 에서 본론을 찾을 수 없다. 후속으로 나눠 줄인다.
- **`p0-planning` 도 검사** — 별도 패키지에 자체 테스트가 있고 범위가 둘로 커진다. 이번에는 backend 만 한다.

## 결과

- `backend (ruff)` 는 이제 ruff 와 mypy 를 같이 돈다. job 이름은 develop 필수 검사라 바꾸지 않는다.
- **develop 규칙이 PR 브랜치를 최신으로 맞추라고 요구하지 않는다.** 이 변경이 develop 에 들어가기 전에 CI 가 초록이던 PR 은 타입 검사 없이 머지될 수 있다. develop push CI 가 뒤에서 잡는다 — 그때 깨지면 후속 PR 로 고친다.
- 줄 표시(None 265줄 · 도구 한계 11줄)를 줄여 가는 후속이 있다. 한 파일씩 고치고, 고친 줄의 표시는 `warn_unused_ignores` 가 알려 주는 대로 지운다.
- `mypy` · `types-lxml` 은 버전을 고정했다. 올릴 때는 새 오류 · 오탐이 생길 수 있으니 `cd backend && mypy` 로 먼저 본다.
- ADR-011 의 「기존 job 과 합치지 않는다」는 pytest 에 대한 결정이다. 타입 검사는 같은 job 안에서 `!cancelled()` 단계로 돌아 그 이유(앞 단계 실패가 뒤 결과를 가린다)를 같은 방법으로 피한다.
