import json

import llm_complete_command.model_capabilities_cache as model_cache


def test_set_and_get_model_capability_round_trip(tmp_path, monkeypatch):
    cache_path = tmp_path / "model-capabilities.json"
    monkeypatch.setattr(model_cache, "_cache_file_path", lambda: cache_path)
    monkeypatch.setattr(model_cache.time, "time", lambda: 1_000)

    model_cache.set_model_capability("model-a", "supports_temperature", True)

    monkeypatch.setattr(model_cache.time, "time", lambda: 1_100)
    value = model_cache.get_model_capability("model-a", "supports_temperature")
    assert value is True


def test_get_model_capability_returns_none_when_expired(tmp_path, monkeypatch):
    cache_path = tmp_path / "model-capabilities.json"
    monkeypatch.setattr(model_cache, "_cache_file_path", lambda: cache_path)
    monkeypatch.setattr(model_cache.time, "time", lambda: 1_000)

    model_cache.set_model_capability("model-a", "supports_temperature", False)

    monkeypatch.setattr(
        model_cache.time,
        "time",
        lambda: 1_000 + model_cache.CACHE_TTL_SECONDS + 1,
    )
    value = model_cache.get_model_capability("model-a", "supports_temperature")
    assert value is None


def test_read_cache_recovers_from_invalid_json(tmp_path, monkeypatch):
    cache_path = tmp_path / "model-capabilities.json"
    cache_path.write_text("{not-valid-json")
    monkeypatch.setattr(model_cache, "_cache_file_path", lambda: cache_path)

    value = model_cache._read_cache()
    assert value == {model_cache.MODEL_CAPABILITIES_KEY: {}}


def test_get_model_capability_ignores_non_boolean_values(tmp_path, monkeypatch):
    cache_path = tmp_path / "model-capabilities.json"
    cache_path.write_text(
        json.dumps(
            {
                model_cache.MODEL_CAPABILITIES_KEY: {
                    "model-a": {
                        model_cache.UPDATED_AT_KEY: 50_000,
                        "supports_temperature": "yes",
                    }
                }
            }
        )
    )
    monkeypatch.setattr(model_cache, "_cache_file_path", lambda: cache_path)
    monkeypatch.setattr(model_cache.time, "time", lambda: 50_001)

    value = model_cache.get_model_capability("model-a", "supports_temperature")
    assert value is None
