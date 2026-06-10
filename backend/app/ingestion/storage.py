"""File storage abstraction (Phase 1A: local filesystem backend).

Layout (relative to the configured base path):

    <base>/reports/YYYY/MM/<uuid>.pdf

Key rules:
  * Original filenames are NEVER trusted as paths — every stored file gets a
    fresh UUID name, preventing path traversal and collisions.
  * The DB stores the *relative* storage_path (backend-agnostic); the service
    resolves it to an absolute path via `get_absolute_path()`.

A future S3 backend can implement the same surface (save/read/get_absolute_path)
without touching callers.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class LocalStorage:
    """Stores uploaded documents on the local filesystem."""

    def __init__(self, base_path: str | None = None) -> None:
        self._base = Path(base_path or settings.storage_local_path).resolve()

    def _dated_dir(self, now: datetime | None = None) -> Path:
        now = now or datetime.now(timezone.utc)
        return Path("reports") / f"{now.year:04d}" / f"{now.month:02d}"

    def save(self, data: bytes, *, extension: str = ".pdf") -> str:
        """Persist bytes under a UUID name; return the relative storage path."""
        rel_dir = self._dated_dir()
        filename = f"{uuid.uuid4().hex}{extension.lower()}"
        rel_path = rel_dir / filename
        abs_path = self._base / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(data)
        log.info("storage.saved", storage_path=str(rel_path), bytes=len(data))
        return str(rel_path)

    def get_absolute_path(self, storage_path: str) -> Path:
        """Resolve a stored relative path to an absolute filesystem path."""
        return self._base / storage_path

    def read(self, storage_path: str) -> bytes:
        return self.get_absolute_path(storage_path).read_bytes()


def get_storage() -> LocalStorage:
    """Storage accessor (FastAPI/Celery dependency). S3 backend added later."""
    return LocalStorage()
