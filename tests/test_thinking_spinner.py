import re

import llm_complete_command.thinking_spinner as thinking_spinner


ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_PATTERN.sub("", text)


def test_elapsed_color_escape_starts_white_and_ends_red():
    assert thinking_spinner._elapsed_color_escape(0.0) == "\x1b[38;2;255;255;255m"
    assert (
        thinking_spinner._elapsed_color_escape(
            thinking_spinner.ELAPSED_COLOR_TRANSITION_SECONDS
        )
        == "\x1b[38;2;235;38;38m"
    )


def test_elapsed_color_escape_clamps_at_end_color_after_transition_window():
    assert thinking_spinner._elapsed_color_escape(10_000.0) == "\x1b[38;2;235;38;38m"


def test_status_text_right_aligns_single_digit_elapsed_time(monkeypatch):
    spinner = thinking_spinner.ThinkingSpinner("test-model")
    spinner._started_at = 100.0
    monkeypatch.setattr(thinking_spinner.time, "monotonic", lambda: 101.5)

    status_text = spinner._status_text()

    assert "\x1b[38;2;254;247;247m" in status_text
    assert _strip_ansi(status_text) == "thinking |  1.5s | test-model"


def test_status_text_keeps_two_digit_elapsed_time_stable(monkeypatch):
    spinner = thinking_spinner.ThinkingSpinner("test-model")
    spinner._started_at = 100.0
    monkeypatch.setattr(thinking_spinner.time, "monotonic", lambda: 125.6)

    status_text = spinner._status_text()

    assert "\x1b[38;2;243;131;131m" in status_text
    assert _strip_ansi(status_text) == "thinking | 25.6s | test-model"
