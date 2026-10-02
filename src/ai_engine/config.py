"""LLM provider configuration for the AI analysis engine (Task 6.1).

The AI engine interprets a deterministic `drift_report.json`; it never detects
drift. The LLM is therefore optional: when no provider is configured, a required
credential is missing, or the client library is not installed, `load_config()`
returns a *disabled* configuration with a reason instead of raising, and callers
fall back to deterministic-only output. Only malformed values (an unknown
provider, a non-numeric timeout, an endpoint that is not a plain http(s) URL)
raise `AiConfigError`, because silently ignoring a typo would hide a mistake.

Configuration comes from environment variables only; this module never reads
`.env` files. The provider is opt-in (`AI_LLM_PROVIDER`, default `none`) so
that a credential which merely happens to be present in an environment (for
example a CI runner) never sends Terraform evidence to an LLM by accident.

    AI_LLM_PROVIDER            none | openai | azure_openai        (default none)
    AI_LLM_MODEL               model name (required for openai)
    AI_LLM_TEMPERATURE         0.0-2.0                             (default 0)
    AI_LLM_TIMEOUT_SECONDS     > 0                                 (default 60)
    AI_LLM_MAX_RETRIES         >= 0                                (default 0)

Transport retries are opt-in: with the default, one LLM call is at most one HTTP
request. With AI_LLM_MAX_RETRIES=N the OpenAI client may resend the same prompt
up to N more times (connection errors, 408/409/429, 5xx), so a run can then make
up to N+1 HTTP attempts.

    openai:        OPENAI_API_KEY, AI_LLM_MODEL (required), OPENAI_BASE_URL (optional, any
                   OpenAI-compatible endpoint)
    azure_openai:  AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT,
                   AZURE_OPENAI_DEPLOYMENT (all required),
                   AZURE_OPENAI_API_VERSION (default below)

API keys are held as `pydantic.SecretStr`: they never appear in `repr()`,
`str()`, `summary()` or log events.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from enum import Enum
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, SecretStr

from drift_engine.logs import log_event

logger = logging.getLogger(__name__)

DEFAULT_AZURE_API_VERSION = "2024-10-21"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 0  # opt-in: no hidden resends of the prompt


class AiConfigError(ValueError):
    """A configuration value is malformed. The message never contains a secret."""


class LLMProvider(str, Enum):
    NONE = "none"
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"


class AiConfig(BaseModel):
    """Resolved, immutable LLM configuration.

    `enabled` is False whenever the LLM must not be used; `disabled_reason`
    then says why. A disabled config is a normal state, not an error.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: LLMProvider = LLMProvider.NONE
    enabled: bool = False
    disabled_reason: str | None = "AI_LLM_PROVIDER is not set (LLM analysis is opt-in)"
    model: str | None = None
    api_key: SecretStr | None = None
    base_url: str | None = None
    azure_endpoint: str | None = None
    azure_deployment: str | None = None
    api_version: str | None = None
    temperature: float = DEFAULT_TEMPERATURE
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES

    def summary(self) -> dict[str, Any]:
        """Secret-free description, safe for logs and reports."""
        return {
            "provider": self.provider.value,
            "enabled": self.enabled,
            "disabled_reason": self.disabled_reason,
            "model": self.azure_deployment if self.provider is LLMProvider.AZURE_OPENAI else self.model,
            "endpoint_host": _host(self.azure_endpoint or self.base_url),
            "api_key_set": self.api_key is not None,
        }


def _host(url: str | None) -> str | None:
    return urlsplit(url).hostname if url else None


def _get(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _number(env: Mapping[str, str], name: str, default: float, kind: type, minimum: float, maximum: float | None = None,
            exclusive_min: bool = False) -> Any:
    raw = _get(env, name)
    if raw is None:
        return kind(default)
    try:
        value = kind(raw)
    except ValueError:
        raise AiConfigError(f"{name} must be a {kind.__name__}, got {raw!r}") from None
    too_low = value <= minimum if exclusive_min else value < minimum
    if too_low or (maximum is not None and value > maximum) or value != value:  # value != value: NaN
        bound = f"> {minimum}" if exclusive_min else f">= {minimum}"
        if maximum is not None:
            bound += f" and <= {maximum}"
        raise AiConfigError(f"{name} must be {bound}, got {raw!r}")
    return value


def _url(env: Mapping[str, str], name: str) -> str | None:
    raw = _get(env, name)
    if raw is None:
        return None
    parts = urlsplit(raw)
    # Do not echo the value: a malformed URL may embed credentials.
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise AiConfigError(f"{name} must be an http(s) URL with a host")
    if parts.username or parts.password:
        raise AiConfigError(f"{name} must not contain credentials; use the API key variable instead")
    if parts.query or parts.fragment:
        raise AiConfigError(f"{name} must not contain a query string or fragment")
    if parts.scheme == "http" and parts.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise AiConfigError(f"{name} must use https (plain http is allowed only for localhost)")
    return raw.rstrip("/")


def load_config(env: Mapping[str, str] | None = None) -> AiConfig:
    """Resolve the LLM configuration from `env` (default: `os.environ`)."""
    env = os.environ if env is None else env

    raw_provider = (_get(env, "AI_LLM_PROVIDER") or LLMProvider.NONE.value).lower()
    try:
        provider = LLMProvider(raw_provider)
    except ValueError:
        allowed = ", ".join(p.value for p in LLMProvider)
        raise AiConfigError(f"AI_LLM_PROVIDER must be one of {allowed}, got {raw_provider!r}") from None

    common: dict[str, Any] = {
        "provider": provider,
        "temperature": _number(env, "AI_LLM_TEMPERATURE", DEFAULT_TEMPERATURE, float, 0.0, 2.0),
        "timeout_seconds": _number(env, "AI_LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, float, 0.0,
                                   exclusive_min=True),
        "max_retries": _number(env, "AI_LLM_MAX_RETRIES", DEFAULT_MAX_RETRIES, int, 0),
    }

    if provider is LLMProvider.NONE:
        config = AiConfig(**common)
    elif provider is LLMProvider.OPENAI:
        key = _get(env, "OPENAI_API_KEY")
        model = _get(env, "AI_LLM_MODEL")
        config = AiConfig(
            **common,
            model=model,
            api_key=SecretStr(key) if key else None,
            base_url=_url(env, "OPENAI_BASE_URL"),
        )
        missing = [name for name, value in (("OPENAI_API_KEY", key), ("AI_LLM_MODEL", model)) if not value]
        config = _finalize(config, missing=missing)
    else:
        key = _get(env, "AZURE_OPENAI_API_KEY")
        endpoint = _url(env, "AZURE_OPENAI_ENDPOINT")
        deployment = _get(env, "AZURE_OPENAI_DEPLOYMENT")
        config = AiConfig(
            **common,
            api_key=SecretStr(key) if key else None,
            azure_endpoint=endpoint,
            azure_deployment=deployment,
            api_version=_get(env, "AZURE_OPENAI_API_VERSION") or DEFAULT_AZURE_API_VERSION,
        )
        missing = [name for name, value in (("AZURE_OPENAI_API_KEY", key), ("AZURE_OPENAI_ENDPOINT", endpoint),
                                            ("AZURE_OPENAI_DEPLOYMENT", deployment)) if not value]
        config = _finalize(config, missing=missing)

    log_event(logger, logging.INFO, "ai_config_resolved", "AI LLM configuration resolved", **config.summary())
    return config


def _finalize(config: AiConfig, missing: list[str]) -> AiConfig:
    if missing:
        reason = f"{config.provider.value} selected but {', '.join(missing)} not set"
        return config.model_copy(update={"enabled": False, "disabled_reason": reason})
    return config.model_copy(update={"enabled": True, "disabled_reason": None})


def create_chat_model(config: AiConfig, http_client: Any | None = None) -> tuple[Any | None, str | None]:
    """Build the LangChain chat model for `config`.

    Returns `(model, None)` on success or `(None, reason)` when the LLM is
    unavailable. Construction makes no network call; an unreachable endpoint is
    reported later by `ai_engine.llm.invoke_llm`. `http_client` (an
    `httpx.Client`) replaces the default transport, e.g. a local mock in tests.
    """
    if not config.enabled:
        return None, config.disabled_reason
    try:
        from langchain_openai import AzureChatOpenAI, ChatOpenAI
    except ImportError:
        return None, "langchain-openai is not installed (pip install '.[ai]')"

    common = {
        "api_key": config.api_key,
        "temperature": config.temperature,
        "timeout": config.timeout_seconds,
        "max_retries": config.max_retries,
    }
    if http_client is not None:
        common["http_client"] = http_client
    try:
        if config.provider is LLMProvider.AZURE_OPENAI:
            model = AzureChatOpenAI(azure_endpoint=config.azure_endpoint, azure_deployment=config.azure_deployment,
                                    api_version=config.api_version, **common)
        else:
            model = ChatOpenAI(model=config.model, base_url=config.base_url, **common)
    except Exception as exc:  # client validation failure: degrade, never leak the message
        return None, f"could not create {config.provider.value} client ({type(exc).__name__})"
    return model, None
