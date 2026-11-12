"""Render the known groups and unknown quantities in each original picture."""

from functools import lru_cache
from hashlib import sha256
import json
from math import ceil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets'
PAPER = '#fff5e4'
INK = '#234237'
GREEN = '#2e7560'
MINT = '#d3eadc'
RUST = '#a64727'
PEACH = '#f3cfa9'
GOLD = '#f5dfa8'
FONT = '/System/Library/Fonts/Hiragino Sans GB.ttc'

SORT_MODELS = (
    ('add',5,3),('sub',8,3),('add',7,2),('add',4,6),('sub',10,4),
    ('sub',12,3),('add',8,3),('sub',11,5),('add',6,4),
)
LAUNCH_MODELS = (
    ('add',6,2),('sub',9,4),('add',7,3),('sub',12,4),('add',5,4),
    ('add',7,5),('sub',14,5),('sub',13,5),
)


def board(size=(720,410)):
    image=Image.new('RGBA',size,PAPER)
    return image,ImageDraw.Draw(image)


@lru_cache
def font(size):
    return ImageFont.truetype(FONT,size)


def mark(draw,value,xy,size,color=INK):
    draw.text(xy,str(value),font=font(size),fill=color,anchor='mm')


def rounded(draw,box,color,stroke=GREEN,width=5):
    draw.rounded_rectangle(box,radius=20,fill=color,outline=stroke,width=width)


@lru_cache
def original(key):
    with Image.open(ASSETS/f'{key}.png') as source:
        image=source.convert('RGBA')
    return image.crop(image.getchannel('A').point(lambda a:255 if a>=16 else 0).getbbox())


@lru_cache
def resized(key,size):
    image=original(key).copy()
    image.thumbnail(size,Image.Resampling.LANCZOS)
    return image


def stamp(image,key,center,size):
    item=resized(key,size)
    x,y=center
    image.alpha_composite(item,(x-item.width//2,y-item.height//2))


def scene(key,size):
    return ImageOps.fit(original(key).convert('RGB'),size,Image.Resampling.LANCZOS).convert('RGBA')


def positions(count,center,pitch,columns):
    x,y=center
    rows=ceil(count/columns)
    for row in range(rows):
        length=min(columns,count-row*columns)
        for col in range(length):
            yield round(x+(col-(length-1)/2)*pitch[0]),round(y+(row-(rows-1)/2)*pitch[1])


def place(image,key,count,center,*,size=(52,65),pitch=(62,73),columns=5,crossed=0):
    d=ImageDraw.Draw(image)
    for i,(x,y) in enumerate(positions(count,center,pitch,columns)):
        stamp(image,key,(x,y),size)
        if i<crossed:
            dx,dy=max(11,size[0]//3),max(12,size[1]//3)
            d.line((x-dx,y-dy,x+dx,y+dy),fill='#8c3024',width=6)


def flow(draw,x,y,direction):
    start,end=x-direction*64,x+direction*62
    draw.line((start,y,end,y),fill=RUST,width=8)
    draw.polygon([(end,y),(end-direction*23,y-14),(end-direction*23,y+14)],fill=RUST)


def two_groups(a,b,*,key='lantern-one',event='still',focus='whole',label=True):
    image,d=board()
    rounded(d,(23,57,697,358),'#fff9eb',INK if focus=='whole' else '#bcaa88',8 if focus=='whole' else 3)
    for x,n,color,group in ((38,a,PEACH,'left'),(370,b,MINT,'right')):
        rounded(d,(x,83,x+312,304),color,INK if focus==group else GREEN,10 if focus==group else 4)
        place(image,key,n,(x+156,194),size=(51,66),pitch=(57,70))
        if label:
            mark(d,n,(x+156,328),38)
    if event=='out':
        flow(d,92,50,-1)
    if event=='come':
        flow(d,527,50,-1)
    if label:
        mark(d,'?',(360,382),46,RUST)
    return image


def whole(count,*,key='lantern-one',crossed=0,label=False):
    image,d=board()
    rounded(d,(28,50,692,355),'#f8e3bc')
    place(image,key,count,(360,199),size=(59,66),pitch=(73,75),columns=8,crossed=crossed)
    if label:
        mark(d,count,(360,326),52)
    return image


def hidden(total,visible,*,key='lantern-one'):
    image,d=board()
    rounded(d,(21,45,699,366),'#fff9eb',INK,6)
    rounded(d,(37,85,352,302),PEACH)
    rounded(d,(369,85,683,302),MINT)
    place(image,key,visible,(195,194),size=(51,63),pitch=(58,70))
    stamp(image,'cloth-cover',(527,192),(280,200))
    mark(d,'?',(527,209),64,'#fff9eb')
    mark(d,total,(360,338),50)
    return image


def relation_icon(kind,a,b):
    """All icons use the same colors; the question mark determines the rule."""
    image,d=board((190,190))
    rounded(d,(4,4,185,185),'#fff9eb',INK,6)
    d.rounded_rectangle((39,12,150,80),radius=10,fill=GOLD,outline=INK,width=4)
    mark(d,'?' if kind=='add' else a,(95,47),63 if kind=='add' else 50,RUST if kind=='add' else INK)
    d.line((95,81,95,97),fill=INK,width=5)
    d.line((48,97,142,97),fill=INK,width=5)
    for x,n,fill in ((47,a if kind=='add' else b,PEACH),(143,b if kind=='add' else '?',MINT)):
        d.rounded_rectangle((x-35,106,x+35,172),radius=10,fill=fill,outline=INK,width=4)
        mark(d,n,(x,141),59 if n=='?' else 49,RUST if n=='?' else INK)
    return image


def large_model(kind,a,b):
    image,d=board((340,410))
    if kind=='add':
        for y,n,fill,ink in ((144,a,PEACH,RUST),(282,b,MINT,GREEN)):
            rounded(d,(12,y-54,328,y+55),fill,ink)
            place(image,'lantern-one',n,(130,y),size=(39,43),pitch=(47,47),columns=4)
            mark(d,n,(270,y),60,ink)
        mark(d,'?',(170,44),67,RUST)
        if (a,b)==(7,5):
            flow(d,102,79,-1)
    else:
        rounded(d,(12,14,328,108),GOLD)
        mark(d,a,(170,62),66)
        rounded(d,(12,124,328,249),PEACH,RUST)
        place(image,'lantern-one',b,(130,184),size=(40,44),pitch=(48,49),columns=4)
        mark(d,b,(270,185),60,RUST)
        rounded(d,(12,264,328,394),MINT)
        stamp(image,'cloth-cover',(171,328),(238,115))
        mark(d,'?',(172,334),70,'#fff9eb')
    return image


def operator(draw,kind,x,y,radius,width):
    draw.line((x-radius,y,x+radius,y),fill=INK,width=width)
    if kind=='add':
        draw.line((x,y-radius,x,y+radius),fill=INK,width=width)


def answer_icon(kind,value=None):
    image,d=board((190,190))
    rounded(d,(4,4,185,185),'#fff9eb',INK,7)
    if value is None:
        operator(d,kind,95,93,49,13)
    else:
        d.ellipse((66,12,124,70),fill=GOLD,outline=INK,width=4)
        operator(d,kind,95,41,15,5)
        mark(d,value,(95,126),89,INK)
    return image


def family(a,b):
    total=a+b
    image,d=board()
    for y,label in ((83,f'{a}+{b}={total}'),(203,f'{total}-{b}={a}'),(323,f'{total}-{a}={b}')):
        rounded(d,(82,y-47,638,y+47),MINT)
        mark(d,label,(360,y),74)
    return image


def cover_scene():
    image=scene('lantern-room',(590,370))
    place(image,'lantern-one',6,(294,307),size=(52,60),pitch=(60,65),columns=6)
    return image


def quiz_visuals():
    for letter,focus in zip('abc',('left','whole','right')):
        yield f'q1-{letter}',two_groups(4,7,key='bead-one',focus=focus,label=False),['picture-check.q1'],['bead-one']
    for letter,(a,b) in zip('abc',((4,6),(5,7),(5,6))):
        yield f'q2-{letter}',two_groups(a,b,key='fan-one',label=False),['picture-check.q2'],['fan-one']
    for letter,n in zip('abc',(13,9,14)):
        yield f'q3-{letter}',whole(n,key='saucer-one'),['picture-check.q3'],['saucer-one']
    yield 'q4-stimulus',hidden(12,5,key='button-one'),['picture-check.q4'],['button-one','cloth-cover']
    for letter,n in zip('abc',(6,7,8)):
        yield f'q4-{letter}',whole(n,key='button-one'),['picture-check.q4'],['button-one']
    for letter,n in zip('abc',(9,6,15)):
        yield f'q5-{letter}',whole(n,key='strip-one'),['picture-check.q5'],['strip-one']
    for letter,n in zip('abc',(8,0,6)):
        yield f'q6-{letter}',whole(14,key='stamp-one',crossed=n),['picture-check.q6'],['stamp-one']


def visuals():
    yield 'lantern-cover',cover_scene(),['lantern-questions'],['lantern-room','lantern-one']
    yield 'sort-backdrop',scene('sorting-room',(416,234)),['choose-the-operation'],['sorting-room']
    yield 'marble-backdrop',scene('launch-room',(416,234)),['repair-the-model'],['launch-room']
    yield 'arriving-lights',two_groups(6,3,event='come'),['read-and-solve'],['lantern-one']
    yield 'check-nine',whole(9,crossed=3,label=True),['read-and-solve','connect-add-and-subtract'],['lantern-one']
    yield 'two-stands',two_groups(6,3),['same-addition-stories'],['lantern-one']
    yield 'lights-out',two_groups(3,6,event='out'),['same-addition-stories'],['lantern-one']
    yield 'remove-three',whole(9,crossed=3),['find-the-hidden-part'],['lantern-one']
    yield 'cover-three',hidden(9,6),['find-the-hidden-part'],['lantern-one','cloth-cover']
    yield 'family-diagram',family(6,3),['connect-add-and-subtract'],[]
    yield 'shipped-lights',two_groups(4,7,event='out'),['check-and-ask'],['lantern-one']
    yield 'ship-check',whole(11,crossed=4,label=True),['check-and-ask'],['lantern-one']
    yield 'twelve-remove',whole(12,crossed=8,label=True),['tell-a-new-story'],['lantern-one']
    yield 'twelve-hide',hidden(12,8),['tell-a-new-story'],['lantern-one','cloth-cover']
    for kind,a,b in SORT_MODELS:
        yield f'sort-{kind}-{a}-{b}',relation_icon(kind,a,b),['choose-the-operation'],[]
    yield 'dock-add',answer_icon('add'),['choose-the-operation'],[]
    yield 'dock-sub',answer_icon('sub'),['choose-the-operation'],[]
    for kind,a,b in LAUNCH_MODELS:
        yield f'model-{kind}-{a}-{b}',relation_icon(kind,a,b),['repair-the-model'],[]
        image = large_model(kind,a,b)
        parents=['lantern-one'] if kind=='add' else ['lantern-one','cloth-cover']
        yield f'large-{kind}-{a}-{b}',image,['repair-the-model'],parents
    for kind,n in (('add',8),('sub',5),('add',5),('add',10),('sub',8),('add',9),
                   ('add',12),('sub',9),('sub',12)):
        yield f'answer-{kind}-{n}',answer_icon(kind,n),['repair-the-model'],[]
    yield from quiz_visuals()


def render():
    digest=lambda p:sha256(p.read_bytes()).hexdigest()
    sources={}
    for receipt in sorted((ROOT/'art-source').glob('*.receipt.json')):
        for row in json.loads(receipt.read_text())['assets']:
            sources[row['assetKey']]={**row,'file':row['path'],'kind':'codex-builtin-imagegen'}
    for key,image,uses,parents in visuals():
        p=ASSETS/f'{key}.png'
        image.save(p,optimize=True)
        sources[key]={'file':p.relative_to(ROOT).as_posix(),'sha256':digest(p),
                      'kind':'deterministic-lesson-diagram','usedBy':uses,'source':'diagrams/render.py',
                      'sourceSha256':digest(Path(__file__)),'sourceAssets':{k:sources[k]['sha256'] for k in parents}}
    doc={'schemaVersion':'mira.courseware.asset-sources.v1','assets':sources}
    (ROOT/'asset-sources.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    render()
