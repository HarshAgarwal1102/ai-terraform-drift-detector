"""LangGraph state and graph for the AI analysis engine (Tasks 6.1-6.3).

`AiState` keeps deterministic evidence and model output apart:

- `drift_report` is the contract `drift_report.json` produced by drift_engine.
  It is evidence and is enforced read-only: the graph input is deep-copied into
  `FrozenDict` / `FrozenList` containers whose mutating methods raise
  `EvidenceMutationError`, and the channel's reducer rejects any write after
  the initial input, so no node can modify or replace it.
- `parsed_drift` is deterministic data derived from `drift_report` by the
  `parse_drift` node (Task 6.2): the contract's non-in_sync resources and a
  value-free summary per resource. It is protected the same way: written once
  (by `parse_drift`), then frozen.
- `security_targets` is the deterministic security routing of `classify_drift`
  (Task 6.3): which changes go to security analysis and why. Write-once, frozen.
- `inferences` holds model-generated interpretation keyed by the node that
  produced it. Nothing in it is evidence.
- `llm` records whether an LLM was usable for this run, and why not.
- `warnings` collects non-fatal problems such as an unreachable endpoint.

The graph runs START -> `initialize` -> `parse_drift` -> `classify_drift` ->
`analyze_security` -> END. All but `analyze_security` are deterministic; it is
the first LLM-backed node and writes only to `inferences`. Tasks 6.4-6.6 add
the remaining analysis nodes. Every LLM call goes through `invoke_llm`,
which turns a missing, unreachable or failing LLM into a result object instead
of an exception, so the graph always completes with deterministic data.
"""

from __future__ import annotations

import logging
import operator
from collections.abc import Mapping
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from ai_engine.config import AiConfig, create_chat_model, load_config
from ai_engine.llm import AZURE_CONTENT_FILTER_MESSAGE, LLMCallResult, invoke_llm  # noqa: F401 (re-exported)
from ai_engine.evidence import EvidenceLimits
from ai_engine.nodes.parse_drift import ParsedDrift, parse_drift
from ai_engine.nodes.security_analysis import classify_drift, make_analyze_security
from drift_engine.logs import log_event

logger = logging.getLogger(__name__)


class EvidenceMutationError(TypeError):
    """Raised on any attempt to modify or replace `AiState.drift_report`."""


def _reject_mutation(self: Any, *args: Any, **kwargs: Any) -> None:
    raise EvidenceMutationError("deterministic evidence is immutable")


class FrozenDict(dict):
    """Read-only dict. Still a `dict`, so `json.dumps` and `isinstance` checks work."""

    __slots__ = ()
    __setitem__ = __delitem__ = __ior__ = _reject_mutation
    clear = pop = popitem = setdefault = update = _reject_mutation

    def __copy__(self) -> FrozenDict:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> FrozenDict:
        return self

    def __reduce__(self) -> tuple[Any, ...]:
        return (type(self), (dict(self),))


class FrozenList(list):
    """Read-only list. Still a `list`, so `json.dumps` and `isinstance` checks work."""

    __slots__ = ()
    __setitem__ = __delitem__ = __iadd__ = __imul__ = _reject_mutation
    append = extend = insert = pop = remove = clear = sort = reverse = _reject_mutation

    def __copy__(self) -> FrozenList:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> FrozenList:
        return self

    def __reduce__(self) -> tuple[Any, ...]:
        return (type(self), (list(self),))


def freeze_evidence(value: Any) -> Any:
    """Deep-copy parsed JSON into read-only containers; reject non-JSON values."""
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("evidence object keys must be strings")
        return FrozenDict((key, freeze_evidence(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return FrozenList(freeze_evidence(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"evidence must contain only JSON values, found {type(value).__name__}")


def _write_once(field: str):
    """Reducer factory: accept the first write to `field`, freeze it, reject every later write.

    LangGraph seeds the channel with an empty plain dict, so the first call
    sees a non-frozen `current`.
    """

    def reducer(current: Any, update: Any) -> FrozenDict:
        if isinstance(current, FrozenDict):
            raise EvidenceMutationError(f"{field} is immutable deterministic evidence; nodes must not write it")
        if not isinstance(update, Mapping):
            raise TypeError(f"{field} must be a JSON object")
        return freeze_evidence(update)

    reducer.__name__ = reducer.__qualname__ = f"write_once_{field}"
    return reducer


write_once_evidence = _write_once("drift_report")
write_once_parsed_drift = _write_once("parsed_drift")
write_once_security_targets = _write_once("security_targets")


def merge_dicts(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    """Reducer for `inferences`: each node adds its own key."""
    return {**(left or {}), **(right or {})}


class LlmStatus(TypedDict):
    available: bool
    provider: str
    model: str | None
    reason: str | None


class AiState(TypedDict, total=False):
    drift_report: Annotated[dict[str, Any], write_once_evidence]
    parsed_drift: Annotated[ParsedDrift, write_once_parsed_drift]
    security_targets: Annotated[dict[str, Any], write_once_security_targets]
    llm: LlmStatus
    inferences: Annotated[dict[str, Any], merge_dicts]
    warnings: Annotated[list[str], operator.add]


def build_graph(config: AiConfig | None = None, llm: Any | None = None, limits: EvidenceLimits = EvidenceLimits()):
    """Compile the analysis graph.

    `llm` overrides the client built from `config` (tests inject a fake model).
    The client is bound to the nodes, not stored in state, so state stays plain
    serializable data.
    """
    if llm is None:
        config = config or load_config()
        llm, reason = create_chat_model(config)
    else:
        reason = None
    summary = config.summary() if config else {"provider": "custom", "model": None}
    status = LlmStatus(
        available=llm is not None,
        provider=summary["provider"],
        model=summary["model"],
        reason=None if llm is not None else reason,
    )

    def initialize(state: AiState) -> dict[str, Any]:
        report = state.get("drift_report")
        # An unset channel reads as LangGraph's empty plain-dict seed, never a FrozenDict.
        if not isinstance(report, FrozenDict) or not report:
            raise ValueError("AiState.drift_report must be the parsed drift_report.json object")
        update: dict[str, Any] = {"llm": status, "inferences": {}}
        if not status["available"]:
            update["warnings"] = [f"AI analysis limited to deterministic evidence: {status['reason']}"]
        log_event(logger, logging.INFO, "ai_graph_initialized", "AI analysis graph initialized",
                  llm_available=status["available"], provider=status["provider"])
        return update

    graph = StateGraph(AiState)
    graph.add_node("initialize", initialize)
    graph.add_node("parse_drift", parse_drift)
    graph.add_node("classify_drift", classify_drift)
    graph.add_node("analyze_security", make_analyze_security(llm, limits))
    graph.add_edge(START, "initialize")
    graph.add_edge("initialize", "parse_drift")
    graph.add_edge("parse_drift", "classify_drift")
    graph.add_edge("classify_drift", "analyze_security")
    graph.add_edge("analyze_security", END)
    return graph.compile()


def run_analysis(drift_report: Mapping[str, Any], config: AiConfig | None = None, llm: Any | None = None,
                 limits: EvidenceLimits = EvidenceLimits()) -> AiState:
    """Run the graph over a parsed `drift_report.json` and return the final state.

    The caller's object is never shared with the graph: the `drift_report`
    reducer deep-copies it into read-only containers on input.
    """
    return build_graph(config=config, llm=llm, limits=limits).invoke({"drift_report": drift_report})
