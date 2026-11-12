"""Draw the original story diagrams, handwriting paths, and quiz variants."""

from functools import lru_cache
from hashlib import sha256
import json
from math import atan2, cos, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

LESSON = Path(__file__).resolve().parents[1]
ASSETS = LESSON / 'assets'
PAPER = '#fff5e2'
INK = '#25433b'
MINT = '#d5eee4'
LINE = '#378477'
BLUE = '#70c2cc'
WATERLINE = '#176f82'
RUST = '#aa4a2a'
KAI = '/System/Library/AssetsV2/com_apple_MobileAsset_Font8/88d6cc32a907955efa1d014207889413890573be.asset/AssetData/Kaiti.ttc'
SANS = '/System/Library/Fonts/Hiragino Sans GB.ttc'
WATER_ROWS = (237, 150, 65)

# Paths on a 100 by 100 square, in the pen direction and textbook stroke order.
STROKES = {
    '只': (
        [(30,20),(30,46)], [(30,20),(72,20),(70,46)], [(30,46),(70,46)],
        [(44,61),(36,72),(23,83)], [(59,64),(72,73),(81,84)],
    ),
    '石': (
        [(17,25),(82,25)], [(49,25),(44,45),(34,61),(16,75)], [(39,51),(39,82)],
        [(39,51),(76,51),(75,82)], [(39,82),(75,82)],
    ),
    '多': (
        [(45,12),(35,25),(25,31)], [(37,24),(65,24),(55,38),(39,50),(25,55)],
        [(39,30),(49,36)], [(60,46),(50,61),(37,66)],
        [(55,58),(80,58),(67,73),(48,86),(25,91)], [(52,65),(63,72)],
    ),
    '出': (
        [(29,23),(29,46),(72,46)], [(72,23),(72,46)], [(50,11),(50,80)],
        [(21,56),(21,80),(80,80)], [(80,56),(80,80)],
    ),
    '个': (
        [(50,14),(44,34),(29,48),(14,54)], [(50,16),(62,37),(74,46),(85,52)],
        [(50,43),(50,86)],
    ),
}


def canvas(size=(720, 400), fill=PAPER):
    return Image.new('RGBA', size, fill)


@lru_cache
def font(size, kai=False):
    return ImageFont.truetype(KAI if kai else SANS, size)


@lru_cache
def artwork(key):
    with Image.open(ASSETS / f'{key}.png') as source:
        art = source.convert('RGBA')
    return art.crop(art.getchannel('A').point(lambda v: 255 if v >= 16 else 0).getbbox())


def stamp(image, key, box):
    left, top, width, height = box
    art = artwork(key).copy()
    art.thumbnail((width,height), Image.Resampling.LANCZOS)
    x = left + (width - art.width)//2
    y = top + (height - art.height)//2
    image.alpha_composite(art, (x,y))
    return x,y,art.width,art.height


def scene(key, size):
    art = artwork(key)
    return ImageOps.fit(art.convert('RGB'), size, Image.Resampling.LANCZOS).convert('RGBA')


def arrow(draw, a, b, fill=RUST, width=8):
    draw.line((*a,*b), fill=fill, width=width)
    direction = atan2(b[1]-a[1],b[0]-a[0])
    sides = [(b[0]-cos(direction+angle)*width*3,b[1]-sin(direction+angle)*width*3)
             for angle in (-.52,.52)]
    draw.polygon([b,*sides],fill=fill)


def bottle(level, *, wide=False, guides=(), stone_count=None):
    """One schematic vessel; the dashed guides preserve earlier waterlines."""
    image = canvas((200,318),'#00000000')
    draw = ImageDraw.Draw(image)
    left, right = (55,145) if wide else (70,130)
    outline = [(left,28),(left,63),(42,95),(36,125),(36,273),(44,294),
               (57,302),(143,302),(156,294),(164,273),(164,125),(158,95),
               (right,63),(right,28)]
    mask = Image.new('L',image.size)
    ImageDraw.Draw(mask).polygon(outline,fill=255)
    image.paste(MINT,(0,0),mask)
    y = WATER_ROWS[level]
    layer = canvas(image.size,'#00000000')
    water = ImageDraw.Draw(layer)
    water.rectangle((0,y,199,317),fill=BLUE)
    water.line((20,y,180,y),fill=WATERLINE,width=7)
    image.paste(layer,(0,0),Image.composite(mask,Image.new('L',image.size),layer.getchannel('A')))
    count = level * 6 if stone_count is None else stone_count
    for index in range(count):
        px = 48 + (index % 3) * 37
        py = 274 - (index // 3) * 21
        stamp(image,'stone-one',(px,py,31,22))
    for guide in guides:
        y_guide = WATER_ROWS[guide]
        for x in range(46,151,19):
            draw.line((x,y_guide,x+9,y_guide),fill='#fff9ec',width=4)
    draw.line(outline,fill=LINE,width=6,joint='curve')
    draw.ellipse((left,21,right,36), fill='#fcfff5', outline=LINE,width=5)
    draw.line((48,136,48,193),fill='#fcfff5',width=4)
    return image


def put_vessel(image, origin, level, **options):
    image.alpha_composite(bottle(level,**options),origin)


def small_frame(kind, size=(300,270)):
    image = canvas((460,390))
    draw = ImageDraw.Draw(image)
    draw.ellipse((11,280,454,385),fill='#f2d8a8')
    if kind in ('dry','drink'):
        level = 0 if kind == 'dry' else 2
        x, y = 208, 56
        draw.rounded_rectangle((77,118,258,338),radius=26,fill='#d2bca3',outline='#b39b80',width=4)
        put_vessel(image,(x,y),level)
        # The identical beak point reaches the upper mark and misses the
        # lower mark. The stone slab supports the feet in both pictures.
        stamp(image,'crow-reach',(83,2,231,120))
    elif kind == 'stone':
        stamp(image,'crow-stand',(12,19,302,304))
        stamp(image,'stone-one',(337,255,89,56))
        stamp(image,'stone-one',(317,312,58,36))
    elif kind in ('drop','take'):
        put_vessel(image,(135,55),1,stone_count=5)
        stamp(image,'pinch-hand',(178,0,128,95))
        stamp(image,'stone-one',(223,76,42,29))
        a,b = (292,55),(290,134)
        arrow(draw,a if kind=='drop' else b,b if kind=='drop' else a)
    else:
        stamp(image,'crow-walk',(30,55,395,240))
    return image.resize(size,Image.Resampling.LANCZOS)


def panel_strip(cards, *, size=(840,380), cols=None):
    image = canvas(size)
    draw = ImageDraw.Draw(image)
    cols = cols or len(cards)
    rows = (len(cards)+cols-1)//cols
    slot_width, slot_height = size[0]//cols,size[1]//rows
    for i,card in enumerate(cards):
        x,y = (i%cols)*slot_width,(i//cols)*slot_height
        draw.rounded_rectangle((x+5,y+5,x+slot_width-6,y+slot_height-6),radius=18,
                               fill='#fff9e9',outline=LINE,width=4)
        content = ImageOps.contain(card,(slot_width-21,slot_height-21))
        image.alpha_composite(content,(x+(slot_width-content.width)//2,y+(slot_height-content.height)//2))
    return image


def water_panel(level, *, guides=(), wide=False):
    image = canvas((274,338))
    put_vessel(image,(29,6),level,guides=guides,wide=wide)
    return image


def handwriting(chars):
    image = canvas((900, 188 * len(chars)))
    draw = ImageDraw.Draw(image)
    for row,char in enumerate(chars):
        y = 15+row*188
        draw.text((59,y+70),char,font=font(95,True),fill=INK,anchor='mm')
        for step in range(len(STROKES[char])):
            x = 119+128*step
            side = 112
            draw.rounded_rectangle((x,y,x+side,y+side),radius=6,fill='#fffdf0',outline=LINE,width=3)
            for d in range(5,side,14):
                draw.line((x+side//2,y+d,x+side//2,y+d+6),fill='#9db9ac',width=2)
                draw.line((x+d,y+side//2,x+d+6,y+side//2),fill='#9db9ac',width=2)
            for i,path in enumerate(STROKES[char][:step+1]):
                points = [(x+round(a*side/100),y+round(b*side/100)) for a,b in path]
                draw.line(points,fill=RUST if i==step else INK,width=5,joint='curve')
            draw.text((x+side//2,y+137),str(step+1),font=font(24),fill=RUST,anchor='mm')
    return image


def radical():
    image = canvas((390,270))
    draw = ImageDraw.Draw(image)
    draw.text((112,137),'辶',font=font(132,True),fill=RUST,anchor='mm')
    draw.text((280,137),'进',font=font(132,True),fill=INK,anchor='mm')
    return image


def pen_basket(direction):
    image = canvas((360,315))
    draw = ImageDraw.Draw(image)
    stamp(image,'craft-basket',(74,123,217,181))
    if direction == 'side':
        stamp(image,'paintbrush',(9,43,132,124))
        arrow(draw,(86,58),(141,58))
    else:
        stamp(image,'paintbrush',(85,8,134,131))
        a,b=(212,56),(212,166)
        arrow(draw,a if direction=='in' else b,b if direction=='in' else a)
    return image


def toy_touch(mode):
    image = canvas((360,315))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((16,246,343,264),radius=8,fill='#bc8f59')
    stamp(image,'toy-bird',(24,99,188,149))
    if mode == 'touch':
        stamp(image,'star-charm',(202,41,119,160))
    elif mode == 'high':
        stamp(image,'star-charm',(204,1,119,122))
    else:
        stamp(image,'star-charm',(243,35,105,157))
    return image


def toy_bottle(level, wide):
    image = canvas((425,350))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((63,176,253,272),radius=20,fill='#dfc7a5')
    put_vessel(image,(190,10),level,wide=wide)
    stamp(image,'toy-bird',(84,40,204,138))
    return image


def pool(kind):
    image = canvas((330,240))
    draw = ImageDraw.Draw(image)
    draw.ellipse((13,94,288,225),fill=BLUE,outline=WATERLINE,width=6)
    if kind in ('ball','find','scoop'):
        stamp(image,'toy-ball',(119,111,78,78))
    if kind == 'find':
        stamp(image,'scoop-net',(175,2,147,124))
    elif kind == 'scoop':
        stamp(image,'scoop-net',(52,56,154,151))
        stamp(image,'toy-ball',(119,111,78,78))
    elif kind == 'out':
        stamp(image,'scoop-net',(184,0,139,138))
        stamp(image,'toy-ball',(241,31,59,59))
    return image


def aligned_boat(key):
    art = artwork(key).copy()
    width = 168
    art = art.resize((width,round(art.height*width/art.width)),Image.Resampling.LANCZOS)
    canvas_up = canvas((210,320),'#00000000')
    canvas_up.alpha_composite(art,((210-width)//2,307-art.height))
    # The template rotates a right-facing sprite back toward the screen top.
    return canvas_up.transpose(Image.Transpose.ROTATE_270)


def art():
    yield 'boat-right-idle',aligned_boat('boat-idle'),['word-scenes'],['boat-idle']
    yield 'boat-right-blow',aligned_boat('boat-blow'),['word-scenes'],['boat-blow']
    opening=scene('garden-scene',(660,400))
    stamp(opening,'crow-walk',(99,113,364,258))
    yield 'opening-crow',opening,['story-stage'],['garden-scene','crow-walk']
    yield 'channel-backdrop',scene('channel-scene',(416,234)),['word-scenes'],['channel-scene']
    yield 'projection-backdrop',scene('projection-scene',(416,234)),['retell-route'],['projection-scene']
    for key in ('search','dry','stone','drop','take','drink'):
        parents = {'search':['crow-walk'],'dry':['crow-reach','stone-one'],'stone':['crow-stand','stone-one'],
                   'drop':['pinch-hand','stone-one'],'take':['pinch-hand','stone-one'],'drink':['crow-reach','stone-one']}
        yield f'story-{key}',small_frame(key),['story-stage','read-and-recognize','word-scenes','retell-route'],parents[key]
    yield 'look-close',panel_strip([small_frame('dry'),small_frame('stone')]),['look-around'],['crow-reach','crow-stand','stone-one']
    yield 'steps-story',panel_strip([small_frame(k) for k in ('dry','stone','drop','drink')]),['say-the-story'],['crow-reach','crow-stand','pinch-hand','stone-one']
    yield 'vessel-mouth',water_panel(0),['the-bottle-problem'],[]
    yield 'vessel-low',water_panel(0),['word-scenes'],[]
    yield 'vessel-high',water_panel(2),['word-scenes'],['stone-one']
    yield 'vessel-process',panel_strip([water_panel(level,guides=tuple(range(level))) for level in range(3)]),['see-it-rise'],['stone-one']
    yield 'stroke-first',handwriting('只石'),['write-first-two'],[]
    yield 'stroke-last',handwriting('多出个'),['write-last-three'],[]
    yield 'radical-cards',radical(),['read-radical'],[]

    for k,m in zip('abc',('in','out','side')):
        yield f'q1-{k}',pen_basket(m),['picture-check.q1'],['craft-basket','paintbrush']
    for k,m in zip('abc',('high','touch','far')):
        yield f'q2-{k}',toy_touch(m),['picture-check.q2'],['toy-bird','star-charm']
    for k,(level,wide) in zip('abc',((0,True),(2,False),(0,False))):
        yield f'q3-{k}',toy_bottle(level,wide),['picture-check.q3'],['toy-bird','stone-one']
    for k,sequence in zip('abc',((0,0,2),(0,1,2),(2,1,0))):
        yield f'q4-{k}',panel_strip([water_panel(level,wide=True) for level in sequence],size=(450,230)),['picture-check.q4'],['stone-one']
    for k,sequence in zip('abc',(('ball','find','scoop','out'),('find','ball','scoop','out'),('ball','out','find','scoop'))):
        yield f'q5-{k}',panel_strip([pool(part) for part in sequence],size=(320,268),cols=2),['picture-check.q5'],['toy-ball','scoop-net']
    for k,sequence in zip('abc',(('ball','find'),('find','out'),('scoop','out'))):
        yield f'q6-{k}',panel_strip([pool(part) for part in sequence],size=(350,240)),['picture-check.q6'],['toy-ball','scoop-net']


def write_assets():
    digest=lambda p:sha256(p.read_bytes()).hexdigest()
    sources={}
    for receipt in sorted((LESSON/'art-source').glob('*.receipt.json')):
        payload=json.loads(receipt.read_text())
        for row in payload['assets']:
            sources[row['assetKey']]={**row,'file':row['path'],'kind':'codex-builtin-imagegen'}
    for key,image,uses,parents in art():
        p=ASSETS/f'{key}.png'
        image.save(p,optimize=True)
        sources[key]={'file':p.relative_to(LESSON).as_posix(),'sha256':digest(p),
                      'kind':'deterministic-lesson-diagram','usedBy':uses,'source':'diagrams/render.py',
                      'sourceSha256':digest(Path(__file__)),'sourceAssets':{q:sources[q]['sha256'] for q in parents}}
    manifest={'schemaVersion':'mira.courseware.asset-sources.v1','assets':sources}
    (LESSON/'asset-sources.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    write_assets()
