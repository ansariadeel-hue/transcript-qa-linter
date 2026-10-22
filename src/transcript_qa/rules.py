"""Lint rules. Each rule yields ``(line, col, message)`` tuples.

Rules receive a :class:`Context` with the parsed transcript, the effective
configuration and the effective language. Severity and enable/disable are
applied by :mod:`transcript_qa.linter`, so rules stay pure.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Callable, Iterator

from .model import Segment, Transcript
from .scripts import (
    LANGUAGE_SCRIPTS,
    NATIVE_DIGITS,
    dominant_script,
    iter_digit_runs,
    iter_words,
    word_scripts,
)

TAG_RE = re.compile(r"\[([^\[\]]*)\]")
TRAILING_TIME_RE = re.compile(r"\s+\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?$")
BRACKET_PAIRS = {")": "(", "]": "[", "}": "{"}

Finding = tuple[int | None, int | None, str]


@dataclass
class Context:
    transcript: Transcript
    config: dict
    language: str | None

    @property
    def expected_script(self) -> str | None:
        return LANGUAGE_SCRIPTS.get((self.language or "").split("-")[0])

    def col(self, seg: Segment, index: int) -> int | None:
        return seg.text_col + index


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    severity: str
    description: str
    check: Callable[[Context], Iterator[Finding]]


def mask_tags(text: str) -> str:
    """Blank out ``[tag]`` spans (keeping offsets) so they are not linted as words."""
    return TAG_RE.sub(lambda m: " " * len(m.group(0)), text)


def fmt_ts(seconds: float) -> str:
    h, rem = divmod(round(seconds * 1000), 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


# --------------------------------------------------------------------------
# Timestamps
# --------------------------------------------------------------------------

def check_malformed_timestamp(ctx: Context):
    for seg in ctx.transcript.segments:
        if seg.timestamp_raw is not None and seg.timestamp is None:
            yield (seg.line, seg.timestamp_col,
                   f"malformed timestamp '{seg.timestamp_raw}' (expected HH:MM:SS.mmm, e.g. 00:01:23.450)")


def check_non_monotonic_timestamp(ctx: Context):
    prev: Segment | None = None
    for seg in ctx.transcript.segments:
        if seg.timestamp is None:
            continue
        if prev is not None and seg.timestamp < prev.timestamp:
            yield (seg.line, seg.timestamp_col,
                   f"timestamp {fmt_ts(seg.timestamp)} goes backwards (previous {fmt_ts(prev.timestamp)} "
                   f"at {ctx.transcript.unit} {prev.line})")
        prev = seg


def check_missing_timestamp(ctx: Context):
    segs = ctx.transcript.segments
    if not any(s.timestamp_raw is not None for s in segs):
        return
    for seg in segs:
        if seg.timestamp_raw is None:
            yield (seg.line, 1 if ctx.transcript.kind == "text" else None,
                   "segment has no timestamp while others do")


# --------------------------------------------------------------------------
# Tags and brackets
# --------------------------------------------------------------------------

def _tag_name(content: str) -> str:
    # "[inaudible 00:01:02]" -> "inaudible"; "[foreign: Urdu]" -> "foreign"
    name = TRAILING_TIME_RE.sub("", content.strip())
    name = name.split(":", 1)[0]
    return " ".join(name.split())


def check_unknown_tag(ctx: Context):
    case_sensitive = ctx.config["tag_case_sensitive"]
    allowed = list(ctx.config["allowed_tags"])
    norm = (lambda s: s) if case_sensitive else str.lower
    allowed_set = {norm(a) for a in allowed}
    for seg in ctx.transcript.segments:
        for m in TAG_RE.finditer(seg.text):
            name = _tag_name(m.group(1))
            if norm(name) in allowed_set:
                continue
            msg = f"unknown notation tag [{m.group(1)}]"
            close = difflib.get_close_matches(norm(name), [norm(a) for a in allowed], n=1, cutoff=0.7)
            if close:
                msg += f" (did you mean [{close[0]}]?)"
            elif not name:
                msg = "empty notation tag []"
            yield (seg.line, ctx.col(seg, m.start()), msg)


def check_unbalanced_brackets(ctx: Context):
    for seg in ctx.transcript.segments:
        stack: list[tuple[str, int]] = []
        for i, ch in enumerate(seg.text):
            if ch in "([{":
                stack.append((ch, i))
            elif ch in BRACKET_PAIRS:
                if stack and stack[-1][0] == BRACKET_PAIRS[ch]:
                    stack.pop()
                else:
                    yield (seg.line, ctx.col(seg, i), f"unmatched closing '{ch}'")
        for ch, i in stack:
            yield (seg.line, ctx.col(seg, i), f"unclosed '{ch}'")


# --------------------------------------------------------------------------
# Whitespace
# --------------------------------------------------------------------------

def _whitespace_targets(ctx: Context):
    """(line, base_col, string) pairs to scan for whitespace problems."""
    tr = ctx.transcript
    if tr.kind == "text":
        for lineno, raw in tr.raw_lines:
            yield lineno, 1, raw
    else:
        for seg in tr.segments:
            yield seg.line, 1, seg.text


def check_double_space(ctx: Context):
    for line, base, s in _whitespace_targets(ctx):
        body_end = len(s.rstrip())
        body_start = len(s) - len(s.lstrip())
        for m in re.finditer(r" {2,}", s):
            if m.start() >= body_start and m.end() <= body_end:
                yield (line, base + m.start(), f"{len(m.group(0))} consecutive spaces")


def check_trailing_whitespace(ctx: Context):
    for line, base, s in _whitespace_targets(ctx):
        stripped = s.rstrip()
        if stripped != s:
            yield (line, base + len(stripped), "trailing whitespace")
        if ctx.transcript.kind == "json" and s.strip() and s != s.lstrip():
            yield (line, base, "leading whitespace in segment text")


# --------------------------------------------------------------------------
# Content
# --------------------------------------------------------------------------

def check_empty_segment(ctx: Context):
    for seg in ctx.transcript.segments:
        if not seg.text.strip():
            what = "after speaker label" if seg.speaker else "after timestamp" if seg.timestamp_raw else ""
            yield (seg.line, seg.text_col if ctx.transcript.kind == "text" else None,
                   f"empty segment{(' (no text ' + what + ')') if what else ''}")


def check_script_mixing(ctx: Context):
    allow = {w.casefold() for w in ctx.config["script_allowlist"]}
    fixed = ctx.expected_script
    for seg in ctx.transcript.segments:
        text = mask_tags(seg.text)
        expected = fixed or dominant_script(text)
        if expected is None:
            continue
        for start, word in iter_words(text):
            scripts = word_scripts(word)
            if not scripts:
                continue
            if len(scripts) > 1:
                yield (seg.line, ctx.col(seg, start),
                       f"word '{word}' mixes scripts ({', '.join(sorted(scripts))})")
                continue
            (script,) = scripts
            if script != expected and word.casefold() not in allow:
                where = f"{expected} {'transcript' if fixed else 'segment'}"
                yield (seg.line, ctx.col(seg, start), f"{script} word '{word}' in {where}")


def check_numeral_style(ctx: Context):
    mode = ctx.config["numerals"]
    if mode == "off":
        return
    runs = []  # (seg, start, run, style)
    for seg in ctx.transcript.segments:
        for start, run, style in iter_digit_runs(mask_tags(seg.text)):
            runs.append((seg, start, run, style))
    if not runs:
        return
    native = NATIVE_DIGITS.get(ctx.expected_script or "")
    if mode == "ascii":
        bad = lambda style: style != "ascii"  # noqa: E731
        why = "use ASCII digits 0-9"
    elif mode == "native":
        if native is None:
            # Latin-script or unknown language: native == ASCII.
            bad = lambda style: style != "ascii"  # noqa: E731
            why = "use ASCII digits for this language"
        else:
            bad = lambda style: style != native  # noqa: E731
            why = f"use {native} digits"
    else:  # consistent
        counts = Counter(style for *_, style in runs)
        if len(counts) < 2:
            return
        first_seen = {}
        for *_, style in runs:
            first_seen.setdefault(style, len(first_seen))
        majority = max(counts, key=lambda s: (counts[s], -first_seen[s]))
        bad = lambda style: style != majority  # noqa: E731
        why = (f"inconsistent with the file's {majority} digits "
               f"({counts[majority]} of {sum(counts.values())} numbers use {majority})")
    for seg, start, run, style in runs:
        if bad(style):
            yield (seg.line, ctx.col(seg, start), f"{style} numeral '{run}': {why}")


# --------------------------------------------------------------------------
# Speakers
# --------------------------------------------------------------------------

def _speaker_key(label: str) -> str:
    return re.sub(r"[\s_\-.]+", "", label).casefold()


def check_inconsistent_speaker(ctx: Context):
    labelled = [s for s in ctx.transcript.segments if s.speaker]
    if not labelled:
        return
    counts = Counter(s.speaker for s in labelled)
    first_line = {}
    for s in labelled:
        first_line.setdefault(s.speaker, s.line)

    def rank(label):  # most frequent first, then earliest
        return (-counts[label], first_line[label])

    by_key = defaultdict(list)
    for label in counts:
        by_key[_speaker_key(label)].append(label)
    canonical_of = {}
    for labels in by_key.values():
        canon = min(labels, key=rank)
        for label in labels:
            if label != canon:
                canonical_of[label] = (canon, "is written differently from")
    # Fuzzy: near-identical keys that are not just numbered variants.
    canon_labels = sorted({min(v, key=rank) for v in by_key.values()}, key=rank)
    for i, a in enumerate(canon_labels):
        for b in canon_labels[i + 1:]:
            ka, kb = _speaker_key(a), _speaker_key(b)
            if re.sub(r"\d", "", ka) == re.sub(r"\d", "", kb):
                continue
            if difflib.SequenceMatcher(None, ka, kb).ratio() >= 0.85:
                canonical_of.setdefault(b, (a, "looks like a misspelling of"))
                for variant in by_key[kb]:
                    canonical_of.setdefault(variant, (a, "looks like a misspelling of"))
    for seg in labelled:
        if seg.speaker in canonical_of:
            canon, how = canonical_of[seg.speaker]
            yield (seg.line, seg.speaker_col,
                   f"speaker label '{seg.speaker}' {how} '{canon}' (first used at "
                   f"{ctx.transcript.unit} {first_line[canon]})")


def check_unknown_speaker(ctx: Context):
    allowed = ctx.config["speakers"]
    if not allowed:
        return
    for seg in ctx.transcript.segments:
        if seg.speaker and seg.speaker not in allowed:
            msg = f"speaker '{seg.speaker}' is not in the configured speaker list"
            close = difflib.get_close_matches(seg.speaker, allowed, n=1, cutoff=0.6)
            if close:
                msg += f" (did you mean '{close[0]}'?)"
            yield (seg.line, seg.speaker_col, msg)


def check_missing_speaker(ctx: Context):
    segs = ctx.transcript.segments
    if not any(s.speaker for s in segs):
        return
    for seg in segs:
        if not seg.speaker:
            yield (seg.line, seg.text_col if ctx.transcript.kind == "text" else None,
                   "segment has no speaker label while others do")


RULES: list[Rule] = [
    Rule("TS001", "malformed-timestamp", "error", "Timestamp is not [HH:MM:SS.mmm] or has out-of-range fields.", check_malformed_timestamp),
    Rule("TS002", "non-monotonic-timestamp", "error", "Timestamp is earlier than the previous segment's.", check_non_monotonic_timestamp),
    Rule("TS003", "missing-timestamp", "warning", "Segment lacks a timestamp although other segments have one.", check_missing_timestamp),
    Rule("TAG001", "unknown-tag", "error", "Notation tag not in the allowed set (suggests the closest allowed tag).", check_unknown_tag),
    Rule("BR001", "unbalanced-brackets", "error", "Unmatched or unclosed (), [] or {}.", check_unbalanced_brackets),
    Rule("WS001", "double-space", "warning", "Two or more consecutive spaces inside a line.", check_double_space),
    Rule("WS002", "trailing-whitespace", "warning", "Whitespace at the end of a line (or around JSON segment text).", check_trailing_whitespace),
    Rule("SEG001", "empty-segment", "error", "Segment has a timestamp/speaker but no text.", check_empty_segment),
    Rule("SCR001", "script-mixing", "warning", "Word in an unexpected script for the language/segment (allowlist aware).", check_script_mixing),
    Rule("SPK001", "inconsistent-speaker", "warning", "Speaker label spelled/cased differently from an earlier label.", check_inconsistent_speaker),
    Rule("SPK002", "unknown-speaker", "error", "Speaker label not in the configured 'speakers' list.", check_unknown_speaker),
    Rule("SPK003", "missing-speaker", "warning", "Segment lacks a speaker label although other segments have one.", check_missing_speaker),
    Rule("NUM001", "numeral-style", "warning", "Digits violate the configured numeral style (consistent/ascii/native).", check_numeral_style),
]

RULES_BY_ID = {r.id: r for r in RULES}
PARSE_RULE_ID = "PARSE001"
