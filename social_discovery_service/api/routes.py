"""FastAPI routes for the social discovery service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..jobs.manager import JobManager, get_job_manager
from ..security.api_keys import Role, require_roles

router = APIRouter()


class JobCreateRequest(BaseModel):
    batch_name: str = Field(..., description="Friendly name for the batch")
    hotel_domains: List[str] = Field(..., min_items=1, description="List of hotel domains to crawl")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class JobCreateResponse(BaseModel):
    batch_id: str
    submitted_at: datetime
    job_count: int


@router.post("/jobs/batch", response_model=JobCreateResponse)
async def submit_job_batch(
    payload: JobCreateRequest,
    manager: JobManager = Depends(get_job_manager),
    _: Role = Depends(require_roles(Role.ADMIN, Role.SUBMITTER)),
) -> JobCreateResponse:
    batch = await manager.enqueue_batch(payload.batch_name, payload.hotel_domains, payload.metadata)
    return JobCreateResponse(batch_id=batch.batch_id, submitted_at=batch.submitted_at, job_count=len(batch.jobs))


class JobStatusResponse(BaseModel):
    job_id: str
    domain: str
    status: str
    attempts: int
    last_error: Optional[str]
    completed_at: Optional[datetime]


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    manager: JobManager = Depends(get_job_manager),
    _: Role = Depends(require_roles(Role.ADMIN, Role.SUBMITTER)),
) -> JobStatusResponse:
    job = await manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(**job.to_dict())


class DiscoveredLink(BaseModel):
    url: str
    source_url: Optional[str]
    network: Optional[str]
    last_seen: datetime


class JobResultsResponse(BaseModel):
    job_id: str
    domain: str
    links: List[DiscoveredLink]


@router.get("/jobs/{job_id}/results", response_model=JobResultsResponse)
async def get_job_results(
    job_id: str,
    limit: int = Query(100, ge=1, le=500),
    manager: JobManager = Depends(get_job_manager),
    _: Role = Depends(require_roles(Role.ADMIN, Role.SUBMITTER)),
) -> JobResultsResponse:
    job = await manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    links = await manager.get_discovered_links(job_id, limit=limit)
    return JobResultsResponse(job_id=job.job_id, domain=job.domain, links=links)


class HealthResponse(BaseModel):
    status: str = "ok"
    timestamp: datetime


@router.get("/health", response_model=HealthResponse, include_in_schema=False)
async def health_check() -> HealthResponse:
    return HealthResponse(timestamp=datetime.utcnow())
