"""Build harbor game art from locally registered illustration sources."""

from PIL import Image

from quantity_compositions import ROOT, _place, _sprite


BOAT_COUNTS = (1, 2, 3, 4, 6, 8)


def boat_target(boat, count):
    """Use one isolated boat per position, with gaps even in the largest group."""
    image = Image.new('RGBA', (184, 112))
    top = min(count, 4)
    rows = [top] if count <= 4 else [top, count - top]
    for row, length in enumerate(rows):
        y = 56 if len(rows) == 1 else 28 + 56 * row
        _place(image, boat, [(int(92 + (i - (length - 1) / 2) * 42), y)
                             for i in range(length)], (36, 46))
    return image


def main():
    source = ROOT / 'art-source'
    assets = ROOT / 'assets'
    assets.mkdir(exist_ok=True)
    with Image.open(source / 'harbor-backdrop.png') as image:
        image.thumbnail((1280, 720), Image.Resampling.LANCZOS)
        image.save(assets / 'game-harbor.png', optimize=True)
    for key in ('rover', 'rover-pop', 'scallop-shell-single'):
        if key == 'scallop-shell-single':
            sprite = _sprite(source / f'{key}.png')
        else:
            with Image.open(source / f'{key}.webp') as image:
                sprite = image.convert('RGBA')
        sprite.thumbnail((256, 256), Image.Resampling.LANCZOS)
        name = 'game-shell' if key == 'scallop-shell-single' else f'game-{key}'
        sprite.save(assets / f'{name}.png', optimize=True)
    boat = _sprite(source / 'wooden-boat-single.png')
    for count in BOAT_COUNTS:
        boat_target(boat, count).save(assets / f'boat-target-{count}.png', optimize=True)


if __name__ == '__main__':
    main()
