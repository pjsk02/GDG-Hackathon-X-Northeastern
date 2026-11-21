"""eval/crosslingual_check.py on a tiny index with a fake 'multilingual' embedder (offline)."""

import numpy as np
import pandas as pd

from eval.crosslingual_check import build_index, crosslingual_stats
from memory.embedder import HashEmbedder
from memory.store import VectorStore

# Each concept has an English and a German word, so the fake embedder matches across languages.
CONCEPTS = {"vpn": 0, "rechnung": 1, "invoice": 1, "drucker": 2, "printer": 2}


class ConceptEmbedder:
    name = "concept-3"

    def embed(self, texts, *, is_query=False):
        out = np.zeros((len(texts), 3), dtype=np.float32)
        for i, t in enumerate(texts):
            for word, dim in CONCEPTS.items():
                if word in t.lower():
                    out[i, dim] += 1.0
        out[out.sum(axis=1) == 0, 2] = 1.0
        return out / np.linalg.norm(out, axis=1, keepdims=True)


KB = pd.DataFrame(
    [
        ("TKT-1", "VPN down", "vpn broken", "en", "IT"),
        ("TKT-2", "VPN ausgefallen", "vpn geht nicht", "de", "IT"),
        ("TKT-3", "Invoice wrong", "invoice amount", "en", "Billing"),
        ("TKT-4", "Rechnung falsch", "rechnung betrag", "de", "Billing"),
        ("TKT-5", "Printer jam", "printer", "en", "IT"),
    ],
    columns=["ticket_id", "subject", "body", "language", "queue"],
).assign(answer="ok", type="Incident", priority="low")


def _store(tmp_path, embedder):
    store = VectorStore(tmp_path / "x.sqlite", embedder)
    build_index(store, KB)
    return store


def _meta():
    return {r["ticket_id"]: r for r in KB.to_dict("records")}


def test_multilingual_embedder_finds_english_precedents_and_skips_self(tmp_path):
    store = _store(tmp_path, ConceptEmbedder())
    german = KB[KB["language"] == "de"]
    stats = crosslingual_stats(store, _meta(), german, k=1)
    # Without skipping itself, each German ticket would be its own (German) top hit.
    assert stats["queries"] == 2
    assert stats["top1_english"] == 1.0
    assert stats["top1_same_queue"] == 1.0
    assert stats["share_topk_english"] == 1.0


def test_bag_of_words_stays_in_german(tmp_path):
    store = _store(tmp_path, HashEmbedder(dim=64))
    german = KB[KB["language"] == "de"]
    stats = crosslingual_stats(store, _meta(), german, k=2)
    assert stats["queries"] == 2
    # Shares are fractions over k hits, and the ticket itself never counts.
    assert 0.0 <= stats["share_topk_english"] <= 1.0


def test_small_batches_give_the_same_numbers(tmp_path):
    store = _store(tmp_path, ConceptEmbedder())
    german = KB[KB["language"] == "de"]
    assert crosslingual_stats(store, _meta(), german, k=3, batch=1) == crosslingual_stats(
        store, _meta(), german, k=3, batch=64
    )


def test_empty_index_or_no_queries(tmp_path):
    empty = VectorStore(tmp_path / "empty.sqlite", ConceptEmbedder())
    assert crosslingual_stats(empty, _meta(), KB)["queries"] == 0
    store = _store(tmp_path, ConceptEmbedder())
    assert crosslingual_stats(store, _meta(), KB.iloc[0:0])["queries"] == 0


def test_index_path_reuses_the_demo_index_only_for_its_own_embedder(tmp_path):
    from eval.crosslingual_check import EVAL_DIR, index_path
    from shared.settings import Settings

    demo = tmp_path / "sentinel.sqlite"
    s = Settings(_env_file=None, sentinel_memory_path=demo)
    assert index_path("ollama", s, "ollama-embeddinggemma") == EVAL_DIR / "crosslingual_ollama.sqlite"
    assert not demo.exists()  # looking never creates the demo file

    build_index(VectorStore(demo, ConceptEmbedder()), KB)  # the demo index holds concept-3 vectors
    assert index_path("concept", s, "concept-3") == demo
    assert index_path("gemini", s, "gemini-gemini-embedding-001") == EVAL_DIR / "crosslingual_gemini.sqlite"
