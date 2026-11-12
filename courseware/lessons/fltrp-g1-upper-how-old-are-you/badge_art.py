"""Draw the lesson's exact age numerals and the physical orientation of their badges."""

from hashlib import sha256
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
FONT = ROOT.parents[2] / 'mobile/test/assets/fonts/NotoSansCJKsc-Regular.otf'
NUMERAL = '#254c3d'
BASELINE = '#ae6033'
BADGE_SIZE = (256, 256)
SCENE_SIZE = (640, 380)

BADGE_LAYOUTS = {
    'badge-three': (3,),
    'badge-six': (6,),
    'badge-seven': (7,),
    'badge-eight': (8,),
    'badge-nine': (9,),
    'badge-ten': (10,),
    'badge-six-inverted': (6,),
    'badge-direction-upright': (6,),
    'badge-direction-inverted': (6,),
    'quiz-age-pair-four-five': (4, 5),
    'quiz-age-pair-three-four': (3, 4),
    'quiz-age-pair-four-four': (4, 4),
}


def badge(age):
    image = Image.new('RGBA', BADGE_SIZE)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((25, 12, 231, 243), radius=35, fill='#ffedc6', outline='#5a7a5d', width=10)
    draw.rounded_rectangle((69, 201, 187, 214), radius=6, fill=BASELINE)
    font = ImageFont.truetype(str(FONT), 140 if age < 10 else 126)
    text = str(age)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font, stroke_width=2)
    draw.text((128 - (left + right) / 2, 113 - (top + bottom) / 2), text, font=font,
              fill=NUMERAL, stroke_width=2, stroke_fill=NUMERAL)
    return image


def render_badge_art(key):
    ages = BADGE_LAYOUTS[key]
    sprites = [badge(age) for age in ages]
    if key.endswith('-inverted'):
        sprites[0] = sprites[0].transpose(Image.Transpose.ROTATE_180)
    if key.startswith('badge-') and not key.startswith('badge-direction-'):
        return sprites[0]
    scene = Image.new('RGB', SCENE_SIZE, '#fff5df')
    centers = (320,) if len(sprites) == 1 else (190, 450)
    for x, sprite in zip(centers, sprites):
        scene.paste(sprite, (x - BADGE_SIZE[0] // 2, 62), sprite)
    return scene


def write_badge_art():
    manifest_path = ROOT / 'asset-provenance.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {
        'schemaVersion': 'mira.courseware.asset-provenance.v1',
        'assets': {},
    }
    assets = manifest['assets']
    renderer_sha = sha256(Path(__file__).read_bytes()).hexdigest()
    font_sha = sha256(FONT.read_bytes()).hexdigest()
    for key, ages in BADGE_LAYOUTS.items():
        image = render_badge_art(key)
        with io.BytesIO() as stream:
            image.save(stream, format='PNG', optimize=True)
            data = stream.getvalue()
        path = f'assets/{key}.png'
        (ROOT / path).parent.mkdir(exist_ok=True)
        (ROOT / path).write_bytes(data)
        assets[key] = {
            'sourceKind': 'deterministic_age_badge_diagram',
            'path': path,
            'sha256': sha256(data).hexdigest(),
            'bytes': len(data),
            'pixels': list(image.size),
            'ages': list(ages),
            'rotatedDegrees': 180 if key.endswith('-inverted') else 0,
            'renderer': Path(__file__).name,
            'rendererSha256': renderer_sha,
            'font': 'mobile/test/assets/fonts/NotoSansCJKsc-Regular.otf',
            'fontSha256': font_sha,
        }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    write_badge_art()
