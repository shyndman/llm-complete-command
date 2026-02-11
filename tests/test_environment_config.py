import llm_complete_command.environment_config as environment_config


def test_deep_merge_dicts_merges_nested_objects_without_mutating_inputs():
    base = {
        "os": {"family": "Linux", "name": "Ubuntu", "version": "24.04"},
        "tools": {"rg": {"available": True, "version": "14.0"}},
    }
    override = {
        "os": {"version": "24.10"},
        "tools": {"fd": {"available": True, "version": "9.0"}},
    }

    merged = environment_config._deep_merge_dicts(base, override)

    assert merged == {
        "os": {"family": "Linux", "name": "Ubuntu", "version": "24.10"},
        "tools": {
            "rg": {"available": True, "version": "14.0"},
            "fd": {"available": True, "version": "9.0"},
        },
    }
    assert base["os"]["version"] == "24.04"


def test_is_fresh_uses_ttl_window(monkeypatch):
    monkeypatch.setattr(environment_config.time, "time", lambda: 10_000)

    assert environment_config._is_fresh({"detected_at": 10_000})
    assert environment_config._is_fresh(
        {"detected_at": 10_000 - environment_config.ENVIRONMENT_PROBE_TTL_SECONDS}
    )
    assert not environment_config._is_fresh(
        {"detected_at": 10_000 - environment_config.ENVIRONMENT_PROBE_TTL_SECONDS - 1}
    )
    assert not environment_config._is_fresh({"detected_at": "not-an-int"})


def test_detect_terminal_name_prefers_term_program_then_known_env_vars(monkeypatch):
    monkeypatch.setenv("TERM_PROGRAM", "iTerm")
    monkeypatch.setenv("KITTY_PID", "123")
    assert environment_config._detect_terminal_name() == "iTerm"

    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    assert environment_config._detect_terminal_name() == "kitty"

    monkeypatch.delenv("KITTY_PID", raising=False)
    monkeypatch.setenv("WEZTERM_PANE", "1")
    assert environment_config._detect_terminal_name() == "wezterm"

    monkeypatch.delenv("WEZTERM_PANE", raising=False)
    monkeypatch.setenv("ALACRITTY_SOCKET", "socket")
    assert environment_config._detect_terminal_name() == "alacritty"


def test_probe_tools_captures_available_and_missing_tools(monkeypatch):
    monkeypatch.setattr(
        environment_config.shutil,
        "which",
        lambda tool_name: f"/usr/bin/{tool_name}" if tool_name == "rg" else None,
    )
    monkeypatch.setattr(
        environment_config,
        "_command_version",
        lambda tool_name, _args: "ripgrep 14.0" if tool_name == "rg" else "unknown",
    )

    tools = environment_config._probe_tools()

    assert tools["rg"] == {
        "available": True,
        "path": "/usr/bin/rg",
        "version": "ripgrep 14.0",
    }
    assert tools["fd"]["available"] is False
    assert tools["fd"]["path"] == environment_config.UNKNOWN_VALUE
    assert tools["fd"]["version"] == environment_config.UNKNOWN_VALUE


def test_load_effective_environment_merges_detected_and_override(monkeypatch):
    monkeypatch.setattr(
        environment_config,
        "_load_detected_environment",
        lambda: {
            "os": {"family": "Linux", "name": "Ubuntu", "version": "24.04"},
            "tools": {"rg": {"available": True}},
        },
    )
    monkeypatch.setattr(
        environment_config,
        "_read_yaml_dict",
        lambda _path: {
            "os": {"version": "24.10"},
            "tools": {"fd": {"available": True}},
        },
    )
    monkeypatch.setattr(environment_config, "_override_config_path", lambda: object())

    merged = environment_config.load_effective_environment()

    assert merged["os"] == {"family": "Linux", "name": "Ubuntu", "version": "24.10"}
    assert merged["tools"] == {
        "rg": {"available": True},
        "fd": {"available": True},
    }
