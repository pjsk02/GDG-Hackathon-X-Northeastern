"""Index source code with exact line ranges.

Usage: python -m memory.ingest_code path/to/repo [more paths] [--reset]
"""

from pathlib import Path

from memory.chunking import chunk_lines
from memory.common import read_text, run_cli

CODE_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".go", ".rs", ".c", ".h", ".cc", ".cpp",
    ".hpp", ".cs", ".rb", ".php", ".swift", ".scala", ".r", ".sql", ".sh", ".ps1", ".yaml", ".yml", ".toml",
}


def to_chunks(path: Path, source: str):
    # 40-line windows: small enough that a citation points at one function, big enough to keep context.
    return chunk_lines(read_text(path), source, "code", max_lines=40, overlap=8, language=path.suffix.lstrip("."))


if __name__ == "__main__":
    run_cli(__doc__, CODE_EXTS, to_chunks)
