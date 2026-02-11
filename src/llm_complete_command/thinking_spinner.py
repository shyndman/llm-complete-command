import sys
import threading
import time

from yaspin import yaspin


SPINNER_REFRESH_SECONDS = 0.1
ELAPSED_TIME_FIELD_WIDTH = 5
ELAPSED_COLOR_TRANSITION_SECONDS = 45.0
ELAPSED_COLOR_START_RGB = (255, 255, 255)
ELAPSED_COLOR_END_RGB = (235, 38, 38)
ANSI_RESET = "\x1b[0m"


def _clamp(value: float, lower_bound: float, upper_bound: float) -> float:
    return max(lower_bound, min(value, upper_bound))


def _interpolate_channel(start: int, end: int, progress: float) -> int:
    return int(start + (end - start) * progress)


def _elapsed_color_escape(elapsed_seconds: float) -> str:
    progress = _clamp(elapsed_seconds / ELAPSED_COLOR_TRANSITION_SECONDS, 0.0, 1.0)
    red = _interpolate_channel(
        ELAPSED_COLOR_START_RGB[0], ELAPSED_COLOR_END_RGB[0], progress
    )
    green = _interpolate_channel(
        ELAPSED_COLOR_START_RGB[1], ELAPSED_COLOR_END_RGB[1], progress
    )
    blue = _interpolate_channel(
        ELAPSED_COLOR_START_RGB[2], ELAPSED_COLOR_END_RGB[2], progress
    )
    return f"\x1b[38;2;{red};{green};{blue}m"


class ThinkingSpinner:
    def __init__(self, model_name: str):
        self._model_name = model_name
        self._spinner = None
        self._started_at = 0.0
        self._stop_event = threading.Event()
        self._updater_thread = None

    def start(self) -> None:
        if self._spinner is not None or not sys.stderr.isatty():
            return

        self._started_at = time.monotonic()
        self._spinner = yaspin(text=self._status_text(), stream=sys.stderr)
        self._spinner.start()

        self._updater_thread = threading.Thread(
            target=self._update_text_loop,
            daemon=True,
        )
        self._updater_thread.start()

    def stop(self) -> None:
        if self._spinner is None:
            return

        self._stop_event.set()
        if self._updater_thread is not None:
            self._updater_thread.join(timeout=0.2)

        self._spinner.stop()
        self._spinner = None

    def _status_text(self) -> str:
        elapsed_seconds = time.monotonic() - self._started_at
        elapsed_text = f"{elapsed_seconds:.1f}s".rjust(ELAPSED_TIME_FIELD_WIDTH)
        elapsed_color = _elapsed_color_escape(elapsed_seconds)
        return (
            f"thinking | {elapsed_color}{elapsed_text}{ANSI_RESET} | {self._model_name}"
        )

    def _update_text_loop(self) -> None:
        while not self._stop_event.wait(SPINNER_REFRESH_SECONDS):
            if self._spinner is None:
                return
            self._spinner.text = self._status_text()
