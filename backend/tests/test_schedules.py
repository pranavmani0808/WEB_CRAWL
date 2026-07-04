import uuid
from datetime import datetime, timedelta

from app.models.crawl_job import CrawlJob
from app.models.crawl_schedule import CrawlSchedule


async def _job_for(app_client, headers, url="scheduled.com"):
    return (await app_client.post("/api/crawl", json={"url": url}, headers=headers)).json()["job_id"]


async def test_create_schedule_via_job(app_client, registered_user):
    headers, _ = registered_user
    job_id = await _job_for(app_client, headers)

    resp = await app_client.post(f"/api/crawl/jobs/{job_id}/schedule", json={"frequency": "daily"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["frequency"] == "daily"
    assert body["domain"] == "scheduled.com"
    assert body["enabled"] is True
    assert body["next_run_at"] is not None


async def test_reschedule_same_domain_updates_instead_of_duplicating(app_client, registered_user):
    headers, _ = registered_user
    job_id = await _job_for(app_client, headers)

    await app_client.post(f"/api/crawl/jobs/{job_id}/schedule", json={"frequency": "daily"}, headers=headers)
    resp = await app_client.post(f"/api/crawl/jobs/{job_id}/schedule", json={"frequency": "weekly"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["frequency"] == "weekly"

    listing = (await app_client.get("/api/crawl/schedules", headers=headers)).json()
    assert len(listing) == 1
    assert listing[0]["frequency"] == "weekly"


async def test_invalid_frequency_rejected(app_client, registered_user):
    headers, _ = registered_user
    job_id = await _job_for(app_client, headers)
    resp = await app_client.post(f"/api/crawl/jobs/{job_id}/schedule", json={"frequency": "fortnightly"}, headers=headers)
    assert resp.status_code == 422


async def test_delete_schedule(app_client, registered_user):
    headers, _ = registered_user
    job_id = await _job_for(app_client, headers)
    created = (await app_client.post(f"/api/crawl/jobs/{job_id}/schedule", json={"frequency": "hourly"}, headers=headers)).json()

    resp = await app_client.delete(f"/api/crawl/schedules/{created['id']}", headers=headers)
    assert resp.status_code == 200
    assert (await app_client.get("/api/crawl/schedules", headers=headers)).json() == []


async def test_cannot_delete_another_users_schedule(app_client, app_client_extra_user, registered_user):
    other_headers = app_client_extra_user
    job_id = await _job_for(app_client, other_headers, url="theirs-sched.com")
    created = (await app_client.post(f"/api/crawl/jobs/{job_id}/schedule", json={"frequency": "daily"}, headers=other_headers)).json()

    headers, _ = registered_user
    resp = await app_client.delete(f"/api/crawl/schedules/{created['id']}", headers=headers)
    assert resp.status_code == 404


async def test_dispatch_due_schedules_starts_job_and_advances_next_run(mongo_db, monkeypatch):
    from app.workers import tasks as tasks_module
    from app.workers.tasks import _dispatch_due_schedules

    dispatched_ids = []
    monkeypatch.setattr(
        tasks_module.crawl_domain_task, "delay",
        lambda job_id: dispatched_ids.append(job_id),
    )

    user_id = uuid.uuid4()
    due = CrawlSchedule(
        domain_id=uuid.uuid4(), user_id=user_id,
        frequency="hourly", next_run_at=datetime.utcnow() - timedelta(minutes=5),
    )
    await due.insert()

    not_due = CrawlSchedule(
        domain_id=uuid.uuid4(), user_id=user_id,
        frequency="daily", next_run_at=datetime.utcnow() + timedelta(hours=6),
    )
    await not_due.insert()

    disabled = CrawlSchedule(
        domain_id=uuid.uuid4(), user_id=user_id,
        frequency="hourly", next_run_at=datetime.utcnow() - timedelta(minutes=5),
        enabled=False,
    )
    await disabled.insert()

    started = await _dispatch_due_schedules()

    assert len(started) == 1
    assert dispatched_ids == started

    job = await CrawlJob.get(uuid.UUID(started[0]))
    assert job is not None
    assert job.domain_id == due.domain_id
    assert job.user_id == user_id
    assert job.meta_data.get("scheduled") is True

    refreshed = await CrawlSchedule.get(due.id)
    assert refreshed.last_run_at is not None
    assert refreshed.next_run_at > datetime.utcnow() + timedelta(minutes=50)

    untouched = await CrawlSchedule.get(not_due.id)
    assert untouched.last_run_at is None
