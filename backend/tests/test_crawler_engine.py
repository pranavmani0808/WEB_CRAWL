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


async def test_update_job_progress_aggregates_status_buckets(mongo_db):
    """The aggregation-based stats sync must bucket exactly like the old
    fetch-everything Python loop: error categories win over status codes,
    and only this job's run (updated_at >= started_at) is counted.
    """
    from datetime import datetime, timedelta

    from app.models.crawl_job import CrawlJob as CrawlJobModel

    domain = Domain(
        user_id=uuid.uuid4(),
        original_url="https://agg.com",
        normalized_url="https://agg.com",
        domain="agg.com",
    )
    await domain.insert()

    job = CrawlJobModel(domain_id=domain.id, user_id=uuid.uuid4(), status="running")
    job.started_at = datetime.utcnow() - timedelta(minutes=5)
    await job.insert()

    fixtures = [
        (200, "success", 100),
        (204, "success", 300),
        (301, "redirect", 50),
        (404, "client_error", 150),
        (500, "server_error", None),
        (None, "timeout", None),
        (None, "dns_error", None),
    ]
    for i, (code, category, rt) in enumerate(fixtures):
        await URL(
            domain_id=domain.id,
            sitemap_id=uuid.uuid4(),
            url=f"https://agg.com/{i}",
            url_hash=f"agg-{i}",
            crawl_status=URLCrawlStatus.CHECKED.value,
            status_code=code,
            status_category=category,
            response_time_ms=rt,
        ).insert()

    # A stale URL from a previous run of the same domain must be excluded.
    stale = URL(
        domain_id=domain.id,
        sitemap_id=uuid.uuid4(),
        url="https://agg.com/stale",
        url_hash="agg-stale",
        crawl_status=URLCrawlStatus.CHECKED.value,
        status_code=200,
        status_category="success",
    )
    await stale.insert()
    await URL.find(URL.id == stale.id).update(
        {"$set": {"updated_at": job.started_at - timedelta(days=1)}}
    )

    engine = CrawlerEngine(job.id)
    engine.job = job
    engine.domain = domain
    await engine._update_job_progress()

    assert job.urls_2xx == 2
    assert job.urls_3xx == 1
    assert job.urls_4xx == 1
    assert job.urls_5xx == 1
    assert job.urls_timeout == 1
    assert job.urls_dns_error == 1
    assert job.avg_response_time_ms == int((100 + 300 + 50 + 150) / 4)
    assert job.crawl_speed_urls_per_sec is not None


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
