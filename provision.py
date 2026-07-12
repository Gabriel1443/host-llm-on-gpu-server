"""Rent a vast.ai GPU instance matching config.json and print how to reach it.

Usage:
    uv run python provision.py [--config config.json] [--timeout 600] [--force]

Reads config.json (see config.py) for GPU filters, disk size, the Ollama
port to expose, and which model to host: search offers -> create instance
(onstart starts `ollama serve` and pulls the configured model) -> poll until
running -> print instance id + reachable host:port.

Refuses to run if local state (see state.py) already tracks an instance,
to avoid silently orphaning it — run teardown.py first, or pass --force.
"""

from __future__ import annotations

import argparse
import shlex
import sys
import time

import state
from config import Config, ConfigError, load_config
from vast_client import Instance, VastAPIError, VastClient

OLLAMA_IMAGE = "ollama/ollama:latest"
POLL_INTERVAL_SECONDS = 5
DEFAULT_TIMEOUT_SECONDS = 600


class ProvisionError(Exception):
    """Raised when provisioning cannot complete."""


def pick_offer(client: VastClient, cfg: Config):
    offers = client.search_offers(
        gpu_name=cfg.vast.gpu,
        max_price=cfg.vast.max_price,
        min_disk_gb=cfg.vast.disk_gb,
        verified=cfg.vast.verified,
        min_cpu_cores=cfg.vast.min_cpu_cores,
    )
    if not offers:
        raise ProvisionError(
            f"no rentable offer found for gpu={cfg.vast.gpu!r} "
            f"max_price={cfg.vast.max_price} disk_gb={cfg.vast.disk_gb} "
            f"verified={cfg.vast.verified} min_cpu_cores={cfg.vast.min_cpu_cores} "
            f"(try raising max_price or lowering disk_gb)"
        )
    return offers[0]  # cheapest first (search_offers orders by dph_total asc)


def wait_until_running(
    client: VastClient,
    instance_id: int,
    port: int,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    poll_interval: int = POLL_INTERVAL_SECONDS,
    sleep=time.sleep,
    now=time.monotonic,
) -> Instance:
    """Poll until the instance is running with the port mapped, or raise on timeout."""
    deadline = now() + timeout_seconds
    last_status = "unknown"
    while now() < deadline:
        inst = client.get_instance(instance_id)
        if inst is None:
            raise ProvisionError(f"instance {instance_id} disappeared while waiting")
        last_status = inst.status
        host_port = extract_host_port(inst, port)
        if inst.status == "running" and host_port is not None:
            return inst
        sleep(poll_interval)
    raise ProvisionError(
        f"instance {instance_id} did not become reachable within "
        f"{timeout_seconds}s (last status: {last_status})"
    )


def extract_host_port(instance: Instance, container_port: int) -> tuple[str, int] | None:
    """Return (host, host_port) for the given container port, or None if not mapped yet."""
    mapping = instance.ports.get(f"{container_port}/tcp")
    if not mapping:
        return None
    binding = mapping[0]
    host = instance.public_ipaddr or binding.get("HostIp")
    host_port = binding.get("HostPort")
    if not host or not host_port:
        return None
    return host, int(host_port)


def build_onstart_script(model: str, port: int) -> str:
    """Shell script: start `ollama serve`, wait for it to be ready, pull `model`.

    Runs serve in the background and polls the CLI until it responds, rather
    than a fixed sleep, since boot/model-download time varies by instance.
    `wait` at the end keeps the container alive on the serve process.

    `ollama serve` needs OLLAMA_HOST=0.0.0.0:{port} (set in the instance env,
    see vast_client.create_instance) to bind on all interfaces so the exposed
    port is reachable. But the `ollama` CLI also reads OLLAMA_HOST to know
    where to *connect*, and dialing 0.0.0.0 as a client target is invalid —
    so the readiness check and pull below override it to 127.0.0.1 for
    those two calls only. Without this the readiness loop never succeeds
    and spins forever, leaving a billed instance running with no model.
    """
    quoted_model = shlex.quote(model)
    local = f"OLLAMA_HOST=127.0.0.1:{port}"
    return (
        "ollama serve & "
        f"until {local} ollama list >/dev/null 2>&1; do sleep 1; done; "
        f"{local} ollama pull {quoted_model}; "
        "wait"
    )


def provision(cfg: Config, *, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS, force: bool = False) -> None:
    existing = state.load()
    if existing is not None and not force:
        raise ProvisionError(
            f"local state already tracks instance {existing.instance_id} "
            f"(run teardown.py first, or pass --force if you know it's already gone)"
        )

    client = VastClient(cfg.api_key)

    offer = pick_offer(client, cfg)
    print(
        f"renting offer {offer.id}: {offer.gpu_name} "
        f"@ ${offer.dph_total:.3f}/hr, {offer.disk_space:.0f}GB disk"
    )

    instance_id = client.create_instance(
        offer.id,
        image=OLLAMA_IMAGE,
        disk_gb=cfg.vast.disk_gb,
        port=cfg.ollama_port,
        onstart=build_onstart_script(cfg.model, cfg.ollama_port),
    )
    print(f"instance {instance_id} created, waiting for Ollama to serve and pull {cfg.model!r}...")

    instance = wait_until_running(client, instance_id, cfg.ollama_port, timeout_seconds=timeout_seconds)
    host, host_port = extract_host_port(instance, cfg.ollama_port)

    state.save(state.InstanceState(instance_id=instance_id, host=host, port=host_port))

    print(f"instance {instance_id} is running")
    print(f"connect from local with: http://{host}:{host_port}")
    print(f"note: {cfg.model!r} may still be downloading on the server after this returns")
    print("remember to run teardown.py when you're done — rented GPUs bill hourly")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.json", help="path to config.json")
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="seconds to wait for boot"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="provision even if local state already tracks an instance",
    )
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
        provision(cfg, timeout_seconds=args.timeout, force=args.force)
    except (ConfigError, ProvisionError, VastAPIError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
