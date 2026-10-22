"""Parse plain-text and JSON transcripts into :class:`Transcript` objects.

Plain-text format (one segment per line)::

    # lang: hi
    [00:00:01.250] Speaker 1: नमस्ते, आज हम ...
    [00:00:04.900] Speaker 2: [laughter] हाँ ...

* Lines starting with ``#`` are comments / metadata (``# lang: <code>``).
* Blank lines are ignored.
* The optional leading ``[HH:MM:SS.mmm]`` is the segment start time.
* The optional ``Label:`` right after it (at most three words, no sentence
  punctuation) is the speaker label.

JSON format::

    {"language": "mr",
     "segments": [{"start": "00:00:01.000", "speaker": "A", "text": "..."}]}

A bare list of segment objects is accepted too.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .model import Segment, Transcript

TIMESTAMP_RE = re.compile(r"^(\d{2}):([0-5]\d):([0-5]\d)\.(\d{3})$")
# A leading bracket whose content is made of digits and time punctuation is
# treated as a (possibly malformed) timestamp rather than a notation tag.
LEADING_TS_RE = re.compile(r"\s*\[([0-9:.,;\s]*\d[0-9:.,;\s]*)\]")
SPEAKER_RE = re.compile(r"\s*([^\s:\[\](){}][^:\[\](){}]{0,39}?)\s*:(?=\s|$)")
META_RE = re.compile(r"#\s*(lang|language)\s*:\s*([A-Za-z-]+)\s*$", re.IGNORECASE)
SPEAKER_FORBIDDEN = set(",.?!;\"।॥")


class ParseError(ValueError):
    pass


def parse_timestamp(value: str) -> float | None:
    """``"00:01:23.450"`` -> 83.45 seconds; ``None`` if malformed."""
    m = TIMESTAMP_RE.match(value.strip()) if value is not None else None
    if not m:
        return None
    h, mnt, s, ms = (int(g) for g in m.groups())
    return h * 3600 + mnt * 60 + s + ms / 1000.0


def _looks_like_speaker(label: str) -> bool:
    if any(ch in SPEAKER_FORBIDDEN for ch in label):
        return False
    return 1 <= len(label.split()) <= 3


def parse_text(content: str, path: str = "<text>") -> Transcript:
    tr = Transcript(path=path, kind="text")
    for lineno, raw in enumerate(content.splitlines(), start=1):
        tr.raw_lines.append((lineno, raw))
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            m = META_RE.match(stripped)
            if m and tr.language is None:
                tr.language = m.group(2).lower()
            continue
        seg = Segment(line=lineno, text="", raw=raw)
        pos = 0
        m = LEADING_TS_RE.match(raw)
        if m:
            seg.timestamp_raw = m.group(1)
            seg.timestamp_col = m.start(1)  # 1-based column of '['
            seg.timestamp = parse_timestamp(m.group(1))
            pos = m.end()
        m = SPEAKER_RE.match(raw, pos)
        if m and _looks_like_speaker(m.group(1)):
            seg.speaker = m.group(1)
            seg.speaker_col = m.start(1) + 1
            pos = m.end()
        # skip the single separator space(s) before the text
        while pos < len(raw) and raw[pos] in " \t":
            pos += 1
        seg.text = raw[pos:]
        seg.text_col = pos + 1
        tr.segments.append(seg)
    return tr


def parse_json(content: str, path: str = "<json>") -> Transcript:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc.msg} (line {exc.lineno}, col {exc.colno})") from None
    language = None
    if isinstance(data, dict):
        language = data.get("language") or data.get("lang")
        segments = data.get("segments")
    else:
        segments = data
    if not isinstance(segments, list):
        raise ParseError("expected a list of segments or an object with a 'segments' list")
    tr = Transcript(path=path, kind="json", language=language.lower() if isinstance(language, str) else None)
    for i, obj in enumerate(segments, start=1):
        if not isinstance(obj, dict):
            raise ParseError(f"segment {i} is not an object")
        text = obj.get("text")
        text = "" if text is None else str(text)
        start = obj.get("start", obj.get("timestamp"))
        speaker = obj.get("speaker")
        seg = Segment(line=i, text=text, text_col=1)
        if start is not None:
            seg.timestamp_raw = str(start)
            seg.timestamp = parse_timestamp(str(start))
        if speaker is not None and str(speaker).strip():
            seg.speaker = str(speaker)
        tr.segments.append(seg)
    return tr


def load_transcript(path: str | Path) -> Transcript:
    display = path if isinstance(path, str) else str(path)  # report paths as given
    path = Path(path)
    content = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        return parse_json(content, display)
    return parse_text(content, display)
