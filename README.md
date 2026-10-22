# transcript-qa-linter

> A CI-friendly QA linter for verbatim transcription and translation deliverables in English, Hindi, Marathi and Tamil.

[![CI](https://github.com/ansariadeel-hue/transcript-qa-linter/actions/workflows/ci.yml/badge.svg)](https://github.com/ansariadeel-hue/transcript-qa-linter/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)

## Why

Verbatim transcription projects come with long style guides: timestamps in a
fixed format, a closed set of notation tags (`[inaudible]`, `[crosstalk]`, …),
consistent speaker labels, a numeral convention, no stray whitespace. Many
review rejections come from mechanical mistakes rather than from what was
heard: a `[inaudable]` typo, a timestamp that jumps backwards, `Speaker 2`
vs `speaker_2`, Latin words that slipped into a Devanagari segment, or
`२०२३` in a file that otherwise uses `2023`.

These checks are cheap to automate. `transcript-qa` runs them on every file,
reports each problem with a rule id, severity and line/column, and exits
non-zero on errors so it can gate a delivery folder in CI or a pre-submit
script — leaving human reviewers to focus on what was actually said.

## Features

| id | name | default | checks |
|---|---|---|---|
| TS001 | malformed-timestamp | error | Timestamp is not [HH:MM:SS.mmm] or has out-of-range fields. |
| TS002 | non-monotonic-timestamp | error | Timestamp is earlier than the previous segment's. |
| TS003 | missing-timestamp | warning | Segment lacks a timestamp although other segments have one. |
| TAG001 | unknown-tag | error | Notation tag not in the allowed set (suggests the closest allowed tag). |
| BR001 | unbalanced-brackets | error | Unmatched or unclosed (), [] or {}. |
| WS001 | double-space | warning | Two or more consecutive spaces inside a line. |
| WS002 | trailing-whitespace | warning | Whitespace at the end of a line (or around JSON segment text). |
| SEG001 | empty-segment | error | Segment has a timestamp/speaker but no text. |
| SCR001 | script-mixing | warning | Word in an unexpected script for the language/segment (allowlist aware). |
| SPK001 | inconsistent-speaker | warning | Speaker label spelled/cased differently from an earlier label. |
| SPK002 | unknown-speaker | error | Speaker label not in the configured 'speakers' list. |
| SPK003 | missing-speaker | warning | Segment lacks a speaker label although other segments have one. |
| NUM001 | numeral-style | warning | Digits violate the configured numeral style (consistent/ascii/native). |
| PARSE001 | parse-error | error | File could not be parsed (e.g. invalid JSON). |

- Scripts are detected with **Unicode block ranges** (Latin, Devanagari, Tamil,
  Arabic/Urdu); words are runs of letters *and combining marks*, so matras,
  viramas and nukta stay inside a word and ZWJ/ZWNJ are allowed.
- **Allowlist** for legitimate code-mixed words (`WhatsApp`, `episode`, …).
- **Numeral styles**: `consistent` (flag the minority digit style in a file),
  `ascii`, `native` (Devanagari `०-९` / Tamil `௦-௯`), or `off`. Digits inside
  timestamps and tags are ignored.
- Close-match suggestions for misspelled tags and speakers (`difflib`).
- Plain-text and JSON transcripts; text or JSON output; per-rule severity
  overrides and disabling; `--fail-on` threshold for CI.
- Pure Python standard library at runtime.

## Install

```bash
pip install git+https://github.com/ansariadeel-hue/transcript-qa-linter
```

## Quickstart

The `examples/` folder contains short transcripts in four languages, with
deliberate problems in all but `en_clean.txt`:

```bash
transcript-qa check examples/en_interview.txt examples/en_clean.txt \
    examples/hi_podcast.txt examples/mr_news.json examples/ta_call.txt \
    --config examples/rules.json
```

```text
examples/en_interview.txt:5:62: error BR001 unclosed '('
examples/en_interview.txt:6:72: warning WS001 2 consecutive spaces
examples/en_interview.txt:6:79: error TAG001 unknown notation tag [inaudable] (did you mean [inaudible]?)
examples/en_interview.txt:7:1: error TS002 timestamp 00:00:13.900 goes backwards (previous 00:00:15.400 at line 6)
examples/en_interview.txt:7:16: warning SPK001 speaker label 'Interviwer' looks like a misspelling of 'Interviewer' (first used at line 3)
examples/en_interview.txt:8:1: error TS001 malformed timestamp '0:00:21.5' (expected HH:MM:SS.mmm, e.g. 00:01:23.450)
examples/en_interview.txt:9:28: warning WS002 trailing whitespace
examples/en_interview.txt:9:29: error SEG001 empty segment (no text after speaker label)
examples/hi_podcast.txt:5:16: warning SPK001 speaker label 'speaker_2' is written differently from 'Speaker 2' (first used at line 4)
examples/hi_podcast.txt:6:42: warning SCR001 Latin word 'actually' in Devanagari transcript
examples/hi_podcast.txt:6:60: warning SCR001 Latin word 'news' in Devanagari transcript
examples/hi_podcast.txt:7:35: warning NUM001 devanagari numeral '२०२३': inconsistent with the file's ascii digits (1 of 2 numbers use ascii)
examples/hi_podcast.txt:7:61: error BR001 unclosed '['
examples/hi_podcast.txt:7:62: warning SCR001 Latin word 'noise' in Devanagari transcript
examples/hi_podcast.txt:8:74: warning WS002 trailing whitespace
examples/mr_news.json:seg 3:18: warning WS001 2 consecutive spaces
examples/mr_news.json:seg 4: error SEG001 empty segment (no text after speaker label)
examples/mr_news.json:seg 4: error TS002 timestamp 00:00:08.000 goes backwards (previous 00:00:09.250 at segment 3)
examples/mr_news.json:seg 5:22: warning SCR001 Latin word 'traffic' in Devanagari transcript
examples/mr_news.json:seg 5:41: error TAG001 unknown notation tag [musik] (did you mean [music]?)
examples/ta_call.txt:4:30: warning SCR001 word 'orderஐ' mixes scripts (Latin, Tamil)
examples/ta_call.txt:6:46: warning NUM001 tamil numeral '௪௫௭௩': inconsistent with the file's ascii digits (1 of 2 numbers use ascii)
examples/ta_call.txt:7:53: error BR001 unmatched closing ')'
examples/ta_call.txt:8:1: error TS001 malformed timestamp '00:00:61.000' (expected HH:MM:SS.mmm, e.g. 00:01:23.450)

5 file(s) checked: 11 error(s), 13 warning(s), 0 info  [BR001x3, NUM001x2, SCR001x5, SEG001x2, SPK001x2, TAG001x2, TS001x2, TS002x2, WS001x2, WS002x2]
```

Exit code: `1` (errors were found). On the clean file:

```bash
transcript-qa check examples/en_clean.txt --config examples/rules.json
```

```text
1 file(s) checked: 0 error(s), 0 warning(s), 0 info
```

Exit code: `0`.

Notes on the output:

- Locations are `file:line:col` for text files and `file:seg N:col` for JSON
  segments; columns are 1-based Unicode code points.
- `hi_podcast.txt:7` shows how one mistake can cascade: the unclosed `[noise`
  is reported as `BR001`, and because it is no longer a tag, `noise` is also
  reported as a Latin word.
- `order` is in the example allowlist, so `ta_call.txt:5` is not flagged, but
  `orderஐ` (Latin stem + Tamil case suffix) on line 4 is.

Other commands:

```bash
transcript-qa check examples/*.txt --format json        # machine-readable
transcript-qa check file.txt --lang hi --fail-on warning # stricter CI gate
transcript-qa rules                                      # list rules
```

Exit codes: `0` no failing issues, `1` issues at or above `--fail-on`
(default `error`), `2` usage/config/I-O error.

## Configuration

`--config rules.json` is merged over the defaults; unknown keys and unknown
rule ids are rejected.

```json
{
  "allowed_tags": [
    "inaudible",
    "crosstalk",
    "laughter",
    "noise",
    "music",
    "pause"
  ],
  "script_allowlist": [
    "OK",
    "episode",
    "order",
    "WhatsApp"
  ],
  "numerals": "consistent",
  "disable": [],
  "severity": {
    "SPK003": "info"
  }
}
```

| key | default | meaning |
|---|---|---|
| `allowed_tags` | inaudible, crosstalk, laughter, noise, music, pause, cough, applause, silence, foreign | Allowed `[tag]` names. `[inaudible 00:01:02]` and `[foreign: Urdu]` are matched by name. |
| `tag_case_sensitive` | `false` | Whether `[Laughter]` must match case exactly. |
| `speakers` | `[]` | If non-empty, the only valid speaker labels (enables `SPK002`). |
| `script_allowlist` | `[]` | Words allowed in another script (case-insensitive). |
| `numerals` | `"consistent"` | `consistent`, `ascii`, `native` or `off`. |
| `language` | `null` | Fallback language (`en`, `hi`, `mr`, `ta`, `ur`). |
| `disable` | `[]` | Rule ids to skip. |
| `severity` | `{}` | Per-rule override: `error`, `warning` or `info`. |

Language precedence: `--lang` > the file's own declaration > config `language`.
With no language, the script-mixing rule uses each segment's majority script.

## Data format

**Plain text** — one segment per line; blank lines are ignored and `#` lines
are comments (`# lang: hi` declares the language):

```text
# lang: hi
[00:00:00.500] Speaker 1: नमस्ते, आज हम मौसम के बारे में बात करेंगे।
[00:00:03.200] Speaker 2: जी हाँ, इस साल बारिश बहुत ज़्यादा हुई। [laughter]
```

- Optional leading timestamp `[HH:MM:SS.mmm]` (a leading bracket containing only
  digits and `:.,` is treated as a timestamp and validated).
- Optional speaker label `Name:` right after it (1–3 words, no sentence punctuation).

**JSON** — an object with `language` and `segments`, or a bare list of segments:

```json
{
  "language": "mr",
  "segments": [
    {"start": "00:00:01.000", "speaker": "Anchor", "text": "नमस्कार, आजच्या बातम्यांमध्ये आपले स्वागत आहे."}
  ]
}
```

## Python API

```python
from transcript_qa import lint_text, make_config

cfg = make_config({"script_allowlist": ["WhatsApp"]})
for issue in lint_text("A: मैंने WhatsApp पर message भेजा\n", cfg, language="hi"):
    print(issue.rule, issue.col, issue.message)
# SCR001 22 Latin word 'message' in Devanagari transcript
```

## Project structure

```
transcript-qa-linter/
├── src/transcript_qa/
│   ├── parser.py    # text/JSON transcript parsing, timestamp validation
│   ├── scripts.py   # Unicode script + digit classification
│   ├── rules.py     # all lint rules (id, severity, check function)
│   ├── config.py    # defaults, JSON loading, validation
│   ├── linter.py    # runs rules, applies severity overrides
│   └── cli.py       # `transcript-qa check|rules`
├── tests/           # pytest suite
├── examples/        # en/hi/mr/ta sample transcripts + rules.json
└── .github/workflows/ci.yml
```

Run the tests with `python -m pytest -q` from the project root.

## License

MIT — see [LICENSE](LICENSE).
