"""`.env` 로딩 범위 테스트.

핵심 보장: `from_env(env=<dict>)`는 개발자 로컬 `.env`를 절대 읽지 않는다.
테스트 결과가 로컬 파일에 좌우되면 안 된다.
"""

from __future__ import annotations

import os

import pytest

from ssuksak.shared.llm import config as config_module
from ssuksak.shared.llm.config import (
    DOTENV_PATH,
    PROJECT_ROOT,
    LLMConfig,
    LLMConfigError,
    load_project_dotenv,
)

EXPLICIT_ENV = {
    "ELICE_MLAPI_BASE_URL": "https://explicit.example/v1",
    "ELICE_MLAPI_API_KEY": "explicit-key",
    "LLM_MODEL": "explicit-model",
    "LLM_TIMEOUT_SECONDS": "7",
    "LLM_MAX_RETRIES": "3",
}


# ------------------------------------------------------------ 경로 확인


def test_dotenv_path_points_at_project_root():
    assert DOTENV_PATH == PROJECT_ROOT / ".env"
    assert (PROJECT_ROOT / "pyproject.toml").is_file(), (
        f"PROJECT_ROOT 계산이 틀렸다: {PROJECT_ROOT}"
    )


def test_env_example_exists_and_has_no_real_secret():
    example = PROJECT_ROOT / ".env.example"
    assert example.is_file(), ".env.example이 있어야 한다"

    text = example.read_text(encoding="utf-8")
    # 필요한 이름이 모두 문서화되어 있다.
    for key in (
        "ELICE_MLAPI_BASE_URL",
        "ELICE_MLAPI_API_KEY",
        "LLM_MODEL",
        "LLM_TIMEOUT_SECONDS",
        "LLM_MAX_RETRIES",
        "LLM_REASONING_EFFORT",
        "RUN_LIVE_LLM_TESTS",
    ):
        assert key in text, f".env.example에 {key}가 없다"

    # Live 기본값은 0이다.
    assert "RUN_LIVE_LLM_TESTS=0" in text

    # 자리표시자만 있고 실제 Key 형태가 없다.
    assert "<your-elice-serverless-api-key>" in text
    for leak in ("sk-", "Bearer ", "elice_live_"):
        assert leak not in text, f".env.example에 실제 Key 흔적이 있다: {leak}"


def test_gitignore_covers_dotenv_but_keeps_example():
    gitignore = PROJECT_ROOT / ".gitignore"
    assert gitignore.is_file(), ".gitignore가 있어야 한다"

    lines = [
        line.strip()
        for line in gitignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert ".env" in lines
    assert ".env.*" in lines
    assert "!.env.example" in lines


# --------------------------------------- 명시적 env는 .env를 읽지 않는다


def test_explicit_env_does_not_load_dotenv(monkeypatch: pytest.MonkeyPatch):
    """가장 중요한 보장. loader가 호출조차 되지 않아야 한다."""
    called: list[bool] = []
    monkeypatch.setattr(
        config_module, "load_project_dotenv", lambda: called.append(True) or True
    )

    config = LLMConfig.from_env(dict(EXPLICIT_ENV))

    assert called == [], "명시적 env 경로에서 .env를 로드했다"
    assert config.model == "explicit-model"


def test_explicit_env_ignores_os_environ(monkeypatch: pytest.MonkeyPatch):
    """OS 환경변수도 섞이지 않는다."""
    monkeypatch.setenv("LLM_MODEL", "os-environ-model")
    monkeypatch.setenv("ELICE_MLAPI_BASE_URL", "https://os.example/v1")

    config = LLMConfig.from_env(dict(EXPLICIT_ENV))

    assert config.model == "explicit-model"
    assert config.base_url == "https://explicit.example/v1"


def test_explicit_env_missing_key_still_fails_fast():
    env = dict(EXPLICIT_ENV)
    del env["LLM_MODEL"]
    with pytest.raises(LLMConfigError, match="LLM_MODEL"):
        LLMConfig.from_env(env)


def test_empty_explicit_env_fails_even_if_os_environ_is_complete(
    monkeypatch: pytest.MonkeyPatch,
):
    for k, v in EXPLICIT_ENV.items():
        monkeypatch.setenv(k, v)

    with pytest.raises(LLMConfigError):
        LLMConfig.from_env({})


# ------------------------------------- 실제 환경 경로에서는 .env를 읽는다


def test_real_env_path_invokes_dotenv_loader(monkeypatch: pytest.MonkeyPatch):
    called: list[bool] = []
    monkeypatch.setattr(
        config_module, "load_project_dotenv", lambda: called.append(True) or True
    )
    for k, v in EXPLICIT_ENV.items():
        monkeypatch.setenv(k, v)

    config = LLMConfig.from_env()

    assert called == [True], "실제 환경 경로에서 .env 로더가 호출되지 않았다"
    assert config.model == "explicit-model"


def test_loader_returns_false_when_dotenv_absent(monkeypatch: pytest.MonkeyPatch):
    """`.env`가 없으면 조용히 False를 반환하고 예외를 던지지 않는다."""
    missing = PROJECT_ROOT / ".env.definitely-not-here"
    monkeypatch.setattr(config_module, "DOTENV_PATH", missing)
    assert load_project_dotenv() is False


def test_loader_reads_a_temp_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """로더가 실제 파일을 읽어 Process 환경에 넣는지."""
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "SSUKSAK_DOTENV_PROBE=loaded-from-file\n", encoding="utf-8"
    )
    monkeypatch.setattr(config_module, "DOTENV_PATH", dotenv)
    monkeypatch.delenv("SSUKSAK_DOTENV_PROBE", raising=False)

    assert load_project_dotenv() is True
    assert os.environ["SSUKSAK_DOTENV_PROBE"] == "loaded-from-file"


def test_dotenv_does_not_override_existing_os_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    """override=False. CI에서 주입한 값이 로컬 파일에 밀리지 않는다."""
    dotenv = tmp_path / ".env"
    dotenv.write_text("SSUKSAK_DOTENV_PROBE=from-file\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "DOTENV_PATH", dotenv)
    monkeypatch.setenv("SSUKSAK_DOTENV_PROBE", "from-os")

    load_project_dotenv()

    assert os.environ["SSUKSAK_DOTENV_PROBE"] == "from-os"


# ------------------------------------------------- 기존 이름 alias 부재


@pytest.mark.parametrize("legacy", ["PROXY_TOKEN", "CHAT_PROXY_URL", "OPENAI_MODEL"])
def test_legacy_env_names_are_not_supported(legacy: str):
    """기존 이름 alias를 두지 않는다. 새 이름 하나로 통일한다."""
    source = pathlib_read(config_module.__file__)
    # 코드에서 legacy 이름을 조회하지 않는다 (docstring 언급은 허용).
    assert f'"{legacy}"' not in source, f"{legacy}를 코드에서 조회하고 있다"


def pathlib_read(path: str) -> str:
    import pathlib

    text = pathlib.Path(path).read_text(encoding="utf-8")
    # docstring 블록을 제외한 실행 코드만 남긴다.
    parts = text.split('"""')
    return "".join(parts[i] for i in range(0, len(parts), 2))


def test_legacy_names_only_appear_in_documentation():
    """문서에는 남겨도 되지만 조회 로직에는 없어야 한다."""
    import pathlib

    source = pathlib.Path(config_module.__file__).read_text(encoding="utf-8")
    assert "PROXY_TOKEN" in source, "docstring에 마이그레이션 안내는 남아 있다"

    executable = pathlib_read(config_module.__file__)
    assert "PROXY_TOKEN" not in executable


# ------------------------------------------------- Key 비노출 유지


def test_api_key_still_hidden_after_dotenv_change():
    config = LLMConfig.from_env(dict(EXPLICIT_ENV))
    assert "explicit-key" not in repr(config)
    assert "explicit-key" not in str(config)
    assert "api_key" not in config.safe_summary
    assert config.api_key == "explicit-key"
