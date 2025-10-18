from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional

DEFAULT_COOKIE_PATH = Path.home() / ".config" / "yt-transcriber" / "youtube.cookies.txt"
# yt-dlp requires a URL when exporting cookies.  Any public YouTube URL works;
# this one is short and unlikely to disappear.
_EXPORT_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


class CookieRefreshError(RuntimeError):
    """Raised when automatic cookie export fails."""


def is_cookie_expired(path: Path) -> bool:
    """Return True if the cookie jar is missing or all cookies are expired."""
    if not path.exists():
        return True

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return True

    now = time.time()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain = parts[0]
        try:
            expiry = int(parts[4])
        except ValueError:
            continue
        if "youtube" not in domain.lower():
            continue
        if expiry == 0 or expiry > now:
            return False

    return True


def refresh_cookies_from_browser(
    browser_spec: str,
    dest: Path,
    *,
    quiet: bool = True,
) -> Path:
    """Export fresh cookies from the given browser profile into dest."""
    dest.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--skip-download",
        "--cookies-from-browser",
        browser_spec,
        "--cookies",
        str(dest),
        _EXPORT_URL,
    ]
    if quiet:
        cmd.insert(1, "--quiet")

    result = subprocess.run(  # noqa: S603
        cmd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "yt-dlp cookie export failed"
        raise CookieRefreshError(message)

    return dest


def ensure_cookie_jar(
    desired_path: Optional[Path],
    browser_spec: str,
    *,
    verbose: bool = False,
) -> Path:
    """Ensure a valid cookie jar exists by refreshing it if needed."""
    path = (desired_path or DEFAULT_COOKIE_PATH).expanduser()
    if not is_cookie_expired(path):
        return path

    return refresh_cookies_from_browser(browser_spec, path, quiet=not verbose)
