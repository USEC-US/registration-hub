import os
from collections.abc import Iterable


def env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: Iterable[str] = ()) -> list[str]:
    raw_value = os.getenv(name)
    if raw_value is None:
        return list(default)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def local_secret_key(name: str, *, debug: bool) -> str:
    raw_value = os.getenv(name, "").strip()
    if raw_value:
        return raw_value
    if debug:
        return "local-development-secret-key"
    raise RuntimeError(f"{name} must be set when DEBUG=False.")
