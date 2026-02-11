import click
from click.testing import CliRunner

import llm_complete_command as plugin


class _FakeModel:
    def __init__(self, conversation):
        self._conversation = conversation
        self.needs_key = "provider-key"
        self.key_env_var = "PROVIDER_API_KEY"
        self.key = None

    def conversation(self):
        return self._conversation


def test_complete_command_wires_model_key_and_exec_flow(monkeypatch):
    captured: dict[str, object] = {}
    fake_conversation = object()
    fake_model = _FakeModel(fake_conversation)

    monkeypatch.setattr("llm.get_default_model", lambda: "default-model")
    monkeypatch.setattr(plugin.llm, "get_model", lambda model_id: fake_model)
    monkeypatch.setattr(
        plugin.llm,
        "get_key",
        lambda key, needs_key, key_env_var: f"resolved:{key}:{needs_key}:{key_env_var}",
    )
    monkeypatch.setattr(
        plugin, "render_default_prompt", lambda: "default system prompt"
    )
    monkeypatch.setattr(
        plugin,
        "interactive_exec",
        lambda conversation, prompt, system: captured.update(
            {"conversation": conversation, "prompt": prompt, "system": system}
        ),
    )

    cli = click.Group()
    plugin.register_commands(cli)
    runner = CliRunner()

    result = runner.invoke(cli, ["complete", "show", "cwd"])

    assert result.exit_code == 0
    assert captured == {
        "conversation": fake_conversation,
        "prompt": "show cwd",
        "system": "default system prompt",
    }
    assert fake_model.key == "resolved:None:provider-key:PROVIDER_API_KEY"
