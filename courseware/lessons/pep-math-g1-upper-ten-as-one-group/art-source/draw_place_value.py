"""Exact counting, bundling and place-value diagrams for 10的再认识."""

import argparse
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


SOURCE = Path(__file__).resolve().parents[1]
PAPER = '#fff7e5'
CREAM = '#f5e5c6'
INK = '#264c41'
GREEN = '#599683'
ORANGE = '#c35f35'
LINE = '#a3896a'
FONT = '/System/Library/Fonts/Supplemental/Arial Unicode.ttf'


@lru_cache(maxsize=None)
def font(size):
    return ImageFont.truetype(FONT, size)


class Drawing:
    def __init__(self, width=720, height=360):
        self.image = Image.new('RGB', (width, height), PAPER)
        self.draw = ImageDraw.Draw(self.image)

    def text(self, x, y, value, size=48):
        self.draw.text((x, y), str(value), fill=INK, font=font(size), anchor='mm')

    def box(self, bounds, radius=12, fill=PAPER, outline=LINE, width=3):
        self.draw.rounded_rectangle(bounds, radius=radius, fill=fill, outline=outline, width=width)

    def arrow(self, x, y, end):
        self.draw.line((x, y, end, y), fill=INK, width=5)
        self.draw.polygon(((end, y), (end-15, y-9), (end-15, y+9)), fill=INK)

    def chips(self, count, x, y, gap, cols, radius, *, shape='round', fill=GREEN):
        for i in range(count):
            cx, cy = x+(i%cols)*gap, y+(i//cols)*gap
            bounds = (cx-radius, cy-radius, cx+radius, cy+radius)
            if shape == 'square':
                self.box(bounds, radius//3, fill, INK, 2)
            else:
                self.draw.ellipse(bounds, fill=fill, outline=INK, width=2)

    def sticks(self, count, x, y, cols, dx, dy, length, width):
        for i in range(count):
            px, py = x+i%cols*dx, y+i//cols*dy
            self.box((px-width/2, py, px+width/2, py+length), max(3, width//2),
                     GREEN, INK, max(1, width//6))

    def bundle(self, x, y, gap, length, width):
        self.sticks(10, x, y, 10, gap, 0, length, width)
        self.box((x-width, y+length*.4, x+9*gap+width, y+length*.59), 5, ORANGE, INK, 2)

    def abacus(self, bounds, tens, ones, *, places=False, digits=None, capacity=10):
        x0,y0,x1,y1 = bounds
        w,h = x1-x0,y1-y0
        base = y0+h*(.71 if digits else .82)
        left,right = x0+w*.27,x0+w*.73
        bar = max(4, round(h*.07))
        bead = (base-y0-h*.15)/capacity
        for cx,count in ((left,tens),(right,ones)):
            self.draw.line((cx,y0+h*.08,cx,base), fill=INK, width=bar)
            for i in range(count):
                cy=base-(i+.66)*bead
                self.box((cx-w*.14,cy-bead*.45,cx+w*.14,cy+bead*.45), max(2,round(bead*.45)),
                         ORANGE,INK, max(1,round(h*.009)))
        self.box((x0+w*.04,base,x1-w*.04,base+h*.12), max(4,round(h*.03)), CREAM)
        self.draw.line(((x0+x1)/2,base,(x0+x1)/2,base+h*.12),fill=LINE,width=2)
        if places:
            for cx,name in ((left,'十位'),(right,'个位')):
                self.text(cx,base+h*.06,name,round(min(w*.13,h*.09)))
        if digits:
            for cx,digit in zip((left,right),digits):
                self.box((cx-w*.15,y1-h*.15,cx+w*.15,y1-h*.01), 6, CREAM)
                if digit is not None:
                    self.text(cx,y1-h*.08,digit,round(h*.12))


def count_board(grouped, extra=4):
    c=Drawing()
    if grouped:
        c.box((53,83,436,281),radius=32,fill=CREAM,outline=ORANGE,width=7)
    c.chips(10,100,134,71,5,21)
    c.chips(extra,505,134,55,3,19)
    return c


def class_sticks(bundled):
    c=Drawing()
    if bundled:
        c.bundle(207,55,34,250,23)
    else:
        c.sticks(10,206,54,5,76,142,108,20)
    return c


def stick_card(*, loose=0, bundled=False):
    c=Drawing(280,160)
    if bundled:
        x = 25 if loose else 73
        c.bundle(x,24,13,113,10)
        c.sticks(loose,181,36,3,32,50,37,10)
    else:
        cols=min(loose,5)
        x=140-(cols-1)*26
        c.sticks(loose,x,35 if loose>5 else 28,cols,52,58,41 if loose>5 else 100,13)
    return c


def exchange_board():
    c=Drawing()
    for i,(tens,ones) in enumerate(((0,9),(0,10),(1,0))):
        x=22+i*240
        c.abacus((x,55,x+194,304),tens,ones,places=True)
        if i<2:
            c.arrow(x+193,167,x+224)
    return c


def position_pair():
    c=Drawing()
    c.abacus((57,42,328,325),0,1,places=True)
    c.abacus((391,42,662,325),1,0,places=True)
    return c


def digit_board():
    c=Drawing()
    for i in range(10):
        x=54+68*i
        c.box((x-27,48,x+27,122),10)
        c.text(x,86,i,46)
    c.box((240,180,480,315),16,CREAM)
    for x,digit in ((305,1),(415,0)):
        c.text(x,247,digit,102)
    return c


def abacus_card(tens,ones,*,big=False,digits=None):
    width,height=(720,360) if big else (220,220)
    c=Drawing(width,height)
    c.abacus((width*.12,7,width*.88,height-8),tens,ones,places=big,digits=digits,
             capacity=10 if big else max(5,ones))
    return c


def unlabelled_one():
    c=Drawing()
    c.abacus((149,37,571,320),0,1)
    return c


def tray(count,shape='square'):
    c=Drawing(480,240)
    c.box((34,27,446,213),24,CREAM)
    c.chips(count,126,74,57,5,20,shape=shape)
    return c


def loose_chips(count):
    c=Drawing(480,240)
    cols=min(count,4)
    if count:
        c.chips(count,240-(cols-1)*35,93 if count>4 else 120,70,cols,20)
    return c


def number_labels(*digits):
    c=Drawing(480,240)
    if len(digits)==1:
        c.box((55,33,425,207),16,CREAM)
        c.text(240,120,digits[0],106)
    else:
        for x,digit in zip((133,347),digits):
            c.box((x-91,35,x+91,205),16,CREAM)
            c.text(x,120,digit,96)
    return c


def label_pair_stem():
    c=Drawing()
    c.box((26,55,339,305),19,CREAM)
    c.chips(8,91,143,59,4,19)
    c.box((381,55,694,305),19,CREAM)
    c.chips(10,427,143,55,5,18)
    return c


def drawings():
    yield from [
        ('count-before',count_board(False)),('count-after',count_board(True)),
        ('class-loose-ten',class_sticks(False)),('class-bundle-ten',class_sticks(True)),
        ('exchange-board',exchange_board()),('position-pair',position_pair()),('digits-board',digit_board()),
    ]
    for name,number in [('one',1),('two',2),('three',3),('four',4),('five',5),('nine',9),('ten',10)]:
        yield 'stick-loose-'+name,stick_card(loose=number)
    for name,number in [('',0),('-one',1),('-two',2),('-three',3),('-five',5),('-six',6)]:
        yield 'stick-bundle'+name,stick_card(bundled=True,loose=number)
    for name,number in [('one',1),('two',2),('three',3),('four',4),('five',5),('ten',10)]:
        yield 'ab-'+name,abacus_card(int(number==10),number%10)
    quiz = {
        'stamp-packet': (tray(0),[tray(n) for n in (9,10,11)]),
        'seven-loose': (count_board(True,7),[loose_chips(n) for n in (6,8,7)]),
        'ten-bead-trade': (abacus_card(0,10,big=True),[abacus_card(a,b,big=True) for a,b in ((1,0),(0,1),(0,9))]),
        'one-on-the-right': (unlabelled_one(),[tray(10,'round'),loose_chips(1),tray(0)]),
        'keep-the-place': (abacus_card(1,0,big=True,digits=(1,None)),[number_labels(n) for n in (9,1,0)]),
        'two-known-digits': (label_pair_stem(),[number_labels(a,b) for a,b in ((8,10),(8,1),(0,10))]),
    }
    for key,(stem,options) in quiz.items():
        yield 'q-'+key,stem
        for letter,option in zip('abc',options):
            yield f'q-{key}-{letter}',option


def write_assets(directory):
    directory.mkdir(parents=True,exist_ok=True)
    records={}
    for key,drawing in drawings():
        path=directory/(key+'.png')
        drawing.image.save(path,optimize=True)
        records[key]={'file':'assets/'+path.name,'kind':'deterministic_semantic_diagram',
                      'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                      'pixels':list(drawing.image.size)}
    return records


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=SOURCE/'assets')
    args=parser.parse_args()
    print(json.dumps(write_assets(args.output),ensure_ascii=False,indent=2))
