"""CSV and summary storage utilities."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional


OUTPUT_COLUMNS = [
    "hotel_id",
    "hotel_name",
    "url",
    "canonical_url",
    "http_status",
    "response_time_ms",
    "found:facebook",
    "facebook_url",
    "found:instagram",
    "instagram_url",
    "found:x",
    "x_url",
    "found:youtube",
    "youtube_url",
    "found:tiktok",
    "tiktok_url",
    "found:linkedin",
    "linkedin_url",
    "other_socials",
    "page_snapshot_path",
    "last_checked_utc_iso",
    "error_message",
]


@dataclass
class ResultRow:
    hotel_id: str
    hotel_name: str
    url: str
    canonical_url: Optional[str] = None
    http_status: Optional[int] = None
    response_time_ms: Optional[int] = None
    found_facebook: bool = False
    facebook_url: Optional[str] = None
    found_instagram: bool = False
    instagram_url: Optional[str] = None
    found_x: bool = False
    x_url: Optional[str] = None
    found_youtube: bool = False
    youtube_url: Optional[str] = None
    found_tiktok: bool = False
    tiktok_url: Optional[str] = None
    found_linkedin: bool = False
    linkedin_url: Optional[str] = None
    other_socials: List[str] = field(default_factory=list)
    page_snapshot_path: Optional[str] = None
    last_checked_utc_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "hotel_id": self.hotel_id,
            "hotel_name": self.hotel_name,
            "url": self.url,
            "canonical_url": self.canonical_url or "",
            "http_status": self.http_status if self.http_status is not None else "",
            "response_time_ms": self.response_time_ms if self.response_time_ms is not None else "",
            "found:facebook": str(self.found_facebook).lower(),
            "facebook_url": self.facebook_url or "",
            "found:instagram": str(self.found_instagram).lower(),
            "instagram_url": self.instagram_url or "",
            "found:x": str(self.found_x).lower(),
            "x_url": self.x_url or "",
            "found:youtube": str(self.found_youtube).lower(),
            "youtube_url": self.youtube_url or "",
            "found:tiktok": str(self.found_tiktok).lower(),
            "tiktok_url": self.tiktok_url or "",
            "found:linkedin": str(self.found_linkedin).lower(),
            "linkedin_url": self.linkedin_url or "",
            "other_socials": "|".join(self.other_socials),
            "page_snapshot_path": self.page_snapshot_path or "",
            "last_checked_utc_iso": self.last_checked_utc_iso,
            "error_message": self.error_message or "",
        }


def read_input_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def write_output_csv(path: Path, rows: Iterable[ResultRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_dict())


def write_summary_json(path: Path, summary: Dict[str, int]) -> None:
    path.write_text(json.dumps(summary, indent=2, sort_keys=True))


__all__ = [
    "ResultRow",
    "read_input_csv",
    "write_output_csv",
    "write_summary_json",
    "OUTPUT_COLUMNS",
]
