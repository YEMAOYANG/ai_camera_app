"""Draw four matched age badges with the exact teaching numerals."""

from hashlib import sha256
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
FONT = ROOT.parents[2] / 'mobile/test/assets/fonts/NotoSansCJKsc-Regular.otf'
AGES = {'age-two': 2, 'age-four': 4, 'age-five': 5, 'age-eight': 8}


def badge(age):
    image = Image.new('RGBA', (256, 256))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((24, 18, 231, 238), radius=32, fill='#ffedc6', outline='#547766', width=9)
    draw.rounded_rectangle((69, 200, 187, 212), radius=6, fill='#ad6139')
    number = str(age)
    font = ImageFont.truetype(str(FONT), 140)
    left, top, right, bottom = draw.textbbox((0, 0), number, font=font)
    draw.text((128 - (left + right) / 2, 112 - (top + bottom) / 2), number, font=font, fill='#254c3d')
    return image


def write_badges():
    path = ROOT / 'asset-provenance.json'
    manifest = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
        'schemaVersion': 'mira.courseware.asset-provenance.v1', 'assets': {},
    }
    font_sha = sha256(FONT.read_bytes()).hexdigest()
    renderer_sha = sha256(Path(__file__).read_bytes()).hexdigest()
    for key, age in AGES.items():
        with io.BytesIO() as stream:
            badge(age).save(stream, format='PNG', optimize=True)
            data = stream.getvalue()
        name = f'assets/{key}.png'
        (ROOT / name).parent.mkdir(exist_ok=True)
        (ROOT / name).write_bytes(data)
        manifest['assets'][key] = {
            'sourceKind': 'deterministic_age_badge_diagram', 'path': name,
            'sha256': sha256(data).hexdigest(), 'bytes': len(data), 'pixels': [256, 256], 'age': age,
            'renderer': Path(__file__).name, 'rendererSha256': renderer_sha,
            'font': 'mobile/test/assets/fonts/NotoSansCJKsc-Regular.otf', 'fontSha256': font_sha,
        }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    write_badges()
