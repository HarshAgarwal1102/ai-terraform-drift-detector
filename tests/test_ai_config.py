"""Task 6.1: AI engine LLM configuration and LangGraph skeleton.

No test contacts a real LLM. The unreachable-endpoint test targets a closed
port on 127.0.0.1, so it needs no network access.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import logging
import pickle
import socket
from pathlib import Path

import pytest

from ai_engine.config import (
    DEFAULT_AZURE_API_VERSION,
    AiConfig,
    AiConfigError,
    LLMProvider,
    create_chat_model,
    load_config,
)
from drift_engine.classifier import evaluate

HAS_AI_EXTRA = all(importlib.util.find_spec(m) for m in ("langgraph", "langchain_openai"))
requires_ai = pytest.mark.skipif(not HAS_AI_EXTRA, reason="needs the 'ai' extra")
if HAS_AI_EXTRA:
    import langchain_openai
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from langchain_core.messages import HumanMessage

    from langgraph.graph import END, START, StateGraph

    from ai_engine.graph import (
        AZURE_CONTENT_FILTER_MESSAGE,
        AiState,
        EvidenceMutationError,
        FrozenDict,
        FrozenList,
        LLMCallResult,
        build_graph,
        freeze_evidence,
        invoke_llm,
        run_analysis,
    )

SECRET = "sk-test-NOT-A-REAL-KEY-1234567890"

OPENAI_ENV = {"AI_LLM_PROVIDER": "openai", "OPENAI_API_KEY": SECRET, "AI_LLM_MODEL": "test-model"}
AZURE_ENV = {
    "AI_LLM_PROVIDER": "azure_openai",
    "AZURE_OPENAI_API_KEY": SECRET,
    "AZURE_OPENAI_ENDPOINT": "https://example-aoai.openai.azure.com/",
    "AZURE_OPENAI_DEPLOYMENT": "drift-analysis",
}

# A real contract drift_report.json, built by drift_engine from the external_drift plan fixture
# (the graph validates it against the report contract since Task 6.2).
_EVIDENCE = Path(__file__).parent / "fixtures" / "plan_evidence" / "external_drift"
DRIFT_REPORT = evaluate(str(_EVIDENCE / "plan.sanitized.json"), str(_EVIDENCE / "detection_run.json")).report


# --------------------------------------------------------------------------- config


def test_default_is_disabled_and_opt_in():
    config = load_config({})
    assert config.provider is LLMProvider.NONE
    assert not config.enabled
    assert "opt-in" in config.disabled_reason


def test_credentials_alone_do_not_enable_llm():
    config = load_config({"OPENAI_API_KEY": SECRET, "AZURE_OPENAI_API_KEY": SECRET})
    assert config.provider is LLMProvider.NONE and not config.enabled


def test_openai_config():
    config = load_config({**OPENAI_ENV, "OPENAI_BASE_URL": "https://llm.example.com/v1/"})
    assert config.enabled and config.disabled_reason is None
    assert config.model == "test-model"
    assert config.base_url == "https://llm.example.com/v1"
    assert config.api_key.get_secret_value() == SECRET
    assert (config.temperature, config.timeout_seconds, config.max_retries) == (0.0, 60.0, 0)  # retries opt-in


def test_azure_openai_config():
    config = load_config({**AZURE_ENV, "AI_LLM_PROVIDER": " Azure_OpenAI "})
    assert config.enabled
    assert config.azure_endpoint == "https://example-aoai.openai.azure.com"
    assert config.azure_deployment == "drift-analysis"
    assert config.api_version == DEFAULT_AZURE_API_VERSION


@pytest.mark.parametrize(
    ("env", "missing"),
    [
        ({"AI_LLM_PROVIDER": "openai", "AI_LLM_MODEL": "m"}, ["OPENAI_API_KEY"]),
        ({"AI_LLM_PROVIDER": "openai", "OPENAI_API_KEY": SECRET}, ["AI_LLM_MODEL"]),
        ({**OPENAI_ENV, "OPENAI_API_KEY": "   "}, ["OPENAI_API_KEY"]),
        ({"AI_LLM_PROVIDER": "azure_openai"}, ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT"]),
        ({**AZURE_ENV, "AZURE_OPENAI_DEPLOYMENT": ""}, ["AZURE_OPENAI_DEPLOYMENT"]),
    ],
)
def test_missing_credentials_disable_gracefully(env, missing):
    config = load_config(env)
    assert not config.enabled
    for name in missing:
        assert name in config.disabled_reason
    assert create_chat_model(config) == (None, config.disabled_reason)


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({"AI_LLM_PROVIDER": "anthropic"}, "AI_LLM_PROVIDER must be one of"),
        ({"AI_LLM_TEMPERATURE": "hot"}, "AI_LLM_TEMPERATURE must be a float"),
        ({"AI_LLM_TEMPERATURE": "3"}, "AI_LLM_TEMPERATURE must be >= 0.0 and <= 2.0"),
        ({"AI_LLM_TEMPERATURE": "nan"}, "AI_LLM_TEMPERATURE must be"),
        ({"AI_LLM_TIMEOUT_SECONDS": "0"}, "AI_LLM_TIMEOUT_SECONDS must be > 0.0"),
        ({"AI_LLM_MAX_RETRIES": "-1"}, "AI_LLM_MAX_RETRIES must be >= 0"),
        ({"AI_LLM_MAX_RETRIES": "1.5"}, "AI_LLM_MAX_RETRIES must be a int"),
    ],
)
def test_malformed_values_raise(env, message):
    with pytest.raises(AiConfigError, match=message):
        load_config(env)


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("ftp://example.com", "http\\(s\\) URL"),
        ("not a url", "http\\(s\\) URL"),
        (f"https://user:{SECRET}@example.com", "must not contain credentials"),
        (f"https://example.com/v1?api-key={SECRET}", "query string"),
        ("http://example.com/v1", "must use https"),
    ],
)
def test_unsafe_endpoints_rejected_without_echoing_value(url, message):
    with pytest.raises(AiConfigError, match=message) as info:
        load_config({**OPENAI_ENV, "OPENAI_BASE_URL": url})
    assert SECRET not in str(info.value)


def test_plain_http_allowed_for_localhost():
    assert load_config({**OPENAI_ENV, "OPENAI_BASE_URL": "http://localhost:11434/v1"}).enabled


def test_numeric_overrides():
    config = load_config({**OPENAI_ENV, "AI_LLM_TEMPERATURE": "0.2", "AI_LLM_TIMEOUT_SECONDS": "15",
                          "AI_LLM_MAX_RETRIES": "3"})
    assert (config.temperature, config.timeout_seconds, config.max_retries) == (0.2, 15.0, 3)


def test_secret_never_exposed(caplog):
    caplog.set_level(logging.DEBUG, logger="ai_engine")
    for env in (OPENAI_ENV, AZURE_ENV):
        config = load_config(env)
        assert SECRET not in repr(config)
        assert SECRET not in str(config)
        assert SECRET not in str(config.summary())
        assert config.summary()["api_key_set"] is True
    records = [r for r in caplog.records if getattr(r, "event", None) == "ai_config_resolved"]
    assert len(records) == 2
    assert all(SECRET not in str(r.fields) and SECRET not in r.getMessage() for r in records)


def test_summary_reports_deployment_and_host():
    summary = load_config(AZURE_ENV).summary()
    assert summary["model"] == "drift-analysis"
    assert summary["endpoint_host"] == "example-aoai.openai.azure.com"


def test_config_is_immutable():
    config = load_config(OPENAI_ENV)
    with pytest.raises(Exception):
        config.enabled = False


def test_reads_os_environ_by_default(monkeypatch):
    for name, value in OPENAI_ENV.items():
        monkeypatch.setenv(name, value)
    assert load_config().enabled


# --------------------------------------------------------------------------- client factory

@requires_ai
def test_create_openai_client():
    model, reason = create_chat_model(load_config({**OPENAI_ENV, "AI_LLM_TIMEOUT_SECONDS": "5"}))
    assert reason is None
    assert isinstance(model, langchain_openai.ChatOpenAI)
    assert (model.model_name, model.request_timeout, model.temperature) == ("test-model", 5.0, 0.0)
    assert SECRET not in repr(model)


@requires_ai
def test_create_azure_client():
    model, reason = create_chat_model(load_config(AZURE_ENV))
    assert reason is None
    assert isinstance(model, langchain_openai.AzureChatOpenAI)
    assert model.deployment_name == "drift-analysis"
    assert model.openai_api_version == DEFAULT_AZURE_API_VERSION
    assert SECRET not in repr(model)


@requires_ai
def test_missing_client_library_degrades(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "langchain_openai":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    model, reason = create_chat_model(load_config(OPENAI_ENV))
    assert model is None and "langchain-openai is not installed" in reason


# --------------------------------------------------------------------------- graph

@requires_ai
def test_ai_state_schema():
    assert set(AiState.__annotations__) == {"drift_report", "parsed_drift", "security_targets", "llm",
                                            "inferences", "warnings"}
    assert AiState.__total__ is False


@requires_ai
def test_graph_without_llm_falls_back_to_deterministic():
    report = copy.deepcopy(DRIFT_REPORT)
    state = run_analysis(report, config=load_config({}))
    assert state["drift_report"] == DRIFT_REPORT
    assert report == DRIFT_REPORT  # evidence untouched
    assert state["llm"] == {"available": False, "provider": "none", "model": None,
                            "reason": "AI_LLM_PROVIDER is not set (LLM analysis is opt-in)"}
    # Task 6.3: the only AI node records why it did not run; nothing else enters `inferences`.
    assert set(state["inferences"]) == {"analyze_security"}
    assert state["inferences"]["analyze_security"]["status"] == "skipped"
    assert len(state["warnings"]) == 1 and "deterministic evidence" in state["warnings"][0]


@requires_ai
def test_graph_with_missing_key_does_not_raise():
    state = run_analysis(DRIFT_REPORT, config=load_config({"AI_LLM_PROVIDER": "openai", "AI_LLM_MODEL": "m"}))
    assert state["llm"]["available"] is False
    assert "OPENAI_API_KEY" in state["llm"]["reason"]


@requires_ai
def test_graph_with_configured_llm():
    state = run_analysis(DRIFT_REPORT, config=load_config(OPENAI_ENV))
    assert state["llm"] == {"available": True, "provider": "openai", "model": "test-model", "reason": None}
    assert "warnings" not in state or state["warnings"] == []
    assert SECRET not in str(state)


@requires_ai
def test_graph_with_injected_llm():
    state = run_analysis(DRIFT_REPORT, llm=FakeListChatModel(responses=["ok"]))
    assert state["llm"]["available"] is True and state["llm"]["provider"] == "custom"


@requires_ai
def test_graph_rejects_missing_report():
    with pytest.raises(ValueError, match="drift_report"):
        build_graph(config=load_config({})).invoke({})


@requires_ai
def test_invoke_llm_success():
    result = invoke_llm(FakeListChatModel(responses=["analysis"]), [HumanMessage("hi")])
    assert result == LLMCallResult(content="analysis") and result.ok


@requires_ai
def test_invoke_llm_without_model():
    result = invoke_llm(None, [HumanMessage("hi")])
    assert not result.ok and result.content is None


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@requires_ai
def test_invoke_llm_unreachable_endpoint_degrades():
    env = {**OPENAI_ENV, "OPENAI_BASE_URL": f"http://127.0.0.1:{_closed_port()}/v1",
           "AI_LLM_TIMEOUT_SECONDS": "5", "AI_LLM_MAX_RETRIES": "0"}
    model, _ = create_chat_model(load_config(env))
    result = invoke_llm(model, [HumanMessage("hi")])
    assert not result.ok
    assert result.error.startswith("LLM call failed (") and "ConnectionError" in result.error
    assert SECRET not in result.error


@requires_ai
def test_invoke_llm_does_not_hide_programming_errors():
    class Broken:
        def invoke(self, messages):
            raise KeyError("bug")

    with pytest.raises(KeyError):
        invoke_llm(Broken(), [HumanMessage("hi")])


@requires_ai
def test_invoke_llm_programming_value_errors_still_raise():
    class Broken:
        def __init__(self, exc):
            self.exc = exc

        def invoke(self, messages):
            raise self.exc

    class OtherValueError(ValueError):
        pass

    for exc in (ValueError("bug"), ValueError(AZURE_CONTENT_FILTER_MESSAGE + "!"),
                OtherValueError(AZURE_CONTENT_FILTER_MESSAGE)):
        with pytest.raises(ValueError):
            invoke_llm(Broken(exc), [HumanMessage("hi")])


@requires_ai
def test_invoke_llm_azure_content_filter_degrades():
    """Regression: a real AzureChatOpenAI response with finish_reason=content_filter."""
    import httpx

    def handler(request):
        return httpx.Response(200, json={
            "id": "chatcmpl-1", "object": "chat.completion", "created": 0, "model": "gpt",
            "choices": [{"index": 0, "finish_reason": "content_filter",
                         "message": {"role": "assistant", "content": ""}}],
        })

    model = langchain_openai.AzureChatOpenAI(
        azure_endpoint="https://example-aoai.openai.azure.com", azure_deployment="drift-analysis",
        api_version=DEFAULT_AZURE_API_VERSION, api_key=SECRET, max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = invoke_llm(model, [HumanMessage("hi")])
    assert result == LLMCallResult(error="LLM response blocked by content filter")


# --------------------------------------------------------------------------- evidence immutability

def _graph_with_node(node):
    graph = StateGraph(AiState)
    graph.add_node("node", node)
    graph.add_edge(START, "node")
    graph.add_edge("node", END)
    return graph.compile()


@requires_ai
def test_graph_input_is_deep_copied():
    report = copy.deepcopy(DRIFT_REPORT)
    state = run_analysis(report, config=load_config({}))
    report["resources"][0]["attribute_changes"].append({"path": ["tags", "injected"]})
    report["summary"]["drifted_resources"] = 99
    assert state["drift_report"] == DRIFT_REPORT
    assert state["drift_report"]["resources"] is not report["resources"]
    assert isinstance(state["drift_report"], FrozenDict)
    assert isinstance(state["drift_report"]["resources"], FrozenList)


@requires_ai
@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r["resources"][0]["attribute_changes"].append({"path": ["tags", "invented"]}),
        lambda r: r["resources"].pop(),
        lambda r: r["resources"][0].update({"address": "invented"}),
        lambda r: r["summary"].__setitem__("drifted_resources", 99),
        lambda r: r.pop("summary"),
    ],
    ids=["nested-append", "list-pop", "nested-update", "nested-setitem", "top-pop"],
)
def test_node_cannot_mutate_evidence_in_place(mutate):
    report = copy.deepcopy(DRIFT_REPORT)

    def node(state):
        mutate(state["drift_report"])
        return {}

    with pytest.raises(EvidenceMutationError):
        _graph_with_node(node).invoke({"drift_report": report})
    assert report == DRIFT_REPORT


@requires_ai
@pytest.mark.parametrize("replacement", [lambda r: {"resources": []}, lambda r: r], ids=["new-value", "same-value"])
def test_node_cannot_replace_evidence(replacement):
    def node(state):
        return {"drift_report": replacement(state["drift_report"])}

    with pytest.raises(EvidenceMutationError, match="nodes must not write it"):
        _graph_with_node(node).invoke({"drift_report": DRIFT_REPORT})


@requires_ai
def test_ai_output_stays_separate_from_evidence():
    def node(state):
        return {"inferences": {"node": {"summary": "inferred"}}}

    state = _graph_with_node(node).invoke({"drift_report": DRIFT_REPORT})
    assert state["inferences"] == {"node": {"summary": "inferred"}}
    assert state["drift_report"] == DRIFT_REPORT


@requires_ai
@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.__setitem__("k", 1), lambda d: d.__delitem__("a"), lambda d: d.clear(),
        lambda d: d.pop("a"), lambda d: d.popitem(), lambda d: d.setdefault("k", 1),
        lambda d: d.update(k=1), lambda d: d.__ior__({"k": 1}),
        lambda d: d["l"].__setitem__(0, 9), lambda d: d["l"].__delitem__(0), lambda d: d["l"].append(9),
        lambda d: d["l"].extend([9]), lambda d: d["l"].insert(0, 9), lambda d: d["l"].pop(),
        lambda d: d["l"].remove(1), lambda d: d["l"].clear(), lambda d: d["l"].sort(),
        lambda d: d["l"].reverse(), lambda d: d["l"].__iadd__([9]), lambda d: d["l"].__imul__(2),
    ],
)
def test_every_mutating_method_is_blocked(mutate):
    frozen = freeze_evidence({"a": 1, "l": [2, 1]})
    with pytest.raises(EvidenceMutationError):
        mutate(frozen)
    assert frozen == {"a": 1, "l": [2, 1]}


@requires_ai
def test_frozen_evidence_copies_and_serializes():
    frozen = freeze_evidence({"a": [1, {"b": None}], "c": (True, 1.5)})
    assert copy.deepcopy(frozen) is frozen and copy.copy(frozen) is frozen
    assert json.loads(json.dumps(frozen)) == {"a": [1, {"b": None}], "c": [True, 1.5]}
    restored = pickle.loads(pickle.dumps(frozen))
    assert restored == frozen and isinstance(restored["a"][1], FrozenDict)


@requires_ai
@pytest.mark.parametrize("value", [{"a": {1, 2}}, {1: "a"}, {"a": object()}])
def test_non_json_evidence_rejected(value):
    with pytest.raises(TypeError):
        freeze_evidence(value)


@requires_ai
def test_frozen_real_report_validates_against_drift_engine_model():
    from drift_engine.models import DriftReport

    state = run_analysis(copy.deepcopy(DRIFT_REPORT), config=load_config({}))
    assert DriftReport.model_validate(state["drift_report"]).outcome == "succeeded"
    assert json.loads(json.dumps(state["drift_report"])) == DRIFT_REPORT
