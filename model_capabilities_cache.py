import json
import time
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir


CACHE_APP_NAME = "llm-complete-command"
CACHE_FILE_NAME = "model-capabilities.json"
CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
MODEL_CAPABILITIES_KEY = "models"
UPDATED_AT_KEY = "updated_at"


def _cache_file_path() -> Path:
    cache_dir = Path(user_cache_dir(CACHE_APP_NAME))
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / CACHE_FILE_NAME


def _read_cache() -> dict[str, Any]:
    path = _cache_file_path()
    if not path.exists():
        return {MODEL_CAPABILITIES_KEY: {}}

    try:
        cache = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {MODEL_CAPABILITIES_KEY: {}}

    if not isinstance(cache, dict):
        return {MODEL_CAPABILITIES_KEY: {}}

    model_capabilities = cache.get(MODEL_CAPABILITIES_KEY)
    if not isinstance(model_capabilities, dict):
        cache[MODEL_CAPABILITIES_KEY] = {}

    return cache


def _write_cache(cache: dict[str, Any]) -> None:
    path = _cache_file_path()
    path.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")


def get_model_capability(model_id: str, capability: str) -> bool | None:
    cache = _read_cache()
    model_capabilities = cache.get(MODEL_CAPABILITIES_KEY, {})
    if not isinstance(model_capabilities, dict):
        return None

    model_entry = model_capabilities.get(model_id)
    if not isinstance(model_entry, dict):
        return None

    updated_at = model_entry.get(UPDATED_AT_KEY)
    if not isinstance(updated_at, int):
        return None

    if int(time.time()) - updated_at > CACHE_TTL_SECONDS:
        return None

    value = model_entry.get(capability)
    if isinstance(value, bool):
        return value

    return None


def set_model_capability(model_id: str, capability: str, value: bool) -> None:
    cache = _read_cache()
    model_capabilities = cache.setdefault(MODEL_CAPABILITIES_KEY, {})

    model_entry = model_capabilities.get(model_id)
    if not isinstance(model_entry, dict):
        model_entry = {}

    model_entry[capability] = value
    model_entry[UPDATED_AT_KEY] = int(time.time())
    model_capabilities[model_id] = model_entry

    _write_cache(cache)
