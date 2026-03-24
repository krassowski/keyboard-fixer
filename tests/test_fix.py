import pytest

import evdev_fix
import fix


@pytest.fixture
def mock_suggestions(monkeypatch):
    suggestions = {
        "thi": ["Thai", "this"],
        "tet": ["TET", "test"],
        "cae": ["Case", "case"],
        "ok": ["OK", "OKs", "okay"],
        "ee": ["EEO", "ESE", "see"],
        "otor": ["motor"],
        "let's": None,
    }

    def fake_get_suggestions(word):
        return suggestions.get(word, None)

    monkeypatch.setattr(fix, "get_suggestions", fake_get_suggestions)
    return suggestions


def test_fix_line_handles_standalone_i_and_missing_s(mock_suggestions):
    assert fix.fix_line("thi i a tet") == "this is a test"


def test_fix_plural_after_number(mock_suggestions):
    assert fix.fix_line("2 cat") == "2 cats"
    assert fix.fix_line("100 file") == "100 files"
    assert fix.fix_line("1 cat") == "1 cat"  # singular — no change


def test_fix_plural_after_quantifier(mock_suggestions):
    assert fix.fix_line("many book") == "many books"
    assert fix.fix_line("several option") == "several options"
    assert fix.fix_line("these cat") == "these cats"


def test_fix_plural_not_applied_without_context(mock_suggestions):
    assert fix.fix_line("the cat") == "the cat"  # no plural indicator
    assert fix.fix_line("a file") == "a file"


def test_fix_plural_not_applied_for_custom_broken_letter(mock_suggestions):
    assert fix.fix_line("many book", broken_letter="m") == "many book"  # rule inactive


def test_fix_line_pronoun_till_becomes_still():
    assert fix.fix_line("I till love it") == "I still love it"
    assert fix.fix_line("she till") == "she still"
    assert fix.fix_line("we till need") == "we still need"
    assert fix.fix_line("till then") == "till then"  # no pronoun before — keep as-is


def test_fix_line_promotes_sentence_start_i_to_capital_i(mock_suggestions):
    assert fix.fix_line("i am here") == "I am here"
    assert fix.fix_line("then i went home") == "then I went home"


def test_fix_line_handles_lets_contraction(mock_suggestions):
    assert fix.fix_line("let' go") == "let's go"


def test_fix_line_prefers_lowercase_candidates_and_skips_acronyms(mock_suggestions):
    assert fix.fix_line("cae ok ee") == "case ok see"


def test_fix_line_supports_custom_broken_letter(mock_suggestions):
    assert fix.fix_line("otor oil", broken_letter="m") == "motor oil"


def test_fix_parse_args_accepts_custom_broken_letter():
    args = fix.parse_args(["--broken-letter", "m", "otor", "oil"])
    assert args.broken_letter == "m"
    assert args.text == ["otor", "oil"]


def test_evdev_parse_args_accepts_custom_broken_letter():
    args = evdev_fix.parse_args(["--broken-letter", "m", "/dev/input/event20"])
    assert args.broken_letter == "m"
    assert args.idle_seconds == 1.0
    assert args.device == "/dev/input/event20"


def test_evdev_resolve_word_uses_shared_fix_logic(mock_suggestions):
    assert evdev_fix.LiveKeyboardFixer.resolve_word("otor", False, None, broken_letter="m") == "motor"
