import llm_complete_command.system_prompt as system_prompt


def test_format_tool_lines_outputs_each_expected_tool_in_order():
    environment = {
        "tools": {
            "rg": {"available": True, "version": "ripgrep 14.0"},
            "fd": {"available": False, "version": "unknown"},
        }
    }

    lines = system_prompt._format_tool_lines(environment).splitlines()

    assert lines[0] == "- rg: available (ripgrep 14.0)"
    assert lines[1] == "- fd: missing (unknown)"
    assert lines[2] == "- choose: missing (unknown)"


def test_format_tool_preferences_uses_available_tools_and_avoids_default_message():
    environment = {
        "tools": {
            "rg": {"available": True},
            "fd": {"available": False},
            "jq": {"available": True},
        }
    }

    preferences = system_prompt._format_tool_preferences(environment)

    assert "Prefer rg instead of grep" in preferences
    assert "Prefer jq for JSON filtering" in preferences
    assert "Use standard POSIX tools" not in preferences


def test_build_system_prompt_contains_core_sections_and_additional_details():
    environment = {
        "os": {"family": "Linux", "name": "Ubuntu", "version": "24.10"},
        "shell": {"name": "zsh", "path": "/usr/bin/zsh", "version": "5.9"},
        "terminal": {"name": "wezterm", "version": "20240203"},
        "tools": {},
        "additional_details": {"workspace": "repo-root"},
    }

    prompt = system_prompt.build_system_prompt(environment)

    assert "Runtime environment:" in prompt
    assert "Detected tools:" in prompt
    assert "Tool preferences:" in prompt
    assert "- workspace: repo-root" in prompt
