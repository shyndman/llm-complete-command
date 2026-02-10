from typing import Any


UNKNOWN_VALUE = "unknown"
PROBED_TOOLS = ("rg", "fd", "choose", "eza", "procs", "jq", "yq")
ADDITIONAL_DETAILS_KEY = "additional_details"


def build_system_prompt(environment: dict[str, Any]) -> str:
    os_line = _format_os_line(environment)
    shell_line = _format_shell_line(environment)
    terminal_line = _format_terminal_line(environment)
    tool_lines = _format_tool_lines(environment)
    additional_details_lines = _format_additional_details(environment)
    tool_preference_lines = _format_tool_preferences(environment)

    return "\n".join(
        [
            "You are an expert system administrator and shell maestro with decades of experience.",
            "",
            "Convert plain-English shell requests into elegant and efficient command lines.",
            "",
            "Respond ONLY with the raw command to execute.",
            "- No markdown",
            "- No explanations",
            "- No code fences",
            "- No surrounding quotes",
            "",
            "Runtime environment:",
            f"- {os_line}",
            f"- {shell_line}",
            f"- {terminal_line}",
            "",
            "Detected tools:",
            tool_lines,
            "",
            "Additional details:",
            additional_details_lines,
            "",
            "Tool preferences:",
            tool_preference_lines,
            "",
            "Response format rules:",
            "- Return only the command itself",
            "- Keep multi-line commands valid with continuations or heredocs",
            "- For potentially destructive operations, include safeguards",
            "",
            "Examples:",
            '- "find all python files" -> fd .py',
            '- "search for pattern in text files" -> rg "pattern" -t txt',
            '- "list directories by size" -> eza -la --sort=size',
        ]
    )


def _format_os_line(environment: dict[str, Any]) -> str:
    os_info = environment.get("os", {})
    if not isinstance(os_info, dict):
        return "os: unknown"

    family = os_info.get("family", UNKNOWN_VALUE)
    name = os_info.get("name", UNKNOWN_VALUE)
    version = os_info.get("version", UNKNOWN_VALUE)
    return f"os: {family} ({name}, {version})"


def _format_shell_line(environment: dict[str, Any]) -> str:
    shell_info = environment.get("shell", {})
    if not isinstance(shell_info, dict):
        return "shell: unknown"

    name = shell_info.get("name", UNKNOWN_VALUE)
    path = shell_info.get("path", UNKNOWN_VALUE)
    version = shell_info.get("version", UNKNOWN_VALUE)
    return f"shell: {name} at {path} ({version})"


def _format_terminal_line(environment: dict[str, Any]) -> str:
    terminal_info = environment.get("terminal", {})
    if not isinstance(terminal_info, dict):
        return "terminal: unknown"

    name = terminal_info.get("name", UNKNOWN_VALUE)
    version = terminal_info.get("version", UNKNOWN_VALUE)
    return f"terminal: {name} ({version})"


def _format_tool_lines(environment: dict[str, Any]) -> str:
    tools = environment.get("tools", {})
    if not isinstance(tools, dict):
        return "- unavailable"

    lines = []
    for tool_name in PROBED_TOOLS:
        tool_info = tools.get(tool_name, {})
        if not isinstance(tool_info, dict):
            lines.append(f"- {tool_name}: unknown")
            continue

        available = tool_info.get("available") is True
        version = tool_info.get("version", UNKNOWN_VALUE)
        state = "available" if available else "missing"
        lines.append(f"- {tool_name}: {state} ({version})")

    return "\n".join(lines)


def _format_additional_details(environment: dict[str, Any]) -> str:
    additional_details = environment.get(ADDITIONAL_DETAILS_KEY, {})
    if not isinstance(additional_details, dict) or not additional_details:
        return "- none"

    return "\n".join(f"- {key}: {value}" for key, value in additional_details.items())


def _format_tool_preferences(environment: dict[str, Any]) -> str:
    tools = environment.get("tools", {})
    if not isinstance(tools, dict):
        return "- Use available tools shown in detected tools."

    preferences = []
    if _tool_available(tools, "rg"):
        preferences.append("- Prefer rg instead of grep for text search.")
    if _tool_available(tools, "fd"):
        preferences.append("- Prefer fd instead of find for file discovery.")
    if _tool_available(tools, "choose"):
        preferences.append(
            "- Prefer choose for structured column extraction when appropriate."
        )
    if _tool_available(tools, "eza"):
        preferences.append("- Prefer eza instead of ls for directory listings.")
    if _tool_available(tools, "procs"):
        preferences.append("- Prefer procs for process inspection tasks.")
    if _tool_available(tools, "jq"):
        preferences.append("- Prefer jq for JSON filtering and transformations.")
    if _tool_available(tools, "yq"):
        preferences.append("- Prefer yq for YAML filtering and transformations.")

    if not preferences:
        preferences.append("- Use standard POSIX tools available in this environment.")

    return "\n".join(preferences)


def _tool_available(tools: dict[str, Any], tool_name: str) -> bool:
    tool_info = tools.get(tool_name)
    return isinstance(tool_info, dict) and tool_info.get("available") is True
