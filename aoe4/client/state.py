from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from .tracker import TrackerState


def state_key(seed: str, team: int, slot: int, profile_id: int) -> str:
    safe_seed = re.sub(r"[^A-Za-z0-9_.-]", "_", seed)[:80] or "unknown_seed"
    return f"{safe_seed}_team{team}_slot{slot}_profile{profile_id}.json"


class StateStore:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def load(self, key: str) -> TrackerState:
        path = self.directory / key
        if not path.exists():
            return TrackerState()
        try:
            with path.open("r", encoding="utf-8") as stream:
                data = json.load(stream)
            if not isinstance(data, Mapping):
                raise ValueError("state root is not an object")
            return TrackerState.from_dict(data)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            corrupt_path = path.with_suffix(path.suffix + ".corrupt")
            try:
                os.replace(path, corrupt_path)
            except OSError:
                pass
            return TrackerState()

    def save(self, key: str, state: TrackerState) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / key
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(state.to_dict(), stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)


class ProfileStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> int | None:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8")).get("profile_id")
            return int(value) if value is not None else None
        except (OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError):
            return None

    def save(self, profile_id: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps({"profile_id": int(profile_id)}, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)

