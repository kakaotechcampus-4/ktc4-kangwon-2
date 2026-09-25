from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    # 기본값을 두지 않는다. "dummy" 가 들어간 채로 real 모드가 돌면
    # 키 없이 호출이 나가고 401 이 날 때까지 원인을 못 찾는다.
    elice_api_key: str | None = None
    # str 이면 'Real' · 'production' 이 들어와도 통과하고 mock 분기에 안 걸려
    # 실제 호출이 나간다. 이제 기동 시점에 터진다.
    llm_mode: Literal["mock", "real"] = "mock"
    is_server: bool = False

    # 로그인 토큰 서명 열쇠. 바뀌면 발급된 토큰이 전부 무효가 된다.
    # 기본값을 두지 않는다 — 기본값이 있으면 서버에 안 넣은 채로 배포되고,
    # 그 열쇠는 저장소에 적혀 있으므로 누구나 토큰을 만들 수 있다.
    secret_key: str

    # 트렌드 수집 (ADR-016). 없으면 그 소스만 건너뛰고 나머지는 모은다.
    # 주 1회 작업에서만 쓴다 — 교사 요청 경로에서는 부르지 않는다.
    youtube_api_key: str | None = None
    naver_client_id: str | None = None
    naver_client_secret: str | None = None


settings = Settings()
