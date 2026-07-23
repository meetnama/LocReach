"""URL host/port helpers — critical for Render https://…onrender.com (no :port)."""
from sources.utils import service_url_host_port


def test_local_searxng_default_port():
    host, port = service_url_host_port("http://localhost:8888", 8888)
    assert host == "localhost"
    assert port == 8888


def test_local_without_explicit_port_uses_local_default():
    host, port = service_url_host_port("http://127.0.0.1", 8888)
    assert host == "127.0.0.1"
    assert port == 8888


def test_https_render_uses_443_not_8888():
    host, port = service_url_host_port(
        "https://locreach-searxng.onrender.com", 8888,
    )
    assert host == "locreach-searxng.onrender.com"
    assert port == 443


def test_http_remote_uses_80_not_local_default():
    host, port = service_url_host_port("http://openserp.example.com", 7000)
    assert host == "openserp.example.com"
    assert port == 80


def test_explicit_nondefault_port_kept():
    host, port = service_url_host_port("https://example.com:8443", 8888)
    assert port == 8443


def test_running_on_cloud_detects_onrender_urls(monkeypatch):
    from sources.utils import running_on_cloud

    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("LOCREACH_CLOUD", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.setenv("SEARXNG_URL", "https://locreach-searxng.onrender.com")
    monkeypatch.setenv("OPENSERP_URL", "https://locreach-openserp.onrender.com")
    assert running_on_cloud() is True

    monkeypatch.setenv("SEARXNG_URL", "http://localhost:8888")
    monkeypatch.setenv("OPENSERP_URL", "http://localhost:7000")
    assert running_on_cloud() is False

    monkeypatch.setenv("LOCREACH_CLOUD", "1")
    assert running_on_cloud() is True
