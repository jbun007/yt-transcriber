from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

_BASE_OPTS: Dict[str, Any] = {
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
}


@dataclass(frozen=True)
class ClientProbe:
    player_client: str
    supports_cookies: bool = True
    extractor_args: Optional[Dict[str, Any]] = None


# Each probe represents a different way of asking YouTube for data.  Some clients
# (web, web_embedded) can send authenticated cookies, others cannot but still
# work as anonymous fallbacks.  We try them in order until one succeeds.
_CLIENT_PROBES: Sequence[ClientProbe] = (
    ClientProbe(
        "web",
        supports_cookies=True,
        extractor_args={"youtube": {"player_skip": ["sabr"], "po_token": ["web.gpu"]}},
    ),
    ClientProbe("web_embedded", supports_cookies=True),
    ClientProbe("ios", supports_cookies=False),
    ClientProbe("android", supports_cookies=False),
    ClientProbe("tv_embedded", supports_cookies=False),
)


def _build_opts(
    *,
    player_client: Optional[str] = None,
    cookies_file: Optional[Path] = None,
    cookies_from_browser: Optional[str] = None,
    verbose: bool = False,
    extractor_args: Optional[Dict[str, Any]] = None,
    **overrides: Any,
) -> Dict[str, Any]:
    """Merge base yt-dlp options with overrides and optional player client settings."""
    opts: Dict[str, Any] = {**_BASE_OPTS, **overrides}
    if verbose:
        opts.pop("quiet", None)
        opts.pop("no_warnings", None)
        opts["verbose"] = True
    # yt-dlp lets us provide fine-grained extractor arguments.  We build those up
    # cumulatively so callers can layer settings without clobbering defaults.
    merged_extractor_args = dict(opts.get("extractor_args") or {})
    if player_client:
        youtube_args = dict(merged_extractor_args.get("youtube") or {})
        youtube_args.setdefault("player_client", [])
        if player_client not in youtube_args["player_client"]:
            youtube_args["player_client"].append(player_client)
        merged_extractor_args["youtube"] = youtube_args
    if extractor_args:
        for key, value in extractor_args.items():
            existing = merged_extractor_args.get(key)
            if existing and isinstance(existing, dict) and isinstance(value, dict):
                merged_extractor_args[key] = {**existing, **value}
            else:
                merged_extractor_args[key] = value
    if merged_extractor_args:
        opts["extractor_args"] = merged_extractor_args
    if cookies_file:
        opts["cookiefile"] = str(cookies_file)
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = cookies_from_browser
    return opts


def get_info(
    url: str,
    *,
    cookies: Optional[Path] = None,
    cookies_from_browser: Optional[str] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Return minimal metadata for the supplied YouTube URL."""
    last_error: Optional[DownloadError] = None
    for probe in _CLIENT_PROBES:
        # Only clients that support cookies should be given the authentication jar.
        probe_cookies_file = cookies if (cookies and probe.supports_cookies) else None
        probe_cookies_browser = (
            cookies_from_browser if (cookies_from_browser and probe.supports_cookies) else None
        )
        opts = _build_opts(
            player_client=probe.player_client,
            cookies_file=probe_cookies_file,
            cookies_from_browser=probe_cookies_browser,
            extractor_args=probe.extractor_args,
            verbose=verbose,
        )
        with YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except DownloadError as err:
                last_error = err
                continue

        return {
            "id": info.get("id") or info.get("display_id") or "",
            "title": info.get("title") or "audio",
            "duration": info.get("duration"),
        }

    raise last_error or DownloadError("Failed to fetch video metadata.")


def fetch_best_audio(
    url: str,
    tmpdir: Path,
    *,
    cookies: Optional[Path] = None,
    cookies_from_browser: Optional[str] = None,
    verbose: bool = False,
) -> Path:
    """
    Download the best available audio for the URL into tmpdir and return the file path.

    Raises:
        DownloadError: if yt-dlp fails to download the audio.
    """
    tmpdir.mkdir(parents=True, exist_ok=True)
    last_error: Optional[DownloadError] = None

    for probe in _CLIENT_PROBES:
        # Skip authenticated cookie sources for clients that cannot use them.
        probe_cookies_file = cookies if (cookies and probe.supports_cookies) else None
        probe_cookies_browser = (
            cookies_from_browser if (cookies_from_browser and probe.supports_cookies) else None
        )
        opts = _build_opts(
            player_client=probe.player_client,
            cookies_file=probe_cookies_file,
            cookies_from_browser=probe_cookies_browser,
            extractor_args=probe.extractor_args,
            verbose=verbose,
            format="bestaudio/best",
            outtmpl="%(id)s.%(ext)s",
            paths={"home": str(tmpdir)},
            skip_download=False,
        )

        with YoutubeDL(opts) as ydl:
            try:
                result = ydl.extract_info(url, download=True)
            except DownloadError as err:
                last_error = err
                continue

        requested = result.get("requested_downloads") or []
        if requested:
            filepath = requested[0].get("filepath")
            if filepath:
                return Path(filepath)

        filepath = result.get("filepath")
        if filepath:
            return Path(filepath)

        files = sorted(tmpdir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            return files[0]

        last_error = DownloadError("yt-dlp did not report any downloaded audio file.")

    raise last_error or DownloadError("Failed to download audio with yt-dlp.")
