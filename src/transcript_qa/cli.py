"""Command-line interface: ``transcript-qa check FILE... [--config rules.json]``.

Exit codes: 0 = no failing issues, 1 = failing issues found (errors by
default, see ``--fail-on``), 2 = usage / configuration / I/O error.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from typing import Sequence

from . import __version__
from .config import ConfigError, load_config, make_config
from .linter import KNOWN_RULE_IDS, lint_file
from .model import Issue
from .rules import RULES

SEVERITY_RANK = {"error": 3, "warning": 2, "info": 1}
FAIL_THRESHOLD = {"error": 3, "warning": 2, "info": 1, "never": 99}


def format_location(issue: Issue) -> str:
    if issue.line is None:
        return issue.path
    if issue.unit == "segment":
        loc = f"{issue.path}:seg {issue.line}"
    else:
        loc = f"{issue.path}:{issue.line}"
    return f"{loc}:{issue.col}" if issue.col is not None else loc


def summarize(issues: Sequence[Issue], n_files: int) -> dict:
    counts = Counter(i.severity for i in issues)
    return {
        "files": n_files,
        "files_with_issues": len({i.path for i in issues}),
        "errors": counts.get("error", 0),
        "warnings": counts.get("warning", 0),
        "infos": counts.get("info", 0),
    }


def format_text(issues: Sequence[Issue], n_files: int) -> str:
    lines = [f"{format_location(i)}: {i.severity} {i.rule} {i.message}" for i in issues]
    s = summarize(issues, n_files)
    if lines:
        lines.append("")
    by_rule = Counter(i.rule for i in issues)
    lines.append(
        f"{s['files']} file(s) checked: {s['errors']} error(s), {s['warnings']} warning(s), "
        f"{s['infos']} info"
        + (f"  [{', '.join(f'{r}x{n}' for r, n in sorted(by_rule.items()))}]" if by_rule else "")
    )
    return "\n".join(lines) + "\n"


def format_json(issues: Sequence[Issue], n_files: int) -> str:
    return json.dumps(
        {"summary": summarize(issues, n_files), "issues": [i.to_dict() for i in issues]},
        ensure_ascii=False, indent=2,
    ) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transcript-qa",
        description="QA linter for verbatim transcripts (English, Hindi, Marathi, Tamil).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    chk = sub.add_parser("check", help="lint one or more transcript files (.txt or .json)")
    chk.add_argument("files", nargs="+", help="transcript files")
    chk.add_argument("--config", help="JSON config file (see README)")
    chk.add_argument("--format", choices=("text", "json"), default="text", help="output format")
    chk.add_argument("--lang", help="override language for all files (en, hi, mr, ta, ur)")
    chk.add_argument("--fail-on", choices=("error", "warning", "info", "never"), default="error",
                     help="lowest severity that makes the exit code non-zero (default: error)")

    sub.add_parser("rules", help="list available rules")
    return parser


def _setup_stdout() -> None:
    # Indic text must not crash on legacy Windows consoles.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover
            pass


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_stdout()

    if args.command == "rules":
        for rule in RULES:
            print(f"{rule.id:<7} {rule.severity:<8} {rule.name:<24} {rule.description}")
        return 0

    try:
        cfg = load_config(args.config, KNOWN_RULE_IDS) if args.config else make_config(known_rules=KNOWN_RULE_IDS)
    except (OSError, ConfigError) as exc:
        print(f"transcript-qa: config error: {exc}", file=sys.stderr)
        return 2

    issues: list[Issue] = []
    for path in args.files:
        try:
            issues.extend(lint_file(path, cfg, args.lang))
        except OSError as exc:
            print(f"transcript-qa: cannot read {path}: {exc.strerror or exc}", file=sys.stderr)
            return 2

    out = format_json(issues, len(args.files)) if args.format == "json" else format_text(issues, len(args.files))
    sys.stdout.write(out)
    threshold = FAIL_THRESHOLD[args.fail_on]
    return 1 if any(SEVERITY_RANK[i.severity] >= threshold for i in issues) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
