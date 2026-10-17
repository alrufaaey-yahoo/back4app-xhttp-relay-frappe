import sys
import types

import pytest


class _Request:
    method = "GET"
    args = {}
    headers = {}


fake_frappe = types.SimpleNamespace(
    conf={},
    request=_Request(),
    local=types.SimpleNamespace(request=_Request(), response={}),
    whitelist=lambda **_: (lambda fn: fn),
    log_error=lambda *args, **kwargs: None,
    get_traceback=lambda: "traceback",
    ValidationError=ValueError,
)
sys.modules.setdefault("frappe", fake_frappe)

from back4app_xhttp_relay.api import (  # noqa: E402
    _blocked_ip,
    normalize_url,
    rewrite_css_text,
    rewrite_html,
)


def test_normalize_domain_adds_https():
    assert normalize_url("example.com/path") == "https://example.com/path"


def test_normalize_rejects_unsupported_and_credentials():
    with pytest.raises(ValueError):
        normalize_url("ftp://example.com")
    with pytest.raises(ValueError):
        normalize_url("https://user:pass@example.com")


def test_private_and_metadata_addresses_are_blocked():
    for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fc00::1"):
        assert _blocked_ip(address)


def test_html_links_and_resources_use_proxy_route():
    body = b'''<html><head><base href="https://example.com/docs/"><link href="/app.css"></head>
    <body><a href="next">Next</a><img src="img/a.png"><form action="/search"></form>
    <script src="/app.js"></script></body></html>'''
    output = rewrite_html(body, "https://example.com/start") .decode()
    assert "/api/method/back4app_xhttp_relay.api.proxy?url=" in output
    assert "example.com" in output
    assert 'href="/app.css"' not in output
    assert 'src="/app.js"' not in output


def test_css_urls_are_rewritten_and_data_urls_preserved():
    output = rewrite_css_text(".a{background:url('../img/a.png')} .b{background:url(data:image/png;base64,abc)}", "https://example.com/css/main.css")
    assert "/api/method/back4app_xhttp_relay.api.proxy?url=" in output
    assert "data:image/png;base64,abc" in output
