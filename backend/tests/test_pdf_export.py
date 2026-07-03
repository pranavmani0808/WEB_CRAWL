import uuid
from datetime import datetime

from app.models.crawl_job import CrawlJob
from app.models.url import URL


async def test_download_pdf_for_completed_job(app_client, registered_user):
    headers, _ = registered_user
    job_id = (await app_client.post("/api/crawl", json={"url": "pdftest.com"}, headers=headers)).json()["job_id"]

    job = await CrawlJob.get(uuid.UUID(job_id))
    job.status = "completed"
    job.started_at = datetime.utcnow()
    job.completed_at = datetime.utcnow()
    job.total_urls_checked = 2
    job.urls_2xx = 1
    job.urls_4xx = 1
    await job.save()

    await URL(
        domain_id=job.domain_id,
        sitemap_id=uuid.uuid4(),
        url="https://pdftest.com/",
        url_hash="pdftest-home",
        status_code=200,
        status_category="success",
        crawl_status="checked",
    ).insert()
    await URL(
        domain_id=job.domain_id,
        sitemap_id=uuid.uuid4(),
        url="https://pdftest.com/missing",
        url_hash="pdftest-missing",
        status_code=404,
        status_category="client_error",
        crawl_status="checked",
    ).insert()

    resp = await app_client.get(f"/api/crawl/jobs/{job_id}/pdf", headers=headers)

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


async def test_download_pdf_for_missing_job_returns_404(app_client, registered_user):
    headers, _ = registered_user
    resp = await app_client.get(f"/api/crawl/jobs/{uuid.uuid4()}/pdf", headers=headers)
    assert resp.status_code == 404
