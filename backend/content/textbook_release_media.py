"""Recognize bounded, self-contained video/model bytes before release archive.

Container validation is not a codec, pedagogy or playback approval. Existing
audio/image admission remains unchanged; new formats need structural headers.
"""
import json
import struct

from content.textbook_release import fail

MAX_MEDIA_BYTES = 16 * 1024 * 1024
MIME_TYPES = {'.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.png': 'image/png', '.webp': 'image/webp',
              '.mp4': 'video/mp4', '.webm': 'video/webm', '.glb': 'model/gltf-binary'}


def _require(condition):
    if not condition:
        fail('课件视频或三维素材容器无效，或引用了未归档的外部资源')


def _mp4(raw):
    _require(len(raw) >= 24 and raw[4:8] == b'ftyp')
    offset, boxes = 0, []
    while offset < len(raw):
        _require(len(raw) - offset >= 8)
        length = int.from_bytes(raw[offset:offset + 4], 'big')
        kind = raw[offset + 4:offset + 8]
        header = 8
        if length == 1:
            _require(len(raw) - offset >= 16)
            length = int.from_bytes(raw[offset + 8:offset + 16], 'big')
            header = 16
        elif length == 0:
            length = len(raw) - offset
        _require(header <= length <= len(raw) - offset)
        if not boxes:
            _require(kind == b'ftyp' and length >= header + 8 and (length - header) % 4 == 0)
        boxes.append(kind)
        offset += length
    _require(b'mdat' in boxes and any(kind in boxes for kind in (b'moov', b'moof')))


def _vint(raw, offset, *, identifier=False):
    _require(offset < len(raw) and raw[offset] != 0)
    first, length, marker = raw[offset], 1, 0x80
    while not first & marker:
        length += 1
        marker >>= 1
    _require(length <= (4 if identifier else 8) and offset + length <= len(raw))
    value = int.from_bytes(raw[offset:offset + length], 'big')
    if not identifier:
        value &= (1 << (7 * length)) - 1
    return value, length, not identifier and value == (1 << (7 * length)) - 1


def _webm(raw):
    _require(len(raw) >= 12 and raw[:4] == b'\x1a\x45\xdf\xa3')
    header_size, size_length, unknown = _vint(raw, 4)
    end, cursor = 4 + size_length + header_size, 4 + size_length
    _require(not unknown and end <= len(raw))
    document_type = None
    while cursor < end:
        kind, id_length, _ = _vint(raw, cursor, identifier=True)
        size, field_length, unknown = _vint(raw, cursor + id_length)
        start = cursor + id_length + field_length
        _require(not unknown and start + size <= end)
        if kind == 0x4282:
            _require(document_type is None)
            document_type = raw[start:start + size]
        cursor = start + size
    _require(cursor == end and document_type == b'webm' and raw[end:end + 4] == b'\x18\x53\x80\x67')
    segment_size, size_length, unknown = _vint(raw, end + 4)
    payload_start = end + 4 + size_length
    _require(payload_start < len(raw) and (unknown or payload_start + segment_size == len(raw)))


def _no_resource_uris(value):
    if isinstance(value, dict):
        return all(not (key == 'uri' and field) and _no_resource_uris(field) for key, field in value.items())
    if isinstance(value, list):
        return all(_no_resource_uris(item) for item in value)
    return True


def _glb(raw):
    _require(len(raw) >= 20 and raw[:4] == b'glTF')
    version, length = struct.unpack_from('<II', raw, 4)
    _require(version == 2 and length == len(raw) and length % 4 == 0)
    cursor, chunks = 12, []
    while cursor < len(raw):
        _require(len(raw) - cursor >= 8)
        size, kind = struct.unpack_from('<II', raw, cursor)
        cursor += 8
        _require(size > 0 and size % 4 == 0 and cursor + size <= len(raw))
        chunks.append((kind, raw[cursor:cursor + size]))
        cursor += size
    _require(1 <= len(chunks) <= 2 and chunks[0][0] == 0x4E4F534A
             and (len(chunks) == 1 or chunks[1][0] == 0x004E4942))
    try:
        document = json.loads(chunks[0][1].decode('utf-8').rstrip(' '))
    except (ValueError, UnicodeError):
        fail('课件三维素材 JSON 数据无效')
    _require(isinstance(document, dict) and isinstance(document.get('asset'), dict)
             and document['asset'].get('version') == '2.0' and _no_resource_uris(document))
    buffers = document.get('buffers', [])
    _require(isinstance(buffers, list) and len(buffers) <= 1)
    if buffers:
        size = buffers[0].get('byteLength') if isinstance(buffers[0], dict) else None
        _require(len(chunks) == 2 and type(size) is int and 0 < size <= len(chunks[1][1]) <= size + 3)


def media_mime_type(suffix, raw):
    suffix = suffix.lower()
    if suffix not in MIME_TYPES or not 0 < len(raw) <= MAX_MEDIA_BYTES:
        fail('课件素材格式或大小无效')
    validator = {'.mp4': _mp4, '.webm': _webm, '.glb': _glb}.get(suffix)
    if validator:
        validator(raw)
    return MIME_TYPES[suffix]
