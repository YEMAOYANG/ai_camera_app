from __future__ import annotations

import io
import os
from typing import Mapping


def frame_gate_config() -> dict:
    return {
        "stable_hash_threshold": int(os.getenv("APP_AI_VISION_STABLE_HASH_THRESHOLD", "8")),
        "max_stale_seconds": int(os.getenv("APP_AI_VISION_MAX_STALE_SECONDS", "180")),
    }


def compute_dhash(image_bytes: bytes, *, hash_size: int = 8) -> str:
    import hashlib

    from PIL import Image

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("L")
    except Exception:
        return hashlib.sha256(image_bytes).hexdigest()[:16]
    resized = image.resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = list(resized.getdata())
    bits: list[str] = []
    for row in range(hash_size):
        row_offset = row * (hash_size + 1)
        for col in range(hash_size):
            left = pixels[row_offset + col]
            right = pixels[row_offset + col + 1]
            bits.append("1" if left > right else "0")
    value = int("".join(bits), 2)
    width = max(1, (hash_size * hash_size + 3) // 4)
    return format(value, f"0{width}x")


def hamming_distance(left: str, right: str) -> int:
    if not left or not right:
        return 999
    length = min(len(left), len(right))
    distance = sum(1 for index in range(length) if left[index] != right[index])
    return distance + abs(len(left) - len(right))


def frame_is_stable(
    *,
    previous: Mapping[str, object] | None,
    current_hash: str,
    now_ms: int,
    threshold: int | None = None,
    max_stale_seconds: int | None = None,
) -> bool:
    config = frame_gate_config()
    threshold = threshold if threshold is not None else config["stable_hash_threshold"]
    max_stale_seconds = max_stale_seconds if max_stale_seconds is not None else config["max_stale_seconds"]
    if not previous:
        return False
    previous_hash = str(previous.get("hash") or "").strip()
    if not previous_hash:
        return False
    last_changed_at = int(previous.get("last_changed_at") or previous.get("updated_at") or 0)
    if last_changed_at > 0 and (now_ms - last_changed_at) > max_stale_seconds * 1000:
        return False
    return hamming_distance(previous_hash, current_hash) <= threshold


def next_frame_state(
    *,
    previous: Mapping[str, object] | None,
    current_hash: str,
    now_ms: int,
) -> dict:
    previous_hash = str((previous or {}).get("hash") or "").strip()
    changed = not previous_hash or hamming_distance(previous_hash, current_hash) > frame_gate_config()["stable_hash_threshold"]
    return {
        "hash": current_hash,
        "last_changed_at": now_ms if changed else int((previous or {}).get("last_changed_at") or now_ms),
        "updated_at": now_ms,
    }
