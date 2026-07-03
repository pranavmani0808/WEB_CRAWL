import uuid

from app.models.crawl_job import CrawlJob


async def test_start_crawl_creates_domain_and_job(app_client, registered_user):
    headers, _ = registered_user
    resp = await app_client.post("/api/crawl", json={"url": "example.com"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"]
    assert body["domain_id"]


async def test_start_crawl_reuses_existing_domain(app_client, registered_user):
    headers, _ = registered_user
    first = await app_client.post("/api/crawl", json={"url": "example.com"}, headers=headers)
    second = await app_client.post("/api/crawl", json={"url": "https://example.com"}, headers=headers)
    assert first.json()["domain_id"] == second.json()["domain_id"]
    assert first.json()["job_id"] != second.json()["job_id"]


async def test_list_jobs_only_returns_current_users_jobs(app_client, app_client_extra_user, registered_user):
    headers, _ = registered_user
    other_headers = app_client_extra_user

    await app_client.post("/api/crawl", json={"url": "mine.com"}, headers=headers)
    await app_client.post("/api/crawl", json={"url": "theirs.com"}, headers=other_headers)

    resp = await app_client.get("/api/crawl/jobs", headers=headers)
    assert resp.status_code == 200
    jobs = resp.json()
    assert len(jobs) == 1
    assert jobs[0]["domain"] == "mine.com"


async def test_retry_all_requeues_both_pending_and_failed_jobs(app_client, registered_user):
    """Regression test: retry-pending used to only match status == "pending",
    which made "Retry All" a silent no-op for jobs that had already flipped to
    "failed" - the exact case the "Jobs stuck?" banner is meant to fix.
    """
    headers, _ = registered_user

    pending_job_id = (await app_client.post("/api/crawl", json={"url": "pending.com"}, headers=headers)).json()["job_id"]
    failed_job_id = (await app_client.post("/api/crawl", json={"url": "failed.com"}, headers=headers)).json()["job_id"]

    failed_job = await CrawlJob.get(uuid.UUID(failed_job_id))
    failed_job.status = "failed"
    failed_job.total_urls_checked = 12
    failed_job.urls_4xx = 12
    await failed_job.save()

    resp = await app_client.post("/api/crawl/jobs/retry-pending", headers=headers)
    assert resp.status_code == 200
    dispatched = set(resp.json()["job_ids"])
    assert pending_job_id in dispatched
    assert failed_job_id in dispatched

    refreshed_failed = await CrawlJob.get(uuid.UUID(failed_job_id))
    assert refreshed_failed.status == "pending"
    assert refreshed_failed.total_urls_checked == 0
    assert refreshed_failed.urls_4xx == 0


async def test_retry_all_ignores_completed_jobs(app_client, registered_user):
    headers, _ = registered_user
    job_id = (await app_client.post("/api/crawl", json={"url": "done.com"}, headers=headers)).json()["job_id"]

    job = await CrawlJob.get(uuid.UUID(job_id))
    job.status = "completed"
    await job.save()

    resp = await app_client.post("/api/crawl/jobs/retry-pending", headers=headers)
    assert resp.status_code == 200
    assert job_id not in resp.json()["job_ids"]

    refreshed = await CrawlJob.get(uuid.UUID(job_id))
    assert refreshed.status == "completed"


async def test_cancel_then_delete_job(app_client, registered_user):
    headers, _ = registered_user
    job_id = (await app_client.post("/api/crawl", json={"url": "cancelme.com"}, headers=headers)).json()["job_id"]

    cancel_resp = await app_client.post(f"/api/crawl/jobs/{job_id}/cancel", headers=headers)
    assert cancel_resp.status_code == 200

    job = await CrawlJob.get(uuid.UUID(job_id))
    assert job.status == "stopping"

    delete_resp = await app_client.delete(f"/api/crawl/jobs/{job_id}", headers=headers)
    assert delete_resp.status_code == 200

    assert await CrawlJob.get(uuid.UUID(job_id)) is None


async def test_cannot_access_another_users_job(app_client, app_client_extra_user, registered_user):
    other_headers = app_client_extra_user
    job_id = (await app_client.post("/api/crawl", json={"url": "private.com"}, headers=other_headers)).json()["job_id"]

    headers, _ = registered_user
    resp = await app_client.get(f"/api/crawl/jobs/{job_id}", headers=headers)
    assert resp.status_code == 404
