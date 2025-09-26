"""Checkpoint management for incremental resume."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional


class CheckpointStore:
    """Simple JSON-based checkpoint store."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: Dict[str, Dict] = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
            except Exception:
                self._data = {}

    def is_processed(self, key: str) -> bool:
        return key in self._data

    def get(self, key: str) -> Optional[Dict]:
        return self._data.get(key)

    def set(self, key: str, value: Dict) -> None:
        self._data[key] = value

    def save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True))


__all__ = ["CheckpointStore"]
