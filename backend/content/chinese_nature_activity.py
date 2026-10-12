"""Bounded natural motion and rain-radical activities for picture-led Chinese.

Promoted from the reviewed original compiler; its SHA is retained below.
No output imports, arbitrary geometry recipes, or paid dispatch.
"""
from content import textbook_activity_templates as shared
from content import textbook_activity_models as models

SOURCE_COMPILER_SHA256 = '92bd8b702cd76e7d4ff7b63b733b87d5ffd0b8e57c164f1861f4af9fefb649cb'

def tools(items):return '<div class="tools">'+''.join(shared.button(*x) for x in items)+'</div>'

MODEL_GEOMETRY=r"""
function customTriangle(a,b,c,color){const out=[];triangle(out,a,b,c,color,.93);return out;}
function snowGeometry(){const out=[];for(let k=0;k<3;k++){const a=k*Math.PI/3,c=Math.cos(a),s=Math.sin(a),p=(x,y)=>[x*c-y*s,x*s+y*c,0],color=[.82,.94,.98];triangle(out,p(-.22,-.016),p(.22,-.016),p(.22,.016),color,1);triangle(out,p(-.22,-.016),p(.22,.016),p(-.22,.016),color,1);}return out;}
function createScene(){meshes.length=0;part('ground','box',0,-.14,0,6,.18,3.2,[.78,.84,.71]);
 if(active==='wind'){for(let i=0;i<3;i++){geometries['blade'+i]=customTriangle([-.08,0,0],[.10,0,.025],[.38,1.25,.02],[.38,.61,.34]);part('object','blade'+i,(i-1)*.7,0,0,1,1,1,[1,1,1],0,-.25);}}
 else if(active==='snow'){geometries.snowflake=snowGeometry();for(let j=0;j<5;j++){const x=(j%3-1)*.85,y=.7+Math.floor(j/3)*.8;part('object','snowflake',x,y,0,1,1,1,[1,1,1]);}}
 else{part('pond','cylinder',0,-.02,0,3,.09,1.8,[.48,.73,.79]);part('object','sphere',0,.28,0,.9,.42,.4,[.85,.61,.30]);geometries.tail=customTriangle([-.40,.28,0],[-.82,.55,0],[-.82,.03,0],[.74,.46,.26]);part('object','tail',0,0,0,1,1,1,[1,1,1]);part('object','sphere',.31,.35,.17,.06,.06,.06,[.17,.28,.25]);}
}
function resetGeometry(){active='wind';manualX=0;manualAngle=0;motionRunning=false;poses.object={x:0,y:0,z:0,angle:0,tilt:0};selected='object';modelState='initial';if(gl){createScene();drawModel();}}
function commitState(id){const allowed=['wind','snow','swim'];if(!allowed.includes(id))return false;active=id;manualX=0;manualAngle=0;poses.object={x:0,y:0,z:0,angle:0,tilt:0};modelState=id;motionRunning=adapter==='seasons_natural_motion';createScene();animateModel(0);drawModel();return true;}
function animateModel(t){if(adapter!=='seasons_natural_motion'||!motionRunning)return;const p=poses.object;p.x=manualX;p.angle=manualAngle;
if(active==='wind')p.tilt=.18*Math.sin(t*2);else if(active==='snow'){p.y=.25-.45*((t*.35)%1);p.angle=manualAngle+.22*Math.sin(t*1.5);p.x=manualX+.12*Math.sin(t);}else{p.x=manualX+.5*Math.sin(t*1.1);p.angle=manualAngle+.12*Math.sin(t*1.1);}}
"""

def model_engine(adapter,stone_data):
    if adapter != "seasons_natural_motion" or stone_data:
        raise ValueError("natural_motion_adapter_invalid")
    code=shared.WEBGL
    old="let selected='tree',modelState='initial';const poses={tree:{x:-2,z:0,angle:0},bird:{x:0,z:0,angle:0},field:{x:2,z:0,angle:0}};"
    new='const adapter='+shared.js(adapter)+',stoneData='+shared.js(stone_data)+";let selected='object',modelState='initial',active='',manualX=0,manualAngle=0,motionRunning=false;const poses={};"
    if code.count(old)!=1:raise ValueError('pinned_model_anchor_changed')
    code=code.replace(old,new);a=code.index('function createScene(){');b=code.index('\nfunction compile(',a);code=code[:a]+MODEL_GEOMETRY+code[b:]
    code=code.replace('const world=multiply(translate(p.x,0,p.z),multiply(rotateY(p.angle),m.local));','const world=multiply(translate(p.x,p.y||0,p.z),multiply(rotateY(p.angle),multiply(rotateX(p.tilt||0),m.local)));')
    code=code.replace('createScene();document.getElementById','resetGeometry();createScene();document.getElementById')
    code=code.replace('if(gl&&!document.hidden)drawModel();','if(gl&&!document.hidden){animateModel(performance.now()/1000);drawModel();}')
    return code

def model(scene,assets):
    body='<canvas id="model-canvas" class="model" aria-label="可操作的原创观察模型"></canvas><div class="choices">'+''.join(shared.picture_button('state-'+s['sceneStateId'],s['assetId'],assets[s['assetId']],extra='data-state="'+s['sceneStateId']+'"') for s in scene['states'])+'</div>'
    body+=tools([('start','开始观察','start','data-cancel'),('replay','重听','replay','data-cancel'),('left','向左移','left',''),('right','向右移','right',''),('rotate','转一转','rotate',''),('reset','回到开始','reset','data-cancel'),('finish','继续','next',''),('model-retry','重新加载模型','replay','data-cancel hidden')])
    code=models.MODEL_CONTROLS
    old='p.x+=delta;p.angle+=rotation;createScene();drawModel();'
    new='manualX+=delta;manualAngle+=rotation;p.x=manualX;p.angle=manualAngle;createScene();drawModel();'
    if code.count(old)!=1:raise ValueError('pinned_model_controls_changed')
    code=code.replace(old,new)
    code=code.replace('p.x+delta< -2.35||p.x+delta>2.35','manualX+delta< -1.6||manualX+delta>1.6')
    config={'states':scene['states'],'intro':scene['initialCueId'],'retry':scene['retryCueId'],'reset':scene['resetCueId'],'complete':scene['completeCueId']}
    return shared.scene_html(scene,body,model_engine(scene['modelAdapterKey'],[])+code.replace('CONFIG',shared.js(config)))

def radical(scene,assets):
    body='<div style="text-align:center"><button id="character" aria-label="霜字" style="position:relative;font-size:126px;line-height:1.2;min-width:170px;min-height:170px"><span style="margin:0;font-size:126px">霜</span><span id="rain-part" hidden style="position:absolute;inset:6px 0 0;margin:0;font-size:126px;color:#287a9b;clip-path:inset(0 0 58% 0)">霜</span></button></div><div class="choices">'+shared.picture_button('look-frost','frost',assets['frost'])+shared.picture_button('look-rain','rain',assets['rain'])+'</div>'
    body+=tools([('start','听老师说','start','data-cancel'),('top','看看上面','hint',''),('replay','重听','replay','data-cancel'),('reset','收起提示','reset','data-cancel'),('finish','再看一遍','next','')])
    config={k:scene[k] for k in ['initialCueId','wholeCueId','topCueId','pictureCueId','resetCueId','finishCueId']}
    code=r"""
const config=CONFIG;function refreshControls(){}
function action(kind){if(interactionBusy)return;run(async signal=>{document.getElementById('rain-part').hidden=kind!=='top';await narrate(kind==='top'?config.topCueId:kind==='picture'?config.pictureCueId:config.wholeCueId,signal);});}
listen('character',()=>action('whole'));listen('look-frost',()=>action('picture'));listen('look-rain',()=>action('top'));listen('top',()=>action('top'));listen('start',()=>run(signal=>narrate(config.initialCueId,signal)));listen('replay',replay);listen('reset',()=>run(async signal=>{document.getElementById('rain-part').hidden=true;await narrate(config.resetCueId,signal);}));listen('finish',()=>{if(!interactionBusy)run(signal=>narrate(config.finishCueId,signal));});
function applyTeacherState(state){if(Object.keys(state).length!==1)return;if(['whole','top','picture'].includes(state.sceneStateId)){assisted=true;action(state.sceneStateId);}}
""".replace('CONFIG',shared.js(config))
    return shared.scene_html(scene,body,code)
