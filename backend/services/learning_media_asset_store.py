from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import tempfile
from typing import Protocol


@dataclass(frozen=True)
class StoredMediaAsset:
    storage_key: str
    byte_size: int
    content_hash: str


class LearningMediaAssetStore(Protocol):
    def put_audio(
        self,
        *,
        job_id: str,
        segment_id: str,
        content_hash: str,
        mime_type: str,
        audio: bytes,
    ) -> StoredMediaAsset:
        """Persist immutable bytes and return a server-side storage key."""

    def read_audio(self, storage_key: str) -> bytes:
        """Read the exact final-storage bytes for integrity validation."""


class FilesystemLearningMediaAssetStore:
    """Content-addressed local store for development or a single-node worker.

    Production object storage can implement the same protocol.  The returned
    key is relative and is never a public URL; signed delivery remains an API
    concern.
    """

    _EXTENSIONS = {
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/flac": "flac",
        "audio/ogg": "ogg",
        "audio/webm": "webm",
    }

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()

    def put_audio(
        self,
        *,
        job_id: str,
        segment_id: str,
        content_hash: str,
        mime_type: str,
        audio: bytes,
    ) -> StoredMediaAsset:
        actual_hash = hashlib.sha256(audio).hexdigest()
        if actual_hash != content_hash:
            raise ValueError("media bytes do not match the declared checksum")
        extension = self._EXTENSIONS.get(str(mime_type).split(";", 1)[0].strip().lower())
        if extension is None:
            raise ValueError("unsupported generated audio MIME type")
        safe_job_id = self._safe_component(job_id)
        safe_segment_id = self._safe_component(segment_id)
        relative = Path("narration") / safe_job_id / f"{safe_segment_id}-{actual_hash}.{extension}"
        destination = (self.root / relative).resolve()
        if self.root not in destination.parents:
            raise ValueError("invalid media storage path")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            persisted_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
            if persisted_hash != actual_hash:
                raise ValueError("existing media object has a different checksum")
        else:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".mira-audio-",
                dir=str(destination.parent),
            )
            try:
                with os.fdopen(descriptor, "wb") as temporary:
                    temporary.write(audio)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temporary_name, destination)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)
        return StoredMediaAsset(
            storage_key=relative.as_posix(),
            byte_size=len(audio),
            content_hash=actual_hash,
        )

    def read_audio(self, storage_key: str) -> bytes:
        normalized = str(storage_key or "").strip()
        if not normalized or Path(normalized).is_absolute():
            raise ValueError("invalid media storage key")
        source = (self.root / normalized).resolve()
        if self.root not in source.parents or not source.is_file():
            raise ValueError("media object is unavailable")
        return source.read_bytes()

    @staticmethod
    def _safe_component(value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for character in normalized
        ):
            raise ValueError("media storage identifiers must be URL-safe")
        return normalized
