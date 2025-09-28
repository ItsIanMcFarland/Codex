"""URL helper utilities."""

from __future__ import annotations

from typing import Optional

import httpx


async def resolve_redirects(client: httpx.AsyncClient, url: str, max_hops: int = 5) -> str:
    current = url
    for _ in range(max_hops):
        try:
            response = await client.head(current, follow_redirects=False, timeout=10.0)
        except Exception:
            return current
        if response.status_code in {301, 302, 303, 307, 308} and "location" in response.headers:
            current = response.headers["location"]
            if not current.startswith("http"):
                # Fallback to GET with follow redirects to resolve relative
                try:
                    final = await client.get(url, follow_redirects=True, timeout=10.0)
                    return str(final.url)
                except Exception:
                    return url
        else:
            return current
    return current


__all__ = ["resolve_redirects"]
