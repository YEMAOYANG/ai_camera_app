"""Exact mathematical pictures used by this lesson's picture quiz."""
from pathlib import Path
from PIL import Image, ImageDraw

SIZE = 512
SHAPES = {
    'square': [(116, 116), (396, 116), (396, 396), (116, 396)],
    'triangle': [(256, 84), (426, 414), (86, 414)],
    'rectangle': [(66, 166), (446, 166), (446, 346), (66, 346)],
}
ARROWS = {
    'up': [(216, 420), (296, 420), (296, 224), (396, 224), (256, 72), (116, 224), (216, 224)],
    'left': [(420, 216), (420, 296), (224, 296), (224, 396), (72, 256), (224, 116), (224, 216)],
    'right': [(92, 216), (92, 296), (288, 296), (288, 396), (440, 256), (288, 116), (288, 216)],
}
RECORD_COUNTS = {f'record-{count}': count for count in range(6, 11)}


def render(name, pictures=None):
    image = Image.new('RGB', (SIZE, SIZE), '#fffaf0')
    draw = ImageDraw.Draw(image)
    if name in SHAPES:
        draw.polygon(SHAPES[name], fill='#ddb17a', outline='#80572e', width=10)
    elif name in ARROWS:
        draw.polygon(ARROWS[name], fill='#4e825b', outline='#2d5337', width=7)
    elif name in RECORD_COUNTS:
        for index in range(RECORD_COUNTS[name]):
            row, column = divmod(index, 5)
            x = 48 + 88 * column
            y = 140 + 160 * row
            draw.ellipse((x, y, x + 64, y + 64), fill='#c17b48')
    elif name == 'left-route':
        # Empty destination circle is strictly left of the starting point.
        draw.line((100, 256, 405, 256), fill='#ded5bf', width=12)
        draw.ellipse((57, 213, 143, 299), fill='#fffaf0', outline='#678d6b', width=9)
        draw.ellipse((362, 213, 448, 299), fill='#dfa85e', outline='#825a32', width=7)
        draw.line((405, 249, 405, 184), fill='#825a32', width=8)
        draw.polygon([(405, 164), (388, 190), (422, 190)], fill='#825a32')
    elif name == 'stamp-demo':
        draw.ellipse((46, 186, 206, 346), fill='#ddb17a', outline='#80572e', width=9)
        draw.ellipse((306, 186, 466, 346), fill='#e8a173', outline='#ac6246', width=9)
        draw.line((230, 266, 280, 266), fill='#678d6b', width=10)
        draw.polygon([(294, 266), (274, 252), (274, 280)], fill='#678d6b')
    elif name == 'route-demo':
        for y in range(4):
            draw.rectangle((166, 44 + y*110, 346, 154 + y*110), outline='#819c7d', width=4)
        draw.ellipse((221, 399, 291, 469), fill='#dfa85e', outline='#825a32', width=6)
        for y in (350, 240, 130):
            draw.line((256, y+15, 256, y-20), fill='#4e825b', width=9)
            draw.polygon([(256,y-35),(240,y-12),(272,y-12)],fill='#4e825b')
    elif name == 'score-demo':
        pictures = pictures or {key: Image.open(Path(__file__).parent / 'assets' / (key + '.png')) for key in ('leaf','flower')}
        for key, y, count in [('flower', 72, 1), ('leaf', 292, 2)]:
            icon = pictures[key].convert('RGB').resize((172,172))
            image.paste(icon, (40,y))
            draw.line((225,y+86,279,y+86), fill='#678d6b', width=9)
            draw.polygon([(294,y+86),(273,y+72),(273,y+100)],fill='#678d6b')
            for index in range(count):
                x = 320 + 90*index
                draw.ellipse((x,y+54,x+62,y+116),fill='#c17b48')
    else:
        raise ValueError(name)
    return image


def build_assets(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name in list(SHAPES) + list(ARROWS) + list(RECORD_COUNTS) + ['left-route', 'stamp-demo', 'route-demo', 'score-demo']:
        render(name).save(destination / (name + '-diagram.png'))


if __name__ == '__main__':
    build_assets(Path(__file__).parent / 'assets')
