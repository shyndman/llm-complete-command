import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml
from platformdirs import user_config_dir


APP_NAME = "llm-complete-command"
UNKNOWN_VALUE = "unknown"
DETECTED_CONFIG_FILE_NAME = "config.detected.yaml"
OVERRIDE_CONFIG_FILE_NAME = "config.yaml"
DETECTED_AT_KEY = "detected_at"
ADDITIONAL_DETAILS_KEY = "additional_details"
ENVIRONMENT_PROBE_TTL_SECONDS = 7 * 24 * 60 * 60
PROBED_TOOLS = ("rg", "fd", "choose", "eza", "procs", "jq", "yq")
COMMAND_TIMEOUT_SECONDS = 2


def load_effective_environment() -> dict[str, Any]:
    detected_environment = _load_detected_environment()
    override_environment = _read_yaml_dict(_override_config_path())
    return _deep_merge_dicts(detected_environment, override_environment)


def _load_detected_environment() -> dict[str, Any]:
    detected_path = _detected_config_path()
    detected_environment = _read_yaml_dict(detected_path)

    if _is_fresh(detected_environment):
        return detected_environment

    refreshed_environment = _probe_environment()
    _write_yaml_dict(detected_path, refreshed_environment)
    return refreshed_environment


def _is_fresh(environment: dict[str, Any]) -> bool:
    detected_at = environment.get(DETECTED_AT_KEY)
    if not isinstance(detected_at, int):
        return False

    elapsed_seconds = int(time.time()) - detected_at
    return elapsed_seconds <= ENVIRONMENT_PROBE_TTL_SECONDS


def _probe_environment() -> dict[str, Any]:
    return {
        DETECTED_AT_KEY: int(time.time()),
        "os": _safe_probe(
            _probe_os,
            {"family": UNKNOWN_VALUE, "name": UNKNOWN_VALUE, "version": UNKNOWN_VALUE},
        ),
        "shell": _safe_probe(
            _probe_shell,
            {"name": UNKNOWN_VALUE, "path": UNKNOWN_VALUE, "version": UNKNOWN_VALUE},
        ),
        "terminal": _safe_probe(
            _probe_terminal,
            {"name": UNKNOWN_VALUE, "version": UNKNOWN_VALUE},
        ),
        "tools": _safe_probe(_probe_tools, {}),
        ADDITIONAL_DETAILS_KEY: {},
    }


def _probe_os() -> dict[str, str]:
    family = platform.system() or UNKNOWN_VALUE

    if family == "Linux":
        distro_name, distro_version = _probe_linux_distribution()
        return {"family": family, "name": distro_name, "version": distro_version}

    if family == "Darwin":
        macos_version = _command_version("sw_vers", ["-productVersion"])
        return {"family": family, "name": "macOS", "version": macos_version}

    return {
        "family": family,
        "name": family,
        "version": platform.release() or UNKNOWN_VALUE,
    }


def _probe_linux_distribution() -> tuple[str, str]:
    os_release_path = Path("/etc/os-release")
    if not os_release_path.exists():
        return "Linux", platform.release() or UNKNOWN_VALUE

    values: dict[str, str] = {}
    try:
        os_release_contents = os_release_path.read_text()
    except OSError:
        return "Linux", platform.release() or UNKNOWN_VALUE

    for line in os_release_contents.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')

    name = values.get("PRETTY_NAME") or values.get("NAME") or "Linux"
    version = values.get("VERSION_ID") or platform.release() or UNKNOWN_VALUE
    return name, version


def _probe_shell() -> dict[str, str]:
    shell_path = os.getenv("SHELL") or UNKNOWN_VALUE
    shell_name = (
        os.path.basename(shell_path) if shell_path != UNKNOWN_VALUE else UNKNOWN_VALUE
    )
    shell_version = UNKNOWN_VALUE

    if shell_path != UNKNOWN_VALUE:
        shell_version = _command_version(shell_path, ["--version"])

    return {
        "name": shell_name,
        "path": shell_path,
        "version": shell_version,
    }


def _probe_terminal() -> dict[str, str]:
    terminal_name = _detect_terminal_name()
    terminal_version = os.getenv("TERM_PROGRAM_VERSION") or UNKNOWN_VALUE

    if terminal_version == UNKNOWN_VALUE and shutil.which(terminal_name):
        terminal_version = _command_version(terminal_name, ["--version"])

    return {"name": terminal_name, "version": terminal_version}


def _detect_terminal_name() -> str:
    term_program = os.getenv("TERM_PROGRAM")
    if term_program:
        return term_program

    if os.getenv("KITTY_PID"):
        return "kitty"
    if os.getenv("WEZTERM_PANE"):
        return "wezterm"
    if os.getenv("ALACRITTY_SOCKET"):
        return "alacritty"

    return os.getenv("TERM") or UNKNOWN_VALUE


def _probe_tools() -> dict[str, dict[str, str | bool]]:
    tools: dict[str, dict[str, str | bool]] = {}
    for tool_name in PROBED_TOOLS:
        tool_path = shutil.which(tool_name)
        available = tool_path is not None
        version = (
            _command_version(tool_name, ["--version"]) if available else UNKNOWN_VALUE
        )

        tools[tool_name] = {
            "available": available,
            "path": tool_path or UNKNOWN_VALUE,
            "version": version,
        }

    return tools


def _command_version(command: str, args: list[str]) -> str:
    output = _run_command([command, *args])
    if output is None:
        return UNKNOWN_VALUE

    first_line = output.splitlines()[0].strip() if output else ""
    return first_line or UNKNOWN_VALUE


def _run_command(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    output = (result.stdout or "").strip()
    if output:
        return output

    error_output = (result.stderr or "").strip()
    return error_output or None


def _safe_probe(probe_function, fallback_value):
    try:
        return probe_function()
    except Exception:
        return fallback_value


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, override_value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(override_value, dict):
            merged[key] = _deep_merge_dicts(base_value, override_value)
        else:
            merged[key] = override_value
    return merged


def _config_dir() -> Path:
    config_dir = Path(user_config_dir(APP_NAME))
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _detected_config_path() -> Path:
    return _config_dir() / DETECTED_CONFIG_FILE_NAME


def _override_config_path() -> Path:
    return _config_dir() / OVERRIDE_CONFIG_FILE_NAME


def _read_yaml_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    try:
        raw_data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError):
        return {}

    return raw_data if isinstance(raw_data, dict) else {}


def _write_yaml_dict(path: Path, data: dict[str, Any]) -> None:
    try:
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    except OSError:
        return
