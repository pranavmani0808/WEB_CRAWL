"""Selective JavaScript rendering for SPA/client-rendered pages.

Most pages don't need a browser - fetching and parsing raw HTML is 10-100x
cheaper. The crawler only escalates to headless Chromium when the raw HTML
looks like an empty client-side app shell (see looks_js_rendered), and the
number of rendered pages per crawl is capped so a fully client-rendered
1000-page site can't pin the worker's memory/CPU for an hour.
"""
import asyncio
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# <div id="root"></div> and friends - the tell-tale mount point of a
# client-rendered app with no server-rendered content inside it.
_APP_SHELL_RE = re.compile(
    r'<div[^>]+id=["\'](?:root|app|__next|___gatsby|q-app|svelte)["\'][^>]*>\s*(?:<!--[^>]*-->\s*)*</div>',
    re.IGNORECASE,
)

_NOSCRIPT_HINTS = (
    "enable javascript",
    "javascript is required",
    "javascript to run this app",
    "doesn't work properly without javascript",
)


_INLINE_SCRIPT_RE = re.compile(r"<script[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)


def looks_js_rendered(html: str, word_count: int) -> bool:
    """Heuristic: does this page's raw HTML look like an empty JS app shell?

    A false positive costs one multi-second browser render (bounded by the
    per-crawl cap); a false negative means the page gets audited on its raw
    HTML like the crawler always used to. Tuned against real cases: React/
    Next-style empty mount divs, "enable JavaScript" noscript fallbacks, and
    pages that ship their content as data inside an inline script (e.g.
    quotes.toscrape.com/js embeds all quotes in one <script> block and
    renders them client-side - barely any scripts, almost no visible text).
    """
    if not html or word_count > 80:
        return False

    lower = html.lower()

    if _APP_SHELL_RE.search(html):
        return True

    if any(hint in lower for hint in _NOSCRIPT_HINTS):
        return True

    if word_count >= 40:
        return False

    # Nearly no visible text: decide by how much JS the page carries.
    script_count = lower.count("<script")
    inline_script_bytes = sum(len(m) for m in _INLINE_SCRIPT_RE.findall(html))
    return script_count >= 2 or inline_script_bytes > 1500


class JsRenderer:
    """Lazily-launched headless Chromium shared by one crawl job.

    The browser only starts if a page actually needs rendering, at most
    `concurrency` pages render at once, and at most `max_pages` render per
    crawl. Every failure degrades gracefully to the raw HTML.
    """

    def __init__(self, max_pages: int = 80, concurrency: int = 2, timeout_ms: int = 20000):
        self.max_pages = max_pages
        self.timeout_ms = timeout_ms
        self._sem = asyncio.Semaphore(concurrency)
        self._launch_lock = asyncio.Lock()
        self._playwright = None
        self._browser = None
        self._unavailable = False
        self.rendered_count = 0

    async def _ensure_browser(self) -> bool:
        if self._browser:
            return True
        if self._unavailable:
            return False
        async with self._launch_lock:
            if self._browser:
                return True
            if self._unavailable:
                return False
            try:
                from playwright.async_api import async_playwright
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"]
                )
                logger.info("Headless Chromium launched for JS rendering")
                return True
            except Exception as e:
                # Playwright not installed / chromium missing / launch failed:
                # disable rendering for this crawl rather than failing pages.
                logger.warning(f"JS rendering unavailable, continuing with raw HTML: {e}")
                self._unavailable = True
                return False

    async def render(self, url: str) -> Optional[str]:
        """Return the rendered DOM's HTML, or None if rendering is
        unavailable, capped out, or failed for this URL."""
        if self.rendered_count >= self.max_pages:
            return None
        if not await self._ensure_browser():
            return None

        async with self._sem:
            if self.rendered_count >= self.max_pages:
                return None
            page = await self._browser.new_page()
            try:
                # networkidle is the closest signal for "the SPA finished
                # loading data"; some sites keep sockets open forever, so a
                # timeout there still falls through to grabbing whatever DOM
                # exists at that point.
                try:
                    await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
                except Exception:
                    pass
                html = await page.content()
                self.rendered_count += 1
                return html
            except Exception as e:
                logger.warning(f"JS render failed for {url}: {e}")
                return None
            finally:
                await page.close()

    async def close(self):
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"Error shutting down JS renderer: {e}")
        finally:
            self._browser = None
            self._playwright = None
