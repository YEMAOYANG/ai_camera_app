"""Bounded, original water-well model for picture-led Chinese word practice."""
from content import textbook_activity_templates as t


WELL_CUE_KEYS = ('initialCueId','lowerCueId','raiseCueId','resetCueId','completeCueId','retryCueId')

WELL_GEOMETRY = r'''
function createScene(){
  meshes.length=0;
  part('well','box',0,-.18,0,3.6,.12,2.8,[.71,.79,.61]);
  part('well','cylinder',0,.05,0,1.48,.08,1.48,[.30,.63,.72]);
  for(let row=0;row<3;row++)for(let i=0;i<16;i++){
    const angle=(i+(row%2)*.5)*Math.PI/8;
    // A deliberate front cutaway exposes the bucket and water in this model.
    if(Math.cos(angle)>.6)continue;
    part('well','box',Math.sin(angle)*.82,.14+row*.26,Math.cos(angle)*.82,.32,.24,.18,[.64+row*.035,.63+row*.035,.54+row*.035],angle);
  }
  for(const x of [-1.10,1.10])part('well','box',x,1.30,0,.14,2.75,.16,[.53,.37,.22]);
  part('well','box',0,2.63,0,2.48,.19,.20,[.58,.42,.25]);
  part('well','cylinder',0,2.42,0,.24,2.35,.24,[.67,.48,.28],Math.PI/2,Math.PI/2);
  const ropeTop=2.40,ropeBottom=bucketY+.51;
  part('well','cylinder',0,(ropeTop+ropeBottom)/2,0,.028,ropeTop-ropeBottom,.028,[.46,.37,.24]);
  for(let i=0;i<12;i++){
    const angle=i*Math.PI/6;
    part('well','box',Math.sin(angle)*.22,bucketY+.18,Math.cos(angle)*.22,.115,.34,.065,[.70,.50,.29],angle);
  }
  part('well','cylinder',0,bucketY+.025,0,.44,.045,.44,[.59,.41,.23]);
  for(const x of [-.21,.21])part('well','box',x,bucketY+.40,0,.025,.25,.025,[.43,.40,.32]);
  part('well','box',0,bucketY+.52,0,.44,.025,.025,[.43,.40,.32]);
  if(filled)part('well','cylinder',0,bucketY+.27,0,.37,.035,.37,[.28,.66,.78]);
  const spin=(1.5-bucketY)*3;
  part('well','box',1.29,2.42+Math.sin(spin)*.25,Math.cos(spin)*.25,.18,.09,.09,[.77,.56,.32]);
}
function updateModel(){createScene();drawModel();canvas.dataset.bucketState=state;canvas.dataset.bucketHeight=bucketY.toFixed(3);canvas.dataset.filled=String(filled);canvas.dataset.rotation=poses.well.angle.toFixed(3);}
function animateBucket(target,signal){return new Promise((resolve,reject)=>{
  const from=bucketY,start=performance.now();let frame;
  const abort=()=>{cancelAnimationFrame(frame);signal.removeEventListener('abort',abort);reject(new Error('cancelled'));};
  signal.addEventListener('abort',abort,{once:true});
  if(signal.aborted||document.hidden){abort();return;}
  function step(now){if(signal.aborted||document.hidden){abort();return;}
    const p=Math.min(1,(now-start)/1250),e=p*p*(3-2*p);bucketY=from+(target-from)*e;updateModel();
    if(p<1)frame=requestAnimationFrame(step);else{signal.removeEventListener('abort',abort);resolve();}}
  frame=requestAnimationFrame(step);
});}
'''

WELL_CONTROLS = r'''
function refreshControls(){
  document.getElementById('lower').disabled=interactionBusy||!started||!gl||state!=='high_empty';
  document.getElementById('raise').disabled=interactionBusy||!started||!gl||state!=='low_full';
  document.getElementById('finish').disabled=interactionBusy||!gl||state!=='high_full';
  document.getElementById('rotate').disabled=interactionBusy||!gl;
}
function show(){updateModel();const step=state==='high_empty'?0:state==='low_full'?1:2;
  document.querySelectorAll('#well-progress i').forEach((dot,i)=>dot.classList.toggle('done',i<=step));refreshControls();}
function begin(intro){cancelOperation();started=false;state='high_empty';filled=false;bucketY=1.5;poses.well.angle=0;show();
  run(async signal=>{if(!gl){await narrate(config.retryCueId,signal);return;}
    await narrate(intro?config.initialCueId:config.resetCueId,signal);started=true;});}
listen('start',()=>begin(true));listen('reset',()=>begin(false));listen('replay',replay);
listen('lower',()=>{if(interactionBusy||!started||!gl||state!=='high_empty')return;
  run(async signal=>{await animateBucket(.02,signal);filled=true;state='low_full';show();await narrate(config.lowerCueId,signal);});});
listen('raise',()=>{if(interactionBusy||!started||!gl||state!=='low_full')return;
  run(async signal=>{await animateBucket(1.5,signal);state='high_full';show();await narrate(config.raiseCueId,signal);});});
listen('rotate',()=>{if(interactionBusy||!gl)return;poses.well.angle+=Math.PI/6;updateModel();});
listen('finish',()=>{if(interactionBusy||state!=='high_full')return;run(signal=>narrate(config.completeCueId,signal));});
listen('model-retry',()=>{initModel();show();});
function applyTeacherState(value){if(Object.keys(value).length===1&&value.sceneStateId==='reset'){assisted=true;begin(false);}}
initModel();show();
'''


def well_scene(scene, assets):
    if scene.get('adapterId') != 'well_bucket_lift_v1':
        raise ValueError('well_adapter_not_reviewed')
    cfg={key:scene[key] for key in WELL_CUE_KEYS}
    body='<canvas id="model-canvas" class="model" aria-label="可旋转的水井剖面模型，水桶可以上下移动"></canvas><div id="well-progress" class="progress" aria-label="空桶、取水、提起水桶"><i></i><i></i><i></i></div><div class="tools">'
    for identity,label,icon,extra in [('start','听老师说','start','data-cancel'),('replay','再听一次','replay','data-cancel'),
        ('lower','放下水桶','left',''),('raise','提起水桶','right',''),('rotate','转动水井','rotate',''),
        ('reset','再取一次水','reset','data-cancel'),('finish','听老师小结','speaker',''),('model-retry','重新加载水井','replay','hidden data-cancel')]:
        control=t.button(identity,label,icon,extra)
        if identity in {'lower','raise'}:
            arrow='M32 14v32m-13-13 13 13 13-13' if identity=='lower' else 'M32 50V18m-13 13 13-13 13 13'
            start,end=control.index('<svg'),control.index('</svg>')+6
            control=control[:start]+'<svg viewBox="0 0 64 64" aria-hidden="true"><path d="'+arrow+'" fill="none" stroke="currentColor" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/></svg>'+control[end:]
        body+=control
    body+='</div><style>.model{height:clamp(220px,42vh,360px)}.tools button span{display:none}.tools button{min-width:64px;min-height:64px}</style>'
    engine=t.WEBGL
    anchor="let selected='tree',modelState='initial';const poses={tree:{x:-2,z:0,angle:0},bird:{x:0,z:0,angle:0},field:{x:2,z:0,angle:0}};"
    if engine.count(anchor)!=1:raise ValueError('well_renderer_anchor_changed')
    engine=engine.replace(anchor,'const config='+t.js(cfg)+";let bucketY=1.5,filled=false,started=false,state='high_empty';const poses={well:{x:0,z:0,angle:0}};")
    a,b=engine.index('function createScene(){'),engine.index('\nfunction compile(')
    engine=engine[:a]+WELL_GEOMETRY+engine[b:]+WELL_CONTROLS
    return t.scene_html(scene,body,engine)
