"""Index the historical knowledge base (kb_train only) into the vector store.

One chunk per resolved ticket:

    id/source  TKT-00042                     <- what the drafted reply must cite
    text       Subject / Body / Resolution   <- what a quote is verified against
    embedded   subject + body only           <- so an incoming problem matches past problems
    metadata   type, queue, priority, language, subject, answer, tags

The holdout split is never read here, so nothing it contains can reach retrieval.

    python -m sentinel.ingest_tickets --reset            # full kb_train
    python -m sentinel.ingest_tickets --reset --limit 4000
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

from memory.store import VectorStore
from memory.embedder import get_embedder
from sentinel import dataset
from shared.contracts import Chunk
from shared.settings import get_settings

BATCH = 128  # Ollama embeds a list in one call; 128 keeps each request ~2-4 s


def ticket_chunk(row: pd.Series) -> Chunk:
    subject = str(row.get("subject") or "").strip()
    body = str(row.get("body") or "").strip()
    answer = str(row.get("answer") or "").strip()
    text = "\n".join(
        part
        for part in [
            f"Subject: {subject}" if subject else "",
            f"Body: {body}",
            f"Resolution: {answer}" if answer else "",
        ]
        if part
    )
    tags = [str(row.get(c) or "").strip() for c in dataset.TAG_COLUMNS if str(row.get(c) or "").strip()]
    return Chunk(
        id=str(row["ticket_id"]),
        source=str(row["ticket_id"]),
        kind="ticket",
        text=text,
        locator="resolution",
        metadata={
            "ticket_id": str(row["ticket_id"]),
            "type": str(row["type"]),
            "queue": str(row["queue"]),
            "priority": str(row["priority"]),
            "language": str(row["language"]),
            "subject": subject,
            "answer": answer,
            "tags": ", ".join(tags),
        },
    )


def index_kb(
    kb_train_df: pd.DataFrame, memory_path: Path | str | None = None, reset: bool = False, verbose: bool = True
) -> int:
    settings = get_settings()
    store = VectorStore(memory_path or settings.memory_path, get_embedder(settings))
    if reset:
        store.reset()

    rows = kb_train_df.to_dict("records")
    total, t0 = 0, time.perf_counter()
    for start in range(0, len(rows), BATCH):
        batch = rows[start : start + BATCH]
        chunks = [ticket_chunk(pd.Series(r)) for r in batch]
        store.add(chunks, embed_texts=[dataset.ticket_text(r) for r in batch])
        total += len(chunks)
        if verbose:
            elapsed = time.perf_counter() - t0
            rate = total / elapsed if elapsed else 0
            eta = (len(rows) - total) / rate / 60 if rate else 0
            print(f"  {total:>6,}/{len(rows):,}  {rate:5.1f} tickets/s  eta {eta:4.1f} min", flush=True)
    return total


def main() -> None:
    ap = argparse.ArgumentParser(description="Index kb_train tickets into the vector store.")
    ap.add_argument("--reset", action="store_true", help="clear the index first")
    ap.add_argument("--limit", type=int, default=None, help="index only the first N kb tickets (smoke test)")
    ap.add_argument("--memory", default=None, help="sqlite path (default: MEMORY_PATH from .env)")
    args = ap.parse_args()

    kb, test = dataset.load_split()
    report = dataset.leakage_report(kb, test)
    assert report["ok"], f"leakage check failed: {report}"
    if args.limit:
        kb = kb.head(args.limit)

    settings = get_settings()
    path = args.memory or settings.memory_path
    print(f"indexing {len(kb):,} kb_train tickets -> {path} (embedder: {settings.embed_provider})", flush=True)
    n = index_kb(kb, memory_path=args.memory, reset=args.reset)
    print(f"done: {n:,} ticket chunks indexed")


if __name__ == "__main__":
    main()
