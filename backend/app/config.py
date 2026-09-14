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


settings = Settings()
