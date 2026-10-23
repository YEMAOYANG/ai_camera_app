"""Reproduce both old and improved quantity diagrams from one frozen image.

The caller verifies the old frozen PNG hash and compares its complete decoded
RGB pixels to the reconstructed diagram. This tolerates PNG encoder versions,
never a visual difference. New diagrams retain the count and cannot overlap.
No model, network, OCR, or image-semantics assertion is used here.
"""
import io

from PIL import Image

TRANSFORM = 'rgb-thumbnail-repeat-png.v1'


def rgb_pixels(raw):
    with Image.open(io.BytesIO(raw)) as image:
        if image.format != 'PNG' or any(n > 2048 for n in image.size):
            raise ValueError('数量图必须是有界 PNG')
        return image.size, image.convert('RGB').tobytes()


def quantity_png(raw, *, source_size, count, layout):
    if (not isinstance(source_size, list) or len(source_size) != 2
            or any(type(n) is not int or not 1 <= n <= 12000 for n in source_size)
            or source_size[0] * source_size[1] > 40_000_000
            or type(count) is not int or not 1 <= count <= 20
            or not isinstance(layout, dict) or set(layout) != {
                'cropBox', 'thumbnailSize', 'canvasSize', 'positions', 'centerWithinThumbnail'}):
        raise ValueError('数量图尺寸、数量或布局定义无效')
    crop, thumb, canvas, positions = (layout[k] for k in ('cropBox', 'thumbnailSize', 'canvasSize', 'positions'))
    if (not isinstance(crop, list) or len(crop) != 4 or any(type(n) is not int for n in crop)
            or not 0 <= crop[0] < crop[2] <= source_size[0]
            or not 0 <= crop[1] < crop[3] <= source_size[1]
            or any(not isinstance(v, list) or len(v) != 2
                   or any(type(n) is not int or not 1 <= n <= 2048 for n in v) for v in (thumb, canvas))
            or type(layout['centerWithinThumbnail']) is not bool
            or not isinstance(positions, list) or len(positions) != count
            or any(not isinstance(p, list) or len(p) != 2
                   or any(type(n) is not int or n < 0 for n in p) for p in positions)):
        raise ValueError('数量图必须有完整裁剪范围和逐个对象的位置')
    with Image.open(io.BytesIO(raw)) as original:
        if original.format not in {'PNG', 'JPEG', 'WEBP'} or list(original.size) != source_size:
            raise ValueError('原图格式或尺寸与冻结定义不符')
        tile = original.convert('RGB').crop(tuple(crop))
        tile.thumbnail(tuple(thumb), Image.Resampling.BICUBIC)
    boxes = []
    output = Image.new('RGB', tuple(canvas), '#fffdf7')
    for x, y in positions:
        if layout['centerWithinThumbnail']:
            x += (thumb[0] - tile.width) // 2
        box = (x, y, x + tile.width, y + tile.height)
        if (box[2] > canvas[0] or box[3] > canvas[1]
                or any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in boxes)):
            raise ValueError('每个对象必须完整可见且不能重叠')
        boxes.append(box)
        output.paste(tile, (x, y))
    encoded = io.BytesIO()
    output.save(encoded, format='PNG', optimize=False, compress_level=6)
    return encoded.getvalue()
