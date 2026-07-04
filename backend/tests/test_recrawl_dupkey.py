import uuid

from app.core.constants import URLCrawlStatus
from app.crawler.crawler_engine import CrawlerEngine, get_url_hash
from app.models.crawl_job import CrawlJob
from app.models.domain import Domain
from app.models.url import URL


class _NoSitemapParser:
    """Sitemap parser stub that finds nothing, forcing the fallback path."""
    async def discover_sitemaps(self, url, on_sitemap_parsed=None):
        return


async def test_sitemapless_fallback_survives_existing_url_hash(mongo_db):
    """Regression: crawling a domain whose homepage URL already exists in the
    collection (e.g. under a duplicate 'Ahrefs.com' vs 'ahrefs.com' record)
    used to crash the whole crawl with an E11000 duplicate-key error on the
    global-unique url_hash index. The fallback must reuse the existing row.
    """
    homepage = "https://ahrefs.com"

    # A pre-existing row for the same URL, owned by a DIFFERENT domain record
    # (the casing-duplicate). Its url_hash collides with what the fallback
    # will try to insert.
    other_domain_id = uuid.uuid4()
    existing = URL(
        domain_id=other_domain_id,
        sitemap_id=uuid.uuid4(),
        url=homepage,
        url_hash=get_url_hash(homepage),
        crawl_status=URLCrawlStatus.CHECKED.value,
        status_code=200,
    )
    await existing.insert()

    domain = Domain(
        user_id=uuid.uuid4(),
        original_url=homepage,
        normalized_url=homepage,
        domain="ahrefs.com",
    )
    await domain.insert()

    job = CrawlJob(domain_id=domain.id, user_id=uuid.uuid4(), status="running")
    await job.insert()

    engine = CrawlerEngine(job.id)
    engine.job = job
    engine.domain = domain
    engine.sitemap_parser = _NoSitemapParser()

    # Must not raise E11000.
    await engine._stage_sitemap_discovery()

    # The existing row is reused and re-homed to this domain, queued pending -
    # and crucially there is still exactly one row for that url_hash.
    rows = await URL.find(URL.url_hash == get_url_hash(homepage)).to_list()
    assert len(rows) == 1
    assert rows[0].domain_id == domain.id
    assert rows[0].crawl_status == URLCrawlStatus.PENDING.value
