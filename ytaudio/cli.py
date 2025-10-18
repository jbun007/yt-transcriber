from __future__ import annotations

import tempfile
import time
from pathlib import Path

import typer
from yt_dlp.utils import DownloadError

from .audio import FFmpegNotFoundError, ensure_ffmpeg, to_mp3_and_wav
from .cookies import (
    CookieRefreshError,
    DEFAULT_COOKIE_PATH,
    ensure_cookie_jar,
    is_cookie_expired,
)
from .download import fetch_best_audio, get_info
from .stt import load_model, transcribe, write_json, write_srt, write_txt, write_vtt
from .utils import ensure_outdir, slugify

app = typer.Typer(add_completion=False)

_WRITERS = {
    "txt": write_txt,
    "srt": write_srt,
    "vtt": write_vtt,
    "json": write_json,
}


def _progress(message: str) -> None:
    """Emit a lightweight status message to stderr so stdout stays machine-friendly."""
    typer.echo(f"[ytaudio] {message}", err=True)


@app.command()
def main(
    url: str,
    outdir: Path = typer.Option(Path("."), help="Directory for output files."),
    basename: str | None = typer.Option(None, help="Override base filename."),
    model: str = typer.Option("small", help="faster-whisper model size or path."),
    language: str = typer.Option("auto", help="Language code or auto for detection."),
    format: str = typer.Option("txt", help="Transcript format: txt|srt|vtt|json."),
    device: str = typer.Option("auto", help="Device for inference: auto|cpu|cuda."),
    threads: int = typer.Option(0, help="Number of CPU threads for faster-whisper."),
    cookies: Path | None = typer.Option(
        None,
        help="Path to a Netscape-format cookie jar with authenticated YouTube cookies.",
    ),
    cookies_from_browser: str | None = typer.Option(
        None,
        help="Browser profile spec for yt-dlp cookies-from-browser option.",
    ),
    verbose: bool = typer.Option(
        False,
        help="Enable verbose error output and keep temp files.",
        flag_value=True,
    ),
) -> None:
    """Download audio, convert to MP3, and transcribe locally."""
    start_time = time.perf_counter()
    _progress("Checking ffmpeg availability")
    try:
        ensure_ffmpeg()
    except FFmpegNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    _progress("Preparing output directory")
    outdir = ensure_outdir(outdir)

    # Work out which cookie jar (if any) we should use for authenticated downloads.
    cookies_path = cookies
    if cookies_from_browser:
        _progress("Refreshing YouTube cookies")
        try:
            cookies_path = ensure_cookie_jar(
                cookies_path or DEFAULT_COOKIE_PATH,
                cookies_from_browser,
                verbose=verbose,
            ).resolve()
            if verbose:
                typer.echo(f"Using cookie jar: {cookies_path}", err=True)
        except CookieRefreshError as exc:
            typer.echo(f"Failed to refresh cookies: {exc}", err=True)
            raise typer.Exit(code=3) from exc
    elif cookies_path:
        cookies_path = cookies_path.expanduser().resolve()
        if not cookies_path.exists():
            typer.echo(f"Cookie file not found: {cookies_path}", err=True)
            raise typer.Exit(code=3)
        if is_cookie_expired(cookies_path):
            typer.echo(
                f"Cookie file {cookies_path} appears expired. "
                "Provide --cookies-from-browser to refresh automatically.",
                err=True,
            )

    cookies_from_browser_option = None if cookies_path else cookies_from_browser

    _progress("Fetching video metadata")
    try:
        info = get_info(
            url,
            cookies=cookies_path,
            cookies_from_browser=cookies_from_browser_option,
            verbose=verbose,
        )
    except DownloadError as exc:
        typer.echo(f"Failed to fetch video metadata: {exc}", err=True)
        raise typer.Exit(code=3) from exc

    base = basename or slugify(f"{info.get('title', 'audio')}_{info.get('id', '')}")
    delete_tmp = not verbose
    with tempfile.TemporaryDirectory(prefix="ytaudio_", delete=delete_tmp) as temp_dir:
        tmp_path = Path(temp_dir)
        if verbose:
            typer.echo(f"Using temp directory: {tmp_path}", err=True)

        _progress("Downloading audio source")
        try:
            src_path = fetch_best_audio(
                url,
                tmp_path,
                cookies=cookies_path,
                cookies_from_browser=cookies_from_browser_option,
                verbose=verbose,
            )
        except DownloadError as exc:
            if verbose:
                typer.echo(f"Download error: {exc}", err=True)
            raise typer.Exit(code=3) from exc
        except Exception as exc:
            if verbose:
                typer.echo(f"Unexpected download error: {exc}", err=True)
            raise typer.Exit(code=3) from exc

        mp3_path = outdir / f"{base}.mp3"
        wav_path = tmp_path / f"{base}.wav"
        _progress("Converting audio to MP3 and WAV")
        try:
            mp3_path, wav_path = to_mp3_and_wav(src_path, mp3_path, wav_path)
        except FFmpegNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        except Exception as exc:
            if verbose:
                typer.echo(f"Transcode error: {exc}", err=True)
            raise typer.Exit(code=4) from exc

        _progress("Loading transcription model")
        try:
            model_obj = load_model(model, device=device, threads=threads)
        except Exception as exc:
            if verbose:
                typer.echo(f"Model load error: {exc}", err=True)
            raise typer.Exit(code=5) from exc

        _progress("Transcribing audio")
        try:
            transcript = transcribe(model_obj, wav_path, language=language, word_ts=False)
        except Exception as exc:
            if verbose:
                typer.echo(f"Transcription error: {exc}", err=True)
            raise typer.Exit(code=5) from exc

        writer = _WRITERS.get(format.lower(), write_txt)
        ext = _format_extension(format)
        transcript_dir = outdir
        if ext == "txt":
            transcript_dir = ensure_outdir(outdir / "transcriptions")
        transcript_path = transcript_dir / f"{base}.transcript.{ext}"

        _progress("Writing transcript")
        try:
            writer(transcript, transcript_path)
        except Exception as exc:
            if verbose:
                typer.echo(f"Failed to write transcript: {exc}", err=True)
            raise typer.Exit(code=5) from exc

        _progress("Removing MP3 artefact")
        try:
            mp3_path.unlink(missing_ok=True)
        except OSError as exc:
            if verbose:
                typer.echo(f"Failed to remove MP3: {exc}", err=True)

        # Standard output is the only value-based interface the CLI exposes.
        # Printing just the transcript path keeps the tool composable in scripts.
        typer.echo(str(transcript_path))

        if verbose and not delete_tmp:
            typer.echo(f"Temp files kept in {tmp_path}", err=True)

    duration = time.perf_counter() - start_time
    typer.echo(f"[ytaudio] Completed in {duration:.1f}s", err=True)


def _format_extension(fmt: str) -> str:
    fmt_lower = fmt.lower()
    return fmt_lower if fmt_lower in _WRITERS else "txt"
