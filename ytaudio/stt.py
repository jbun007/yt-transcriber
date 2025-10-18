from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from faster_whisper import WhisperModel


@dataclass
class WordTiming:
    word: str
    start: float
    end: float


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    words: List[WordTiming] = field(default_factory=list)


@dataclass
class Transcript:
    language: str
    segments: List[TranscriptSegment]


def load_model(name_or_path: str, device: str = "auto", threads: int = 0) -> WhisperModel:
    """Load and return a faster-whisper model."""
    # faster-whisper treats 0 as "auto-detect cpu threads", so we normalise here.
    cpu_threads = threads if threads > 0 else 0
    return WhisperModel(name_or_path, device=device, compute_type="auto", cpu_threads=cpu_threads)


def transcribe(
    model: WhisperModel,
    wav_path: Path,
    language: str = "auto",
    word_ts: bool = False,
) -> Transcript:
    """Transcribe the wav file with faster-whisper and return segment data."""
    segments, info = model.transcribe(
        str(wav_path),
        language=None if language == "auto" else language,
        word_timestamps=word_ts,
    )

    collected: List[TranscriptSegment] = []
    # Convert faster-whisper's generator output into plain dataclasses the rest of the
    # application can reason about.  This keeps the CLI decoupled from library details.
    for seg in segments:
        words: List[WordTiming] = []
        if word_ts and seg.words:
            words = [WordTiming(word=w.word, start=w.start, end=w.end) for w in seg.words if w.word.strip()]
        collected.append(
            TranscriptSegment(
                start=float(seg.start or 0.0),
                end=float(seg.end or 0.0),
                text=seg.text.strip(),
                words=words,
            )
        )

    language_out = info.language if getattr(info, "language", None) else language
    return Transcript(language=language_out or "unknown", segments=collected)


def write_txt(transcript: Transcript, out_path: Path) -> Path:
    """Write transcript as plain text."""
    # Plain text is forgiving; we simply stack segments separated by newlines.
    text = "\n".join(seg.text for seg in transcript.segments if seg.text)
    out_path.write_text(text.strip() + ("\n" if text else ""))
    return out_path


def write_srt(transcript: Transcript, out_path: Path) -> Path:
    """Write transcript as SubRip subtitles."""
    lines = []
    for idx, seg in enumerate(transcript.segments, start=1):
        if not seg.text:
            continue
        start = _format_timestamp(seg.start, separator=",")
        end = _format_timestamp(seg.end, separator=",")
        lines.extend([str(idx), f"{start} --> {end}", seg.text.strip(), ""])
    out_path.write_text("\n".join(lines).strip() + "\n")
    return out_path


def write_vtt(transcript: Transcript, out_path: Path) -> Path:
    """Write transcript as WebVTT subtitles."""
    lines = ["WEBVTT", ""]
    for seg in transcript.segments:
        if not seg.text:
            continue
        start = _format_timestamp(seg.start, separator=".")
        end = _format_timestamp(seg.end, separator=".")
        lines.extend([f"{start} --> {end}", seg.text.strip(), ""])
    out_path.write_text("\n".join(lines).strip() + "\n")
    return out_path


def write_json(transcript: Transcript, out_path: Path) -> Path:
    """Write transcript metadata and segments as JSON."""
    payload = {
        "language": transcript.language,
        "segments": [
            {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "words": [
                    {"word": w.word, "start": w.start, "end": w.end} for w in seg.words
                ]
                if seg.words
                else [],
            }
            for seg in transcript.segments
        ],
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    return out_path


def _format_timestamp(value: float, separator: str) -> str:
    """Convert seconds into SRT/WebVTT timestamp format."""
    total_ms = int(round(value * 1000))
    hours, remainder = divmod(total_ms, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, milliseconds = divmod(remainder, 1000)
    if separator == ",":
        return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"
    return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"
