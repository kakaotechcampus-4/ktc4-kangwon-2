from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    # 기본값을 두지 않는다. 주입이 안 된 채로 "dummy" 가 들어가면
    # real 모드에서 키 없이 호출이 나가고 401 이 날 때까지 원인을 못 찾는다.
    elice_api_key: str | None = None
    # 'Real' · 'production' 같은 값이 들어오면 기동 시점에 터진다.
    llm_mode: Literal["mock", "real"] = "mock"
    is_server: bool = False


settings = Settings()
