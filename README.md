# Hotel Social Discover

Hotel Social Discover is an asyncio friendly crawler that inspects hotel websites to identify social media profiles. It respects robots.txt directives, performs optional JavaScript rendering via Playwright, and outputs normalized social profile links.

## Features

- Async HTTP fetching with retries using `httpx` and `tenacity`.
- Robots.txt compliance for the `hotel-social-discover` user agent.
- Heuristic detection of JavaScript-heavy pages with optional Playwright rendering (headless by default).
- Extraction and normalization of social profile links (Facebook, Instagram, X/Twitter, YouTube, TikTok, LinkedIn, and others).
- Optional PNG snapshots from Playwright for debugging.
- Incremental resume capability using a JSON checkpoint file.
- CSV input/output with detailed metadata and JSON summary export.
- Structured logging with rotating file handlers.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
playwright install --with-deps chromium
```

> ⚠️ Playwright browser downloads are large. Skip the install command above if you will only perform static HTTP fetching.

## Configuration

Configuration values are loaded from environment variables and a `.env` file. See the bundled `.env` for defaults.

Key options:

- `HSD_CONCURRENCY`: Maximum concurrent tasks (default 10).
- `HSD_RATE_LIMIT_PER_DOMAIN`: Minimum seconds between requests to the same domain (default 2.0).
- `HSD_USER_AGENT`: User agent string for both HTTP requests and robots.txt checks.
- `HSD_CHECKPOINT_PATH`: Path to resume checkpoint JSON file (default `.hotel_social_discover_checkpoint.json`).

## Usage

```bash
python cli.py crawl \
  --input examples/hotels.csv \
  --output results.csv \
  --concurrency 10 \
  --timeout 12 \
  --headful=false \
  --proxy-file proxies.txt \
  --resume=true \
  --save-snapshots
```

### Arguments

- `--input`: Path to CSV file containing hotel records. Must include `hotel_id`, `hotel_name`, and `url` columns.
- `--output`: Path to CSV output file (required).
- `--concurrency`: Maximum concurrent crawls (overrides default).
- `--timeout`: Request timeout in seconds (default from config).
- `--headful`: `true` or `false` to run Playwright in headful mode. Rendering is disabled unless `--render` is also passed.
- `--render`: Enable Playwright rendering when heuristics indicate dynamic content.
- `--proxy-file`: Optional path to newline-separated proxy URLs.
- `--resume`: Enable checkpoint resume (default true). Use `--force` to ignore checkpoint entries.
- `--save-snapshots`: Save rendered page screenshots alongside CSV output.
- `--summary-json`: Path to JSON summary file (default `results.summary.json`).

## CSV Input

Input CSV columns must include:

```
hotel_id,hotel_name,url
```

Extra columns are preserved during processing.

## Output

The output CSV contains:

```
hotel_id,hotel_name,url,canonical_url,http_status,response_time_ms,found:facebook,facebook_url,found:instagram,instagram_url,found:x,x_url,found:youtube,youtube_url,found:tiktok,tiktok_url,found:linkedin,linkedin_url,other_socials,page_snapshot_path,last_checked_utc_iso,error_message
```

## Legal & Ethical Notice

**Use this tool only on websites that you own or are authorized to crawl.** Respect each website's terms of service, robots.txt directives, and rate limits. Never attempt to bypass CAPTCHAs, authentication gates, or other access controls. The authors accept no responsibility for misuse.

## Development

Run tests with:

```bash
pytest
```

## Example

```
python cli.py crawl --input examples/hotels.csv --output results.csv --render --save-snapshots
```
