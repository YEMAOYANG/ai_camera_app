"""Build the summer lesson's cropped art and exact glyph, stroke and star diagrams."""
from hashlib import sha256
import json
from math import cos, sin
from pathlib import Path
from statistics import median

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parent
CREAM, PINE, SAGE, ORANGE = "#fff1d7", "#24453c", "#a6b8a0", "#bd572c"
FONT = "/System/Library/Fonts/Supplemental/Songti.ttc"
ATLAS = {
    "summer-atlas": ((0, 420, 833, 1254), (0, 419, 819, 1254), 12,
        ("ice-pop", "watermelon", "mung-soup", "bamboo-mat", "mosquito-coil",
         "floral-water", "palm-fan", "bamboo-chair", "firefly")),
    "weather-atlas": ((0, 420, 833, 1254), (0, 418, 834, 1254), 12,
        ("dawn-glow", "dusk-glow", "cloud-cap", "cloud-waist", "morning-rain",
         "day-clears", "night-rain", "ant-snake", "rain-umbrella")),
    "everyday-atlas": ((0, 418, 831, 1247), (0, 419, 831, 1261), 10,
        ("family-sky", None, "bounce-ball", "surprise", "ask-a-friend", "finish-watering",
         "cracker-packet", "milk-carton", "bread-wrap")),
    "story-atlas": ((0, 314, 628, 941, 1254), (0, 315, 628, 940, 1254), 7,
        ("ant-grass", "lily-lowers", "ant-on-leaf", "dragonfly-carries", "firefly-guides",
         "rockery", "lawn", "flowerbed", "garden-rover", "garden-rover-pop", "summer-boat",
         "summer-boat-pop", "firefly-sticker", "game-bubble", "story-backdrop", "summer-backdrop")),
    "quiz-atlas": ((0, 323, 647, 971), (0, 324, 646, 947, 1270, 1619), 4,
        tuple(f"quiz-{n}-{x}" for n in (1, 3, 5, 6, 7) for x in "abc")),
}

# GF 0023—2020 print pp. 10 and 39, checked against the exact lesson's notes.
STROKES = {
    "豆": (
        ((.35,.23),(.66,.21)), ((.34,.37),(.38,.53)),
        ((.34,.37),(.70,.35),(.66,.53)), ((.38,.52),(.66,.51)),
        ((.41,.60),(.46,.69)), ((.61,.58),(.56,.72)), ((.23,.78),(.80,.76)),
    ),
    "斗": (
        ((.37,.22),(.45,.30)), ((.34,.36),(.42,.44)),
        ((.23,.54),(.75,.50)), ((.55,.18),(.55,.84)),
    ),
}
DIPPER = ((.15,.24),(.31,.30),(.38,.41),(.49,.54),(.78,.67),(.69,.80),(.46,.70))
PACK_LABELS = {
    "cracker-packet": ("饼干", .49, .42),
    "milk-carton": ("牛奶", .40, .56),
    "bread-wrap": ("面包", .51, .52),
    "quiz-7-a": ("梨汁", .53, .46),
    "quiz-7-b": ("牛奶", .50, .55),
    "quiz-7-c": ("蛋卷", .50, .45),
}
STORY_TOKENS = ("ant-grass", "lily-lowers", "dragonfly-carries", "firefly-guides",
                "rockery", "lawn", "flowerbed")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def matte_free(image):
    """Clear only background mint paper reachable from the corners."""
    rgba = image.convert("RGBA")
    width, height = image.size
    points = ((5, 5), (width - 6, 5), (5, height - 6), (width - 6, height - 6))
    paper = [median(channel) for channel in zip(*(rgba.getpixel(point)[:3] for point in points))]
    mask = Image.new("L", image.size)
    mask.putdata([255 if max(abs(value - bg) for value, bg in zip(rgb, paper)) > 24 else 0
                  for rgb in image.convert("RGB").getdata()])
    for corner in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        ImageDraw.floodfill(mask, corner, 128)
    mask = mask.point(lambda pixel: 0 if pixel == 128 else 255)
    bounds = mask.getbbox()
    if not bounds or 0 in bounds[:2] or bounds[2] == width or bounds[3] == height:
        raise ValueError("sprite cut touches its original crop edge")
    rgba.putalpha(mask.filter(ImageFilter.GaussianBlur(.45)))
    return rgba.crop(bounds)


def board(size):
    return Image.new("RGBA", size, CREAM)


def paste(canvas, image, center, size):
    item = image.copy()
    item.thumbnail(size, Image.Resampling.LANCZOS)
    x, y = center
    canvas.alpha_composite(item, (round(x - item.width / 2), round(y - item.height / 2)))


def arrow(draw, x, y):
    draw.line((x - 11, y, x + 10, y), width=5, fill=ORANGE)
    draw.polygon(((x + 14, y), (x + 6, y - 7), (x + 6, y + 7)), fill=ORANGE)


def grid(items, columns, *, tile=188):
    rows = (len(items) + columns - 1) // columns
    canvas = board((columns * tile + 12, rows * tile + 12))
    for index, image in enumerate(items):
        row, column = divmod(index, columns)
        paste(canvas, image, (6 + column * tile + tile / 2, 6 + row * tile + tile / 2),
              (tile - 14, tile - 14))
    return canvas


def route(images):
    canvas = board((744, 354))
    draw = ImageDraw.Draw(canvas)
    rows = (STORY_TOKENS[:4], STORY_TOKENS[4:])
    for i, row in enumerate(rows):
        step = 184 if i == 0 else 228
        for j, name in enumerate(row):
            x, y = 372 + round((j - (len(row) - 1) / 2) * step), 85 + 177 * i
            paste(canvas, images[name], (x, y), (151, 151))
            if j < len(row) - 1:
                arrow(draw, x + step / 2, y)
    return canvas


def preview(items, vehicle, bubble):
    canvas = board((570, 284))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((12, 12, 558, 272), radius=25, fill="#dde9ce")
    for i, sprite in enumerate(items):
        paste(canvas, sprite, (285 + round((i - (len(items) - 1) / 2) * 117), 93), (96, 96))
    paste(canvas, vehicle, (274, 211), (150, 102))
    paste(canvas, bubble, (400, 199), (42, 42))
    return canvas


def star_card(points, edges, *, angle=0):
    canvas = Image.new("RGBA", (360, 360), "#21364d")
    draw = ImageDraw.Draw(canvas)
    locations = [(round(180 + ((x-.5)*cos(angle)-(y-.5)*sin(angle))*330),
                  round(180 + ((x-.5)*sin(angle)+(y-.5)*cos(angle))*330)) for x, y in points]
    for start, end in edges:
        draw.line((locations[start], locations[end]), fill="#c4d5ce", width=6)
    for x, y in locations:
        draw.ellipse((x-10, y-10, x+10, y+10), fill="#ffebad", outline="#fff1d7", width=2)
    return canvas


def dipper(angle=0):
    return star_card(DIPPER, ((0,1),(1,2),(2,3),(3,4),(4,5),(5,6),(6,3)), angle=angle)


def field(draw, x, y, size):
    draw.rounded_rectangle((x, y, x + size, y + size), radius=8, outline=SAGE, width=3)
    draw.line((x + size // 2, y + 3, x + size // 2, y + size - 3), fill="#cad5bf", width=2)
    draw.line((x + 3, y + size // 2, x + size - 3, y + size // 2), fill="#cad5bf", width=2)


def stroke_paths(draw, paths, x, y, size, highlight):
    width = max(4, round(size * .046))
    for index, path in enumerate(paths):
        pixels = [(round(x + px * size), round(y + py * size)) for px, py in path]
        color = ORANGE if index == highlight else PINE
        draw.line(pixels, fill=color, width=width, joint="curve")
        r = width // 2
        for ax, ay in (pixels[0], pixels[-1]):
            draw.ellipse((ax-r, ay-r, ax+r, ay+r), fill=color)


def handwriting():
    canvas = board((734, 450))
    draw = ImageDraw.Draw(canvas)
    for row, (character, paths) in enumerate(STROKES.items()):
        top = 9 + 224 * row
        field(draw, 13, top, 202)
        stroke_paths(draw, paths, 13, top, 202, len(paths) - 1)
        for i in range(len(paths)):
            line, column = divmod(i, 4)
            x, y = 240 + 119 * column, top + line * 107 + (47 if row else 0)
            field(draw, x, y, 100)
            stroke_paths(draw, paths[:i+1], x, y, 100, i)
    return canvas


def glyph(draw, text, position, size, fill=PINE):
    draw.text(position, text, font=ImageFont.truetype(FONT, size), anchor="mm", fill=fill)


def mark(draw, symbol, center, size):
    x, y = center
    r = size * .105
    if symbol == "。":
        draw.ellipse((x-r, y-r, x+r, y+r), outline=ORANGE, width=max(4, int(size*.055)))
    elif symbol == "，":
        draw.ellipse((x-r, y-r, x+r, y+r), fill=ORANGE)
        draw.line((x+r*.58, y+r*.68, x-r*.72, y+r*1.74), fill=ORANGE, width=max(4, round(r*.9)))
    else:
        glyph(draw, symbol, center, round(size * .88), ORANGE)


def copy_board():
    canvas = board((707, 355))
    draw = ImageDraw.Draw(canvas)
    for i, char in enumerate("花开了，我笑了。"):
        row, col = divmod(i, 4)
        x, y, size = 30 + col * 165, 13 + row * 173, 156
        field(draw, x, y, size)
        if char in "，。":
            mark(draw, char, (x+31, y+123), 94)
        else:
            glyph(draw, char, (x+78, y+79), 104)
    return canvas


def punctuation_card(symbol):
    canvas = board((330, 292))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((24, 21, 306, 271), radius=34, fill="#f7e6bf", outline=SAGE, width=4)
    mark(draw, symbol, (164, 146), 200)
    return canvas


def text_on_pack(image, text, x, y):
    image = image.copy()
    draw = ImageDraw.Draw(image)
    glyph(draw, text, (round(x*image.width), round(y*image.height)), round(image.width*.17), "#303a2f")
    return image


def generate(root=ROOT):
    asset_dir, art_dir = root/"assets", root/"art-source"
    lesson = json.loads((root/"lesson.json").read_text())
    images, metadata, components = {}, {}, {}
    for atlas, (x_edges, y_edges, inset, names) in ATLAS.items():
        sheet_path = art_dir/f"{atlas}.png"
        prompt_path = art_dir/f"{atlas}.prompt.txt"
        sheet_hash, prompt_hash, prompt = digest(sheet_path), digest(prompt_path), prompt_path.read_text()
        with Image.open(sheet_path) as sheet:
            assert sheet.size == (x_edges[-1], y_edges[-1])
            for index, name in enumerate(names):
                if name is None:
                    continue
                row, column = divmod(index, len(x_edges)-1)
                crop = (x_edges[column]+inset, y_edges[row]+inset,
                        x_edges[column+1]-inset, y_edges[row+1]-inset)
                image = sheet.crop(crop).convert("RGBA")
                sprite = atlas == "story-atlas" and 8 <= index < 14
                if sprite:
                    image = matte_free(image)
                if name in PACK_LABELS:
                    image = text_on_pack(image, *PACK_LABELS[name])
                if sprite or atlas == "summer-atlas":
                    image.thumbnail((260, 260), Image.Resampling.LANCZOS)
                images[name] = image
                metadata[name] = {"source":"Codex built-in image_gen","generatedSource":f"art-source/{atlas}.png",
                                  "generatedSourceSha256":sheet_hash,"prompt":prompt,"promptSha256":prompt_hash,
                                  "sourceCrop":crop}
                if sprite or name in PACK_LABELS:
                    metadata[name].update(drawingSource="diagrams.py",
                        postprocess="mint matte cleared" if sprite else "registered educational label applied")

    def derived(name, image, *sources):
        images[name] = image
        components[name] = sources
        metadata[name] = {"source":"composition of registered ImageGen panels" if sources else "course-specific semantic diagram",
                          "drawingSource":"diagrams.py","components":sources}

    grids = {
        "summer-food-board": (3, ("ice-pop", "watermelon", "mung-soup")),
        "summer-porch-board": (3, ("bamboo-mat", "mosquito-coil", "floral-water")),
        "summer-yard-board": (3, ("palm-fan", "bamboo-chair", "firefly")),
        "food-package-board": (3, ("cracker-packet", "milk-carton", "bread-wrap")),
        "sky-sayings-board": (2, ("dawn-glow", "dusk-glow", "cloud-cap", "cloud-waist")),
        "rain-sayings-board": (3, ("morning-rain", "day-clears", "night-rain", "ant-snake", "rain-umbrella")),
        "ant-pond-board": (3, ("ant-grass", "lily-lowers", "ant-on-leaf")),
        "ant-journey-board": (3, ("dragonfly-carries", "firefly-guides", "rockery", "lawn", "flowerbed")),
    }
    for name, (columns, names) in grids.items():
        derived(name, grid([images[key] for key in names], columns), *names)

    derived("sky-names-board", grid([images["family-sky"], dipper()], 2, tile=285), "family-sky")
    ball = images["bounce-ball"]
    w, h = ball.size
    detail = ball.crop((round(.22*w), round(.12*h), round(.85*w), h))
    derived("expand-a-sentence-board", grid([detail, ball], 2, tile=290), "bounce-ball")
    practice = ("ask-a-friend", "surprise", "finish-watering")
    practice_cards = []
    for picture, symbol in zip(practice, ("？", "！", "。")):
        tile = grid([images[picture]], 1, tile=235)
        draw = ImageDraw.Draw(tile)
        draw.rounded_rectangle((156, 160, 232, 234), radius=13, fill=CREAM, outline=SAGE, width=3)
        mark(draw, symbol, (195, 196), 69)
        practice_cards.append(tile)
    derived("punctuation-board", grid([*practice_cards, punctuation_card("，")], 2), *practice)
    derived("bean-dipper-writing", handwriting())
    derived("copy-a-sentence-board", copy_board())
    derived("garden-route-board", route(images), *STORY_TOKENS)
    for name, source, crop in (
            ("maze-grass-icon", "ant-grass", (.18, .13, .80, .97)),
            ("maze-dragonfly-icon", "dragonfly-carries", (.04, .07, .94, .79)),
            ("maze-firefly-icon", "firefly-guides", (.49, .06, .98, .62))):
        image = images[source]
        width, height = image.size
        box = tuple(round(value * (width if i % 2 == 0 else height)) for i, value in enumerate(crop))
        derived(name, image.crop(box), source)
    for name, keys, vehicle in (
            ("summer-game-start", ("ice-pop", "watermelon", "mung-soup"), "summer-boat"),
            ("ant-game-start", STORY_TOKENS[:4], "garden-rover")):
        derived(name, preview([images[k] for k in keys], images[vehicle], images["game-bubble"]),
                *keys, vehicle, "game-bubble")

    derived("quiz-2-a", dipper(-.34))
    triangle = ((.49,.22),(.76,.68),(.22,.68),(.24,.35),(.64,.85),(.80,.30),(.38,.79))
    derived("quiz-2-b", star_card(triangle, ((0,1),(1,2),(2,0))))
    curve = ((.17,.51),(.28,.39),(.39,.39),(.50,.50),(.61,.61),(.72,.61),(.83,.49))
    derived("quiz-2-c", star_card(curve, tuple((i,i+1) for i in range(6))))
    for key, symbol in zip(("quiz-4-a", "quiz-4-b", "quiz-4-c"), ("。", "！", "？")):
        derived(key, punctuation_card(symbol))

    uses = {name:set() for name in images}
    for scene in lesson["scenes"]:
        key = scene["key"]
        if scene["type"] == "slide":
            uses[scene["data"]["picture"]].add(key)
        elif scene["type"] == "interactive":
            uses[scene["startImage"]].add(key)
            text = (root/"pages"/f"{scene['page']}.js").read_text()
            for name in images:
                if f"__IMG:{name}__" in text:
                    uses[name].add(key)
        else:
            for question in scene["questions"]:
                for option in question["options"].values():
                    uses[option["visual"]["image"]].add(question["id"])
    for name, inputs in components.items():
        for key in inputs:
            uses[key].update(uses[name])

    assert lesson["images"].keys() <= images.keys() and all(uses.values())
    rows = []
    for name, image in images.items():
        dest = asset_dir/f"{name}.png"
        image.save(dest, format="PNG", optimize=True)
        rows.append({"assetKey":name,"path":str(dest.relative_to(root)),"sha256":digest(dest),
                     "width":image.width,"height":image.height,"usedBy":sorted(uses[name]),**metadata[name]})
    (root/"asset-sources.json").write_text(json.dumps(
        {"schemaVersion":"mira.courseware.asset-sources.v1","assets":rows},ensure_ascii=False,indent=2)+"\n")


if __name__ == "__main__":
    generate()
