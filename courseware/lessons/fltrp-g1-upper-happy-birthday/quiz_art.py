"""Derive uniformly framed picture options from the lesson's five quiz atlases."""

from PIL import Image


SOURCE_GROUPS = {
    'quiz-wish-scenes': ('quiz-wish-farewell', 'quiz-wish-birthday', 'quiz-wish-hello'),
    'quiz-thanks-people': ('quiz-thank-baker', 'quiz-thank-giver', 'quiz-thank-celebrant'),
    'quiz-three-stationery': ('quiz-item-eraser', 'quiz-item-pencil', 'quiz-item-pen'),
    'quiz-welcome-roles': ('quiz-welcome-giver', 'quiz-welcome-receiver', 'quiz-welcome-bystander'),
    'quiz-book-actions': ('quiz-book-reading', 'quiz-book-giving', 'quiz-book-pointing'),
}
CELL_SIZE = 724
INSET = 14
CARD_SIZE = (320, 320)
STATIONERY_ATLAS = 'quiz-three-stationery'


def quiz_art(source, key, master):
    if master.size != (3 * CELL_SIZE, CELL_SIZE):
        raise ValueError('expected a 2172x724 quiz atlas')
    column = SOURCE_GROUPS[source].index(key)
    left = column * CELL_SIZE
    # The divider starts at x=716. Keep the preceding six pixels of the
    # receiving hand and gift in the giver option without changing its scale.
    shift = 6 if key == 'quiz-welcome-giver' else 0
    crop = (left + INSET + shift, INSET, left + CELL_SIZE - INSET + shift, CELL_SIZE - INSET)
    panel = master.crop(crop)
    if source == STATIONERY_ATLAS:
        ground = Image.new('RGBA', panel.size, '#fff5df')
        panel = Image.alpha_composite(ground, panel)
    return panel.convert('RGB').resize(CARD_SIZE, Image.Resampling.LANCZOS), crop
