from __future__ import annotations

import re
from pathlib import Path

_SLUG_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def slugify(value: str, max_length: int = 80) -> str:
    """Convert arbitrary text into a filesystem-safe slug."""
    normalized = _SLUG_PATTERN.sub("_", value.strip())
    slug = re.sub(r"_{2,}", "_", normalized).strip("_").lower()
    if not slug:
        slug = "audio"
    if max_length and len(slug) > max_length:
        slug = slug[:max_length].rstrip("_-.")
        slug = slug or "audio"
    return slug


def ensure_outdir(path: Path) -> Path:
    """Ensure output directory exists and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path
