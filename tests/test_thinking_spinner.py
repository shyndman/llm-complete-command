import llm_complete_command.thinking_spinner as thinking_spinner


def test_status_text_right_aligns_single_digit_elapsed_time(monkeypatch):
    spinner = thinking_spinner.ThinkingSpinner("test-model")
    spinner._started_at = 100.0
    monkeypatch.setattr(thinking_spinner.time, "monotonic", lambda: 101.5)

    assert spinner._status_text() == "thinking |  1.5s | test-model"


def test_status_text_keeps_two_digit_elapsed_time_stable(monkeypatch):
    spinner = thinking_spinner.ThinkingSpinner("test-model")
    spinner._started_at = 100.0
    monkeypatch.setattr(thinking_spinner.time, "monotonic", lambda: 125.6)

    assert spinner._status_text() == "thinking | 25.6s | test-model"
