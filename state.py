"""Tracks the currently-provisioned vast.ai instance locally.

provision.py writes this after successfully renting an instance; teardown.py
reads it so destroying doesn't require the user to look up the instance id
manually. The state file is gitignored — it's local, throwaway bookkeeping,
not shared project state.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

STATE_PATH = Path(".vast_state.json")


@dataclass(frozen=True)
class InstanceState:
    instance_id: int
    host: str
    port: int


def save(state: InstanceState, *, path: Path = STATE_PATH) -> None:
    path.write_text(json.dumps(asdict(state)), encoding="utf-8")


def load(*, path: Path = STATE_PATH) -> InstanceState | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    data = json.loads(raw)
    return InstanceState(**data)


def clear(*, path: Path = STATE_PATH) -> None:
    path.unlink(missing_ok=True)
