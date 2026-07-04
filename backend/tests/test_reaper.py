import uuid
from datetime import datetime, timedelta

from app.models.crawl_job import CrawlJob
from app.models.crawl_log import CrawlLog
from app.models.url import URL
from app.workers.tasks import _reap_stale_jobs


async def test_reaper_fails_silent_job_and_requeues_inflight_urls(mongo_db):
    domain_id = uuid.uuid4()
    stale = CrawlJob(
        domain_id=domain_id, user_id=uuid.uuid4(), status="running",
        started_at=datetime.utcnow() - timedelta(hours=1),
        last_activity_at=datetime.utcnow() - timedelta(minutes=30),
    )
    await stale.insert()

    stuck_url = URL(
        domain_id=domain_id, sitemap_id=uuid.uuid4(),
        url="https://stale.com/x", url_hash="stale-x", crawl_status="checking",
    )
    await stuck_url.insert()

    reaped = await _reap_stale_jobs()

    assert str(stale.id) in reaped
    refreshed = await CrawlJob.get(stale.id)
    assert refreshed.status == "failed"
    assert refreshed.completed_at is not None

    requeued = await URL.get(stuck_url.id)
    assert requeued.crawl_status == "pending"

    logs = await CrawlLog.find(CrawlLog.crawl_job_id == stale.id).to_list()
    assert any("Retry" in l.message for l in logs)


async def test_reaper_leaves_active_and_terminal_jobs_alone(mongo_db):
    healthy = CrawlJob(
        domain_id=uuid.uuid4(), user_id=uuid.uuid4(), status="running",
        started_at=datetime.utcnow() - timedelta(hours=2),
        last_activity_at=datetime.utcnow() - timedelta(minutes=2),
    )
    await healthy.insert()

    done = CrawlJob(
        domain_id=uuid.uuid4(), user_id=uuid.uuid4(), status="completed",
        started_at=datetime.utcnow() - timedelta(days=2),
    )
    await done.insert()

    reaped = await _reap_stale_jobs()
    assert reaped == []
    assert (await CrawlJob.get(healthy.id)).status == "running"
    assert (await CrawlJob.get(done.id)).status == "completed"


async def test_reaper_uses_started_at_for_legacy_jobs_without_heartbeat(mongo_db):
    legacy = CrawlJob(
        domain_id=uuid.uuid4(), user_id=uuid.uuid4(), status="stopping",
        started_at=datetime.utcnow() - timedelta(hours=3),
        last_activity_at=None,
    )
    await legacy.insert()

    reaped = await _reap_stale_jobs()
    assert str(legacy.id) in reaped
    assert (await CrawlJob.get(legacy.id)).status == "failed"
