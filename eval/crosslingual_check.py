"""Cross-lingual retrieval check (owner: Rithwik, role C).

For every German ticket in the VALIDATION slice, search the kb_train index (skipping the ticket itself) and measure:

    share_topk_english  share of the top-k precedents that are English tickets
    top1_english        how often the top precedent is English
    top1_same_queue     how often the top precedent has the same queue as the German ticket

A bag-of-words embedder (hash) can only match German to German; a multilingual embedder (gemini) should pull in
English precedents for the same problem. The holdout is never read.

Each embedder needs its own index (chunk ids are ticket ids, so one file holds one embedder):

    the demo index data/sentinel.sqlite, if it already holds this embedder's vectors (e.g. Je's EmbeddingGemma
    index for ollama); otherwise data/eval/crosslingual_<provider>.sqlite, built here on demand (always for hash,
    with --build for the others). The demo index is never written to.

    python -m eval.crosslingual_check                     # hash vs gemini
    python -m eval.crosslingual_check --providers hash,ollama   # on the demo laptop: hash vs EmbeddingGemma
    python -m eval.crosslingual_check --limit 200         # first 200 German validation tickets
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

import numpy as np
import pandas as pd

from memory.embedder import get_embedder
from memory.store import VectorStore
from sentinel import dataset
from sentinel.ingest_tickets import ticket_chunk
from shared.settings import Settings, get_settings

OUT_PATH = Path("data/eval/crosslingual.json")
EVAL_DIR = Path("data/eval")


def crosslingual_stats(
    store: VectorStore, kb_meta: dict[str, dict], queries: pd.DataFrame, k: int = 5, batch: int = 64
) -> dict[str, float | int]:
    """Score `queries` (rows with ticket_id, subject, body, queue) against `store`, skipping each ticket itself.

    `kb_meta` maps every indexed ticket id to its row (needs "language" and "queue").
    """
    ids, matrix = store.vectors()
    if not ids or queries.empty:
        return {"queries": 0, "share_topk_english": 0.0, "top1_english": 0.0, "top1_same_queue": 0.0,
                "top1_score_mean": 0.0}
    rows = queries.to_dict("records")
    english_shares, top1_en, top1_queue, top1_scores = [], [], [], []
    for start in range(0, len(rows), batch):
        part = rows[start : start + batch]
        q = store.embedder.embed([dataset.ticket_text(r) for r in part], is_query=True)
        scores = matrix @ q.T  # (n_index, n_batch)
        for j, row in enumerate(part):
            col = scores[:, j]
            # k + 1 candidates is enough: at most one of them is the ticket itself.
            top = np.argpartition(-col, min(k + 1, len(col) - 1))[: k + 1]
            top = top[np.argsort(-col[top])]
            hits = [i for i in top if ids[i] != str(row["ticket_id"])][:k]
            if not hits:
                continue
            langs = [kb_meta[ids[i]]["language"] for i in hits]
            english_shares.append(sum(lang == "en" for lang in langs) / len(hits))
            top1_en.append(langs[0] == "en")
            top1_queue.append(kb_meta[ids[hits[0]]]["queue"] == row["queue"])
            top1_scores.append(float(col[hits[0]]))
    n = len(english_shares)
    return {
        "queries": n,
        "share_topk_english": round(float(np.mean(english_shares)), 4) if n else 0.0,
        "top1_english": round(float(np.mean(top1_en)), 4) if n else 0.0,
        "top1_same_queue": round(float(np.mean(top1_queue)), 4) if n else 0.0,
        "top1_score_mean": round(float(np.mean(top1_scores)), 4) if n else 0.0,
    }


def index_path(provider: str, settings: Settings, embedder_name: str) -> Path:
    """The demo index when it already has this embedder's vectors, else this script's own file for the provider."""
    demo = Path(settings.sentinel_memory_path)
    if demo.exists():
        with sqlite3.connect(demo) as db:
            try:
                has = db.execute("SELECT 1 FROM chunks WHERE embedder = ? LIMIT 1", (embedder_name,)).fetchone()
            except sqlite3.OperationalError:  # not an index file
                has = None
        if has:
            return demo
    return EVAL_DIR / f"crosslingual_{provider}.sqlite"


def build_index(store: VectorStore, kb: pd.DataFrame, batch: int = 256) -> int:
    rows = kb.to_dict("records")
    for start in range(0, len(rows), batch):
        part = rows[start : start + batch]
        store.add([ticket_chunk(pd.Series(r)) for r in part], embed_texts=[dataset.ticket_text(r) for r in part])
    return len(rows)


def run(providers: list[str], k: int = 5, limit: int | None = None, build: bool = False) -> dict[str, dict]:
    kb, _ = dataset.load_split()  # the holdout half is ignored
    _, val = dataset.split_train_val(kb)
    german = val[val["language"] == "de"]
    if limit:
        german = german.head(limit)
    kb_meta = {str(r["ticket_id"]): r for r in kb.to_dict("records")}

    results: dict[str, dict] = {}
    for provider in providers:
        settings = get_settings().model_copy(update={"embed_provider": provider})
        try:
            embedder = get_embedder(settings)
        except ValueError as e:  # e.g. gemini without a key
            print(f"{provider}: skipped ({e})")
            continue
        path = index_path(provider, settings, embedder.name)
        store = VectorStore(path, embedder)
        if store.count() == 0:
            if provider == "hash" or build:
                path.parent.mkdir(parents=True, exist_ok=True)
                print(f"{provider}: building index {path} ({len(kb):,} tickets)...", flush=True)
                build_index(store, kb)
            else:
                print(f"{provider}: skipped (no {store.embedder.name} vectors in {settings.sentinel_memory_path} "
                      f"or {path}; pass --build to embed kb_train into {path})")
                continue
        t0 = time.perf_counter()
        stats = crosslingual_stats(store, kb_meta, german, k=k)
        stats.update(embedder=store.embedder.name, index=str(path), seconds=round(time.perf_counter() - t0, 1))
        results[provider] = stats
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description="German validation tickets: how often are English precedents found?")
    ap.add_argument("--providers", default="hash,gemini", help="comma-separated embed providers to compare")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--limit", type=int, default=None, help="only the first N German validation tickets")
    ap.add_argument("--build", action="store_true", help="build a missing index (costs API calls for gemini)")
    args = ap.parse_args()

    results = run([p.strip() for p in args.providers.split(",") if p.strip()], args.k, args.limit, args.build)
    if not results:
        return
    cols = ["queries", "share_topk_english", "top1_english", "top1_same_queue", "top1_score_mean", "seconds"]
    print(f"\n{'provider':<10}" + "".join(f"{c:>20}" for c in cols))
    for provider, stats in results.items():
        print(f"{provider:<10}" + "".join(f"{stats[c]:>20}" for c in cols))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({"k": args.k, "results": results}, indent=2))
    print(f"\nwritten: {OUT_PATH}")


if __name__ == "__main__":
    main()
