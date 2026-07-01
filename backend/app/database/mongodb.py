from beanie import init_beanie, PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorClient as AsyncClient
from app.core.config import settings


async def init_db():
    """Initialize MongoDB connection and Beanie ODM."""
    client = AsyncClient(settings.MONGODB_URL)

    # Import all models so Beanie can register them
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

    await init_beanie(
        database=client.WEB_CRAWL,
        document_models=[
            User, Domain, CrawlJob, URL, Sitemap, Subdomain,
            CrawlLog, CrawlStatistics, Report, Export,
            CrawlHistory, CrawlComparison, TokenBlocklist, Session
        ]
    )

    return client
