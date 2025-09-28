"""API key based authentication utilities."""

from __future__ import annotations

from enum import Enum
from typing import Dict, Iterable, Optional

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from ..config import get_settings


class Role(str, Enum):
    """Role enumeration for API keys."""

    ADMIN = "admin"
    SUBMITTER = "submitter"


_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _build_role_map() -> Dict[str, Role]:
    settings = get_settings()
    role_map: Dict[str, Role] = {}
    role_map.update({key: Role.ADMIN for key in settings.admin_api_keys})
    role_map.update({key: Role.SUBMITTER for key in settings.submitter_api_keys})
    return role_map


def get_current_role(api_key: Optional[str] = Security(_api_key_header)) -> Role:
    """Validate API key and return the associated role."""

    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    role_map = _build_role_map()
    try:
        return role_map[api_key]
    except KeyError as exc:  # pragma: no cover - simple guard
        raise HTTPException(status_code=403, detail="Invalid API key") from exc


def require_roles(*allowed_roles: Iterable[Role]):
    """FastAPI dependency to enforce role-based access control."""

    allowed_set = {Role(role) for role in allowed_roles}

    def _dependency(role: Role = Depends(get_current_role)) -> Role:
        if role not in allowed_set:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return role

    return _dependency


__all__ = ["Role", "get_current_role", "require_roles"]
