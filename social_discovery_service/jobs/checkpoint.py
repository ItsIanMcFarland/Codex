"""Checkpointing helpers for job recovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from ..config import get_settings


class CheckpointStore:
    """Persist checkpoints to disk for worker recovery."""

    def __init__(self) -> None:
        settings = get_settings()
        self.path = settings.data_dir / "checkpoints.json"
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    def read(self) -> Dict[str, str]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def write(self, data: Dict[str, str]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def update_job(self, worker_id: str, job_id: str) -> None:
        data = self.read()
        data[worker_id] = job_id
        self.write(data)

    def clear_job(self, worker_id: str) -> None:
        data = self.read()
        if worker_id in data:
            data.pop(worker_id)
            self.write(data)


__all__ = ["CheckpointStore"]
