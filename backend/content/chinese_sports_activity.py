"""Picture-operated ball actions for learning 拍 and 踢, without skill scoring."""
from content import textbook_activity_templates as t


SPORTS_CUE_KEYS = ('initialCueId', 'dribbleCueId', 'kickCueId',
                   'resetCueId', 'completeCueId', 'retryCueId')

SPORTS_GEOMETRY = r'''
function link(a,b,width,color){
  const dx=b[0]-a[0],dy=b[1]-a[1],dz=b[2]-a[2],length=Math.hypot(dx,dy,dz);
  part('world','cylinder',(a[0]+b[0])/2,(a[1]+b[1])/2,(a[2]+b[2])/2,width,length,width,color,
    Math.atan2(dx,dz),Math.acos(dy/length));
}
function createScene(){
  meshes.length=0;const skin=[.89,.69,.52],shirt=[.44,.64,.70],trousers=[.44,.56,.48];
  part('world','box',0,-.10,0,5.8,.16,2.8,[.73,.80,.62]);
  part('world','box',0,.002,.85,5.3,.018,.025,[.97,.95,.85]);
  part('world','box',-.9,1.13,0,.51,.60,.35,shirt);
  part('world','sphere',-.9,1.76,0,.53,.61,.48,skin);
  part('world','sphere',-.92,1.96,-.035,.52,.27,.48,[.31,.25,.20]);
  for(const x of [-1.01,-.80])part('world','sphere',x,1.79,.225,.045,.045,.035,[.17,.20,.17]);
  part('world','box',-.90,1.60,.227,.12,.018,.018,[.60,.35,.29]);
  link([-1.08,.85,0],[-1.08,.17,0],.13,trousers);
  link([-.72,.85,0],[footX,.18+footLift,0],.13,trousers);
  part('world','box',-1.03,.09,.10,.30,.16,.36,[.89,.85,.71]);
  part('world','box',footX+.05,.09+footLift,.10,.30,.16,.36,[.89,.85,.71]);
  link([-1.17,1.36,0],[-1.43,1.03,.02],.105,skin);
  link([-.64,1.36,0],[actionMode==='dribble'?.15:-.35,handY,.02],.105,skin);
  part('world','sphere',actionMode==='dribble'?.15:-.35,handY,.02,.18,.11,.16,skin);
  part('world','sphere',ballX,ballY,.03,.46,.46,.46,actionMode==='dribble'?[.82,.55,.30]:[.96,.94,.83]);
  if(actionMode==='kick'){
    for(const x of [-.12,.12])part('world','sphere',ballX+x,ballY,.23,.12,.13,.035,[.35,.43,.35]);
    part('world','sphere',ballX,ballY+.15,.18,.13,.12,.04,[.35,.43,.35]);
  }else{
    part('world','box',ballX,ballY,.261,.025,.36,.013,[.51,.35,.22]);
    part('world','box',ballX,ballY,.262,.37,.024,.013,[.51,.35,.22]);
  }
}
function showModel(){createScene();drawModel();canvas.dataset.actionMode=actionMode;
  canvas.dataset.ballX=ballX.toFixed(3);canvas.dataset.ballY=ballY.toFixed(3);
  canvas.dataset.footX=footX.toFixed(3);canvas.dataset.rotation=poses.world.angle.toFixed(3);}
function animateSports(mode,signal){return new Promise((resolve,reject)=>{
  const before={actionMode,ballX,ballY,footX,footLift,handY},startedAt=performance.now(),duration=2000;
  let frame,settled=false;actionMode=mode;ballX=mode==='dribble'?.15:.35;ballY=mode==='dribble'?.95:.25;footX=-.72;footLift=0;handY=mode==='dribble'?1.22:1.02;
  const abort=()=>{if(settled)return;settled=true;cancelAnimationFrame(frame);signal.removeEventListener('abort',abort);
    ({actionMode,ballX,ballY,footX,footLift,handY}=before);showModel();reject(new Error('cancelled'));};
  signal.addEventListener('abort',abort,{once:true});if(signal.aborted||document.hidden){abort();return;}
  function step(now){if(signal.aborted||document.hidden){abort();return;}
    const p=Math.min(1,(now-startedAt)/duration);
    if(mode==='dribble'){ballY=.25+.70*Math.abs(Math.cos(2*Math.PI*p));handY=1.22-.42*Math.max(0,Math.sin(2*Math.PI*p));}
    else{const swing=Math.sin(Math.PI*Math.min(1,p/.70));footX=-.72+.82*swing;footLift=.15*swing;
      ballX=.35+1.75*Math.max(0,(p-.35)/.65);ballY=.25;}
    showModel();if(p<1)frame=requestAnimationFrame(step);else{settled=true;signal.removeEventListener('abort',abort);resolve();}}
  showModel();frame=requestAnimationFrame(step);
});}
'''

SPORTS_CONTROLS = r'''
function refreshControls(){
  for(const id of ['dribble','kick'])document.getElementById(id).disabled=interactionBusy||!started||!stateHeard||!gl;
  document.getElementById('finish').disabled=interactionBusy||!stateHeard||!gl||seen.size!==2;
  document.getElementById('rotate').disabled=interactionBusy||!gl;
}
function show(){showModel();document.querySelectorAll('#sports-progress i').forEach((dot,i)=>{
  const done=seen.has(['dribble','kick'][i]);dot.classList.toggle('done',done);dot.setAttribute('aria-label',done?'这个动作已观察':'这个动作还没观察');});refreshControls();}
function begin(intro){cancelOperation();started=false;stateHeard=false;seen.clear();currentCue=config.initialCueId;
  actionMode='dribble';ballX=.15;ballY=.95;footX=-.72;footLift=0;handY=1.22;poses.world.angle=0;show();
  run(async signal=>{if(!gl){await narrate(config.retryCueId,signal);return;}
    await narrate(intro?config.initialCueId:config.resetCueId,signal);started=true;stateHeard=true;});}
listen('start',()=>begin(true));listen('reset',()=>begin(false));
listen('replay',()=>run(async signal=>{stateHeard=false;if(!gl){await narrate(config.retryCueId,signal);return;}
  await narrate(currentCue,signal);started=true;stateHeard=true;}));
for(const mode of ['dribble','kick'])listen(mode,()=>{if(interactionBusy||!started||!stateHeard||!gl)return;
  run(async signal=>{stateHeard=false;await animateSports(mode,signal);currentCue=config[mode+'CueId'];
    await narrate(currentCue,signal);seen.add(mode);stateHeard=true;show();});});
listen('rotate',()=>{if(interactionBusy||!gl)return;poses.world.angle+=Math.PI/6;showModel();});
listen('finish',()=>{if(interactionBusy||!stateHeard||seen.size!==2)return;run(signal=>narrate(config.completeCueId,signal));});
listen('model-retry',()=>{initModel();show();});
function applyTeacherState(value){if(Object.keys(value).length===1&&value.sceneStateId==='reset'){assisted=true;begin(false);}}
initModel();show();
'''


def sports_scene(scene, assets):
    if scene.get('adapterId') != 'hand_foot_ball_v1':
        raise ValueError('sports_adapter_not_reviewed')
    config = {key: scene[key] for key in SPORTS_CUE_KEYS}
    body = ('<canvas id="model-canvas" class="model" aria-label="手拍球和脚踢球的立体模型"></canvas>'
            '<div class="choices sports-choices">')
    for mode in ('dribble', 'kick'):
        body += t.picture_button(mode, scene[mode+'AssetId'], assets[scene[mode+'AssetId']])
    body += '</div><div id="sports-progress" class="progress" aria-label="拍和踢的观察进度"><i></i><i></i></div><div class="tools">'
    for identity, label, icon, extra in [
        ('start', '听老师说', 'start', 'data-cancel'), ('replay', '再听动作', 'replay', 'data-cancel'),
        ('rotate', '转动球场', 'rotate', ''), ('reset', '重新观察', 'reset', 'data-cancel'),
        ('finish', '听老师小结', 'speaker', ''), ('model-retry', '重新加载球场', 'replay', 'hidden data-cancel')]:
        body += t.button(identity,label,icon,extra)
    body += '</div><style>.model{height:clamp(210px,39vh,300px)}.sports-choices{justify-content:center}.sports-choices>button{max-width:180px;min-height:88px}.sports-choices>button svg{max-height:96px}</style>'
    engine = t.WEBGL
    anchor = "let selected='tree',modelState='initial';const poses={tree:{x:-2,z:0,angle:0},bird:{x:0,z:0,angle:0},field:{x:2,z:0,angle:0}};"
    if engine.count(anchor) != 1:
        raise ValueError('sports_renderer_anchor_changed')
    engine = engine.replace(anchor, 'const config='+t.js(config)
        + ";let started=false,stateHeard=false,actionMode='dribble',ballX=.15,ballY=.95,footX=-.72,footLift=0,handY=1.22;let currentCue=config.initialCueId;const seen=new Set();const poses={world:{x:0,z:0,angle:0}};")
    start,end=engine.index('function createScene(){'),engine.index('\nfunction compile(')
    engine=engine[:start]+SPORTS_GEOMETRY+engine[end:]+SPORTS_CONTROLS
    return t.scene_html(scene,body,engine)
