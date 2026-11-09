"""Draw the exact three book-count states in the four worked examples."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ASSETS = Path(__file__).parent / 'assets'
EXAMPLES = {
    'add-add': (3, 1, 2),
    'subtract-subtract': (9, -4, -2),
    'add-subtract': (3, 4, -1),
    'subtract-add': (7, -4, 2),
}
DOT_COLOR = '#3d785e'
DOT_POSITIONS = tuple((68 + 86 * column, 94 + 112 * row) for row in range(2) for column in range(5))


def count_states(initial, first, second):
    counts = (initial, initial + first, initial + first + second)
    if not all(0 <= count <= 10 for count in counts):
        raise ValueError('Book counts must stay within the ten-slot shelf')
    return counts


def render(example, book):
    counts = count_states(*example)
    canvas = Image.new('RGBA', (840, 600), '#fdf5e4')
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=54)
    book = book.convert('RGBA')
    book.thumbnail((74, 74), Image.Resampling.LANCZOS)
    for step, count in enumerate(counts):
        y = 10 + step * 198
        draw.rounded_rectangle((10, y, 830, y + 182), 28, fill='#fffdf4', outline='#cab592', width=4)
        draw.rounded_rectangle((39, y + 53, 153, y + 129), 22, fill='#e4f0e5')
        draw.text((96, y + 90), str(count), font=font, anchor='mm', fill='#245347')
        for slot in range(10):
            row, column = divmod(slot, 5)
            x = 194 + column * 120
            top = y + 13 + row * 80
            fill = '#f4e5ca'
            if slot < count:
                grew = step > 0 and slot >= counts[step - 1]
                fill = '#e6f2e8' if grew else '#fff4dc'
            draw.rounded_rectangle((x, top, x + 104, top + 74), 10, fill=fill, outline='#d1b48d', width=3)
            if slot < count:
                canvas.alpha_composite(book, (x + (104 - book.width) // 2, top + (74 - book.height) // 2))
    return canvas.convert('RGB')


def render_quantity(count):
    if type(count) is not int or not 0 <= count <= 10:
        raise ValueError('Quantity must fit in two rows of five')
    canvas = Image.new('RGB', (480, 300), '#fffaf0')
    draw = ImageDraw.Draw(canvas)
    for index, (x, y) in enumerate(DOT_POSITIONS):
        draw.rounded_rectangle((x - 34, y - 34, x + 34, y + 34), 12, outline='#c7b892', width=3)
        if index < count:
            draw.ellipse((x - 25, y - 25, x + 25, y + 25), fill=DOT_COLOR)
    return canvas


if __name__ == '__main__':
    with Image.open(ASSETS / 'single-book.png') as image:
        for key, example in EXAMPLES.items():
            render(example, image).save(ASSETS / f'{key}.png')
    for count in range(2, 11):
        render_quantity(count).save(ASSETS / f'quantity-{count}.png')
