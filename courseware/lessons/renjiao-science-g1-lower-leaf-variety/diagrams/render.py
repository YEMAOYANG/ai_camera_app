"""Compose leaf comparisons and record diagrams from verified lesson specimens."""
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'assets'
PAPER, CREAM, MINT='#fff4dc','#f4dfb7','#dceacb'
INK, GREEN, RUST='#26473c','#527554','#a44734'
FONT='/System/Library/Fonts/Hiragino Sans GB.ttc'
VIEWS={
    'fan':('ginkgo-top','ginkgo-side'),
    'long':('maize-top','maize-side'),
    'broad':('camphor-top','camphor-side'),
}
EXAMPLES={'fan':'gold-ginkgo','long':'straw-maize','round':'lotus-blade','broad':'pale-camphor'}


def board(size=(670,416),color=PAPER):
    im=Image.new('RGBA',size,color)
    return im,ImageDraw.Draw(im)


@lru_cache
def font(size):
    return ImageFont.truetype(FONT,size)


def text(d,value,xy,size=30,color=INK):
    d.text(xy,str(value),anchor='mm',font=font(size),fill=color)


def panel(d,box,color=CREAM,outline=GREEN,width=4):
    d.rounded_rectangle(box,16,fill=color,outline=outline,width=width)


def circle(d,xy,r,color=None,outline=RUST,width=4):
    x,y=xy
    d.ellipse((x-r,y-r,x+r,y+r),fill=color,outline=outline,width=width)


@lru_cache
def art(key):
    with Image.open(ASSETS/f'{key}.png') as source:
        im=source.convert('RGBA')
    bounds=im.getchannel('A').point(lambda a:255 if a>=16 else 0).getbbox()
    return im.crop(bounds)


@lru_cache
def sprite(key,box,angle=0):
    im=art(key).rotate(angle,expand=True)
    im.thumbnail(box,Image.Resampling.LANCZOS)
    return im


def place(im,key,xy,box,angle=0):
    pic=sprite(key,box,angle)
    x,y=map(round,xy)
    im.alpha_composite(pic,(x-pic.width//2,y-pic.height//2))
    return pic.size


def background(key,size=(416,234)):
    return ImageOps.fit(art(key).convert('RGB'),size,Image.Resampling.LANCZOS).convert('RGBA')


def sample_grid(entries, size=(730,410), cols=2):
    im,d=board(size)
    rows=(len(entries)+cols-1)//cols
    w,h=(size[0]-35)//cols,(size[1]-30)//rows
    for i,(key,angle) in enumerate(entries):
        x,y=18+i%cols*w,16+i//cols*h
        panel(d,(x,y,x+w-9,y+h-9),MINT)
        place(im,key,(x+(w-9)//2,y+(h-9)//2),(w-29,h-30),angle)
    return im


def backed_leaf(key, *, side=False):
    im,d=board((600,360))
    panel(d,(15,18,584,342),'#eff0d6','#88a27d')
    # Preserve the natural aspect ratio and use a fixed line as a reference plane.
    if side:
        d.line((59,231,540,231),fill='#b4a287',width=5)
        place(im,key,(301,192),(481,162))
    else:
        place(im,key,(301,180),(481,277))
    return im


def paired_cover():
    im,d=board((796,366))
    for i,key in enumerate(VIEWS['fan']):
        x=12+392*i
        panel(d,(x,57,x+378,347),MINT)
        pic=backed_leaf(key,side=i==1)
        pic.thumbnail((355,278),Image.Resampling.LANCZOS)
        im.alpha_composite(pic,(x+12,91))
        place(im,'leaf-camera',(x+190,29),(52,47))
    return im


def same_shape_examples():
    im,d=board((788,380))
    for i,(a,b) in enumerate([('ginkgo-top','paper-fan'),('maize-top','cloth-ribbon'),('lotus-blade','round-plate')]):
        x=12+i*261
        panel(d,(x,17,x+246,363),MINT)
        place(im,a,(x+123,112),(212,138))
        d.line((x+39,193,x+207,193),fill='#a6a489',width=3)
        place(im,b,(x+123,268),(180,118))
    return im


def known_observation():
    im,d=board((680,410))
    panel(d,(13,20,326,390),MINT)
    panel(d,(348,20,665,390),MINT)
    place(im,'pale-camphor',(164,234),(267,160))
    place(im,'careful-hand',(102,170),(159,128),-6)
    place(im,'waft-child',(441,221),(116,283))
    d.line((503,267,635,267),fill=GREEN,width=6)
    place(im,'pale-camphor',(574,248),(115,55))
    return im


def outline(im,key,center,box,mode):
    pic=sprite(key,box)
    mask=pic.getchannel('A').point(lambda a:255 if a>80 else 0)
    x,y=center; x0,y0=x-pic.width//2,y-pic.height//2
    if mode in ('outline','full'):
        pad=Image.new('L',(pic.width+8,pic.height+8),0)
        pad.paste(mask,(4,4))
        ring=pad.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(5))
        ink=Image.new('RGBA',ring.size,INK); ink.putalpha(ring)
        im.alpha_composite(ink,(x0-4,y0-4))
    if mode in ('veins','full'):
        d=ImageDraw.Draw(im)
        # Draw only visible primary veins from this pale camphor specimen.
        def line(points):
            d.line([(x0+u*pic.width,y0+v*pic.height) for u,v in points],fill=INK,width=7,joint='curve')
        line([(0,.52),(.2,.51),(.5,.48),(.83,.47),(.97,.47)])
        line([(.19,.52),(.31,.39),(.48,.27),(.65,.18),(.75,.19)])
        line([(.19,.52),(.34,.64),(.5,.76),(.64,.79),(.73,.75)])


def note_page(mode='full',key='pale-camphor'):
    im,d=board()
    place(im,'leaf-notebook',(332,207),(643,393))
    outline(im,key,(328,211),(442,190),mode)
    place(im,'green-pencil',(503,355),(211,34),-12)
    return im


def annotated_leaf(key, emphasis):
    im,d=board()
    panel(d,(16,18,654,398),MINT)
    y=210; x=337
    width,height=place(im,key,(x,y),(506,251))
    left=x-width//2; top=y-height//2
    if emphasis=='stalk':
        circle(d,(left+width*.095,y+height*.015),49,width=7)
    if emphasis=='rib':
        circle(d,(left+width*.48,top+height*.49),62,width=7)
    if emphasis=='tip':
        circle(d,(left+width*.91,top+height*.48),48,width=7)
    if emphasis=='blade':
        d.ellipse((left+width*.22,top-6,left+width*1.01,top+height+7),outline=RUST,width=7)
    return im


def near_spines(who):
    im,d=board((394,275))
    panel(d,(12,10,382,264),MINT)
    ground=245
    d.line((28,ground,367,ground),fill=GREEN,width=5)
    person_positions={'observe-child':(113,(108,202)),'reach-child':(205,(169,202)),'lean-child':(213,(159,170))}
    x,box=person_positions[who]
    person=sprite(who,box); plant=sprite('barrel-cactus',(119,145))
    im.alpha_composite(person,(x-person.width//2,ground-person.height))
    im.alpha_composite(plant,(318-plant.width//2,ground-plant.height))
    return im


def gallery(keys):
    return sample_grid([(k,0) for k in keys],size=(798,358),cols=len(keys))


def neutral_shape(key):
    im,d=board((158,138),'#f9edc9')
    panel(d,(3,3,154,134),'#f0e4bd',GREEN,6)
    leaf=sprite(key,(132,105),0)
    a=leaf.getchannel('A').point(lambda v:255 if v>=64 else 0)
    silhouette=Image.new('RGBA',leaf.size,INK); silhouette.putalpha(a)
    im.alpha_composite(silhouette,((158-leaf.width)//2,(138-leaf.height)//2))
    return im


def picture_options():
    for letter,key in zip('abc',('pale-camphor','gold-ginkgo','maple-blade')):
        yield 'q1-'+letter,gallery([key]),[key]
    yield 'q2-stimulus',backed_leaf('camphor-top'),['camphor-top']
    for letter,spot in zip('abc',('stalk','rib','tip')):
        yield 'q2-'+letter,annotated_leaf('camphor-top',spot),['camphor-top']
    for letter,keys in zip('abc',[['lotus-blade','lotus-blade'],['maize-top','pale-camphor'],['lotus-blade','maize-top']]):
        yield 'q3-'+letter,gallery(keys),list(set(keys))
    for letter,key in zip('abc',('reach-child','observe-child','lean-child')):
        yield 'q4-'+letter,near_spines(key),[key,'barrel-cactus']
    yield 'q5-stimulus',backed_leaf('pale-camphor'),['pale-camphor']
    for letter,mode in zip('abc',('outline','veins','full')):
        yield 'q5-'+letter,note_page(mode),['pale-camphor','leaf-notebook','green-pencil']
    for letter,key in zip('abc',('victoria-float','fan-palm','living-stones')):
        yield 'q6-'+letter,gallery([key]),[key]


def visuals():
    yield 'courtyard-cover',background('leaf-courtyard',(694,440)),['which-leaf-came-to-the-table'],['leaf-courtyard']
    samples=['ginkgo-top','gold-ginkgo','camphor-top','maize-top']
    yield 'four-samples',sample_grid([(key,0) for key in samples]),['which-leaf-came-to-the-table'],samples
    yield 'safe-known-sample',known_observation(),['safe-observation-and-drawing'],['pale-camphor','waft-child','careful-hand']
    yield 'known-leaf-note',note_page(key='camphor-top'),['draw-what-you-see'],['camphor-top','leaf-notebook','green-pencil']
    yield 'observe-backdrop',background('oak-worktable'),['paired-leaf-observations'],['oak-worktable']
    yield 'sort-backdrop',background('leaf-courtyard'),['sort-by-visible-leaf-shape'],['leaf-courtyard']
    yield 'same-leaf-cover',paired_cover(),['paired-leaf-observations'],[*VIEWS['fan'],'leaf-camera']
    yield 'shape-pairs',same_shape_examples(),['what-does-it-look-like'],['ginkgo-top','paper-fan','maize-top','cloth-ribbon','lotus-blade','round-plate']
    yield 'more-shapes',gallery(['maple-blade','pine-needles']),['what-does-it-look-like'],['maple-blade','pine-needles']
    yield 'compare-broad-leaves',gallery(['pale-camphor','maple-blade']),['compare-parts-and-find-a-rule'],['pale-camphor','maple-blade']
    yield 'blade-mark',annotated_leaf('pale-camphor','blade'),['compare-parts-and-find-a-rule'],['pale-camphor']
    yield 'rib-mark',annotated_leaf('pale-camphor','rib'),['compare-parts-and-find-a-rule'],['pale-camphor']
    yield 'stalk-mark',annotated_leaf('pale-camphor','stalk'),['compare-parts-and-find-a-rule'],['pale-camphor']
    for group,key in EXAMPLES.items():
        yield 'dock-'+group,neutral_shape(key),['sort-by-visible-leaf-shape'],[key]
    for group,pair in VIEWS.items():
        for view,key in zip(('top','side'),pair):
            yield f'view-{view}-{group}',backed_leaf(key,side=view=='side'),['paired-leaf-observations'],[key]
    for key,entries in [('water-and-fan',['victoria-float','fan-palm']),('thorn-tube-stone',['barrel-cactus','green-scallion','living-stones'])]:
        yield key,gallery(entries),['strange-leaf-gallery'],entries
    yield 'home-leaf-note',sample_grid([('maple-blade',0),('gold-ginkgo',-20),('pine-needles',25),('pale-camphor',0)]),['take-a-leaf-note-home'],['maple-blade','gold-ginkgo','pine-needles','pale-camphor']
    for key,im,parents in picture_options():
        yield key,im,['picture-quiz'],parents


def render():
    def digest(p):
        return sha256(p.read_bytes()).hexdigest()
    sources={}
    for receipt in sorted((ROOT/'art-source').glob('*.receipt.json')):
        for a in json.loads(receipt.read_text())['assets']:
            sources[a['assetKey']]={**a,'file':a['path'],'kind':'codex-builtin-imagegen'}
    for key,im,uses,parents in visuals():
        p=ASSETS/f'{key}.png';im.save(p,optimize=True)
        sources[key]={'file':p.relative_to(ROOT).as_posix(),'sha256':digest(p),
                      'kind':'deterministic-lesson-diagram','usedBy':uses,'source':'diagrams/render.py',
                      'sourceSha256':digest(Path(__file__)),'sourceAssets':{a:sources[a]['sha256'] for a in sorted(parents)}}
    (ROOT/'asset-sources.json').write_text(json.dumps({'schemaVersion':'mira.courseware.asset-sources.v1','assets':sources},
                                                      ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    render()
