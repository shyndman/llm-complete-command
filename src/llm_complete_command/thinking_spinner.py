import os
import re
import select
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
TEXT_SIZING_SCALE_NUMERATOR = 7
TEXT_SIZING_SCALE_DENOMINATOR = 8
TEXT_SIZING_DETECTION_TIMEOUT_SECONDS = 0.1
CPR_QUERY = "\x1b[6n"
OSC_TERMINATOR = "\x07"
CPR_RESPONSE_PATTERN = re.compile(rb"\x1b\[(\d+);(\d+)R")
STATUS_SEPARATOR = " · "

_text_sizing_scale_support_cache: bool | None = None


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


def _osc66_fractional_scale(text: str) -> str:
    return (
        f"\x1b]66;n={TEXT_SIZING_SCALE_NUMERATOR}:d={TEXT_SIZING_SCALE_DENOMINATOR};"
        f"{text}{OSC_TERMINATOR}"
    )


def _read_cpr_positions(fd: int, expected_responses: int) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    buffer = b""
    deadline = time.monotonic() + TEXT_SIZING_DETECTION_TIMEOUT_SECONDS

    while len(positions) < expected_responses:
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            break

        readable, _, _ = select.select([fd], [], [], remaining_seconds)
        if not readable:
            break

        try:
            chunk = os.read(fd, 1024)
        except OSError:
            break

        if not chunk:
            break

        buffer += chunk

        while len(positions) < expected_responses:
            match = CPR_RESPONSE_PATTERN.search(buffer)
            if match is None:
                break
            row = int(match.group(1))
            column = int(match.group(2))
            positions.append((row, column))
            buffer = buffer[match.end() :]

    return positions


def _cpr_positions_support_scale(positions: list[tuple[int, int]]) -> bool:
    if len(positions) < 3:
        return False

    first_column = positions[0][1]
    second_column = positions[1][1]
    third_column = positions[2][1]
    width_supported = second_column - first_column == 2
    scale_supported = third_column - second_column == 2
    return width_supported and scale_supported


def _detect_text_sizing_scale_support() -> bool:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        return False

    try:
        tty_fd = os.open("/dev/tty", os.O_RDWR)
    except OSError:
        return False

    probe = (
        f"{CPR_QUERY}"
        f"\x1b]66;w=2; {OSC_TERMINATOR}{CPR_QUERY}"
        f"\x1b]66;s=2; {OSC_TERMINATOR}{CPR_QUERY}"
    ).encode("ascii")

    try:
        os.write(tty_fd, probe)
        positions = _read_cpr_positions(tty_fd, expected_responses=3)
        return _cpr_positions_support_scale(positions)
    except OSError:
        return False
    finally:
        os.close(tty_fd)


def _supports_fractional_text_sizing() -> bool:
    global _text_sizing_scale_support_cache
    if _text_sizing_scale_support_cache is None:
        _text_sizing_scale_support_cache = _detect_text_sizing_scale_support()
    return _text_sizing_scale_support_cache


class ThinkingSpinner:
    def __init__(self, model_name: str):
        self._model_name = model_name
        self._spinner = None
        self._started_at = 0.0
        self._stop_event = threading.Event()
        self._updater_thread = None
        self._use_fractional_status_text = False

    def start(self) -> None:
        if self._spinner is not None or not sys.stderr.isatty():
            return

        self._started_at = time.monotonic()
        self._use_fractional_status_text = _supports_fractional_text_sizing()
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

        if not self._use_fractional_status_text:
            return (
                f"thinking{STATUS_SEPARATOR}{elapsed_color}{elapsed_text}{ANSI_RESET}"
                f"{STATUS_SEPARATOR}{self._model_name}"
            )

        return (
            f"{_osc66_fractional_scale(f'thinking{STATUS_SEPARATOR}')}"
            f"{elapsed_color}{_osc66_fractional_scale(elapsed_text)}{ANSI_RESET}"
            f"{_osc66_fractional_scale(f'{STATUS_SEPARATOR}{self._model_name}')}"
        )

    def _update_text_loop(self) -> None:
        while not self._stop_event.wait(SPINNER_REFRESH_SECONDS):
            if self._spinner is None:
                return
            self._spinner.text = self._status_text()
