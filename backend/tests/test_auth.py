async def test_register_creates_user_and_returns_tokens(app_client):
    resp = await app_client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "username": "alice", "password": "password123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["access_token"]
    assert body["refresh_token"]


async def test_register_rejects_duplicate_email(app_client):
    payload = {"email": "dupe@example.com", "username": "dupe1", "password": "password123"}
    first = await app_client.post("/api/auth/register", json=payload)
    assert first.status_code == 200

    second = await app_client.post("/api/auth/register", json={**payload, "username": "dupe2"})
    assert second.status_code == 409


async def test_register_rejects_duplicate_username(app_client):
    await app_client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "username": "shared", "password": "password123"},
    )
    resp = await app_client.post(
        "/api/auth/register",
        json={"email": "b@example.com", "username": "shared", "password": "password123"},
    )
    assert resp.status_code == 409


async def test_login_with_correct_credentials_succeeds(app_client):
    await app_client.post(
        "/api/auth/register",
        json={"email": "bob@example.com", "username": "bob", "password": "correcthorse"},
    )
    resp = await app_client.post(
        "/api/auth/login", json={"email": "bob@example.com", "password": "correcthorse"}
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_login_with_wrong_password_rejected(app_client):
    await app_client.post(
        "/api/auth/register",
        json={"email": "carol@example.com", "username": "carol", "password": "correcthorse"},
    )
    resp = await app_client.post(
        "/api/auth/login", json={"email": "carol@example.com", "password": "wrongpassword"}
    )
    assert resp.status_code == 401


async def test_me_requires_authentication(app_client):
    resp = await app_client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_me_returns_current_user(app_client, registered_user):
    headers, user = registered_user
    resp = await app_client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == user["email"]
