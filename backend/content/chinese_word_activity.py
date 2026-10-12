"""Original picture and finite interaction family for reviewed primary literacy.

This module has no textbook IDs, network calls or publication authority. A
recipe supplies exact page-reviewed words, context pictures and recorded cues.
"""
from html import escape
from pathlib import Path

from content import textbook_activity_templates as t
from content.textbook_activity_models import MODEL_CONTROLS


def picture(key):
    """Meaning comes from the scene; target characters are added separately."""
    sky = '<rect width="320" height="220" rx="18" fill="#e9f5ee"/><path d="M0 162Q140 130 320 157V220H0Z" fill="#afc88d"/>'
    sun = '<circle cx="240" cy="51" r="25" fill="#edc467"/><g stroke="#d8a440" stroke-width="5">' + ''.join(
        f'<path d="M240 13v-9" transform="rotate({n*45} 240 51)"/>' for n in range(8)) + '</g>'
    water = '<ellipse cx="151" cy="161" rx="126" ry="39" fill="#a6d9d8" stroke="#609ba1" stroke-width="3"/><path d="M66 165q24-10 47 0m21 13q23-9 47 0m18-16q24-10 47 0" fill="none" stroke="#def2e6" stroke-width="4"/>'
    stone = '<g id="moving"><ellipse cx="111" cy="159" rx="18" ry="10" fill="#a09a83"/><ellipse cx="168" cy="171" rx="14" ry="8" fill="#c6b58b"/></g>'
    frog = '<g id="moving"><ellipse cx="150" cy="151" rx="57" ry="33" fill="#70a25c"/><ellipse cx="151" cy="156" rx="34" ry="24" fill="#cee0ab"/><circle cx="126" cy="116" r="21" fill="#70a25c"/><circle cx="177" cy="116" r="21" fill="#70a25c"/><circle cx="127" cy="115" r="13" fill="#fffbed"/><circle cx="177" cy="115" r="13" fill="#fffbed"/><circle cx="130" cy="113" r="6" fill="#334c3b"/><circle cx="175" cy="113" r="6" fill="#334c3b"/><path d="M127 145q25 15 48 0" fill="none" stroke="#436b3d" stroke-width="4"/><path d="M103 164 71 187h40m80-23 33 23h-40" fill="none" stroke="#70a25c" stroke-width="14" stroke-linecap="round"/></g>'
    child = '<g><path d="M67 194v-56q33-30 66 0v56" fill="#7699af"/><ellipse cx="100" cy="92" rx="29" ry="35" fill="#e6bd98"/><path d="M72 89V69q25-31 54 0v21l-22-17-16 12Z" fill="#5a483d"/><circle cx="91" cy="92" r="3" fill="#403d32"/><circle cx="112" cy="92" r="3" fill="#403d32"/><path d="M89 106q13 11 25 0" fill="none" stroke="#9c654f" stroke-width="3"/></g>'
    wheat = '<g id="moving"><path d="M153 188V62m0 85-38-36m38 10 38-35" fill="none" stroke="#598b50" stroke-width="8"/><path d="M151 137q-43-41-59-19 28 30 59 19m4-32q39-38 58-16-31 26-58 16" fill="#78a954"/><ellipse cx="153" cy="61" rx="17" ry="38" fill="#d1ba67"/><path d="M144 32h17m-22 13h25m-25 15h26m-25 15h23m-19 14h14" stroke="#a58f46" stroke-width="3"/></g>'
    flame = '<g id="moving"><path d="M109 175q-41-42 4-72-3 30 12 34 27-50 20-87 69 61 52 117-15 44-88 8Z" fill="#d88656"/><path d="M135 171q-15-27 17-49 0 20 17 30 13 42-34 19Z" fill="#f4cf7d"/></g>'
    moon = '<g id="moving"><path d="M194 34a65 65 0 1 0 15 119 66 66 0 0 1-15-119Z" fill="#e9cd87" stroke="#c3a566" stroke-width="3"/><circle cx="106" cy="63" r="4" fill="#fff2ce"/><circle cx="238" cy="117" r="5" fill="#fff2ce"/></g>'
    if key == 'clear':
        art, label = sky + water + stone, '清澈水面下面能看见两块石子'
    elif key == 'river':
        art = sky + '<path d="M171 88Q91 119 140 148T70 220H256Q310 183 214 157T209 88Z" fill="#a6d9d8" stroke="#609ba1" stroke-width="3"/><path d="M174 112q-22 9-6 21m22 33q33 10 30 24m-105 19 43-14" fill="none" stroke="#e3f4ed" stroke-width="5"/>'
        label = '河水沿弯曲河道流向远方，两边是河岸'
    elif key == 'sunny':
        art, label = sky + '<g id="moving">' + sun + '</g><path d="M35 162V102h42v60m-56-55 35-26 35 26" fill="#d7b18e" stroke="#96775c" stroke-width="4"/>', '阳光照着房子，天空晴朗'
    elif key in {'eyes', 'eat', 'frog'}:
        art, label = sky + water + frog, '青蛙睁着两只大眼睛，在田边观察'
        if key == 'eyes':
            art += '<ellipse cx="256" cy="87" rx="9" ry="5" fill="#766f50"/><ellipse cx="250" cy="81" rx="6" ry="4" fill="#f6f7e8"/><ellipse cx="260" cy="80" rx="6" ry="4" fill="#f6f7e8"/>'
            label = '青蛙睁着两只大眼睛，看着面前的小虫'
        if key == 'eat':
            art += '<path d="M177 146 254 132" stroke="#c68475" stroke-width="4"/><ellipse cx="259" cy="129" rx="9" ry="5" fill="#766f50"/><path d="M253 124 246 117m16 8 8-9" stroke="#766f50" stroke-width="2"/>'
            label = '青蛙用舌头捉到一只小虫'
    elif key in {'feeling','please','protect','give','happy','afraid','move','like'}:
        art = sky + child
        if key in {'feeling','happy','like'}:
            art += '<rect x="153" y="129" width="87" height="58" rx="7" fill="#d8a17c"/><path d="M147 127h98m-47 0v62m-3-62q-45-35-29-36 24-4 29 36 5-37 29-35 15 5-29 35" fill="none" stroke="#e2bd64" stroke-width="8"/><path d="M125 145h38" stroke="#e6bd98" stroke-width="12" stroke-linecap="round"/>'
            label = '小朋友笑着收到包装好的礼物，心情高兴'
        elif key in {'please','give'}:
            art += '<path d="M128 140 181 119m13 20h77v14h-77m9 14v38m56-38v38m-55-66V78h57v61" fill="none" stroke="#a88563" stroke-width="9"/><path d="M128 140 181 119" stroke="#e6bd98" stroke-width="12" stroke-linecap="round"/>'
            label = '小朋友伸手邀请朋友坐到空椅子上'
        elif key == 'protect':
            art += '<g transform="translate(144 68) scale(.43)">' + frog.replace('id="moving"','') + '</g><path d="M130 134 137 159" stroke="#e6bd98" stroke-width="10"/>'
            label = '小朋友站在远处安静看青蛙，双手没有抓它'
        elif key == 'afraid':
            art += '<path d="M196 63 246 82 210 108 245 129" fill="none" stroke="#dba461" stroke-width="10"/><path d="M65 139 53 97m81 44 14-43" stroke="#e6bd98" stroke-width="11" stroke-linecap="round"/>'
            label = '小朋友在雷声旁捂住耳朵，表现害怕'
        else:
            art += '<circle cx="224" cy="172" r="27" fill="#cf9a70"/><path d="m145 158 24 0m-24 9 24 0" stroke="#80947b" stroke-width="4"/>'
            label = '小朋友推动圆球，圆球离开原来的位置'
    elif key in {'wheat','seedling'}:
        art, label = sky + wheat, '一棵有叶片和穗的禾苗'
    elif key == 'fire':
        art, label = sky + '<path d="m91 190 120-10m-118-2 116 15" stroke="#977251" stroke-width="11"/>' + flame, '隔着距离观察图画中的火焰'
    elif key == 'autumn':
        art = sky + '<g transform="translate(-55 35) scale(.75)">' + wheat.replace('id="moving"','') + '</g><g transform="translate(120 28) scale(.75)">' + flame + '</g>'
        label = '左边禾苗，右边火焰，对应左右两个字形线索'
    elif key == 'moon':
        art, label = '<rect width="320" height="220" rx="18" fill="#536c89"/>' + moon, '深蓝天空中的月亮和星星'
    elif key == 'bright':
        art, label = sky + '<g transform="translate(-105 35)">' + sun + '</g><g transform="translate(114 55) scale(.65)">' + moon + '</g>', '太阳和月亮并排，提供日月两个线索'
    elif key in {'cool','time','many','empty','guess','side','command','attack'}:
        if key == 'cool':
            art, label = sky + child + '<path d="M191 102q57 10 67-31m-58 46q57 10 67-21" fill="none" stroke="#7dafba" stroke-width="6"/><path d="m184 184 25-57 46 23-43 47Z" fill="#d9c390"/>', '小朋友拿扇子轻轻扇风'
        elif key == 'time':
            art = sky + '<circle cx="160" cy="111" r="76" fill="#fffbed" stroke="#7798a3" stroke-width="8"/><path d="M160 111V64m0 47 38 24" stroke="#957453" stroke-width="8" stroke-linecap="round"/>'
            label = '时钟的长短指针指向不同位置'
        elif key in {'many','empty'}:
            art = sky + '<path d="M61 117h201l-22 76H83Z" fill="#dbc89e" stroke="#aa8c62" stroke-width="5"/>'
            if key == 'many':
                art += ''.join(f'<circle cx="{90+(i%6)*28}" cy="{126+(i//6)*26}" r="11" fill="#a4b982"/>' for i in range(12))
            label = '篮子里有很多果子' if key == 'many' else '篮子是空的，里面没有果子'
        elif key == 'side':
            art, label = sky + '<path d="M125 145h132v16H125Zm14 16v42m104-42v42" stroke="#a5805e" stroke-width="8" fill="none"/><circle cx="81" cy="178" r="28" fill="#cf9a70"/>', '圆球在桌子旁边'
        elif key == 'command':
            art, label = sky + child + '<path d="M128 143 196 105m0-30v84" stroke="#9e7e57" stroke-width="8"/><path d="M196 78h62v38h-62Z" fill="#c58771"/>', '领队举起小旗发出集合的信号'
        elif key == 'attack':
            art, label = sky + '<path d="M191 82h80v111h-80Z" fill="none" stroke="#819da2" stroke-width="6"/><circle cx="109" cy="164" r="26" fill="#c8966e"/><path d="M45 165h26m-26-16h22m96 16h32" stroke="#8f9e80" stroke-width="5"/>', '球向球门前进，表示比赛中的进攻'
        else:
            art, label = sky + child + '<path d="M176 91h81v82h-81Z" fill="#dbc79f" stroke="#ad916a" stroke-width="4"/><path d="m176 91 40-24 41 24" fill="#c6ad85"/><path d="M129 131 169 120" stroke="#e6bd98" stroke-width="10"/>', '小朋友观察盒子旁的图画线索，正在猜想'
    else:
        raise ValueError('unknown_chinese_picture:' + key)
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 220" role="img" aria-label="' + escape(label, quote=True) + '"><title>' + escape(label) + '</title>' + art + '</svg>'


def word_picture(key, character):
    image = picture(key)
    return image.replace('</svg>', '<rect x="5" y="5" width="69" height="73" rx="12" fill="#fff9e7"/><text x="40" y="60" text-anchor="middle" font-size="51" font-family="STHeiti,Songti SC,serif" fill="#355348">' + escape(character) + '</text></svg>')


def voxel_glyphs(states):
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc', 72)
    result = {}
    for state in states:
        char, cut = state['character'], state['splitFraction']
        if len(char) != 1 or not .2 <= cut <= .65:
            raise ValueError('reviewed_glyph_split_required')
        bitmap = Image.new('L', (100, 100)); draw = ImageDraw.Draw(bitmap)
        bounds = draw.textbbox((0, 0), char, font=font)
        draw.text((8-bounds[0], 8-bounds[1]), char, font=font, fill=255)
        bitmap = bitmap.crop(bitmap.getbbox()).resize((44, 44))
        points = [(x, y) for y in range(44) for x in range(44) if bitmap.getpixel((x, y)) > 127]
        expected = round(cut*44)
        boundary = min(range(max(9, expected-4), min(31, expected+5)),
                       key=lambda x: (sum(px==x for px,py in points), abs(x-expected)))
        groups = [[[x,y] for x,y in points if x < boundary], [[x,y] for x,y in points if x >= boundary]]
        if not all(groups): raise ValueError('empty_glyph_part')
        result[state['sceneStateId']] = groups
    return result


GLYPHS = r"""
function relief(points){const out=[],u=.052;for(const [x,y]of points){const cube=geometries.box;for(let i=0;i<cube.length;i+=6)out.push(cube[i]*u+(x-21.5)*u,cube[i+1]*u+(21.5-y)*u+1.15,cube[i+2]*.14,cube[i+3],cube[i+4],cube[i+5]);}return out;}
function createScene(){meshes.length=0;part('ground','box',0,-.13,0,4,.1,2,[.81,.85,.74]);for(let i=0;i<2;i++){const key='glyph_'+modelState+'_'+i;if(!geometries[key])geometries[key]=relief(glyphs[modelState][i]);part('object',key,separated?(i===0?-.38:.38):0,0,0,1,1,1,i===0?[.28,.52,.44]:[.70,.47,.28]);}}
function resetGeometry(){modelState=firstState;separated=false;poses.object={x:0,z:0,angle:0};if(gl){createScene();drawModel();}}
function commitState(id){if(!Object.hasOwn(glyphs,id))return false;modelState=id;separated=false;createScene();drawModel();return true;}
"""


def glyph_scene(scene, assets):
    body = '<canvas id="model-canvas" class="model" aria-label="可以分合部件的真实汉字浮雕模型"></canvas><div class="choices">' + ''.join(
        t.picture_button('state-'+s['sceneStateId'], s['assetId'], assets[s['assetId']], extra='data-state="'+s['sceneStateId']+'"') for s in scene['states']) + '</div><div class="tools">'
    for name, label, icon in [('start','先听老师说','start'),('replay','重听','replay'),('left','向左移','left'),('right','向右移','right'),('rotate','转一转','rotate'),('reset','重新摆','reset'),('finish','听老师小结','speaker'),('separate','分开看','separate'),('join','合起来','join'),('model-retry','重试模型','replay')]:
        body += t.button(name,label,icon, 'data-cancel' if name in {'start','replay','reset'} else 'hidden data-cancel' if name=='model-retry' else '')
    body += '</div>'
    code = t.WEBGL
    anchor = "let selected='tree',modelState='initial';const poses={tree:{x:-2,z:0,angle:0},bird:{x:0,z:0,angle:0},field:{x:2,z:0,angle:0}};"
    assert code.count(anchor) == 1
    first = scene['states'][0]['sceneStateId']
    code = code.replace(anchor, 'const glyphs='+t.js(voxel_glyphs(scene['states']))+';const firstState='+t.js(first)+";let selected='object',modelState=firstState,separated=false;const poses={object:{x:0,z:0,angle:0}};")
    a,b=code.index('function createScene(){'),code.index('\nfunction compile(')
    code = code[:a] + GLYPHS + code[b:]
    cfg = {'states':scene['states'],'intro':scene['initialCueId'],'retry':scene['retryCueId'],'reset':scene['resetCueId'],'complete':scene['completeCueId']}
    code += MODEL_CONTROLS.replace('CONFIG', t.js(cfg))
    code += '\nfunction splitParts(value){if(interactionBusy||!gl)return;run(async signal=>{separated=value;createScene();drawModel();await displayed(signal);await narrate(value?'+t.js(scene['separateCueId'])+':'+t.js(scene['joinCueId'])+',signal);});}listen("separate",()=>splitParts(true));listen("join",()=>splitParts(false));'
    return t.scene_html(scene, body, code).replace('</style>',
        '.choices>button{min-height:94px}.choices>button svg{max-height:86px}'
        '.tools button span{display:none}.model{height:160px;min-height:160px}</style>', 1)


CARDS = r"""
const config=CONFIG;let current=0,started=false,ready=false;
function refreshControls(){document.getElementById('next').disabled=interactionBusy||!started||!ready;document.getElementById('previous').disabled=interactionBusy||!started||current===0;}
function onCueCompleted(id){if(id===config.cards[current].cueId)ready=true;}
function show(){document.querySelectorAll('[data-card]').forEach((b,i)=>{b.hidden=i!==current;});refreshControls();}
function readCard(){return run(async signal=>{started=true;ready=false;show();await narrate(config.cards[current].cueId,signal);});}
listen('start',()=>run(async signal=>{started=true;current=0;ready=false;show();await narrate(config.intro,signal);await narrate(config.cards[current].cueId,signal);}));listen('reset',()=>run(async signal=>{current=0;ready=false;started=true;show();await narrate(config.reset,signal);await narrate(config.cards[0].cueId,signal);}));listen('replay',readCard);listen('previous',()=>{if(interactionBusy||current===0)return;current--;readCard();});listen('next',()=>{if(interactionBusy||!started||!ready)return;if(current===config.cards.length-1){run(signal=>narrate(config.complete,signal));return;}current++;readCard();});
document.querySelectorAll('[data-card]').forEach((b,i)=>b.addEventListener('click',()=>{if(i===current&&!interactionBusy)readCard();}));
listen('write',()=>run(async signal=>{document.getElementById('writing-observation').hidden=false;await narrate(config.write,signal);}));
function applyTeacherState(state){if(Object.keys(state).length===1&&state.sceneStateId==='reset'){assisted=true;current=0;readCard();}}
show();
"""


def cards_scene(scene, assets):
    # These are successive narrated observations, never competing answer choices.
    body = '<div class="choices">'+''.join(
        '<button type="button" id="card-'+str(i)+'" data-mira-word-card="'+escape(c['character'], quote=True)
        +'" data-card="'+str(i)+'" aria-label="重听这个字"'+(' hidden' if i else '')+'>'
        +assets[c['assetId']]+'</button>' for i,c in enumerate(scene['cards']))+'</div><div class="tools">'
    for key,label,icon in [('start','听老师说','start'),('replay','重听','replay'),('previous','上一张','left'),('next','下一张','next'),('reset','重新开始','reset'),('write','拿纸笔练一练','pencil')]:
        body+=t.button(key,label,icon,'data-cancel' if key in {'start','replay','reset'} else '')
    body += '</div><div id="writing-observation" hidden aria-label="听老师说，在纸上练写">'+''.join(
        '<span style="display:inline-block;font-size:64px;margin:8px;padding:8px;border:1px solid #a9bbab;background:#fffaf0">'
        +escape(char)+'</span>' for char in scene.get('writingCharacters', []))+'</div>'
    return t.scene_html(scene,body,CARDS.replace('CONFIG',t.js({'cards':scene['cards'],'intro':scene['initialCueId'],'reset':scene['resetCueId'],'complete':scene['completeCueId'],'write':scene['writeCueId']}))).replace('</style>',
        '.choices{grid-template-columns:1fr;max-width:430px}.choices>button svg{max-height:210px}'
        '#writing-observation{text-align:center}</style>', 1)
