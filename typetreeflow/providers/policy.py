from __future__ import annotations

import re
from pathlib import Path

SECRET_KEY_RE = re.compile(
    r"(?i)\b("
    r"api[_-]?key|authorization|bearer|cookie|credential|pass(?:word|wd)?|"
    r"secret|session|token"
    r")\b"
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b("
    r"api[_-]?key|authorization|bearer|cookie|credential|pass(?:word|wd)?|"
    r"secret|session|token"
    r")\b\s*[:=]\s*[^;\s,\t]+"
)


def redact_secret_like_text(value: object, replacement: str = "[REDACTED]") -> str:
    text = str(value)
    text = SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}={replacement}",
        text,
    )
    parts = text.split()
    redacted: list[str] = []
    previous_secret_key = False
    for part in parts:
        if previous_secret_key:
            redacted.append(replacement)
            previous_secret_key = False
            continue
        redacted.append(part)
        previous_secret_key = bool(SECRET_KEY_RE.fullmatch(part.rstrip(":=")))
    return " ".join(redacted) if len(parts) > 1 else text


def default_provider_cache_path(outdir: str | Path, provider_key: str) -> Path:
    safe_key = provider_key.strip().replace("\\", "_").replace("/", "_")
    if not safe_key:
        raise ValueError("Provider cache requires a provider key.")
    return Path(outdir) / "cache" / "provider" / safe_key


def validate_provider_private_cache_path(
    path: str | Path,
    *,
    outdir: str | Path,
) -> Path:
    cache_path = Path(path)
    root = Path(outdir)
    ncbi_cache = (root / "cache" / "ncbi").resolve()
    resolved = cache_path.resolve()
    if resolved == ncbi_cache or ncbi_cache in resolved.parents:
        raise ValueError("Provider private cache must not be under cache/ncbi.")
    return cache_path
