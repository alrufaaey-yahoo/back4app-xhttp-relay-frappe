"""HTTP relay endpoint for Frappe.

Call it with:
    /api/method/back4app_xhttp_relay.api.relay?path=/some/path

The target is configured in site_config.json as
``back4app_relay_target_domain``.  An optional
``back4app_relay_token`` can protect the endpoint with X-Relay-Token.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import frappe
import requests
from werkzeug.exceptions import BadRequest, Forbidden


_DROP_HEADERS = {
    "host",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "forwarded",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-forwarded-port",
    "content-length",
}
_PASS_HEADERS = {
    "accept",
    "accept-encoding",
    "content-type",
    "cookie",
    "user-agent",
    "x-forwarded-for",
    "x-real-ip",
}


def _setting(name: str, default=None):
    """Read a site config value without exposing the whole site config."""
    return frappe.conf.get(name, default)


def _target_url(path: str) -> str:
    base = (_setting("back4app_relay_target_domain") or "https://vps.thumbayan.com:443").rstrip("/")
    parsed_base = urlsplit(base)
    if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
        raise frappe.ValidationError("back4app_relay_target_domain must be an http(s) URL")

    if not path:
        path = "/"
    if not path.startswith("/"):
        path = "/" + path
    parsed_path = urlsplit(path)
    # The target host is always taken from configuration; callers can only choose the path/query.
    return urlunsplit((parsed_base.scheme, parsed_base.netloc, parsed_path.path or "/", parsed_path.query, ""))


def _request_headers() -> dict[str, str]:
    incoming = frappe.request.headers
    headers: dict[str, str] = {}
    for key, value in incoming.items():
        lower = key.lower()
        if lower in _DROP_HEADERS or lower.startswith("x-vercel-") or lower == "x-relay-token":
            continue
        if lower in _PASS_HEADERS:
            headers[key] = value
    # Preserve the original client IP in the same way as the Node implementation.
    client_ip = incoming.get("X-Real-IP") or incoming.get("X-Forwarded-For")
    if client_ip:
        headers["X-Forwarded-For"] = client_ip
    return headers


def _set_raw_response(response: requests.Response) -> None:
    """Ask Frappe to return the upstream body instead of wrapping it in JSON."""
    frappe.local.response["type"] = "binary"
    frappe.local.response["filecontent"] = response.content
    frappe.local.response["content_type"] = response.headers.get("Content-Type", "application/octet-stream")
    frappe.local.response["http_status_code"] = response.status_code
    output_headers = {}
    for key, value in response.headers.items():
        if key.lower() not in _DROP_HEADERS and key.lower() not in {"content-length", "content-encoding"}:
            output_headers[key] = value
    frappe.local.response["headers"] = output_headers


@frappe.whitelist(allow_guest=True)
def health():
    """Simple health endpoint for monitoring."""
    return {"status": "ok"}


@frappe.whitelist(allow_guest=True)
def relay(path: str | None = None):
    """Relay the current request to the configured upstream target.

    ``path`` is a URL path with an optional query string. The endpoint accepts
    GET/POST/PUT/PATCH/DELETE/OPTIONS/HEAD and forwards the request body.
    """
    configured_token = _setting("back4app_relay_token")
    supplied_token = frappe.request.headers.get("X-Relay-Token")
    if configured_token and supplied_token != configured_token:
        raise Forbidden("Invalid relay token")

    method = frappe.request.method.upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
        raise BadRequest("HTTP method is not supported by the relay")

    target = _target_url(path or frappe.request.args.get("path") or "/")
    try:
        upstream = requests.request(
            method=method,
            url=target,
            headers=_request_headers(),
            data=frappe.request.get_data(cache=True),
            timeout=(10, 120),
            allow_redirects=False,
        )
    except requests.RequestException:
        frappe.log_error(frappe.get_traceback(), "Back4App XHTTP Relay upstream failure")
        frappe.local.response["http_status_code"] = 502
        return "Bad Gateway: Proxy Request Failed"

    _set_raw_response(upstream)
    return None
