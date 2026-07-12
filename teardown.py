"""Destroy a rented vast.ai instance to stop billing.

Usage:
    uv run python teardown.py [--config config.json] [--instance-id ID] [--yes]

By default, destroys the instance provision.py last recorded locally (see
state.py) — no manual instance id lookup needed. Pass --instance-id to
target a different instance. Prompts for confirmation unless --yes is given.
Safe to run with nothing to destroy: it prints a message and exits 0.
"""

from __future__ import annotations

import argparse
import sys

import state
from config import Config, ConfigError, load_config
from vast_client import VastAPIError, VastClient


class TeardownError(Exception):
    """Raised when teardown can't proceed."""


def resolve_instance_id(client: VastClient, *, instance_id: int | None) -> int | None:
    """Return the instance id to destroy, or None if there's nothing to do.

    Preference order: explicit --instance-id, then the locally recorded
    state, then (if unambiguous) the sole running instance on the account.
    """
    if instance_id is not None:
        return instance_id

    saved = state.load()
    if saved is not None:
        return saved.instance_id

    running = [i for i in client.show_instances() if i.status == "running"]
    if not running:
        return None
    if len(running) > 1:
        ids = ", ".join(str(i.id) for i in running)
        raise TeardownError(
            f"no local state and multiple running instances (ids: {ids}); "
            f"pass --instance-id to pick one"
        )
    return running[0].id


def teardown(
    cfg: Config,
    *,
    instance_id: int | None,
    confirm: bool = True,
    ask=input,
) -> None:
    client = VastClient(cfg.api_key)

    target_id = resolve_instance_id(client, instance_id=instance_id)
    if target_id is None:
        print("no instance to destroy")
        return

    if confirm:
        answer = ask(f"destroy instance {target_id}? this stops billing and deletes its data [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            print("aborted, instance left running")
            return

    client.destroy_instance(target_id)
    state.clear()
    print(f"instance {target_id} destroyed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.json", help="path to config.json")
    parser.add_argument("--instance-id", type=int, default=None, help="vast.ai instance id")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
        teardown(cfg, instance_id=args.instance_id, confirm=not args.yes)
    except (ConfigError, TeardownError, VastAPIError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
