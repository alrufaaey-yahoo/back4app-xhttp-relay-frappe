"""Direct and API HTTP relay for Frappe.

The direct relay is installed as a Frappe ``before_request`` hook. Public
requests such as ``/`` and ``/path?query=1`` are forwarded to the configured
upstream while Frappe administration, assets, and API routes remain available.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import frappe
import requests
from werkzeug.exceptions import BadRequest, Forbidden
from werkzeug.wrappers import Response


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

# Keep Frappe usable for administration and for the explicit API endpoints.
_EXEMPT_PREFIXES = (
    "/api/",
    "/assets/",
    "/files/",
    "/private/files/",
    "/app",
    "/desk",
    "/login",
    "/setup",
    "/socket.io",
    "/backups",
    "/.well-known/",
)


def _setting(name: str, default=None):
    return frappe.conf.get(name, default)


def _base_target() -> tuple[str, str]:
    base = (_setting("back4app_relay_target_domain") or "https://vps.thumbayan.com:443").rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise frappe.ValidationError("back4app_relay_target_domain must be an http(s) URL")
    return parsed.scheme, parsed.netloc


def _target_url(path: str) -> str:
    scheme, netloc = _base_target()
    parsed_path = urlsplit(path or "/")
    safe_path = parsed_path.path or "/"
    return urlunsplit((scheme, netloc, safe_path, parsed_path.query, ""))


def _request_headers() -> dict[str, str]:
    incoming = frappe.request.headers
    headers: dict[str, str] = {}
    client_ip = incoming.get("X-Real-IP") or incoming.get("X-Forwarded-For")

    for key, value in incoming.items():
        lower = key.lower()
        if lower in _DROP_HEADERS or lower == "x-relay-token" or lower.startswith("x-vercel-"):
            continue
        headers[key] = value

    if client_ip:
        headers["X-Forwarded-For"] = client_ip
    headers["X-Forwarded-Proto"] = "https" if frappe.request.scheme == "https" else "http"
    headers["X-Forwarded-Host"] = frappe.request.host
    return headers


def _token_is_valid() -> bool:
    configured_token = _setting("back4app_relay_token")
    if not configured_token:
        return True
    return frappe.request.headers.get("X-Relay-Token") == configured_token


def _make_upstream_response(target: str) -> Response:
    try:
        upstream = requests.request(
            method=frappe.request.method.upper(),
            url=target,
            headers=_request_headers(),
            data=frappe.request.get_data(cache=True),
            timeout=(10, 120),
            allow_redirects=False,
        )
    except requests.RequestException:
        frappe.log_error(frappe.get_traceback(), "Back4App XHTTP Relay upstream failure")
        return Response("Bad Gateway: Proxy request failed", status=502, content_type="text/plain")

    return Response(
        upstream.content,
        status=upstream.status_code,
        content_type=upstream.headers.get("Content-Type") or "application/octet-stream",
    )


def _is_exempt(path: str) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in _EXEMPT_PREFIXES)



def relay_before_request():
    """Route public requests through Frappe's raw binary API response path.

    Frappe executes ``before_request`` hooks before its normal router. Rewriting
    the internal path/form command here keeps the public URL unchanged while
    letting Frappe build the response safely (including status and headers).
    """
    path = frappe.request.path or "/"
    if _is_exempt(path):
        return
    if not _token_is_valid():
        frappe.local.request.environ["PATH_INFO"] = "/api/method/back4app_xhttp_relay.api.relay"
        frappe.local.form_dict.cmd = "back4app_xhttp_relay.api.relay"
        frappe.local.form_dict.path = path
        return

    query = frappe.request.query_string.decode() if frappe.request.query_string else ""
    original_path = f"{path}?{query}" if query else path
    frappe.local.request.environ["PATH_INFO"] = "/api/method/back4app_xhttp_relay.api.relay"
    frappe.local.form_dict.cmd = "back4app_xhttp_relay.api.relay"
    frappe.local.form_dict.path = original_path


@frappe.whitelist(allow_guest=True)
def health():
    """Health endpoint for monitoring without contacting the upstream."""
    return {"status": "ok", "upstream": _setting("back4app_relay_target_domain") or "https://vps.thumbayan.com:443"}


@frappe.whitelist(allow_guest=True)
def relay(path: str | None = None):
    """Explicit API relay retained for clients that prefer an API method."""
    if not _token_is_valid():
        raise Forbidden("Invalid relay token")
    method = frappe.request.method.upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
        raise BadRequest("HTTP method is not supported by the relay")
    target = _target_url(path or frappe.request.args.get("path") or "/")
    response = _make_upstream_response(target)
    frappe.local.response["type"] = "binary"
    frappe.local.response["filecontent"] = response.get_data()
    frappe.local.response["content_type"] = response.content_type or "application/octet-stream"
    frappe.local.response["http_status_code"] = response.status_code
    return None
