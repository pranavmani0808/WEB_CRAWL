import asyncio
import uuid
import logging
from app.workers.celery_app import celery_app
from app.crawler.crawler_engine import CrawlerEngine
from app.core.config import settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)


async def _run_crawl(crawl_job_id: uuid.UUID):
    """Create a fresh DB engine & session factory per task, then run the engine."""
    # A new engine must be created inside the event loop so asyncpg attaches to it correctly.
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    try:
        crawler = CrawlerEngine(crawl_job_id, session_factory=session_factory)
        await crawler.execute()
    finally:
        await engine.dispose()


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
