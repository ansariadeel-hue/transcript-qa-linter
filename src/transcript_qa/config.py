"""Linter configuration (JSON file merged over sensible defaults)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from .model import SEVERITIES

DEFAULT_CONFIG: dict = {
    # Notation tags allowed inside square brackets, e.g. [inaudible].
    "allowed_tags": [
        "inaudible", "crosstalk", "laughter", "noise", "music", "pause",
        "cough", "applause", "silence", "foreign",
    ],
    "tag_case_sensitive": False,
    # If non-empty, speaker labels must be one of these (exact spelling).
    "speakers": [],
    # Words allowed to appear in a script other than the segment's script
    # (brand names, common code-mixed words). Compared case-insensitively.
    "script_allowlist": [],
    # "consistent" | "ascii" | "native" | "off"
    "numerals": "consistent",
    # Default language when the file does not declare one (en, hi, mr, ta, ur).
    "language": None,
    # Rule ids to disable, and per-rule severity overrides.
    "disable": [],
    "severity": {},
}

NUMERAL_MODES = ("consistent", "ascii", "native", "off")


class ConfigError(ValueError):
    pass


def validate_config(cfg: dict, known_rules: set[str] | None = None) -> dict:
    unknown = set(cfg) - set(DEFAULT_CONFIG)
    if unknown:
        raise ConfigError(f"unknown config key(s): {', '.join(sorted(unknown))}")
    for key in ("allowed_tags", "speakers", "script_allowlist", "disable"):
        value = cfg[key]
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ConfigError(f"'{key}' must be a list of strings")
    if cfg["numerals"] not in NUMERAL_MODES:
        raise ConfigError(f"'numerals' must be one of {', '.join(NUMERAL_MODES)}")
    if cfg["language"] is not None and not isinstance(cfg["language"], str):
        raise ConfigError("'language' must be a string or null")
    if not isinstance(cfg["tag_case_sensitive"], bool):
        raise ConfigError("'tag_case_sensitive' must be true or false")
    if not isinstance(cfg["severity"], dict):
        raise ConfigError("'severity' must be an object mapping rule id -> severity")
    for rule, sev in cfg["severity"].items():
        if sev not in SEVERITIES:
            raise ConfigError(f"severity for {rule} must be one of {', '.join(SEVERITIES)}")
    if known_rules is not None:
        bad = [r for r in list(cfg["disable"]) + list(cfg["severity"]) if r not in known_rules]
        if bad:
            raise ConfigError(f"unknown rule id(s): {', '.join(sorted(set(bad)))}")
    return cfg


def make_config(overrides: dict | None = None, known_rules: set[str] | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if overrides:
        if not isinstance(overrides, dict):
            raise ConfigError("config must be a JSON object")
        unknown = set(overrides) - set(DEFAULT_CONFIG)
        if unknown:
            raise ConfigError(f"unknown config key(s): {', '.join(sorted(unknown))}")
        cfg.update(copy.deepcopy(overrides))
    return validate_config(cfg, known_rules)


def load_config(path: str | Path, known_rules: set[str] | None = None) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: invalid JSON: {exc.msg} (line {exc.lineno})") from None
    return make_config(data, known_rules)
