"""Prepare registered forest art, exact notice cards, clocks, and handwriting."""
from hashlib import sha256
import json
from math import cos, pi, sin
from pathlib import Path
from statistics import median

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parent
CREAM, PINE, SAGE, ORANGE = "#fff1d7", "#24453c", "#a6b8a0", "#bd572c"
ATLAS = {
    "story-atlas": ((0,311,624,935,1247),(0,315,627,935,1261),8,
        ("tiger-assigns","bear-first","fox-asks","tiger-day","bear-second","wolf-asks","tiger-eight",
         "bear-third","deer-asks","tiger-remembers","bear-fourth","everyone-arrives",
         "forest-clearing","child-notifies","meeting-sticker","role-listeners")),
    "props-atlas": ((0,316,632,947,1263),(0,312,624,934,1246),6,
        ("bear-ready","bear-run","bear-jump","story-scroll","notice-cart","notice-cart-up",
         "dock-date","dock-time","dock-place","dock-full","exchange-paper","hop-backdrop",
         "sort-backdrop","wood-cabin","orchard","big-tree")),
    "quiz-atlas": ((0,419,834,1254),(0,418,798,1254),7,
        ("leaf-print","flowerbed","ticket-window","quiz-5-a","quiz-5-b","quiz-5-c",
         "two-places",None,None)),
}
STROKES = {
    "国": (
        ((.23,.23),(.25,.82)), ((.23,.23),(.77,.21),(.75,.82)),
        ((.37,.36),(.64,.34)), ((.39,.48),(.61,.47)), ((.51,.35),(.51,.64)),
        ((.34,.66),(.67,.64)), ((.57,.53),(.64,.59)), ((.25,.79),(.75,.78)),
    ),
    "都": (
        ((.21,.26),(.53,.25)), ((.37,.18),(.37,.42)), ((.16,.42),(.57,.40)),
        ((.51,.23),(.45,.43),(.32,.55),(.19,.62)), ((.30,.53),(.32,.81)),
        ((.30,.54),(.53,.52),(.51,.81)), ((.32,.64),(.52,.63)), ((.32,.77),(.51,.76)),
        ((.64,.27),(.85,.26),(.77,.43),(.84,.54),(.83,.63),(.76,.67)),
        ((.64,.27),(.64,.83)),
    ),
    "百": (
        ((.20,.23),(.80,.21)), ((.52,.23),(.44,.39)), ((.32,.42),(.34,.81)),
        ((.32,.42),(.72,.40),(.70,.81)), ((.34,.57),(.71,.56)), ((.34,.77),(.70,.75)),
    ),
    "点": (
        ((.48,.17),(.48,.45)), ((.48,.32),(.73,.31)),
        ((.33,.45),(.34,.63)), ((.33,.45),(.66,.43),(.65,.63)), ((.34,.62),(.65,.60)),
        ((.30,.72),(.22,.83)), ((.40,.72),(.43,.82)), ((.56,.72),(.60,.82)), ((.70,.71),(.80,.82)),
    ),
    "听": (
        ((.20,.38),(.22,.66)), ((.20,.38),(.41,.37),(.40,.66)), ((.22,.63),(.40,.62)),
        ((.80,.21),(.67,.26),(.53,.30)), ((.57,.28),(.57,.56),(.53,.70),(.46,.81)),
        ((.57,.46),(.86,.45)), ((.74,.46),(.74,.82)),
    ),
    "时": (
        ((.18,.32),(.20,.79)), ((.18,.32),(.43,.30),(.41,.79)),
        ((.20,.52),(.42,.51)), ((.20,.75),(.41,.73)), ((.48,.42),(.86,.40)),
        ((.73,.21),(.73,.76),(.70,.81),(.64,.76)), ((.53,.53),(.60,.62)),
    ),
    "林": (
        ((.16,.38),(.48,.37)), ((.32,.22),(.32,.82)),
        ((.31,.43),(.23,.63),(.14,.72)), ((.33,.48),(.44,.60)),
        ((.52,.37),(.85,.35)), ((.69,.19),(.69,.83)),
        ((.67,.41),(.59,.62),(.49,.72)), ((.70,.43),(.75,.60),(.88,.74)),
    ),
}
HOP_PICTURES = {
    "hop-tiger-icon":("tiger-assigns",(.35,.79)),
    "hop-first-icon":("bear-first",(.14,.65)),
    "hop-fox-icon":("fox-asks",(.30,.78)),
    "hop-day-icon":("tiger-day",(.37,.92)),
    "hop-wolf-icon":("wolf-asks",(.32,.86)),
    "hop-deer-icon":("deer-asks",(.36,.86)),
    "hop-plaza-icon":("forest-clearing",(.36,.91)),
    "hop-final-icon":("everyone-arrives",(.40,.89)),
}
STORY_MASKS = ((False,False,False),(True,False,False),(True,True,False),(True,True,True))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def matte_free(image):
    rgba=image.convert("RGBA")
    w,h=image.size
    corners=((5,5),(w-6,5),(5,h-6),(w-6,h-6))
    paper=[median(c) for c in zip(*(rgba.getpixel(p)[:3] for p in corners))]
    mask=Image.new("L",image.size)
    mask.putdata([255 if max(abs(v-bg) for v,bg in zip(rgb,paper))>24 else 0
                  for rgb in image.convert("RGB").getdata()])
    for p in ((0,0),(w-1,0),(0,h-1),(w-1,h-1)):
        ImageDraw.floodfill(mask,p,128)
    mask=mask.point(lambda p: 0 if p==128 else 255)
    bounds=mask.getbbox()
    if not bounds or 0 in bounds[:2] or bounds[2]==w or bounds[3]==h:
        raise ValueError("sprite reaches crop edge")
    rgba.putalpha(mask.filter(ImageFilter.GaussianBlur(.43)))
    return rgba.crop(bounds)


def board(size):
    return Image.new("RGBA",size,CREAM)


def paste(canvas, image, center, bounds):
    item=image.copy()
    item.thumbnail(bounds,Image.Resampling.LANCZOS)
    x,y=center
    canvas.alpha_composite(item,(round(x-item.width/2),round(y-item.height/2)))


def grid(items, columns, tile=205):
    rows=(len(items)+columns-1)//columns
    canvas=board((columns*tile+12,rows*tile+12))
    for i,item in enumerate(items):
        row,col=divmod(i,columns)
        paste(canvas,item,(6+col*tile+tile/2,6+row*tile+tile/2),(tile-12,tile-12))
    return canvas


def clock(hour, *, afternoon=False):
    canvas=board((240,240))
    draw=ImageDraw.Draw(canvas)
    draw.ellipse((26,26,214,214),fill="#ffe2b7",outline=ORANGE,width=9)
    for i in range(12):
        theta=i*pi/6
        x,y=120+75*sin(theta),120-75*cos(theta)
        draw.ellipse((x-3,y-3,x+3,y+3),fill=PINE)
    theta=(hour%12)*pi/6
    draw.line((120,120,120+48*sin(theta),120-48*cos(theta)),fill=PINE,width=12)
    draw.line((120,120,120,53),fill=PINE,width=8)
    draw.ellipse((111,111,129,129),fill=PINE)
    if afternoon:
        draw.ellipse((180,25,218,63),fill="#ef9a40")
    return canvas


def notice(date, time, place, *, square=False):
    canvas=board((270,270) if square else (333,145))
    draw=ImageDraw.Draw(canvas)
    w,h=canvas.size
    draw.rounded_rectangle((5,5,w-5,h-5),radius=17,fill="#f8dfac",outline=ORANGE,width=6)
    if square:
        cell=110
        slots=((17,15),(143,15),(80,141))
    else:
        cell=(w-32)//3
        slots=tuple((12+i*(cell+7),(h-cell)//2) for i in range(3))
    for (x,y),picture in zip(slots,(date,time,place)):
        draw.rounded_rectangle((x,y,x+cell,y+cell),radius=9,fill=CREAM,outline=SAGE,width=3)
        if picture is None:
            for offset in range(9,cell-11,12):
                draw.line((x+offset,y+9,x+offset+7,y+9),fill=ORANGE,width=4)
                draw.line((x+offset,y+cell-9,x+offset+7,y+cell-9),fill=ORANGE,width=4)
            draw.line((x+cell*.33,y+cell*.5,x+cell*.67,y+cell*.5),fill=ORANGE,width=6)
        else:
            paste(canvas,picture,(x+cell/2,y+cell/2),(cell-10,cell-10))
    return canvas


def notice_tally(images, masks):
    canvas=board((680,420))
    draw=ImageDraw.Draw(canvas)
    for index,mask in enumerate(masks):
        row,col=divmod(index,2)
        x,y=171+337*col,91+205*row
        options=(images["dock-date"],clock(8),images["dock-place"])
        paste(canvas,notice(*(value if flag else None for value,flag in zip(options,mask))),
              (x,y),(314,136))
        for number in range(10):
            cx=x-108+24*number
            draw.ellipse((cx-6,y+77,cx+6,y+89),fill=PINE)
    return canvas


def quiz_notices(images,masks):
    canvas=board((661,390))
    draw=ImageDraw.Draw(canvas)
    options=(images["dock-date"],clock(8),images["dock-place"])
    for index,mask in enumerate(masks):
        row,col=divmod(index,2)
        x,y=168+326*col,102+181*row
        card=notice(*(value if flag else None for value,flag in zip(options,mask)))
        paste(canvas,card,(x,y),(298,128))
        draw.ellipse((x-122,y+70,x-103,y+89),fill=PINE)
        draw.line((x-94,y+80,x+127,y+80),fill=SAGE,width=7)
    return canvas


def field(draw,x,y,size):
    draw.rounded_rectangle((x,y,x+size,y+size),radius=10,outline=SAGE,width=3)
    draw.line((x+size//2,y+3,x+size//2,y+size-3),fill="#cad5bf",width=2)
    draw.line((x+3,y+size//2,x+size-3,y+size//2),fill="#cad5bf",width=2)


def trace(draw,paths,x,y,size,orange=()):
    width=max(4,round(size*.043))
    for i,line in enumerate(paths):
        color=ORANGE if i in orange else PINE
        pixels=[(round(x+px*size),round(y+py*size)) for px,py in line]
        draw.line(pixels,fill=color,width=width,joint="curve")
        r=width//2
        for ax,ay in (pixels[0],pixels[-1]):
            draw.ellipse((ax-r,ay-r,ax+r,ay+r),fill=color)


def writing(chars,highlights):
    canvas=board((751,225*len(chars)))
    draw=ImageDraw.Draw(canvas)
    for row,char in enumerate(chars):
        top=9+225*row
        paths=STROKES[char]
        field(draw,10,top,202)
        trace(draw,paths,10,top,202,highlights[row])
        for i in range(len(paths)):
            line,col=divmod(i,5)
            x,y=231+102*col,top+101*line
            field(draw,x,y,87)
            trace(draw,paths[:i+1],x,y,87,(i,))
    return canvas


def country_card(highlight):
    canvas=board((344,320))
    draw=ImageDraw.Draw(canvas)
    field(draw,30,16,285)
    trace(draw,STROKES["国"],30,16,285,(highlight,))
    if highlight==7:
        draw.polygon(((252,240),(234,230),(234,250)),fill=ORANGE)
    return canvas


def start_card(items,player):
    canvas=board((574,286))
    draw=ImageDraw.Draw(canvas)
    draw.rounded_rectangle((12,12,562,274),radius=25,fill="#dcebd1")
    for i,item in enumerate(items):
        paste(canvas,item,(287+round((i-(len(items)-1)/2)*121),91),(106,105))
    paste(canvas,player,(287,214),(151,111))
    return canvas


def generate(root=ROOT):
    asset_dir,art_dir=root/"assets",root/"art-source"
    lesson=json.loads((root/"lesson.json").read_text())
    images,metadata,components={},{},{}
    for atlas,(xs,ys,inset,names) in ATLAS.items():
        source,prompt_path=art_dir/f"{atlas}.png",art_dir/f"{atlas}.prompt.txt"
        sheet_hash,prompt_hash,prompt=digest(source),digest(prompt_path),prompt_path.read_text()
        with Image.open(source) as sheet:
            assert sheet.size==(xs[-1],ys[-1])
            for i,name in enumerate(names):
                if name is None:
                    continue
                row,col=divmod(i,len(xs)-1)
                x0,y0,x1,y1=(xs[col]+inset,ys[row]+inset,xs[col+1]-inset,ys[row+1]-inset)
                if name in ("tiger-eight","bear-third"):
                    y1=round(y0+.61*(y1-y0))
                crop=(x0,y0,x1,y1)
                image=sheet.crop(crop).convert("RGBA")
                sprite=atlas=="props-atlas" and i<10 and name!="dock-place"
                if sprite:
                    image=matte_free(image)
                    image.thumbnail((268,268),Image.Resampling.LANCZOS)
                images[name]=image
                metadata[name]={"source":"Codex built-in image_gen","generatedSource":f"art-source/{atlas}.png",
                                "generatedSourceSha256":sheet_hash,"prompt":prompt,"promptSha256":prompt_hash,"sourceCrop":crop}
                if sprite:
                    metadata[name].update(postprocess="mint matte cleared",drawingSource="diagrams.py")

    def derive(name,picture,*inputs):
        images[name]=picture
        components[name]=inputs
        metadata[name]={"source":"composition of registered ImageGen panels" if inputs else "course-specific semantic diagram",
                        "drawingSource":"diagrams.py","components":inputs}

    for name,(source,(top,bottom)) in HOP_PICTURES.items():
        image=images[source]
        w,h=image.size
        derive(name,image.crop((0,round(top*h),w,round(bottom*h))),source)
    derive("hop-eight-icon",grid([images["tiger-eight"],clock(8)],2,150),"tiger-eight")
    visuals={
        "start-story-board":(2,("tiger-assigns","bear-first")),
        "first-message-board":(3,("bear-first","fox-asks","tiger-day")),
        "last-message-board":(3,("bear-fourth","forest-clearing","everyone-arrives")),
        "role-reading-board":(2,("role-listeners","child-notifies")),
    }
    for name,(cols,keys) in visuals.items():
        derive(name,grid([images[k] for k in keys],cols),*keys)
    second=("bear-second","wolf-asks","tiger-eight")
    derive("second-message-board",grid([*(images[k] for k in second),clock(8)],2),*second)
    third=("bear-third","deer-asks","tiger-remembers","forest-clearing")
    derive("third-message-board",grid([images[k] for k in third],2),*third)

    for name,assets in (
        ("missing-day-card",(None,10,"wood-cabin")),
        ("missing-time-card",("dock-date",None,"orchard")),
        ("missing-place-card",("dock-date",9,None)),
        ("complete-card",("dock-date",3,"big-tree")),
    ):
        date,hour,place=assets
        pic=notice(images.get(date),clock(hour,afternoon=hour==3) if hour else None,images.get(place),square=True)
        derive(name,pic,*(key for key in (date,place) if key))
    cards=("missing-day-card","missing-time-card","missing-place-card","complete-card")
    derive("sorting-examples-board",grid([images[k] for k in cards],2),*cards)
    derive("notice-rehearsal-board",grid([images[cards[0]],images[cards[1]],images[cards[2]],
                                        grid([images["complete-card"],images["exchange-paper"]],2,110)],2),
           *cards,"exchange-paper")
    derive("four-notice-board",notice_tally(images,STORY_MASKS),"dock-date","dock-place")
    for name,keys,player in (
        ("hop-start",("hop-tiger-icon","hop-fox-icon","hop-deer-icon"),"bear-ready"),
        ("sort-start",cards,"notice-cart"),
    ):
        derive(name,start_card([images[k] for k in keys],images[player]),*keys,player)
    for name,chars,highlights in (
        ("write-guo-dou-board","国都",((7,),(8,9))),
        ("write-bai-dian-board","百点",((0,),(5,6,7,8))),
        ("write-ting-shi-board","听时",((3,4),(5,))),
        ("write-lin-board","林",((3,7),)),
    ):
        derive(name,writing(chars,highlights))
    full=(True,True,True)
    for x,masks in zip("abc",((full,*STORY_MASKS[1:]),STORY_MASKS,(full,full,*STORY_MASKS[:2]))):
        derive(f"quiz-1-{x}",quiz_notices(images,masks),"dock-date","dock-place")
    for x,key in zip("abc",("dock-date","dock-time","flowerbed")):
        derive(f"quiz-2-{x}",grid([images[key]],1,300),key)
    for x,key in zip("abc",("dock-date","dock-time","two-places")):
        derive(f"quiz-3-{x}",grid([images[key],images["ticket-window"]],2,190),key,"ticket-window")
    for x,(date,place) in zip("abc",((False,True),(True,True),(True,False))):
        card=notice(images["dock-date"] if date else None,clock(9),images["wood-cabin"] if place else None)
        derive(f"quiz-4-{x}",grid([card,images["leaf-print"]],1,217),"dock-date","wood-cabin","leaf-print")
    for x,stroke in zip("abc",(7,0,6)):
        derive(f"quiz-6-{x}",country_card(stroke))

    uses={name:set() for name in images}
    for scene in lesson["scenes"]:
        key=scene["key"]
        if scene["type"]=="slide":
            uses[scene["data"]["picture"]].add(key)
        elif scene["type"]=="interactive":
            uses[scene["startImage"]].add(key)
            text=(root/"pages"/f"{scene['page']}.js").read_text()
            for name in images:
                if f"__IMG:{name}__" in text:
                    uses[name].add(key)
        else:
            for question in scene["questions"]:
                for option in question["options"].values():
                    uses[option["visual"]["image"]].add(question["id"])
    for name,inputs in reversed(tuple(components.items())):
        for source in inputs:
            uses[source].update(uses[name])
    assert lesson["images"].keys()<=images.keys() and all(uses.values())
    rows=[]
    for name,image in images.items():
        dest=asset_dir/f"{name}.png"
        image.save(dest,format="PNG",optimize=True)
        rows.append({"assetKey":name,"path":str(dest.relative_to(root)),"sha256":digest(dest),
                     "width":image.width,"height":image.height,"usedBy":sorted(uses[name]),**metadata[name]})
    (root/"asset-sources.json").write_text(json.dumps(
        {"schemaVersion":"mira.courseware.asset-sources.v1","assets":rows},ensure_ascii=False,indent=2)+"\n")


if __name__=="__main__":
    generate()
