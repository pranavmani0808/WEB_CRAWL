import os
import sys

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017/test_web_crawl")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-do-not-use-in-prod")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pytest_asyncio
from beanie import init_beanie
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

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

DOCUMENT_MODELS = [
    User, Domain, CrawlJob, URL, Sitemap, Subdomain,
    CrawlLog, CrawlStatistics, Report, Export,
    CrawlHistory, CrawlComparison, TokenBlocklist, Session,
    UrlSnapshot, CrawlSchedule,
]


@pytest_asyncio.fixture
async def mongo_db():
    """A fresh in-memory Mongo (mongomock) database, wired up to Beanie, per test."""
    client = AsyncMongoMockClient()
    db = client["test_web_crawl"]
    await init_beanie(database=db, document_models=DOCUMENT_MODELS)
    return db


@pytest_asyncio.fixture
async def app_client(mongo_db, monkeypatch):
    """An httpx AsyncClient bound directly to the FastAPI app, with the real
    Mongo/Celery startup wiring swapped for the in-memory test double so tests
    never touch production infrastructure.
    """
    import main as main_module
    from app.workers.tasks import crawl_domain_task

    async def _noop_lifecycle():
        return None

    monkeypatch.setattr(main_module, "init_db", _noop_lifecycle)
    monkeypatch.setattr(main_module, "close_db", _noop_lifecycle)
    monkeypatch.setattr(crawl_domain_task, "delay", lambda *args, **kwargs: None)

    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def registered_user(app_client):
    """Registers a user and returns (auth_headers, user_body)."""
    resp = await app_client.post(
        "/api/auth/register",
        json={"email": "tester@example.com", "username": "tester", "password": "supersecret123"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    return headers, body["user"]


@pytest_asyncio.fixture
async def app_client_extra_user(app_client):
    """Auth headers for a second, distinct user sharing the same in-memory DB."""
    resp = await app_client.post(
        "/api/auth/register",
        json={"email": "other@example.com", "username": "other", "password": "supersecret123"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
