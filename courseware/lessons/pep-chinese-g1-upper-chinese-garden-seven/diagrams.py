"""Render exact relationships, directions and stroke differences for this lesson."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
PINE, CREAM, ORANGE, SAGE = "#253e35", "#fff2d6", "#cb5d28", "#8fa98b"

STROKES = {
    "爸": (
        ((41,10),(35,17),(26,22)), ((59,11),(70,21)),
        ((53,22),(41,32),(19,39)), ((51,26),(65,35),(85,40)),
        ((32,50),(70,47),(68,69)), ((50,49),(49,69)), ((32,70),(68,69)),
        ((32,50),(31,77),(35,87),(48,91),(73,90),(79,87),(81,79)),
    ),
    "妈": (
        ((28,14),(23,39),(16,56),(31,65),(42,74)),
        ((39,35),(34,57),(24,75),(14,84)), ((12,47),(43,37)),
        ((53,27),(78,24),(76,47)),
        ((55,34),(51,58),(85,56),(82,77),(77,87),(71,82)),
        ((51,73),(76,70)),
    ),
}

COMPARE = {
    "了": ((51,18),(54,40),(59,58),(58,76),(53,87),(44,81)),
    "才": ((53,14),(53,76),(50,87),(43,80)),
    "云": ((58,22),(49,41),(35,65),(66,52)),
    "山": ((36,22),(36,72),(71,67)),
    "儿": ((34,17),(34,51),(36,66),(46,76),(62,78),(75,76),(77,65)),
    "四": ((34,17),(34,51),(36,66),(46,76),(62,78),(76,78)),
    "我": ((39,15),(42,37),(49,56),(59,71),(71,83),(78,85),(81,73)),
    "心": ((28,42),(33,62),(45,75),(58,78),(70,75),(79,67),(74,59)),
}


def image(root, name):
    with Image.open(root / "art-source" / (name + ".png")) as value:
        return value.convert("RGBA")


def place(canvas, raw, at, size, rotation=0):
    sprite = raw.copy()
    sprite.thumbnail(size, Image.Resampling.LANCZOS)
    if rotation:
        sprite = sprite.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
    canvas.alpha_composite(sprite, (round(at[0] - sprite.width / 2), round(at[1] - sprite.height / 2)))


def board(size):
    return Image.new("RGBA", size, CREAM)


def text_center(draw, xy, value, size):
    draw.text(xy, value, font=ImageFont.truetype(FONT, size), fill=PINE, anchor="mm")


def path(draw, stroke, x, y, span, color):
    coords = [(round(x + px * span / 100), round(y + py * span / 100)) for px, py in stroke]
    width = max(3, span // 17)
    draw.line(coords, fill=color, width=width, joint="curve")
    radius = width // 2
    for a, b in (coords[0], coords[-1]):
        draw.ellipse((a - radius,b - radius,a + radius,b + radius), fill=color)


def grid(draw, x, y, size):
    draw.rounded_rectangle((x, y, x + size, y + size), radius=size // 18, outline=SAGE, width=2)
    draw.line((x + size / 2, y + 4, x + size / 2, y + size - 4), fill="#cad0ac", width=1)
    draw.line((x + 4, y + size / 2, x + size - 4, y + size / 2), fill="#cad0ac", width=1)


def writing():
    canvas = board((740, 464))
    draw = ImageDraw.Draw(canvas)
    for row, (glyph, strokes) in enumerate(STROKES.items()):
        top = 13 + row * 227
        grid(draw, 15, top, 205)
        for stroke in strokes:
            path(draw, stroke, 15, top, 205, PINE)
        for i, _ in enumerate(strokes):
            x, y = 244 + (i % 4) * 122, top + (i // 4) * 107
            grid(draw, x, y, 100)
            for j, stroke in enumerate(strokes[:i+1]):
                path(draw, stroke, x, y, 100, ORANGE if i == j else PINE)
    return canvas


def comparison(glyphs):
    canvas = board((660, 488))
    draw = ImageDraw.Draw(canvas)
    for i, glyph in enumerate(glyphs):
        x, y = 18 + (i % 2) * 325, 18 + (i // 2) * 236
        text_center(draw, (x + 55, y + 106), glyph, 94)
        grid(draw, x + 115, y + 20, 175)
        path(draw, COMPARE[glyph], x + 115, y + 20, 175, ORANGE)
    return canvas


def relationships(people, parent, generations):
    canvas = board((440, 250))
    draw = ImageDraw.Draw(canvas)
    centers = [(76, 126), (220, 126), (363, 126)]
    sequence = [people["child"], people[parent], people["granny"]][:generations+1]
    for (x, y), portrait in zip(centers, sequence):
        draw.ellipse((x-55, y-55, x+55, y+55), fill="#eed6a1", outline=SAGE, width=4)
        place(canvas, portrait, (x,y), (101,101))
    for (x, y) in centers[:generations]:
        draw.line((x+57,y,x+85,y), fill=ORANGE, width=7)
        draw.polygon([(x+87,y),(x+74,y-8),(x+74,y+8)],fill=ORANGE)
    return canvas


def radical_choice(index):
    canvas = board((420, 290))
    draw = ImageDraw.Draw(canvas)
    text_center(draw, (210,145), "奶", 186)
    outlines = ((220,56,317,238),(104,56,204,238),(99,49,321,245))
    draw.rounded_rectangle(outlines[index], radius=24, outline=ORANGE, width=8)
    return canvas


def stroke_choice(stroke):
    canvas = board((420, 280))
    draw = ImageDraw.Draw(canvas)
    grid(draw, 94, 19, 232)
    path(draw, stroke, 94, 19, 232, ORANGE)
    return canvas


def direction(actor, star, selected=None):
    canvas = board((440, 334))
    draw = ImageDraw.Draw(canvas)
    center = (220,167)
    positions = {"east":(353,167), "west":(87,167), "north":(220,66), "south":(220,268)}
    for name, (x,y) in positions.items():
        draw.line([center,(x,y)], fill="#b1bd8d", width=4)
        draw.ellipse((x-30,y-30,x+30,y+30), fill="#f0db9f", outline=SAGE, width=3)
        if selected == name:
            place(canvas, star, (x,y), (51,51))
    if selected is None:
        for name, glyph in zip(("east","west","north","south"), "东西北南"):
            text_center(draw, positions[name], glyph, 39)
    else:
        text_center(draw, (412,168), "东", 31)
    place(canvas, actor, center, (103,103), -90)
    return canvas


def mosaic(images, *, columns, tile):
    rows = (len(images) + columns - 1) // columns
    width, height = tile
    canvas = board((columns * (width+8) + 8, rows * (height+8) + 8))
    for index, frame in enumerate(images):
        x = 8 + index % columns * (width+8) + width/2
        y = 8 + index // columns * (height+8) + height/2
        place(canvas, frame, (x,y), tile)
    return canvas


def sound(frame, origin, reach):
    canvas = frame.copy()
    draw = ImageDraw.Draw(canvas)
    w, h = canvas.size
    x, y = (origin[0]*w, origin[1]*h)
    for amount in (0.42, 0.7, 1):
        radius = reach * w * amount
        height = min(h * 0.42, radius * 0.6)
        rect = (x-radius,y-height,x+radius,y+height)
        draw.arc(rect,-29,29,fill="#fff7d4",width=9)
        draw.arc(rect,-29,29,fill=ORANGE,width=5)
    return canvas


def moon_choice(frame, bounds):
    canvas = frame.copy()
    w,h = canvas.size
    x1,y1,x2,y2 = bounds
    box = (x1*w,y1*h,x2*w,y2*h)
    draw = ImageDraw.Draw(canvas)
    draw.ellipse(box, outline="#fff4cd", width=9)
    draw.ellipse(box, outline=ORANGE, width=5)
    return canvas


def render(root=ROOT):
    assets = root / "assets"

    def save(name, content):
        content.save(assets / (name + ".png"), optimize=True)

    people = {name:image(root,name) for name in ("child","mother","father","granny")}
    for suffix,(parent,count) in zip("abc",(("mother",2),("father",2),("mother",1))):
        save("family-choice-"+suffix, relationships(people,parent,count))
    for index, suffix in enumerate("abc"):
        save("radical-choice-"+suffix, radical_choice(index))
    for suffix, form in zip("abc",("山","四","儿")):
        save("stroke-choice-"+suffix, stroke_choice(COMPARE[form]))

    with Image.open(assets/"compass-person.png") as source:
        actor = source.convert("RGBA")
    with Image.open(assets/"star-pin.png") as source:
        star = source.convert("RGBA")
    save("direction-east", direction(actor,star))
    for suffix, side in zip("abc",("east","south","north")):
        save("direction-choice-"+suffix, direction(actor,star,side))

    save("write-family",writing())
    save("strokes-first",comparison("了才云山"))
    save("strokes-second",comparison("儿四我心"))
    save("proverb-strip",mosaic([image(root,name) for name in ("beans","shade","first-step","improve")],
                              columns=2,tile=(330,185)))
    save("monkey-strip",mosaic([image(root,name) for name in ("monkey-sees","monkey-tries","monkey-checks")],
                              columns=1,tile=(430,156)))

    near = sound(image(root,"quiet"),(.23,.58),.23)
    far = sound(image(root,"hall"),(.22,.48),.74)
    save("volume-teach",mosaic([near,far],columns=1,tile=(500,208)))
    for suffix, reach in zip("abc",(.27,.52,.78)):
        save("far-choice-"+suffix, sound(image(root,"rehearsal"),(.18,.48),reach))
    for suffix, reach in zip("abc",(.18,.75,.06)):
        save("near-choice-"+suffix, sound(image(root,"exhibit"),(.17,.48),reach))
    for suffix, bounds in zip("abc",((.21,.73,.83,.96),(.01,.02,.39,.29),(.74,.03,.94,.30))):
        save("moon-choice-"+suffix, moon_choice(image(root,"moon-details"),bounds))


if __name__ == "__main__":
    render()
