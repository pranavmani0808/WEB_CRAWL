import uuid
from datetime import datetime, timedelta

from app.core.constants import URLCrawlStatus
from app.crawler.crawler_engine import CrawlerEngine
from app.crawler.issue_detector import IssueDetector
from app.models.crawl_job import CrawlJob
from app.models.crawl_log import CrawlLog
from app.models.crawl_statistics import CrawlStatistics
from app.models.domain import Domain
from app.models.url import URL


async def test_reporting_stage_uses_projection_and_still_detects_duplicates(mongo_db):
    """The reporting stage projects each checked URL down to a handful of
    fields instead of loading full SEO metadata (all links + images) for
    every page - that end-of-crawl load was its own OOM on big sites. This
    verifies the slim projection still reconstructs what duplication
    detection and the stats rollup need.
    """
    domain = Domain(
        user_id=uuid.uuid4(), original_url="https://rep.com",
        normalized_url="https://rep.com", domain="rep.com",
    )
    await domain.insert()

    job = CrawlJob(domain_id=domain.id, user_id=uuid.uuid4(), status="running")
    job.started_at = datetime.utcnow() - timedelta(minutes=1)
    await job.insert()

    # Two identical pages (planted duplicate) carrying heavy link/image
    # arrays that the projection must NOT need, plus one distinct page.
    heavy = {
        "title": "Same Title Shared By Two Pages",
        "meta_description": "Identical meta description on both pages here.",
        "h1": "Same", "word_count": 500,
        "links": [f"/l{i}" for i in range(300)],
        "images": [{"src": f"/i{i}.png"} for i in range(50)],
    }
    metas = [heavy, dict(heavy), {
        "title": "Totally Different Page", "meta_description": "Nothing alike here.",
        "h1": "Diff", "word_count": 90, "links": [], "images": [],
    }]
    for i, meta in enumerate(metas):
        await URL(
            domain_id=domain.id, sitemap_id=uuid.uuid4(),
            url=f"https://rep.com/p{i}", url_hash=f"rep-{i}",
            crawl_status=URLCrawlStatus.CHECKED.value,
            status_code=200, status_category="success",
            response_time_ms=100, content_type="text/html",
            content_length=1000, meta_data=meta,
        ).insert()

    engine = CrawlerEngine(job.id)
    engine.job = job
    engine.domain = domain
    engine.issue_detector = IssueDetector()
    await engine._stage_reporting()

    stats = await CrawlStatistics.find_one(CrawlStatistics.domain_id == domain.id)
    assert stats is not None
    assert stats.html_urls == 3

    dup_logs = await CrawlLog.find(CrawlLog.crawl_job_id == job.id).to_list()
    dups = [l for l in dup_logs if l.message.startswith("Duplication Issue on")]
    assert len(dups) >= 1
    assert "rep.com/p0" in dups[0].message
