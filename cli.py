"""Command line interface for Hotel Social Discover."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from itertools import cycle
from pathlib import Path
from typing import Dict, List, Optional

import httpx

from hotel_social_discover.checkpoint import CheckpointStore
from hotel_social_discover.config import load_config, parse_bool
from hotel_social_discover.fetcher import Fetcher
from hotel_social_discover.logging_utils import configure_logging, get_logger
from hotel_social_discover.parser import parse_social_links
from hotel_social_discover.robots import RobotsManager
from hotel_social_discover.storage import ResultRow, read_input_csv, write_output_csv, write_summary_json
from hotel_social_discover.url_tools import resolve_redirects

logger = get_logger(__name__)

# IMPORTANT: Only crawl websites you are authorized to access. Respect robots.txt and terms of service.


SHORTENER_DOMAINS = {
    "bit.ly",
    "t.co",
    "tinyurl.com",
    "ow.ly",
    "buff.ly",
    "rebrand.ly",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hotel Social Discover CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    crawl = subparsers.add_parser("crawl", help="Crawl hotel websites for social links")
    crawl.add_argument("--input", required=True, help="Input CSV with hotels")
    crawl.add_argument("--output", required=True, help="Output CSV for results")
    crawl.add_argument("--concurrency", type=int, help="Max concurrency")
    crawl.add_argument("--timeout", type=float, help="Request timeout")
    crawl.add_argument("--headful", type=str, default=None, help="Run Playwright headful true/false")
    crawl.add_argument("--render", action="store_true", help="Enable Playwright rendering")
    crawl.add_argument("--proxy-file", type=str, help="Optional proxy list file")
    crawl.add_argument("--resume", type=str, default="true", help="Enable resume true/false")
    crawl.add_argument("--force", action="store_true", help="Process even if checkpoint has entry")
    crawl.add_argument("--save-snapshots", action="store_true", help="Save rendered page screenshots")
    crawl.add_argument("--summary-json", type=str, help="Summary JSON output path")
    crawl.add_argument("--log-file", type=str, help="Optional log file path")

    return parser


async def process_hotel(
    record: Dict[str, str],
    fetcher: Fetcher,
    robots: RobotsManager,
    checkpoint: CheckpointStore,
    proxy: Optional[str],
    force: bool,
    resume_enabled: bool,
    summary: Counter,
) -> ResultRow:
    hotel_id = record.get("hotel_id") or record.get("id") or ""
    hotel_name = record.get("hotel_name") or record.get("name") or ""
    url = record.get("url") or record.get("website") or ""

    if not url:
        return ResultRow(hotel_id=hotel_id, hotel_name=hotel_name, url=url, error_message="missing_url")

    if resume_enabled and checkpoint.is_processed(url) and not force:
        cached = checkpoint.get(url) or {}
        summary["skipped_checkpoint"] += 1
        return ResultRow(
            hotel_id=hotel_id,
            hotel_name=hotel_name,
            url=url,
            canonical_url=cached.get("canonical_url"),
            http_status=cached.get("http_status"),
            response_time_ms=cached.get("response_time_ms"),
            found_facebook=cached.get("found_facebook", False),
            facebook_url=cached.get("facebook_url"),
            found_instagram=cached.get("found_instagram", False),
            instagram_url=cached.get("instagram_url"),
            found_x=cached.get("found_x", False),
            x_url=cached.get("x_url"),
            found_youtube=cached.get("found_youtube", False),
            youtube_url=cached.get("youtube_url"),
            found_tiktok=cached.get("found_tiktok", False),
            tiktok_url=cached.get("tiktok_url"),
            found_linkedin=cached.get("found_linkedin", False),
            linkedin_url=cached.get("linkedin_url"),
            other_socials=cached.get("other_socials", []),
            page_snapshot_path=cached.get("page_snapshot_path"),
            error_message=cached.get("error_message"),
        )

    allowed = await robots.allowed(url)
    if not allowed:
        summary["skipped_robots"] += 1
        row = ResultRow(hotel_id=hotel_id, hotel_name=hotel_name, url=url, error_message="blocked_by_robots")
        if resume_enabled:
            checkpoint.set(url, row.to_dict())
        return row

    fetch_result = await fetcher.fetch(url, proxy=proxy)
    if fetch_result.error:
        summary["errors"] += 1
        row = ResultRow(
            hotel_id=hotel_id,
            hotel_name=hotel_name,
            url=url,
            canonical_url=fetch_result.final_url,
            http_status=fetch_result.status_code,
            response_time_ms=fetch_result.elapsed_ms,
            error_message=fetch_result.error,
        )
        if resume_enabled:
            checkpoint.set(url, row.to_dict())
        return row

    summary["scanned"] += 1

    bucket, others = parse_social_links(fetch_result.body or "", fetch_result.final_url)

    # Resolve shortened URLs
    resolved_cache: Dict[str, str] = {}
    async def resolve(link: str) -> str:
        if link in resolved_cache:
            return resolved_cache[link]
        domain = httpx.URL(link).host or ""
        if domain in SHORTENER_DOMAINS:
            resolved_cache[link] = await resolve_redirects(fetcher.client, link)
        else:
            resolved_cache[link] = link
        return resolved_cache[link]

    facebook_urls = [await resolve(url) for url in bucket["facebook"]]
    instagram_urls = [await resolve(url) for url in bucket["instagram"]]
    x_urls = [await resolve(url) for url in bucket["x"]]
    youtube_urls = [await resolve(url) for url in bucket["youtube"]]
    tiktok_urls = [await resolve(url) for url in bucket["tiktok"]]
    linkedin_urls = [await resolve(url) for url in bucket["linkedin"]]

    for platform, items in (
        ("facebook", facebook_urls),
        ("instagram", instagram_urls),
        ("x", x_urls),
        ("youtube", youtube_urls),
        ("tiktok", tiktok_urls),
        ("linkedin", linkedin_urls),
    ):
        if items:
            summary[f"found_{platform}"] += len(items)

    row = ResultRow(
        hotel_id=hotel_id,
        hotel_name=hotel_name,
        url=url,
        canonical_url=fetch_result.final_url,
        http_status=fetch_result.status_code,
        response_time_ms=fetch_result.elapsed_ms,
        found_facebook=bool(facebook_urls),
        facebook_url="|".join(facebook_urls) if facebook_urls else None,
        found_instagram=bool(instagram_urls),
        instagram_url="|".join(instagram_urls) if instagram_urls else None,
        found_x=bool(x_urls),
        x_url="|".join(x_urls) if x_urls else None,
        found_youtube=bool(youtube_urls),
        youtube_url="|".join(youtube_urls) if youtube_urls else None,
        found_tiktok=bool(tiktok_urls),
        tiktok_url="|".join(tiktok_urls) if tiktok_urls else None,
        found_linkedin=bool(linkedin_urls),
        linkedin_url="|".join(linkedin_urls) if linkedin_urls else None,
        other_socials=others,
        page_snapshot_path=fetch_result.snapshot_path,
    )

    if resume_enabled:
        checkpoint.set(url, row.to_dict())
    return row


async def crawl_command(args: argparse.Namespace) -> None:
    config = load_config()

    if args.concurrency:
        config.concurrency = args.concurrency
    if args.timeout:
        config.timeout = args.timeout
    if args.headful is not None:
        config.headful = parse_bool(args.headful)
    if args.render:
        config.render = True
    if args.proxy_file:
        config.proxy_list = [line.strip() for line in Path(args.proxy_file).read_text().splitlines() if line.strip()]
    if args.summary_json:
        config.summary_json = Path(args.summary_json)

    resume_enabled = parse_bool(args.resume)

    configure_logging(Path(args.log_file) if args.log_file else None)

    input_path = Path(args.input)
    output_path = Path(args.output)

    records = read_input_csv(input_path)
    logger.info("Loaded %s records from %s", len(records), input_path)

    proxy_cycle = cycle(config.proxy_list) if config.proxy_list else None

    async with httpx.AsyncClient(
        headers={"User-Agent": config.user_agent},
        follow_redirects=True,
    ) as client:
        robots = RobotsManager(config.user_agent, client)
        fetcher = Fetcher(
            client=client,
            timeout=config.timeout,
            render=config.render,
            headful=config.headful,
            rate_limit_per_domain=config.rate_limit_per_domain,
            user_agent=config.user_agent,
            save_snapshots=args.save_snapshots,
            snapshot_dir=str(output_path.parent / "snapshots") if args.save_snapshots else None,
        )

        checkpoint = CheckpointStore(config.checkpoint_path)

        semaphore = asyncio.Semaphore(config.concurrency)
        summary: Counter = Counter()
        results: List[ResultRow] = []

        async def worker(record: Dict[str, str]) -> None:
            async with semaphore:
                proxy = next(proxy_cycle) if proxy_cycle else None
                row = await process_hotel(
                    record=record,
                    fetcher=fetcher,
                    robots=robots,
                    checkpoint=checkpoint,
                    proxy=proxy,
                    force=args.force,
                    resume_enabled=resume_enabled,
                    summary=summary,
                )
                results.append(row)

        await asyncio.gather(*(worker(record) for record in records))

        if resume_enabled:
            checkpoint.save()

    write_output_csv(output_path, results)
    logger.info("Wrote %s rows to %s", len(results), output_path)

    summary_dict = {
        "scanned": summary.get("scanned", 0),
        "skipped_checkpoint": summary.get("skipped_checkpoint", 0),
        "skipped_robots": summary.get("skipped_robots", 0),
        "errors": summary.get("errors", 0),
        "found_facebook": summary.get("found_facebook", 0),
        "found_instagram": summary.get("found_instagram", 0),
        "found_x": summary.get("found_x", 0),
        "found_youtube": summary.get("found_youtube", 0),
        "found_tiktok": summary.get("found_tiktok", 0),
        "found_linkedin": summary.get("found_linkedin", 0),
    }

    write_summary_json(config.summary_json, summary_dict)
    logger.info("Summary saved to %s", config.summary_json)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "crawl":
        asyncio.run(crawl_command(args))
    else:
        parser.error("Unknown command")


if __name__ == "__main__":
    main()
