import uuid
from datetime import datetime, timedelta

from app.models.crawl_job import CrawlJob
from app.models.url_snapshot import UrlSnapshot


async def _make_completed_job(app_client, headers, url, created_at):
    job_id = (await app_client.post("/api/crawl", json={"url": url}, headers=headers)).json()["job_id"]
    job = await CrawlJob.get(uuid.UUID(job_id))
    job.status = "completed"
    job.created_at = created_at
    job.total_urls_checked = 3
    await job.save()
    return job


async def test_comparable_jobs_excludes_self_and_snapshotless_jobs(app_client, registered_user):
    headers, _ = registered_user
    now = datetime.utcnow()

    job_a = await _make_completed_job(app_client, headers, "diffsite.com", now - timedelta(days=2))
    job_b = await _make_completed_job(app_client, headers, "diffsite.com", now - timedelta(days=1))

    # Only job_b gets a snapshot - job_a should be excluded from "comparable"
    # results the same way a pre-comparison-feature job would be.
    await UrlSnapshot(crawl_job_id=job_b.id, domain_id=job_b.domain_id, url="https://diffsite.com/", url_hash="h1", status_code=200).insert()

    # job_a has no snapshot, but job_b does - job_a should see job_b as comparable.
    resp = await app_client.get(f"/api/crawl/jobs/{job_a.id}/comparable", headers=headers)
    assert resp.status_code == 200
    assert [c["id"] for c in resp.json()] == [str(job_b.id)]

    # job_b's only other job (job_a) has no snapshot, so nothing comparable.
    resp2 = await app_client.get(f"/api/crawl/jobs/{job_b.id}/comparable", headers=headers)
    assert resp2.status_code == 200
    assert resp2.json() == []


async def test_compare_detects_added_removed_broken_and_fixed_urls(app_client, registered_user):
    headers, _ = registered_user
    now = datetime.utcnow()

    older = await _make_completed_job(app_client, headers, "quotes.toscrape.com", now - timedelta(days=1))
    newer = await _make_completed_job(app_client, headers, "quotes.toscrape.com", now)

    # Stable page, unchanged.
    await UrlSnapshot(crawl_job_id=older.id, domain_id=older.domain_id, url="https://quotes.toscrape.com/", url_hash="home", status_code=200, status_category="success").insert()
    await UrlSnapshot(crawl_job_id=newer.id, domain_id=newer.domain_id, url="https://quotes.toscrape.com/", url_hash="home", status_code=200, status_category="success").insert()

    # Was broken, now fixed (404 -> 200).
    await UrlSnapshot(crawl_job_id=older.id, domain_id=older.domain_id, url="https://quotes.toscrape.com/tag/love/", url_hash="tag-love", status_code=404, status_category="client_error").insert()
    await UrlSnapshot(crawl_job_id=newer.id, domain_id=newer.domain_id, url="https://quotes.toscrape.com/tag/love/", url_hash="tag-love", status_code=200, status_category="success").insert()

    # Was fine, now broken (200 -> 500).
    await UrlSnapshot(crawl_job_id=older.id, domain_id=older.domain_id, url="https://quotes.toscrape.com/author/einstein/", url_hash="author-einstein", status_code=200, status_category="success").insert()
    await UrlSnapshot(crawl_job_id=newer.id, domain_id=newer.domain_id, url="https://quotes.toscrape.com/author/einstein/", url_hash="author-einstein", status_code=500, status_category="server_error").insert()

    # Removed in the newer crawl.
    await UrlSnapshot(crawl_job_id=older.id, domain_id=older.domain_id, url="https://quotes.toscrape.com/old-page/", url_hash="old-page", status_code=200, status_category="success").insert()

    # Newly added in the newer crawl.
    await UrlSnapshot(crawl_job_id=newer.id, domain_id=newer.domain_id, url="https://quotes.toscrape.com/new-page/", url_hash="new-page", status_code=200, status_category="success").insert()

    resp = await app_client.get(f"/api/crawl/jobs/{older.id}/compare/{newer.id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["older_job"]["id"] == str(older.id)
    assert body["newer_job"]["id"] == str(newer.id)
    assert body["summary"] == {
        "urls_added": 1,
        "urls_removed": 1,
        "newly_broken": 1,
        "newly_fixed": 1,
        "status_changed": 2,
    }
    assert body["added_urls"] == ["https://quotes.toscrape.com/new-page/"]
    assert body["removed_urls"] == ["https://quotes.toscrape.com/old-page/"]
    assert body["newly_fixed"][0] == {"url": "https://quotes.toscrape.com/tag/love/", "old_status": 404, "new_status": 200}
    assert body["newly_broken"][0] == {"url": "https://quotes.toscrape.com/author/einstein/", "old_status": 200, "new_status": 500}


async def test_compare_rejects_jobs_from_different_domains(app_client, registered_user):
    headers, _ = registered_user
    now = datetime.utcnow()
    job_a = await _make_completed_job(app_client, headers, "siteone.com", now - timedelta(days=1))
    job_b = await _make_completed_job(app_client, headers, "sitetwo.com", now)

    for job in (job_a, job_b):
        await UrlSnapshot(crawl_job_id=job.id, domain_id=job.domain_id, url="https://x/", url_hash="x", status_code=200).insert()

    resp = await app_client.get(f"/api/crawl/jobs/{job_a.id}/compare/{job_b.id}", headers=headers)
    assert resp.status_code == 400


async def test_compare_returns_404_when_a_job_has_no_snapshots(app_client, registered_user):
    headers, _ = registered_user
    now = datetime.utcnow()
    older = await _make_completed_job(app_client, headers, "nosnap.com", now - timedelta(days=1))
    newer = await _make_completed_job(app_client, headers, "nosnap.com", now)
    await UrlSnapshot(crawl_job_id=newer.id, domain_id=newer.domain_id, url="https://nosnap.com/", url_hash="h", status_code=200).insert()

    resp = await app_client.get(f"/api/crawl/jobs/{older.id}/compare/{newer.id}", headers=headers)
    assert resp.status_code == 404
