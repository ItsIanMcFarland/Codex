"""Domain models for jobs and batches."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class CrawlJob:
    job_id: str
    domain: str
    status: str = "queued"
    attempts: int = 0
    last_error: Optional[str] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    db_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "domain": self.domain,
            "status": self.status,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "completed_at": self.completed_at,
        }


@dataclass
class JobBatch:
    batch_id: str
    batch_name: str
    submitted_at: datetime
    jobs: List[CrawlJob]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, batch_name: str, domains: List[str], metadata: Dict[str, Any]) -> "JobBatch":
        now = datetime.utcnow()
        jobs = [
            CrawlJob(job_id=str(uuid.uuid4()), domain=domain, metadata=metadata.copy())
            for domain in domains
        ]
        return cls(batch_id=str(uuid.uuid4()), batch_name=batch_name, submitted_at=now, jobs=jobs, metadata=metadata)
