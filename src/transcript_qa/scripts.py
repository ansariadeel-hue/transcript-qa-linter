"""Unicode script and digit classification (block ranges, no third-party data)."""

from __future__ import annotations

import unicodedata
from collections import Counter

# (start, end, script) — inclusive code point ranges.
SCRIPT_RANGES: list[tuple[int, int, str]] = [
    (0x0041, 0x005A, "Latin"),
    (0x0061, 0x007A, "Latin"),
    (0x00C0, 0x024F, "Latin"),
    (0x1E00, 0x1EFF, "Latin"),
    (0x0600, 0x06FF, "Arabic"),
    (0x0750, 0x077F, "Arabic"),
    (0x0900, 0x097F, "Devanagari"),
    (0xA8E0, 0xA8FF, "Devanagari"),
    (0x0B80, 0x0BFF, "Tamil"),
]

LANGUAGE_SCRIPTS = {
    "en": "Latin",
    "hi": "Devanagari",
    "mr": "Devanagari",
    "ta": "Tamil",
    "ur": "Arabic",
}

# Digit styles: ASCII and the native digit blocks of the supported scripts.
DIGIT_RANGES: list[tuple[int, int, str]] = [
    (0x0030, 0x0039, "ascii"),
    (0x0966, 0x096F, "devanagari"),
    (0x0BE6, 0x0BEF, "tamil"),
    (0x06F0, 0x06F9, "extended-arabic"),
    (0x0660, 0x0669, "arabic-indic"),
]
NATIVE_DIGITS = {"Devanagari": "devanagari", "Tamil": "tamil", "Arabic": "extended-arabic"}

ZERO_WIDTH = {"‌", "‍"}  # ZWNJ / ZWJ are legitimate inside Indic words


def script_of(ch: str) -> str | None:
    """Script name for a letter/mark, ``"Other"`` for unknown letters, else None."""
    cp = ord(ch)
    for start, end, name in SCRIPT_RANGES:
        if start <= cp <= end:
            cat = unicodedata.category(ch)
            return name if cat[0] in "LM" else None
    cat = unicodedata.category(ch)
    if cat[0] == "L":
        return "Other"
    return None  # digits, punctuation, generic combining marks, spaces


def digit_style(ch: str) -> str | None:
    cp = ord(ch)
    for start, end, name in DIGIT_RANGES:
        if start <= cp <= end:
            return name
    return None


def is_word_char(ch: str) -> bool:
    return ch in ZERO_WIDTH or unicodedata.category(ch)[0] in "LM"


def iter_words(text: str):
    """Yield ``(start_index, word)`` for runs of letters/marks (incl. ZWJ/ZWNJ)."""
    start = None
    for i, ch in enumerate(text):
        if is_word_char(ch):
            if start is None:
                start = i
        elif start is not None:
            yield start, text[start:i]
            start = None
    if start is not None:
        yield start, text[start:]


def word_scripts(word: str) -> set[str]:
    return {s for s in (script_of(c) for c in word) if s}


def dominant_script(text: str) -> str | None:
    counts = Counter(s for s in (script_of(c) for c in text) if s)
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def iter_digit_runs(text: str):
    """Yield ``(start_index, run, style)`` for consecutive digits of one style."""
    i = 0
    while i < len(text):
        style = digit_style(text[i])
        if style is None:
            i += 1
            continue
        j = i
        while j < len(text) and digit_style(text[j]) == style:
            j += 1
        yield i, text[i:j], style
        i = j
