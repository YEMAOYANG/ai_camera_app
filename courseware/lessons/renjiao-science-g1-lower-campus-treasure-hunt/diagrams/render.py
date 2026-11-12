"""Render fixed campus positions, two cameras of each doorway, and route exercises."""
from functools import lru_cache
from hashlib import sha256
from math import atan2, cos, sin
from pathlib import Path
import json

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'assets'
PAPER, CREAM, MINT='#fff3dc','#f6dfb7','#e2ebcf'
INK, GREEN, RUST='#24473b','#4e735b','#ad4935'
FONT='/System/Library/Fonts/Hiragino Sans GB.ttc'
VECTORS={'北':(0,-1),'东':(1,0),'南':(0,1),'西':(-1,0)}
ROTATION={'北':0,'东':-90,'南':180,'西':90}
ROOMS={
    'reading': {'x':165,'door':'door-green','symbol':'blue-book','neighbor':'ochre-bench','offset':-58,'color':'#7d9d7b'},
    'music': {'x':349,'door':'door-gold','symbol':'plum-drum','neighbor':'pot-plant','offset':58,'color':'#d9ab52'},
    'studio': {'x':533,'door':'door-red','symbol':'wood-palette','neighbor':'notice-board','offset':58,'color':'#ca795b'},
}
TEACH_SPOTS={'pot-plant':(0,2),'ochre-bench':(3,2),'blue-book':(3,0),'blue-bucket':(3,3)}
TEACH_ROUTE=[((0,2),(3,2)),((3,2),(3,0))]
QUIZ_SPOTS={'campus-flag':(1,3),'wind-chime':(1,1),'notice-board':(3,1),'plum-drum':(3,3)}
QUIZ_ROUTE=[((1,3),(1,1)),((1,1),(3,1))]


def difference(face, target):
    fx,fy=VECTORS[face]
    return (fx*target[0]+fy*target[1], -fy*target[0]+fx*target[1])


def board(size=(680,420),color=PAPER):
    im=Image.new('RGBA',size,color)
    return im,ImageDraw.Draw(im)


@lru_cache
def font(size):
    return ImageFont.truetype(FONT,size)


def text(d,value,xy,size=30,color=INK):
    d.text(xy,str(value),font=font(size),fill=color,anchor='mm')


@lru_cache
def art(key):
    with Image.open(ASSETS/f'{key}.png') as src:
        im=src.convert('RGBA')
    m=im.getchannel('A').point(lambda a:255 if a>=16 else 0).getbbox()
    return im.crop(m)


@lru_cache
def sprite(key,size,angle=0):
    im=art(key).rotate(angle,expand=True)
    im.thumbnail(size,Image.Resampling.LANCZOS)
    return im


def stamp(im,key,point,size,angle=0,ground=False):
    source=sprite(key,size,angle)
    x,y=map(round,point)
    im.alpha_composite(source,(x-source.width//2,y-(source.height if ground else source.height//2)))


def background(key,size=(416,234)):
    return ImageOps.fit(art(key).convert('RGB'),size,Image.Resampling.LANCZOS).convert('RGBA')


def panel(d,box,color=CREAM,outline=GREEN,width=4,radius=14):
    d.rounded_rectangle(box,radius,fill=color,outline=outline,width=width)


def circle(d,xy,r,fill,outline=None,width=3):
    x,y=xy
    d.ellipse((x-r,y-r,x+r,y+r),fill,outline,width)


def arrow(d,a,b,color=RUST,width=8):
    ang=atan2(b[1]-a[1],b[0]-a[0]); head=2.7*width
    d.line((*a,*b),fill=color,width=width)
    d.polygon([b,*[(b[0]-head*cos(ang+t),b[1]-head*sin(ang+t)) for t in (-.5,.5)]],fill=color)


def compass(d,xy,size=45,marks=VECTORS,letter_size=24):
    x,y=xy
    for key,(dx,dy) in VECTORS.items():
        arrow(d,xy,(x+dx*size*.63,y+dy*size*.63),INK,max(2,size//11))
        if key in marks: text(d,key,(x+dx*size,y+dy*size),letter_size)
    circle(d,xy,size//10,RUST)


def compass_badge():
    im=Image.new('RGBA',(196,196));d=ImageDraw.Draw(im)
    panel(d,(5,5,190,190),'#fff0cd',width=5)
    compass(d,(97,97),63,letter_size=34)
    return im


def child(im,d,who,point,face,r=37):
    circle(d,point,r,MINT,GREEN,4)
    stamp(im,who,point,(r+13,r+24),ROTATION[face])
    x,y=point; dx,dy=VECTORS[face]
    arrow(d,(x+dx*(r-3),y+dy*(r-3)),(x+dx*(r+33),y+dy*(r+33)),width=7)


def doorway(room,view):
    im,d=board()
    chosen=ROOMS[room]
    panel(d,(17,22,662,397),MINT)
    if view=='top':
        compass(d,(50,348),24,letter_size=18)
        panel(d,(89,242,647,369),'#f0d3a2','#b48865')
        for token,entry in ROOMS.items():
            x=entry['x']; marked=token==room
            panel(d,(x-75,78,x+75,241),entry['color'],RUST if marked else GREEN,7 if marked else 4)
            panel(d,(x-35,225,x+35,260),'#fff4d4',RUST if marked else GREEN,4,radius=5)
            stamp(im,entry['symbol'],(x,158),(99,90))
        x=chosen['x']
        circle(d,(x,341),17,'#dbb161',RUST,3)
        arrow(d,(x,321),(x,272),width=8)
        stamp(im,chosen['neighbor'],(x+chosen['offset'],302),(64,60))
    else:
        panel(d,(21,45,656,323),'#e3c2a1','#b48865')
        d.rectangle((22,322,655,392),fill='#eecb9d')
        d.line((23,322,653,322),fill='#bc8b64',width=5)
        for token,entry in ROOMS.items():
            x=entry['x']; marked=token==room
            if marked: panel(d,(x-76,56,x+76,319),'#f8d39b',RUST,6)
            stamp(im,entry['door'],(x,311),(123,163),ground=True)
            stamp(im,entry['symbol'],(x,111),(81,67))
        x=chosen['x']
        stamp(im,chosen['neighbor'],(x+chosen['offset'],359),(78,65),ground=True)
        circle(d,(x,359),16,'#dbb161',RUST,3)
    return im


def camera_cover():
    im,d=board((804,354))
    for i,kind in enumerate(('top','front')):
        pic=doorway('reading',kind);pic.thumbnail((369,270),Image.Resampling.LANCZOS)
        x=12+400*i
        panel(d,(x,57,x+379,336),CREAM)
        im.alpha_composite(pic,(x+5,76))
        stamp(im,'campus-camera',(x+190,28),(53,53))
    return im


def campus_map(spots,segments=(),*, extra=(), start=None):
    im,d=board()
    panel(d,(17,17,663,403),MINT,'#7e9475')
    compass(d,(91,89),45,letter_size=26)
    def xy(point): return 167+point[0]*105,68+point[1]*94
    for r in range(4):
        for c in range(5):
            x,y=xy((c,r))
            panel(d,(x-50,y-41,x+50,y+42),'#f5e4be','#ddc69e',2,radius=10)
    for a,b in segments:
        x,y=xy(a);xx,yy=xy(b);dx,dy=xx-x,yy-y
        arrow(d,(x+.19*dx,y+.19*dy),(xx-.2*dx,yy-.2*dy),width=11)
    for key,pos in spots.items():
        stamp(im,key,xy(pos),(79,72))
    if start is not None:
        c,r=start; x,y=xy((c,r))
        circle(d,(x,y+35),11,RUST,'#f7dfa9',2)
    for who,pos,face in extra:
        child(im,d,who,xy(pos),face)
    return im


def ambiguous():
    points={'blue-book':(0,1),'plum-drum':(4,1),'pot-plant':(2,2)}
    return campus_map(points,extra=[('green-child',(1,1),'西'),('gold-child',(3,1),'东')])


def clue_steps():
    im,d=board((740,390))
    for index,part in enumerate(['pot-plant',None,'ochre-bench','blue-book']):
        x=20+181*index
        panel(d,(x,45,x+159,328),CREAM)
        if part: stamp(im,part,(x+80,189),(106,108))
        else:
            arrow(d,(x+29,152),(x+126,152),width=11)
            for mark in range(3): circle(d,(x+45+36*mark,229),9,INK)
        text(d,index+1,(x+80,295),36)
    return im


def natural_set():
    im,d=board((735,340))
    for i,key in enumerate(('moss-trunk','sunflower-heads','snow-slopes')):
        x=17+240*i
        panel(d,(x,31,x+220,305),MINT)
        stamp(im,key,(x+110,168),(193,206))
    return im


def tool_card(kind='both'):
    im,d=board((425,280))
    panel(d,(11,11,414,269),CREAM)
    if kind=='both':
        stamp(im,'brass-compass',(108,132),(156,217))
        compass(d,(108,151),44,letter_size=23)
        stamp(im,'folded-plan',(301,151),(168,143))
        compass(d,(301,150),44,letter_size=23)
    else:
        stamp(im,kind,(215,141),(259,220))
    return im


def icon(key):
    im,d=board((315,230));panel(d,(12,12,303,218),CREAM)
    stamp(im,key,(156,114),(182,166))
    return im


def complete_clue(option):
    im,d=board((390,255))
    panel(d,(14,14,375,241),MINT)
    if option in ('a','b'):
        circle(d,(193,145),66,'#f5dfb5','#c39b66',4)
        circle(d,(148,171),17,RUST,'#ffefca',3)
    if option=='b':
        child(im,d,'green-child',(211,148),'北',37)
    if option=='c':
        child(im,d,'green-child',(119,153),'北',37)
        child(im,d,'gold-child',(271,106),'南',37)
    return im


def treasure_position(place):
    im,d=board()
    panel(d,(18,18,662,402),MINT)
    panel(d,(167,92,510,320),'#e0bc86','#aa8159',5)
    stamp(im,'pot-plant',(573,203),(112,147))
    stamp(im,'treasure-tin',place,(109,82))
    return im


def visuals():
    door_parents=[e[k] for e in ROOMS.values() for k in ('door','symbol','neighbor')]
    yield 'campus-opening',background('school-walkway',(700,444)),['one-clue-two-possibilities'],['school-walkway']
    yield 'ambiguous-faces',ambiguous(),['one-clue-two-possibilities'],['green-child','gold-child','blue-book','plum-drum','pot-plant']
    yield 'maze-background',background('tile-backdrop'),['draw-then-drive'],['tile-backdrop']
    yield 'camera-background',background('cork-backdrop'),['verify-the-door'],['cork-backdrop']
    yield 'maze-compass',compass_badge(),['draw-then-drive'],[]
    yield 'clue-sequence',clue_steps(),['mark-the-route-first'],['pot-plant','ochre-bench','blue-book']
    yield 'teaching-map',campus_map(TEACH_SPOTS,TEACH_ROUTE,start=(0,2)),['mark-the-route-first','retrace-and-fix'],list(TEACH_SPOTS)
    yield 'wrong-map',campus_map(TEACH_SPOTS,[TEACH_ROUTE[0],((3,2),(3,3))],start=(0,2)),['retrace-and-fix'],list(TEACH_SPOTS)
    yield 'door-camera-cover',camera_cover(),['verify-the-door'],[*door_parents,'campus-camera']
    for room in ROOMS:
        for view in ('top','front'):
            yield f'checkpoint-{view}-{room}',doorway(room,view),['verify-the-door','compare-checkpoint'],door_parents
    yield 'natural-clues',natural_set(),['five-direction-clues'],['moss-trunk','sunflower-heads','snow-slopes']
    yield 'direction-tools',tool_card(),['five-direction-clues'],['brass-compass','folded-plan']
    yield 'family-map',campus_map({'campus-flag':(1,3),'pot-plant':(1,1),'treasure-tin':(3,1)},[((1,3),(1,1)),((1,1),(3,1))]),['make-your-own-clue'],['campus-flag','pot-plant','treasure-tin']
    quiz1={'notice-board':(2,1),'pot-plant':(4,0)}
    for letter,position,face in [('a',(2,2),'东'),('b',(2,2),'西'),('c',(4,1),'西')]:
        yield 'q1-'+letter,campus_map(quiz1,extra=[('green-child',position,face)]),['picture-quiz'],[*quiz1,'green-child']
    yield 'q2-stimulus',campus_map(QUIZ_SPOTS,start=(1,3)),['picture-quiz'],list(QUIZ_SPOTS)
    for letter,route in [('a',QUIZ_ROUTE),('b',[((1,3),(3,3)),((3,3),(3,1))]),('c',[((1,3),(1,1)),((1,1),(0,1))])]:
        yield 'q2-'+letter,campus_map(QUIZ_SPOTS,route,start=(1,3)),['picture-quiz'],list(QUIZ_SPOTS)
    quiz3={'wood-palette':(2,0),'blue-bucket':(0,2),'wind-chime':(4,2)}
    yield 'q3-stimulus',campus_map(quiz3,extra=[('gold-child',(2,2),'西')]),['picture-quiz'],[*quiz3,'gold-child']
    for letter,key in zip('abc',('blue-bucket','wind-chime','wood-palette')):
        yield 'q3-'+letter,icon(key),['picture-quiz'],[key]
    for letter,parents in [('a',[]),('b',['green-child']),('c',['green-child','gold-child'])]:
        yield 'q4-'+letter,complete_clue(letter),['picture-quiz'],parents
    for letter,pos in zip('abc',((221,205),(343,130),(450,203))):
        yield 'q5-'+letter,treasure_position(pos),['picture-quiz'],['pot-plant','treasure-tin']
    for letter,kind in zip('abc',('both','moss-trunk','snow-slopes')):
        keys=['brass-compass','folded-plan'] if kind=='both' else [kind]
        yield 'q6-'+letter,tool_card(kind),['picture-quiz'],keys


def render():
    def digest(p):
        return sha256(p.read_bytes()).hexdigest()
    sources={}
    for receipt in sorted((ROOT/'art-source').glob('*.receipt.json')):
        for a in json.loads(receipt.read_text())['assets']:
            sources[a['assetKey']]={**a,'file':a['path'],'kind':'codex-builtin-imagegen'}
    for key,im,uses,parents in visuals():
        p=ASSETS/f'{key}.png';im.save(p,optimize=True)
        sources[key]={'file':p.relative_to(ROOT).as_posix(),'sha256':digest(p),
                      'kind':'deterministic-lesson-diagram','usedBy':uses,'source':'diagrams/render.py',
                      'sourceSha256':digest(Path(__file__)),'sourceAssets':{a:sources[a]['sha256'] for a in sorted(parents)}}
    (ROOT/'asset-sources.json').write_text(json.dumps({'schemaVersion':'mira.courseware.asset-sources.v1','assets':sources},ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    render()
