import pytest


@pytest.mark.asyncio
async def test_login_is_rate_limited(app_client):
    """The 11th login attempt in a window from one IP is rejected with 429
    (limit is 10/minute). A unique X-Forwarded-For gives this test its own
    bucket so it doesn't interfere with other tests' quota.
    """
    import main as main_module
    main_module.limiter.enabled = True
    try:
        headers = {"X-Forwarded-For": "203.0.113.77"}  # test-only client IP
        statuses = []
        for _ in range(12):
            r = await app_client.post(
                "/api/auth/login",
                json={"email": "nobody@example.com", "password": "wrongpass"},
                headers=headers,
            )
            statuses.append(r.status_code)
        # First 10 are normal auth failures (401); at least one later call is 429.
        assert 429 in statuses, statuses
        assert statuses.index(429) >= 10, f"limited too early: {statuses}"
    finally:
        main_module.limiter.enabled = False


@pytest.mark.asyncio
async def test_ssrf_guard_blocks_internal_crawl_target(app_client, registered_user):
    """The /api/crawl entry point rejects internal/private URLs (400) before
    any fetch happens."""
    headers, _ = registered_user
    for target in ["http://169.254.169.254/", "http://localhost:9000", "http://10.1.2.3"]:
        r = await app_client.post("/api/crawl", json={"url": target}, headers=headers)
        assert r.status_code == 400, (target, r.status_code)
        assert "can't be crawled" in r.json().get("message", "")


@pytest.mark.asyncio
async def test_ssrf_guard_allows_public_crawl_target(app_client, registered_user):
    headers, _ = registered_user
    r = await app_client.post("/api/crawl", json={"url": "example.com"}, headers=headers)
    assert r.status_code == 200
    assert r.json().get("job_id")
