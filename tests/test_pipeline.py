"""Offline tests: hash embedder + extractive provider, no network or models needed."""

from pathlib import Path

import pytest

from agent.grounding import ground
from agent.pipeline import Agent
from memory import ingest_code, ingest_docs, ingest_media
from memory.chunking import chunk_lines, parse_subtitles
from memory.embedder import HashEmbedder
from memory.store import VectorStore
from shared.contracts import DraftAnswer, DraftFinding
from shared.settings import Settings

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


@pytest.fixture
def agent(tmp_path) -> Agent:
    settings = Settings(_env_file=None, llm_provider="extractive", embed_provider="hash",
                        memory_path=tmp_path / "mem.sqlite")
    store = VectorStore(settings.memory_path, HashEmbedder())
    store.add(ingest_docs.to_chunks(SAMPLES / "docs/street_services.md", "street_services.md"))
    store.add(ingest_code.to_chunks(SAMPLES / "code/permits.py", "permits.py"))
    store.add(ingest_media.to_chunks(SAMPLES / "media/council_meeting.srt", "council_meeting.srt"))
    return Agent(settings=settings, store=store)


def test_answers_with_grounded_citation(agent):
    ans = agent.ask("How quickly are reported potholes repaired?")
    assert not ans.abstained
    top = ans.findings[0]
    assert top.evidence_source == "street_services.md"
    assert "two business days" in top.evidence_quote
    assert top.line_or_timestamp == "L8"


def test_media_citation_has_timestamp(agent):
    ans = agent.ask("When will the Main Street bike lane pilot be reviewed?")
    assert ans.findings[0].evidence_source == "council_meeting.srt"
    assert ans.findings[0].line_or_timestamp.startswith("00:00:")


def test_abstains_when_unrelated(agent):
    assert agent.ask("Give me a recipe for chocolate chip cookies.").abstained


def test_grounding_rejects_fabrications(agent):
    retrieved = agent.store.search("pothole", 3)
    cid = retrieved[0].chunk.id
    draft = DraftAnswer(findings=[
        DraftFinding(claim="ok", chunk_id=cid, evidence_quote=retrieved[0].chunk.text.splitlines()[0],
                     confidence_score=0.9),
        DraftFinding(claim="fake chunk", chunk_id="nope", evidence_quote="anything at all", confidence_score=0.9),
        DraftFinding(claim="fake quote", chunk_id=cid, evidence_quote="potholes are fixed by robots",
                     confidence_score=0.9),
        DraftFinding(claim="unsure", chunk_id=cid, evidence_quote=retrieved[0].chunk.text.splitlines()[0],
                     confidence_score=0.2),
    ])
    findings, rejected = ground(draft, retrieved, min_confidence=0.5)
    assert [f.claim for f in findings] == ["ok"]
    assert len(rejected) == 3


def test_chunk_lines_locators():
    chunks = chunk_lines("\n".join(f"line {i}" for i in range(1, 101)), "x.py", "code", max_lines=60, overlap=10)
    assert [c.locator for c in chunks] == ["L1-L60", "L51-L100"]


def test_parse_vtt():
    cues = parse_subtitles("WEBVTT\n\n00:01.000 --> 00:03.500\n<v Bob>Hello there\n")
    assert cues[0].start == 1.0 and cues[0].end == 3.5 and cues[0].text == "Hello there"
