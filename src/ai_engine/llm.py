"""LLM call wrapper shared by the AI analysis nodes (Tasks 6.1, 6.3).

Every LLM call goes through `invoke_llm`, which turns a missing, unreachable or
failing LLM into an `LLMCallResult` instead of an exception, so the graph always
completes with deterministic data. Genuine programming errors still raise.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from drift_engine.logs import log_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMCallResult:
    """Outcome of one LLM call. Exactly one of `content` / `error` is set."""

    content: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


# AzureChatOpenAI raises a plain ValueError with exactly this message when Azure's
# content filter blocks a *response* (langchain_openai/chat_models/azure.py,
# _create_chat_result). A blocked *prompt* arrives as HTTP 400 (openai.BadRequestError).
AZURE_CONTENT_FILTER_MESSAGE = "Azure has not provided the response due to a content filter being triggered"


def _is_content_filter_block(exc: ValueError) -> bool:
    # Exact type and message only: any other ValueError is treated as a bug and re-raised.
    return type(exc) is ValueError and str(exc) == AZURE_CONTENT_FILTER_MESSAGE


def _recoverable_errors() -> tuple[type[BaseException], ...]:
    errors: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError)
    try:
        import openai
    except ImportError:
        return errors
    return errors + (openai.OpenAIError,)


def invoke_llm(llm: Any | None, messages: Sequence[Any]) -> LLMCallResult:
    """Call `llm` with `messages`, degrading instead of raising when it fails.

    Only the exception type is reported: provider error messages can echo
    request details, so they are not copied into state or logs.
    """
    if llm is None:
        return LLMCallResult(error="LLM unavailable")
    try:
        response = llm.invoke(list(messages))
    except _recoverable_errors() as exc:
        log_event(logger, logging.WARNING, "llm_call_failed", "LLM call failed", error_type=type(exc).__name__)
        return LLMCallResult(error=f"LLM call failed ({type(exc).__name__})")
    except ValueError as exc:
        if not _is_content_filter_block(exc):
            raise
        log_event(logger, logging.WARNING, "llm_call_failed", "LLM response blocked by content filter",
                  error_type="content_filter")
        return LLMCallResult(error="LLM response blocked by content filter")
    content = getattr(response, "content", response)
    return LLMCallResult(content=content if isinstance(content, str) else str(content))
