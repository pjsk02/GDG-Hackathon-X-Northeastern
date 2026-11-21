"""Index media as timestamped transcript windows.

Usage: python -m memory.ingest_media path/to/media [more paths] [--reset]

Handles:
  .srt / .vtt        subtitles
  .json              transcript list: [{"start": 1.2, "end": 3.4, "text": "..."}, ...]
                     (or {"segments": [...]}, i.e. Whisper output)
  .mp3/.wav/.m4a/.mp4/.mov/.webm
                     transcribed locally with faster-whisper: pip install -e ".[media]"
"""

import json
from pathlib import Path

from memory.chunking import Cue, chunk_cues, parse_subtitles
from memory.common import read_text, run_cli

TRANSCRIPT_EXTS = {".srt", ".vtt", ".json"}
AV_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".mp4", ".mov", ".mkv", ".webm"}
MEDIA_EXTS = TRANSCRIPT_EXTS | AV_EXTS

_whisper = None


def transcribe(path: Path) -> list[Cue]:
    global _whisper
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError('faster-whisper not installed: pip install -e ".[media]"') from e
    if _whisper is None:
        _whisper = WhisperModel("base", device="auto", compute_type="int8")
    segments, _ = _whisper.transcribe(str(path))
    return [Cue(s.start, s.end, s.text.strip()) for s in segments if s.text.strip()]


def to_chunks(path: Path, source: str):
    ext = path.suffix.lower()
    if ext in {".srt", ".vtt"}:
        cues = parse_subtitles(read_text(path))
    elif ext == ".json":
        data = json.loads(read_text(path))
        segs = data.get("segments", []) if isinstance(data, dict) else data
        cues = [Cue(float(s["start"]), float(s["end"]), str(s["text"]).strip()) for s in segs]
    else:
        cues = transcribe(path)
    return chunk_cues(cues, source, window_s=30.0, media_type=ext.lstrip("."))


if __name__ == "__main__":
    run_cli(__doc__, MEDIA_EXTS, to_chunks)
