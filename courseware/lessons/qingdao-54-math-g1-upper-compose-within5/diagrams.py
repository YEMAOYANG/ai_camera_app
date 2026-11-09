"""Draw this lesson's exact counted objects, branch diagrams, and quiz cards."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


CREAM = '#fff8ea'
INK = '#234942'
TEAL = '#14685f'
GOLD = '#d87f10'
RED = '#8d392b'
ASSETS = Path(__file__).parent / 'assets'
FONT = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'


def image(size):
    frame = Image.new('RGB', size, CREAM)
    return frame, ImageDraw.Draw(frame)


def number(draw, xy, value, size=66):
    draw.text(xy, str(value), fill=INK, font=ImageFont.truetype(FONT, size), anchor='mm')


def item(draw, x, y, radius, kind, color):
    r = radius
    if kind == 'seed':
        draw.ellipse((x-r*.68, y-r, x+r*.68, y+r), fill=color, outline=INK, width=3)
        draw.line((x+2, y-r*.48, x-3, y+r*.38), fill='#ffd68e', width=3)
    elif kind == 'bookmark':
        draw.polygon([(x-r*.58,y-r),(x+r*.58,y-r),(x+r*.58,y+r),
                      (x,y+r*.57),(x-r*.58,y+r)], fill=color, outline=INK, width=3)
    elif kind == 'ticket':
        draw.rounded_rectangle((x-r, y-r*.66, x+r, y+r*.66), radius=8, fill=color, outline=INK, width=3)
        draw.line((x+r*.43,y-r*.48,x+r*.43,y+r*.48), fill=CREAM, width=3)
    elif kind == 'book':
        draw.rounded_rectangle((x-r*.78,y-r,x+r*.78,y+r), radius=5, fill=color, outline=INK, width=3)
        draw.line((x-r*.44,y-r*.76,x-r*.44,y+r*.76), fill=CREAM, width=4)
    elif kind == 'leaf':
        draw.ellipse((x-r*.78,y-r,x+r*.78,y+r), fill=color, outline=INK, width=3)
        draw.line((x,y-r*.6,x,y+r*.6), fill=CREAM, width=3)
    elif kind == 'tile':
        draw.rounded_rectangle((x-r*.8,y-r*.8,x+r*.8,y+r*.8), radius=6, fill=color, outline=INK, width=3)
    elif kind == 'clip':
        draw.polygon([(x-r*.48,y-r),(x+r*.48,y-r),(x+r*.43,y-r*.2),(x+r*.68,y+r),
                      (x+r*.12,y+r),(x,y+r*.34),(x-r*.12,y+r),(x-r*.68,y+r),
                      (x-r*.43,y-r*.2)], fill=color, outline=INK, width=3)
        draw.line((x-r*.42,y-r*.17,x+r*.42,y-r*.17),fill=CREAM,width=5)
    else:
        draw.ellipse((x-r,y-r,x+r,y+r), fill=color, outline=INK, width=3)
        if kind == 'ball':
            draw.arc((x-r*.65,y-r*.9,x+r*.42,y+r*.75), 260, 96, fill=CREAM, width=3)
        elif kind == 'seal':
            draw.rectangle((x-r*.26,y-r*.26,x+r*.26,y+r*.26), fill=CREAM)


def row(draw, box, count, kind, color):
    x0, y0, x1, y1 = box
    radius = min(34, (y1-y0)*.26, (x1-x0-14)/(count*2.5)) if count else 0
    step = radius*2.38
    for index in range(count):
        item(draw, (x0+x1)/2+(index-(count-1)/2)*step, (y0+y1)/2, radius, kind, color)


def trays(draw, left, right, *, y=65, height=146, kind='seed', color=None, width=700):
    for i, count in enumerate((left,right)):
        x0=28+i*(width/2)
        box=(x0,y,x0+width/2-56,y+height)
        draw.rounded_rectangle(box, radius=28, outline=(TEAL,GOLD)[i], width=6,
                               fill=('#dceee5','#ffe2a6')[i])
        row(draw, box, count, kind, color or (TEAL,GOLD)[i])


def branch(draw, total, left, right, *, center, top, combine=False, scale=1):
    cx, y = center, top
    span, gap, radius = int(122*scale), int(166*scale), int(43*scale)
    nodes = [(cx,y+radius), (cx-span,y+radius+gap), (cx+span,y+radius+gap)]
    values = (total,left,right)
    if combine:
        nodes = [(cx,y+radius+gap), (cx-span,y+radius), (cx+span,y+radius)]
    for limb in nodes[1:]:
        draw.line((*nodes[0],*limb), fill=INK, width=max(4,int(8*scale)))
    for index, ((x,z), value) in enumerate(zip(nodes,values)):
        draw.ellipse((x-radius,z-radius,x+radius,z+radius), fill=('#e5f0df','#dbefe9','#ffdfa4')[index],outline=INK,width=4)
        number(draw,(x,z+1),value,int(58*scale))


def arrow(draw, *, y, x=350):
    draw.line((x+54,y,x-52,y), fill=INK, width=9)
    draw.polygon([(x-66,y),(x-40,y-18),(x-40,y+18)], fill=INK)


def save(asset_id, render, *, size=(700,280)):
    frame, draw = image(size)
    render(draw)
    frame.save(ASSETS / (asset_id+'.png'), optimize=True)


def quiz_visuals():
    save('quiz-1-prompt', lambda d: trays(d,1,2,kind='bookmark'))
    for letter, count in zip('abc',(4,3,2)):
        save(f'quiz-1-{letter}',lambda d: row(d,(75,45,625,235),count,'bookmark',TEAL))

    def ticket_prompt(draw):
        trays(draw,3,2,y=109,kind='ticket',color=RED)
        arrow(draw,y=67)
    save('quiz-2-prompt',ticket_prompt)
    for letter, (left,right) in zip('abc',((4,1),(2,3),(3,2))):
        save(f'quiz-2-{letter}',lambda d: trays(d,left,right,kind='ticket',color=RED))

    save('quiz-3-prompt',lambda d: trays(d,2,2,kind='book'))
    for letter, (left,right) in zip('abc',((1,3),(3,1),(2,2))):
        def book_branch(draw):
            branch(draw,4,left,right,center=350,top=10,combine=True,scale=.72)
            for x,count,color in ((218,left,TEAL),(482,right,GOLD)):
                row(draw,(x-120,195,x+120,282),count,'book',color)
        save(f'quiz-3-{letter}',book_branch)

    save('quiz-4-prompt',lambda d: row(d,(65,53,635,240),4,'seal',RED))
    for letter, (left,right) in zip('abc',((1,3),(2,2),(3,1))):
        save(f'quiz-4-{letter}',lambda d: trays(d,left,right,kind='seal',color=RED))

    def two_rows(draw, top, bottom):
        trays(draw,*top,y=21,height=105,kind='leaf',color=TEAL)
        trays(draw,*bottom,y=153,height=105,kind='tile',color=RED)
    def two_total_rows(draw):
        row(draw,(100,14,600,131),3,'leaf',TEAL)
        draw.line((150,138,550,138),fill='#d3b382',width=3)
        row(draw,(100,152,600,269),2,'tile',RED)
    save('quiz-5-prompt',two_total_rows)
    for letter, (top,bottom) in zip('abc',(((1,2),(1,1)),((2,1),(1,1)),((1,2),(1,2)))):
        save(f'quiz-5-{letter}',lambda d: two_rows(d,top,bottom))

    def covered(draw):
        trays(draw,1,0,y=104,height=155,kind='ball',color=RED)
        draw.rounded_rectangle((379,104,671,259),radius=28,fill='#eeb851',outline=GOLD,width=6)
        draw.rounded_rectangle((478,215,572,244),radius=10,fill='#b87024')
        for x in (232,291,350,409,468):
            draw.rounded_rectangle((x-23,24,x+23,74),radius=8,outline=TEAL,width=4)
    save('quiz-6-prompt',covered)
    for letter,count in zip('abc',(2,3,4)):
        save(f'quiz-6-{letter}',lambda d: row(d,(65,50,635,240),count,'ball',RED))


def teaching_visuals():
    def opening(draw):
        row(draw,(45,12,655,103),5,'seed',RED)
        draw.polygon([(350,136),(326,107),(374,107)], fill=INK)
        trays(draw,1,4,y=145,height=110,kind='seed',color=RED)
    save('teach-seed-groups',opening)
    save('teach-split-five',lambda d: branch(d,5,3,2,center=350,top=10))
    save('teach-join-five',lambda d: branch(d,5,3,2,center=350,top=10,combine=True))
    def split_three(draw):
        for center,left,right in ((175,1,2),(525,2,1)):
            branch(draw,3,left,right,center=center,top=38,scale=.84)
    save('teach-split-three',split_three)
    save('teach-split-two',lambda d: branch(d,2,1,1,center=350,top=10))
    save('teach-clip-groups',lambda d: trays(d,1,2,kind='clip'))


if __name__ == '__main__':
    teaching_visuals()
    quiz_visuals()
