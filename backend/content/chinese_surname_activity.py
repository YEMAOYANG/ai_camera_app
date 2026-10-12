"""Bounded, source-aligned surname component models for primary literacy.

Real font pixels are extruded into movable 3D parts. This is shape observation;
the separate stroke renderer is responsible for teaching writing order.
"""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from content import textbook_activity_templates as shared
from content import textbook_activity_models as models
from content.textbook_activity_ir import require

SOURCE_COMPILER_SHA256 = '906378f5304ea7b32185e82219b9bad811f02a2e1a7d9c6ee391aa6f9fd52282'
FONT = Path('/System/Library/Fonts/STHeiti Medium.ttc')
FONT_SHA256 = '2d37f927fb4c24a2ba4d318b903a607f6b7ad4e5f365c26aba6aaccb84038beb'
ACTORS = [
    {'key':'li','char':'李','layout':'vertical','parts':['木','子']},
    {'key':'zhang','char':'张','layout':'horizontal','parts':['弓','长']},
    {'key':'hu','char':'胡','layout':'horizontal','parts':['古','月']},
    {'key':'wu','char':'吴','layout':'vertical','parts':['口','天']},
]
PORTRAIT_IDS = ['actor_'+a['key'] for a in ACTORS]
CUE_KEYS = ['initialCueId','retryCueId','resetCueId','completeCueId','separateCueId','joinCueId']


def tools(items):
    return '<div class="tools">'+''.join(shared.button(*x) for x in items)+'</div>'


def validate_scene(scene, scope):
    expected=[{'sceneStateId':a['key'],'assetId':'actor_'+a['key'],
               'char':a['char'],'layout':a['layout'],'parts':a['parts']} for a in ACTORS]
    actual=[{k:s.get(k) for k in expected[0]} for s in scene.get('states',[])]
    own={c['cueId'] for c in scene.get('finiteCues',[])}
    require(scene.get('modelAdapterKey')=='real_font_voxel_relief_character_components'
            and scope.get('introducedPortraitAssetIds')==PORTRAIT_IDS
            and set('李张胡吴')<=set(scope.get('recognizedCharacters',[]))
            and set(scene.get('activityGoalIds',[]))=={'surname_character_components'}
            and actual==expected and all(scene.get(k) in own for k in CUE_KEYS)
            and all(s.get('observationCueId') in own for s in scene.get('states',[]))
            and not any(k in scene for k in ('html','script','geometry','glyphs')),
            'integrated_surname_component_contract_invalid')


MODEL_TOOLS=[('start','先听老师说','start','data-cancel'),('replay','重听','replay','data-cancel'),('left','向左移','left',''),('right','向右移','right',''),('rotate','转一转','rotate',''),('reset','重新摆','reset','data-cancel'),('finish','听老师说','next',''),('model-retry','重新加载模型','replay','data-cancel hidden')]

def engine(geometry,declarations):
    code=shared.WEBGL;anchor="let selected='tree',modelState='initial';const poses={tree:{x:-2,z:0,angle:0},bird:{x:0,z:0,angle:0},field:{x:2,z:0,angle:0}};"
    if code.count(anchor)!=1:raise ValueError('engine_anchor')
    code=code.replace(anchor,declarations+";let selected='object',modelState='initial';const poses={object:{x:0,z:0,angle:0}};")
    a,b=code.index('function createScene(){'),code.index('\nfunction compile(')
    code=code[:a]+geometry+code[b:]
    return code.replace('createScene();document.getElementById','resetGeometry();createScene();document.getElementById')

@lru_cache(maxsize=1)
def glyph_data():
    """Real system-font contours, pixel-extruded as two movable relief components."""
    from PIL import Image, ImageDraw, ImageFont
    require(sha256(FONT.read_bytes()).hexdigest()==FONT_SHA256, "surname_reviewed_font_changed")
    font=ImageFont.truetype(str(FONT),64);result={}
    for actor in ACTORS:
        image=Image.new('L',(80,80));draw=ImageDraw.Draw(image);box=draw.textbbox((0,0),actor['char'],font=font);draw.text((8-box[0],8-box[1]),actor['char'],font=font,fill=255)
        image=image.crop(image.getbbox()).resize((40,40));coords=[(x,y) for y in range(40) for x in range(40) if image.getpixel((x,y))>=128]
        vertical=actor['layout']=='vertical';counts=[sum((y if vertical else x)==i for x,y in coords) for i in range(40)]
        expected={'li':.48,'wu':.40,'zhang':.40,'hu':.52}[actor['key']]*40
        boundary=min(range(11,29),key=lambda i:(counts[i],abs(i-expected)))
        # 胡 has a sweeping 月 stroke below 古; a straight split cuts that real stroke.
        # These row bounds were checked against the exact 40px system-font bitmap.
        def first(x,y):
            if actor['key']=='hu':return x<(21 if y<18 else 18 if y<32 else 14 if y<36 else 0)
            return (y if vertical else x)<boundary
        groups=[[[x,y] for x,y in coords if first(x,y)],[[x,y] for x,y in coords if not first(x,y)]]
        if not all(groups):raise ValueError('empty_glyph_component')
        result[actor['key']]={'char':actor['char'],'layout':actor['layout'],'boundary':'row_traced_Gu_Yue' if actor['key']=='hu' else boundary,'pixels':groups}
    return result

GLYPH_GEOMETRY=r"""
function relief(pixels){const out=[],unit=.048;for(const [x,y]of pixels){const tx=(x-19.5)*unit,ty=(19.5-y)*unit+1;const cube=geometries.box;for(let i=0;i<cube.length;i+=6)out.push(cube[i]*unit+tx,cube[i+1]*unit+ty,cube[i+2]*.12,cube[i+3],cube[i+4],cube[i+5]);}return out;}
function createScene(){meshes.length=0;part('ground','box',0,-.12,0,4,.1,2,[.80,.85,.73]);const g=glyphs[active];for(let i=0;i<2;i++){const key='glyph_'+active+'_'+i;if(!geometries[key])geometries[key]=relief(g.pixels[i]);const direction=i===0?-1:1,dx=separated&&g.layout==='horizontal'?direction*.38:0,dy=separated&&g.layout==='vertical'?-direction*.38:0;part('object',key,dx,dy,0,1,1,1,i===0?[.30,.50,.43]:[.64,.42,.28]);meshes[meshes.length-1].glyphPart=i;}}
function resetGeometry(){active='li';separated=false;poses.object={x:0,z:0,angle:0};modelState='li';if(gl){createScene();drawModel();}}
function commitState(id){if(!Object.hasOwn(glyphs,id))return false;active=id;separated=false;modelState=id;poses.object={x:0,z:0,angle:0};createScene();drawModel();return true;}
"""

def glyph_model(scene,assets):
    body='<canvas id="model-canvas" class="model" aria-label="真实字形像素挤出的立体字形部件，观察而非书写"></canvas><div class="choices">'+''.join(shared.picture_button('state-'+s['sceneStateId'],s['assetId'],assets[s['assetId']],extra='data-state="'+s['sceneStateId']+'"') for s in scene['states'])+'</div>'+tools(MODEL_TOOLS+[('separate','分开一点看','left',''),('join','回到原位','right','')])
    cfg={'states':scene['states'],'intro':scene['initialCueId'],'retry':scene['retryCueId'],'reset':scene['resetCueId'],'complete':scene['completeCueId']}
    code=engine(GLYPH_GEOMETRY,'const glyphs='+shared.js(glyph_data())+";let active='li',separated=false")+models.MODEL_CONTROLS.replace('CONFIG',shared.js(cfg))
    code+="\nfunction splitGlyph(value){if(interactionBusy||!gl)return;run(async signal=>{separated=value;createScene();drawModel();await displayed(signal);await narrate(value?"+shared.js(scene['separateCueId'])+":"+shared.js(scene['joinCueId'])+",signal);});}listen('separate',()=>splitGlyph(true));listen('join',()=>splitGlyph(false));"
    return shared.scene_html(scene,body,code)
