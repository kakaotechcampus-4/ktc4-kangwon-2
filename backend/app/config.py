from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    elice_api_key: str = "dummy"
    llm_mode: str = "mock"
    is_server: bool = False


settings = Settings()
