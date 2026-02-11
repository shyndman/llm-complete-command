import llm_complete_command as plugin


class _FakeModel:
    def __init__(self, model_id: str):
        self.model_id = model_id


class _FakeConversation:
    def __init__(self, model_id: str = "test-model"):
        self.model = _FakeModel(model_id)
        self.prompt_calls: list[tuple[str, dict[str, object]]] = []
        self._responses: list[object] = []

    def queue_response(self, response: object) -> None:
        self._responses.append(response)

    def prompt(self, prompt: str, **kwargs):
        self.prompt_calls.append((prompt, kwargs))
        if self._responses:
            return self._responses.pop(0)
        return object()


def test_collect_response_text_streams_chunks_and_calls_first_callback_once():
    written_chunks: list[str] = []
    first_chunk_notifications: list[str] = []

    response_text = plugin._collect_response_text(
        ["echo", " ", "hello"],
        write_chunk=written_chunks.append,
        on_first_chunk=lambda: first_chunk_notifications.append("called"),
    )

    assert response_text == "echo hello"
    assert written_chunks == ["echo", " ", "hello"]
    assert first_chunk_notifications == ["called"]


def test_collect_response_text_wraps_stream_errors_with_chunk_count():
    def broken_stream():
        yield "first"
        raise RuntimeError("stream failed")

    with_error = broken_stream()

    try:
        plugin._collect_response_text(with_error, write_chunk=lambda _chunk: None)
    except plugin.ResponseStreamError as error:
        assert isinstance(error.original, RuntimeError)
        assert str(error.original) == "stream failed"
        assert error.emitted_chunks == 1
    else:
        raise AssertionError("Expected ResponseStreamError")


def test_generate_command_text_marks_temperature_capability_supported(monkeypatch):
    conversation = _FakeConversation("model-alpha")
    set_calls: list[tuple[str, str, bool]] = []

    monkeypatch.setattr(plugin, "get_model_capability", lambda _model, _cap: None)
    monkeypatch.setattr(
        plugin,
        "set_model_capability",
        lambda model, capability, value: set_calls.append((model, capability, value)),
    )
    monkeypatch.setattr(
        plugin,
        "_collect_with_spinner",
        lambda _conversation, _response, _write_chunk: "ls -la",
    )

    output = plugin._generate_command_text(
        conversation,
        prompt="list files",
        system="system prompt",
        write_chunk=lambda _chunk: None,
    )

    assert output == "ls -la"
    assert len(conversation.prompt_calls) == 1
    prompt, kwargs = conversation.prompt_calls[0]
    assert prompt == "list files"
    assert kwargs == {
        "system": "system prompt",
        "temperature": plugin.DEFAULT_TEMPERATURE,
    }
    assert set_calls == [
        ("model-alpha", plugin.SUPPORTS_TEMPERATURE_CAPABILITY, True),
    ]


def test_generate_command_text_retries_without_temperature_when_unsupported(
    monkeypatch,
):
    class UnsupportedTemperatureError(Exception):
        def __init__(self):
            super().__init__("temperature unsupported")
            self.param = plugin.TEMPERATURE_PARAM
            self.code = plugin.UNSUPPORTED_VALUE_CODE

    conversation = _FakeConversation("model-beta")
    conversation.queue_response("first response")
    conversation.queue_response("second response")

    set_calls: list[tuple[str, str, bool]] = []
    spinner_calls = {"count": 0}

    monkeypatch.setattr(plugin, "get_model_capability", lambda _model, _cap: True)
    monkeypatch.setattr(
        plugin,
        "set_model_capability",
        lambda model, capability, value: set_calls.append((model, capability, value)),
    )

    def fake_collect_with_spinner(_conversation, _response, _write_chunk):
        if spinner_calls["count"] == 0:
            spinner_calls["count"] += 1
            raise plugin.ResponseStreamError(
                UnsupportedTemperatureError(), emitted_chunks=0
            )
        return "retry-success"

    monkeypatch.setattr(plugin, "_collect_with_spinner", fake_collect_with_spinner)

    output = plugin._generate_command_text(
        conversation,
        prompt="do something",
        system="system prompt",
        write_chunk=lambda _chunk: None,
    )

    assert output == "retry-success"
    assert len(conversation.prompt_calls) == 2
    assert conversation.prompt_calls[0][1] == {
        "system": "system prompt",
        "temperature": plugin.DEFAULT_TEMPERATURE,
    }
    assert conversation.prompt_calls[1][1] == {"system": "system prompt"}
    assert set_calls == [
        ("model-beta", plugin.SUPPORTS_TEMPERATURE_CAPABILITY, False),
    ]


def test_generate_command_text_reraises_original_error_when_no_retry(monkeypatch):
    conversation = _FakeConversation("model-gamma")

    class SomeStreamError(Exception):
        pass

    monkeypatch.setattr(plugin, "get_model_capability", lambda _model, _cap: True)
    monkeypatch.setattr(
        plugin,
        "_collect_with_spinner",
        lambda _conversation, _response, _write_chunk: (_ for _ in ()).throw(
            plugin.ResponseStreamError(SomeStreamError("boom"), emitted_chunks=1)
        ),
    )

    try:
        plugin._generate_command_text(
            conversation,
            prompt="do something",
            system="system prompt",
            write_chunk=lambda _chunk: None,
        )
    except SomeStreamError as error:
        assert str(error) == "boom"
    else:
        raise AssertionError("Expected SomeStreamError")

    assert len(conversation.prompt_calls) == 1
