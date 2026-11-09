"""Editable geometry for the lesson diagrams and picture questions.

Re-render from this directory with Python and Pillow. Coordinates represent
blocks, never illustrative approximations of a count, seam or gap.
"""

from pathlib import Path

from PIL import Image, ImageDraw


INK = '#24464a'
PAPER = '#f7f1df'
TEAL = ('#73c9c1', '#45a79f', '#267a75')
AMBER = ('#f8d58c', '#ecae58', '#c57832')
CORAL = ('#ffb3a0', '#ee8e72', '#b75e50')
SLATE = ('#d5e4e0', '#bdcfc9', '#8ca9a2')
ASSETS = Path(__file__).with_name('assets')


def grid(wide, deep, high=1):
    return [(x, y, z) for z in range(high) for y in range(deep) for x in range(wide)]


def project(point):
    x, y, z = point
    return x + 0.50 * y, -z - 0.35 * y


def paint_blocks(draw, cells, box, palette=TEAL, *, ghosts=()):
    """Paint visible surfaces of unit cells with explicit seams."""
    marks = dict(cells) if isinstance(cells, dict) else dict.fromkeys(cells, palette)
    bounds = [project((x + dx, y + dy, z + dz))
              for x, y, z in [*marks, *ghosts]
              for dx, dy, dz in ((0, 0, 0), (1, 1, 1), (1, 1, 0), (0, 0, 1))]
    left, top, width, height = box
    min_x, max_x = min(x for x, _ in bounds), max(x for x, _ in bounds)
    min_y, max_y = min(y for _, y in bounds), max(y for _, y in bounds)
    scale = min(width / (max_x - min_x), height / (max_y - min_y))

    def pos(point):
        x, y = project(point)
        return (left + width / 2 + (x - (min_x + max_x) / 2) * scale,
                top + height / 2 + (y - (min_y + max_y) / 2) * scale)

    for x, y, z in ghosts:
        corners = [pos(p) for p in ((x,y,z), (x+1,y,z), (x+1,y+1,z), (x,y+1,z))]
        draw.polygon(corners, fill='#f2e7cc', outline='#aa9270', width=3)

    order = sorted(marks, key=lambda xyz: (xyz[0] - xyz[1] + xyz[2], xyz[0], -xyz[1], xyz[2]))
    for x, y, z in order:
        light, mid, dark = marks[x, y, z]
        faces = [
            ((x,y-1,z), ((x,y,z),(x+1,y,z),(x+1,y,z+1),(x,y,z+1)), mid),
            ((x+1,y,z), ((x+1,y,z),(x+1,y+1,z),(x+1,y+1,z+1),(x+1,y,z+1)), dark),
            ((x,y,z+1), ((x,y,z+1),(x+1,y,z+1),(x+1,y+1,z+1),(x,y+1,z+1)), light),
        ]
        for neighbor, polygon, fill in faces:
            if neighbor not in marks:
                draw.polygon([pos(p) for p in polygon], fill=fill, outline=INK, width=3)


def paint_bars(draw, bars, box, *, lengthwise='x'):
    """Paint each rectangular block without a seam across its longer face."""
    left, top, width, height = box
    wide, deep = (2, 1) if lengthwise == 'x' else (1, 2)
    bounds = [project((x+dx,y+dy,z+dz)) for x,y,z in bars
              for dx,dy,dz in ((0,0,0),(wide,deep,1),(wide,deep,0),(0,0,1))]
    min_x, max_x = min(x for x,_ in bounds), max(x for x,_ in bounds)
    min_y, max_y = min(y for _,y in bounds), max(y for _,y in bounds)
    s = min(width / (max_x-min_x), height / (max_y-min_y))

    def pos(point):
        x,y = project(point)
        return (left+width/2+(x-(min_x+max_x)/2)*s, top+height/2+(y-(min_y+max_y)/2)*s)

    for index, (x,y,z) in enumerate(sorted(bars, key=lambda xyz: (xyz[0]-xyz[1]+xyz[2], xyz[0], -xyz[1], xyz[2]))):
        light, mid, dark = TEAL if index % 2 == 0 else AMBER
        front = ((x,y,z),(x+wide,y,z),(x+wide,y,z+1),(x,y,z+1))
        side = ((x+wide,y,z),(x+wide,y+deep,z),(x+wide,y+deep,z+1),(x+wide,y,z+1))
        top_face = ((x,y,z+1),(x+wide,y,z+1),(x+wide,y+deep,z+1),(x,y+deep,z+1))
        for face, fill in ((front,mid),(side,dark),(top_face,light)):
            draw.polygon([pos(p) for p in face], fill=fill, outline=INK, width=3)


def paint_cylinders(draw, sections, box):
    """Sections describe relative center offsets and diameters, bottom first."""
    left, top, width, height = box
    stride = min(74, height / (len(sections) + 0.70))
    diameter = min(width * 0.58, stride * 1.55)
    ellipse = diameter * 0.32
    center = left + width / 2
    bottom = top + (height + stride * len(sections)) / 2 - ellipse / 2
    for level, (offset, ratio) in enumerate(sections):
        x = center + diameter * offset
        half = diameter * ratio / 2
        end = bottom - stride * level
        begin = end - stride
        light, mid, _ = (TEAL, AMBER)[level % 2]
        draw.ellipse((x-half,end-ellipse/2,x+half,end+ellipse/2), fill=mid, outline=INK, width=3)
        draw.rectangle((x-half,begin,x+half,end), fill=mid)
        draw.line((x-half,begin,x-half,end), fill=INK, width=3)
        draw.line((x+half,begin,x+half,end), fill=INK, width=3)
        draw.ellipse((x-half,begin-ellipse/2,x+half,begin+ellipse/2), fill=light, outline=INK, width=3)


def paint_ball(draw, box):
    x,y,w,h = box
    r = min(w,h) * 0.41
    cx, cy = x + w / 2, y + h / 2
    draw.ellipse((cx-r,cy-r,cx+r,cy+r), fill='#ec9b67', outline=INK, width=4)
    draw.arc((cx-r*.78,cy-r*.8,cx+r*.58,cy+r*.65), 205, 265, fill='#f8ce9b', width=9)


def paint_plan(draw, *, wide, deep, fill, box):
    left, top, width, height = box
    cell = min(width / wide, height / deep)
    x0, y0 = left + (width - wide * cell) / 2, top + (height - deep * cell) / 2
    for x in range(wide):
        for y in range(deep):
            x1, y1 = x0 + x * cell, y0 + y * cell
            draw.rounded_rectangle((x1+2,y1+2,x1+cell-2,y1+cell-2), radius=7,
                                   fill=fill.get((x,y),'#f3e7cc'), outline=INK, width=3)


def paint_piece(draw, cells, box):
    left, top, width, height = box
    wide, deep = max(x for x, _ in cells)+1, max(y for _, y in cells)+1
    cell = min(86, width/wide, height/deep)
    x0, y0 = left+(width-wide*cell)/2, top+(height-deep*cell)/2
    for x, y in cells:
        draw.rounded_rectangle((x0+x*cell+2,y0+y*cell+2,x0+(x+1)*cell-2,y0+(y+1)*cell-2),
                               radius=7, fill=AMBER[1], outline=INK, width=3)


def save(name, paint, size=(420, 290)):
    width, height = size
    image = Image.new('RGB', size, PAPER)
    draw = ImageDraw.Draw(image)
    paint(draw, (28, 26, width - 56, height - 52))
    image.save(ASSETS / f'{name}.png', optimize=True)


def gallery(draw, box):
    x,y,w,h = box
    for index, painter in enumerate((
            lambda d,b: paint_bars(d,[(0,0,0)],b),
            lambda d,b: paint_blocks(d,[(0,0,0)],b,AMBER),
            lambda d,b: paint_cylinders(d,[(0,1)],b), paint_ball)):
        left = x + index * w / 4
        draw.rounded_rectangle((left+8,y+5,left+w/4-8,y+h-5), radius=24, fill='#fff9ed', outline='#dfcdae', width=3)
        painter(draw,(left+23,y+47,w/4-46,h-94))


def construction_board(draw, fixed, open_cells, box):
    marks = {p:TEAL for p in fixed}
    marks.update((p,SLATE) for p in open_cells)
    paint_blocks(draw,marks,box)


def construction_targets():
    steps = {
        'join-x': ([(0,0,0)], [(1,0,0),(2,0,0)]),
        'join-z': ([(0,0,0)], [(0,0,1),(0,0,2)]),
        'join-bend': (grid(2,1), [(1,0,1)]),
        'cube-base-corner': ([(0,0,0),(1,0,0),(0,1,0)], [(1,1,0)]),
        'cube-upper-pair': ([*grid(2,2),(0,1,1),(1,1,1)], [(0,0,1),(1,0,1)]),
        'cube-upper-layer': (grid(2,2), [(x,y,1) for x,y,_ in grid(2,2)]),
    }
    for name, (filled, open_cells) in steps.items():
        save(name, lambda d,b: construction_board(d,filled,open_cells,b))


def gap_targets():
    plans = {
        'gap-demo': (3,2,{(1,1),(2,1)}),
        'gap-column': (3,2,{(0,0),(0,1)}),
        'gap-elbow': (3,3,{(0,1),(0,2),(1,2)}),
    }
    for name,(wide,deep,missing) in plans.items():
        grid_cells = {(x,y) for x in range(wide) for y in range(deep)}
        fixed = dict.fromkeys(grid_cells - missing,TEAL[1])
        save(name, lambda d,b: paint_plan(d,wide=wide,deep=deep,fill=fixed,box=b))
        result = {**fixed, **dict.fromkeys(missing,AMBER[1])}
        save(name+'-filled', lambda d,b: paint_plan(d,wide=wide,deep=deep,fill=result,box=b))


def main():
    ASSETS.mkdir(exist_ok=True)
    save('gallery', gallery, (960, 350))
    save('single-bar', lambda d,b: paint_bars(d,[(0,0,0)],b))
    save('ball', paint_ball)
    save('match-bar', lambda d,b: paint_bars(d,[(0,0,0)],b,lengthwise='y'))
    save('match-cube', lambda d,b: paint_blocks(d,[(0,0,0)],b,CORAL))
    save('match-cylinder', lambda d,b: paint_cylinders(d,[(0,1.28)],b))
    def aligned_pairs(d,b):
        x,y,w,h=b
        paint_blocks(d,grid(2,1),(x,y+30,w*.53,h-50))
        paint_blocks(d,grid(1,1,2),(x+w*.58,y+10,w*.40,h-20),AMBER)
    save('aligned-pair-views', aligned_pairs)
    construction_targets()
    gap_targets()
    block_diagrams = {
        'single-cube': [(0,0,0)], 'row-two': grid(2,1), 'tower-two': grid(1,1,2),
        'row-three': grid(3,1), 'tower-three': grid(1,1,3),
        'step-three': [(0,0,0),(1,0,0),(1,0,1)],
        'layer-four': grid(2,2), 'big-cube': grid(2,2,2),
        'quiz-row-four': grid(4,1),
        'quiz-step-four': [(0,0,0),(1,0,0),(1,0,1),(1,0,2)],
        'quiz-turn-four': [(0,0,0),(1,0,0),(1,1,0),(1,2,0)],
        'quiz-seven-cubes': [p for p in grid(2,2,2) if p != (1,0,1)],
        'quiz-six-notch': [p for p in grid(2,2,2) if p not in ((0,0,1),(1,0,1))],
        'quiz-flat-six': grid(3,2),
        'quiz-flat-seven': [*grid(3,2),(3,1,0)],
        'quiz-flat-eight': grid(4,2),
        'hidden-demo': [(0,0,0),(1,0,0),(0,1,0),(0,1,1)],
        'quiz-hidden-stack': [*grid(2,2),(0,1,1),(0,1,2)],
    }
    for name,cells in block_diagrams.items():
        palette = {xyz:(TEAL if xyz[2] == 0 else AMBER) for xyz in cells}
        save(name, lambda d,b: paint_blocks(d,palette,b))
    def separate_layers(d,b):
        x,y,w,h=b
        paint_blocks(d,{(0,0,0):SLATE,(1,0,0):SLATE,(0,1,0):CORAL},(x,y+95,w*.55,h-100))
        paint_blocks(d,[(0,0,0)],(x+w*.62,y+6,w*.35,h-140),AMBER)
    save('hidden-demo-reveal', separate_layers)
    bar_diagrams = {
        'bars-cube': [(0,0,0),(0,1,0),(0,0,1),(0,1,1)],
        'bars-row': [(0,0,0),(2,0,0),(4,0,0),(6,0,0)],
    }
    for name,bars in bar_diagrams.items():
        save(name, lambda d,b: paint_bars(d,bars,b))
    for name, bars in {
        'bars-quiz-cube': [(0,0,0),(1,0,0),(0,0,1),(1,0,1)],
        'bars-quiz-stair': [(0,0,0),(1,0,0),(0,0,1),(0,0,2)],
        'bars-quiz-post': [(0,0,z) for z in range(4)],
    }.items():
        save(name, lambda d,b: paint_bars(d,bars,b,lengthwise='y'))
    for name,sections in {
        'cylinder': [(0,1)], 'cylinder-two': [(0,1)]*2, 'cylinder-three': [(0,1)]*3,
        'cylinder-shifted': [(0,1),(0.42,1)],
        'cylinder-shift-left': [(0,1),(-0.42,1)], 'cylinder-three-shift': [(0,1),(0,1),(0.44,1)],
        'cylinder-three-thin': [(0,1),(0,1),(0,0.68)],
        'quiz-cylinder-four': [(0,1)]*4, 'quiz-cylinder-shift': [(0,1),(0,1),(0.5,1),(0.5,1)],
        'quiz-cylinder-left': [(0,1),(0,1),(-0.5,1),(-0.5,1)],
    }.items():
        save(name, lambda d,b: paint_cylinders(d,sections,b))
    for count in (5,6,7):
        def dots(d,b):
            left,top,width,height=b
            for i in range(count):
                cx=left+width*(1+(i%4)*2)/8
                cy=top+height*(1+(i//4)*2)/4
                d.ellipse((cx-23,cy-23,cx+23,cy+23),fill=TEAL[1],outline=INK,width=3)
        save(f'quiz-dots-{count}',dots)
    save('quiz-gap-target', lambda d,b: paint_plan(d,wide=4,deep=2,fill={p:TEAL[1] for p in ((0,0),(1,0),(2,0),(0,1),(1,1))},box=b))
    for name,cells in {
        'quiz-piece-turn':[(1,0),(0,1),(1,1)], 'piece-line':[(0,0),(1,0),(2,0)],
        'piece-pair':[(0,0),(1,0)], 'piece-upright':[(0,0),(0,1)],
        'piece-elbow':[(0,0),(0,1),(1,1)], 'piece-square':[(0,0),(1,0),(0,1),(1,1)],
    }.items():
        save(name,lambda d,b: paint_piece(d,cells,b))


if __name__ == '__main__':
    main()
