from __future__ import annotations

import argparse
from pathlib import Path

from .scraper import scrape_reviews_to_excel


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape product reviews from Coupang and export to Excel."
    )
    parser.add_argument("--url", required=True, help="Coupang product URL")
    parser.add_argument(
        "--output",
        default="output/coupang_reviews.xlsx",
        help="Output Excel file path",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=5,
        help="Maximum number of review pages to scrape",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Run browser in visible mode for debugging",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45000,
        help="Playwright timeout in milliseconds",
    )
    parser.add_argument(
        "--proxy-server",
        help="Optional Playwright proxy server, for example http://host:port",
    )
    parser.add_argument(
        "--storage-state",
        help="Optional Playwright storage state JSON file exported from a real browser session",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    row_count = scrape_reviews_to_excel(
        product_url=args.url,
        output_path=output_path,
        max_pages=args.pages,
        headless=not args.headful,
        timeout_ms=args.timeout_ms,
        proxy_server=args.proxy_server,
        storage_state_path=Path(args.storage_state) if args.storage_state else None,
    )

    print(f"Saved {row_count} reviews to {output_path}")
    return 0
