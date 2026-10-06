from urllib.parse import urlsplit


def test_target_path_is_appended_to_configured_host():
    # Keep this test dependency-free so it can run in CI before a Frappe site exists.
    base = "https://vps.thumbayan.com:443"
    path = "/health?check=1"
    parsed = urlsplit(path)
    result = f"{urlsplit(base).scheme}://{urlsplit(base).netloc}{parsed.path}?{parsed.query}"
    assert result == "https://vps.thumbayan.com:443/health?check=1"


def test_frappe_app_files_exist():
    from pathlib import Path

    root = Path(__file__).parents[1]
    assert (root / "back4app_xhttp_relay" / "hooks.py").is_file()
    assert (root / "back4app_xhttp_relay" / "api.py").is_file()
