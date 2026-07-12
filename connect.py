"""Verify a rented Ollama instance is actually reachable from this machine.

Usage:
    uv run python connect.py [--config config.json] [--instance-id ID]
                              [--host HOST --port PORT] [--prompt "hi"]

Resolves the instance's public host:port (from vast.ai, or given directly
via --host/--port) and checks it two ways: GET /api/tags (lists models) and
a small POST /api/generate against the configured model.
"""

from __future__ import annotations

import argparse
import sys

import requests

from config import Config, ConfigError, load_config
from provision import extract_host_port
from vast_client import VastAPIError, VastClient

REQUEST_TIMEOUT_SECONDS = 10
GENERATE_TIMEOUT_SECONDS = 120
DEFAULT_PROMPT = "Say OK."


class ConnectError(Exception):
    """Raised when the instance can't be resolved or reached."""


def resolve_target(
    client: VastClient, port: int, *, instance_id: int | None = None
) -> tuple[str, int]:
    """Return (host, host_port) for a running instance exposing `port`.

    If instance_id is given, use that instance. Otherwise, require exactly
    one running instance with the port mapped (ambiguous otherwise).
    """
    if instance_id is not None:
        inst = client.get_instance(instance_id)
        if inst is None:
            raise ConnectError(f"no instance found with id {instance_id}")
        candidates = [inst]
    else:
        candidates = [i for i in client.show_instances() if i.status == "running"]

    reachable = [(i, extract_host_port(i, port)) for i in candidates]
    reachable = [(i, hp) for i, hp in reachable if hp is not None]

    if not reachable:
        raise ConnectError(
            f"no running instance with port {port} mapped "
            f"(pass --instance-id, or run provision.py first)"
        )
    if len(reachable) > 1:
        ids = ", ".join(str(i.id) for i, _ in reachable)
        raise ConnectError(
            f"multiple running instances expose port {port} (ids: {ids}); "
            f"pass --instance-id to pick one"
        )

    _, host_port = reachable[0]
    return host_port


def check_tags(host: str, port: int, *, timeout: int = REQUEST_TIMEOUT_SECONDS) -> list[str]:
    """GET /api/tags. Returns the list of model names available on the server."""
    url = f"http://{host}:{port}/api/tags"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise ConnectError(f"GET /api/tags failed: {exc}") from exc
    data = resp.json()
    return [m.get("name", "?") for m in data.get("models", [])]


def check_generate(
    host: str, port: int, model: str, prompt: str, *, timeout: int = GENERATE_TIMEOUT_SECONDS
) -> str:
    """POST /api/generate with a small prompt. Returns the generated text."""
    url = f"http://{host}:{port}/api/generate"
    body = {"model": model, "prompt": prompt, "stream": False}
    try:
        resp = requests.post(url, json=body, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise ConnectError(f"POST /api/generate failed: {exc}") from exc
    data = resp.json()
    if "response" not in data:
        raise ConnectError(f"unexpected /api/generate response: {data}")
    return data["response"]


def run_check(
    cfg: Config,
    *,
    instance_id: int | None,
    host: str | None,
    port: int | None,
    prompt: str = DEFAULT_PROMPT,
) -> None:
    if host is not None:
        target_port = port or cfg.ollama_port
        target = (host, target_port)
    else:
        client = VastClient(cfg.api_key)
        target = resolve_target(client, cfg.ollama_port, instance_id=instance_id)

    target_host, target_port = target
    print(f"checking http://{target_host}:{target_port} ...")

    models = check_tags(target_host, target_port)
    print(f"/api/tags ok — models on server: {models or '(none pulled yet)'}")

    if cfg.model not in models:
        print(f"warning: configured model {cfg.model!r} not in server's model list yet")

    response = check_generate(target_host, target_port, cfg.model, prompt)
    print(f"/api/generate ok — response: {response.strip()[:200]!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.json", help="path to config.json")
    parser.add_argument("--instance-id", type=int, default=None, help="vast.ai instance id")
    parser.add_argument("--host", default=None, help="skip vast.ai lookup, connect here directly")
    parser.add_argument("--port", type=int, default=None, help="port to use with --host")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="prompt to send to /api/generate")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
        run_check(
            cfg,
            instance_id=args.instance_id,
            host=args.host,
            port=args.port,
            prompt=args.prompt,
        )
    except (ConfigError, ConnectError, VastAPIError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
