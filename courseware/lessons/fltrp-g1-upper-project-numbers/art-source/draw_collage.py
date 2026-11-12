"""Compose exact object counts for the Numbers project from single cutouts."""
from functools import lru_cache
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / 'assets'
CREAM = '#fff4dd'
PINE = '#214d3c'
TEAL = '#cbe2cb'
APRICOT = '#f7d2aa'
FONT = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'


@lru_cache(maxsize=32)
def sprite(kind, size):
    with Image.open(ASSETS / ('paper-' + kind + '.png')) as source:
        rgba = source.convert('RGBA')
        mask = rgba.getchannel('A').point(lambda value: 255 if value >= 16 else 0)
        image = rgba.crop(mask.getbbox())
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        return image


def stamp(image, kind, x, y, size):
    art = sprite(kind, size)
    image.alpha_composite(art, (round(x-art.width/2), round(y-art.height/2)))


def label(image, value, x, y, size, color=PINE):
    font = ImageFont.truetype(FONT, size)
    ImageDraw.Draw(image).text((x,y),str(value),anchor='mm',font=font,fill=color)


def positions(n, scattered=False):
    if type(n) is not int or not 0 <= n <= 10:
        raise ValueError('A collage card can hold zero to ten cutouts')
    if scattered:
        return [(87,79),(172,88),(263,72),(357,91),(441,78),
                (106,183),(190,174),(280,186),(369,176),(454,185)][:n]
    return [(84+86*(i%5),88+98*(i//5)) for i in range(n)]


def collage(kind, count, scattered=False):
    image=Image.new('RGBA',(510,270),CREAM)
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((20,20,490,249),radius=24,fill='#eaf1dc',outline='#93ad90',width=3)
    for x,y in positions(count,scattered):
        stamp(image,kind,x,y,69)
    return image


def group_mix(a, n, b, m, interleave=False):
    kinds = [a] * n + [b] * m
    if interleave:
        kinds=[]
        for i in range(max(n,m)):
            if i<n: kinds.append(a)
            if i<m: kinds.append(b)
    image=Image.new('RGBA',(510,270),CREAM)
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((19,20,491,249),radius=20,fill='#edf0d8',outline='#9cb39b',width=3)
    for kind,(x,y) in zip(kinds,positions(n+m,scattered=interleave)):
        stamp(image,kind,x,y,68)
    return image


def number_strip(numbers, kind):
    image=Image.new('RGBA',(690,320),TEAL)
    draw=ImageDraw.Draw(image)
    for col,n in enumerate(numbers):
        x=19+132*col
        draw.rounded_rectangle((x,19,x+123,301),radius=16,fill=CREAM)
        label(image,n,x+61,58,48)
        for i in range(n):
            row,j=divmod(i,3)
            stamp(image,kind,x+25+36*j,111+43*row,31)
    return image


def slots(kind, target, filled):
    if not 0 <= filled <= target <= 10:
        raise ValueError('Filled spaces must fit within the collage card')
    image=Image.new('RGBA',(510,270),CREAM)
    draw=ImageDraw.Draw(image)
    label(image,target,255,48,55)
    for i in range(target):
        row,col=divmod(i,5)
        row_total=min(5,target-row*5)
        x=255+(col-(row_total-1)/2)*80
        y=117+80*row
        draw.rounded_rectangle((x-34,y-32,x+34,y+32),radius=13,fill=APRICOT if i<filled else TEAL,
                               outline='#8aa589',width=3)
        if i<filled:
            stamp(image,kind,x,y,57)
    return image


def game_group(kind, count, station=False):
    if not 1 <= count <= 10:
        raise ValueError('A delivery card can show one to ten pieces')
    image=Image.new('RGBA',(240,158),TEAL if station else CREAM)
    draw=ImageDraw.Draw(image)
    # The object at left names the category. Only the dots at right are counted.
    draw.rounded_rectangle((5,7,113,151),radius=18,fill='#f4e3bf',outline='#8fa78b',width=3)
    stamp(image,kind,59,79,97)
    label(image,count,175,54,76)
    for i in range(count):
        x,y=133+21*(i%5),106+22*(i//5)
        draw.ellipse((x-7,y-7,x+7,y+7),fill=PINE)
    return image


def tracked(kind, count, marks):
    image=collage(kind,count)
    draw=ImageDraw.Draw(image)
    already=set()
    spots=positions(count)
    for number,i in enumerate(marks,1):
        x,y=spots[i]
        duplicate=i in already
        already.add(i)
        draw.ellipse((x-35,y-36,x+35,y+36),outline='#328567',width=3)
        px=x-24 if duplicate else x+29
        py=y-26
        draw.ellipse((px-14,py-14,px+14,py+14),fill=PINE)
        label(image,number,px,py,20,'#fff7dc')
    return image


def main():
    definitions=json.loads((HERE/'project-math.json').read_text())
    renderers=dict(collage=collage,group_mix=group_mix,number_strip=number_strip,
                   slots=slots,game_group=game_group,tracked=tracked)
    for key,(kind,args,options) in definitions.items():
        renderers[kind](*args,**options).save(ASSETS/(key+'.png'),optimize=True)


if __name__=='__main__':
    main()
