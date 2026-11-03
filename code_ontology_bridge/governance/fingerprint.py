"""Content fingerprints for freshness checks.

A certification is only as strong as the evidence it was made against. Each
event stores a fingerprint of the source files its check read; when the files
change, the fingerprint moves and the certification is stale. Modification
times play no part, so a fresh clone of the same commit yields the same value.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

ABSENT = "absent"


def resolve(root: Path, rel: str) -> Path:
    """Resolve a recorded source path; absolute paths are kept as given."""
    path = Path(rel)
    return path if path.is_absolute() else root / path


def file_token(root: Path, rel: str) -> str:
    """SHA-256 of a file's bytes, or ``absent`` when it cannot be read."""
    try:
        return hashlib.sha256(resolve(root, rel).read_bytes()).hexdigest()
    except OSError:
        return ABSENT


def compute_source_fingerprint(root: Path, rel_paths: Iterable[str]) -> str:
    """Deterministic 16-hex digest over ``path NUL content-hash`` lines.

    Paths are sorted and take part in the digest, so a file that appears,
    disappears or moves changes the value as much as an edit does.
    """
    digest = hashlib.sha256()
    for rel in sorted({str(p) for p in rel_paths}):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_token(root, rel).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()[:16]


def file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
