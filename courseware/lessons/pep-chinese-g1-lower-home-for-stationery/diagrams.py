"""Prepare registered artwork and exact handwriting examples for 文具的家."""
from hashlib import sha256
import json
from pathlib import Path
from statistics import median

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parent
CREAM, PINE, SAGE, ORANGE = "#fff1d7", "#24453c", "#a6b8a0", "#bd572c"
FONT = "/System/Library/Fonts/Supplemental/Songti.ttc"
ATLAS = {
    "story-atlas": ((0,362,724,1086,1448),(0,362,724,1086),7,
        ("looking-for-pencil","scattered-tools","looking-for-eraser","asking-mother","mother-suggests",
         "case-in-bag","three-tools-in-case","checking-tools","brush-goes-in","lid-goes-on",
         "touch-closed-box","stationery-sticker")),
    "word-atlas": ((0,420,842,1262),(0,415,831,1246),5,
        ("fresh-book","new-year","new-rider","open-window","safe-home","flat-path",
         "partners","together","reading-alone")),
    "game-atlas": ((0,362,724,1086,1448),(0,362,724,1086),7,
        ("pencil","eraser","sharpener","case","cubby","palette","delivery-rover","delivery-rover-load",
         "word-boat","word-boat-pop","delivery-backdrop","word-backdrop")),
    "quiz-atlas": ((0,362,724,1086),(0,362,724,1086,1448),9,
        tuple(f"quiz-{n}-{x}" for n in (1,2,3,6) for x in "abc")),
}

# Normalized centerlines in the sequence recorded in official-notes.json.
STROKES = {
    "笔": (
        ((.30,.19),(.25,.32)), ((.27,.25),(.45,.24)), ((.35,.26),(.40,.33)),
        ((.60,.18),(.54,.30)), ((.57,.24),(.78,.22)), ((.65,.25),(.70,.32)),
        ((.64,.37),(.50,.41),(.35,.43)), ((.36,.51),(.69,.48)),
        ((.31,.62),(.77,.58)), ((.52,.42),(.51,.69),(.52,.77),(.57,.81),(.75,.81),(.80,.74)),
    ),
    "知": (
        ((.30,.22),(.24,.40)), ((.26,.32),(.46,.30)), ((.20,.49),(.50,.47)),
        ((.36,.32),(.34,.58),(.25,.76),(.19,.82)), ((.36,.58),(.49,.73)),
        ((.57,.40),(.60,.74)), ((.57,.40),(.80,.38),(.77,.72)), ((.60,.71),(.77,.70)),
    ),
    "道": (
        ((.47,.16),(.52,.23)), ((.67,.15),(.63,.24)), ((.41,.27),(.78,.26)),
        ((.59,.27),(.55,.37)), ((.47,.37),(.48,.68)), ((.47,.37),(.72,.35),(.71,.68)),
        ((.48,.46),(.71,.45)), ((.48,.55),(.71,.54)), ((.48,.65),(.71,.64)),
        ((.24,.29),(.31,.36)), ((.18,.46),(.35,.44),(.30,.53),(.36,.59),(.26,.74)),
        ((.17,.79),(.28,.75),(.49,.80),(.72,.83),(.84,.79)),
    ),
    "放": (
        ((.35,.19),(.40,.26)), ((.19,.32),(.49,.31)),
        ((.32,.43),(.46,.42),(.44,.72),(.41,.76),(.35,.69)),
        ((.32,.32),(.30,.56),(.24,.73),(.17,.81)),
        ((.62,.19),(.55,.43)), ((.58,.35),(.83,.33)),
        ((.73,.36),(.68,.58),(.58,.74),(.47,.83)), ((.57,.47),(.65,.64),(.83,.82)),
    ),
    "平": (
        ((.30,.23),(.70,.21)), ((.35,.34),(.42,.46)), ((.67,.33),(.60,.48)),
        ((.19,.57),(.82,.55)), ((.50,.43),(.50,.84)),
    ),
    "安": (
        ((.48,.17),(.55,.23)), ((.28,.28),(.25,.42)),
        ((.29,.32),(.78,.30),(.74,.40)),
        ((.49,.40),(.38,.59),(.54,.68),(.70,.79)),
        ((.65,.46),(.58,.65),(.46,.77),(.31,.82)), ((.23,.53),(.79,.51)),
    ),
    "盒": (
        ((.50,.17),(.34,.32),(.23,.38)), ((.50,.17),(.65,.31),(.77,.38)), ((.39,.36),(.62,.35)),
        ((.37,.43),(.39,.58)), ((.37,.43),(.65,.42),(.63,.58)), ((.39,.56),(.63,.55)),
        ((.29,.65),(.31,.83)), ((.29,.65),(.72,.64),(.71,.83)),
        ((.44,.65),(.45,.82)), ((.58,.65),(.58,.82)), ((.20,.83),(.81,.82)),
    ),
}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def matte_free(image):
    rgba = image.convert("RGBA")
    width, height = image.size
    points = ((5,5),(width-6,5),(5,height-6),(width-6,height-6))
    paper = [median(channel) for channel in zip(*(rgba.getpixel(p)[:3] for p in points))]
    mask = Image.new("L", image.size)
    mask.putdata([255 if max(abs(v-bg) for v,bg in zip(rgb,paper)) > 23 else 0
                  for rgb in image.convert("RGB").getdata()])
    for corner in ((0,0),(width-1,0),(0,height-1),(width-1,height-1)):
        ImageDraw.floodfill(mask, corner, 128)
    mask = mask.point(lambda p: 0 if p == 128 else 255)
    box = mask.getbbox()
    if not box or 0 in box[:2] or box[2] == width or box[3] == height:
        raise ValueError("sprite cut touches its original crop edge")
    rgba.putalpha(mask.filter(ImageFilter.GaussianBlur(.45)))
    return rgba.crop(box)


def board(size):
    return Image.new("RGBA", size, CREAM)


def paste(canvas, image, center, bounds):
    item = image.copy()
    item.thumbnail(bounds, Image.Resampling.LANCZOS)
    x, y = center
    canvas.alpha_composite(item, (round(x-item.width/2), round(y-item.height/2)))


def grid(items, columns, tile=200):
    rows = (len(items) + columns - 1) // columns
    canvas = board((columns*tile+10, rows*tile+10))
    for i, image in enumerate(items):
        row, col = divmod(i, columns)
        paste(canvas, image, (5+col*tile+tile/2, 5+row*tile+tile/2), (tile-14,tile-14))
    return canvas


def arrow(draw, x, y):
    draw.line((x-11,y,x+10,y), width=5, fill=ORANGE)
    draw.polygon(((x+14,y),(x+6,y-7),(x+6,y+7)), fill=ORANGE)


def pair(left, right):
    canvas = board((608, 310))
    paste(canvas, left, (142,155), (271,280))
    paste(canvas, right, (466,155), (271,280))
    arrow(ImageDraw.Draw(canvas), 304, 155)
    return canvas


def field(draw, x, y, size):
    draw.rounded_rectangle((x,y,x+size,y+size), radius=10, outline=SAGE, width=3)
    draw.line((x+size//2,y+3,x+size//2,y+size-3), fill="#cad5bf", width=2)
    draw.line((x+3,y+size//2,x+size-3,y+size//2), fill="#cad5bf", width=2)


def trace(draw, paths, x, y, size, orange=()):
    width = max(4,round(size*.039))
    for i, line in enumerate(paths):
        pixels = [(round(x+px*size),round(y+py*size)) for px,py in line]
        color = ORANGE if i in orange else PINE
        draw.line(pixels, fill=color, width=width, joint="curve")
        r = width // 2
        for ax,ay in (pixels[0],pixels[-1]):
            draw.ellipse((ax-r,ay-r,ax+r,ay+r), fill=color)


def writing(chars, highlights):
    canvas = board((802, 236*len(chars)))
    draw = ImageDraw.Draw(canvas)
    for row, char in enumerate(chars):
        top = 9 + 236*row
        paths = STROKES[char]
        field(draw, 9, top, 212)
        trace(draw, paths, 9, top, 212, highlights[row])
        for i in range(len(paths)):
            line, col = divmod(i,6)
            x,y = 232+93*col,top+106*line+(47 if len(paths)<=6 else 0)
            field(draw, x,y, 84)
            trace(draw, paths[:i+1], x,y,84,(i,))
    return canvas


def box_glyph(orange):
    canvas = board((345, 326))
    draw = ImageDraw.Draw(canvas)
    field(draw, 30, 16, 290)
    trace(draw, STROKES["盒"], 30,16,290,orange)
    return canvas


def printed_ju():
    canvas = board((307, 307))
    draw = ImageDraw.Draw(canvas)
    draw.text((153,150), "具", font=ImageFont.truetype(FONT,200), fill=PINE, anchor="mm")
    return canvas


def preview(items, vehicle):
    canvas = board((563, 282))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((10,10,553,271), radius=28, fill="#dfebd0")
    for i, image in enumerate(items):
        paste(canvas,image,(282+round((i-(len(items)-1)/2)*120),92),(108,103))
    paste(canvas,vehicle,(281,208),(167,116))
    return canvas


def generate(root=ROOT):
    asset_dir, art_dir = root/"assets", root/"art-source"
    lesson = json.loads((root/"lesson.json").read_text())
    images, metadata, components = {}, {}, {}
    for atlas, (xs,ys,inset,names) in ATLAS.items():
        sheet_path, prompt_path = art_dir/f"{atlas}.png", art_dir/f"{atlas}.prompt.txt"
        sheet_sha, prompt_sha, prompt = digest(sheet_path), digest(prompt_path), prompt_path.read_text()
        with Image.open(sheet_path) as sheet:
            assert sheet.size == (xs[-1],ys[-1])
            for i,name in enumerate(names):
                row,col = divmod(i,len(xs)-1)
                cut = (xs[col]+inset,ys[row]+inset,xs[col+1]-inset,ys[row+1]-inset)
                bitmap = sheet.crop(cut).convert("RGBA")
                sprite = atlas=="game-atlas" and i<10
                if sprite:
                    bitmap = matte_free(bitmap)
                if sprite or atlas=="word-atlas":
                    bitmap.thumbnail((275,275), Image.Resampling.LANCZOS)
                images[name] = bitmap
                metadata[name] = {"source":"Codex built-in image_gen","generatedSource":f"art-source/{atlas}.png",
                                  "generatedSourceSha256":sheet_sha,"prompt":prompt,"promptSha256":prompt_sha,
                                  "sourceCrop":cut}
                if sprite:
                    metadata[name].update(postprocess="mint matte cleared",drawingSource="diagrams.py")

    def derive(name, picture, *inputs):
        images[name] = picture
        components[name] = inputs
        metadata[name] = {"source":"composition of registered ImageGen panels" if inputs else "course-specific semantic diagram",
                          "drawingSource":"diagrams.py","components":inputs}

    lost = ("looking-for-pencil","scattered-tools","looking-for-eraser")
    derive("lost-stationery-board",grid([*(images[k] for k in lost),printed_ju()],2),*lost)
    family = ("asking-mother","mother-suggests")
    derive("home-dialogue-board",grid([images[k] for k in family],2,260),*family)
    derive("quick-action-board",pair(images["fresh-book"],images["cubby"]),"fresh-book","cubby")
    derive("stationery-case-board",grid([images["case-in-bag"],box_glyph(range(6,11))],2,270),"case-in-bag")
    derive("check-stationery-board",pair(images["three-tools-in-case"],images["checking-tools"]),"three-tools-in-case","checking-tools")
    sets = {
        "delivery-practice-board": (3,("pencil","eraser","sharpener","case","cubby","palette")),
        "new-words-board": (2,("fresh-book","new-year","new-rider","open-window")),
        "flat-words-board": (3,("safe-home","flat-path","reading-alone")),
        "companion-words-board": (2,("partners","together")),
    }
    for name,(columns,keys) in sets.items():
        derive(name,grid([images[k] for k in keys],columns),*keys)
    for name,keys,vehicle in (
            ("delivery-start",("pencil","eraser","sharpener","case"),"delivery-rover"),
            ("words-start",("fresh-book","flat-path","together"),"word-boat")):
        derive(name,preview([images[k] for k in keys],images[vehicle]),*keys,vehicle)
    for key,chars,emphasis in (
            ("write-bi-zhi-board","笔知",((9,),(4,))),
            ("write-dao-board","道",((9,10,11),)),
            ("write-fang-board","放",((2,7),)),
            ("write-ping-an-board","平安",((4,),(5,)))):
        derive(key,writing(chars,emphasis))
    for letter,keys in zip("abc",(("brush-goes-in","lid-goes-on"),("lid-goes-on","brush-goes-in"),
                                 ("touch-closed-box","lid-goes-on"))):
        derive(f"quiz-4-{letter}",pair(*(images[k] for k in keys)),*keys)
    for letter,parts in zip("abc",((0,1),(3,4,5),range(6,11))):
        derive(f"quiz-5-{letter}",box_glyph(parts))

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
    for name,inputs in components.items():
        for input_name in inputs:
            uses[input_name].update(uses[name])
    assert lesson["images"].keys() <= images.keys() and all(uses.values())
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
