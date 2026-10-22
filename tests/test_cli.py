import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from transcript_qa.cli import main
from transcript_qa.config import ConfigError, load_config, make_config
from transcript_qa.linter import KNOWN_RULE_IDS, lint_file

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"
SAMPLES = ["en_interview.txt", "en_clean.txt", "hi_podcast.txt", "mr_news.json", "ta_call.txt"]


def test_clean_example_passes(capsys):
    assert main(["check", str(EX / "en_clean.txt"), "--config", str(EX / "rules.json")]) == 0
    assert "0 error(s), 0 warning(s)" in capsys.readouterr().out


def test_examples_report_expected_rules(capsys):
    files = [str(EX / f) for f in SAMPLES]
    assert main(["check", *files, "--config", str(EX / "rules.json"), "--format", "json"]) == 1
    data = json.loads(capsys.readouterr().out)
    rules = {i["rule"] for i in data["issues"]}
    assert {"TS001", "TS002", "TAG001", "BR001", "WS001", "WS002", "SCR001",
            "SEG001", "SPK001", "NUM001"} <= rules
    assert data["summary"]["files"] == 5
    assert data["summary"]["errors"] > 0
    assert not any(i["file"].endswith("en_clean.txt") for i in data["issues"])


def test_each_sample_language_has_issues():
    cfg = load_config(EX / "rules.json", KNOWN_RULE_IDS)
    for name in SAMPLES:
        issues = lint_file(EX / name, cfg)
        assert bool(issues) == (name != "en_clean.txt"), name


def test_fail_on_levels(capsys, tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("A: hello  world\n", encoding="utf-8")  # warning only
    assert main(["check", str(f)]) == 0
    assert main(["check", str(f), "--fail-on", "warning"]) == 1
    capsys.readouterr()


def test_bad_config_and_missing_file_exit_2(capsys, tmp_path):
    cfg = tmp_path / "rules.json"
    cfg.write_text('{"numerals": "roman"}', encoding="utf-8")
    assert main(["check", str(EX / "en_clean.txt"), "--config", str(cfg)]) == 2
    assert main(["check", str(tmp_path / "missing.txt")]) == 2
    err = capsys.readouterr().err
    assert "numerals" in err and "cannot read" in err


def test_config_validation():
    with pytest.raises(ConfigError, match="unknown config key"):
        make_config({"allowed_tag": []})
    with pytest.raises(ConfigError, match="unknown rule"):
        make_config({"disable": ["XX999"]}, KNOWN_RULE_IDS)
    with pytest.raises(ConfigError, match="severity"):
        make_config({"severity": {"WS001": "fatal"}})


def test_invalid_json_transcript_is_reported(tmp_path, capsys):
    f = tmp_path / "broken.json"
    f.write_text('{"segments": [', encoding="utf-8")
    assert main(["check", str(f)]) == 1
    assert "PARSE001" in capsys.readouterr().out


def test_rules_command_lists_rules(capsys):
    assert main(["rules"]) == 0
    out = capsys.readouterr().out
    assert "TS001" in out and "SCR001" in out


def test_console_script_module_runs():
    proc = subprocess.run(
        [sys.executable, "-m", "transcript_qa", "check", str(EX / "hi_podcast.txt"),
         "--config", str(EX / "rules.json")],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    assert proc.returncode == 1
    assert "SPK001" in proc.stdout and "SCR001" in proc.stdout
