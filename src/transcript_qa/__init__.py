"""transcript-qa-linter: QA checks for verbatim transcription deliverables."""

__version__ = "0.1.0"

from .config import ConfigError, load_config, make_config  # noqa: E402
from .linter import lint_file, lint_json, lint_text, lint_transcript  # noqa: E402
from .model import Issue, Segment, Transcript  # noqa: E402
from .parser import parse_json, parse_text  # noqa: E402
from .rules import RULES  # noqa: E402

__all__ = [
    "ConfigError",
    "Issue",
    "RULES",
    "Segment",
    "Transcript",
    "lint_file",
    "lint_json",
    "lint_text",
    "lint_transcript",
    "load_config",
    "make_config",
    "parse_json",
    "parse_text",
    "__version__",
]
