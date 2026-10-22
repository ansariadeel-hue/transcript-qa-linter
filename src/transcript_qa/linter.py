"""Run the rule set over transcripts and collect issues."""

from __future__ import annotations

from pathlib import Path

from .config import make_config
from .model import Issue, Transcript
from .parser import ParseError, load_transcript, parse_json, parse_text
from .rules import PARSE_RULE_ID, RULES, Context

KNOWN_RULE_IDS = {r.id for r in RULES} | {PARSE_RULE_ID}


def lint_transcript(tr: Transcript, config: dict | None = None, language: str | None = None) -> list[Issue]:
    cfg = config if config is not None else make_config()
    lang = language or tr.language or cfg.get("language")
    ctx = Context(tr, cfg, lang.lower() if lang else None)
    disabled = set(cfg["disable"])
    issues: list[Issue] = []
    for rule in RULES:
        if rule.id in disabled:
            continue
        severity = cfg["severity"].get(rule.id, rule.severity)
        for line, col, message in rule.check(ctx):
            issues.append(Issue(tr.path, line, col, rule.id, severity, message, tr.unit))
    issues.sort(key=Issue.sort_key)
    return issues


def lint_text(content: str, config: dict | None = None, language: str | None = None,
              path: str = "<text>") -> list[Issue]:
    return lint_transcript(parse_text(content, path), config, language)


def lint_json(content: str, config: dict | None = None, language: str | None = None,
              path: str = "<json>") -> list[Issue]:
    return lint_transcript(parse_json(content, path), config, language)


def lint_file(path: str | Path, config: dict | None = None, language: str | None = None) -> list[Issue]:
    cfg = config if config is not None else make_config()
    try:
        tr = load_transcript(path)
    except (ParseError, UnicodeDecodeError) as exc:
        severity = cfg["severity"].get(PARSE_RULE_ID, "error")
        return [Issue(path if isinstance(path, str) else str(path), None, None, PARSE_RULE_ID, severity, f"cannot parse file: {exc}", "file")]
    return lint_transcript(tr, cfg, language)
