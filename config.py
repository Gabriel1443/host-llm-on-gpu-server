"""Config loading and validation for host-llm-on-gpu-server.

Reads a JSON config (default: ``config.json``) describing which GPU to rent on
vast.ai and which Ollama model to host, and pulls the vast.ai API key from the
environment (never from the config file).

Usage::

    from config import load_config
    cfg = load_config()          # reads ./config.json + VAST_API_KEY env
    print(cfg.model, cfg.api_key)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = "config.json"
API_KEY_ENV = "VAST_API_KEY"
DEFAULT_OLLAMA_PORT = 11434


class ConfigError(Exception):
    """Raised when the config file or environment is missing/invalid."""


DEFAULT_VERIFIED = True


@dataclass(frozen=True)
class VastConfig:
    """vast.ai offer-search filters."""

    gpu: str
    max_price: float
    disk_gb: int
    verified: bool = DEFAULT_VERIFIED
    min_cpu_cores: float | None = None


@dataclass(frozen=True)
class Config:
    """Fully validated application config."""

    vast: VastConfig
    model: str
    ollama_port: int
    api_key: str


def _require(mapping: dict, key: str, types: type | tuple[type, ...], where: str):
    """Return ``mapping[key]`` if present and correctly typed, else raise."""
    path = f"{where}{key}"
    if key not in mapping:
        raise ConfigError(f"missing required field {path!r}")
    value = mapping[key]
    # bool is a subclass of int — reject it where a number is expected.
    if isinstance(value, bool) and bool not in (
        types if isinstance(types, tuple) else (types,)
    ):
        raise ConfigError(f"field {path!r} must be {_type_names(types)}, got bool")
    if not isinstance(value, types):
        got = type(value).__name__
        raise ConfigError(f"field {path!r} must be {_type_names(types)}, got {got}")
    return value


def _type_names(types: type | tuple[type, ...]) -> str:
    if not isinstance(types, tuple):
        types = (types,)
    return " or ".join(t.__name__ for t in types)


def load_config(
    path: str | os.PathLike = DEFAULT_CONFIG_PATH,
    *,
    env: dict | None = None,
) -> Config:
    """Load, validate, and return the config.

    Args:
        path: Path to the JSON config file.
        env: Environment mapping to read the API key from (defaults to os.environ).
             Injectable for testing.

    Raises:
        ConfigError: on a missing file, invalid JSON, bad/missing fields, or a
            missing ``VAST_API_KEY`` in the environment.
    """
    env = os.environ if env is None else env

    config_path = Path(path)
    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(
            f"config file not found: {config_path} "
            f"(copy config.json.example to config.json)"
        ) from None

    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {config_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"config root must be a JSON object, got {type(raw).__name__}")

    # --- vast filters -------------------------------------------------------
    vast_raw = _require(raw, "vast", dict, where="")
    gpu = _require(vast_raw, "gpu", str, where="vast.")
    max_price = float(_require(vast_raw, "max_price", (int, float), where="vast."))
    disk_gb = _require(vast_raw, "disk_gb", int, where="vast.")
    if max_price <= 0:
        raise ConfigError("field 'vast.max_price' must be > 0")
    if disk_gb <= 0:
        raise ConfigError("field 'vast.disk_gb' must be > 0")

    if "verified" in vast_raw:
        verified = _require(vast_raw, "verified", bool, where="vast.")
    else:
        verified = DEFAULT_VERIFIED

    if "min_cpu_cores" in vast_raw:
        min_cpu_cores = float(_require(vast_raw, "min_cpu_cores", (int, float), where="vast."))
        if min_cpu_cores <= 0:
            raise ConfigError("field 'vast.min_cpu_cores' must be > 0")
    else:
        min_cpu_cores = None

    # --- model --------------------------------------------------------------
    model = _require(raw, "model", str, where="").strip()
    if not model:
        raise ConfigError("field 'model' must be a non-empty string")

    # --- ollama_port (optional, defaults to 11434) --------------------------
    if "ollama_port" in raw:
        ollama_port = _require(raw, "ollama_port", int, where="")
        if not (1 <= ollama_port <= 65535):
            raise ConfigError("field 'ollama_port' must be between 1 and 65535")
    else:
        ollama_port = DEFAULT_OLLAMA_PORT

    # --- API key (from env, never from file) --------------------------------
    api_key = env.get(API_KEY_ENV, "").strip()
    if not api_key:
        raise ConfigError(
            f"environment variable {API_KEY_ENV} is not set "
            f"(export {API_KEY_ENV}=... — do not put it in config.json)"
        )

    return Config(
        vast=VastConfig(
            gpu=gpu,
            max_price=max_price,
            disk_gb=disk_gb,
            verified=verified,
            min_cpu_cores=min_cpu_cores,
        ),
        model=model,
        ollama_port=ollama_port,
        api_key=api_key,
    )


if __name__ == "__main__":
    # Small CLI: print the loaded config with the key redacted.
    try:
        cfg = load_config()
    except ConfigError as exc:
        raise SystemExit(f"config error: {exc}")
    redacted = "set" if cfg.api_key else "missing"
    print(
        f"gpu={cfg.vast.gpu} max_price={cfg.vast.max_price} "
        f"disk_gb={cfg.vast.disk_gb} verified={cfg.vast.verified} "
        f"min_cpu_cores={cfg.vast.min_cpu_cores} model={cfg.model} "
        f"ollama_port={cfg.ollama_port} api_key={redacted}"
    )
