"""Render the age lesson's explanation and picture-check art from local masters."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


FONT = Path(__file__).resolve().parents[3] / 'mobile/test/assets/fonts/NotoSansCJKsc-Regular.otf'
SLIDES = ('workshop-cover', 'friends-different-heights', 'same-age-pair', 'interview-desk')
GUESTS = 'gallery-quiz-guests'
SOURCE_GROUPS = {
    **{key: (key,) for key in SLIDES},
    'question-meaning-triptych': ('quiz-asking-greeting', 'quiz-asking-age', 'quiz-asking-name'),
    GUESTS: ('quiz-guest-earmuffs', 'quiz-guest-roundhat', 'quiz-guest-apron'),
    'answering-after-name-triptych': ('quiz-answering-age', 'quiz-answering-name', 'quiz-answering-greeting'),
}
# Centers are in the original square panel, before removing the atlas gutters.
AGE_MARKS = {
    'quiz-asking-age': (7, (364, 553), (319, 633, 410, 645)),
    'quiz-answering-age': (8, (509, 587), (464, 648, 555, 660)),
}


def draw_age(panel, key):
    age, (x, y), baseline = AGE_MARKS[key]
    draw = ImageDraw.Draw(panel)
    font = ImageFont.truetype(str(FONT), 152)
    text = str(age)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font, stroke_width=2)
    draw.text((x - (left + right) / 2, y - (top + bottom) / 2), text,
              font=font, fill='#254c3d', stroke_width=2, stroke_fill='#254c3d')
    draw.rounded_rectangle(baseline, radius=6, fill='#ae6033')


def source_art(source, key, original):
    if source in SLIDES:
        return ImageOps.fit(original.convert('RGB'), (960, 540), Image.Resampling.LANCZOS), None
    index = SOURCE_GROUPS[source].index(key)
    left = index * 724
    if source == GUESTS:
        crop = (left, 0, left + 724, 724)
        panel = Image.new('RGBA', (724, 724), '#fff5df')
        panel.alpha_composite(original.crop(crop))
        return panel.convert('RGB').resize((320, 320), Image.Resampling.LANCZOS), crop
    panel = original.crop((left, 0, left + 724, 724))
    if key in AGE_MARKS:
        draw_age(panel, key)
    # Drop both atlas separator strips by the same amount for every option.
    inset = 10
    crop = (left + inset, inset, left + 724 - inset, 724 - inset)
    return panel.crop((inset, inset, 724 - inset, 724 - inset)).resize(
        (320, 320), Image.Resampling.LANCZOS), crop
