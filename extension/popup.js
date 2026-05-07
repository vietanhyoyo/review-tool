// ─── Scraping function injected into the Coupang tab ─────────────────────────
// Must be completely self-contained (no closures over popup.js scope).
async function scrapeAllReviews(maxPages) {
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  function cleanText(el) {
    return (el?.textContent ?? '').replace(/\s+/g, ' ').trim();
  }

  async function waitForEl(selector, timeout) {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const el = document.querySelector(selector);
      if (el) return el;
      await sleep(200);
    }
    return null;
  }

  // Try to scroll to and open the review section
  async function openReviewSection() {
    const reviewSel = '.sdp-review article, .product-review article';
    if (document.querySelector(reviewSel)) return true;

    // Dismiss common popups
    for (const text of ['오늘 하루 보지 않기', '닫기', '나중에']) {
      const el = Array.from(document.querySelectorAll('button, a'))
        .find(e => e.textContent.includes(text));
      if (el) { el.click(); await sleep(300); }
    }

    // Find and click the review tab (상품평)
    function clickReviewTab() {
      const tab = Array.from(document.querySelectorAll('a, button, [role="tab"]'))
        .find(el => el.textContent.includes('상품평'));
      if (tab) { tab.click(); return true; }
      return false;
    }

    clickReviewTab();
    await sleep(1800);
    if (document.querySelector(reviewSel)) return true;

    // Scroll down progressively to trigger lazy-loaded review section
    for (const y of [800, 1600, 2600, 4000, 6000, 8000]) {
      window.scrollTo({ top: y, behavior: 'instant' });
      await sleep(700);
      clickReviewTab();
      await sleep(500);
      if (document.querySelector(reviewSel)) return true;
    }

    return !!document.querySelector('.sdp-review, .product-review, #sdpReview');
  }

  function getSection() {
    return document.querySelector('.sdp-review, .product-review, #sdpReview');
  }

  // Fingerprint the visible reviews to detect page change
  function sectionSignature() {
    const section = getSection();
    if (!section) return '';
    return Array.from(section.querySelectorAll('article'))
      .slice(0, 3)
      .map(a => (a.textContent ?? '').slice(0, 60))
      .join('|');
  }

  function extractPage(pageNumber) {
    const section = getSection();
    if (!section) return [];
    const now = new Date().toISOString();
    const rows = [];

    for (const article of section.querySelectorAll('article')) {
      // Rating
      const full = article.querySelectorAll('i[class*="twc-bg-full-star"]').length;
      const half = article.querySelectorAll('i[class*="twc-bg-half-star"]').length;
      const ratingNum = full + half * 0.5;
      const rating = ratingNum === Math.floor(ratingNum)
        ? String(Math.floor(ratingNum))
        : String(ratingNum);

      // Author — span with twc-font-bold + twc-text-bluegray-900
      const authorEl =
        article.querySelector('span[class*="twc-font-bold"][class*="twc-text-bluegray-900"]') ||
        article.querySelector('[class*="user-profile__name"]') ||
        article.querySelector('strong');
      const author = cleanText(authorEl);

      // Headline — div (not span) with twc-font-bold + twc-text-bluegray-900
      const headlineEl =
        article.querySelector('div[class*="twc-font-bold"][class*="twc-text-bluegray-900"]') ||
        article.querySelector('[class*="headline"]');
      const headline = cleanText(headlineEl);

      // Content
      const contentEl =
        article.querySelector('[class*="twc-break-all"]') ||
        article.querySelector('[class*="review__content"]') ||
        article.querySelector('p');
      const content = cleanText(contentEl);

      // Date
      let reviewDate = '';
      for (const el of article.querySelectorAll('[class*="twc-text-bluegray-700"], time, [class*="date"]')) {
        const m = cleanText(el).match(/\d{4}[./-]\d{1,2}[./-]\d{1,2}/);
        if (m) { reviewDate = m[0]; break; }
      }

      // Review ID (on child with data-review-id attribute)
      const idEl = article.querySelector('[data-review-id]');
      const reviewId = idEl?.dataset?.reviewId ?? '';

      // Helpful count
      const helpEl = article.querySelector('[data-count]');
      const helpfulCount = helpEl?.dataset?.count ?? '0';

      // Option / variant text
      const optionEl = article.querySelector(
        '[class*="review__info__option"], [class*="product-info"], [class*="option"]'
      );
      const optionText = cleanText(optionEl);

      if (!content && !rating) continue;

      rows.push({
        product_url: window.location.href,
        review_id: reviewId,
        author,
        rating,
        headline,
        content,
        option_text: optionText,
        helpful_count: helpfulCount,
        review_date: reviewDate,
        collected_at: now,
        page_number: pageNumber,
      });
    }
    return rows;
  }

  function realClick(el) {
    for (const type of ['mousedown', 'mouseup', 'click'])
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true }));
  }

  // Find all numeric page-number buttons currently visible on the page.
  // Scoped to the review section's sibling/parent area to avoid stray numbers.
  function getVisiblePageBtns() {
    // Start from the review section and walk up until we find the pagination
    const section = getSection();
    const searchRoot = section?.parentElement ?? document;
    return Array.from(searchRoot.querySelectorAll('button, a')).filter(el => {
      const text = el.textContent.replace(/\s+/g, ' ').trim();
      return /^\d+$/.test(text) && parseInt(text) >= 1 && parseInt(text) <= 9999;
    });
  }

  // The "next group" button (>) sits immediately after the last visible page number.
  // We find it positionally — no reliance on class names or text content.
  function getNextGroupBtn() {
    const pageBtns = getVisiblePageBtns();
    if (pageBtns.length === 0) return null;

    const last = pageBtns[pageBtns.length - 1];
    const parent = last.parentElement;
    if (!parent) return null;

    // Walk siblings after the last page-number button
    let passed = false;
    for (const child of parent.children) {
      if (!passed) {
        if (child === last || child.contains(last)) passed = true;
        continue;
      }
      const btn = child.matches('button, a') ? child : child.querySelector('button, a');
      if (btn && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true') return btn;
    }
    return null;
  }

  // Find a specific page-number button among the currently visible page buttons.
  function findPageBtn(label) {
    return getVisiblePageBtns().find(el =>
      el.textContent.replace(/\s+/g, ' ').trim() === label &&
      !el.disabled &&
      el.getAttribute('aria-disabled') !== 'true' &&
      el.getAttribute('aria-current') !== 'page'
    ) ?? null;
  }

  async function goToNextPage(nextNum) {
    const prevSig = sectionSignature();
    const label = String(nextNum);

    // If the target page button is not yet visible, click the ">" arrow
    // (next group) until it appears. Coupang shows 10 pages per group.
    async function revealPageBtn() {
      let btn = findPageBtn(label);
      if (btn) return btn;

      for (let i = 0; i < 20; i++) {
        const nextGroup = getNextGroupBtn();
        if (!nextGroup) break;

        realClick(nextGroup);
        await sleep(800); // wait for new page numbers to render

        btn = findPageBtn(label);
        if (btn) return btn;
      }
      return null;
    }

    const btn = await revealPageBtn();
    if (!btn) return false;

    btn.scrollIntoView({ behavior: 'instant', block: 'nearest' });
    await sleep(200);
    realClick(btn);
    await sleep(800);

    // Wait up to 15s for review content to change
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline) {
      await sleep(600);
      const sig = sectionSignature();
      if (sig && sig !== prevSig) return true;
    }
    return false;
  }

  // ── Main ──
  const opened = await openReviewSection();
  if (!opened) {
    return { ok: false, error: 'Không tìm thấy phần đánh giá. Hãy vào trang sản phẩm Coupang và thử lại.' };
  }

  await waitForEl('.sdp-review article, .product-review article', 6000);

  const allReviews = [];
  const seenKeys = new Set();

  for (let page = 1; page <= maxPages; page++) {
    const pageRows = extractPage(page);
    let added = 0;
    for (const r of pageRows) {
      const key = r.review_id || r.content.slice(0, 50);
      if (key && !seenKeys.has(key)) {
        seenKeys.add(key);
        allReviews.push(r);
        added++;
      }
    }

    if (added === 0 && page > 1) break;
    if (page >= maxPages) break;

    const ok = await goToNextPage(page + 1);
    if (!ok) break;
  }

  return { ok: true, reviews: allReviews };
}


// ─── Detect total review pages (injected into tab) ───────────────────────────
async function detectTotalPages() {
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  function realClick(el) {
    for (const type of ['mousedown', 'mouseup', 'click'])
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true }));
  }

  function getPaginationArea() {
    const nextBtn = document.querySelector('button.sdp-review__article__page__next');
    if (nextBtn) return nextBtn.closest('ol, ul, nav, div[class*="page"]') ?? nextBtn.parentElement;
    return document.querySelector('[class*="sdp-review__article__page"], [class*="review__article__page"]');
  }

  function getMaxVisible() {
    const root = getPaginationArea() ?? document;
    let max = 0;
    for (const el of root.querySelectorAll('button, a')) {
      const text = el.textContent.replace(/\s+/g, ' ').trim();
      if (!/^\d+$/.test(text)) continue;
      const n = parseInt(text);
      if (n > max && n < 10000) max = n;
    }
    return max;
  }

  function getNextGroupBtn() {
    return (
      document.querySelector('button.sdp-review__article__page__next') ||
      Array.from(document.querySelectorAll('button, a')).find(el => {
        const cls = el.className || '';
        const text = el.textContent.replace(/\s+/g, ' ').trim();
        return (cls.includes('page__next') || text === '다음') &&
               !el.disabled && el.getAttribute('aria-disabled') !== 'true';
      })
    );
  }

  let max = getMaxVisible();
  if (max === 0) return 0;

  // Keep clicking "next group" arrow until it disappears or max stops growing
  for (let i = 0; i < 200; i++) {
    const btn = getNextGroupBtn();
    if (!btn) break;

    realClick(btn);
    await sleep(400);

    const newMax = getMaxVisible();
    if (newMax <= max) break;
    max = newMax;
  }

  return max;
}


// ─── Popup UI logic ───────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  const statusEl    = document.getElementById('status');
  const mainEl      = document.getElementById('main');
  const warnEl      = document.getElementById('notOnCoupang');
  const btn         = document.getElementById('scrapeBtn');
  const scrapeAllBtn = document.getElementById('scrapeAllBtn');
  const pagesIn     = document.getElementById('pages');

  function setStatus(msg, kind) {
    statusEl.textContent = msg;
    statusEl.className = kind;
  }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  if (!tab.url?.includes('coupang.com')) {
    warnEl.hidden = false;
    return;
  }
  mainEl.hidden = false;

  // Auto-detect total pages and prefill input
  btn.disabled = true;
  setStatus('Đang đếm số trang...', 'loading');
  try {
    const [{ result: total }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: detectTotalPages,
    });
    if (total > 0) {
      pagesIn.value = total;
      setStatus(`Tìm thấy ${total} trang đánh giá.`, 'success');
    } else {
      setStatus('Chưa thấy phần đánh giá — hãy cuộn xuống trước.', 'error');
    }
  } catch {
    setStatus('', '');
  } finally {
    btn.disabled = false;
    scrapeAllBtn.disabled = false;
  }

  async function runScrape(maxPages) {
    btn.disabled = true;
    scrapeAllBtn.disabled = true;
    setStatus('Đang lấy đánh giá... (có thể mất vài phút)', 'loading');
    try {
      const [{ result }] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: scrapeAllReviews,
        args: [maxPages],
      });
      if (!result.ok) { setStatus(result.error, 'error'); return; }
      if (result.reviews.length === 0) { setStatus('Không tìm thấy đánh giá nào.', 'error'); return; }
      downloadExcel(result.reviews);
      setStatus(`Hoàn tất! Đã tải ${result.reviews.length} đánh giá.`, 'success');
    } catch (err) {
      setStatus(`Lỗi: ${err.message}`, 'error');
    } finally {
      btn.disabled = false;
      scrapeAllBtn.disabled = false;
    }
  }

  scrapeAllBtn.addEventListener('click', () => runScrape(9999));
  btn.addEventListener('click', () => runScrape(parseInt(pagesIn.value) || 9999));
});

function downloadExcel(reviews) {
  const cols = [
    'product_url', 'review_id', 'author', 'rating',
    'headline', 'content', 'option_text',
    'helpful_count', 'review_date', 'collected_at', 'page_number',
  ];
  const header = [
    'URL sản phẩm', 'ID đánh giá', 'Tác giả', 'Sao',
    'Tiêu đề', 'Nội dung', 'Tuỳ chọn',
    'Hữu ích', 'Ngày đánh giá', 'Thời điểm lấy', 'Trang',
  ];

  const escape = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';

  const lines = [
    header.map(escape).join(','),
    ...reviews.map(r => cols.map(c => escape(r[c])).join(',')),
  ];

  // UTF-8 BOM ensures Korean text displays correctly when opened in Excel
  const bom = '﻿';
  const blob = new Blob([bom + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const url  = URL.createObjectURL(blob);
  const a    = Object.assign(document.createElement('a'), {
    href: url,
    download: `coupang_reviews_${Date.now()}.csv`,
  });
  a.click();
  URL.revokeObjectURL(url);
}
