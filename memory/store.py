"""SQLite-backed vector store with brute-force cosine search.

Single file, no server, no extra deps. Comfortable up to ~100k chunks; swap the
internals for LanceDB / sqlite-vec / pgvector later without changing the interface.
Vectors are tagged with the embedder name so switching embedders never mixes dimensions
(re-ingest after switching).
"""

import json
import sqlite3
from pathlib import Path

import numpy as np

from memory.embedder import Embedder, get_embedder
from shared.contracts import Chunk, RetrievedChunk, SourceKind
from shared.settings import Settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id        TEXT PRIMARY KEY,
    source    TEXT NOT NULL,
    kind      TEXT NOT NULL,
    text      TEXT NOT NULL,
    locator   TEXT NOT NULL,
    metadata  TEXT NOT NULL,
    embedder  TEXT NOT NULL,
    vec       BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_source ON chunks(source);
CREATE INDEX IF NOT EXISTS chunks_embedder ON chunks(embedder);
"""


class VectorStore:
    def __init__(self, path: Path | str, embedder: Embedder):
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.embedder = embedder
        self._cache: tuple[list[str], np.ndarray] | None = None

    def add(self, chunks: list[Chunk], embed_texts: list[str] | None = None) -> int:
        """Store chunks. `embed_texts` embeds something other than `chunk.text` (same order).

        Used by ticket ingestion: a ticket chunk *stores* subject + body + historical answer (so
        quotes can be verified against the resolution) but is *embedded* on subject + body only,
        so an incoming ticket is matched against past problems, not past answers.
        """
        if not chunks:
            return 0
        if embed_texts is not None and len(embed_texts) != len(chunks):
            raise ValueError("embed_texts must be the same length as chunks")
        vecs = self.embedder.embed(embed_texts if embed_texts is not None else [c.text for c in chunks])
        self.db.executemany(
            "INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?,?,?,?)",
            [
                (c.id, c.source, c.kind, c.text, c.locator, json.dumps(c.metadata), self.embedder.name, v.tobytes())
                for c, v in zip(chunks, vecs)
            ],
        )
        self.db.commit()
        self._cache = None
        return len(chunks)

    def delete_source(self, source: str) -> None:
        self.db.execute("DELETE FROM chunks WHERE source = ?", (source,))
        self.db.commit()
        self._cache = None

    def reset(self) -> None:
        self.db.execute("DELETE FROM chunks")
        self.db.commit()
        self._cache = None

    def count(self) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM chunks WHERE embedder = ?", (self.embedder.name,)
        ).fetchone()[0]

    def sources(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT DISTINCT source FROM chunks ORDER BY source")]

    def get(self, chunk_id: str) -> Chunk | None:
        row = self.db.execute(
            "SELECT id, source, kind, text, locator, metadata FROM chunks WHERE id = ?", (chunk_id,)
        ).fetchone()
        return self._row_to_chunk(row) if row else None

    def search(self, query: str, k: int = 6, kind: SourceKind | None = None) -> list[RetrievedChunk]:
        ids, matrix = self._matrix()
        if not ids:
            return []
        q = self.embedder.embed([query], is_query=True)[0]
        scores = matrix @ q
        order = np.argsort(-scores)
        results: list[RetrievedChunk] = []
        for i in order:
            chunk = self.get(ids[i])
            if chunk is None or (kind and chunk.kind != kind):
                continue
            results.append(RetrievedChunk(chunk=chunk, score=round(float(scores[i]), 4)))
            if len(results) >= k:
                break
        return results

    def vectors(self) -> tuple[list[str], np.ndarray]:
        """(chunk ids, unit vectors) for this store's embedder, for batch scoring (eval scripts)."""
        return self._matrix()

    def _matrix(self) -> tuple[list[str], np.ndarray]:
        if self._cache is None:
            # Stream the cursor into one preallocated array instead of fetchall() + np.stack:
            # same result at a fraction of the peak memory, which matters on a laptop that is
            # also hosting two local models (22,869 x 768 float32 = 67 MB on its own).
            n = self.count()
            cursor = self.db.execute("SELECT id, vec FROM chunks WHERE embedder = ?", (self.embedder.name,))
            ids, matrix = [], None
            for i, (chunk_id, blob) in enumerate(cursor):
                if matrix is None:
                    matrix = np.empty((n, len(blob) // 4), dtype=np.float32)
                if i < n:
                    matrix[i] = np.frombuffer(blob, dtype=np.float32)
                    ids.append(chunk_id)
            if matrix is None:
                matrix = np.zeros((0, 0), dtype=np.float32)
            elif len(ids) < n:  # rows changed under us; keep only what was read
                matrix = matrix[: len(ids)]
            self._cache = (ids, matrix)
        return self._cache

    @staticmethod
    def _row_to_chunk(row) -> Chunk:
        id_, source, kind, text, locator, metadata = row
        return Chunk(id=id_, source=source, kind=kind, text=text, locator=locator, metadata=json.loads(metadata))


def open_store(settings: Settings) -> VectorStore:
    return VectorStore(settings.memory_path, get_embedder(settings))
