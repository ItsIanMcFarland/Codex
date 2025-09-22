#!/usr/bin/env python3
"""Asynchronous checker for social media profile URLs.

Reads an input CSV of social URLs, probes them concurrently, and writes a
classified output CSV along with optional summaries of inactive or unknown
results. The script is tuned for the quirks of Facebook, Instagram, TikTok,
YouTube, X/Twitter, and LinkedIn.
"""

import argparse
import asyncio
import csv
import re
import sys
import unicodedata
from collections import Counter
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

# --- Optional dependencies ---
try:  # pragma: no cover - runtime dependency guidance
    import httpx
    import pandas as pd
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover - runtime dependency guidance
    NEED = "httpx beautifulsoup4 pandas"
    print(
        f"Missing dependency: {exc}. Install with:  pip install {NEED}",
        file=sys.stderr,
    )
    sys.exit(1)


# -------------------- Config & Patterns --------------------
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

# Sign-in/cookie walls — default to Unknown (unless --login-wall-as-inactive)
LOGIN_WALL_HINTS = [
    r"you must log in to continue",
    r"log in to facebook",
    r"log in to continue",
    r"allow essential and optional cookies",
    r"sign in to x",
    r"sign in to continue",
    # LinkedIn
    r"join linkedin",
    r"sign in",
    r"sign in or join",
    r"you’re signed out|you're signed out",
    r"for the full experience",
    r"accept cookies|manage cookies",
]

# Multi-language helpers (broad but targeted to FB/LN soft-404s)
FB_DEAD_I18N = [
    # EN
    r"this content isn.?t available (right now)?",
    r"this page isn.?t available|page isn.?t available|page not found",
    r"the link you followed may be broken",
    r"the page you requested cannot be displayed right now",
    r"we couldn.?t find the page you requested",
    r"content is currently unavailable",
    r"404 not found",
    # ES/PT/FR/DE/IT/PL (common FB locales)
    r"esta página no está disponible|contenido no está disponible|página no disponible",
    r"esta página não está disponível|conteúdo indisponível|página indisponível|página não encontrada",
    r"cette page n.?est pas disponible|contenu indisponible|page introuvable",
    r"diese seite ist (derzeit )?nicht verfügbar|inhalt (derzeit )?nicht verfügbar|seite nicht gefunden",
    r"questa pagina non è disponibile|contenuto non disponibile|pagina non trovata",
    r"ta strona (nie jest dostępna|została usunięta)|strona nie została znaleziona",
]

LINKEDIN_DEAD_I18N = [
    r"page not found|404 not found",
    r"this page doesn.?t exist|this page does not exist",
    r"we couldn.?t find the page you were looking for",
    r"profile not found|the profile you requested does not exist",
    r"this content isn.?t available|content (is )?unavailable",
    r"this page no longer exists",
    # non-EN (broad)
    r"página (não encontrada|não existe)|página não disponível",
    r"página no encontrada|esta página no existe",
    r"page introuvable|cette page n.?existe pas",
    r"seite nicht gefunden|seite existiert nicht",
    r"pagina non trovata|questa pagina non esiste",
    r"strona nie została znaleziona|ta strona nie istnieje",
]

ERROR_PATTERNS: Dict[str, List[re.Pattern]] = {
    "instagram": [
        re.compile(pat, re.IGNORECASE)
        for pat in [
            r"sorry, this page isn.?t available",
            r"the link you followed may be broken",
            r"page may have been removed",
            r"page not found",
            r"this page could not be found",
            r"404 not found",
        ]
    ],
    "facebook": [re.compile(pat, re.IGNORECASE) for pat in FB_DEAD_I18N],
    "tiktok": [
        re.compile(pat, re.IGNORECASE)
        for pat in [
            r"couldn.?t find this account",
            r"video (currently )?unavailable",
            r"page not available",
            r"this account has been suspended",
            r"404 not found",
        ]
    ],
    "youtube": [
        re.compile(pat, re.IGNORECASE)
        for pat in [
            r"this channel does not exist",
            r"(video|content) unavailable",
            r"this page isn.?t available",
            r"404 not found",
            r"this account has been terminated",
        ]
    ],
    "x": [
        re.compile(pat, re.IGNORECASE)
        for pat in [
            r"this account doesn.?t exist",
            r"account suspended",
            r"page doesn.?t exist|page not found",
            r"404 not found",
        ]
    ],
    "linkedin": [re.compile(pat, re.IGNORECASE) for pat in LINKEDIN_DEAD_I18N],
}

URL_CANDIDATES = [
    "urls",
    "url",
    "link",
    "links",
    "profile",
    "social url",
    "social_url",
    "social",
    "page",
    "handle url",
    "handle_url",
    "profile url",
    "profile_url",
]
LOC_CANDIDATES = [
    "location/corporate",
    "location",
    "hotel",
    "property",
    "property name",
    "location name",
    "name",
    "location_name",
    "brand location",
]


# -------------------- Helpers --------------------
def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def guess_platform(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:  # pragma: no cover - defensive guard
        return "unknown"
    if "instagram.com" in host:
        return "instagram"
    if "facebook.com" in host or "fb.watch" in host:
        return "facebook"
    if "tiktok.com" in host:
        return "tiktok"
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "x.com" in host or "twitter.com" in host:
        return "x"
    if "linkedin.com" in host:
        return "linkedin"
    return "unknown"


def looks_like_login_wall(text_norm: str) -> bool:
    return any(re.search(pattern, text_norm, re.IGNORECASE) for pattern in LOGIN_WALL_HINTS)


def pattern_hit(
    platform: str, text_norm: str, title_norm: str, metas_norm: str
) -> Tuple[bool, str]:
    patterns = ERROR_PATTERNS.get(platform, [])
    for pattern in patterns:
        if pattern.search(text_norm) or pattern.search(title_norm) or pattern.search(metas_norm):
            return True, pattern.pattern
    return False, ""


# --- FB-specific soft 404 cues (beyond copy), incl. about/reviews shells ---
FB_SOFT404_CUES = [
    r'content="https://www\.facebook\.com/unsupportedbrowser',
    r'href="https://www\.facebook\.com/help/',
    r"/checkpoint/",
    r'property="og:url" content="https://www\.facebook\.com/unsupportedbrowser',
    r'http-equiv="refresh"',
]


def extra_facebook_dead_signals(html: str) -> bool:
    html_normalized = normalize_text(html)
    if any(re.search(pattern, html, re.IGNORECASE) for pattern in FB_SOFT404_CUES):
        return True
    try:
        soup = BeautifulSoup(html or "", "html.parser")
        title = soup.title.string if soup.title and soup.title.string else ""
        title_normalized = normalize_text(title)
        body_len = len(html_normalized)
        if (
            "facebook" in title_normalized
            and body_len < 2000
            and "profile" not in html_normalized
            and "page" not in html_normalized
        ):
            return True
    except Exception:  # pragma: no cover - soup failures are non-fatal
        pass
    return False


def classify(
    platform: str,
    html_text: str,
    status_code: int,
    login_wall_as_inactive: bool,
    url: str,
) -> Tuple[str, str]:
    """Return (Status, DetectedPattern)."""

    # Quick X/Twitter sanity: bad handles like trailing %20 etc.
    if platform == "x" or "twitter.com" in url:
        decoded = unquote(url)
        if "%20" in url or decoded.endswith((" ", "\u00A0")):
            return "Inactive", "InvalidHandle(%20/space)"

    text_norm = normalize_text(html_text)

    # Parse title + meta for stronger signals
    title_norm = ""
    metas_norm = ""
    try:
        soup = BeautifulSoup(html_text or "", "html.parser")
        title_norm = normalize_text(soup.title.string) if soup.title and soup.title.string else ""
        meta_values = []
        for meta_tag in soup.find_all("meta"):
            for key in ("content", "value"):
                value = meta_tag.get(key)
                if value:
                    meta_values.append(str(value))
        metas_norm = normalize_text(" ".join(meta_values))
    except Exception:  # pragma: no cover - soup failures are non-fatal
        pass

    # Login/consent walls
    combined_norm = " ".join([text_norm, title_norm, metas_norm])
    if looks_like_login_wall(combined_norm):
        return ("Inactive" if login_wall_as_inactive else "Unknown", "LoginWall")

    # Platform pattern hits
    hit, pattern = pattern_hit(platform, text_norm, title_norm, metas_norm)
    if hit:
        return "Inactive", pattern

    # FB soft-404 extras (about/reviews often land here)
    if platform == "facebook" and extra_facebook_dead_signals(html_text):
        return "Inactive", "FBSoft404"

    # HTTP heuristics
    if status_code == 404:
        return "Inactive", "HTTP 404"
    if 200 <= status_code < 400:
        if len(html_text) < 800:
            return "Unknown", f"SmallBody({len(html_text)})"
        return "Active", ""
    if status_code in (401, 403):
        return ("Inactive" if login_wall_as_inactive else "Unknown", f"HTTP {status_code}")
    return "Unknown", f"HTTP {status_code}"


async def fetch(
    client: "httpx.AsyncClient", url: str, timeout: float, retries: int = 2, backoff: float = 0.75
) -> Tuple[int, str]:
    for attempt in range(retries + 1):
        try:
            response = await client.get(
                url,
                follow_redirects=True,
                timeout=timeout,
                headers={
                    "User-Agent": USER_AGENTS[attempt % len(USER_AGENTS)],
                    "Accept-Language": "en-US,en;q=0.8",
                },
            )
            return response.status_code, response.text or ""
        except Exception:  # pragma: no cover - network flakes fall through to retry
            if attempt < retries:
                await asyncio.sleep(backoff * (2**attempt))
    return 0, ""


# -------------------- Pipeline --------------------
async def worker(
    name: int,
    queue: "asyncio.Queue",
    client: "httpx.AsyncClient",
    timeout: float,
    results: List[dict],
    url_col: str,
    loc_col: Optional[str],
    login_wall_as_inactive: bool,
) -> None:
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            break
        idx, row = item
        url = str(row.get(url_col, "")).strip()
        loccorp = row.get(loc_col, "") if loc_col else ""
        platform = guess_platform(url)
        status_code, html = await fetch(client, url, timeout)
        status, pattern = classify(platform, html, status_code, login_wall_as_inactive, url)
        results.append(
            {
                "row_index": idx,
                "Location/Corporate": loccorp,
                "URL": url,
                "Platform": platform,
                "HTTP_Status": status_code,
                "DetectedPattern": pattern,
                "Status": status,
            }
        )
        queue.task_done()


def autodetect_column(
    df: "pd.DataFrame", candidates: List[str], keyword_hints: Optional[List[str]] = None
) -> Optional[str]:
    lower_map = {col.lower(): col for col in df.columns}
    for candidate in candidates:
        if candidate in lower_map:
            return lower_map[candidate]
    if keyword_hints:
        for column in df.columns:
            lowered = column.lower()
            if any(keyword in lowered for keyword in keyword_hints):
                return column
    return None


async def main_async(args: argparse.Namespace) -> None:
    df = pd.read_csv(args.input_csv)
    url_col = args.url_col or autodetect_column(df, URL_CANDIDATES, ["url", "link"])
    if not url_col:
        print(
            "[Error] Could not find a URL column. "
            f"Looked for: {URL_CANDIDATES}\nAvailable: {list(df.columns)}",
            file=sys.stderr,
        )
        sys.exit(1)
    loc_col = args.location_col or autodetect_column(
        df, LOC_CANDIDATES, ["location", "property", "hotel", "name", "brand"]
    )

    queue: "asyncio.Queue" = asyncio.Queue()
    for item in df.iterrows():
        await queue.put(item)
    for _ in range(args.concurrency):
        await queue.put(None)

    results: List[dict] = []
    limits = httpx.Limits(
        max_keepalive_connections=args.concurrency,
        max_connections=args.concurrency,
    )
    async with httpx.AsyncClient(limits=limits) as client:
        workers = [
            asyncio.create_task(
                worker(
                    worker_id,
                    queue,
                    client,
                    args.timeout,
                    results,
                    url_col,
                    loc_col,
                    args.login_wall_as_inactive,
                )
            )
            for worker_id in range(args.concurrency)
        ]
        await queue.join()
        for worker_task in workers:
            await worker_task

    results_sorted = sorted(results, key=lambda r: r["row_index"])
    fields = [
        "row_index",
        "Location/Corporate",
        "URL",
        "Platform",
        "HTTP_Status",
        "DetectedPattern",
        "Status",
    ]

    with open(args.output_csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results_sorted)

    status_counts = Counter(result["Status"] for result in results_sorted)
    platform_breakdown = Counter(result["Platform"] for result in results_sorted)

    total_urls = df[url_col].shape[0]
    unique_urls = df[url_col].nunique(dropna=True)
    duplicate_urls = total_urls - unique_urls
    total_loc = unique_loc = duplicate_loc = None
    if loc_col and loc_col in df.columns:
        total_loc = df[loc_col].shape[0]
        unique_loc = df[loc_col].nunique(dropna=True)
        duplicate_loc = total_loc - unique_loc

    with open(args.summary_csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Total URLs", total_urls])
        writer.writerow(["Unique URLs", unique_urls])
        writer.writerow(["Duplicate URLs", duplicate_urls])
        if loc_col:
            writer.writerow(["Total Location/Corporate", total_loc])
            writer.writerow(["Unique Location/Corporate", unique_loc])
            writer.writerow(["Duplicate Location/Corporate", duplicate_loc])
        writer.writerow([])
        writer.writerow(["Status", "Count"])
        for status, count in status_counts.items():
            writer.writerow([status, count])
        writer.writerow([])
        writer.writerow(["Platform", "Count"])
        for platform, count in platform_breakdown.items():
            writer.writerow([platform, count])

    if args.unknowns_csv:
        unknown_rows = [result for result in results_sorted if result["Status"] == "Unknown"]
        with open(args.unknowns_csv, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(unknown_rows)
    if args.inactive_csv:
        inactive_rows = [result for result in results_sorted if result["Status"] == "Inactive"]
        with open(args.inactive_csv, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(inactive_rows)


# -------------------- CLI --------------------
def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="""
        Check social URLs (Facebook/Instagram/TikTok/YouTube/X/LinkedIn).
        Reads an input CSV, writes detailed results and a summary sheet.
        """
    )
    parser.add_argument("input_csv", help="Input CSV path (e.g., Accor_Final.csv)")
    parser.add_argument("output_csv", help="Detailed results CSV path (e.g., accor_url_status.csv)")
    parser.add_argument("--summary-csv", default="summary.csv")
    parser.add_argument("--unknowns-csv", default=None, help="Optional CSV of Unknown-only rows")
    parser.add_argument("--inactive-csv", default=None, help="Optional CSV of Inactive-only rows")
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--url-col", default=None, help="Name of the URL column (auto-detect if omitted)")
    parser.add_argument("--location-col", default=None, help="Name of the Location/Corporate column")
    parser.add_argument(
        "--login-wall-as-inactive",
        action="store_true",
        help="Count login/consent walls as INACTIVE instead of Unknown.",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
