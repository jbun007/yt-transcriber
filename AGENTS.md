# ytaudio Contributor Guide

## Core Idea
- Minimal Typer-based CLI that turns a YouTube URL into a listener-ready MP3 and a local transcript using faster-whisper.
- Keep the codebase short, explicit, and free of hidden services so humans and agents can reason about every step.
- Prefer sensible defaults; expose only the flags needed to adjust paths, naming, models, formats, device selection, thread hints, and verbosity.

## Scope & Behavior
- Pipeline: download bestaudio with yt-dlp -> convert to MP3 + 16 kHz mono WAV with ffmpeg -> transcribe locally with faster-whisper -> write transcript.
- Fail fast when `ffmpeg` is missing and surface actionable installation hints.
- Clean up temporary files even on failure unless `--verbose` is set (useful for diagnostics).
- Default transcript format is TXT; optional SRT, VTT, or JSON writers are available.
- Word timestamps remain off by default to favor speed.

## Requirements
- Python 3.10 or newer.
- `ffmpeg` available on `PATH`.
- Python dependencies installed via `pip install -e .`:
  - `typer[all]`
  - `yt-dlp`
  - `faster-whisper` (plus any optional CUDA extras for GPU inference).

## CLI Reference
```
ytaudio <youtube_url>
        [--outdir PATH]
        [--basename NAME]
        [--model tiny|base|small|medium|large-v3|PATH]
        [--language auto|en|...]
        [--format txt|srt|vtt|json]
        [--device auto|cpu|cuda]
        [--threads N]
        [--verbose]
```

### Outputs
- `<basename>.mp3` (44.1 kHz stereo) in `outdir` (default `.`).
- `<basename>.transcript.<ext>` where `<ext>` matches the chosen format.

### Exit Codes
- `0` success
- `2` missing ffmpeg
- `3` download error
- `4` transcode error
- `5` transcription error

## Repository Layout
```
ytaudio/
  __init__.py
  cli.py          # Typer CLI, orchestration, error handling
  download.py     # yt-dlp helpers
  audio.py        # ffmpeg detection + MP3 / 16 kHz WAV conversion
  stt.py          # faster-whisper load/transcribe/write helpers
pyproject.toml    # dependencies + console script entry point
README.md
LICENSE
```

## Module Responsibilities
- `download.get_info(url)` -> metadata dictionary (`id`, `title`, `duration`).
- `download.fetch_best_audio(url, tmpdir)` -> Path to the downloaded source file (no re-encode).
- `audio.ensure_ffmpeg()` -> return ffmpeg path or raise `FileNotFoundError`.
- `audio.to_mp3_and_wav(src, out_mp3, out_wav16k)` -> create MP3 and 16 kHz mono WAV.
- `stt.load_model(name_or_path, device, threads)` -> faster-whisper model instance.
- `stt.transcribe(model, wav_path, language, word_ts=False)` -> transcript data structure.
- `stt.write_txt/srt/vtt/json(transcript, out_path)` -> persist transcript files.

## CLI Orchestration Sketch
```python
with tempfile.TemporaryDirectory() as temp_dir:
    info = get_info(url)
    base = basename or slugify(f"{info['title']}_{info['id']}")
    src = fetch_best_audio(url, Path(temp_dir))
    mp3_path, wav_path = to_mp3_and_wav(src, outdir / f"{base}.mp3", Path(temp_dir) / f"{base}.wav")
    model = load_model(model_name, device=device, threads=threads)
    transcript = transcribe(model, wav_path, language=language, word_ts=False)
    writers[format](transcript, outdir / f"{base}.transcript.{ext}")
```

## Development Notes
- Use `pathlib.Path` consistently for filesystem interactions.
- Derive default `basename` by slugifying `"{title}_{id}"` to stay filesystem safe.
- Respect `--verbose` by printing caught exceptions before exiting with the mapped code.
- Ensure temp directories are scoped with context managers so they clean up automatically.

## Install & Local Usage
```
python -m venv .venv
source .venv/bin/activate
pip install -e .
```
Make sure `ffmpeg` is installed first (`brew install ffmpeg` on macOS, `apt-get install ffmpeg` on Debian/Ubuntu).

Example runs:
- `ytaudio "https://youtu.be/<video_id>" --outdir ./out`
- `ytaudio "https://youtu.be/<video_id>" --model base --format srt`

## Smoke Test Checklist
1. Run against a short clip: `ytaudio "<url>" --model tiny --format txt`.
2. Confirm the MP3 and transcript files are created and non-empty.
3. Inspect stderr with `--verbose` if any step fails.
