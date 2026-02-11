import re

import llm_complete_command.thinking_spinner as thinking_spinner


ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;]*m")
OSC66_PATTERN = re.compile(r"\x1b]66;[^;]*;([^\x07]*)\x07")


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_PATTERN.sub("", text)


def _strip_control_sequences(text: str) -> str:
    without_osc66 = OSC66_PATTERN.sub(r"\1", text)
    return _strip_ansi(without_osc66)


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


def test_cpr_positions_support_scale_requires_width_and_scale_steps():
    assert thinking_spinner._cpr_positions_support_scale([(4, 1), (4, 3), (4, 5)])
    assert not thinking_spinner._cpr_positions_support_scale([(4, 1), (4, 1), (4, 1)])
    assert not thinking_spinner._cpr_positions_support_scale([(4, 1), (4, 3), (4, 4)])
    assert not thinking_spinner._cpr_positions_support_scale([(4, 1), (4, 3)])


def test_supports_fractional_text_sizing_caches_probe_result(monkeypatch):
    probe_calls = {"count": 0}

    def fake_detect() -> bool:
        probe_calls["count"] += 1
        return True

    monkeypatch.setattr(
        thinking_spinner, "_detect_text_sizing_scale_support", fake_detect
    )
    monkeypatch.setattr(thinking_spinner, "_text_sizing_scale_support_cache", None)

    assert thinking_spinner._supports_fractional_text_sizing()
    assert thinking_spinner._supports_fractional_text_sizing()
    assert probe_calls["count"] == 1


def test_start_enables_fractional_status_text_when_supported(monkeypatch):
    class FakeYaspin:
        def __init__(self, text, stream):
            self.text = text
            self.stream = stream

        def start(self):
            return None

        def stop(self):
            return None

    spinner = thinking_spinner.ThinkingSpinner("test-model")
    monkeypatch.setattr(thinking_spinner, "yaspin", FakeYaspin)
    monkeypatch.setattr(thinking_spinner.sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr(
        thinking_spinner, "_supports_fractional_text_sizing", lambda: True
    )

    spinner.start()

    assert spinner._use_fractional_status_text
    spinner.stop()


def test_status_text_scales_all_text_when_fractional_mode_enabled(monkeypatch):
    spinner = thinking_spinner.ThinkingSpinner("test-model")
    spinner._started_at = 100.0
    spinner._use_fractional_status_text = True
    monkeypatch.setattr(thinking_spinner.time, "monotonic", lambda: 101.5)

    status_text = spinner._status_text()

    assert "\x1b]66;n=9:d=10;thinking | \x07" in status_text
    assert "\x1b]66;n=9:d=10; 1.5s\x07" in status_text
    assert "\x1b]66;n=9:d=10; | test-model\x07" in status_text
    assert _strip_control_sequences(status_text) == "thinking |  1.5s | test-model"
