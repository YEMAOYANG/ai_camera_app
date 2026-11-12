"""Derive game sprites and opening cards from the lesson's ImageGen masters."""

import io

from PIL import Image, ImageOps


ATLAS_LAYOUTS = {
    'birthday-game-actors': (3, 2, ('boat-idle', 'boat-blow', 'maze-rover', 'maze-bubble', 'birthday-sticker')),
    'workshop-gift-atlas': (3, 2, ('gift-pen', 'gift-pencil', 'gift-ball', 'gift-book', 'gift-bag')),
    'birthday-dialogue-atlas': (2, 2, ('role-wish', 'role-give', 'role-thanks', 'role-welcome')),
}
BACKDROPS = ('boat-backdrop', 'maze-backdrop')
# These rectangles are in isolated atlas cells. The active boat is 5 px left
# of its idle chassis. The active rover is 32 px left and 2 px lower.
VEHICLE_CROPS = {
    'boat-idle': (32, 110, 492, 398),
    'boat-blow': (27, 110, 487, 398),
    'maze-rover': (61, 91, 534, 427),
    'maze-bubble': (29, 93, 502, 429),
}
OPENINGS = {
    'boat-opening': ('boat-backdrop', {
        'boat-idle': ((384, 286), (235, 142)),
        'gift-ball': ((222, 158), (110, 110)),
        'gift-book': ((546, 158), (110, 110)),
    }),
    'maze-opening': ('maze-backdrop', {
        'maze-rover': ((385, 279), (206, 125)),
        'role-wish': ((231, 161), (112, 112)),
        'role-give': ((537, 161), (128, 112)),
    }),
}


def sprite_art(source, key, master):
    columns, rows, keys = ATLAS_LAYOUTS[source]
    row, column = divmod(keys.index(key), columns)
    width, height = master.width // columns, master.height // rows
    cell_box = (column * width, row * height, (column + 1) * width, (row + 1) * height)
    cell = master.crop(cell_box)
    crop = VEHICLE_CROPS.get(key)
    if crop is None:
        alpha = cell.getchannel('A')
        left, top, right, bottom = alpha.point(lambda level: 255 if level >= 8 else 0).getbbox()
        crop = (max(0, left - 8), max(0, top - 8), min(width, right + 8), min(height, bottom + 8))
    # A common alignment box can extend beyond a cell. Cropping the isolated
    # RGBA cell pads with transparency instead of picking up another sprite.
    sprite = ImageOps.contain(cell.crop(crop), (260, 260), Image.Resampling.LANCZOS)
    return sprite, cell_box, crop


def backdrop_art(master):
    return ImageOps.fit(master.convert('RGB'), (1280, 720), Image.Resampling.LANCZOS)


def opening_art(key, load):
    background, props = OPENINGS[key]
    canvas = load(background).convert('RGBA').resize((768, 432), Image.Resampling.LANCZOS)
    for asset, ((x, y), limits) in props.items():
        sprite = ImageOps.contain(load(asset).convert('RGBA'), limits, Image.Resampling.LANCZOS)
        canvas.alpha_composite(sprite, (x - sprite.width // 2, y - sprite.height // 2))
    return canvas.convert('RGB')


def png(image):
    with io.BytesIO() as stream:
        image.save(stream, format='PNG', optimize=True)
        return stream.getvalue()
