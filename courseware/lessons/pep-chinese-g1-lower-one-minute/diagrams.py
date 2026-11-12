"""Prepare the story art and exact glyph diagrams for 一分钟."""
from hashlib import sha256
import json
from math import atan2, cos, sin
from pathlib import Path
from statistics import median

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parent
CREAM, PINE, SAGE, ORANGE = "#fff1d7", "#24453c", "#a6b8a0", "#bd572c"
FONT = "/System/Library/Fonts/Supplemental/Songti.ttc"
DIGITS = "/System/Library/Fonts/Supplemental/Arial.ttf"
ATLAS = {
    "story-atlas": ((0,315,630,944,1261),(0,313,623,934,1247),7,
        ("alarm-bed","sit-up","wash-face","eat-breakfast","leave-home","wait-curb","cross-green",
         "miss-bus","empty-stop","walk-sidewalk","class-door","sorry-in-class","prepare-ahead",
         "family-minute","minute-sticker","morning-kit")),
    "word-atlas": ((0,419,832,1254),(0,419,831,1254),8,
        ("alarm-word","watch-word","sit-word","wait-word","back-carry","back-point","front-carry",
         "empty-chair","adult-timer")),
    "game-atlas": ((0,362,724,1086,1448),(0,362,724,1086),7,
        ("route-rover","route-rover-pop","word-boat","word-boat-pop","bus-icon","route-alarm-icon",
         None,"bubble-effect","route-backdrop","word-backdrop",None,None)),
    "quiz-atlas": ((0,362,724,1086),(0,362,724,1086,1448),5,
        tuple(f"quiz-{n}-{x}" for n in (1,2,4,6) for x in "abc")),
}
STROKES = {
    "元": (
        ((.36,.25),(.65,.23)), ((.21,.45),(.79,.43)), ((.43,.45),(.39,.64),(.26,.82)),
        ((.58,.45),(.57,.68),(.58,.76),(.64,.80),(.79,.79),(.83,.72)),
    ),
    "车": (
        ((.29,.26),(.72,.24)), ((.51,.20),(.36,.49),(.70,.47)),
        ((.21,.64),(.81,.61)), ((.55,.40),(.55,.84)),
    ),
    "灯": (
        ((.24,.38),(.21,.51)), ((.44,.34),(.37,.48)),
        ((.33,.24),(.33,.53),(.27,.69),(.17,.80)), ((.34,.60),(.44,.72)),
        ((.52,.34),(.83,.32)), ((.71,.34),(.70,.80),(.64,.83),(.59,.77)),
    ),
    "站": (
        ((.30,.18),(.36,.25)), ((.17,.34),(.48,.32)), ((.23,.41),(.27,.55)),
        ((.41,.39),(.37,.60)), ((.18,.69),(.47,.64)),
        ((.64,.19),(.64,.49)), ((.64,.33),(.81,.31)), ((.55,.49),(.56,.81)),
        ((.55,.49),(.84,.48),(.82,.80)), ((.56,.77),(.82,.76)),
    ),
    "坐": (
        ((.38,.24),(.32,.40),(.23,.49)), ((.34,.37),(.43,.48)),
        ((.67,.24),(.61,.39),(.54,.47)), ((.64,.37),(.75,.47)),
        ((.28,.59),(.73,.57)), ((.51,.35),(.51,.79)), ((.19,.80),(.82,.77)),
    ),
    "老": (
        ((.32,.25),(.65,.24)), ((.48,.17),(.48,.42)),
        ((.21,.42),(.79,.40)), ((.70,.28),(.56,.48),(.39,.59),(.22,.67)),
        ((.69,.51),(.57,.60),(.45,.65)), ((.44,.52),(.43,.69),(.44,.77),(.49,.81),(.71,.81),(.78,.74)),
    ),
    "师": (
        ((.29,.28),(.29,.55)), ((.42,.22),(.41,.52),(.36,.69),(.25,.82)),
        ((.51,.26),(.85,.24)), ((.54,.40),(.54,.77)),
        ((.54,.40),(.84,.39),(.82,.73),(.77,.69)), ((.69,.26),(.69,.83)),
    ),
}
ROUTE_CROPS = {
    "route-rise-icon": ("sit-up",(.14,.04,.91,.94)),
    "route-bag-icon": ("leave-home",(.20,.18,.82,.94)),
    "route-curb-icon": ("wait-curb",(.09,.01,.80,.84)),
    "route-cross-icon": ("cross-green",(.21,.01,.83,.88)),
    "route-bus-icon": ("miss-bus",(.25,.20,.99,.87)),
    "route-wait-icon": ("empty-stop",(.04,.12,.87,.93)),
    "route-walk-icon": ("walk-sidewalk",(.12,.13,.72,.92)),
    "route-class-icon": ("class-door",(.13,.12,.95,.89)),
}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def matte_free(image):
    rgba = image.convert("RGBA")
    w,h = image.size
    corners = ((5,5),(w-6,5),(5,h-6),(w-6,h-6))
    paper = [median(c) for c in zip(*(rgba.getpixel(p)[:3] for p in corners))]
    mask = Image.new("L",image.size)
    mask.putdata([255 if max(abs(v-bg) for v,bg in zip(rgb,paper))>24 else 0
                  for rgb in image.convert("RGB").getdata()])
    for p in ((0,0),(w-1,0),(0,h-1),(w-1,h-1)):
        ImageDraw.floodfill(mask,p,128)
    mask = mask.point(lambda p: 0 if p==128 else 255)
    bounds = mask.getbbox()
    if not bounds or 0 in bounds[:2] or bounds[2]==w or bounds[3]==h:
        raise ValueError("sprite reaches crop edge")
    rgba.putalpha(mask.filter(ImageFilter.GaussianBlur(.44)))
    return rgba.crop(bounds)


def board(size):
    return Image.new("RGBA",size,CREAM)


def paste(canvas, item, center, size):
    image=item.copy()
    image.thumbnail(size,Image.Resampling.LANCZOS)
    x,y=center
    canvas.alpha_composite(image,(round(x-image.width/2),round(y-image.height/2)))


def arrow(draw, x, y):
    draw.line((x-11,y,x+10,y),width=5,fill=ORANGE)
    draw.polygon(((x+14,y),(x+6,y-7),(x+6,y+7)),fill=ORANGE)


def grid(items, columns, tile=195, sequence=False):
    rows=(len(items)+columns-1)//columns
    canvas=board((columns*tile+14, rows*tile+14))
    draw=ImageDraw.Draw(canvas)
    for i,item in enumerate(items):
        row,col=divmod(i,columns)
        x,y=7+col*tile+tile/2,7+row*tile+tile/2
        pad=29 if sequence else 16
        paste(canvas,item,(x,y),(tile-pad,tile-pad))
        if sequence and i+1<len(items) and col+1<columns:
            arrow(draw,x+tile/2,y)
    return canvas


def route_card(items, vehicle, bubble):
    canvas=board((573,284))
    draw=ImageDraw.Draw(canvas)
    draw.rounded_rectangle((12,12,561,272),radius=26,fill="#dcebd1")
    for i,item in enumerate(items):
        paste(canvas,item,(286+round((i-(len(items)-1)/2)*119),93),(105,101))
    paste(canvas,vehicle,(278,214),(159,114))
    paste(canvas,bubble,(403,204),(39,39))
    return canvas


def field(draw,x,y,size):
    draw.rounded_rectangle((x,y,x+size,y+size),radius=10,outline=SAGE,width=3)
    draw.line((x+size//2,y+3,x+size//2,y+size-3),fill="#cad5bf",width=2)
    draw.line((x+3,y+size//2,x+size-3,y+size//2),fill="#cad5bf",width=2)


def trace(draw, paths, x, y, size, orange=()):
    width=max(4,round(size*.043))
    for i,line in enumerate(paths):
        color=ORANGE if i in orange else PINE
        pixels=[(round(x+px*size),round(y+py*size)) for px,py in line]
        draw.line(pixels,fill=color,width=width,joint="curve")
        radius=width//2
        for ax,ay in (pixels[0],pixels[-1]):
            draw.ellipse((ax-radius,ay-radius,ax+radius,ay+radius),fill=color)


def writing(chars, highlights):
    canvas=board((751,225*len(chars)))
    draw=ImageDraw.Draw(canvas)
    for i,char in enumerate(chars):
        top=10+225*i
        paths=STROKES[char]
        field(draw,10,top,202)
        trace(draw,paths,10,top,202,highlights[i])
        for j in range(len(paths)):
            row,col=divmod(j,5)
            x,y=231+102*col,top+101*row+(47 if len(paths)<=5 else 0)
            field(draw,x,y,87)
            trace(draw,paths[:j+1],x,y,87,(j,))
    return canvas


def yi_paths(height):
    return (((.29,.24),(.73,.23),(.71,.46)),
            ((.31,.47),(.71,.45)),
            ((.32,height),(.31,.70),(.32,.78),(.39,.82),(.71,.81),(.77,.73)))


def yi_card(height):
    canvas=board((352,327))
    draw=ImageDraw.Draw(canvas)
    field(draw,30,16,290)
    trace(draw,yi_paths(height),30,16,290)
    return canvas


def stroke_card(path):
    canvas=board((346,322))
    draw=ImageDraw.Draw(canvas)
    x,y,size=31,15,285
    field(draw,x,y,size)
    trace(draw,(path,),x,y,size,(0,))
    (x1,y1),(x2,y2)=path[-2:]
    direction=atan2(y2-y1,x2-x1)
    tip=(x+x2*size+cos(direction)*15,y+y2*size+sin(direction)*15)
    points=[(tip[0]-24*cos(direction+angle),tip[1]-24*sin(direction+angle)) for angle in (-.52,.52)]
    draw.polygon([tip,*points],fill=ORANGE)
    return canvas


def timer_face(image, center, font_size):
    bitmap=image.copy()
    draw=ImageDraw.Draw(bitmap)
    draw.text(center,"1:00",font=ImageFont.truetype(DIGITS,font_size),anchor="mm",fill="#233e3a")
    return bitmap


def generate(root=ROOT):
    asset_dir, art_dir=root/"assets",root/"art-source"
    lesson=json.loads((root/"lesson.json").read_text())
    images,metadata,components={},{},{}
    for atlas,(xs,ys,inset,names) in ATLAS.items():
        sheet_path,prompt_path=art_dir/f"{atlas}.png",art_dir/f"{atlas}.prompt.txt"
        sheet_hash,prompt_hash,prompt=digest(sheet_path),digest(prompt_path),prompt_path.read_text()
        with Image.open(sheet_path) as sheet:
            assert sheet.size==(xs[-1],ys[-1])
            for i,name in enumerate(names):
                if name is None:
                    continue
                row,col=divmod(i,len(xs)-1)
                crop=(xs[col]+inset,ys[row]+inset,xs[col+1]-inset,ys[row+1]-inset)
                if name=="quiz-6-b":
                    crop=(*crop[:2],613,crop[3])
                bitmap=sheet.crop(crop).convert("RGBA")
                sprite=atlas=="game-atlas" and i<8
                if sprite:
                    bitmap=matte_free(bitmap)
                if name=="quiz-6-a":
                    bitmap=timer_face(bitmap,(93,193),29)
                if sprite or atlas=="word-atlas":
                    bitmap.thumbnail((268,268),Image.Resampling.LANCZOS)
                images[name]=bitmap
                metadata[name]={"source":"Codex built-in image_gen","generatedSource":f"art-source/{atlas}.png",
                                "generatedSourceSha256":sheet_hash,"prompt":prompt,"promptSha256":prompt_hash,"sourceCrop":crop}
                if sprite or name=="quiz-6-a":
                    metadata[name].update(drawingSource="diagrams.py",
                       postprocess="mint matte cleared" if sprite else "typed timer setup added to display")

    def derive(name, picture, *inputs):
        images[name]=picture
        components[name]=inputs
        metadata[name]={"source":"composition of registered ImageGen panels" if inputs else "course-specific semantic diagram",
                        "drawingSource":"diagrams.py","components":inputs}

    for name,(source,crop) in ROUTE_CROPS.items():
        image=images[source]
        w,h=image.size
        derive(name,image.crop(tuple(round(v*(w if i%2==0 else h)) for i,v in enumerate(crop))),source)

    boards={
        "alarm-and-bed-board":(3,("alarm-bed","sit-up","morning-kit"),True),
        "morning-routine-board":(3,("wash-face","eat-breakfast","leave-home","back-point"),False),
        "crossing-board":(2,("wait-curb","cross-green"),True),
        "bus-walking-board":(3,("miss-bus","empty-stop","walk-sidewalk"),True),
        "route-rehearsal-board":(3,("alarm-bed","leave-home","wait-curb","miss-bus","walk-sidewalk","class-door"),True),
        "if-earlier-board":(2,("wait-curb","miss-bus","prepare-ahead","cross-green"),False),
        "listening-words-board":(3,("alarm-word","watch-word","sit-word","wait-word","back-carry",
                                      "back-point","front-carry","empty-chair"),False),
        "minute-experiment-board":(2,("adult-timer","family-minute"),True),
    }
    for name,(columns,keys,sequence) in boards.items():
        derive(name,grid([images[key] for key in keys],columns,sequence=sequence),*keys)
    derive("arriving-board",grid([images["class-door"],images["sorry-in-class"],yi_card(.35),yi_card(.49)],2),
           "class-door","sorry-in-class")
    for name,keys,vehicle in (
            ("route-start",("route-alarm-icon","route-curb-icon","bus-icon","route-class-icon"),"route-rover"),
            ("words-start",("alarm-word","watch-word","back-carry"),"word-boat")):
        derive(name,route_card([images[k] for k in keys],images[vehicle],images["bubble-effect"]),
               *keys,vehicle,"bubble-effect")
    for name,chars,highlights in (
            ("write-yuan-che-board","元车",((3,),(3,))),
            ("write-deng-zhan-board","灯站",((5,),(4,))),
            ("write-zuo-board","坐",((6,),)),
            ("write-lao-shi-board","老师",((4,),(0,)))):
        derive(name,writing(chars,highlights))
    for x,h in zip("abc",(.49,.24,.35)):
        derive(f"quiz-3-{x}",yi_card(h))
    hook=STROKES["元"][-1]
    for x,steps in zip("abc",(((.64,.31),(.53,.54),(.33,.72)),hook[:-1],hook)):
        derive(f"quiz-5-{x}",stroke_card(steps))

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
