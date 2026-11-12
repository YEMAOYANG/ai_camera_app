"""Cut registered ImageGen panels and draw the six exact handwriting diagrams."""
from hashlib import sha256
import json
from pathlib import Path
from statistics import median

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parent
CREAM, PINE, SAGE, ORANGE = "#fff1d7", "#24453c", "#a6b8a0", "#bd572c"
ATLAS_SOURCE = "Codex built-in image_gen"
ATLAS_CELLS = {
    "story-atlas": (
        (0, 362, 724, 1086), (0, 362, 725, 1087, 1448),
        ("rabbit-clouds", "bird-low", "insects-low", "fish-surface", "fish-deep", "ants-pack",
         "rabbit-tells-ant", "rabbit-runs", "rain-window", "kids-question", "kids-remind", "umbrella-sticker"),
    ),
    "word-atlas": (
        (0, 362, 724, 1086, 1448), (0, 361, 724, 1086),
        ("overcast", "wet-leaf", "free-time", "stuffy", "rush", "news", "water-surface",
         "bend", "bright", "dry-leaf", "busy", "stand"),
    ),
    "game-atlas": (
        (0, 362, 724, 1086, 1448), (0, 362, 725, 1086),
        ("bird-icon", "fish-icon", "ant-icon", "rain-icon", "weather-boat", "weather-boat-pop",
         "maze-rover", "maze-rover-pop", "game-sticker", "game-bubble", "weather-backdrop", "maze-backdrop"),
    ),
    "quiz-atlas": (
        (0, 318, 636, 971), (0, 324, 647, 971, 1294, 1619),
        tuple(f"quiz-{number}-{letter}" for number in range(1, 6) for letter in "abc"),
    ),
}

# Normalized centerlines in book stroke order. Every tuple is one stroke.
STROKES = {
    "这": (
        ((.53,.21),(.61,.28)), ((.44,.34),(.78,.32)),
        ((.66,.34),(.58,.52),(.44,.64)), ((.49,.42),(.62,.52),(.73,.64)),
        ((.25,.30),(.32,.37)), ((.19,.48),(.34,.47),(.30,.55),(.35,.61),(.26,.74)),
        ((.18,.78),(.32,.75),(.48,.78),(.70,.82),(.84,.80)),
    ),
    "看": (
        ((.64,.20),(.49,.24),(.36,.26)), ((.38,.33),(.64,.31)), ((.28,.43),(.75,.41)),
        ((.56,.25),(.50,.45),(.41,.63),(.27,.75)),
        ((.47,.52),(.46,.83)), ((.48,.52),(.69,.50),(.69,.83)),
        ((.48,.61),(.68,.60)), ((.48,.70),(.68,.69)), ((.47,.79),(.69,.78)),
    ),
    "鱼": (
        ((.51,.18),(.45,.29),(.34,.38)), ((.46,.27),(.64,.26),(.53,.41)),
        ((.34,.44),(.39,.70)), ((.35,.44),(.70,.41),(.65,.70)),
        ((.37,.55),(.68,.53)), ((.52,.44),(.53,.68)), ((.39,.68),(.65,.66)),
        ((.21,.79),(.49,.77),(.81,.75)),
    ),
    "面": (
        ((.31,.24),(.70,.22)), ((.50,.24),(.45,.38)), ((.26,.40),(.29,.80)),
        ((.27,.41),(.75,.38),(.73,.81)), ((.42,.40),(.43,.76)), ((.60,.39),(.60,.76)),
        ((.43,.53),(.59,.52)), ((.43,.64),(.59,.63)), ((.29,.77),(.73,.75)),
    ),
    "问": (
        ((.29,.21),(.36,.28)), ((.25,.32),(.25,.80)),
        ((.42,.27),(.75,.25),(.75,.81),(.68,.75)),
        ((.43,.46),(.45,.65)), ((.43,.46),(.61,.44),(.59,.65)), ((.45,.64),(.59,.62)),
    ),
    "加": (
        ((.19,.42),(.47,.40),(.45,.68),(.42,.76),(.35,.70)),
        ((.34,.24),(.31,.48),(.26,.64),(.16,.77)),
        ((.57,.44),(.59,.73)), ((.57,.44),(.81,.42),(.77,.72)), ((.59,.72),(.77,.69)),
    ),
}
WRITING = {
    "write-this-look-card": ("这看", (6, 3), (4, 4)),
    "write-fish-surface-card": ("鱼面", (7, 1), (7, 2)),
    "write-ask-add-card": ("问加", (3, 2), (3, 2)),
}
PAIRS = {
    "low-flight-board": ("bird-low", "insects-low"),
    "voice-practice-board": ("kids-question", "kids-remind"),
}
GRIDS = {
    "fish-water-board": ("fish-deep", "fish-surface", "water-surface", "stuffy", "busy", "free-time"),
    "message-board": ("rabbit-tells-ant", "ants-pack", "news", "rush"),
}
RAIN_SEQUENCE = ("bird-icon", "fish-icon", "ant-icon", "rain-icon", "rabbit-runs", "rain-window")
PREVIEWS = {
    "weather-game-start": (("overcast", "bright", "wet-leaf"), "weather-boat", "game-bubble"),
    "maze-game-start": (("bird-icon", "fish-icon", "ant-icon", "rain-icon"), "maze-rover", "game-bubble"),
}
WORD_PAIRS = ("bright", "overcast", "dry-leaf", "wet-leaf", "stand", "bend")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def strip_matte(image):
    """Remove only mint paper connected to a corner or edge."""
    rgba = image.convert("RGBA")
    width, height = image.size
    corners = [rgba.getpixel((x, y))[:3] for x, y in ((5, 5), (width - 6, 5), (5, height - 6), (width - 6, height - 6))]
    bg = [median(channel) for channel in zip(*corners)]
    mask = Image.new("L", image.size)
    mask.putdata([255 if max(abs(value - paper) for value, paper in zip(pixel, bg)) > 23 else 0
                  for pixel in image.convert("RGB").getdata()])
    for x, y in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        ImageDraw.floodfill(mask, (x, y), 128)
    mask = mask.point(lambda px: 0 if px == 128 else 255)
    rgba.putalpha(mask.filter(ImageFilter.GaussianBlur(.4)))
    box = mask.getbbox()
    if box is None or box[0] == 0 or box[1] == 0 or box[2] == width or box[3] == height:
        raise ValueError("sprite matte touches the crop boundary")
    return rgba.crop(box)


def board(size):
    return Image.new("RGBA", size, CREAM)


def paste(canvas, image, center, size):
    item = image.copy()
    item.thumbnail(size, Image.Resampling.LANCZOS)
    x, y = center
    canvas.alpha_composite(item, (round(x - item.width / 2), round(y - item.height / 2)))


def arrow(draw, x, y):
    draw.line((x - 12, y, x + 11, y), width=5, fill=ORANGE)
    draw.polygon(((x + 15, y), (x + 6, y - 7), (x + 6, y + 7)), fill=ORANGE)


def paired(left, right, sequence):
    canvas = board((742, 373))
    paste(canvas, left, (176, 186), (340, 350))
    paste(canvas, right, (566, 186), (340, 350))
    if sequence:
        arrow(ImageDraw.Draw(canvas), 371, 186)
    return canvas


def picture_grid(images, keys):
    rows = len(keys) // 2
    canvas = board((450, rows * 215 + 10))
    for index, name in enumerate(keys):
        row, column = divmod(index, 2)
        paste(canvas, images[name], (113 + 224 * column, 113 + 215 * row), (198, 198))
    return canvas


def rain_sequence(images):
    canvas = board((620, 390))
    draw = ImageDraw.Draw(canvas)
    for index, name in enumerate(RAIN_SEQUENCE[:4]):
        paste(canvas, images[name], (78 + 155 * index, 69), (119, 96))
        if index < 3:
            arrow(draw, 155 + 155 * index, 69)
    paste(canvas, images["rabbit-runs"], (157, 249), (248, 251))
    paste(canvas, images["rain-window"], (462, 249), (248, 251))
    arrow(draw, 309, 247)
    return canvas


def game_preview(images, cards, vehicle, bubble):
    canvas = board((583, 304))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((14, 13, 569, 291), radius=26, fill="#dcebd6")
    step = 128 if len(cards) == 4 else 145
    for index, name in enumerate(cards):
        x = 291 + round((index - (len(cards) - 1) / 2) * step)
        paste(canvas, images[name], (x, 102), (110, 108))
    paste(canvas, images[vehicle], (281, 220), (163, 115))
    paste(canvas, images[bubble], (400, 217), (43, 43))
    return canvas


def field(draw, x, y, size):
    draw.rounded_rectangle((x, y, x + size, y + size), radius=10, outline=SAGE, width=3)
    draw.line((x + size // 2, y + 3, x + size // 2, y + size - 3), fill="#cbd5bc", width=2)
    draw.line((x + 3, y + size // 2, x + size - 3, y + size // 2), fill="#cbd5bc", width=2)


def strokes(draw, paths, x, y, size, highlight=()):
    width = max(4, round(size * .044))
    for index, points in enumerate(paths):
        color = ORANGE if index in highlight else PINE
        pixels = [(round(x + px * size), round(y + py * size)) for px, py in points]
        draw.line(pixels, fill=color, width=width, joint="curve")
        radius = width // 2
        for ax, ay in (pixels[0], pixels[-1]):
            draw.ellipse((ax - radius, ay - radius, ax + radius, ay + radius), fill=color)


def writing(chars, highlight, splits):
    canvas = board((694, 398))
    draw = ImageDraw.Draw(canvas)
    for index, (char, key_stroke, split) in enumerate(zip(chars, highlight, splits)):
        left = 13 + 347 * index
        field(draw, left + 46, 10, 227)
        strokes(draw, STROKES[char], left + 46, 10, 227, (key_stroke,))
        for stage, size in enumerate((123, 123)):
            x = left + 22 + stage * 149
            field(draw, x, 259, size)
            paths = STROKES[char][:split] if stage == 0 else STROKES[char]
            marks = () if stage == 0 else range(split, len(paths))
            strokes(draw, paths, x, 259, size, marks)
        arrow(draw, left + 157, 320)
    return canvas


def question_mouth(placement):
    canvas = board((384, 337))
    draw = ImageDraw.Draw(canvas)
    x, y, size = 28, 13, 305
    field(draw, x, y, size)
    shift = {"left": -.153, "outside": .395, "center": 0}[placement]
    frame = STROKES["问"][:3]
    mouth = tuple(tuple((px + shift, py) for px, py in path) for path in STROKES["问"][3:])
    strokes(draw, frame + mouth, x, y, size, range(3, 6))
    return canvas


def generate(root=ROOT):
    art_dir, assets_dir = root / "art-source", root / "assets"
    lesson = json.loads((root / "lesson.json").read_text())
    page_text = {
        scene["key"]: (root / "pages" / f"{scene['page']}.js").read_text()
        for scene in lesson["scenes"] if scene["type"] == "interactive"
    }
    images, provenance = {}, {}
    for atlas, (x_values, y_values, names) in ATLAS_CELLS.items():
        path = art_dir / f"{atlas}.png"
        prompt_path = art_dir / f"{atlas}.prompt.txt"
        prompt, prompt_hash = prompt_path.read_text(), digest(prompt_path)
        source_hash = digest(path)
        with Image.open(path) as sheet:
            assert sheet.size == (x_values[-1], y_values[-1])
            for index, name in enumerate(names):
                row, column = divmod(index, len(x_values) - 1)
                box = (x_values[column] + 4, y_values[row] + 4, x_values[column + 1] - 4, y_values[row + 1] - 4)
                cut = sheet.crop(box).convert("RGBA")
                if atlas == "game-atlas" and index < 10:
                    cut = strip_matte(cut)
                if atlas in ("game-atlas", "word-atlas") and "backdrop" not in name:
                    cut.thumbnail((228, 228), Image.Resampling.LANCZOS)
                images[name] = cut
                provenance[name] = {
                    "source": ATLAS_SOURCE, "generatedSource": f"art-source/{atlas}.png",
                    "generatedSourceSha256": source_hash, "prompt": prompt, "promptSha256": prompt_hash,
                    "sourceCrop": box, "postprocess": "paper matte removed" if atlas == "game-atlas" and index < 10 else "opaque crop",
                }
    relationships = {}
    for name, pair in PAIRS.items():
        images[name] = paired(*(images[key] for key in pair), sequence=False)
        relationships[name] = pair
    for name, (cards, vehicle, bubble) in PREVIEWS.items():
        images[name] = game_preview(images, cards, vehicle, bubble)
        relationships[name] = (*cards, vehicle, bubble)
    for name, components in {**GRIDS, "word-practice-board": WORD_PAIRS}.items():
        images[name] = picture_grid(images, components)
        relationships[name] = components
    images["rain-result-board"] = rain_sequence(images)
    relationships["rain-result-board"] = RAIN_SEQUENCE
    images["rain-sticker"] = images["umbrella-sticker"].copy()
    relationships["rain-sticker"] = ("umbrella-sticker",)
    for name, arguments in WRITING.items():
        images[name] = writing(*arguments)
        relationships[name] = ()
    for letter, placement in zip("abc", ("left", "outside", "center")):
        name = f"quiz-6-{letter}"
        images[name] = question_mouth(placement)
        relationships[name] = ()

    uses = {name: set() for name in images}
    for scene in lesson["scenes"]:
        key = scene["key"]
        if scene["type"] == "slide":
            uses[scene["data"]["picture"]].add(key)
        elif scene["type"] == "interactive":
            uses[scene["startImage"]].add(key)
            for name in images:
                if f"__IMG:{name}__" in page_text[key]:
                    uses[name].add(key)
        elif scene["type"] == "quiz":
            for question in scene["questions"]:
                for option in question["options"].values():
                    uses[option["visual"]["image"]].add(question["id"])
    for name, children in relationships.items():
        for child in children:
            uses[child].update(uses[name])
        provenance[name] = {"source": "course-specific semantic diagram" if not children else "composition of registered ImageGen panels",
                            "drawingSource": "diagrams.py", "components": children}

    assert lesson["images"].keys() <= images.keys()
    assert all(uses.values())
    rows = []
    for name, image in images.items():
        dest = assets_dir / f"{name}.png"
        image.save(dest, format="PNG", optimize=True)
        rows.append({"assetKey": name, "path": str(dest.relative_to(root)), "sha256": digest(dest),
                     "width": image.width, "height": image.height, "usedBy": sorted(uses[name]), **provenance[name]})
    manifest = {"schemaVersion": "mira.courseware.asset-sources.v1", "assets": rows}
    (root / "asset-sources.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    generate()
