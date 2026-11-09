"""Render the lesson's original teaching diagrams and picture compositions."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets'
ORIGINALS = ROOT / 'art' / 'originals'
INK, RED, GOLD, PAPER = '#203c37', '#c24531', '#bc7a26', '#fffbeb'
LINE = '#9baf98'
KAI = Path('/System/Library/AssetsV2/com_apple_MobileAsset_Font8/88d6cc32a907955efa1d014207889413890573be.asset/AssetData/Kaiti.ttc')
SANS = Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')

# Curves run in pen direction on a 100 by 100 grid.
STROKES = {
    '了': (
        ((30, 23), (48, 21), (67, 19), (73, 22), (68, 31), (59, 36), (50, 43)),
        ((49, 40), (61, 54), (58, 72), (55, 82), (52, 89), (46, 82), (42, 78)),
    ),
    '子': (
        ((30, 21), (49, 19), (65, 17), (73, 20), (69, 30), (57, 36), (50, 43)),
        ((49, 40), (61, 51), (59, 73), (56, 83), (53, 89), (47, 83), (43, 78)),
        ((15, 53), (35, 51), (67, 50), (85, 50)),
    ),
    '大': (
        ((17, 49), (34, 48), (65, 46), (83, 46)),
        ((51, 18), (52, 47), (46, 69), (18, 83)),
        ((54, 53), (60, 65), (71, 76), (84, 82)),
    ),
    '人': (
        ((50, 18), (49, 47), (36, 72), (16, 83)),
        ((48, 40), (58, 55), (66, 75), (85, 83)),
    ),
}


def canvas(size=(840, 400), color=PAPER):
    return Image.new('RGBA', size, color)


def font(size, kai=False):
    return ImageFont.truetype(str(KAI if kai else SANS), size)


def draw_text(draw, xy, text, size, color=INK, kai=False):
    draw.text(xy, text, font=font(size, kai), fill=color, anchor='mm')


def save(key, art):
    art.save(ASSETS / f'{key}.png', optimize=True)


def fit(image, dimensions):
    scaled = image.copy()
    scaled.thumbnail(dimensions, Image.Resampling.LANCZOS)
    return scaled


def stamp(background, item, center, size, rotation=0):
    item = fit(item, size)
    if rotation:
        item = item.rotate(rotation, Image.Resampling.BICUBIC, expand=True)
    background.alpha_composite(item, (center[0] - item.width // 2, center[1] - item.height // 2))


def grid(draw, x, y, side):
    draw.rounded_rectangle((x, y, x + side, y + side), radius=6, fill='#fffef7', outline=LINE, width=3)
    for offset in range(0, side, 14):
        draw.line((x + side // 2, y + offset, x + side // 2, y + min(side, offset + 7)), fill=LINE, width=2)
        draw.line((x + offset, y + side // 2, x + min(side, offset + 7), y + side // 2), fill=LINE, width=2)


def stroke(draw, path, x, y, side, color):
    def place(a, b):
        return x + a * side / 100, y + b * side / 100
    points = []
    for segment in range(0, len(path) - 1, 3):
        p, q, r, s = path[segment:segment + 4]
        for i in range(65):
            t = i / 64
            u = 1 - t
            points.append(place(*(u**3*p[d] + 3*u*u*t*q[d] + 3*u*t*t*r[d] + t**3*s[d] for d in (0, 1))))
    if not points:
        return
    for i, point in enumerate(points):
        part = i / (len(points) - 1)
        width = (0.026 + 0.026 * (1 - abs(2 * part - 1))) * side
        if part > 0.87:
            width *= max(0.32, (1 - part) / .13)
        px, py = point
        draw.ellipse((px-width/2, py-width/2, px+width/2, py+width/2), fill=color)


def stroke_lesson(key, chars):
    art = canvas((840, 460))
    draw = ImageDraw.Draw(art)
    for row, char in enumerate(chars):
        y = 22 + 220 * row
        draw_text(draw, (98, y + 84), char, 103, kai=True)
        for j in range(len(STROKES[char])):
            x, side = 190 + 202 * j, 152
            grid(draw, x, y, side)
            for i, path in enumerate(STROKES[char][:j + 1]):
                stroke(draw, path, x, y, side, RED if i == j else INK)
            draw_text(draw, (x + side // 2, y + side + 26), str(j + 1), 27, GOLD)
    save(key, art)


def stroke_quiz(key, candidate):
    art = canvas((480, 280))
    draw = ImageDraw.Draw(art)
    x, y, side = 124, 23, 232
    grid(draw, x, y, side)
    for path in STROKES['子'][:2]:
        stroke(draw, path, x, y, side, INK)
    stroke(draw, candidate, x, y, side, RED)
    save(key, art)


def paragraph_card(key, rows):
    art = canvas((640, 365))
    draw = ImageDraw.Draw(art)
    draw.rounded_rectangle((67, 18, 573, 343), 22, fill='#fffef9', outline='#bbc9b3', width=4)
    for i, (indent, length) in enumerate(rows):
        y = 60 + 44*i
        x = 118 + (84 if indent else 0)
        if indent:
            for gap in (119, 160):
                draw.rounded_rectangle((gap, y - 12, gap+29, y+13), 4, outline='#b78545', width=2)
        for j in range(length):
            draw.rounded_rectangle((x+41*j, y-10, x+41*j+29, y+11), 5, fill='#547572')
    save(key, art)


def tone_card():
    art = canvas()
    draw = ImageDraw.Draw(art)
    specs = [('一片片','yí piàn piàn', 2),('一群','yì qún',4),('一会儿','yí huìr',2),('“一”字','yī',1)]
    for i, (term, spelling, tone) in enumerate(specs):
        x = 14 + 206*i
        draw.rounded_rectangle((x, 35, x+192, 365), 22, fill='#fffef8', outline='#bdc9b6', width=3)
        start, end = {1:(127,127),2:(181,110),4:(108,182)}[tone]
        draw.line((x+37,start,x+154,end), width=9, fill=RED)
        draw_text(draw, (x+96,242), term, 46, kai=True)
        draw_text(draw, (x+96,316), spelling, 25)
    save('tone-diagram', art)


def pace_card():
    art = canvas()
    draw = ImageDraw.Draw(art)
    for i, (term, support) in enumerate([('一会儿','会儿'),('凉了','了'),('黄了','了'),('来了','了'),('叶子','子')]):
        x = 14 + (i % 3) * 274
        y = 16 + (i // 3) * 191
        draw.rounded_rectangle((x, y, x+258, y+171), 18, fill='#fffdf5', outline='#bdc9b6', width=3)
        draw_text(draw, (x+129,y+67), term, 53, kai=True)
        draw_text(draw, (x+129,y+127), support, 33, RED, kai=True)
    save('pace-diagram', art)


def radical_card():
    art = canvas()
    draw = ImageDraw.Draw(art)
    for i, (char, radical, color) in enumerate([('秋','禾','#b47625'),('树','木','#397066'),('叶','口','#b35045')]):
        x = 17 + 274*i
        draw.rounded_rectangle((x,28,x+258,367),22,fill='#fffef8',outline='#bdc9b6',width=3)
        mark = Image.new('RGBA', (144,144))
        md = ImageDraw.Draw(mark)
        draw_text(md,(72,71),char,126,kai=True)
        for row in range(mark.height):
            for col in range(10, 59):
                if alpha := mark.getpixel((col,row))[3]:
                    rgb = tuple(int(color[i:i+2],16) for i in (1,3,5))
                    mark.putpixel((col,row),(*rgb,alpha))
        art.alpha_composite(mark,(x+57,52))
        draw_text(draw,(x+129,252),radical+'字旁',33,color)
    save('radical-diagram', art)


def tray(key, leaf, positions, *, width=640, height=360):
    art = canvas((width,height), '#d7b586')
    draw = ImageDraw.Draw(art)
    draw.rectangle((0,0,width,46), fill='#94b4aa')
    draw.line((0,46,width,46), fill='#815d3d', width=7)
    draw.rounded_rectangle((47,65,width-47,height-40), 22, fill='#fff1d0', outline='#a87243', width=7)
    draw.rounded_rectangle((59,77,width-59,height-52), 18, outline='#e0c192', width=3)
    for x, y, angle in positions:
        stamp(art, leaf, (x,y), (115,112), angle)
    save(key, art)


def flock(key, background, goose, points):
    art = background.resize((720, 405), Image.Resampling.LANCZOS).convert('RGBA')
    for x,y in points:
        stamp(art, goose, (x,y), (72,46))
    save(key, art)


def render():
    prompts = json.loads((ROOT / 'imagegen-prompts.json').read_text())
    for key in prompts:
        im = Image.open(ORIGINALS / f'{key}.png')
        size = (1450,816) if key == 'cover' else (980,580)
        if key != 'quiz-maple':
            save(key, fit(im, size))
    cover = Image.open(ORIGINALS / 'cover.png')
    save('cool-path', fit(cover.crop((180,236,665,855)), (760,560)))
    leaf_scene = Image.open(ORIGINALS / 'leaf-fall.png')
    save('yellow-tree', fit(leaf_scene.crop((0,0,665,420)),(760,540)))
    leaf = Image.open(ORIGINALS / 'one-leaf.png').convert('RGBA')
    falling = leaf_scene.crop((1000,300,1672,725)).resize((750,474),Image.Resampling.LANCZOS).convert('RGBA')
    for px,py,angle in [(220,108,-28),(345,215,25),(501,298,67)]:
        stamp(falling,leaf,(px,py),(122,107),angle)
    save('fall-close',falling)
    maple = Image.open(ORIGINALS / 'quiz-maple.png').convert('RGBA')
    tray('many-leaves',leaf,[(175,140,-26),(310,137,12),(451,145,37),(235,244,17),(395,244,-17)])
    tray('one-tray',leaf,[(320,184,8)])
    tray('empty-tray',leaf,[])
    tray('quiz-tray-one',maple,[(320,180,-17)])
    tray('quiz-tray-many',maple,[(164,148,19),(320,154,-21),(474,143,9),(240,244,-8),(395,244,30)])
    tray('quiz-tray-empty',maple,[],width=632)
    sky = Image.open(ORIGINALS / 'blue-sky.png')
    goose = Image.open(ORIGINALS / 'goose.png').convert('RGBA')
    art = sky.resize((840, 472), Image.Resampling.LANCZOS).convert('RGBA')
    stamp(art, goose, (474,188), (450,268))
    save('sky-goose', art)
    recap = canvas((720, 460))
    pen = ImageDraw.Draw(recap)
    for i, (key, bounds) in enumerate([('leaf-fall',(20,20,680,130)),('flock-v',(20,165,680,130)),('cover',(20,310,680,130))],1):
        x,y,width,height = bounds
        if key == 'flock-v':
            scene = sky.resize((720,405), Image.Resampling.LANCZOS).convert('RGBA')
            for px,py in [(360,120),(295,150),(230,180),(165,210),(425,150),(490,180),(555,210)]:
                stamp(scene,goose,(px,py),(59,38))
        else:
            scene = Image.open(ORIGINALS / f'{key}.png')
        center = (.5,.41) if i == 2 else (.5,.47) if i == 3 else (.5,.58)
        recap.alpha_composite(ImageOps.fit(scene.convert('RGBA'),(width,height),Image.Resampling.LANCZOS,centering=center),(x,y))
        pen.ellipse((x+12,y+12,x+62,y+62),fill='#fff6da')
        draw_text(pen,(x+37,y+37),str(i),28)
    save('recap-triptych',recap)
    flock('flock-v',sky,goose,[(360,78),(299,130),(239,182),(179,234),(421,130),(481,182),(541,234)])
    flock('flock-line',sky,goose,[(102+86*i,160) for i in range(7)])
    flock('flock-scatter',sky,goose,[(144,87),(227,214),(302,140),(361,209),(452,86),(517,153),(589,223)])
    paragraph_card('paragraph-diagram',[(True,7),(False,8),(True,7),(False,5),(True,4)])
    paragraph_card('quiz-layout-one',[(True,7),(False,8),(False,7),(False,6),(False,4)])
    paragraph_card('quiz-layout-two',[(True,7),(False,8),(False,7),(True,6),(False,4)])
    paragraph_card('quiz-layout-three',[(True,7),(False,8),(True,7),(True,6),(False,4)])
    tone_card()
    pace_card()
    radical_card()
    stroke_lesson('stroke-le-zi','了子')
    stroke_lesson('stroke-da-ren','大人')
    stroke_quiz('quiz-stroke-dot',((66,57),(69,60),(74,63),(76,66)))
    stroke_quiz('quiz-stroke-flat',STROKES['子'][2])
    stroke_quiz('quiz-stroke-left',((78,51),(73,62),(66,73),(60,81)))
    print(f'Rendered {len(list(ASSETS.glob("*.png")))} local assets')


if __name__ == '__main__':
    render()
