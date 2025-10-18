from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Tuple


class FFmpegNotFoundError(FileNotFoundError):
    """Raised when ffmpeg is missing from PATH."""


def ensure_ffmpeg() -> str:
    """Return the ffmpeg executable path or raise if missing."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegNotFoundError("ffmpeg not found on PATH. Install ffmpeg and retry.")
    return ffmpeg


def to_mp3_and_wav(src: Path, out_mp3: Path, out_wav16k: Path) -> Tuple[Path, Path]:
    """
    Convert src into a listener MP3 and 16 kHz mono WAV for transcription.

    Returns:
        Tuple[Path, Path]: (mp3_path, wav_path)
    """
    ffmpeg = ensure_ffmpeg()

    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    out_wav16k.parent.mkdir(parents=True, exist_ok=True)

    # First pass: produce the user-facing MP3 copy.
    mp3_cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-ar",
        "44100",
        "-ac",
        "2",
        str(out_mp3),
    ]
    # Second pass: create a 16 kHz mono WAV for the speech recogniser.
    wav_cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(out_wav16k),
    ]

    _run_ffmpeg(mp3_cmd, "MP3")
    _run_ffmpeg(wav_cmd, "WAV")

    return out_mp3, out_wav16k


def _run_ffmpeg(cmd: list[str], label: str) -> None:
    """Execute ffmpeg command and raise RuntimeError on failure."""
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="ignore") if exc.stderr else ""
        raise RuntimeError(f"ffmpeg failed to create {label}: {stderr.strip()}") from exc
