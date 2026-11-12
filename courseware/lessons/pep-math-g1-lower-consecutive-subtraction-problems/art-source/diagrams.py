"""Render exact teaching quantities and picture quiz options for this lesson."""
from hashlib import sha256
from pathlib import Path
import argparse
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent
BACKGROUND = '#fff4dd'
INK = '#284c46'
SOFT = '#e7d7b6'
ACCENT = '#a3403d'
FONT = Path('/System/Library/Fonts/Supplemental/Arial Bold.ttf')
EXAMPLES = {
    'main': {'total': 22, 'size': 6},
    'zero': {'total': 16, 'size': 4},
    'compare': {'total': 20, 'sizes': [4, 7]},
}
QUIZ = {
    'fixed-group': {'total': 23, 'size': 5, 'options': [4, 5, 6]},
    'second-remainder': {'total': 29, 'size': 7, 'steps': 2, 'options': [15, 22, 14]},
    'stop-short': {'total': 31, 'size': 6, 'options': [[4, 7], [6, 0], [5, 1]]},
    'stop-zero': {'total': 18, 'size': 6, 'options': [[2, 6], [3, 0], [3, 2]]},
    'compare-packs': {'total': 24, 'sizes': [6, 8], 'options': [[4, 3], [3, 4], [4, 4]]},
}
ROUTE_VALUES = [0, 2, 3, 5, 7, 9, 10, 12, 15, 21]


def font(size):
    return ImageFont.truetype(str(FONT), size) if FONT.exists() else ImageFont.load_default(size=size)


def label(draw, value, x, y, size=36, color=INK):
    draw.text((x, y), str(value), font=font(size), fill=color, anchor='mm')


def badge(draw, x, y, radius, color=ACCENT):
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)
    draw.ellipse((x-radius*.46, y-radius*.48, x+radius*.07, y+radius*.06), fill='#ffe5ab')


def rack(draw, count, x, y, *, columns=5, gap=24, radius=8, color=ACCENT):
    for index in range(count):
        row, column = divmod(index, columns)
        badge(draw, x+column*gap, y+row*gap, radius, color)


def tile(draw, bounds, fill='#fff9ed', line=SOFT, width=4):
    draw.rounded_rectangle(bounds, radius=13, fill=fill, outline=line, width=width)


def bag(draw, x, y, size, digits=None):
    points = [(x+size*.29,y+size*.17),(x+size*.71,y+size*.17),(x+size*.91,y+size*.85),
              (x+size*.8,y+size),(x+size*.2,y+size),(x+size*.09,y+size*.85)]
    draw.polygon(points, fill='#e8b967', outline=INK)
    draw.line((x+size*.3,y+size*.19,x+size*.7,y+size*.19), fill=INK, width=max(2, round(size*.045)))
    if digits is not None:
        label(draw, digits, x+size*.5, y+size*.66, max(12, round(size*.33)))


def make_card(count, *, size=(500, 340), numeral=True):
    image = Image.new('RGB', size, BACKGROUND)
    draw = ImageDraw.Draw(image)
    w, h = size
    tile(draw, (14, 14, w-14, h-14))
    if numeral:
        label(draw, count, w/2, h*.27, round(h*.27))
    if count:
        columns = min(count, 8)
        gap = min(44, (w-60)/columns)
        rows = (count+columns-1)//columns
        center_y = h*.68 if numeral else h/2
        rack(draw, count, w/2-(columns-1)*gap/2, center_y-(rows-1)*gap/2,
             columns=columns, gap=gap, radius=gap*.33)
    else:
        draw.rounded_rectangle((w*.35,h*.53,w*.65,h*.8),radius=18,outline=INK,width=5)
    return image


def bag_contents(count):
    image = Image.new('RGB',(500,350),BACKGROUND)
    draw = ImageDraw.Draw(image)
    bag(draw,90,15,320)
    label(draw,count,250,115,58)
    columns=min(3,count)
    rack(draw,count,250-(columns-1)*62/2,195,columns=columns,gap=62,radius=18)
    return image


def grouped(total, size):
    full, rest = divmod(total, size)
    image = Image.new('RGB',(790,330),BACKGROUND)
    draw = ImageDraw.Draw(image)
    group_width = 140
    blocks = full+1
    start = (790-blocks*group_width)/2
    for index in range(blocks):
        x = start+index*group_width
        is_full = index<full
        count = size if is_full else rest
        tile(draw,(x+5,72,x+135,261),fill='#f7e4b9' if is_full else '#fffaf0',
             line=INK if is_full else '#947d68')
        if is_full:
            bag(draw,x+48,94,44)
        else:
            label(draw, rest, x+70,113,29)
        gap = 23
        columns = min(size,4)
        rack(draw,count,x+70-(columns-1)*gap/2,167,columns=columns,gap=gap,radius=8)
    label(draw,total,395,43,47)
    return image


def chain(total,size):
    values = list(range(total,-1,-size))
    image = Image.new('RGB',(825,280),BACKGROUND)
    draw = ImageDraw.Draw(image)
    xs = [83 + i*(659/(len(values)-1)) for i in range(len(values))]
    for i,(x,value) in enumerate(zip(xs,values)):
        tile(draw,(x-48,92,x+48,202),fill='#edc67b' if i==len(values)-1 else '#fff9ed',line=INK)
        label(draw,value,x,147,56)
        if i:
            left=xs[i-1]+52
            right=x-54
            draw.line((left,148,right,148),fill=INK,width=6)
            draw.polygon([(right,148),(right-17,137),(right-17,159)],fill=INK)
            label(draw,'−'+str(size),(left+right)/2,113,30)
    return image


def result_card(full, size, remainder):
    image=Image.new('RGB',(500,350),BACKGROUND)
    draw=ImageDraw.Draw(image)
    tile(draw,(17,25,318,323),line=INK,fill='#fff9ed')
    tile(draw,(331,25,485,323),line='#92735a',fill='#fff9ed')
    label(draw,full,165,86,68)
    for index in range(full):
        row,col=divmod(index,3)
        bag(draw,47+col*86,138+row*79,59,size)
    label(draw,remainder,410,102,66)
    if remainder:
        columns=min(3,remainder)
        rack(draw,remainder,410-(columns-1)*23/2,173,columns=columns,gap=23,radius=8)
    else:
        draw.rounded_rectangle((365,158,454,214),radius=12,outline=INK,width=4)
    return image


def compare_card(sizes, fulls):
    image=Image.new('RGB',(500,355),BACKGROUND)
    draw=ImageDraw.Draw(image)
    for index,(size,full) in enumerate(zip(sizes,fulls)):
        y=15+index*168
        tile(draw,(10,y,490,y+151),line=INK)
        label(draw,size,75,y+59,51)
        rack(draw,size,43,y+103,columns=4,gap=18,radius=6)
        draw.line((129,y+74,195,y+74),fill=INK,width=6)
        draw.polygon([(195,y+74),(181,y+65),(181,y+84)],fill=INK)
        label(draw,full,239,y+72,55)
        for pack in range(full):
            row,col=divmod(pack,3)
            bag(draw,281+col*62,y+19+row*61,44)
    return image


def add_back(total,size):
    full,rest=divmod(total,size)
    image=grouped(total,size)
    draw=ImageDraw.Draw(image)
    expression=' + '.join([str(size)]*full+[str(rest)])+' = '+str(total)
    label(draw,expression,395,293,40)
    return image


def route_start():
    image = Image.new('RGB',(750,340),BACKGROUND)
    left = make_card(17,size=(348,310))
    right = make_card(5,size=(348,310))
    image.paste(left,(12,15))
    image.paste(right,(390,15))
    return image


def token_image():
    image=Image.new('RGBA',(96,96),(0,0,0,0))
    draw=ImageDraw.Draw(image)
    badge(draw,48,48,42)
    return image


def generated_assets():
    yield 'token-badge',token_image(),{'oneObject':True}
    yield 'one-full-group',make_card(6),{'count':6}
    yield 'circle-main',grouped(22,6),EXAMPLES['main']
    yield 'arrow-main',chain(22,6),EXAMPLES['main']
    yield 'stopping-main',result_card(3,6,4),{'full':3,'size':6,'remainder':4}
    yield 'zero-example',grouped(16,4),EXAMPLES['zero']
    yield 'addition-check',add_back(22,6),EXAMPLES['main']
    yield 'compare-example',compare_card([4,7],[5,2]),EXAMPLES['compare']
    yield 'catch-opening',grouped(8,3),{'total':8,'size':3,'remainder':2}
    yield 'route-opening',route_start(),{'total':17,'size':5}
    for amount in ROUTE_VALUES:
        yield 'station-'+str(amount),make_card(amount,size=(216,216)),{'count':amount}
    yield 'quiz-fixed-prompt',make_card(23,numeral=False),{'count':23}
    for quiz,question in QUIZ.items():
        for key,value in zip('abc',question['options']):
            if quiz=='fixed-group':
                image=bag_contents(value)
            elif quiz=='second-remainder':
                image=make_card(value)
            elif quiz=='compare-packs':
                image=compare_card(question['sizes'],value)
            else:
                image=result_card(value[0],question['size'],value[1])
            yield 'quiz-'+quiz+'-'+key,image,{'option':value, **{k:v for k,v in question.items() if k!='options'}}


def record(path, **kwargs):
    return {'path':str(path.relative_to(SOURCE)),'sha256':sha256(path.read_bytes()).hexdigest(),
            'bytes':path.stat().st_size,**kwargs}


def render(prompt):
    assets=SOURCE/'assets'
    assets.mkdir(exist_ok=True)
    records={}
    atlas=HERE/'packing-atlas.png'
    with Image.open(atlas) as source:
        image=source.convert('RGB')
    names=('packing-room','pack-cart','finish-sticker','backstage-path')
    for i,name in enumerate(names):
        row,col=divmod(i,2)
        coords=(round(col*image.width/2)+10,round(row*image.height/2)+10,
                round((col+1)*image.width/2)-10,round((row+1)*image.height/2)-10)
        path=assets/(name+'.png')
        image.crop(coords).save(path,optimize=True)
        records[name]=record(path,kind='crop-of-codex-builtin-imagegen',crop=coords)
    for name,img,truth in generated_assets():
        path=assets/(name+'.png')
        img.save(path,optimize=True)
        records[name]=record(path,kind='deterministic-quantity',size=img.size,truth=truth)
    out={'schemaVersion':'mira.courseware.art-provenance.v1',
         'atlas':record(atlas,tool='codex-builtin-imagegen',prompt=prompt),
         'diagramSource':record(Path(__file__)),
         'font':{'name':'Arial Bold','fallback':'Pillow default',
                 'sha256':sha256(FONT.read_bytes()).hexdigest() if FONT.exists() else None},
         'assets':records}
    (SOURCE/'asset-provenance.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--describe',action='store_true')
    parser.add_argument('--atlas-prompt',default=os.getenv('MIRA_PACK_ATLAS_PROMPT'))
    args=parser.parse_args()
    if args.describe:
        print(json.dumps({'examples':EXAMPLES,'quiz':QUIZ,'routeValues':ROUTE_VALUES}))
    else:
        if not args.atlas_prompt:
            parser.error('an atlas provenance prompt is required to write the asset manifest')
        render(args.atlas_prompt)
