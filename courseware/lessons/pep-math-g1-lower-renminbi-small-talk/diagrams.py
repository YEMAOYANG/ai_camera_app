"""Render the original exhibit cards and exact number relations for 小讲堂."""

from functools import lru_cache
from math import cos, pi, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ASSETS = Path(__file__).with_name('assets')
PAPER, INK = '#fff9ec', '#234137'
PINE, SAGE = '#32725d', '#dbe8cc'
CLAY, PEACH = '#ba632c', '#f6ddc2'
BLUE, LAKE = '#386c88', '#dbeaf1'
GOLD = '#efb95b'
DETAILS={'hall':(.23,.40,.81,.67),'potala':(.10,.21,.79,.66),'guilin':(.03,.27,.75,.67),
         'gorges':(.23,.38,.75,.86),'taishan':(.27,.28,.86,.86),'westlake':(.04,.50,.81,.84)}


@lru_cache(maxsize=None)
def font(size):
    for path in ('/System/Library/Fonts/STHeiti Medium.ttc', 'NotoSansCJK-Regular.ttc'):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def canvas(w=840, h=460):
    image=Image.new('RGB',(w,h),PAPER)
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((10,10,w-11,h-11),radius=25,outline=SAGE,width=4)
    return image,draw


def text(draw, x, y, value, size, ink=INK):
    draw.text((x,y),str(value),font=font(size),fill=ink,anchor='mm')


def picture(image,key,box,*,fit='crop',region=None):
    x,y,w,h=box
    with Image.open(ASSETS/f'{key}.png') as src:
        src=src.convert('RGBA')
        if region is not None:
            src=src.crop(tuple(round(a*b) for a,b in zip(region,(src.width,src.height)*2)))
        resized=(ImageOps.fit(src,(w,h),method=Image.Resampling.LANCZOS)
                 if fit=='crop' else ImageOps.contain(src,(w,h),method=Image.Resampling.LANCZOS))
        image.paste(resized,(x+(w-resized.width)//2,y+(h-resized.height)//2),resized)


def rounded(draw, bounds, color=SAGE, *, edge=None, radius=16):
    draw.rounded_rectangle(bounds,radius=radius,fill=color,outline=edge,width=3)


def arrow(draw, a, b, y, ink=PINE):
    draw.line((a,y,b,y),fill=ink,width=5)
    draw.polygon(((b,y),(b-15,y-10),(b-15,y+10)),fill=ink)


def badge(draw,x,y,value,*,fill=SAGE,ink=INK,w=136,h=65,size=49):
    rounded(draw,(x-w/2,y-h/2,x+w/2,y+h/2),fill)
    text(draw,x,y,value,size,ink)


def exhibit(value, landmark):
    image,draw=canvas()
    picture(image,landmark,(28,30,464,396))
    badge(draw,664,113,f'{value} 元',fill=PEACH,w=228,h=96,size=63)
    draw.ellipse((571,207,753,389),outline=PINE,width=10)
    picture(image,landmark,(604,240,116,116),region=DETAILS[landmark])
    draw.line((727,361,779,412),fill=PINE,width=15)
    return image


def gallery():
    image,draw=canvas()
    for i,(value,key) in enumerate(((50,'potala'),(20,'guilin'),(10,'gorges'),(5,'taishan'),(1,'westlake'))):
        x=(66,316,566,191,441)[i]
        y=27 if i<3 else 242
        picture(image,key,(x,y,207,145))
        badge(draw,x+104,y+169,f'{value} 元',w=120,h=48,size=35)
    return image


def landmark_clue(value, landmark):
    image,draw=canvas(800,250)
    badge(draw,204,126,f'{value} 元',fill=PEACH,w=286,h=146,size=95)
    picture(image,landmark,(405,21,363,209),region=DETAILS[landmark])
    return image


def topics():
    image,draw=canvas()
    for i,key in enumerate(('guilin','cowrie','see-through')):
        x,y=30+(i%2)*407,29+(i//2)*209
        rounded(draw,(x,y,x+374,y+185),PEACH if i==1 else LAKE)
        picture(image,key,(x+11,y+8,352,169),fit='contain')
    rounded(draw,(437,238,811,423),SAGE)
    for x,n in zip((511,624,737),(1,2,5)):
        badge(draw,x,329,n,fill=PAPER,w=84,h=87,size=56)
    return image


def series(a,b,*,small=False):
    image,draw=canvas(520,330) if small else canvas()
    width,height=image.size
    for x,(edition,form,value) in zip((width*.28,width*.72),(a,b)):
        w=width*.34
        y=height*.43
        colors=(PEACH,CLAY) if edition==4 else (LAKE,BLUE)
        rounded(draw,(x-w/2,y-57,x+w/2,y+57),colors[0],edge=colors[1])
        if form=='lines':
            for offset in (-24,0,24):
                draw.line((x-w*.29,y+offset,x+w*.29,y+offset),fill=colors[1],width=6)
        elif form=='oval':
            draw.ellipse((x-39,y-34,x+39,y+34),outline=colors[1],width=6)
        else:
            draw.polygon(((x,y-37),(x+43,y),(x,y+37),(x-43,y)),outline=colors[1],width=6)
        badge(draw,x,height*.77,f'第{edition}套',fill=colors[0],ink=colors[1],w=w,h=59,size=40 if small else 54)
        if value is not None:
            badge(draw,x,height*.12,f'{value} 元',w=w,h=52,size=40)
    return image


def old_shapes():
    image,draw=canvas()
    for x,key in ((40,'cowrie'),(446,'square-hole-coin')):
        rounded(draw,(x,42,x+354,416),LAKE if x==40 else PEACH)
        picture(image,key,(x+19,73,316,297),fit='contain')
    return image


def observations(*items):
    image,draw=canvas()
    for i,key in enumerate(items):
        w=780//len(items)
        picture(image,key,(34+i*w,48,w-10,362),fit='contain')
    return image


def number_blocks(parts, *, answer=None, size=(840,460)):
    image,draw=canvas(*size)
    w,h=size
    spacing=w/(len(parts)*2+1)
    for i,n in enumerate(parts):
        x=(2*i+1.5)*spacing
        badge(draw,x,h*.40,n,fill={1:PEACH,2:LAKE,5:SAGE}.get(n,PEACH),w=spacing*1.47,h=h*.35,size=round(h*.25))
        if i:
            text(draw,x-spacing,h*.40,'+',round(h*.16))
    if answer is not None:
        badge(draw,w/2,h*.81,f'= {answer}',fill=SAGE,w=w*.35,h=h*.23,size=round(h*.15))
    return image


def clues(mode):
    image,draw=canvas(520,330)
    if mode=='pair':
        picture(image,'hall',(31,67,192,188),region=DETAILS['hall'])
        picture(image,'hall',(297,45,192,232))
        arrow(draw,226,288,157)
    elif mode=='payment':
        badge(draw,131,155,'6 元',fill=PEACH,w=162,size=54)
        badge(draw,387,155,'4 元',fill=LAKE,w=162,size=54)
        arrow(draw,223,292,155)
    else:
        for x,values in ((145,(1,5)),(375,(2,2))):
            rounded(draw,(x-92,86,x+92,253),PEACH,edge=CLAY)
            for offset,value in zip((-38,38),values):
                badge(draw,x+offset,163,value,w=58,h=65,size=37)
    return image


def share(order, *, compact=False, landmark='westlake', second_view=None):
    image,draw=canvas(520,330) if compact else canvas()
    w,h=image.size
    for i,key in enumerate(order):
        width=w*.245
        x=w*(.18+i*.32)
        left,top=round(x-width/2),round(h*.23)
        bounds=(left,top,round(x+width/2),round(h*.77))
        rounded(draw,bounds,{'question':PEACH,'clue':LAKE,'finding':SAGE}.get(key,PAPER),edge=PINE)
        if key=='question':
            text(draw,x,h*.50,'?',round(h*.31),CLAY)
        elif key=='clue':
            views=((0,landmark,None),(.21,second_view or landmark,None if second_view else DETAILS[landmark]))
            for offset,source,region in views:
                picture(image,source,(left+10,round(h*(.28+offset)),round(width-20),round(h*.19)),region=region)
        elif key=='finding':
            picture(image,landmark,(left+10,round(h*.30),round(width-20),round(h*.28)))
            draw.line(((x-h*.042,h*.672),(x-h*.014,h*.703),(x+h*.051,h*.628)),fill=PINE,width=round(h*.016))
        if i<2:
            arrow(draw,round(x+width/2+2),round(x+w*.32-width/2-4),round(h*.50))
    return image


def symbol(value):
    image,draw=canvas(520,330)
    badge(draw,260,163,value,fill=PEACH,w=278,h=159,size=93)
    return image


def inquiry_stem(kind):
    image,draw=canvas(520,330)
    rounded(draw,(64,48,391,279),LAKE if kind=='architecture' else PEACH,edge=PINE)
    if kind=='architecture':
        draw.polygon(((105,156),(227,92),(347,156)),fill=CLAY)
        draw.rectangle((128,156,327,234),fill=PAPER)
        for x in (150,194,238,282):
            draw.rectangle((x,163,x+19,226),fill=CLAY)
    else:
        draw.ellipse((139,102,321,224),outline='#b9ab83',width=4)
        draw.arc((152,109,302,210),16,150,fill='#b9ab83',width=4)
        draw.line((151,204,290,129),fill='#b9ab83',width=4)
    badge(draw,402,215,'?',fill=PAPER,w=128,h=111,size=82)
    return image


def compare_stem():
    image,draw=canvas(520,330)
    for x in (144,376):
        rounded(draw,(x-87,87,x+87,241),LAKE,edge=PINE)
        text(draw,x,161,'?',61,BLUE)
    return image


def sticker():
    image=Image.new('RGBA',(160,160))
    draw=ImageDraw.Draw(image)
    draw.ellipse((9,9,150,150),fill=PEACH,outline=PINE,width=7)
    points=[(80+r*cos(i*pi/5-pi/2),80+r*sin(i*pi/5-pi/2)) for i,r in enumerate([48,21]*5)]
    draw.polygon(points,fill=GOLD,outline=CLAY,width=4)
    return image


def diagrams():
    quiz_share={'compact':True,'landmark':'potala','second_view':'potala-quiz'}
    return {
        'questions-four':topics(),'hall-reference':exhibit(100,'hall'),'landmark-gallery':gallery(),
        'series-study':series((4,'lines',2),(5,'oval',20)),'historical-shapes':old_shapes(),
        'observe-together':observations('tilt-swatch','touch-swatch'),
        'compose-seven':number_blocks((5,2),answer=7),'compose-eight':number_blocks((5,2,1),answer=8),
        'hop-clues-1':number_blocks((1,2,5),size=(840,300)),
        'hop-clues-2':number_blocks((2,5,2),size=(840,300)),
        'hop-clues-3':number_blocks((5,2,2,2),size=(840,300)),
        'share-steps':share(('question','clue','finding')),'share-empty':share(('','',''),compact=True),
        'exhibit-sticker':sticker(),'q1-stem':inquiry_stem('architecture'),'q1-a':clues('payment'),
        'q1-b':clues('pair'),'q1-c':clues('boxes'),'q2-stem':symbol('50 元'),
        'q3-stem':inquiry_stem('watermark'),'q3-c':number_blocks((1,2,5),size=(520,330)),
        'q4-stem':compare_stem(),'q4-a':series((4,'lines',None),(4,'oval',None),small=True),
        'q4-b':series((4,'lines',None),(5,'oval',None),small=True),
        'q4-c':series((5,'oval',None),(5,'oval',None),small=True),
        'q5-stem':symbol(12),'q5-a':number_blocks((5,5,1),size=(520,330)),
        'q5-b':number_blocks((5,5,5),size=(520,330)),'q5-c':number_blocks((5,5,2),size=(520,330)),
        'q6-a':share(('question','clue','finding'),**quiz_share),
        'q6-b':share(('finding','question','clue'),**quiz_share),
        'q6-c':share(('clue','finding','question'),**quiz_share),
        'exhibit-1':exhibit(1,'westlake'),
        **{f'marble-{value}':landmark_clue(value,landmark) for value,landmark in
           ((100,'hall'),(20,'guilin'),(10,'gorges'),(5,'taishan'),(1,'westlake'))},
    }


if __name__=='__main__':
    for key,image in diagrams().items():
        image.save(ASSETS/f'{key}.png',optimize=True)
