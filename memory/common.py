"""Shared CLI plumbing for the ingest_* scripts."""

import argparse
from collections.abc import Callable, Iterable
from pathlib import Path

from memory.store import open_store
from shared.contracts import Chunk
from shared.settings import get_settings

IGNORE_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", "data", ".pytest_cache"}


def iter_files(root: Path, exts: set[str]) -> Iterable[Path]:
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in exts and not (IGNORE_DIRS & set(path.parts)):
            yield path


def rel_source(path: Path, root: Path) -> str:
    """Source id = <root folder name>/<path inside it>, e.g. `docs/guide.md`.

    Keeping the root's own name means two roots with same-named files (dirA/readme.md, dirB/readme.md)
    get different sources instead of silently replacing each other in the index.
    """
    base = root.parent if root.is_file() else root
    prefix = base.resolve().name
    try:
        rel = path.relative_to(base).as_posix()
    except ValueError:
        return path.resolve().as_posix()
    return f"{prefix}/{rel}" if prefix else rel


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def run_cli(description: str, exts: set[str], to_chunks: Callable[[Path, str], list[Chunk]]) -> None:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("paths", nargs="+", type=Path, help="files or directories to index")
    parser.add_argument("--reset", action="store_true", help="wipe the whole index first")
    args = parser.parse_args()

    store = open_store(get_settings())
    if args.reset:
        store.reset()

    total_files = total_chunks = 0
    for root in args.paths:
        for path in iter_files(root, exts):
            source = rel_source(path, root)
            try:
                chunks = to_chunks(path, source)
            except Exception as e:  # keep going: one bad file must not stop a kickoff-time ingest
                print(f"skip  {source}: {e}")
                continue
            store.delete_source(source)
            n = store.add(chunks)
            total_files += 1
            total_chunks += n
            print(f"index {source}: {n} chunks")
    print(f"done: {total_files} files, {total_chunks} chunks, {store.count()} total in {store.embedder.name}")
