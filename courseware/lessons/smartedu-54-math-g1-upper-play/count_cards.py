"""Render the exact group sizes for the ribbon-game picture choices."""

from pathlib import Path
from sys import argv

from PIL import Image, ImageDraw, ImageOps


def render_count_cards(assets):
    players = []
    for number in range(1, 6):
        with Image.open(assets / f'player-{number}.png') as image:
            players.append(ImageOps.contain(image.convert('RGB'), (148, 194)))

    for name, count in (('three', 3), ('four', 4), ('five', 5)):
        card = Image.new('RGB', (960, 576), '#FFF8ED')
        draw = ImageDraw.Draw(card)
        draw.rounded_rectangle((36, 86, 924, 484), radius=46, fill='#F8E7CF')
        pitch = 162
        first = 480 - (count - 1) * pitch // 2
        for slot, player in enumerate(players[:count]):
            center = first + slot * pitch
            card.paste(player, (center - player.width // 2, 188 - player.height // 2))
        left = first - 72
        right = first + (count - 1) * pitch + 72
        draw.rounded_rectangle((left, 330, right, 390), radius=19, fill='#E8843D', outline='#A9492F', width=4)
        with (assets / f'rule-{name}.png').open('xb') as output:
            card.save(output, format='PNG', optimize=True)


if __name__ == '__main__':
    if len(argv) > 2:
        raise SystemExit('Usage: count_cards.py [assets-directory]')
    render_count_cards(Path(argv[1]) if len(argv) == 2 else Path(__file__).with_name('assets'))
