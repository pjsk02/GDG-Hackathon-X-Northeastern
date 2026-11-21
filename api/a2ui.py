"""AgentAnswer -> A2UI v1.0 messages (https://a2ui.org/specification/v1.0-a2ui/).

The UI is built *here, in code*, from the already-grounded answer. The model never writes UI,
so nothing it says reaches the screen without passing agent.grounding first.

Each answer becomes its own surface, so re-asking with another provider (Gemma 4 vs Gemini)
stacks a second card under the first for side-by-side comparison.

Renderer -> agent actions handled by api.main /a2ui/agent:
    reask        {question, provider}   ask again with a specific provider
    show_source  {chunk_id}             open the full chunk a finding cites
"""

import re
import uuid
from typing import Any

from shared.contracts import AgentAnswer, Chunk

VERSION = "1.0"
BASIC_CATALOG = "https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json"
PROVIDER_LABELS = {"extractive": "Extractive", "ollama": "Gemma 4", "gemini": "Gemini"}

Message = dict[str, Any]
Component = dict[str, Any]


def _surface_id(prefix: str) -> str:
    # Must be unique for the renderer's lifetime; ids follow UAX #31 (letters, digits, _).
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~])")


def md_escape(text: str) -> str:
    """Make arbitrary text render literally: the web renderer treats Text as Markdown."""
    return _MD_SPECIAL.sub(r"\\\1", text)


def md_code_block(text: str) -> str:
    """Fence text verbatim; the fence is longer than any backtick run inside it."""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}\n{text}\n{fence}"


def _text(cid: str, text: str, caption: bool = False, raw: bool = False) -> Component:
    """Text component. The Lit Basic Catalog renders body Text as Markdown and captions as
    plain text, so only body text is escaped (unless `raw`: Markdown we built ourselves)."""
    c: Component = {"id": cid, "component": "Text", "text": text if raw or caption else md_escape(text)}
    if caption:
        c["variant"] = "caption"
    return c


def _button(cid: str, label: str, name: str, context: dict[str, Any], primary: bool = False) -> list[Component]:
    btn: Component = {
        "id": cid,
        "component": "Button",
        "child": f"{cid}_label",
        "action": {"event": {"name": name, "context": context}},
    }
    if primary:
        btn["variant"] = "primary"
    return [btn, _text(f"{cid}_label", label)]


def _surface(surface_id: str, components: list[Component]) -> list[Message]:
    return [
        {"version": VERSION, "createSurface": {"surfaceId": surface_id, "catalogId": BASIC_CATALOG}},
        {"version": VERSION, "updateComponents": {"surfaceId": surface_id, "components": components}},
    ]


def _meta_line(ans: AgentAnswer) -> str:
    parts = [f"{ans.model} via {ans.provider}", f"{ans.latency_ms / 1000:.1f} s"]
    if ans.fell_back:
        failed = [a.provider for a in ans.attempts if not a.ok]
        parts.append(f"fell back from {', '.join(failed)}")
    return " · ".join(parts)


def answer_messages(ans: AgentAnswer, providers: list[str]) -> list[Message]:
    """One surface per answer: question, verified findings as cards, rejections, re-ask buttons."""
    components: list[Component] = []
    body: list[str] = ["question", "meta"]
    components += [_text("question", ans.question), _text("meta", _meta_line(ans), caption=True)]

    if ans.error:
        body.append("error")
        components.append(_text("error", f"Every provider failed: {ans.error}"))
    elif ans.abstained:
        body.append("abstain_card")
        components += [
            {"id": "abstain_card", "component": "Card", "child": "abstain_text"},
            _text("abstain_text", "Not in the indexed data, so no answer. Nothing was made up."),
        ]

    for i, f in enumerate(ans.findings):
        p = f"finding_{i}"
        body.append(f"{p}_card")
        components += [
            {"id": f"{p}_card", "component": "Card", "child": f"{p}_col"},
            # Quote first: it is the verified evidence. The claim is the model's summary of it.
            {"id": f"{p}_col", "component": "Column",
             "children": [f"{p}_quote", f"{p}_cite", f"{p}_claim", f"{p}_open"]},
            _text(f"{p}_quote", f"“{f.evidence_quote}”"),
            _text(f"{p}_cite", f"{f.evidence_source} · {f.line_or_timestamp} · "
                               f"confidence {f.confidence_score:.0%}", caption=True),
            _text(f"{p}_claim", f"Agent summary: {f.claim}", caption=True),
            *_button(f"{p}_open", "Show source", "show_source", {"chunk_id": f.chunk_id}),
        ]

    if ans.rejected:
        body.append("rejected")
        n = len(ans.rejected)
        reasons = "; ".join(r.reason for r in ans.rejected[:3])
        components.append(_text("rejected", f"{n} claim{'s' * (n != 1)} rejected by grounding: {reasons}",
                                caption=True))

    others = [p for p in providers if p != ans.provider]
    if others:
        body.append("reask_row")
        row: list[str] = []
        for p in others:
            cid = f"reask_{p}"
            row.append(cid)
            components += _button(cid, f"Ask {PROVIDER_LABELS.get(p, p)}", "reask",
                                  {"question": ans.question, "provider": p}, primary=p == "gemini")
        components.append({"id": "reask_row", "component": "Row", "children": row})

    components.insert(0, {"id": "body", "component": "Column", "children": body})
    components.insert(0, {"id": "root", "component": "Card", "child": "body"})
    return _surface(_surface_id("answer"), components)


def source_messages(chunk: Chunk | None, chunk_id: str) -> list[Message]:
    """A small surface showing the full chunk a finding cited."""
    if chunk is None:
        comps = [{"id": "root", "component": "Card", "child": "missing"},
                 _text("missing", f"Chunk {chunk_id} is no longer in the index (re-indexed?).")]
    else:
        comps = [
            {"id": "root", "component": "Card", "child": "col"},
            {"id": "col", "component": "Column", "children": ["where", "divider", "text"]},
            _text("where", f"{chunk.source} · {chunk.locator}", caption=True),
            {"id": "divider", "component": "Divider"},
            _text("text", md_code_block(chunk.text), raw=True),
        ]
    return _surface(_surface_id("source"), comps)


def notice_messages(text: str) -> list[Message]:
    return _surface(_surface_id("notice"), [_text("root", text)])
