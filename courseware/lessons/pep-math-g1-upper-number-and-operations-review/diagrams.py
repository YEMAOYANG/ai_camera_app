"""Draw precise counts, place value, arrows, and arithmetic for this lesson."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
PINE, CREAM, ORANGE, SAGE = "#254537", "#fff2d7", "#b9542b", "#83a284"


def board(size):
    return Image.new("RGBA",size,CREAM)


def label(draw, center, value, size=30, color=PINE):
    draw.text(center,str(value),font=ImageFont.truetype(FONT,size),fill=color,anchor="mm")


def paste(canvas, sprite, center, max_size):
    item = sprite.copy()
    item.thumbnail((max_size,max_size),Image.Resampling.LANCZOS)
    x,y=center
    canvas.alpha_composite(item,(round(x-item.width/2),round(y-item.height/2)))


def dots(draw, value, x, y, spacing, *, columns=5, color=ORANGE):
    radius=spacing*.28
    for i in range(value):
        px,py=x+(i%columns)*spacing,y+(i//columns)*spacing
        draw.ellipse((px-radius,py-radius,px+radius,py+radius),fill=color)


def frame_ten(draw, value, x, y, spacing, fill=ORANGE):
    for i in range(10):
        left,top=x+(i%5)*spacing,y+(i//5)*spacing
        draw.rounded_rectangle((left,top,left+spacing-2,top+spacing-2),radius=spacing/7,
            fill="#fcdeab",outline=SAGE,width=max(1,round(spacing/16)))
        if i<value:
            r=spacing*.28; cx,cy=left+spacing/2,top+spacing/2
            draw.ellipse((cx-r,cy-r,cx+r,cy+r),fill=fill)


def arrow(draw, start, finish, color=ORANGE, width=6):
    x,y=finish
    draw.line((start,finish),fill=color,width=width)
    if abs(finish[0]-start[0]) >= abs(finish[1]-start[1]):
        dx=13 if x>start[0] else -13
        head=((x,y),(x-dx,y-8),(x-dx,y+8))
    else:
        dy=13 if y>start[1] else -13
        head=((x,y),(x-8,y-dy),(x+8,y-dy))
    draw.polygon(head,fill=color)


def game_count(n):
    frame=board((232,176)); draw=ImageDraw.Draw(frame)
    if n <= 10:
        frame_ten(draw,n,16,48,40)
    else:
        frame_ten(draw,10,16,16,40,PINE)
        dots(draw,n-10,36,119,40)
    return frame


def stamps(frame, sprite, value, x, y, step, columns):
    for i in range(value):
        paste(frame,sprite,(x+(i%columns)*step,y+(i//columns)*step),round(step*.82))


def ordinal(star, n, selected=None, *, from_right=False):
    frame=board((494,242))
    draw=ImageDraw.Draw(frame)
    start, finish = ((470,122),(425,122)) if from_right else ((18,122),(73,122))
    arrow(draw,start,finish,PINE,8)
    stamps(frame,star,n,114,122,53,n)
    if selected is not None:
        x=114+(n-selected if from_right else selected-1)*53
        draw.ellipse((x-24,97,x+24,147),outline=ORANGE,width=6)
    return frame


def equal_groups(star, circle, left, right, columns):
    frame=board((515,275))
    draw=ImageDraw.Draw(frame)
    draw.rounded_rectangle((13,29,243,243),radius=18,outline=SAGE,width=4)
    draw.rounded_rectangle((270,29,500,243),radius=18,outline=SAGE,width=4)
    stamps(frame,circle,left,48,81,42,5)
    stamps(frame,star,right,305,82,47,columns)
    return frame


def number_pair(left, right):
    frame=board((460,252))
    draw=ImageDraw.Draw(frame)
    for x,num in ((111,left),(349,right)):
        draw.rounded_rectangle((x-67,55,x+67,194),radius=22,fill="#eed4a4",outline=SAGE,width=4)
        label(draw,(x,118),num,84)
    arrow(draw,(187,124),(272,124),PINE,7)
    return frame


def stack_ten(value):
    frame=board((470,252))
    draw=ImageDraw.Draw(frame)
    frame_ten(draw,10,28,63,37,PINE)
    if value==20:
        frame_ten(draw,10,243,63,37,PINE)
    else:
        dots(draw,value-10,267,82,38)
    return frame


def operation_tile(star,n):
    frame=board((470,252))
    stamps(frame,star,n,91,75,68,5)
    return frame


def number_line(start, steps, *, extra=1):
    frame=board((470,230))
    draw=ImageDraw.Draw(frame)
    max_range=max(5,steps+extra)
    dx=386/max_range
    arrow(draw,(24,133),(451,133),PINE,5)
    for i in range(max_range+1):
        x=39+dx*i
        draw.line((x,117,x,151),fill=PINE,width=3)
        label(draw,(x,174),start+i,29)
        if i < steps:
            nx=x+dx
            draw.arc((x,63,nx,126),188,353,fill=ORANGE,width=5)
            draw.polygon(((nx,96),(nx-12,89),(nx-5,108)),fill=ORANGE)
    stop=39+dx*steps
    draw.ellipse((stop-11,122,stop+11,144),fill=ORANGE)
    return frame


def fill_move(initial, outside, move):
    frame=board((520,285))
    draw=ImageDraw.Draw(frame)
    frame_ten(draw,initial,24,48,43,PINE)
    dots(draw,outside,308,92,40,color=ORANGE)
    for i in range(move):
        x=308+i*40
        draw.ellipse((x-17,75,x+17,109),outline=PINE,width=3)
    arrow(draw,(296,147),(241,147),PINE,6)
    frame_ten(draw,min(10,initial+move),24,176,43,PINE)
    dots(draw,outside-move,308,202,40,color=ORANGE)
    if initial+move>10:
        dots(draw,initial+move-10,272,198,37,color=ORANGE)
        draw.ellipse((256,182,288,214),outline=ORANGE,width=4)
    return frame


def bundle_ten(star):
    frame=board((480,245))
    draw=ImageDraw.Draw(frame)
    stamps(frame,star,10,31,89,40,5)
    arrow(draw,(219,110),(264,110),PINE,6)
    frame_ten(draw,10,280,79,35,PINE)
    return frame


def grid(pictures, size):
    w,h=size
    frame=board((w*2+27,h*2+27))
    for i,picture in enumerate(pictures):
        row,col=divmod(i,2)
        item=picture.copy()
        item.thumbnail((w,h),Image.Resampling.LANCZOS)
        x=9+col*(w+9)+(w-item.width)//2
        y=9+row*(h+9)+(h-item.height)//2
        frame.alpha_composite(item,(x,y))
    return frame


def facts(star,circle):
    frame=board((690,475)); draw=ImageDraw.Draw(frame)
    stamps(frame,circle,6,64,83,50,6)
    stamps(frame,star,7,363,83,44,7)
    draw.line((332,47,332,122),fill=SAGE,width=4)
    draw.line((29,141,651,141),fill=PINE,width=4)
    label(draw,(330,177),"13",43)
    for i,formula in enumerate(("6 + 7 = 13","7 + 6 = 13","13 − 6 = 7","13 − 7 = 6")):
        y,x=divmod(i,2)
        left=43+x*325; top=215+y*109
        draw.rounded_rectangle((left,top,left+282,top+84),radius=18,outline=SAGE,width=3)
        label(draw,(left+141,top+42),formula,42)
    return frame


def abacus(tens, ones):
    frame=board((470,250)); draw=ImageDraw.Draw(frame)
    for x,n,title in ((143,tens,"十位"),(328,ones,"个位")):
        draw.line((x,28,x,149),fill=PINE,width=8)
        for i in range(n):
            top=133-i*20
            draw.rounded_rectangle((x-28,top,x+28,top+16),radius=8,fill=ORANGE)
        draw.rounded_rectangle((x-59,155,x+59,196),radius=10,fill="#efd6a3")
        label(draw,(x,174),title,32)
        label(draw,(x,224),n,42)
    return frame


def render(root=ROOT):
    def save(name,image):
        image.save(root/"assets"/(name+".png"),optimize=True)
    with Image.open(root/"art-source/star-stamp.png") as raw:
        star=raw.convert("RGBA")
    with Image.open(root/"art-source/circle-stamp.png") as raw:
        circle=raw.convert("RGBA")
    for n in (*range(1,13),13,14,15,16,18):
        save("count-"+str(n),game_count(n))
    save("count-and-position",grid([
        equal_groups(star,circle,6,6,3),ordinal(star,6,4),
        operation_tile(circle,6),ordinal(star,6,4,from_right=True)],(380,200)))
    save("number-order",grid([
        number_line(11,3),number_pair(13,14),stack_ten(14),stack_ten(17)],(385,235)))
    save("tens-and-ones",grid([
        bundle_ten(star),stack_ten(14),abacus(1,4),stack_ten(20)],(385,225)))
    save("part-and-whole",facts(star,circle))
    save("methods",grid([
        stack_ten(14),number_line(10,4),number_pair(10,14),abacus(1,4)],(385,222)))
    save("make-a-ten",fill_move(9,6,1))
    save("knowledge-map",grid([
        operation_tile(star,15),number_line(13,2),stack_ten(15),fill_move(9,6,1)],(385,240)))
    for suffix,n in zip("abc",(6,8,7)):
        save(f"quiz-1-{suffix}",equal_groups(star,circle,7,n,4))
    for suffix,n in zip("abc",(2,3,4)):
        save(f"quiz-2-{suffix}",ordinal(star,5,n))
    for suffix,n in zip("abc",(17,15,18)):
        save(f"quiz-3-{suffix}",number_pair(16,n))
    for suffix,n in zip("abc",(17,18,19)):
        save(f"quiz-4-{suffix}",stack_ten(n))
    for suffix,n in zip("abc",(12,13,16)):
        save(f"quiz-5-{suffix}",stack_ten(n))
    for suffix,n in zip("abc",(5,6,7)):
        save(f"quiz-6-{suffix}",operation_tile(star,n))
    for suffix,n in zip("abc",(2,1,3)):
        save(f"quiz-7-{suffix}",fill_move(8,7,n))
    for suffix,n in zip("abc",(2,4,3)):
        save(f"quiz-8-{suffix}",number_line(11,n))


if __name__ == "__main__":
    render()
