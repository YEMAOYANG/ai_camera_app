"""Render exact quantities for the nursery story, games and transfer quiz."""

from functools import lru_cache
from hashlib import sha256
import json
from math import atan2, ceil, cos, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets'
PAPER = '#fff6e6'
INK = '#204337'
MINT = '#cfe6d6'
GREEN = '#347863'
PEACH = '#f2d0a9'
RUST = '#a24a27'
GRAY = '#795d47'
FONT = '/System/Library/Fonts/Hiragino Sans GB.ttc'
RETURN_PAIRS = ((4,7),(6,7),(8,5),(4,8))
TILE_PAIRS = ((3,8),(4,9),(6,9),(8,6),(5,7),(9,8),(8,8),(6,7))


def board(size=(720,380)):
    im = Image.new('RGBA',size,PAPER)
    return im,ImageDraw.Draw(im)


@lru_cache
def font(size):
    return ImageFont.truetype(FONT,size)


def mark(draw, value, xy, size, color=INK):
    draw.text(xy,str(value),font=font(size),fill=color,anchor='mm')


@lru_cache
def art(key):
    with Image.open(ASSETS/f'{key}.png') as source:
        image=source.convert('RGBA')
    mask=image.getchannel('A').point(lambda a:255 if a>=16 else 0)
    return image.crop(mask.getbbox())


@lru_cache
def small(key, width, height):
    image=art(key).copy()
    image.thumbnail((width,height),Image.Resampling.LANCZOS)
    return image


def stamp(im, key, center, size):
    image=small(key,*size)
    x,y=center
    im.alpha_composite(image,(x-image.width//2,y-image.height//2))


def scene(key,size):
    return ImageOps.fit(art(key).convert('RGB'),size,Image.Resampling.LANCZOS).convert('RGBA')


def arrow(draw,a,b,color=RUST,width=8):
    draw.line((*a,*b),fill=color,width=width)
    angle=atan2(b[1]-a[1],b[0]-a[0])
    heads=[(b[0]-cos(angle+offset)*3*width,b[1]-sin(angle+offset)*3*width) for offset in (-.5,.5)]
    draw.polygon([b,*heads],fill=color)


def slots(count, center, pitch, columns):
    x,y=center
    rows=ceil(count/columns)
    positions=[]
    for row in range(rows):
        length=min(columns,count-row*columns)
        for i in range(length):
            positions.append((round(x+(i-(length-1)/2)*pitch[0]),
                              round(y+(row-(rows-1)/2)*pitch[1])))
    return positions


def place(im,key,count,center,*,size=(53,55),pitch=(64,59),columns=5,crossed=0):
    draw=ImageDraw.Draw(im)
    for index,(x,y) in enumerate(slots(count,center,pitch,columns)):
        stamp(im,key,(x,y),size)
        if index<crossed:
            dx=max(8,round(size[0]*.35))
            dy=max(8,round(size[1]*.35))
            draw.line((x-dx,y-dy,x+dx,y+dy),fill=RUST,width=5)


def panel(draw,box,color,stroke=GREEN,width=5):
    draw.rounded_rectangle(box,radius=18,fill=color,outline=stroke,width=width)


def tray_quantity(count,role,key='seedling'):
    im,d=board((318,255))
    color,stroke=(PEACH,RUST) if role=='sent' else (MINT,GREEN)
    panel(d,(12,35,306,239),color,stroke)
    if role=='sent':
        arrow(d,(119,22),(199,22),width=6)
    place(im,key,count,(159,132),size=(48,67),pitch=(51,68))
    return im


def story_three():
    im,d=board((780,350))
    for i in range(3):
        x=25+i*249
        panel(d,(x,72,x+218,318),'#f6e3bf')
        stamp(im,'green-tray',(x+109,238),(205,170))
        if i==0:
            place(im,'seedling',5,(x+109,228),size=(35,51),pitch=(35,55),columns=5)
        elif i==1:
            place(im,'seedling',3,(x+109,228),size=(37,53),pitch=(43,55),columns=5)
            stamp(im,'cart-open',(x+105,132),(173,79))
            place(im,'seedling',2,(x+63,123),size=(31,42),pitch=(35,44),columns=3)
            arrow(d,(x+154,129),(x+199,129),width=5)
        else:
            place(im,'seedling',3,(x+109,228),size=(37,53),pitch=(43,55),columns=5)
    for x in (246,495):
        arrow(d,(x-6,196),(x+20,196),width=5)
    return im


def two_parts(sent,left,key='seedling',*,merged=False,cap=True):
    im,d=board((720,405))
    panel(d,(18,44,702,373),'#fff9ec')
    panel(d,(33,69,350,272),PEACH,RUST)
    panel(d,(370,69,687,272),MINT)
    arrow(d,(123,48),(258,48),width=7)
    place(im,key,sent,(191,168),size=(52,65),pitch=(54,68))
    place(im,key,left,(528,168),size=(52,65),pitch=(54,68))
    if cap:
        mark(d,sent,(191,298),48,RUST)
        mark(d,left,(528,298),48,GREEN)
    if merged:
        mark(d,'+', (360,298),50)
        mark(d,f'= {sent+left}', (360,340),46)
    return im


def whole(sent,left,key='seedling',*,crossed=0,total_mark=None):
    count=sent+left
    im,d=board((720,405))
    panel(d,(15,43,705,367),'#f8e6c6')
    place(im,key,count,(360,188),size=(66,70),pitch=(78,78),columns=8,crossed=crossed)
    if total_mark is not None:
        mark(d,total_mark,(360,327),57)
    return im


def equation_card(sent,left):
    im,d=board((700,380))
    for x, value, fill in ((135,sent,PEACH),(355,left,MINT),(568,sent+left,'#f6ddaf')):
        panel(d,(x-84,42,x+84,211),fill)
        mark(d,value,(x,125),95)
    for x,sign in ((244,'+'),(466,'=')):
        mark(d,sign,(x,125),62)
    missing = 10-sent
    leftover = left-missing
    for x,text in ((181,f'{sent}+{missing}=10'),(515,f'10+{leftover}={sent+left}')):
        panel(d,(x-142,256,x+142,346),'#fff9ed')
        mark(d,text,(x,300),50)
    return im


def returned_model(sent,left):
    im,d=board((330,380))
    for y,n,color,stroke in ((72,sent,PEACH,RUST),(203,left,MINT,GREEN)):
        panel(d,(12,y-52,318,y+53),color,stroke)
        place(im,'seedling',n,(128,y),size=(40,45),pitch=(48,47),columns=4)
        if n:
            mark(d,n,(269,y),59,stroke)
    mark(d,f'{sent}+{left}={sent+left}' if sent else '?',(165,322),64)
    return im


def role_icon(role,n):
    im,d=board((184,184))
    color,stroke=(PEACH,RUST) if role=='sent' else (MINT,GREEN)
    panel(d,(4,4,179,179),color,stroke,width=6)
    if role=='sent':
        arrow(d,(42,34),(142,34),width=6)
    stamp(im,'seedling',(49,110),(60,100))
    mark(d,n,(122,113),83,stroke)
    return im


def card_icon(kind,a,b=None):
    im,d=board((184,184))
    if kind=='pair':
        panel(d,(4,4,179,179),PAPER,width=7)
        d.rounded_rectangle((10,10,173,87),radius=10,fill=PEACH)
        d.rounded_rectangle((10,92,173,173),radius=10,fill=MINT)
        mark(d,a,(83,49),72,RUST)
        mark(d,f'+{b}',(90,131),69,GREEN)
    else:
        before=kind=='past'
        color,stroke=('#f7e3ad',GRAY) if before else (MINT,GREEN)
        panel(d,(4,4,179,179),color,stroke,width=7)
        arrow(d,(140,35) if before else (44,35),(44,35) if before else (140,35),stroke,7)
        mark(d,a,(92,115),83,stroke)
    return im


def quiz_visuals():
    for letter,stage in zip('abc',('during','before','after')):
        im,d=board((460,380))
        panel(d,(19,44,441,345),MINT)
        if stage=='before':
            place(im,'leaf-sticker',10,(230,194),size=(59,65),pitch=(70,76))
        elif stage=='during':
            place(im,'leaf-sticker',6,(244,222),size=(54,60),pitch=(62,64))
            place(im,'leaf-sticker',4,(205,79),size=(46,51),pitch=(51,57))
            arrow(d,(329,86),(415,86),width=9)
        else:
            place(im,'leaf-sticker',6,(230,218),size=(59,65),pitch=(70,76))
        yield 'q1-'+letter,im,['picture-check.q1'],['leaf-sticker']
    for letter,count in zip('abc',(8,12,13)):
        yield 'q2-'+letter,whole(0,count,'checker'),['picture-check.q2'],['checker']
    for letter,(a,b) in zip('abc',((6,7),(6,6),(7,7))):
        yield 'q3-'+letter,two_parts(a,b,'index-card',cap=False),['picture-check.q3'],['index-card']
    for letter,(a,b) in zip('abc',((0,9),(5,9),(0,5))):
        yield 'q4-'+letter,whole(a,b,'wax-crayon'),['picture-check.q4'],['wax-crayon']
    for letter,cross in zip('abc',(8,6,9)):
        yield 'q5-'+letter,whole(0,14,'clothespin',crossed=cross),['picture-check.q5'],['clothespin']
    for letter,(count,cross) in zip('abc',((14,0),(10,6),(10,4))):
        yield 'q6-'+letter,whole(0,count,'fabric-swatch',crossed=cross),['picture-check.q6'],['fabric-swatch']


def visuals():
    cover=scene('nursery-shed',(490,300))
    stamp(cover,'green-tray',(241,204),(346,190))
    place(cover,'seedling',5,(241,216),size=(47,56),pitch=(53,60))
    yield 'nursery-cover',cover,['nursery-before-and-after'],['nursery-shed','green-tray','seedling']
    yield 'yard-backdrop',scene('nursery-yard',(416,234)),['bring-the-parts-back'],['nursery-yard']
    yield 'bench-backdrop',scene('nursery-workbench',(416,234)),['restore-pair'],['nursery-workbench']
    yield 'time-three',story_three(),['nursery-before-and-after'],['green-tray','cart-open','seedling']
    yield 'sent-seven',tray_quantity(7,'sent'),['find-both-parts'],['seedling']
    yield 'left-six',tray_quantity(6,'left'),['find-both-parts'],['seedling']
    yield 'combine-7-6',two_parts(7,6,merged=True),['make-an-addition'],['seedling']
    yield 'equation-7-6',equation_card(7,6),['make-an-addition'],[]
    yield 'ask-past',two_parts(3,9),['different-questions'],['seedling']
    yield 'ask-left',whole(3,9,crossed=3,total_mark=12),['different-questions'],['seedling']
    yield 'check-full',whole(7,6,total_mark=13),['replay-and-check'],['seedling']
    yield 'check-cross',whole(7,6,crossed=7),['replay-and-check'],['seedling']
    yield 'invent-story',two_parts(6,6),['make-up-a-story'],['seedling']
    yield 'return-empty',returned_model(0,0),['bring-the-parts-back'],[]
    for n in (4,5,6,7,8,9):
        yield f'sent-{n}',role_icon('sent',n),['bring-the-parts-back'],['seedling']
        yield f'left-{n}',role_icon('left',n),['bring-the-parts-back'],['seedling']
    for a,b in RETURN_PAIRS:
        yield f'returned-{a}-{b}',returned_model(a,b),['bring-the-parts-back'],['seedling']
    for a,b in TILE_PAIRS:
        yield f'tile-{a}-{b}',card_icon('pair',a,b),['restore-pair'],[]
        yield f'workcard-{a}-{b}',two_parts(a,b),['restore-pair'],['seedling']
    for total in sorted({a+b for a,b in TILE_PAIRS}):
        yield f'past-{total}',card_icon('past',total),['restore-pair'],[]
    yield 'after-13',card_icon('after',13),['restore-pair'],[]
    yield from quiz_visuals()


def render():
    digest=lambda p:sha256(p.read_bytes()).hexdigest()
    sources={}
    for receipt in sorted((ROOT/'art-source').glob('*.receipt.json')):
        for row in json.loads(receipt.read_text())['assets']:
            sources[row['assetKey']]={**row,'file':row['path'],'kind':'codex-builtin-imagegen'}
    for key,im,uses,parents in visuals():
        p=ASSETS/f'{key}.png'
        im.save(p,optimize=True)
        sources[key]={'file':p.relative_to(ROOT).as_posix(),'sha256':digest(p),
                      'kind':'deterministic-lesson-diagram','usedBy':uses,'source':'diagrams/render.py',
                      'sourceSha256':digest(Path(__file__)),'sourceAssets':{a:sources[a]['sha256'] for a in parents}}
    doc={'schemaVersion':'mira.courseware.asset-sources.v1','assets':sources}
    (ROOT/'asset-sources.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    render()
