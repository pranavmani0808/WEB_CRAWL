import uuid

from app.models.crawl_job import CrawlJob
from app.models.user import User


async def _make_admin(app_client):
    resp = await app_client.post(
        "/api/auth/register",
        json={"email": "admin@example.com", "username": "admin", "password": "supersecret123"},
    )
    body = resp.json()
    user = await User.find_one(User.email == "admin@example.com")
    user.is_admin = True
    await user.save()
    # re-login so downstream still works; token already valid, is_admin read live
    return {"Authorization": f"Bearer {body['access_token']}"}


async def test_admin_endpoints_reject_non_admins(app_client, registered_user):
    headers, _ = registered_user  # ordinary user
    for path in ["/api/admin/overview", "/api/admin/users"]:
        r = await app_client.get(path, headers=headers)
        assert r.status_code == 403, path


async def test_admin_endpoints_require_auth(app_client):
    r = await app_client.get("/api/admin/overview")
    assert r.status_code == 401


async def test_admin_overview_counts(app_client):
    admin_headers = await _make_admin(app_client)
    # a second user with a couple of crawls
    await app_client.post("/api/auth/register", json={"email": "u1@example.com", "username": "u1", "password": "password123"})
    u1 = await User.find_one(User.email == "u1@example.com")
    await CrawlJob(domain_id=uuid.uuid4(), user_id=u1.id, status="completed", total_urls_checked=50).insert()
    await CrawlJob(domain_id=uuid.uuid4(), user_id=u1.id, status="running", total_urls_checked=10).insert()

    r = await app_client.get("/api/admin/overview", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["users"]["total"] >= 2
    assert body["crawls"]["total"] >= 2
    assert body["crawls"]["running"] >= 1
    assert body["crawls"]["completed"] >= 1
    assert body["total_urls_checked"] >= 60


async def test_admin_users_list_has_crawl_counts(app_client):
    admin_headers = await _make_admin(app_client)
    await app_client.post("/api/auth/register", json={"email": "busy@example.com", "username": "busy", "password": "password123"})
    busy = await User.find_one(User.email == "busy@example.com")
    for _ in range(3):
        await CrawlJob(domain_id=uuid.uuid4(), user_id=busy.id, status="completed", total_urls_checked=20).insert()

    r = await app_client.get("/api/admin/users", headers=admin_headers)
    assert r.status_code == 200
    users = {u["email"]: u for u in r.json()}
    assert users["busy@example.com"]["total_crawls"] == 3
    assert users["busy@example.com"]["urls_checked"] == 60
    assert users["admin@example.com"]["is_admin"] is True


async def test_admin_user_crawls_detail(app_client):
    admin_headers = await _make_admin(app_client)
    await app_client.post("/api/auth/register", json={"email": "target@example.com", "username": "target", "password": "password123"})
    target = await User.find_one(User.email == "target@example.com")
    await CrawlJob(domain_id=uuid.uuid4(), user_id=target.id, status="completed", total_urls_checked=5).insert()

    r = await app_client.get(f"/api/admin/users/{target.id}/crawls", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "target@example.com"
    assert len(body["crawls"]) == 1
