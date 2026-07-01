import asyncio
import uuid
import logging
from app.workers.celery_app import celery_app
from app.crawler.crawler_engine import CrawlerEngine
from app.database.database import init_db, close_db

logger = logging.getLogger(__name__)


async def _run_crawl(crawl_job_id: uuid.UUID):
    """Initialize MongoDB connection and run the crawler engine."""
    # Initialize Beanie connection for this task
    await init_db()

    try:
        crawler = CrawlerEngine(crawl_job_id)
        await crawler.execute()
    finally:
        await close_db()


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
