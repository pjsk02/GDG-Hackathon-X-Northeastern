"""Turn raw files into Chunks with precise locators (line ranges, pages, timestamps)."""

import hashlib
import re
from dataclasses import dataclass

from shared.contracts import Chunk, SourceKind


def chunk_id(source: str, locator: str) -> str:
    return hashlib.sha1(f"{source}#{locator}".encode()).hexdigest()[:16]


def make_chunk(source: str, kind: SourceKind, text: str, locator: str, **metadata) -> Chunk:
    return Chunk(
        id=chunk_id(source, locator),
        source=source,
        kind=kind,
        text=text,
        locator=locator,
        metadata={k: str(v) for k, v in metadata.items()},
    )


# --- line-based (code, plain-text docs) -------------------------------------


def chunk_lines(
    text: str, source: str, kind: SourceKind, max_lines: int = 60, overlap: int = 10, **metadata
) -> list[Chunk]:
    """Fixed windows of lines. Locator is the exact 1-based line range."""
    lines = text.splitlines()
    chunks, start, step = [], 0, max(1, max_lines - overlap)
    while start < len(lines):
        end = min(start + max_lines, len(lines))
        body = "\n".join(lines[start:end])
        if body.strip():
            chunks.append(
                make_chunk(source, kind, body, f"L{start + 1}-L{end}", start_line=start + 1, **metadata)
            )
        if end == len(lines):
            break
        start += step
    return chunks


def chunk_paragraphs(text: str, source: str, kind: SourceKind = "doc", max_chars: int = 1200, **metadata) -> list[Chunk]:
    """Pack blank-line-separated paragraphs up to max_chars, keeping line ranges."""
    lines = text.splitlines()
    paragraphs: list[tuple[int, int]] = []  # (start_idx, end_idx_exclusive)
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].strip():
            j += 1
        paragraphs.append((i, j))
        i = j

    chunks: list[Chunk] = []
    cur_start = cur_end = None
    for p_start, p_end in paragraphs:
        size = sum(len(l) + 1 for l in lines[cur_start:p_end]) if cur_start is not None else 0
        if cur_start is not None and size > max_chars:
            chunks.append(_line_chunk(lines, cur_start, cur_end, source, kind, metadata))
            cur_start = None
        if cur_start is None:
            cur_start = p_start
        cur_end = p_end
    if cur_start is not None:
        chunks.append(_line_chunk(lines, cur_start, cur_end, source, kind, metadata))
    return chunks


def _line_chunk(lines, start, end, source, kind, metadata) -> Chunk:
    return make_chunk(
        source, kind, "\n".join(lines[start:end]), f"L{start + 1}-L{end}", start_line=start + 1, **metadata
    )


def chunk_pages(pages: list[str], source: str, **metadata) -> list[Chunk]:
    """One chunk per page (PDFs). Locator: p<n>."""
    return [make_chunk(source, "doc", t, f"p{n}", page=n, **metadata) for n, t in enumerate(pages, 1) if t.strip()]


# --- timestamped (transcripts, subtitles) -----------------------------------


@dataclass
class Cue:
    start: float  # seconds
    end: float
    text: str


_TS = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")


def parse_ts(ts: str) -> float:
    m = _TS.search(ts)
    if not m:
        raise ValueError(f"bad timestamp: {ts!r}")
    h, mnt, s, ms = m.groups()
    return int(h or 0) * 3600 + int(mnt) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def fmt_ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse_subtitles(text: str) -> list[Cue]:
    """Parse SRT or WebVTT into cues."""
    cues: list[Cue] = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = [l for l in block.strip().splitlines() if l.strip()]
        arrow = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if arrow is None:
            continue
        start, end = lines[arrow].split("-->")
        body = " ".join(re.sub(r"<[^>]+>", "", l) for l in lines[arrow + 1 :]).strip()
        if body:
            cues.append(Cue(parse_ts(start), parse_ts(end.split()[0]), body))
    return cues


def chunk_cues(cues: list[Cue], source: str, window_s: float = 30.0, **metadata) -> list[Chunk]:
    """Group cues into ~window_s windows. One cue per line so quotes map cleanly."""
    chunks: list[Chunk] = []
    group: list[Cue] = []
    for cue in cues:
        if group and cue.end - group[0].start > window_s:
            chunks.append(_cue_chunk(group, source, metadata))
            group = []
        group.append(cue)
    if group:
        chunks.append(_cue_chunk(group, source, metadata))
    return chunks


def _cue_chunk(group: list[Cue], source: str, metadata: dict) -> Chunk:
    locator = f"{fmt_ts(group[0].start)}-{fmt_ts(group[-1].end)}"
    text = "\n".join(c.text for c in group)
    return make_chunk(source, "media", text, locator, start_s=group[0].start, end_s=group[-1].end, **metadata)
