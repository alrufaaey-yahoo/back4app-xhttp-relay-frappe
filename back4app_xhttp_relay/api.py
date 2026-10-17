"""Secure server-side web proxy for Frappe Cloud.

The proxy accepts only a destination URL supplied by the user, fetches it from
Frappe's server, and rewrites supported links/resources back through itself.
It deliberately does not forward browser cookies, authorization headers, or
upstream scripts into the trusted Frappe origin.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import threading
import time
from collections import defaultdict, deque
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

import frappe
import requests
from bs4 import BeautifulSoup
from werkzeug.exceptions import BadRequest, Forbidden, RequestURITooLarge


_PROXY_METHOD = "/api/method/back4app_xhttp_relay.api.proxy"
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_MAX_REDIRECTS = 5
_TIMEOUT = (8, 25)
_ALLOWED_METHODS = {"GET", "HEAD"}
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade", "content-length",
    "content-encoding", "set-cookie", "server", "via",
}
_SAFE_REQUEST_HEADERS = {"accept", "accept-language", "user-agent"}
_RATE_LOCK = threading.Lock()
_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def _setting(name: str, default=None):
    return frappe.conf.get(name, default)


def normalize_url(value: str) -> str:
    """Normalize and validate a public HTTP(S) URL."""
    value = (value or "").strip()
    if not value:
        raise ValueError("A destination URL is required")
    if len(value) > 2048:
        raise ValueError("The destination URL is too long")
    if "://" not in value:
        value = "https://" + value
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Only HTTP and HTTPS URLs are supported")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("The URL must contain a public hostname and no credentials")
    if parsed.fragment:
        parsed = parsed._replace(fragment="")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("The URL contains an invalid port") from exc
    if port not in (None, 80, 443):
        raise ValueError("Only standard HTTP and HTTPS ports are supported")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, parsed.path or "/", parsed.query, ""))


def _blocked_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    # Explicitly reject all non-public ranges, including cloud metadata and
    # IPv4-mapped private IPv6 addresses.
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
        or ip.is_reserved or ip.is_unspecified or ip.is_site_local
        or ip in ipaddress.ip_network("100.64.0.0/10")
        or ip in ipaddress.ip_network("192.0.0.0/24")
    )


def resolve_public_addresses(hostname: str) -> list[str]:
    """Resolve a hostname and reject every result that is not public."""
    try:
        results = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("The destination hostname could not be resolved") from exc
    addresses = sorted({item[4][0] for item in results})
    if not addresses or any(_blocked_ip(address) for address in addresses):
        raise ValueError("The destination is not a public address")
    return addresses


def validate_destination(url: str) -> str:
    normalized = normalize_url(url)
    resolve_public_addresses(urlsplit(normalized).hostname or "")
    return normalized


def _client_ip() -> str:
    request = getattr(frappe.local, "request", None)
    return (request.headers.get("X-Real-IP") if request else None) or "anonymous"


def _check_rate_limit() -> None:
    now = time.monotonic()
    key = _client_ip()
    with _RATE_LOCK:
        bucket = _RATE_BUCKETS[key]
        while bucket and bucket[0] < now - 60:
            bucket.popleft()
        if len(bucket) >= int(_setting("proxy_rate_limit_per_minute", 30)):
            raise Forbidden("Too many proxy requests. Please try again later.")
        bucket.append(now)


def _request_headers() -> dict[str, str]:
    incoming = frappe.request.headers
    return {key: value for key, value in incoming.items() if key.lower() in _SAFE_REQUEST_HEADERS}


def _read_limited(response: requests.Response) -> bytes:
    body = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        body.extend(chunk)
        if len(body) > _MAX_RESPONSE_BYTES:
            raise RequestURITooLarge("The upstream response is too large")
    return bytes(body)


def _fetch(url: str) -> tuple[requests.Response, bytes, str]:
    current = validate_destination(url)
    session = requests.Session()
    response = None
    try:
        for _ in range(_MAX_REDIRECTS + 1):
            # Resolve again immediately before every network request to reduce
            # DNS-rebinding risk. Redirects are never followed by requests.
            current = validate_destination(current)
            response = session.request(
                frappe.request.method.upper(), current,
                headers=_request_headers(), timeout=_TIMEOUT,
                allow_redirects=False, stream=True,
            )
            if response.status_code not in {301, 302, 303, 307, 308}:
                return response, _read_limited(response), current
            location = response.headers.get("Location")
            response.close()
            if not location:
                return response, b"", current
            current = urljoin(current, location)
        raise ValueError("The destination redirected too many times")
    except requests.RequestException as exc:
        raise ConnectionError("The upstream website could not be reached") from exc
    finally:
        if response is not None and response.status_code not in {200, 201, 204}:
            response.close()


def _proxy_url(target: str) -> str:
    return f"{_PROXY_METHOD}?url={quote(target, safe='')}"


def _rewrite_url(raw: str, base_url: str) -> str:
    value = (raw or "").strip()
    if not value or value.startswith(("#", "data:", "javascript:", "mailto:", "tel:", "blob:")):
        return raw
    absolute = urljoin(base_url, value)
    try:
        normalized = normalize_url(absolute)
    except ValueError:
        return raw
    return _proxy_url(normalized)


def rewrite_html(body: bytes, base_url: str) -> bytes:
    soup = BeautifulSoup(body, "html.parser")
    base_tag = soup.find("base", href=True)
    document_base = urljoin(base_url, base_tag["href"]) if base_tag else base_url
    if base_tag:
        base_tag.decompose()
    for tag, attributes in {
        "a": ("href",), "link": ("href",), "img": ("src", "srcset"),
        "script": ("src",), "source": ("src", "srcset"), "video": ("src",),
        "audio": ("src",), "iframe": ("src",), "form": ("action",),
        "input": ("src",),
    }.items():
        for element in soup.find_all(tag):
            for attribute in attributes:
                if not element.get(attribute):
                    continue
                if attribute == "srcset":
                    parts = []
                    for candidate in element[attribute].split(","):
                        pieces = candidate.strip().split(None, 1)
                        pieces[0] = _rewrite_url(pieces[0], document_base)
                        parts.append(" ".join(pieces))
                    element[attribute] = ", ".join(parts)
                else:
                    element[attribute] = _rewrite_url(element[attribute], document_base)
    for element in soup.find_all(style=True):
        element["style"] = rewrite_css_text(element["style"], document_base)
    for style in soup.find_all("style"):
        style.string = rewrite_css_text(style.get_text(), document_base)
    return str(soup).encode("utf-8")


_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)
_CSS_IMPORT_RE = re.compile(r"(@import\s+)(['\"])([^'\"]+)(\2)", re.I)


def rewrite_css_text(text: str, base_url: str) -> str:
    def replace_url(match):
        value = match.group(2).strip()
        if value.startswith(("data:", "#")):
            return match.group(0)
        return f"url(\"{_rewrite_url(value, base_url)}\")"

    text = _CSS_URL_RE.sub(replace_url, text)
    return _CSS_IMPORT_RE.sub(lambda m: m.group(1) + m.group(2) + _rewrite_url(m.group(3), base_url) + m.group(4), text)


def _send(body: bytes, content_type: str, status: int) -> None:
    frappe.local.response["type"] = "binary"
    frappe.local.response["filecontent"] = body
    frappe.local.response["content_type"] = content_type.split(";", 1)[0]
    frappe.local.response["http_status_code"] = status


def _error(message: str, status: int) -> None:
    _send(message.encode("utf-8"), "text/plain; charset=utf-8", status)


@frappe.whitelist(allow_guest=True)
def health():
    return {"status": "ok"}


@frappe.whitelist(allow_guest=True)
def proxy(url: str | None = None):
    """Fetch a public website from the server and return a safe proxied response."""
    if frappe.request.method.upper() not in _ALLOWED_METHODS:
        return _error("Only GET and HEAD requests are supported.", 405)
    _check_rate_limit()
    try:
        target = unquote(url or frappe.request.args.get("url") or "")
        response, body, final_url = _fetch(target)
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        media_type = content_type.split(";", 1)[0].lower()
        if media_type == "text/html" or media_type == "application/xhtml+xml":
            body = rewrite_html(body, final_url)
            content_type = "text/html; charset=utf-8"
        elif media_type == "text/css":
            body = rewrite_css_text(body.decode("utf-8", "replace"), final_url).encode("utf-8")
            content_type = "text/css; charset=utf-8"
        _send(body if frappe.request.method.upper() != "HEAD" else b"", content_type, response.status_code)
    except (ValueError, BadRequest) as exc:
        _error(str(exc), 400)
    except Forbidden as exc:
        _error(str(exc), 403)
    except RequestURITooLarge as exc:
        _error(str(exc), 413)
    except ConnectionError as exc:
        frappe.log_error(frappe.get_traceback(), "Web Proxy upstream failure")
        _error(str(exc), 502)
    return None


# Backward-compatible alias for the previous fixed-host relay endpoint.
@frappe.whitelist(allow_guest=True)
def relay(path: str | None = None):
    target = (_setting("back4app_relay_target_domain") or "").rstrip("/")
    if not target:
        return _error("The legacy relay target is not configured.", 503)
    return proxy(urljoin(target + "/", path or frappe.request.args.get("path") or "/"))
