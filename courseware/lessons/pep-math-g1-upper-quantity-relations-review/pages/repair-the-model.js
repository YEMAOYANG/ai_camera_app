const model = {
  'add-6-2': {kind:'add',a:6,b:2,picture:'__IMG:large-add-6-2__'},
  'sub-9-4': {kind:'sub',a:9,b:4,picture:'__IMG:large-sub-9-4__'},
  'add-7-3': {kind:'add',a:7,b:3,picture:'__IMG:large-add-7-3__'},
  'sub-12-4': {kind:'sub',a:12,b:4,picture:'__IMG:large-sub-12-4__'},
  'add-5-4': {kind:'add',a:5,b:4,picture:'__IMG:large-add-5-4__'},
  'add-7-5': {kind:'add',a:7,b:5,picture:'__IMG:large-add-7-5__',cue:'lantern-launch-before'},
  'sub-14-5': {kind:'sub',a:14,b:5,picture:'__IMG:large-sub-14-5__'},
  'sub-13-5': {kind:'sub',a:13,b:5,picture:'__IMG:large-sub-13-5__'},
};
const result = ({kind,a,b}) => kind==='add' ? a+b : a-b;
const answer = (id) => model[id].kind+'-'+result(model[id]);
const cue = (id) => model[id].cue??'lantern-launch-'+model[id].kind;
const equation = (id) => {
  const m=model[id];
  return m.a+(m.kind==='add'?'+':'−')+m.b+'='+result(m);
};
const positions = [[384,640,896],[352,543,737,928],[352,543,737,928]];
const queues = [['add-6-2','sub-9-4'],['add-7-3','sub-12-4','add-5-4'],['add-7-5','sub-14-5','sub-13-5']];
const targets = [['add-8','sub-5','add-5'],['add-10','sub-8','add-9','add-8'],['sub-9','add-12','sub-12','sub-8']];
const speeds = [[392,0,170,118],[457,11,152,112],[510,19,148,108]];
const hints = ['先想要找整体，还是其中的一部分。','先对好方向，再发射。'];
const feedback = {hint:'lantern-launch-hint',hint2:'lantern-launch-help',praise:'lantern-launch-praise'};
const levels = queues.map((queue,index) => {
  const [speed,drift,targetWidth,targetHeight]=speeds[index];
  return {queue,speed,drift,targetWidth,targetHeight,hints,
    pairs:queue.map(id=>[id,answer(id)]),
    targets:targets[index].map((value,i)=>({value,x:positions[index][i]}))};
});

const title='弹珠找回缺的数';
K.ready({title,sub:'听清要找什么，瞄准关系和得数都相合的牌。'});
const arcade=K.gameTemplates.magnetMarbles({
  title,voiceLead:true,stepVoiceLead:true,doneText:'关系和得数都配好了。',
  levels,
  cues:queues.map(queue=>({...feedback,goal:cue(queue[0]),steps:queue.map(cue)})),
  art:{
    backdrop:'__IMG:marble-backdrop__',sticker:'__IMG:lantern-sticker__',frames:['__IMG:wood-marble__'],
    icons:{
      'add-6-2':'__IMG:model-add-6-2__','sub-9-4':'__IMG:model-sub-9-4__','add-7-3':'__IMG:model-add-7-3__',
      'sub-12-4':'__IMG:model-sub-12-4__','add-5-4':'__IMG:model-add-5-4__','add-7-5':'__IMG:model-add-7-5__',
      'sub-14-5':'__IMG:model-sub-14-5__','sub-13-5':'__IMG:model-sub-13-5__',
      'add-8':'__IMG:answer-add-8__','sub-5':'__IMG:answer-sub-5__','add-5':'__IMG:answer-add-5__',
      'add-10':'__IMG:answer-add-10__','sub-8':'__IMG:answer-sub-8__','add-9':'__IMG:answer-add-9__',
      'add-12':'__IMG:answer-add-12__','sub-9':'__IMG:answer-sub-9__','sub-12':'__IMG:answer-sub-12__',
    },
  },
});
const proof=K.$('#relation-proof');
const picture=K.$('#relation-proof-picture');
const latest=K.$('#relation-proof-result');
K.stage().appendChild(proof);
const draw=arcade.draw;
arcade.draw=(g,canvas)=>{
  draw(g,canvas);
  const queue=g.data.level?.queue;
  proof.hidden=!queue||g.state==='ready'||g.state==='done';
  if(g.state==='done'&&queue&&g.data.progress===queue.length){
    const replay=K.$('#btn-again');
    if(replay&&!K.$('.lantern-finish-equations')){
      const equations=K.el('div','lantern-finish-equations');
      equations.textContent=queue.map(equation).join('　');
      replay.parentElement.insertBefore(equations,replay);
    }
  }
  if(proof.hidden)return;
  const progress=g.data.progress;
  const m=model[queue[Math.min(progress,queue.length-1)]];
  if(picture.getAttribute('src')!==m.picture){
    picture.src=m.picture;
    picture.alt=m.kind==='add'?('两部分分别'+m.a+'和'+m.b+'，求整体'):('整体'+m.a+'，已知一部分'+m.b+'，求另一部分');
  }
  const value=progress?equation(queue[progress-1]):'';
  if(latest.textContent!==value)latest.textContent=value;
};
K.game(arcade);
