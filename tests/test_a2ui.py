"""A2UI output must validate against the official v1.0 schemas (vendored in tests/a2ui_v1_0)."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

import api.main as api_main
from api import a2ui
from tests.test_pipeline import agent  # noqa: F401  (offline fixture: hash embedder + extractive)

SCHEMAS = Path(__file__).parent / "a2ui_v1_0"
BASE = "https://a2ui.org/specification/v1_0/"


def _load(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    common, catalog = _load("common_types.json"), _load("basic_catalog.json")
    # Relative refs: agent_to_renderer -> "catalog.json" / "common_types.json" (resolved against
    # v1_0/), and basic_catalog -> "common_types.json" (resolved against catalogs/basic/).
    registry = Registry().with_resources([
        (BASE + "common_types.json", Resource.from_contents(common)),
        (BASE + "catalogs/basic/common_types.json", Resource.from_contents(common)),
        (BASE + "catalog.json", Resource.from_contents(catalog)),
        (a2ui.BASIC_CATALOG, Resource.from_contents(catalog)),
    ])
    return Draft202012Validator(_load("agent_to_renderer.json"), registry=registry)


def visible(messages: list[dict]) -> str:
    """All Text as the user sees it (Markdown escapes removed)."""
    texts = [c["text"] for m in messages if "updateComponents" in m
             for c in m["updateComponents"]["components"] if c.get("component") == "Text"]
    return re.sub(r"\\(.)", r"\1", "\n".join(texts))


def assert_valid(messages: list[dict], validator: Draft202012Validator) -> None:
    assert messages, "no messages"
    for m in messages:
        errors = sorted(validator.iter_errors(m), key=lambda e: e.path)
        assert not errors, "\n".join(f"{list(e.path)}: {e.message[:300]}" for e in errors)
    comps = [c for m in messages if "updateComponents" in m for c in m["updateComponents"]["components"]]
    ids = [c["id"] for c in comps]
    assert ids.count("root") == 1 and len(ids) == len(set(ids)), "need exactly one root and unique ids"
    refs = {r for c in comps for r in ([c["child"]] if "child" in c else []) + list(c.get("children", []))}
    assert refs <= set(ids), f"dangling child refs: {refs - set(ids)}"


@pytest.fixture
def client(agent, monkeypatch):  # noqa: F811
    monkeypatch.setattr(api_main, "get_agent", lambda: agent)
    return TestClient(api_main.app)


def test_answer_surface_is_valid_and_grounded(agent, validator):  # noqa: F811
    ans = agent.ask("How quickly are reported potholes repaired?")
    msgs = a2ui.answer_messages(ans, api_main.PROVIDERS)
    assert_valid(msgs, validator)
    shown = visible(msgs)
    assert "two business days" in shown and "street_services.md · L8" in shown


def test_abstain_surface_is_valid(agent, validator):  # noqa: F811
    ans = agent.ask("What is the capital of France?")
    assert ans.abstained
    msgs = a2ui.answer_messages(ans, api_main.PROVIDERS)
    assert_valid(msgs, validator)
    assert "Not in the indexed data" in visible(msgs)


def test_surface_ids_are_unique():
    assert len({a2ui.notice_messages("x")[0]["createSurface"]["surfaceId"] for _ in range(50)}) == 50


def test_prompt_then_show_source_action(client, validator):
    msgs = client.post("/a2ui/agent", json={"prompt": "How quickly are reported potholes repaired?"}).json()
    assert_valid(msgs, validator)
    btn = next(c for c in msgs[1]["updateComponents"]["components"] if c.get("component") == "Button"
               and c["action"]["event"]["name"] == "show_source")
    action = {"name": "show_source", "surfaceId": msgs[0]["createSurface"]["surfaceId"],
              "sourceComponentId": btn["id"], "timestamp": "2026-11-17T12:00:00Z",
              "context": btn["action"]["event"]["context"]}
    src = client.post("/a2ui/agent", json={"message": {"version": "1.0", "action": action}}).json()
    assert_valid(src, validator)
    assert "two business days" in visible(src) and src[1]["updateComponents"]["components"][-1]["text"].startswith("```")


def test_reask_action_and_bad_requests(client, validator):
    action = {"name": "reask", "surfaceId": "s", "sourceComponentId": "b", "timestamp": "2026-11-17T12:00:00Z",
              "context": {"question": "How do I report a pothole?", "provider": "extractive"}}
    assert_valid(client.post("/a2ui/agent", json={"message": {"version": "1.0", "action": action}}).json(), validator)
    assert client.post("/a2ui/agent", json={}).status_code == 422
    assert client.post("/a2ui/agent", json={"prompt": "  "}).status_code == 422
    assert client.get("/a2ui").status_code == 200


def test_model_text_cannot_inject_markup():
    raw = "<img src=x onerror=alert(1)> **bold** [link](http://evil)"
    escaped = a2ui.md_escape(raw)
    assert "<" not in escaped.replace("\\<", "") and "](" not in escaped
    assert re.sub(r"\\(.)", r"\1", escaped) == raw
    assert a2ui.md_code_block("a ``` b").startswith("````")
