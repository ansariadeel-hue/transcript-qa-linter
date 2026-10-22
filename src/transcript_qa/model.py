"""Data model shared by the parser, rules and reporters."""

from __future__ import annotations

from dataclasses import dataclass, field

SEVERITIES = ("error", "warning", "info")


@dataclass
class Segment:
    """One transcript segment (a line in .txt, an object in .json).

    ``line`` is the 1-based line number for text files and the 1-based
    segment index for JSON files. Column offsets are 1-based positions in the
    raw line (text files) or in the ``text`` field (JSON files).
    """

    line: int
    text: str
    text_col: int = 1
    timestamp_raw: str | None = None
    timestamp_col: int | None = None
    timestamp: float | None = None
    speaker: str | None = None
    speaker_col: int | None = None
    raw: str | None = None


@dataclass
class Transcript:
    path: str
    kind: str  # "text" or "json"
    segments: list[Segment] = field(default_factory=list)
    language: str | None = None
    raw_lines: list[tuple[int, str]] = field(default_factory=list)  # text files only

    @property
    def unit(self) -> str:
        return "line" if self.kind == "text" else "segment"


@dataclass
class Issue:
    path: str
    line: int | None
    col: int | None
    rule: str
    severity: str
    message: str
    unit: str = "line"

    def to_dict(self) -> dict:
        return {
            "file": self.path,
            "unit": self.unit,
            "line": self.line,
            "col": self.col,
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
        }

    def sort_key(self):
        return (self.path, self.line or 0, self.col or 0, self.rule)
