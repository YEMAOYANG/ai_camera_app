K.ready({title:'拼好纸花桥的空位',sub:'把纸片移到空位上，转好方向再落下。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:edge-check__';},{once:true});

const hints=['先看看空位占几格。','长边、短边都对好。要转方向，可以点转动键。'];
const cues={goal:'bridge-goal',hint:'bridge-hint',hint2:'bridge-help',praise:'bridge-praise'};
K.game(K.gameTemplates.shapeBridge({
  art:{backdrop:'__IMG:bridge-bank__',frames:['__IMG:rabbit-ready__','__IMG:rabbit-hop__'],sticker:'__IMG:petal-sticker__'},
  voiceLead:true,cues:[cues,cues,cues],
  doneText:'桥面的空位都补好啦！',
  levels:[
    {seconds:7.2,hints,slots:[
      {col:4,cells:[[0,0],[1,0]]},
      {col:7,cells:[[0,0],[1,0],[0,1],[1,1]]},
    ]},
    {seconds:5.9,hints,slots:[
      {col:0,cells:[[0,0],[1,0],[2,0]],turns:1},
      {col:7,cells:[[0,0],[0,1]],turns:0},
    ]},
    {seconds:4.7,hints,slots:[
      {col:0,cells:[[0,0],[0,1],[1,1]],turns:1},
      {col:3,cells:[[0,0],[1,0],[2,0],[1,1]],turns:2},
      {col:7,cells:[[0,0],[1,0],[0,1],[1,1]],turns:0},
    ]},
  ],
}));
K.$('[data-arc-input=up]').id='bridge-spin';
K.$('[data-arc-input=action]').id='bridge-drop';
const setTeacherState=K.onState;
K.onState=(state,content)=>{
  setTeacherState(state,content);
  if(state.pause===false||state.demo===false){
    for(const anchor of K.$$('.teach-hl'))anchor.classList.remove('teach-hl');
  }
};
