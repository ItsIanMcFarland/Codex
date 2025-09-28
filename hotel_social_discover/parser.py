"""HTML parsing and social link normalization."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - fallback when dependency missing
    BeautifulSoup = None  # type: ignore
    from html.parser import HTMLParser

    class _AnchorCollector(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.anchors: List[str] = []

        def handle_starttag(self, tag: str, attrs):  # type: ignore[override]
            if tag.lower() != "a":
                return
            for key, value in attrs:
                if key.lower() == "href" and value:
                    self.anchors.append(value)

    def _fallback_parse_anchors(html: str) -> List[str]:
        parser = _AnchorCollector()
        parser.feed(html)
        return parser.anchors
else:
    def _fallback_parse_anchors(html: str) -> List[str]:  # pragma: no cover - bs4 path
        soup = BeautifulSoup(html, "lxml")
        return [a.get("href") or "" for a in soup.find_all("a", href=True)]

try:
    import tldextract
except Exception:  # pragma: no cover - fallback when dependency missing
    tldextract = None  # type: ignore

    def _extract_domain(netloc: str) -> str:
        return netloc.lower()
else:
    def _extract_domain(netloc: str) -> str:  # pragma: no cover - full dependency path
        ext = tldextract.extract(netloc)
        netloc_parts = [part for part in [ext.subdomain, ext.registered_domain] if part]
        return ".".join(netloc_parts).lower() if netloc_parts else netloc.lower()

SOCIAL_PATTERNS = {
    "facebook": re.compile(r"facebook\.com", re.I),
    "instagram": re.compile(r"instagram\.com", re.I),
    "x": re.compile(r"(?:twitter|x)\.com", re.I),
    "youtube": re.compile(r"(?:youtube\.com|youtu\.be)", re.I),
    "tiktok": re.compile(r"tiktok\.com", re.I),
    "linkedin": re.compile(r"linkedin\.com", re.I),
}

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
}


@dataclass
class SocialLink:
    platform: Optional[str]
    url: str


def normalize_url(url: str, base_url: Optional[str] = None) -> Optional[str]:
    if not url:
        return None

    url = unicodedata.normalize("NFKC", url.strip())
    if url.startswith("//"):
        url = "https:" + url
    if base_url:
        url = urljoin(base_url, url)

    parsed = urlparse(url)
    if not parsed.scheme:
        parsed = parsed._replace(scheme="https")
    if not parsed.netloc:
        return None

    parsed = parsed._replace(netloc=_extract_domain(parsed.netloc))

    query = parse_qs(parsed.query, keep_blank_values=False)
    cleaned_query = {k: v for k, v in query.items() if k.lower() not in TRACKING_PARAMS}
    parsed = parsed._replace(query=urlencode(cleaned_query, doseq=True))

    # remove fragments
    parsed = parsed._replace(fragment="")

    normalized = urlunparse(parsed)
    return normalized


def detect_platform(url: str) -> Optional[str]:
    for platform, pattern in SOCIAL_PATTERNS.items():
        if pattern.search(url):
            return platform
    return None


def resolve_duplicates(links: Iterable[SocialLink]) -> Tuple[Dict[str, List[str]], List[str]]:
    bucket: Dict[str, List[str]] = {platform: [] for platform in SOCIAL_PATTERNS}
    others: List[str] = []
    for link in links:
        if link.platform and link.platform in bucket:
            if link.url not in bucket[link.platform]:
                bucket[link.platform].append(link.url)
        else:
            if link.url not in others:
                others.append(link.url)
    return bucket, others


def parse_social_links(html: str, base_url: str) -> Tuple[Dict[str, List[str]], List[str]]:
    anchors = _fallback_parse_anchors(html)
    links: List[SocialLink] = []
    for raw_href in anchors:
        href = normalize_url(raw_href, base_url)
        if not href:
            continue
        platform = detect_platform(href)
        links.append(SocialLink(platform=platform, url=href))

    return resolve_duplicates(links)


def is_js_heavy(html: str) -> bool:
    if not html:
        return True
    scripts = html.lower().count("<script")
    anchors = html.lower().count("<a")
    if len(html) < 2_000:
        return True
    if scripts > 20 and anchors < 5:
        return True
    return False


def looks_like_captcha(html: str) -> bool:
    if not html:
        return False
    return bool(re.search(r"captcha", html, re.I))


__all__ = [
    "parse_social_links",
    "normalize_url",
    "detect_platform",
    "resolve_duplicates",
    "is_js_heavy",
    "looks_like_captcha",
]
