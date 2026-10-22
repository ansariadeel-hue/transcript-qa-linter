import pytest

from transcript_qa import lint_json, lint_text, make_config
from transcript_qa.parser import parse_text, parse_timestamp


def rules_of(issues):
    return [i.rule for i in issues]


def only(issues, rule):
    return [i for i in issues if i.rule == rule]


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

def test_parse_timestamp_reference_values():
    assert parse_timestamp("00:01:23.450") == pytest.approx(83.45)
    assert parse_timestamp("01:00:00.000") == 3600
    for bad in ("0:01:23.450", "00:01:23,450", "00:61:00.000", "00:00:60.000", "00:00:01.5", "abc"):
        assert parse_timestamp(bad) is None


def test_parser_extracts_timestamp_speaker_and_text():
    tr = parse_text("# lang: hi\n\n[00:00:01.000] Speaker 1: नमस्ते दुनिया\nplain line\n")
    assert tr.language == "hi"
    first, second = tr.segments
    assert first.timestamp == 1.0 and first.speaker == "Speaker 1"
    assert first.text == "नमस्ते दुनिया" and first.text_col == 27
    assert first.line == 3
    assert second.speaker is None and second.timestamp_raw is None and second.text == "plain line"


def test_sentence_with_colon_is_not_a_speaker():
    tr = parse_text("He said, honestly: no\n")
    assert tr.segments[0].speaker is None


# --------------------------------------------------------------------------
# Timestamps
# --------------------------------------------------------------------------

def test_malformed_and_non_monotonic_timestamps():
    text = (
        "[00:00:05.000] A: one\n"
        "[00:00:03.000] A: two\n"
        "[00:00:4.00] A: three\n"
        "[00:00:06.000] A: four\n"
    )
    issues = lint_text(text)
    ts1 = only(issues, "TS001")
    ts2 = only(issues, "TS002")
    assert [(i.line, i.col) for i in ts1] == [(3, 1)]
    assert [i.line for i in ts2] == [2]
    assert "00:00:03.000" in ts2[0].message and "00:00:05.000" in ts2[0].message
    assert all(i.severity == "error" for i in ts1 + ts2)


def test_equal_timestamps_are_monotonic():
    assert not only(lint_text("[00:00:01.000] A: x\n[00:00:01.000] B: y\n"), "TS002")


def test_missing_timestamp_when_others_have_one():
    issues = lint_text("[00:00:01.000] A: x\nB: y\n")
    assert [(i.rule, i.line) for i in only(issues, "TS003")] == [("TS003", 2)]


# --------------------------------------------------------------------------
# Tags and brackets
# --------------------------------------------------------------------------

def test_unknown_tag_with_suggestion_and_case_insensitivity():
    issues = lint_text("A: hello [inaudable] there [Laughter] [crosstalk 00:01:02]\n")
    tags = only(issues, "TAG001")
    assert len(tags) == 1
    assert "did you mean [inaudible]" in tags[0].message
    assert tags[0].col == 10


def test_configurable_allowed_tags():
    cfg = make_config({"allowed_tags": ["unclear"], "tag_case_sensitive": True})
    issues = lint_text("A: [unclear] [Unclear] [inaudible]\n", cfg)
    assert len(only(issues, "TAG001")) == 2


def test_unbalanced_brackets():
    issues = only(lint_text("A: (one [two) three]\nB: four)\nC: {five\n"), "BR001")
    messages = [(i.line, i.message) for i in issues]
    assert (2, "unmatched closing ')'") in messages
    assert (3, "unclosed '{'") in messages
    assert any(line == 1 for line, _ in messages)


# --------------------------------------------------------------------------
# Whitespace and empty segments
# --------------------------------------------------------------------------

def test_double_space_and_trailing_whitespace():
    issues = lint_text("A: one  two\t \nB: fine\n")
    assert [(i.rule, i.col) for i in only(issues, "WS001")] == [("WS001", 7)]
    assert [(i.rule, i.col) for i in only(issues, "WS002")] == [("WS002", 12)]


def test_empty_segment_but_tag_only_is_fine():
    issues = lint_text("[00:00:01.000] A:\n[00:00:02.000] B: [inaudible]\n[00:00:03.000]\n")
    assert [i.line for i in only(issues, "SEG001")] == [1, 3]


# --------------------------------------------------------------------------
# Script mixing
# --------------------------------------------------------------------------

def test_latin_inside_devanagari_with_allowlist():
    cfg = make_config({"script_allowlist": ["WhatsApp"]})
    issues = lint_text("A: मैंने WhatsApp पर message भेजा [laughter]\n", cfg, language="hi")
    scr = only(issues, "SCR001")
    assert len(scr) == 1
    assert "'message'" in scr[0].message and "Devanagari" in scr[0].message


def test_devanagari_inside_english_and_mixed_word_tamil():
    en = only(lint_text("A: we said नमस्ते to everyone\n", language="en"), "SCR001")
    assert len(en) == 1 and "नमस्ते" in en[0].message
    ta = only(lint_text("A: என் orderஐ காணவில்லை\n", language="ta"), "SCR001")
    assert len(ta) == 1 and "mixes scripts" in ta[0].message


def test_script_mixing_without_language_uses_segment_majority():
    issues = only(lint_text("A: यह बहुत अच्छा है okay\nB: this is fine\n"), "SCR001")
    assert [(i.line, "okay" in i.message) for i in issues] == [(1, True)]


def test_marathi_with_matras_and_nukta_is_not_flagged():
    text = "A: पुण्यात आज ज़ोरदार पाऊस झाला, क्षमस्व।\n"
    assert not only(lint_text(text, language="mr"), "SCR001")


# --------------------------------------------------------------------------
# Speakers
# --------------------------------------------------------------------------

def test_inconsistent_speaker_labels():
    text = (
        "Speaker 1: a\nSpeaker 2: b\nSPEAKER 1: c\nInterviewer: d\n"
        "Interviewer: e\nInterviwer: f\nSpeaker 1: g\n"
    )
    spk = only(lint_text(text), "SPK001")
    assert [i.line for i in spk] == [3, 6]
    assert "'Speaker 1'" in spk[0].message
    assert "misspelling of 'Interviewer'" in spk[1].message


def test_numbered_speakers_are_not_misspellings():
    assert not only(lint_text("Speaker 1: a\nSpeaker 2: b\nSpeaker 3: c\n"), "SPK001")


def test_unknown_and_missing_speaker():
    cfg = make_config({"speakers": ["Agent", "Customer"]})
    issues = lint_text("Agent: hi\nCustomr: hello\nno label here\n", cfg)
    spk2 = only(issues, "SPK002")
    assert len(spk2) == 1 and "did you mean 'Customer'" in spk2[0].message
    assert [i.line for i in only(issues, "SPK003")] == [3]


# --------------------------------------------------------------------------
# Numerals
# --------------------------------------------------------------------------

def test_numerals_consistent_flags_minority_style():
    issues = only(lint_text("A: 250 और 30 और २०२३\n", language="hi"), "NUM001")
    assert len(issues) == 1 and "२०२३" in issues[0].message


@pytest.mark.parametrize(
    "mode,expected",
    [("ascii", ["२०"]), ("native", ["15"]), ("off", [])],
)
def test_numeral_modes(mode, expected):
    cfg = make_config({"numerals": mode})
    issues = only(lint_text("A: १५ और 15 और २०\n", cfg, language="hi"), "NUM001")
    flagged = [i.message.split("'")[1] for i in issues]
    if mode == "ascii":
        assert flagged == ["१५", "२०"]
    else:
        assert flagged == expected


def test_numerals_in_tags_and_timestamps_ignored():
    text = "[00:00:01.000] A: १२ [inaudible 00:00:02]\n"
    assert not only(lint_text(text, language="hi"), "NUM001")


# --------------------------------------------------------------------------
# JSON transcripts and configuration
# --------------------------------------------------------------------------

def test_json_transcript_rules_use_segment_numbers():
    content = (
        '{"language": "mr", "segments": ['
        '{"start": "00:00:02.000", "speaker": "A", "text": "नमस्कार  मंडळी "},'
        '{"start": "00:00:01.000", "speaker": "A", "text": ""}]}'
    )
    issues = lint_json(content)
    got = {(i.rule, i.line) for i in issues}
    assert {("WS001", 1), ("WS002", 1), ("TS002", 2), ("SEG001", 2)} <= got
    assert all(i.unit == "segment" for i in issues)


def test_disable_and_severity_override():
    cfg = make_config({"disable": ["WS002"], "severity": {"TAG001": "warning"}})
    issues = lint_text("A: x [foo] \n", cfg)
    assert not only(issues, "WS002")
    assert only(issues, "TAG001")[0].severity == "warning"
