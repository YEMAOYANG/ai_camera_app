"""Smaller delivery copies of reviewed lesson pictures and narration.

The reviewed bytes stay the reference. A published item made from such a copy
records the digest of the original it was encoded from, and the audio audit is
checked against that digest. When a tool is missing, fails, or does not make
the file clearly smaller, the original is delivered unchanged.
"""
import io
import shutil
import subprocess
import tempfile
from pathlib import Path


def _webp(raw):
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as image:
        if getattr(image, 'is_animated', False):
            return None
        output = io.BytesIO()
        image.save(output, 'WEBP', quality=84, method=6)
    return output.getvalue()


def _mp3(raw):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        return None
    with tempfile.TemporaryDirectory() as folder:
        source, target = Path(folder) / 'in.wav', Path(folder) / 'out.mp3'
        source.write_bytes(raw)
        # Fixed settings and no metadata, so the same narration always
        # encodes to the same bytes with the same tool version.
        subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-i', str(source), '-vn', '-ac', '1',
                        '-codec:a', 'libmp3lame', '-b:a', '64k', '-map_metadata', '-1',
                        '-fflags', '+bitexact', '-flags:a', '+bitexact', str(target)],
                       check=True, timeout=120, stdin=subprocess.DEVNULL)
        return target.read_bytes()


ENCODERS = {'.png': ('.webp', _webp), '.wav': ('.mp3', _mp3)}


def compact_copy(suffix, raw):
    """Return ``(suffix, bytes)`` to deliver for one reviewed media file."""
    target, encode = ENCODERS.get(suffix, (None, None))
    if not encode:
        return suffix, raw
    try:
        smaller = encode(raw)
    except Exception:  # an unreadable original is still delivered as reviewed
        return suffix, raw
    return (target, smaller) if smaller and len(smaller) * 5 <= len(raw) * 4 else (suffix, raw)
