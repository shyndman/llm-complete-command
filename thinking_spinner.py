import sys
import threading
import time

from yaspin import yaspin


SPINNER_REFRESH_SECONDS = 0.1


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
        return f"thinking | {elapsed_seconds:.1f}s | {self._model_name}"

    def _update_text_loop(self) -> None:
        while not self._stop_event.wait(SPINNER_REFRESH_SECONDS):
            if self._spinner is None:
                return
            self._spinner.text = self._status_text()
