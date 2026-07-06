from app.crawler import ssrf_guard


def test_public_urls_are_allowed():
    for url in ["https://peec.ai", "https://google.com", "http://example.com/page"]:
        assert ssrf_guard.blocked_reason(url) is None


def test_public_ip_that_looks_private_is_allowed():
    # 172.64.x (Cloudflare, e.g. ahrefs.com) is PUBLIC - only 172.16-31.x is
    # private. A naive "172." string match would wrongly block real sites.
    assert ssrf_guard.blocked_reason("http://172.64.148.115") is None


def test_loopback_blocked():
    assert ssrf_guard.blocked_reason("http://127.0.0.1/admin")
    assert ssrf_guard.blocked_reason("http://localhost:8000")


def test_cloud_metadata_blocked():
    assert ssrf_guard.blocked_reason("http://169.254.169.254/latest/meta-data/")


def test_private_ranges_blocked():
    for url in ["http://10.0.0.5", "http://192.168.1.1", "http://172.16.0.1", "http://0.0.0.0"]:
        assert ssrf_guard.blocked_reason(url), url


def test_internal_hostnames_blocked():
    for url in [
        "http://mongodb-8g0n.railway.internal:27017",
        "http://api.railway.internal",
        "http://service.local",
        "http://metadata.google.internal",
    ]:
        assert ssrf_guard.blocked_reason(url), url


def test_non_http_schemes_blocked():
    for url in ["ftp://example.com", "file:///etc/passwd", "gopher://x"]:
        assert ssrf_guard.blocked_reason(url), url


def test_missing_host_blocked():
    assert ssrf_guard.blocked_reason("http://")
