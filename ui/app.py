"""Demo UI: raw evidence vs. cited finding vs. confidence, side by side.

Run: make ui   (needs: pip install -e ".[ui]")
"""

import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `streamlit run ui/app.py` finds packages

import streamlit as st

from agent.pipeline import Agent
from api.a2ui import md_escape

st.set_page_config(page_title="Grounded Agent", layout="wide")


@st.cache_resource(show_spinner="Loading models...")
def get_agent() -> Agent:
    agent = Agent()
    if agent.settings.warm_up:
        agent.warm_up()  # once per server process; failures just mean a slower first answer
    return agent


def highlight(text: str, quote: str) -> str:
    """Escape the chunk and wrap the cited quote in <mark>, tolerant of whitespace differences."""
    escaped = html.escape(text)
    words = [re.escape(html.escape(w)) for w in quote.split()]
    if not words:
        return escaped
    pattern = re.compile(r"\s+".join(words), re.IGNORECASE)
    return pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", escaped, count=1)


agent = get_agent()

with st.sidebar:
    st.header("Settings")
    providers = ["extractive", "ollama", "gemini"]
    provider = st.selectbox("Provider", providers, index=providers.index(agent.settings.llm_provider))
    fallback = st.checkbox("Fall back if provider fails", value=True,
                           help=f"Then: {' -> '.join(agent.provider_chain(provider)[1:]) or 'nothing'}")
    k = st.slider("Chunks retrieved", 1, 20, agent.settings.top_k)
    if cooling := agent.cooling_down():
        st.caption("Skipping (recent failure): " + ", ".join(f"{p} {s:.0f}s" for p, s in cooling.items()))
    st.caption(f"Index: {agent.store.count()} chunks · {agent.store.embedder.name}")
    with st.expander("Indexed sources"):
        for s in agent.store.sources():
            st.text(s)

st.title("Grounded Agent")
question = st.text_input("Ask a question about the indexed data")

if question:
    with st.spinner("Retrieving and verifying..."):
        ans = agent.ask(question, k=k, provider=provider, fallback=fallback)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Verified findings", len(ans.findings))
    c2.metric("Rejected (ungrounded)", len(ans.rejected))
    c3.metric("Latency", f"{ans.latency_ms:.0f} ms")
    c4.metric("Answered by", ans.provider, help=ans.model)
    if ans.fell_back:
        failed = [a for a in ans.attempts if not a.ok]
        st.info(f"{provider} unavailable, answered by **{ans.provider}** instead. "
                + "; ".join(f"{a.provider}: {a.error}" for a in failed))
    if ans.error:
        st.error(f"Every provider failed: {ans.error}")
    if ans.abstained:
        st.warning("No grounded answer found in the indexed data. The agent abstained instead of guessing.")

    chunks = {r.chunk.id: r.chunk for r in ans.retrieved}
    for i, f in enumerate(ans.findings, 1):
        st.divider()
        raw, finding, conf = st.columns([5, 4, 2])
        chunk = chunks[f.chunk_id]
        with raw:
            st.caption(f"Raw input · {chunk.source} · {chunk.locator}")
            st.markdown(
                f"<div style='white-space:pre-wrap;font-family:monospace;font-size:0.85em'>"
                f"{highlight(chunk.text, f.evidence_quote)}</div>",
                unsafe_allow_html=True,
            )
        with finding:
            # Quote first: it is the verified evidence. The claim is the model's summary of it.
            st.caption(f"Verified quote {i}")
            st.markdown(f"> **{md_escape(f.evidence_quote)}**")
            st.code(f"{f.evidence_source} @ {f.line_or_timestamp}", language=None)
            st.caption("Agent summary")
            st.markdown(md_escape(f.claim))
        with conf:
            st.caption("Confidence")
            st.metric("score", f"{f.confidence_score:.2f}", label_visibility="collapsed")
            st.progress(min(max(f.confidence_score, 0.0), 1.0))

    if ans.rejected:
        with st.expander(f"Caught {len(ans.rejected)} ungrounded claim(s)"):
            for r in ans.rejected:
                # Rejected claims are untrusted model text: escape so links/images can't render.
                st.markdown(f"- ~~{md_escape(r.finding.claim)}~~  \n  _{md_escape(r.reason)}_")

    with st.expander("Raw JSON"):
        st.json(ans.model_dump(mode="json"))
