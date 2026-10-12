"""Bounded original ant model connecting visible movement with the word 运."""
from content import textbook_activity_templates as t


ANT_CUE_KEYS = ('initialCueId', 'pickupCueId', 'carryCueId', 'dropCueId',
                'resetCueId', 'completeCueId', 'retryCueId')

ANT_GEOMETRY = r'''
function link(a,b,width,color){
  const dx=b[0]-a[0],dy=b[1]-a[1],dz=b[2]-a[2],length=Math.hypot(dx,dy,dz);
  part('world','cylinder',(a[0]+b[0])/2,(a[1]+b[1])/2,(a[2]+b[2])/2,width,length,width,color,
    Math.atan2(dx,dz),Math.acos(dy/length));
}
function createScene(){
  meshes.length=0;
  part('world','box',0,-.12,0,6.3,.15,3.0,[.72,.66,.46]);
  part('world','cylinder',2.25,-.025,0,.82,.012,.82,[.28,.28,.19]);
  const brown=[.37,.25,.17],dark=[.23,.19,.14];
  part('world','sphere',antX-.47,.64,0,.76,.57,.54,brown);
  part('world','sphere',antX,.60,0,.43,.39,.36,brown);
  part('world','sphere',antX+.43,.66,0,.50,.47,.45,brown);
  // Three leg pairs attach to the thorax. Antennae are separate from the legs.
  for(let i=0;i<3;i++)for(const side of [-1,1]){
    const x=antX+(i-1)*.17,step=Math.sin(gait+(i+side)*Math.PI)*.10;
    const knee=[x+(i-1)*.16+step,.35,side*.43],foot=[x+(i-1)*.30+step,.02,side*.72];
    link([x,.56,side*.10],knee,.055,dark);link(knee,foot,.050,dark);
  }
  for(const side of [-1,1]){
    part('world','sphere',antX+.56,.76,side*.19,.065,.065,.065,[.08,.12,.10]);
    link([antX+.58,.82,side*.12],[antX+.77,1.06,side*.24],.035,dark);
    link([antX+.77,1.06,side*.24],[antX+.91,1.03,side*.35],.035,dark);
    link([antX+.62,.56,side*.10],[antX+.80,.56,side*.05],.035,dark);
  }
  part('world','sphere',foodX,foodY,0,.28,.24,.23,[.91,.77,.43]);
  for(const x of [-2.4,-.3,1.1]){
    link([x,-.02,-1.05],[x+.05,.44,-1.08],.045,[.37,.53,.27]);
    part('world','sphere',x+.15,.28,-1.08,.34,.08,.15,[.48,.65,.34],0,-.35);
  }
}
function updateModel(){createScene();drawModel();canvas.dataset.antState=state;canvas.dataset.antPosition=antX.toFixed(3);
  canvas.dataset.foodPosition=foodX.toFixed(3);canvas.dataset.foodHeight=foodY.toFixed(3);canvas.dataset.rotation=poses.world.angle.toFixed(3);}
function animateAnt(action,signal){return new Promise((resolve,reject)=>{
  const before={antX,foodX,foodY,gait},startedAt=performance.now(),duration=action==='carry'?1800:800;let frame,settled=false;
  const abort=()=>{if(settled)return;settled=true;cancelAnimationFrame(frame);signal.removeEventListener('abort',abort);
    ({antX,foodX,foodY,gait}=before);updateModel();reject(new Error('cancelled'));};
  signal.addEventListener('abort',abort,{once:true});if(signal.aborted||document.hidden){abort();return;}
  function step(now){if(signal.aborted||document.hidden){abort();return;}
    const p=Math.min(1,(now-startedAt)/duration),smooth=p*p*(3-2*p);
    if(action==='pickup'){foodX=before.foodX+(antX+.83-before.foodX)*smooth;foodY=before.foodY+(.57-before.foodY)*smooth;}
    if(action==='carry'){antX=before.antX+(1.10-before.antX)*smooth;foodX=antX+.83;foodY=.57;gait=p*12*Math.PI;}
    if(action==='drop'){foodX=before.foodX+(2.25-before.foodX)*smooth;foodY=before.foodY+(.12-before.foodY)*smooth;}
    updateModel();if(p<1)frame=requestAnimationFrame(step);else{settled=true;signal.removeEventListener('abort',abort);gait=0;resolve();}}
  frame=requestAnimationFrame(step);
});}
'''

ANT_CONTROLS = r'''
function refreshControls(){
  document.getElementById('pickup').disabled=interactionBusy||!started||!stateHeard||!gl||state!=='ready';
  document.getElementById('carry').disabled=interactionBusy||!started||!stateHeard||!gl||state!=='loaded';
  document.getElementById('drop').disabled=interactionBusy||!started||!stateHeard||!gl||state!=='arrived';
  document.getElementById('finish').disabled=interactionBusy||!stateHeard||!gl||state!=='delivered';
  document.getElementById('rotate').disabled=interactionBusy||!gl;
}
function show(){updateModel();const count=['ready','loaded','arrived','delivered'].indexOf(state);
  document.querySelectorAll('#ant-progress i').forEach((dot,i)=>{dot.classList.toggle('done',i<count);
    dot.setAttribute('aria-label',i<count?'这个动作已观察':'这个动作还没观察');});refreshControls();}
function begin(intro){cancelOperation();started=false;stateHeard=false;state='ready';antX=-1.45;foodX=-.20;foodY=.12;gait=0;poses.world.angle=0;show();
  run(async signal=>{if(!gl){await narrate(config.retryCueId,signal);return;}
    await narrate(intro?config.initialCueId:config.resetCueId,signal);started=true;stateHeard=true;});}
function replayState(){run(async signal=>{if(!gl){await narrate(config.retryCueId,signal);return;}
  stateHeard=false;await narrate(config[{ready:'initialCueId',loaded:'pickupCueId',arrived:'carryCueId',delivered:'dropCueId'}[state]],signal);
  started=true;stateHeard=true;});}
listen('start',()=>begin(true));listen('reset',()=>begin(false));listen('replay',replayState);
for(const [action,from,to,cue] of [['pickup','ready','loaded','pickupCueId'],['carry','loaded','arrived','carryCueId'],['drop','arrived','delivered','dropCueId']]){
  listen(action,()=>{if(interactionBusy||!started||!stateHeard||!gl||state!==from)return;
    run(async signal=>{stateHeard=false;await animateAnt(action,signal);state=to;show();await narrate(config[cue],signal);stateHeard=true;});});
}
listen('rotate',()=>{if(interactionBusy||!gl)return;poses.world.angle+=Math.PI/6;updateModel();});
listen('finish',()=>{if(interactionBusy||!stateHeard||state!=='delivered')return;run(signal=>narrate(config.completeCueId,signal));});
listen('model-retry',()=>{initModel();show();});
function applyTeacherState(value){if(Object.keys(value).length===1&&value.sceneStateId==='reset'){assisted=true;begin(false);}}
initModel();show();
'''


def ant_scene(scene, assets):
    if scene.get('adapterId') != 'ant_food_transport_v1':
        raise ValueError('ant_adapter_not_reviewed')
    config = {key: scene[key] for key in ANT_CUE_KEYS}
    body = ('<canvas id="model-canvas" class="model" aria-label="蚂蚁拿起食物并搬到洞口的立体模型"></canvas>'
            '<div id="ant-progress" class="progress" aria-label="拿起、搬运、放下"><i></i><i></i><i></i></div>'
            '<div class="tools">')
    for identity, label, icon, extra in [
        ('start', '听老师说', 'start', 'data-cancel'), ('replay', '再听一次', 'replay', 'data-cancel'),
        ('pickup', '拿起食物', 'up', ''), ('carry', '搬向洞口', 'right', ''),
        ('drop', '放下食物', 'down', ''), ('rotate', '转动模型', 'rotate', ''),
        ('reset', '重新搬运', 'reset', 'data-cancel'), ('finish', '听老师小结', 'speaker', ''),
        ('model-retry', '重新加载蚂蚁', 'replay', 'hidden data-cancel')]:
        # The object and destination in each control carry the task's meaning.
        control = t.button(identity, label, 'right' if icon in {'up', 'down'} else icon, extra)
        if identity in {'pickup', 'carry', 'drop'}:
            if identity == 'pickup':
                art = '<ellipse cx="32" cy="20" rx="10" ry="8" fill="#d9ba70"/><path d="M32 56V36m-9 9 9-9 9 9"/>'
            elif identity == 'drop':
                art = '<ellipse cx="32" cy="47" rx="21" ry="9" fill="#8d7955"/><ellipse cx="32" cy="43" rx="8" ry="6" fill="#d9ba70"/><path d="M32 5v23m-9-9 9 9 9-9"/>'
            else:
                art = '<ellipse cx="14" cy="27" rx="9" ry="6" fill="#86613e"/><ellipse cx="49" cy="28" rx="10" ry="7" fill="#8d7955"/><path d="M10 49h43m-9-8 9 8-9 8"/>'
            start, end = control.index('<svg'), control.index('</svg>') + 6
            picture = '<svg viewBox="0 0 64 64" aria-hidden="true" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" fill="none">'+art+'</svg>'
            control = control[:start] + picture + control[end:]
        body += control
    body += '</div><style>.model{height:clamp(230px,45vh,350px)}.tools button{min-width:68px;min-height:68px}.tools button span{display:none}</style>'
    engine = t.WEBGL
    anchor = "let selected='tree',modelState='initial';const poses={tree:{x:-2,z:0,angle:0},bird:{x:0,z:0,angle:0},field:{x:2,z:0,angle:0}};"
    if engine.count(anchor) != 1:
        raise ValueError('ant_renderer_anchor_changed')
    engine = engine.replace(anchor, 'const config=' + t.js(config)
        + ";let started=false,stateHeard=false,state='ready',antX=-1.45,foodX=-.20,foodY=.12,gait=0;const poses={world:{x:0,z:0,angle:0}};")
    start, end = engine.index('function createScene(){'), engine.index('\nfunction compile(')
    engine = engine[:start] + ANT_GEOMETRY + engine[end:] + ANT_CONTROLS
    return t.scene_html(scene, body, engine)
