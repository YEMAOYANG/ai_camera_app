"""Original bounded zongzi cutaway for the Chinese words outside and inside."""
from content import textbook_activity_templates as t


ZONGZI_CUE_KEYS = ('initialCueId', 'openCueId', 'closeCueId', 'resetCueId',
                   'completeCueId', 'retryCueId')

ZONGZI_GEOMETRY = r'''
function pyramidFaces(side){
  const out=[],top=[0,2.45,0],left=[-1.05,.20,.80],right=[1.05,.20,.80],back=[0,.20,-1.05],front=[0,.20,.80];
  const faces=side==='left'?[[top,left,front],[top,back,left],[left,back,front]]:
    side==='right'?[[top,front,right],[top,right,back],[front,back,right]]:
    [[top,left,right],[top,right,back],[top,back,left],[left,back,right]];
  faces.forEach((v,i)=>triangle(out,...v,[1,1,1],.76+i*.065));return out;
}
geometries.rice=pyramidFaces('whole');geometries.leafLeft=pyramidFaces('left');geometries.leafRight=pyramidFaces('right');
function createScene(){
  meshes.length=0;
  part('plate','cylinder',0,.03,0,5.9,.08,3.8,[.67,.79,.75]);
  // The front is an illustrative cutaway, not a cooking simulation.
  if(openAmount>0){
    part('zongzi','rice',0,.035,0,.87,.88,.87,[1,.97,.78]);
    part('zongzi','sphere',0,1.04,.42,.42,.66,.27,[.66,.29,.20]);
    for(const p of [[-.45,.61,.54],[.46,.58,.56],[-.22,1.45,.26],[.23,1.30,.31]])
      part('zongzi','sphere',...p,.10,.035,.035,[.83,.79,.61],0,.4);
  }
  part('zongzi','leafLeft',-1.55*openAmount,0,0,1,1,1,[.46,.62,.36],-.72*openAmount);
  part('zongzi','leafRight',1.55*openAmount,0,0,1,1,1,[.56,.69,.43],.72*openAmount);
}
function updateModel(){createScene();drawModel();canvas.dataset.wrapperState=state;canvas.dataset.leafOpening=openAmount.toFixed(3);canvas.dataset.rotation=poses.zongzi.angle.toFixed(3);}
function moveLeaves(target,signal){return new Promise((resolve,reject)=>{
  const from=openAmount,start=performance.now();let frame;
  const abort=()=>{cancelAnimationFrame(frame);signal.removeEventListener('abort',abort);openAmount=from;updateModel();reject(new Error('cancelled'));};
  signal.addEventListener('abort',abort,{once:true});if(signal.aborted||document.hidden){abort();return;}
  function step(now){if(signal.aborted||document.hidden){abort();return;}
    const progress=Math.min(1,(now-start)/1000),smooth=progress*progress*(3-2*progress);openAmount=from+(target-from)*smooth;updateModel();
    if(progress<1)frame=requestAnimationFrame(step);else{signal.removeEventListener('abort',abort);resolve();}}
  frame=requestAnimationFrame(step);
});}
'''

ZONGZI_CONTROLS = r'''
function refreshControls(){
  document.getElementById('open').disabled=interactionBusy||!started||!gl||state==='open';
  document.getElementById('close').disabled=interactionBusy||!started||!gl||state!=='open';
  document.getElementById('finish').disabled=interactionBusy||!gl||state!=='rewrapped';
  document.getElementById('rotate').disabled=interactionBusy||!gl;
}
function show(){updateModel();const step=state==='wrapped'?0:state==='open'?1:2;
  document.querySelectorAll('#zongzi-progress i').forEach((dot,i)=>{dot.classList.toggle('done',i<=step);dot.setAttribute('aria-label',i<=step?'这一步已观察':'这一步还没观察');});refreshControls();}
function begin(intro){cancelOperation();started=false;state='wrapped';openAmount=0;poses.zongzi.angle=0;show();
  run(async signal=>{if(!gl){await narrate(config.retryCueId,signal);return;}
    await narrate(intro?config.initialCueId:config.resetCueId,signal);started=true;});}
listen('start',()=>begin(true));listen('reset',()=>begin(false));listen('replay',replay);
listen('open',()=>{if(interactionBusy||!started||!gl||state==='open')return;
  run(async signal=>{await moveLeaves(1,signal);state='open';show();await narrate(config.openCueId,signal);});});
listen('close',()=>{if(interactionBusy||!started||!gl||state!=='open')return;
  run(async signal=>{await moveLeaves(0,signal);state='rewrapped';show();await narrate(config.closeCueId,signal);});});
listen('rotate',()=>{if(interactionBusy||!gl)return;poses.zongzi.angle+=Math.PI/6;updateModel();});
listen('finish',()=>{if(interactionBusy||state!=='rewrapped')return;run(signal=>narrate(config.completeCueId,signal));});
listen('model-retry',()=>{initModel();show();});
function applyTeacherState(value){if(Object.keys(value).length===1&&value.sceneStateId==='reset'){assisted=true;begin(false);}}
initModel();show();
'''


def zongzi_scene(scene, assets):
    if scene.get('adapterId') != 'zongzi_layers_v1':
        raise ValueError('zongzi_adapter_not_reviewed')
    config = {key: scene[key] for key in ZONGZI_CUE_KEYS}
    body = ('<canvas id="model-canvas" class="model" aria-label="可剥开粽叶并旋转的粽子示意模型"></canvas>'
            '<div id="zongzi-progress" class="progress" aria-label="包好、剥开、合上"><i></i><i></i><i></i></div><div class="tools">')
    for identity, label, icon, extra in [
        ('start', '听老师说', 'start', 'data-cancel'), ('replay', '再听一次', 'replay', 'data-cancel'),
        ('open', '剥开粽叶', 'left', ''), ('close', '合上粽叶', 'right', ''),
        ('rotate', '转动粽子', 'rotate', ''), ('reset', '重新观察', 'reset', 'data-cancel'),
        ('finish', '听老师小结', 'speaker', ''), ('model-retry', '重新加载粽子', 'replay', 'hidden data-cancel')]:
        control = t.button(identity, label, icon, extra)
        if identity in {'open', 'close'}:
            arrows = 'M26 48H8m8-8-8 8 8 8M38 48h18m-8-8 8 8-8 8' if identity == 'open' else 'M8 48h18m-8-8 8 8-8 8M56 48H38m8-8-8 8 8 8'
            pictogram = ('<svg viewBox="0 0 64 64" aria-hidden="true"><path d="M29 8 8 34l19 4Z M35 8l21 26-19 4Z" fill="#81a26c" stroke="#4d7252" stroke-width="2"/>'
                         '<path d="' + arrows + '" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>')
            start, end = control.index('<svg'), control.index('</svg>') + 6
            control = control[:start] + pictogram + control[end:]
        body += control
    body += '</div><style>.model{height:clamp(230px,47vh,340px)}.tools button{min-width:68px;min-height:68px}.tools button span{display:none}</style>'
    engine = t.WEBGL
    anchor = "let selected='tree',modelState='initial';const poses={tree:{x:-2,z:0,angle:0},bird:{x:0,z:0,angle:0},field:{x:2,z:0,angle:0}};"
    if engine.count(anchor) != 1:
        raise ValueError('zongzi_renderer_anchor_changed')
    engine = engine.replace(anchor, 'const config=' + t.js(config) + ";let openAmount=0,started=false,state='wrapped';const poses={zongzi:{x:0,z:0,angle:0}};")
    start, end = engine.index('function createScene(){'), engine.index('\nfunction compile(')
    engine = engine[:start] + ZONGZI_GEOMETRY + engine[end:] + ZONGZI_CONTROLS
    return t.scene_html(scene, body, engine)
