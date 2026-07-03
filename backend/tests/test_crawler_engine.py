import uuid

import pytest

from app.core.constants import URLCrawlStatus
from app.crawler.crawler_engine import CrawlerEngine
from app.crawler.rate_limiter import RateLimiter
from app.models.domain import Domain
from app.models.url import URL


def make_engine(rate=10.0):
    engine = CrawlerEngine(uuid.uuid4())
    engine.rate_limiter = RateLimiter(requests_per_second=rate)
    engine.domain = type("FakeDomain", (), {"domain": "example.com"})()

    async def _noop_log(*args, **kwargs):
        return None

    engine.log_event = _noop_log
    return engine


async def test_backoff_does_not_trigger_before_threshold():
    engine = make_engine()
    for _ in range(CrawlerEngine.BLOCK_SIGNAL_THRESHOLD - 1):
        await engine._note_response_for_backoff(429)

    assert engine._backed_off is False
    assert engine.rate_limiter.requests_per_second == 10.0


async def test_backoff_triggers_on_threshold_consecutive_block_signals():
    engine = make_engine()
    for _ in range(CrawlerEngine.BLOCK_SIGNAL_THRESHOLD):
        await engine._note_response_for_backoff(429)

    assert engine._backed_off is True
    assert engine.rate_limiter.requests_per_second == pytest.approx(2.5)


async def test_backoff_counts_any_block_signal_status_not_just_429():
    engine = make_engine()
    signals = [403, 429, 202, 403, 429]
    assert len(signals) == CrawlerEngine.BLOCK_SIGNAL_THRESHOLD
    for status in signals:
        await engine._note_response_for_backoff(status)

    assert engine._backed_off is True


async def test_non_block_status_resets_consecutive_counter():
    engine = make_engine()
    await engine._note_response_for_backoff(429)
    await engine._note_response_for_backoff(429)
    await engine._note_response_for_backoff(200)

    assert engine._consecutive_block_signals == 0
    assert engine._backed_off is False


async def test_backoff_only_applies_once():
    engine = make_engine()
    for _ in range(CrawlerEngine.BLOCK_SIGNAL_THRESHOLD):
        await engine._note_response_for_backoff(429)
    assert engine.rate_limiter.requests_per_second == pytest.approx(2.5)

    # A second full run of block signals must not halve the rate again.
    for _ in range(CrawlerEngine.BLOCK_SIGNAL_THRESHOLD):
        await engine._note_response_for_backoff(429)
    assert engine.rate_limiter.requests_per_second == pytest.approx(2.5)


async def test_reset_domain_urls_for_recrawl_clears_previously_checked_urls(mongo_db):
    """Regression test for sitemap-less domains not fully re-crawling: every
    URL previously marked "checked" for a domain must go back to "pending"
    (with its stale result fields cleared) at the start of a new crawl, not
    just ones still stuck mid-check.
    """
    domain = Domain(
        user_id=uuid.uuid4(),
        original_url="https://example.com",
        normalized_url="https://example.com",
        domain="example.com",
    )
    await domain.insert()

    checked_url = URL(
        domain_id=domain.id,
        sitemap_id=uuid.uuid4(),
        url="https://example.com/a",
        url_hash="hash-a",
        crawl_status=URLCrawlStatus.CHECKED.value,
        status_code=200,
        status_category="success",
        response_time_ms=123,
    )
    await checked_url.insert()

    other_domain_url = URL(
        domain_id=uuid.uuid4(),
        sitemap_id=uuid.uuid4(),
        url="https://other.com/a",
        url_hash="hash-b",
        crawl_status=URLCrawlStatus.CHECKED.value,
        status_code=200,
    )
    await other_domain_url.insert()

    engine = CrawlerEngine(uuid.uuid4())
    engine.domain = domain
    await engine._reset_domain_urls_for_recrawl()

    refreshed = await URL.get(checked_url.id)
    assert refreshed.crawl_status == URLCrawlStatus.PENDING.value
    assert refreshed.status_code is None
    assert refreshed.status_category is None
    assert refreshed.response_time_ms is None

    # Only this domain's URLs should be touched.
    untouched = await URL.get(other_domain_url.id)
    assert untouched.crawl_status == URLCrawlStatus.CHECKED.value
    assert untouched.status_code == 200
