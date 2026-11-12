"""Compose original whole-plant, branch, and evidence-card pictures."""
from functools import lru_cache
from hashlib import sha256
from math import cos, pi, sin
from pathlib import Path
import json

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'assets'
PAPER, CREAM, MINT='#fff4dd','#f4dfb9','#dfeacb'
INK, GREEN, RUST='#26483b','#567451','#a44730'
FONT='/System/Library/Fonts/Hiragino Sans GB.ttc'
BRANCHES={'jasmine':('jasmine-top','jasmine-side'),'forsythia':('forsythia-top','forsythia-side'),
          'willow':('willow-top','willow-profile')}
PETAL_COUNTS={'jasmine':6,'forsythia':4}
WHOLE={'jasmine':'whole-jasmine','forsythia':'whole-forsythia','willow':'whole-willow','pine':'whole-pine'}


def board(size=(692,413)):
    im=Image.new('RGBA',size,PAPER)
    return im,ImageDraw.Draw(im)


@lru_cache
def font(size):
    return ImageFont.truetype(FONT,size)


def text(d,value,point,size=28):
    d.text(point,value,font=font(size),fill=INK,anchor='mm')


def panel(d,box,fill=MINT,outline=GREEN,width=4):
    d.rounded_rectangle(box,16,fill=fill,outline=outline,width=width)


@lru_cache
def art(key):
    path=ROOT/'art-source/campus-willow-profile.png' if key=='willow-profile' else ASSETS/f'{key}.png'
    with Image.open(path) as source:
        im=source.convert('RGBA')
    bbox=im.getchannel('A').point(lambda v:255 if v>=16 else 0).getbbox()
    return im.crop(bbox)


@lru_cache
def sprite(key,box,angle=0):
    im=art(key).copy()
    im.thumbnail(box,Image.Resampling.LANCZOS)
    return im.rotate(angle,Image.Resampling.BICUBIC,expand=True) if angle else im


def place(im,key,point,box,angle=0):
    x,y=point;pic=sprite(key,box,angle)
    im.alpha_composite(pic,(x-pic.width//2,y-pic.height//2))


def background(key,size=(416,234)):
    return ImageOps.fit(art(key).convert('RGB'),size,Image.Resampling.LANCZOS).convert('RGBA')


def gallery(keys,cols=None,size=(700,415)):
    im,d=board(size);cols=cols or len(keys)
    rows=(len(keys)+cols-1)//cols
    w,h=(size[0]-32)//cols,(size[1]-25)//rows
    for i,key in enumerate(keys):
        start=i//cols*cols
        row_offset=(cols-min(len(keys)-start,cols))*w//2
        x,y=16+row_offset+i%cols*w,13+i//cols*h
        panel(d,(x,y,x+w-8,y+h-8))
        place(im,key,(x+(w-8)//2,y+(h-8)//2),(w-22,h-30))
    return im


def branch_card(key,side=False):
    im,d=board((604,349))
    panel(d,(14,15,589,334))
    if side:
        d.line((62,264,541,264),fill='#987e65',width=6)
        place(im,key,(302,163),(486,194))
    else:
        place(im,key,(302,171),(488,260))
    return im


def photo_cover():
    im,d=board((790,362))
    for i,key in enumerate(BRANCHES['jasmine']):
        x=12+389*i
        panel(d,(x,58,x+373,344))
        pic=branch_card(key,i==1);pic.thumbnail((346,272),Image.Resampling.LANCZOS)
        im.alpha_composite(pic,(x+13,92))
        place(im,'campus-plant-camera',(x+186,30),(52,47))
    return im


def petal_positions(count,center,radius):
    x,y=center
    return [(round(x+radius*sin(i*2*pi/count)),round(y-radius*cos(i*2*pi/count)),round(-i*360/count))
            for i in range(count)]


def flower(im,d,sample,center,radius):
    count=PETAL_COUNTS[sample]
    size=(round(radius*.96),round(radius*1.54)) if sample=='jasmine' else (round(radius*.73),round(radius*1.72))
    for x,y,angle in petal_positions(count,center,radius):
        place(im,'single-yellow-petal',(x,y),size,angle)
    x,y=center;r=max(6,radius//5)
    d.ellipse((x-r,y-r,x+r,y+r),fill='#b57128',outline=RUST,width=2)


def yellow_comparison():
    im,d=board((760,425))
    for i,sample in enumerate(('jasmine','forsythia')):
        x=12+377*i
        panel(d,(x,13,x+361,406))
        place(im,WHOLE[sample],(x+180,104),(244,159))
        d.line((x+28,200,x+332,200),fill='#a5a886',width=4)
        flower(im,d,sample,(x+181,300),48)
    return im


def whole_detail(tree='willow',detail=None):
    im,d=board((748,394))
    panel(d,(12,16,360,375))
    panel(d,(381,16,734,375))
    place(im,WHOLE[tree],(185,192),(302,298))
    detail=detail or {'willow':'willow-top','pine':'pine-bark'}[tree]
    place(im,detail,(547,178),(250,211))
    place(im,'plant-lens',(634,289),(96,90))
    return im


def record_card():
    im,d=board((785,415))
    place(im,'plant-notebook',(393,205),(762,397))
    place(im,'whole-jasmine',(246,171),(245,174))
    place(im,'jasmine-top',(532,159),(211,153))
    flower(im,d,'jasmine',(536,257),25)
    text(d,'迎春', (243,298),36)
    return im


def sign(plant,detail=None,caption=None):
    im,d=board((620,397))
    panel(d,(13,14,608,382))
    place(im,'plant-sign',(304,198),(501,357))
    place(im,WHOLE[plant],(219,122),(125,90))
    if detail:
        place(im,detail,(381,122),(117,84))
    if caption:
        text(d,caption,(303,180),27)
    return im


def clue(key):
    if key in ('jasmine','forsythia'):
        im,d=board((194,163))
        panel(d,(3,4,190,159),CREAM)
        flower(im,d,key,(97,79),32)
        return im
    return gallery(['willow-top' if key=='willow' else 'pine-bark'],size=(194,163))


def paired_flowers(include='full'):
    im,d=board((738,386))
    for i,key in enumerate(('jasmine','forsythia')):
        x=12+367*i
        panel(d,(x,17,x+347,365))
        if include=='full':
            place(im,BRANCHES[key][0],(x+174,120),(276,148))
            flower(im,d,key,(x+174,270),43)
        elif include=='whole':
            place(im,WHOLE[key],(x+174,189),(285,266))
        else:
            d.ellipse((x+110,124,x+238,252),fill='#e9b92b',outline='#b78e29',width=3)
    return im


def visuals():
    yield 'campus-cover',background('school-plant-path',(696,437)),['school-plant-walk'],['school-plant-path']
    walk=['whole-dandelion','whole-jasmine','whole-forsythia','whole-willow','whole-pine']
    yield 'campus-variety',gallery(walk,3),['school-plant-walk'],walk
    yield 'two-yellow-plants',yellow_comparison(),['same-yellow-different'],['whole-jasmine','whole-forsythia','single-yellow-petal']
    yield 'whole-willow-detail',whole_detail(),['whole-then-detail'],['whole-willow','willow-top','plant-lens']
    yield 'pine-whole-bark',whole_detail('pine'),['rub-the-bark'],['whole-pine','pine-bark','plant-lens']
    yield 'bark-steps',gallery(['paper-on-bark','crayon-side','bark-print']),['rub-the-bark'],['paper-on-bark','crayon-side','bark-print']
    yield 'plant-photo-start',photo_cover(),['campus-plant-photos'],[*BRANCHES['jasmine'],'campus-plant-camera']
    yield 'cork-background',background('plant-cork'),['campus-plant-photos'],['plant-cork']
    yield 'garden-background',background('school-plant-path'),['match-plant-evidence'],['school-plant-path']
    for k,pair in BRANCHES.items():
        for view,name in zip(('top','side'),pair):
            yield f'plant-{view}-{k}',branch_card(name,view=='side'),['campus-plant-photos'],[name]
    for key in WHOLE:
        parents=['single-yellow-petal'] if key in PETAL_COUNTS else ['willow-top' if key=='willow' else 'pine-bark']
        yield 'clue-'+key,clue(key),['match-plant-evidence'],parents
    yield 'report-card',record_card(),['report-what-you-saw'],['plant-notebook','whole-jasmine','jasmine-top','single-yellow-petal']
    yield 'garden-care',gallery(['campus-gardener','tended-path']),['meet-the-gardener'],['campus-gardener','tended-path']
    yield 'willow-sign',sign('willow','willow-top','柳树  枝条下垂'),['make-a-plant-sign'],['plant-sign','whole-willow','willow-top']
    yield 'home-record',whole_detail('willow'),['home-plant-observation'],['whole-willow','willow-top','plant-lens']
    for c,key in zip('abc',('willow-top','whole-willow','pine-bark')):
        yield 'q1-'+c,gallery([key]),['picture-quiz'],[key]
    for c,mode,parents in [('a','full',['jasmine-top','forsythia-top','single-yellow-petal']),
                           ('b','color',[]),('c','whole',['whole-jasmine','whole-forsythia'])]:
        yield 'q2-'+c,paired_flowers(mode),['picture-quiz'],parents
    for c,keys in [
        ('a',['bark-print','crayon-side','paper-on-bark']),
        ('b',['paper-on-bark','bark-print','crayon-side']),
        ('c',['paper-on-bark','crayon-side','bark-print']),
    ]:
        yield 'q3-'+c,gallery(keys,3,(780,368)),['picture-quiz'],keys
    yield 'q4-stimulus',branch_card('willow-profile',True),['picture-quiz'],['willow-profile']
    for c,key in zip('abc',('whole-pine','whole-willow','whole-jasmine')):
        yield 'q4-'+c,gallery([key]),['picture-quiz'],[key]
    for c,keys in [('a',['whole-pine']),('b',['pine-bark']),('c',['whole-pine','pine-bark'])]:
        yield 'q5-'+c,gallery(keys),['picture-quiz'],keys
    for c,key,detail,caption in [('a','pine','pine-bark','松树  树皮有纹路'),('b','pine',None,None),('c','pine','oval-sprig','松树  叶宽圆')]:
        yield 'q6-'+c,sign(key,detail,caption),['picture-quiz'],['plant-sign',WHOLE[key],*([detail] if detail else [])]


def render():
    def digest(p):
        return sha256(p.read_bytes()).hexdigest()
    sources={}
    for receipt in sorted((ROOT/'art-source').glob('*.receipt.json')):
        for a in json.loads(receipt.read_text())['assets']:
            sources[a['assetKey']]={**a,'file':a['path'],'kind':'codex-builtin-imagegen'}
    profile=json.loads((ROOT/'art-source/campus-willow-profile.plan.json').read_text())
    profile_path=ROOT/profile['file']
    prompt_path=ROOT/profile['promptFile']
    sources['willow-profile']={**profile,'sha256':digest(profile_path),'promptSha256':digest(prompt_path)}
    for unused in ('whole-peony','willow-side'):
        sources[unused]['usedBy']=[]
    for key,im,uses,parents in visuals():
        p=ASSETS/f'{key}.png';im.save(p,optimize=True)
        sources[key]={'file':p.relative_to(ROOT).as_posix(),'sha256':digest(p),
                      'kind':'deterministic-lesson-diagram','usedBy':uses,'source':'diagrams/render.py',
                      'sourceSha256':digest(Path(__file__)),'sourceAssets':{a:sources[a]['sha256'] for a in sorted(parents)}}
    (ROOT/'asset-sources.json').write_text(json.dumps({'schemaVersion':'mira.courseware.asset-sources.v1','assets':sources},
                                                      ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    render()
