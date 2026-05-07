from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import re
import time

import pandas as pd
from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


REVIEW_CONTAINER_SELECTORS = [
    "section.sdp-review",
    "#productReview",
    "#sdpReview",
    "[id*='review']",
    "[class*='sdp-review']",
    "[class*='review-list']",
    "[class*='reviewList']",
    "[class*='review']",
]

REVIEW_ITEM_SELECTORS = [
    "article.sdp-review__article__list",
    "article[class*='sdp-review__article__list']",
    "div.sdp-review__article__list",
    "[class*='reviewArticleReviewList']",
    "[data-review-id]",
    "[class*='review-article']",
    "[class*='reviewItem']",
    "[class*='review-item']",
]

NEXT_PAGE_SELECTORS = [
    "button.sdp-review__article__page__next",
    "button:has-text('다음')",
    "a:has-text('다음')",
]

@dataclass
class ReviewRow:
    product_url: str
    review_id: str
    author: str
    rating: str
    headline: str
    content: str
    option_text: str
    survey_text: str
    helpful_count: str
    review_date: str
    collected_at: str
    page_number: int



def scrape_reviews_to_excel(
    product_url: str,
    output_path: Path,
    max_pages: int = 5,
    headless: bool = True,
    timeout_ms: int = 45_000,
    proxy_server: str | None = None,
    storage_state_path: Path | None = None,
) -> int:
    rows = scrape_reviews(
        product_url=product_url,
        max_pages=max_pages,
        headless=headless,
        timeout_ms=timeout_ms,
        proxy_server=proxy_server,
        storage_state_path=storage_state_path,
    )
    dataframe = pd.DataFrame(asdict(row) for row in rows)
    dataframe.to_excel(output_path, index=False)
    return len(dataframe.index)


def scrape_reviews_from_cdp_to_excel(
    product_url: str,
    output_path: Path,
    cdp_url: str,
    max_pages: int = 5,
    timeout_ms: int = 45_000,
) -> int:
    rows = scrape_reviews_from_cdp(
        product_url=product_url,
        cdp_url=cdp_url,
        max_pages=max_pages,
        timeout_ms=timeout_ms,
    )
    dataframe = pd.DataFrame(asdict(row) for row in rows)
    dataframe.to_excel(output_path, index=False)
    return len(dataframe.index)


def scrape_reviews(
    product_url: str,
    max_pages: int = 5,
    headless: bool = True,
    timeout_ms: int = 45_000,
    proxy_server: str | None = None,
    storage_state_path: Path | None = None,
) -> list[ReviewRow]:
    with sync_playwright() as playwright:
        launch_options = {"headless": headless}
        if proxy_server:
            launch_options["proxy"] = {"server": proxy_server}

        browser = playwright.chromium.launch(**launch_options)
        context_options = dict(
            locale="ko-KR",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 2200},
        )
        if storage_state_path:
            context_options["storage_state"] = str(storage_state_path)

        context = browser.new_context(**context_options)
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        rows = scrape_reviews_from_page(
            page=page,
            product_url=product_url,
            max_pages=max_pages,
            timeout_ms=timeout_ms,
        )

        browser.close()
        return rows


def scrape_reviews_from_cdp(
    product_url: str,
    cdp_url: str,
    max_pages: int = 5,
    timeout_ms: int = 45_000,
) -> list[ReviewRow]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        try:
            _warm_up_coupang_session(page, context, timeout_ms)
            rows = scrape_reviews_from_page(
                page=page,
                product_url=product_url,
                max_pages=max_pages,
                timeout_ms=timeout_ms,
            )
        finally:
            page.close()
        return rows


def _warm_up_coupang_session(page: Page, context, timeout_ms: int) -> None:
    """Visit Coupang homepage to refresh session cookies before scraping."""
    page.goto("https://www.coupang.com/", wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(2_500)


def scrape_reviews_from_page(
    page: Page,
    product_url: str,
    max_pages: int = 5,
    timeout_ms: int = 45_000,
) -> list[ReviewRow]:
    page.set_default_timeout(timeout_ms)
    try:
        page.goto(product_url, wait_until="domcontentloaded")
        # If Coupang returns a session error, wait briefly and retry once
        body_preview = ""
        try:
            body_preview = page.locator("body").inner_text(timeout=5_000)
        except Exception:
            pass
        if "RET9999" in body_preview or "시스템 오류 발생" in body_preview:
            page.wait_for_timeout(3_000)
            page.goto(product_url, wait_until="domcontentloaded")
        ensure_page_access(page)
        dismiss_popups(page)
        open_review_tab(page)
    except Exception:
        raise

    rows: list[ReviewRow] = []
    seen_ids: set[str] = set()

    for page_number in range(1, max_pages + 1):
        review_items = get_review_items(page)
        if review_items.count() == 0:
            break

        current_rows = parse_review_items(
            review_items=review_items,
            product_url=product_url,
            page_number=page_number,
        )
        new_rows = [row for row in current_rows if row.review_id not in seen_ids]
        for row in new_rows:
            seen_ids.add(row.review_id)
        rows.extend(new_rows)

        if page_number >= max_pages:
            break
        if not go_to_next_review_page(page, current_page_number=page_number):
            break

    return rows


def ensure_page_access(page: Page) -> None:
    title = clean_text(page.title())
    body_text = clean_text(page.locator("body").inner_text(timeout=10_000))

    if "RET9999" in body_text or "시스템 오류 발생" in body_text:
        raise RuntimeError(
            "Coupang trả về lỗi phiên (RET9999 — 시스템 오류 발생). "
            "Trong cửa sổ Chrome vừa mở: hãy vào www.coupang.com, "
            "đăng nhập nếu cần, sau đó thử lại."
        )

    blocked_markers = [
        "Access Denied",
        "You don't have permission to access",
        "errors.edgesuite.net",
    ]
    if title in blocked_markers or any(marker in body_text for marker in blocked_markers):
        raise RuntimeError(
            "Coupang trả về Access Denied. "
            "Hãy đảm bảo đã đăng nhập Coupang trong cửa sổ Chrome."
        )


def dismiss_popups(page: Page) -> None:
    for text in ["오늘 하루 보지 않기", "닫기", "나중에"]:
        locator = page.get_by_text(text, exact=False)
        try:
            if locator.first.is_visible():
                locator.first.click(timeout=2_000)
                time.sleep(0.3)
        except PlaywrightTimeoutError:
            continue


def open_review_tab(page: Page) -> None:
    page.wait_for_timeout(2_000)
    if wait_for_review_section(page, timeout_ms=5_000):
        return

    candidate_tabs = [
        page.get_by_role("link", name=re.compile(r"상품평")),
        page.get_by_role("button", name=re.compile(r"상품평")),
        page.get_by_role("tab", name=re.compile(r"상품평")),
        page.get_by_text(re.compile(r"상품평")),
        page.get_by_text(re.compile(r"상품 리뷰")),
        page.locator("a[href*='review']"),
        page.locator("button:has-text('리뷰')"),
        page.locator("[id*='review']"),
        page.locator("[class*='review-tab']"),
        page.locator("[class*='sdp-review'] ~ *"),
    ]

    for tab in candidate_tabs:
        if try_click_review_target(tab):
            page.wait_for_timeout(1_500)
            if wait_for_review_section(page, timeout_ms=8_000):
                return

    for scroll_y in [600, 1200, 1800, 2600, 3600, 4800, 6400, 8000]:
        try:
            page.evaluate(f"window.scrollTo({{ top: {scroll_y}, behavior: 'instant' }})")
        except Exception:
            page.mouse.wheel(0, scroll_y)
        page.wait_for_timeout(1_000)
        if wait_for_review_section(page, timeout_ms=3_000):
            return

        for tab in candidate_tabs:
            if try_click_review_target(tab):
                page.wait_for_timeout(1_200)
                if wait_for_review_section(page, timeout_ms=4_000):
                    return

    raise RuntimeError("Could not open the review section on the Coupang product page.")


def wait_for_review_section(page: Page, timeout_ms: int) -> bool:
    for selector in REVIEW_CONTAINER_SELECTORS:
        try:
            locator = page.locator(selector).first
            locator.wait_for(timeout=timeout_ms)
            if locator.count() > 0:
                return True
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue

    try:
        items = get_review_items(page)
        return items.count() > 0
    except Exception:
        return False


def try_click_review_target(locator: Locator) -> bool:
    try:
        if locator.count() == 0:
            return False
        target = locator.first
        target.scroll_into_view_if_needed(timeout=3_000)
        target.click(timeout=5_000)
        return True
    except PlaywrightTimeoutError:
        return False
    except Exception:
        return False


def get_review_items(page: Page) -> Locator:
    # New Coupang structure: <article> elements inside .sdp-review / .product-review
    for container_sel in [".sdp-review", ".product-review", "#sdpReview"]:
        container = page.locator(container_sel)
        if container.count() > 0:
            articles = container.locator("article")
            if articles.count() > 0:
                return articles
    for selector in REVIEW_ITEM_SELECTORS:
        locator = page.locator(selector)
        if locator.count() > 0:
            return locator
    return page.locator("article")


def parse_review_items(
    review_items: Locator,
    product_url: str,
    page_number: int,
) -> list[ReviewRow]:
    rows: list[ReviewRow] = []
    collected_at = datetime.now(timezone.utc).isoformat()

    for index in range(review_items.count()):
        item = review_items.nth(index)
        review_id = read_review_id(item, index, page_number)
        author = first_text(item, [
            "span[class*='twc-font-bold'][class*='twc-text-bluegray-900']",
            "[class*='user-profile__name']",
            "[class*='review__profile__name']",
            "[class*='author']",
            "strong",
        ])
        rating = extract_rating(item)
        headline = extract_headline(item)
        content = extract_content(item)
        option_text = first_text(item, [
            "[class*='review__info__option']",
            "[class*='product-info']",
            "[class*='option']",
        ])
        survey_text = first_text(item, [
            "[class*='survey']",
            "[class*='help__text']",
        ])
        helpful_count = extract_helpful_count(item)
        review_date = extract_review_date(item)

        if not should_keep_review_row(review_id, rating, content, review_date):
            continue

        rows.append(
            ReviewRow(
                product_url=product_url,
                review_id=review_id,
                author=author,
                rating=rating,
                headline=headline,
                content=content,
                option_text=option_text,
                survey_text=survey_text,
                helpful_count=helpful_count,
                review_date=review_date,
                collected_at=collected_at,
                page_number=page_number,
            )
        )
    return rows


def read_review_id(item: Locator, index: int, page_number: int) -> str:
    # New structure: data-review-id is on a child div (the helpful-button container)
    help_child = item.locator("[data-review-id]")
    if help_child.count() > 0:
        value = help_child.first.get_attribute("data-review-id")
        if value:
            return clean_text(value)
    for attribute in ["data-review-id", "data-article-id", "id"]:
        value = item.get_attribute(attribute)
        if value:
            return clean_text(value)
    text = clean_text(item.inner_text(timeout=3_000))
    return f"page-{page_number}-item-{index}-{abs(hash(text[:120]))}"


def extract_rating(item: Locator) -> str:
    # New Coupang: stars rendered as <i class="...twc-bg-full-star..."> / twc-bg-half-star
    full = item.locator("i[class*='twc-bg-full-star']").count()
    half = item.locator("i[class*='twc-bg-half-star']").count()
    if full > 0 or half > 0:
        score = full + 0.5 * half
        return str(int(score)) if score == int(score) else str(score)

    # Legacy attribute-based
    for attribute in ["data-rating", "data-stars"]:
        value = item.get_attribute(attribute)
        if value:
            return clean_text(value)

    rating_text = first_text(item, [
        "[class*='star-orange']",
        "[class*='rating']",
        "[class*='star']",
        "[aria-label*='점']",
    ])
    match = re.search(r"([0-5](?:[.,]\d+)?)", rating_text)
    if match:
        return match.group(1).replace(",", ".")

    star_fill_width = first_attr(
        item,
        [
            "[class*='star-orange']",
            "[class*='rating'] [style*='width']",
            "[class*='star'] [style*='width']",
        ],
        "style",
    )
    width_match = re.search(r"width:\s*(\d+(?:\.\d+)?)%", star_fill_width)
    if width_match:
        return str(round(float(width_match.group(1)) / 20, 1)).rstrip("0").rstrip(".")

    return rating_text


def extract_helpful_count(item: Locator) -> str:
    # New structure: data-count attribute on the helpful-button div
    help_child = item.locator("[data-count]")
    if help_child.count() > 0:
        value = help_child.first.get_attribute("data-count")
        if value is not None:
            return value
    text = first_text(item, [
        "[class*='help']",
        "button:has-text('도움')",
        "button:has-text('추천')",
    ])
    match = re.search(r"(\d+)", text)
    return match.group(1) if match else text


def extract_headline(item: Locator) -> str:
    # New Coupang: headline is a <div> with twc-font-bold (not a span like the author)
    return first_text(item, [
        "div[class*='twc-font-bold'][class*='twc-text-bluegray-900']",
        "[class*='headline']",
        "[class*='review__title']",
        "[class*='title']",
        "h4",
        "h5",
    ])


def extract_content(item: Locator) -> str:
    content = first_text(item, [
        "[class*='twc-break-all']",
        "[class*='review__content']",
        "[class*='article__list__review__content']",
        "[class*='article__list__review']",
        "[class*='content']",
        "p",
    ])
    if content:
        return content

    text = clean_text(item.inner_text(timeout=3_000))
    if not text:
        return ""

    candidates = split_review_lines(text)
    filtered = [
        line for line in candidates
        if not re.fullmatch(r"\d+(?:\.\d+)?", line)
        and not re.search(r"\b(?:BEST|도움|추천|삭제|신고)\b", line, re.IGNORECASE)
        and not re.search(r"\d{4}\.\d{2}\.\d{2}", line)
        and len(line) >= 8
    ]
    return max(filtered, key=len, default="")


def extract_review_date(item: Locator) -> str:
    # New Coupang: date is in a div with twc-text-bluegray-700 matching YYYY.MM.DD
    for selector in [
        "[class*='twc-text-bluegray-700']",
        "[class*='article__list__info']",
        "[class*='review__date']",
        "[class*='date']",
        "time",
    ]:
        candidates = item.locator(selector)
        for i in range(min(candidates.count(), 6)):
            try:
                text = clean_text(candidates.nth(i).inner_text(timeout=1_500))
                match = re.search(r"\d{4}[./-]\d{1,2}[./-]\d{1,2}", text)
                if match:
                    return match.group(0)
            except Exception:
                continue
    return ""


def should_keep_review_row(
    review_id: str,
    rating: str,
    content: str,
    review_date: str,
) -> bool:
    if review_id.startswith("page-") and not any([rating, content, review_date]):
        return False
    if not any([rating, content, review_date]):
        return False
    return True


def go_to_next_review_page(page: Page, current_page_number: int) -> bool:
    current_marker = review_section_signature(page)
    next_page_text = str(current_page_number + 1)

    # Prefer buttons scoped inside the review section to avoid false matches
    review_section = page.locator(".sdp-review, .product-review").first
    candidates: list[Locator] = []
    if review_section.count() > 0:
        candidates.append(
            review_section.get_by_role("button", name=next_page_text, exact=True)
        )
    candidates.extend([
        page.get_by_role("button", name=next_page_text, exact=True),
        page.get_by_role("link", name=next_page_text, exact=True),
    ])
    candidates.extend(page.locator(selector) for selector in NEXT_PAGE_SELECTORS)

    for locator in candidates:
        try:
            if locator.count() == 0:
                continue
            target = locator.first
            target.scroll_into_view_if_needed(timeout=4_000)
            target.click(timeout=8_000)
            page.wait_for_timeout(600)
            # Scroll back to top of review section so new articles are accessible
            try:
                page.evaluate(
                    "const el = document.querySelector('.sdp-review, .product-review');"
                    "if (el) el.scrollIntoView({behavior: 'instant', block: 'start'});"
                )
            except Exception:
                pass
            wait_for_review_section_change(page, current_marker)
            return True
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue
    return False


def review_section_signature(page: Page) -> str:
    items = get_review_items(page)
    texts = []
    limit = min(items.count(), 3)
    for idx in range(limit):
        try:
            texts.append(clean_text(items.nth(idx).inner_text(timeout=2_000)))
        except PlaywrightTimeoutError:
            continue
    return "|".join(texts)


def wait_for_review_section_change(page: Page, previous_signature: str) -> None:
    deadline = time.time() + 15
    while time.time() < deadline:
        page.wait_for_timeout(700)
        current_signature = review_section_signature(page)
        if current_signature and current_signature != previous_signature:
            return
    raise PlaywrightTimeoutError("Timed out waiting for next review page")


def first_text(item: Locator, selectors: Iterable[str]) -> str:
    for selector in selectors:
        locator = item.locator(selector)
        try:
            if locator.count() == 0:
                continue
            text = clean_text(locator.first.inner_text(timeout=2_500))
            if text:
                return text
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue
    return ""


def first_attr(item: Locator, selectors: Iterable[str], attribute: str) -> str:
    for selector in selectors:
        locator = item.locator(selector)
        try:
            if locator.count() == 0:
                continue
            value = locator.first.get_attribute(attribute)
            if value:
                return clean_text(value)
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue
    return ""


def split_review_lines(text: str) -> list[str]:
    return [clean_text(part) for part in re.split(r"[\r\n]+", text) if clean_text(part)]


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


