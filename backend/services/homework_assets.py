"""Private, metadata-stripped homework assets; no public URLs or camera access."""
from __future__ import annotations
import hashlib
import io
import os
from pathlib import Path
import re
import tempfile
from PIL import Image, ImageOps, ImageStat
from core.errors import ApiError


class HomeworkAssetStore:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def _path(self, key):
        if not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{2}/[a-f0-9]{64}\.(png|wav|mp3|json)', key):
            raise ApiError('homework_asset_invalid', '作业文件无效', 404)
        result = (self.root / key).resolve()
        if self.root not in result.parents:
            raise ApiError('homework_asset_invalid', '作业文件无效', 404)
        return result

    def put(self, data, *, namespace, suffix='png'):
        # Child/submission namespace prevents global cross-family content addressing.
        identity = hashlib.sha256(namespace.encode() + b'\0' + data).hexdigest()
        key = f'{identity[:2]}/{identity}.{suffix}'
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not path.exists():
            fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.upload-')
            try:
                with os.fdopen(fd, 'wb') as file:
                    file.write(data)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return key

    def response_key(self, namespace):
        """Private deterministic journal address; never a public asset URL."""
        identity=hashlib.sha256(('homework-response-journal:'+namespace).encode()).hexdigest()
        return f'{identity[:2]}/{identity}.json'

    def put_response(self, data, *, namespace):
        # The durable reservation's namespace gives recovery one exact file to
        # read even if the process died before its database link committed.
        key=self.response_key(namespace)
        path=self._path(key)
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if path.exists():
            if path.read_bytes()!=data:
                raise ApiError('homework_response_conflict','已保存的识别响应不能替换',409)
            return key
        fd,temporary=tempfile.mkstemp(dir=path.parent,prefix='.response-')
        try:
            with os.fdopen(fd,'wb') as file:
                file.write(data);file.flush();os.fsync(file.fileno())
            os.replace(temporary,path)
            directory_fd=os.open(path.parent,os.O_RDONLY)
            try:os.fsync(directory_fd)
            finally:os.close(directory_fd)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)
        return key

    def read(self, key):
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            raise ApiError('homework_asset_missing', '作业图片已删除或暂不可用', 404)

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)


def normalize_image(data, policy):
    if not isinstance(data, bytes) or not 1 <= len(data) <= policy['maxUploadBytes']:
        raise ApiError('homework_image_size', '每张图片不能超过12MB', 413)
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in {'PNG', 'JPEG'} or source.width * source.height > policy['maxImagePixels']:
                raise ValueError('unsupported image')
            source.load()
            image = ImageOps.exif_transpose(source).convert('RGB')
            output = io.BytesIO()
            image.save(output, format='PNG')
            return output.getvalue(), image.width, image.height
    except (OSError, ValueError, Image.DecompressionBombError):
        raise ApiError('homework_image_invalid', '请上传清晰的JPEG或PNG图片', 400)


def crop_region(raw):
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != {'x', 'y', 'width', 'height'}:
        raise ApiError('homework_region_invalid', '裁剪区域无效', 400)
    if any(type(v) not in {int, float} or not 0 <= v <= 1 for v in raw.values()):
        raise ApiError('homework_region_invalid', '裁剪区域无效', 400)
    if raw['width'] <= 0 or raw['height'] <= 0 or raw['x'] + raw['width'] > 1.000001 or raw['y'] + raw['height'] > 1.000001:
        raise ApiError('homework_region_invalid', '裁剪区域超出图片', 400)
    return {key: round(float(value), 6) for key, value in raw.items()}


def transformed_geometry(width, height, rotation=0, crop=None):
    """Display geometry in the same coordinate space sent to recognition."""
    if rotation in {90, 270}:
        width, height = height, width
    box = None
    if crop:
        x, y, w, h = (crop[key] for key in ('x', 'y', 'width', 'height'))
        box=(int(x*width),int(y*height),int((x+w)*width),int((y+h)*height))
        if box[2]<=box[0] or box[3]<=box[1]:
            raise ApiError('homework_region_invalid','裁剪区域太小，请保留清晰完整的题目',400)
        width, height = box[2]-box[0], box[3]-box[1]
    return (width, height), box


def transformed_image(data, rotation=0, crop=None):
    image = Image.open(io.BytesIO(data)).convert('RGB')
    _, box = transformed_geometry(image.width, image.height, rotation, crop)
    image = image.rotate(-rotation, expand=True)
    if box:
        image = image.crop(box)
    output = io.BytesIO()
    image.save(output, format='PNG')
    return output.getvalue(), image


def quality_error(image, policy):
    # Conservative capture gates; this is not a claim of handwriting/OCR accuracy.
    if min(image.size) < policy['minimumImageSide']:
        return 'image_too_small'
    preview = image.copy()
    preview.thumbnail((800,800))
    gray = preview.convert('L')
    if ImageStat.Stat(gray).stddev[0] < 4:
        return 'image_blank_or_unreadable'
    return None
