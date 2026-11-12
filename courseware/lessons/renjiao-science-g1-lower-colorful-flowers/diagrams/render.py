"""Compose the registered flower specimens, shape analogies and drawing exercises."""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import json

from PIL import Image, ImageDraw, ImageOps

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'assets'
PAPER, CREAM, MINT='#fff4df','#f4dfbe','#ddebcf'
INK, GREEN, RUST='#26483c','#567854','#a64537'
PHOTOS={'trumpet':('glory-top','glory-side'),'cross':('cress-top','cress-side'),'peach':('peach-top','peach-side')}
SHAPES={'trumpet':'glory-side','cross':'cress-top','bell':'golden-bell','butterfly':'pea-flower'}


def board(size=(680,414)):
    im=Image.new('RGBA',size,PAPER)
    return im,ImageDraw.Draw(im)


def panel(d,rect,fill=MINT,outline=GREEN,width=4):
    d.rounded_rectangle(rect,17,fill=fill,outline=outline,width=width)


@lru_cache
def art(key):
    with Image.open(ASSETS/f'{key}.png') as opened:
        im=opened.convert('RGBA')
    bounds=im.getchannel('A').point(lambda a:255 if a>=16 else 0).getbbox()
    return im.crop(bounds)


@lru_cache
def sprite(key,size,angle=0):
    im=art(key).rotate(angle,expand=True)
    im.thumbnail(size,Image.Resampling.LANCZOS)
    return im


def place(im,key,center,size,angle=0,ground=False):
    pic=sprite(key,size,angle);x,y=center
    im.alpha_composite(pic,(x-pic.width//2,y-(pic.height if ground else pic.height//2)))
    return pic.size


def background(key,size=(416,234)):
    return ImageOps.fit(art(key).convert('RGB'),size,Image.Resampling.LANCZOS).convert('RGBA')


def grid(keys,cols=None,size=(680,414)):
    im,d=board(size)
    cols=cols or len(keys)
    rows=(len(keys)+cols-1)//cols
    w,h=(size[0]-30)//cols,(size[1]-28)//rows
    for i,key in enumerate(keys):
        x,y=16+(i%cols)*w,13+(i//cols)*h
        panel(d,(x,y,x+w-8,y+h-8))
        place(im,key,(x+(w-8)//2,y+(h-8)//2),(w-27,h-34))
    return im


def framed(key,side=False,angle=0):
    im,d=board((596,362))
    panel(d,(14,14,581,347))
    if side:
        d.line((78,291,517,291),fill='#b69778',width=5)
        place(im,key,(297,282),(383,241),ground=True)
    else:
        place(im,key,(298,182),(402,278),angle=angle)
    return im


def pair_cover():
    im,d=board((790,365))
    for i,key in enumerate(PHOTOS['trumpet']):
        x=12+i*389
        panel(d,(x,58,x+375,346))
        pic=framed(key,side=i==1);pic.thumbnail((348,269),Image.Resampling.LANCZOS)
        im.alpha_composite(pic,(x+13,94))
        place(im,'flower-camera',(x+188,31),(56,50))
    return im


def round_mark(d,xy,r,outline=RUST,width=7):
    x,y=xy;d.ellipse((x-r,y-r,x+r,y+r),outline=outline,width=width)


def flower_mark(key,mark):
    im,d=board()
    panel(d,(17,18,661,398))
    x,y=338,210
    w,h=place(im,key,(x,y),(391,324))
    spots={'center':(x,y),'petal':(x-int(w*.26),y-int(h*.17)),'gap':(x+int(w*.46),y-int(h*.3))}
    round_mark(d,spots[mark],57 if mark=='center' else 44)
    return im


def draw_cross(d,center,r,parts='all'):
    x,y=center
    if parts in ('outline','all'):
        for dx,dy in [(0,-1),(1,0),(0,1),(-1,0)]:
            cx,cy=x+dx*r*.58,y+dy*r*.58
            w,h=(r*.47,r*.28) if dx else (r*.28,r*.47)
            d.ellipse((cx-w,cy-h,cx+w,cy+h),outline=INK,width=5)
    if parts in ('center','all'):
        round_mark(d,center,max(5,r//10),INK,5)
        for dx,dy in [(1,1),(-1,1),(-1,-1),(1,-1)]:
            d.line((x+dx*4,y+dy*4,x+dx*r*.17,y+dy*r*.17),fill=INK,width=4)


def sketch(kind):
    im,d=board()
    place(im,'flower-notebook',(338,206),(640,381))
    if kind=='wrong-shape':
        round_mark(d,(338,211),107,INK,6)
        round_mark(d,(338,211),27,INK,6)
    else:
        draw_cross(d,(338,211),106,kind)
    return im


def analogy_shape(d,key,c):
    x,y=c
    if key=='trumpet':
        d.polygon([(x-49,y-30),(x+49,y-30),(x+15,y+24),(x+10,y+38),(x-10,y+38),(x-15,y+24)],fill='#d89c4d',outline=RUST,width=4)
        d.ellipse((x-50,y-39,x+50,y-20),fill='#fae5aa',outline=RUST,width=4)
    elif key=='cross':
        d.line((x-38,y,x+38,y),fill=RUST,width=17)
        d.line((x,y-38,x,y+38),fill=RUST,width=17)
    elif key=='bell':
        d.rounded_rectangle((x-38,y-42,x+38,y+23),18,fill='#ddb968',outline=RUST,width=4)
        d.ellipse((x-42,y+11,x+42,y+30),fill='#fae5aa',outline=RUST,width=4)
        d.ellipse((x-6,y+22,x+6,y+40),fill=INK)
    else:
        for dx in (-1,1):
            d.ellipse((x+dx*24-23,y-38,x+dx*24+23,y+8),fill='#c78756',outline=RUST,width=3)
            d.ellipse((x+dx*20-19,y-4,x+dx*20+19,y+30),fill='#e3b97c',outline=RUST,width=3)
        d.rounded_rectangle((x-7,y-16,x+7,y+31),6,fill=INK)


def analogies(groups):
    im,d=board((732,370))
    for i,key in enumerate(groups):
        x=15+i*357
        panel(d,(x,13,x+342,351))
        place(im,SHAPES[key],(x+171,109),(237,162))
        d.line((x+75,206,x+266,206),fill='#a5a687',width=3)
        analogy_shape(d,key,(x+171,275))
    return im


def smell_pose(who,large=False):
    im,d=board((450,282) if not large else (680,414))
    scale=1 if not large else 1.48
    def xy(x,y): return round(x*scale),round(y*scale)
    panel(d,(*xy(11,11),*xy(438,270)))
    d.line((*xy(25,251),*xy(421,251)),fill=GREEN,width=6)
    plant_x,plant_y=xy(358,143); pot_x,pot_y=xy(358,245)
    d.line((plant_x,plant_y,pot_x,pot_y),fill=GREEN,width=7)
    panel(d,(*xy(335,220),*xy(382,251)),'#b8704a',RUST)
    place(im,'wild-rose',(plant_x,plant_y),xy(78,81))
    child_x={'flower-look':116,'flower-waft':142,'flower-lean':254}[who]
    place(im,who,xy(child_x,251),xy(160,202),ground=True)
    return im


def neutral(name,key):
    im,d=board((156,148))
    panel(d,(5,4,151,143),CREAM,width=6)
    pic=sprite(key,(126,119))
    mask=pic.getchannel('A').point(lambda a:255 if a>=64 else 0)
    shadow=Image.new('RGBA',pic.size,INK);shadow.putalpha(mask)
    im.alpha_composite(shadow,((156-pic.width)//2,(148-pic.height)//2))
    return im


def visuals():
    yield 'school-flower-cover',background('campus-flowerbed',(696,440)),['flower-table'],['campus-flowerbed']
    yield 'sample-comparison',grid(['peach-top','double-rose','yellow-cross'],3,(760,398)),['flower-table'],['peach-top','double-rose','yellow-cross']
    yield 'photo-backdrop',background('flower-tabletop'),['flower-photo-pairs'],['flower-tabletop']
    yield 'sort-background',background('campus-flowerbed'),['sort-flower-shapes'],['campus-flowerbed']
    yield 'smell-safely',smell_pose('flower-waft',large=True),['safe-looking'],['flower-waft','wild-rose']
    yield 'funnel-and-cross',analogies(['trumpet','cross']),['compare-flower-shapes'],['glory-side','cress-top']
    yield 'bell-and-butterfly',analogies(['bell','butterfly']),['compare-flower-shapes'],['golden-bell','pea-flower']
    yield 'flower-sketch',sketch('all'),['sketch-a-flower'],['flower-notebook']
    yield 'flower-pair-cover',pair_cover(),['flower-photo-pairs'],[*PHOTOS['trumpet'],'flower-camera']
    for name,keys in PHOTOS.items():
        for view,key in zip(('top','side'),keys):
            yield f'flower-{view}-{name}',framed(key,view=='side'),['flower-photo-pairs'],[key]
    for name,key in SHAPES.items():
        yield f'shape-{name}',neutral(name,key),['sort-flower-shapes'],[key]
    yield 'peach-petal',flower_mark('peach-top','petal'),['find-petals-and-center'],['peach-top']
    yield 'peach-center',flower_mark('peach-top','center'),['find-petals-and-center'],['peach-top']
    yield 'rose-structure',grid(['wild-rose','peach-top']),['find-petals-and-center'],['wild-rose','peach-top']
    yield 'unusual-gallery-a',grid(['rafflesia','passionflower','egret-orchid'],3,(790,373)),['unusual-flower-gallery'],['rafflesia','passionflower','egret-orchid']
    yield 'unusual-gallery-b',grid(['firecracker-flower','lily-bells']),['unusual-flower-gallery'],['firecracker-flower','lily-bells']
    yield 'press-at-home',grid(['press-flower','flower-notebook']),['flower-note-at-home'],['press-flower','flower-notebook']
    for letter,key in zip('abc',('pea-flower','pink-trumpet','wild-rose')):
        yield 'q1-'+letter,grid([key]),['picture-quiz'],[key]
    yield 'q2-stimulus',framed('wild-rose'),['picture-quiz'],['wild-rose']
    for letter,mark in zip('abc',('center','petal','gap')):
        yield 'q2-'+letter,flower_mark('wild-rose',mark),['picture-quiz'],['wild-rose']
    for letter,pair in zip('abc',[['glory-top','cress-top'],['pea-flower','peach-top'],['cress-top','yellow-cross']]):
        yield 'q3-'+letter,grid(pair),['picture-quiz'],pair
    for letter,key in zip('abc',('flower-lean','flower-waft','flower-look')):
        yield 'q4-'+letter,smell_pose(key),['picture-quiz'],[key,'wild-rose']
    yield 'q5-stimulus',framed('yellow-cross',angle=45),['picture-quiz'],['yellow-cross']
    for letter,kind in zip('abc',('center','wrong-shape','all')):
        yield 'q5-'+letter,sketch(kind),['picture-quiz'],['flower-notebook']
    for letter,key in zip('abc',('egret-orchid','lily-bells','firecracker-flower')):
        yield 'q6-'+letter,grid([key]),['picture-quiz'],[key]


def render():
    def digest(p):
        return sha256(p.read_bytes()).hexdigest()
    sources={}
    for receipt in sorted((ROOT/'art-source').glob('*.receipt.json')):
        for a in json.loads(receipt.read_text())['assets']:
            sources[a['assetKey']]={**a,'file':a['path'],'kind':'codex-builtin-imagegen'}
    for key,im,uses,parents in visuals():
        path=ASSETS/f'{key}.png';im.save(path,optimize=True)
        sources[key]={'file':path.relative_to(ROOT).as_posix(),'sha256':digest(path),
                      'kind':'deterministic-lesson-diagram','usedBy':uses,'source':'diagrams/render.py',
                      'sourceSha256':digest(Path(__file__)),'sourceAssets':{a:sources[a]['sha256'] for a in parents}}
    (ROOT/'asset-sources.json').write_text(json.dumps({'schemaVersion':'mira.courseware.asset-sources.v1','assets':sources},
                                                      ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    render()
