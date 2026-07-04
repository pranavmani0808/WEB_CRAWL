from motor.motor_asyncio import AsyncIOMotorClient as AsyncClient
from beanie import init_beanie
from app.core.config import settings

# Global client reference
_mongodb_client: AsyncClient = None


async def init_db():
    """Initialize MongoDB connection and Beanie ODM."""
    global _mongodb_client

    _mongodb_client = AsyncClient(settings.MONGODB_URL)

    # Import all models
    from app.models.user import User
    from app.models.domain import Domain
    from app.models.crawl_job import CrawlJob
    from app.models.url import URL
    from app.models.sitemap import Sitemap
    from app.models.subdomain import Subdomain
    from app.models.crawl_log import CrawlLog
    from app.models.crawl_statistics import CrawlStatistics
    from app.models.report import Report
    from app.models.export import Export
    from app.models.crawl_history import CrawlHistory
    from app.models.crawl_comparison import CrawlComparison
    from app.models.token_blocklist import TokenBlocklist
    from app.models.session import Session
    from app.models.url_snapshot import UrlSnapshot
    from app.models.crawl_schedule import CrawlSchedule

    await init_beanie(
        database=_mongodb_client.WEB_CRAWL,
        document_models=[
            User, Domain, CrawlJob, URL, Sitemap, Subdomain,
            CrawlLog, CrawlStatistics, Report, Export,
            CrawlHistory, CrawlComparison, TokenBlocklist, Session,
            UrlSnapshot, CrawlSchedule
        ]
    )

    return _mongodb_client


async def close_db():
    """Close MongoDB connection."""
    global _mongodb_client
    if _mongodb_client:
        _mongodb_client.close()


async def get_db():
    """Dependency for API endpoints (returns None for Beanie).

    With Beanie, documents can be accessed directly without a session.
    This is kept for backwards compatibility with existing endpoint patterns.
    """
    return None
