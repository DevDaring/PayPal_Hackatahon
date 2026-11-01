"""Private document storage. Keys are server-generated; user filenames never touch the path."""

from __future__ import annotations

import uuid
from pathlib import Path

from .config import get_settings


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("storage key escapes the storage root")
        return p

    def put(self, workspace_id: uuid.UUID, data: bytes, suffix: str = ".pdf") -> str:
        key = f"{workspace_id}/{uuid.uuid4().hex}{suffix}"
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()


_storage: LocalStorage | None = None


def storage() -> LocalStorage:
    global _storage
    if _storage is None:
        _storage = LocalStorage(get_settings().storage_dir)
    return _storage
