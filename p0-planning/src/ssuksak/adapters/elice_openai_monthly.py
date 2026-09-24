"""Elice OpenAI-compatible adapter for Monthly proposal generation.

No environment is read at import time. The default transport uses the Python
standard library, so Planning Core remains importable without an OpenAI SDK.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import os
from typing import Protocol
from urllib import error, request as urllib_request
from urllib.parse import urlparse

from ssuksak.planning.planner.contracts import (
    MONTHLY_MODEL,
    MonthlyCellPlanningRequest,
    MonthlyPlanningRequest,
    RawLlmResponse,
)
from ssuksak.planning.planner.parser import (
    CELL_RESPONSE_SCHEMA,
    MONTHLY_RESPONSE_SCHEMA,
)


class MonthlyLlmConfigurationError(RuntimeError):
    pass


class MonthlyLlmProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MonthlyLlmConfig:
    base_url: str
    api_key: str = field(repr=False)
    model: str = MONTHLY_MODEL
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise MonthlyLlmConfigurationError(
                "ELICE_MLAPI_BASE_URL must be an absolute HTTPS URL"
            )
        if not self.api_key.strip():
            raise MonthlyLlmConfigurationError("ELICE_MLAPI_API_KEY is required")
        if self.model != MONTHLY_MODEL:
            raise MonthlyLlmConfigurationError(
                f"Monthly planner model must be {MONTHLY_MODEL}"
            )
        if self.timeout_seconds <= 0:
            raise MonthlyLlmConfigurationError("MONTHLY_LLM_TIMEOUT_SECONDS must be positive")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "MonthlyLlmConfig":
        source = os.environ if env is None else env
        base_url = source.get("ELICE_MLAPI_BASE_URL", "").strip()
        api_key = source.get("ELICE_MLAPI_API_KEY", "").strip()
        if not base_url:
            raise MonthlyLlmConfigurationError("ELICE_MLAPI_BASE_URL is required")
        if not api_key:
            raise MonthlyLlmConfigurationError("ELICE_MLAPI_API_KEY is required")
        model = source.get("MONTHLY_LLM_MODEL", MONTHLY_MODEL).strip()
        timeout_raw = source.get("MONTHLY_LLM_TIMEOUT_SECONDS", "30").strip()
        try:
            timeout = float(timeout_raw)
        except ValueError as exc:
            raise MonthlyLlmConfigurationError(
                "MONTHLY_LLM_TIMEOUT_SECONDS must be numeric"
            ) from exc
        return cls(base_url, api_key, model, timeout)

    @property
    def endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


class JsonTransport(Protocol):
    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout: float,
    ) -> Mapping[str, object]: ...


class UrllibJsonTransport:
    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout: float,
    ) -> Mapping[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib_request.Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urllib_request.urlopen(req, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise MonthlyLlmProviderError("Elice MLAPI request failed") from exc
        if not isinstance(result, dict):
            raise MonthlyLlmProviderError("Elice MLAPI response must be a JSON object")
        return result


class EliceOpenAiMonthlyAdapter:
    def __init__(
        self,
        config: MonthlyLlmConfig,
        *,
        transport: JsonTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport or UrllibJsonTransport()

    def generate_monthly(self, request: MonthlyPlanningRequest) -> RawLlmResponse:
        return self._complete(
            request.system_prompt,
            request.user_content,
            schema_name="monthly_plan_proposal",
            schema=MONTHLY_RESPONSE_SCHEMA,
        )

    def generate_cell(self, request: MonthlyCellPlanningRequest) -> RawLlmResponse:
        return self._complete(
            request.system_prompt,
            request.user_content,
            schema_name="monthly_cell_proposal",
            schema=CELL_RESPONSE_SCHEMA,
        )

    def _complete(
        self,
        system_prompt: str,
        user_content: str,
        *,
        schema_name: str,
        schema: Mapping[str, object],
    ) -> RawLlmResponse:
        payload: dict[str, object] = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0,
            # Provider-enforced strict Structured Output; the parser still validates.
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        }
        result = self._transport.post_json(
            self._config.endpoint,
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
            timeout=self._config.timeout_seconds,
        )
        try:
            choices = result["choices"]
            message = choices[0]["message"]  # type: ignore[index]
            content = message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise MonthlyLlmProviderError(
                "Elice MLAPI response is missing choices[0].message.content"
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise MonthlyLlmProviderError("Elice MLAPI returned empty content")
        model = result.get("model", self._config.model)
        if not isinstance(model, str) or not model.strip():
            raise MonthlyLlmProviderError("Elice MLAPI returned an invalid model")
        request_id = result.get("id")
        if request_id is not None and not isinstance(request_id, str):
            raise MonthlyLlmProviderError("Elice MLAPI returned an invalid request id")
        return RawLlmResponse(content, model, request_id)
