import uuid

from app.core.config import settings
from app.models.crawl_job import CrawlJob


async def test_per_user_concurrency_limit_blocks_excess_crawls(app_client, registered_user, monkeypatch):
    """A user can't exceed MAX_CONCURRENT_CRAWLS_PER_USER in-flight crawls."""
    monkeypatch.setattr(settings, "MAX_CONCURRENT_CRAWLS_PER_USER", 2)
    headers, _ = registered_user

    # First two are accepted (they stay "pending" since the celery dispatch is
    # a no-op in tests).
    r1 = await app_client.post("/api/crawl", json={"url": "one.com"}, headers=headers)
    r2 = await app_client.post("/api/crawl", json={"url": "two.com"}, headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200

    # Third is rejected with 429.
    r3 = await app_client.post("/api/crawl", json={"url": "three.com"}, headers=headers)
    assert r3.status_code == 429
    assert "already have" in r3.json()["message"]


async def test_limit_is_per_user_not_global(app_client, app_client_extra_user, registered_user, monkeypatch):
    monkeypatch.setattr(settings, "MAX_CONCURRENT_CRAWLS_PER_USER", 1)
    headers, _ = registered_user
    other = app_client_extra_user

    # User A uses their 1 slot.
    assert (await app_client.post("/api/crawl", json={"url": "a.com"}, headers=headers)).status_code == 200
    assert (await app_client.post("/api/crawl", json={"url": "a2.com"}, headers=headers)).status_code == 429

    # User B is unaffected - still has their own slot.
    assert (await app_client.post("/api/crawl", json={"url": "b.com"}, headers=other)).status_code == 200


async def test_finished_crawls_free_the_slot(app_client, registered_user, monkeypatch):
    monkeypatch.setattr(settings, "MAX_CONCURRENT_CRAWLS_PER_USER", 1)
    headers, _ = registered_user

    job_id = (await app_client.post("/api/crawl", json={"url": "done.com"}, headers=headers)).json()["job_id"]
    # at limit now
    assert (await app_client.post("/api/crawl", json={"url": "next.com"}, headers=headers)).status_code == 429

    # complete the first job -> slot frees
    job = await CrawlJob.get(uuid.UUID(job_id))
    job.status = "completed"
    await job.save()

    assert (await app_client.post("/api/crawl", json={"url": "next.com"}, headers=headers)).status_code == 200
