"""Build exact direction, shadow and route models from lesson-owned sprites."""
from functools import lru_cache
from hashlib import sha256
from math import atan2, cos, hypot, sin
from pathlib import Path
import json

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT/'assets'
INK, GREEN, RUST = '#213e34', '#3a6b5b', '#a43e2c'
PAPER, CREAM, MINT = '#fff4dc', '#f4dcb0', '#c7dfc4'
FONT = '/System/Library/Fonts/Hiragino Sans GB.ttc'
DIRECTIONS = {'北':(0,-1),'东':(1,0),'南':(0,1),'西':(-1,0)}
ROTATIONS = {'北':0,'东':-90,'南':180,'西':90}
CLOCKWISE = ('东','南','西','北')
LIGHTS = {'morning':(1.45,0,1.22),'noon-model':(0,1.15,2.37),'evening':(-1.45,0,1.22)}
PEG_HEIGHT = .63
COURT = {'wind-chime':(1.5,0),'elm-tree':(0,-1.23),'vermilion-bench':(0,1.23),'stone-stool':(-1.5,0)}


def shadow_end(lamp):
    x, y, z = lamp
    scale = -PEG_HEIGHT/(z-PEG_HEIGHT)
    return x*scale, y*scale


def relative(face, target):
    fx, fy = DIRECTIONS[face]
    x, y = DIRECTIONS[target]
    return (fx*x+fy*y, -fy*x+fx*y)


@lru_cache
def font(size):
    return ImageFont.truetype(FONT, size)


def label(d, text, point, size=29, color=INK):
    d.text(point,text,anchor='mm',font=font(size),fill=color)


def board(size=(680,452),color=PAPER):
    im=Image.new('RGBA',size,color)
    return im,ImageDraw.Draw(im)


@lru_cache
def art(key):
    with Image.open(ASSETS/f'{key}.png') as source:
        im=source.convert('RGBA')
    bounds=im.getchannel('A').point(lambda a:255 if a>=16 else 0).getbbox()
    return im.crop(bounds)


@lru_cache
def sprite(key, bounds, angle=0):
    im=art(key).rotate(angle,expand=True)
    im.thumbnail(bounds,Image.Resampling.LANCZOS)
    return im


def stamp(im,key,point,size,angle=0,ground=False):
    pic=sprite(key,size,angle)
    x,y=map(round,point)
    im.alpha_composite(pic,(x-pic.width//2,y-(pic.height if ground else pic.height//2)))


def background(key,size=(416,234)):
    return ImageOps.fit(art(key).convert('RGB'),size,Image.Resampling.LANCZOS).convert('RGBA')


def panel(d, box, color=CREAM, outline=GREEN, width=4):
    d.rounded_rectangle(box,radius=15,fill=color,outline=outline,width=width)


def circle(d, center, radius, fill, outline=None, width=3):
    x,y=center
    d.ellipse((x-radius,y-radius,x+radius,y+radius),fill,outline,width)


def arrow(d, a, b, color=RUST, width=8):
    theta=atan2(b[1]-a[1],b[0]-a[0]); tip=2.7*width
    d.line((*a,*b),fill=color,width=width)
    d.polygon([b,*[(b[0]-tip*cos(theta+t),b[1]-tip*sin(theta+t)) for t in (-.55,.55)]],fill=color)


def compass(d, center, unit, *, rotation=0, marks=DIRECTIONS, font_size=24, ink=INK):
    x,y=center
    projected=list(DIRECTIONS.values())
    for mark,(dx,dy) in zip(DIRECTIONS,projected[rotation:]+projected[:rotation]):
        arrow(d,(x,y),(x+dx*unit*.66,y+dy*unit*.66),ink,max(3,unit//10))
        if mark in marks:
            label(d,mark,(x+dx*unit,y+dy*unit),font_size,ink)
    circle(d,(x,y),unit*.12,RUST)


def compass_badge():
    im=Image.new('RGBA',(205,205))
    d=ImageDraw.Draw(im)
    panel(d,(5,5,199,199),'#fff0ce',GREEN,6)
    compass(d,(102,102),69,font_size=40)
    return im


def pupils(im,d,key,xy,face,radius=41):
    circle(d,xy,radius,MINT,GREEN,5)
    stamp(im,key,xy,(radius+12,radius+24),ROTATIONS[face])
    x,y=xy; fx,fy=DIRECTIONS[face]
    arrow(d,(x+fx*(radius-4),y+fy*(radius-4)),(x+fx*(radius+31),y+fy*(radius+31)))


def top_pos(p):
    x,y=p
    return 354+130*x,242+103*y


def side_pos(p):
    x,y=p
    return 346+126*x-104*y,317+24*x+54*y


def points_along_ray(d,a,b,color='#a37d4e',width=3):
    for i in range(0,12,2):
        mix=lambda n:tuple(x+(y-x)*n/12 for x,y in zip(a,b))
        d.line((*mix(i),*mix(i+1)),fill=color,width=width)


def gold_ball(im, xy, r):
    raw=art('yellow-ball')
    # The upper portion of the paper sprite is a wooden model ball. Its
    # center is placed by the diagram rather than inferred from a painting.
    ball=ImageOps.fit(raw.crop((0,0,raw.width,round(raw.height*.43))), (r*2,r*2), Image.Resampling.LANCZOS)
    mask=Image.new('L',ball.size); ImageDraw.Draw(mask).ellipse((0,0,2*r-1,2*r-1),fill=255)
    im.paste(ball,(round(xy[0]-r),round(xy[1]-r)),mask)


def shadow(d, a,b):
    color='#51474d'
    d.line((*a,*b),fill=color,width=20)
    circle(d,b,10,color)


def side_compass(d):
    center=(112,91)
    ox,oy=side_pos((0,0))
    for direction,unit in DIRECTIONS.items():
        x,y=side_pos(unit)
        scale=64/hypot(x-ox,y-oy)
        dx,dy=(x-ox)*scale,(y-oy)*scale
        arrow(d,center,(center[0]+dx*.74,center[1]+dy*.74),INK,4)
        label(d,direction,(center[0]+dx,center[1]+dy),23)
    circle(d,center,6,RUST)


def shadow_photo(phase, view, *, question=False):
    im,d=board()
    lamp=LIGHTS[phase]; src=lamp[:2]
    start=(0,0); end=shadow_end(lamp)
    if view=='top':
        panel(d,(35,45,646,424),'#efdcbf' if question else '#f1d8a8','#a17b59')
        compass(d,(553,119) if question else (102,106),52 if question else 43,font_size=27 if question else 23)
        if question:
            def project(pos): return 317+122*pos[0],266+92*pos[1]
        else:
            project=top_pos
        p=project(start); q=project(end); l=project(src)
        shadow(d,p,q)
        points_along_ray(d,l,p)
        circle(d,p,22,'#b17a39',INK,4)
        circle(d,p,9,'#f0b66b',INK,2)
        gold_ball(im,l,22)
    else:
        corners=[(-1.7,-1.15),(1.7,-1.15),(1.7,1.3),(-1.7,1.3)]
        d.polygon([side_pos(p) for p in corners],fill='#efcb97',outline='#9e775a',width=5)
        side_compass(d)
        p=side_pos(start); q=side_pos(end); l=side_pos(src)
        h=91
        emitter=(l[0],l[1]-h*lamp[2])
        tip=(p[0],p[1]-h*PEG_HEIGHT)
        shadow(d,p,q)
        points_along_ray(d,emitter,q)
        d.line((*l,*emitter),fill='#955a39',width=9)
        d.ellipse((l[0]-23,l[1]-7,l[0]+23,l[1]+7),fill='#a66041')
        stamp(im,'brass-peg',p,(38,74),ground=True)
        gold_ball(im,emitter,22)
        # Use the same model height for the visible peg top and its ray intersection.
        circle(d,tip,7,'#efb968',RUST,2)
    return im


def pair_cover():
    im,d=board((790,363))
    for i,view in enumerate(('top','side')):
        x=14+390*i
        panel(d,(x,54,x+374,347),CREAM)
        pic=shadow_photo('morning',view)
        pic.thumbnail((355,266),Image.Resampling.LANCZOS)
        im.alpha_composite(pic,(x+(374-pic.width)//2,80))
        stamp(im,'courtyard-camera',(x+187,31),(50,50))
    return im


def court_map(heading='东', *, second=False, fixed=COURT, highlighted=None, direction_labels=True):
    im,d=board()
    panel(d,(19,19,661,431),'#eef0ce','#789168')
    if direction_labels:
        compass(d,(104,105),48,font_size=25)
    for key,pos in fixed.items():
        loc=top_pos(pos)
        if key==highlighted: circle(d,loc,62,'#f9d78d',RUST,7)
        stamp(im,key,loc,(104,93))
    pupils(im,d,'green-pupil',top_pos((0,0)),heading)
    if second:
        pupils(im,d,'gold-pupil',top_pos((1.36,.75)),'西',32)
    return im


def direction_ring(start='东'):
    im,d=board()
    x,y=341,224
    circle(d,(x,y),144,'#e0ebce',GREEN,5)
    d.arc((x-116,y-116,x+116,y+116),-72,246,fill=RUST,width=9)
    arrow(d,(x-66,y-89),(x-39,y-111),width=8)
    compass(d,(x,y),97,font_size=48)
    fx,fy=DIRECTIONS[start]; center=(x+fx*97,y+fy*97)
    d.ellipse((center[0]-36,center[1]-36,center[0]+36,center[1]+36),outline=RUST,width=6)
    return im


def route_map(spots, segments=(), *, turn=0):
    im,d=board()
    panel(d,(17,17,663,435),'#e7ebc7','#789168')
    compass(d,(106,100),48,rotation=turn,font_size=26)
    base=(239,100)
    def xy(p):
        return base[0]+p[0]*165,base[1]+p[1]*125
    for c in range(3):
        for r in range(3):
            a=xy((c,r))
            for dest in [(c+1,r),(c,r+1)]:
                if max(dest)<3:
                    b=xy(dest)
                    d.line((*a,*b),fill='#b8b995',width=33)
                    d.line((*a,*b),fill='#fff1ce',width=23)
    for a,b in segments:
        x,y=xy(a); xx,yy=xy(b)
        dx,dy=xx-x,yy-y
        arrow(d,(x+.23*dx,y+.23*dy),(xx-.22*dx,yy-.22*dy),width=13)
    for key,pos in spots.items():
        p=xy(pos)
        circle(d,p,43,'#fff2d5',GREEN,3)
        stamp(im,key,p,(81,78))
    return im


def item_card(key):
    im,d=board((320,235)); panel(d,(15,12,305,223),CREAM)
    stamp(im,key,(160,118),(180,180))
    return im


def safety(pose,*,teaching=False):
    im,d=board((360,270));panel(d,(12,10,348,260),'#f3e5bd' if teaching else '#e8ebce')
    d.line((30,219,330,219),fill=GREEN,width=6)
    peg=285 if teaching else 268
    shadow(d,(peg,219),(205,219))
    stamp(im,'brass-peg',(peg,222),(38,95),ground=True)
    stamp(im,pose,(135,218),(178,170),ground=True)
    if pose=='child-up':
        circle(d,(295,45),22,'#eeb558',RUST)
    return im


def cycle_challenge():
    props={'blue-bucket':(-1.4,0),'wind-chime':(1.45,0),'vermilion-bench':(0,1.2)}
    im=court_map('南',fixed=props);d=ImageDraw.Draw(im)
    d.arc((258,146,450,338),89,167,fill=RUST,width=9)
    arrow(d,(270,281),(259,257),width=7)
    return im


def visuals():
    keys=list(COURT)
    model=['brass-peg','yellow-ball']
    yield 'yard-opening',background('gate-scene',(690,460)),['same-place-different-views'],['gate-scene']
    yield 'yard-two-pupils',court_map(second=True),['same-place-different-views'],['green-pupil','gold-pupil',*keys]
    yield 'photo-backdrop',background('photo-paper'),['direction-photo-pairs'],['photo-paper']
    yield 'maze-backdrop',background('garden-paper'),['follow-cardinal-route'],['garden-paper']
    yield 'compass-badge',compass_badge(),['follow-cardinal-route'],[]
    yield 'fixed-clock',direction_ring(),['classroom-directions'],[]
    yield 'model-safety',safety('child-shadow',teaching=True),['model-noon-and-safety'],['child-shadow','brass-peg']
    yield 'photo-cover',pair_cover(),['direction-photo-pairs'],[*model,'courtyard-camera']
    for phase in LIGHTS:
        for view in ('top','side'):
            yield f'shadow-{view}-{phase}',shadow_photo(phase,view),['three-times-model','direction-photo-pairs'],model
    for head,suffix in [('东','east'),('南','south'),('西','west')]:
        yield 'court-'+suffix,court_map(head),['three-model-facings','record-at-one-station'],['green-pupil',*keys]
    learn={'red-pennant':(1,2),'elm-tree':(1,1),'stone-bridge':(0,1)}
    yield 'route-start',route_map(learn),['read-the-direction-mark','follow-cardinal-route'],list(learn)
    yield 'route-trace',route_map(learn,[((1,2),(1,1)),((1,1),(0,1))]),['read-the-direction-mark'],list(learn)
    yield 'rotated-compass',route_map(learn,turn=1),['read-the-direction-mark'],list(learn)
    yield 'family-practice',court_map('南',highlighted='vermilion-bench'),['apply-at-home'],['green-pupil',*keys]
    for letter,phase in zip('abc',('evening','morning','noon-model')):
        yield 'q1-'+letter,shadow_photo(phase,'top',question=True),['picture-quiz'],model
    for letter,key in zip('abc',('child-shadow','child-up','child-book')):
        yield 'q2-'+letter,safety(key),['picture-quiz'],[key,'brass-peg']
    opposite={'garden-gazebo':(1.5,0),'stone-bridge':(-1.5,0),'blue-bucket':(0,-1.22),'stone-stool':(0,1.22)}
    yield 'q3-stimulus',court_map('东',fixed=opposite),['picture-quiz'],['green-pupil',*opposite]
    for letter,key in zip('abc',('blue-bucket','garden-gazebo','stone-bridge')):
        yield 'q3-'+letter,item_card(key),['picture-quiz'],[key]
    yield 'q4-stimulus',cycle_challenge(),['picture-quiz'],['green-pupil','blue-bucket','wind-chime','vermilion-bench']
    for letter,key in zip('abc',('wind-chime','blue-bucket','vermilion-bench')):
        yield 'q4-'+letter,item_card(key),['picture-quiz'],[key]
    yield 'q5-stimulus',court_map('东',fixed={'oval-pond':(0,-1.25)}),['picture-quiz'],['green-pupil','oval-pond']
    for letter,pos in zip('abc',((0,1.24),(-1.5,0),(0,-1.24))):
        yield 'q5-'+letter,court_map('西',fixed={'oval-pond':pos}),['picture-quiz'],['green-pupil','oval-pond']
    quiz={'red-gate':(0,2),'oval-pond':(0,1),'garden-gazebo':(1,1),'vermilion-bench':(1,2)}
    yield 'q6-stimulus',route_map(quiz),['picture-quiz'],list(quiz)
    routes=[
        [((0,2),(0,1)),((0,1),(1,1))],
        [((0,2),(1,2)),((1,2),(1,1))],
        [((0,2),(1,2)),((1,2),(2,2))],
    ]
    for letter,segments in zip('abc',routes):
        yield 'q6-'+letter,route_map(quiz,segments),['picture-quiz'],list(quiz)


def render():
    def digest(path):
        return sha256(path.read_bytes()).hexdigest()
    sources={}
    for receipt in sorted((ROOT/'art-source').glob('*.receipt.json')):
        for entry in json.loads(receipt.read_text())['assets']:
            sources[entry['assetKey']]={**entry,'file':entry['path'],'kind':'codex-builtin-imagegen'}
    for key,im,uses,parents in visuals():
        path=ASSETS/f'{key}.png';im.save(path,optimize=True)
        sources[key]={'file':path.relative_to(ROOT).as_posix(),'sha256':digest(path),
                      'kind':'deterministic-lesson-diagram','usedBy':uses,'source':'diagrams/render.py',
                      'sourceSha256':digest(Path(__file__)),
                      'sourceAssets':{p:sources[p]['sha256'] for p in parents}}
    (ROOT/'asset-sources.json').write_text(json.dumps({'schemaVersion':'mira.courseware.asset-sources.v1','assets':sources},
                                                      ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    render()
