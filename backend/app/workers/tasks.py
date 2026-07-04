import asyncio
import uuid
import logging
from datetime import datetime, timedelta
from app.workers.celery_app import celery_app
from app.crawler.crawler_engine import CrawlerEngine
from app.database.database import init_db, close_db

logger = logging.getLogger(__name__)

SCHEDULE_INTERVALS = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
}


async def _run_crawl(crawl_job_id: uuid.UUID):
    """Initialize MongoDB connection and run the crawler engine."""
    # Initialize Beanie connection for this task
    await init_db()

    try:
        crawler = CrawlerEngine(crawl_job_id)
        await crawler.execute()
    finally:
        await close_db()


async def _dispatch_due_schedules() -> list:
    """Start a crawl job for every enabled schedule whose next_run_at has
    passed, then advance next_run_at by the schedule's interval.

    next_run_at is advanced from *now* rather than from the previous value,
    so a schedule that was missed for a while (beat down, deploy gap) runs
    once and resumes its cadence instead of firing repeatedly to catch up.
    Returns the started job IDs (as strings) for logging/tests.
    """
    from app.models.crawl_schedule import CrawlSchedule
    from app.models.crawl_job import CrawlJob
    from app.core.config import settings

    now = datetime.utcnow()
    due = await CrawlSchedule.find(
        CrawlSchedule.enabled == True,  # noqa: E712 - Beanie expression syntax
        CrawlSchedule.next_run_at <= now,
    ).to_list()

    dispatched = []
    for schedule in due:
        job = CrawlJob(
            domain_id=schedule.domain_id,
            user_id=schedule.user_id,
            status="pending",
            max_workers=settings.CRAWLER_MAX_WORKERS,
            timeout_seconds=settings.CRAWLER_TIMEOUT_SECONDS,
            respect_robots_txt=settings.CRAWLER_RESPECT_ROBOTS_TXT,
            follow_redirects=settings.CRAWLER_FOLLOW_REDIRECTS,
            meta_data={"scheduled": True, "schedule_id": str(schedule.id)},
        )
        await job.insert()

        interval = SCHEDULE_INTERVALS.get(schedule.frequency, SCHEDULE_INTERVALS["daily"])
        schedule.last_run_at = now
        schedule.next_run_at = now + interval
        await schedule.save()

        crawl_domain_task.delay(str(job.id))
        dispatched.append(str(job.id))
        logger.info(f"Scheduled audit dispatched: job {job.id} for domain {schedule.domain_id} ({schedule.frequency})")

    return dispatched


STALE_JOB_TIMEOUT = timedelta(minutes=10)


async def _reap_stale_jobs() -> list:
    """Fail any running/stopping job whose heartbeat has gone silent.

    A worker process killed mid-crawl (OOM SIGKILL, deploy restart) can't
    mark its own job failed, so without this the job sits in "running"
    forever - the UI polls it endlessly and Retry is never offered. In-flight
    URLs are reset to pending so a retry re-checks them cleanly.
    Returns the reaped job IDs (as strings).
    """
    from app.models.crawl_job import CrawlJob
    from app.models.crawl_log import CrawlLog
    from app.models.url import URL

    now = datetime.utcnow()
    live_jobs = await CrawlJob.find({"status": {"$in": ["running", "stopping"]}}).to_list()

    reaped = []
    for job in live_jobs:
        heartbeat = job.last_activity_at or job.started_at or job.created_at
        if heartbeat and (now - heartbeat) < STALE_JOB_TIMEOUT:
            continue

        job.status = "failed"
        job.completed_at = now
        await job.save()

        await URL.find(
            URL.domain_id == job.domain_id,
            URL.crawl_status == "checking",
        ).update({"$set": {"crawl_status": "pending"}})

        await CrawlLog(
            crawl_job_id=job.id,
            level="error",
            message=(
                "Crawl marked failed: no progress for over "
                f"{int(STALE_JOB_TIMEOUT.total_seconds() // 60)} minutes. The crawl worker likely "
                "ran out of memory or was restarted mid-crawl. Use Retry to re-run this audit."
            ),
            event_type="crawl_reaped",
        ).insert()

        reaped.append(str(job.id))
        logger.warning(f"Reaped stale job {job.id} (last activity: {heartbeat})")

    return reaped


@celery_app.task(name="app.workers.tasks.reap_stale_jobs")
def reap_stale_jobs():
    """Beat-invoked: fail jobs whose worker died without marking them."""
    async def _run():
        await init_db()
        try:
            return await _reap_stale_jobs()
        finally:
            await close_db()

    try:
        reaped = asyncio.run(_run())
        return {"status": "success", "reaped": reaped}
    except Exception as e:
        logger.exception(f"reap_stale_jobs failed: {e}")
        return {"status": "failed", "error": str(e)}


@celery_app.task(name="app.workers.tasks.dispatch_due_schedules")
def dispatch_due_schedules():
    """Beat-invoked: find due CrawlSchedules and start crawls for them."""
    async def _run():
        await init_db()
        try:
            return await _dispatch_due_schedules()
        finally:
            await close_db()

    try:
        dispatched = asyncio.run(_run())
        return {"status": "success", "dispatched": dispatched}
    except Exception as e:
        logger.exception(f"dispatch_due_schedules failed: {e}")
        return {"status": "failed", "error": str(e)}


@celery_app.task(name="app.workers.tasks.crawl_domain_task", bind=True)
def crawl_domain_task(self, crawl_job_id: str):
    """Celery task to asynchronously crawl a domain and perform audit/SEO checks"""
    logger.info(f"Received celery crawl task for job ID: {crawl_job_id}")

    try:
        job_uuid = uuid.UUID(crawl_job_id)
    except ValueError as e:
        logger.error(f"Invalid UUID string provided: {crawl_job_id}")
        return {"status": "failed", "error": f"Invalid UUID: {str(e)}"}

    try:
        asyncio.run(_run_crawl(job_uuid))
        return {"status": "success", "crawl_job_id": crawl_job_id}
    except Exception as e:
        logger.exception(f"Celery task crawl_domain_task failed for job {crawl_job_id}: {e}")
        return {"status": "failed", "error": str(e)}
