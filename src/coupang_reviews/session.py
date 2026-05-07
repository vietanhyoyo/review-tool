from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Open a browser, log in to Coupang manually, then save Playwright storage state."
    )
    parser.add_argument(
        "--login-url",
        default="https://login.coupang.com/login/login.pang",
        help="Coupang login URL to open in the browser",
    )
    parser.add_argument(
        "--output",
        default="storage-state.json",
        help="Path to save the Playwright storage state JSON",
    )
    parser.add_argument(
        "--proxy-server",
        help="Optional Playwright proxy server, for example http://host:port",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    launch_options = {"headless": False}
    if args.proxy_server:
        launch_options["proxy"] = {"server": args.proxy_server}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch_options)
        context = browser.new_context(
            locale="ko-KR",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 2200},
        )
        page = context.new_page()
        page.goto(args.login_url, wait_until="domcontentloaded")

        print("A browser window has been opened for Coupang login.")
        print("1. Log in manually in the browser.")
        print("2. Complete any CAPTCHA or verification if prompted.")
        print("3. After login succeeds, return here and press Enter to save the session.")
        input()

        context.storage_state(path=str(output_path))
        browser.close()

    print(f"Saved storage state to {output_path}")
    return 0
