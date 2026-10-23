from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    # 기본값을 두지 않는다. "dummy" 가 들어간 채로 real 모드가 돌면
    # 키 없이 호출이 나가고 401 이 날 때까지 원인을 못 찾는다.
    # 엘리스 MLAPI. **이름을 어댑터가 찾는 것과 맞춘다** — 예전 ELICE_API_KEY 는
    # 아무도 안 읽어서 "키를 넣었는데 왜 안 되지" 가 났다.
    elice_mlapi_base_url: str | None = None
    elice_mlapi_api_key: str | None = None
    # str 이면 'Real' · 'production' 이 들어와도 통과하고 mock 분기에 안 걸려
    # 실제 호출이 나간다. 이제 기동 시점에 터진다.
    llm_mode: Literal["mock", "real"] = "mock"
    # 주간계획안 생성 · 재생성을 실제 LLM 으로 보낼지(W7). **기본 꺼짐.** `llm_mode=real` 이어도
    # 이것이 꺼져 있으면 주간은 503 이다 — 실제 문장 품질을 확인한 뒤(W7b 실측) 켠다.
    weekly_llm_enabled: bool = False
    is_server: bool = False

    # 파일럿 전 시험용 「전부 지우기」를 켠다. **기본은 꺼짐이고, 파일럿 시작 전에 끈다.**
    #
    # 연간계획안은 확정하면 고칠 수도 지울 수도 없다 — 계획안에는 `unconfirm` 이 없어서
    # 빠져나올 구멍이 없다. 그래서 시험하는 동안만 확정 여부를 안 보고 딸린 월간까지
    # 같이 지우는 길을 연다(`plans/router.py` 의 test-reset).
    #
    # 꺼져 있으면 그 경로는 **404** 다 — 있는지조차 알리지 않는다. 화면 쪽 단추는
    # `NEXT_PUBLIC_ALLOW_TEST_RESET` 가 따로 켠다. 둘이 어긋나도 안전하다:
    # 단추만 켜지면 404 를 받아 「지금은 쓸 수 없어요」가 뜨고, 경로만 켜지면 아무도 안 부른다.
    allow_test_reset: bool = False

    # 로그인 토큰 서명 열쇠. 바뀌면 발급된 토큰이 전부 무효가 된다.
    # 기본값을 두지 않는다 — 기본값이 있으면 서버에 안 넣은 채로 배포되고,
    # 그 열쇠는 저장소에 적혀 있으므로 누구나 토큰을 만들 수 있다.
    secret_key: str

    # 트렌드 수집 (ADR-016). 없으면 그 소스만 건너뛰고 나머지는 모은다.
    # 주 1회 작업에서만 쓴다 — 교사 요청 경로에서는 부르지 않는다.
    youtube_api_key: str | None = None
    naver_client_id: str | None = None
    naver_client_secret: str | None = None
    # 도서관 정보나루. 전국 도서관의 실제 대출 기록이라 광고로 순위가 안 바뀐다(ADR-016).
    library_auth_key: str | None = None


settings = Settings()
