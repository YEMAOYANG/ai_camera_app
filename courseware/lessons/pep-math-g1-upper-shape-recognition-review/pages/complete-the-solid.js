K.ready({title:'接积木补完整',sub:'看虚线缺口。移到合适的图旁，再让积木落下。'});
const opening = K.$('#ready .pic');
opening.style.objectFit = 'contain';
opening.addEventListener('error', () => { opening.src = '__IMG:sample-build__'; }, {once:true});

const hints = ['先看下面图卡的虚线缺口。','比一比接上的面。轮廓对齐，再落下。'];
const cues = {goal:'build-goal',hint:'build-hint',hint2:'build-help',praise:'build-praise'};
const pairs = [
  ['piece-thin','base-thin'],['piece-wide','base-wide'],['piece-four','base-four'],
  ['piece-row','base-row'],['piece-pair','base-pair'],['piece-wall','base-wall'],['piece-beam','base-beam'],
];

const options=K.gameTemplates.fallingTiles({
  art:{
    backdrop:'__IMG:lab-background__',sticker:'__IMG:kite-sticker__',
    icons:{
      'piece-thin':'__IMG:piece-thin__','piece-wide':'__IMG:piece-wide__','piece-four':'__IMG:piece-four__',
      'piece-row':'__IMG:piece-row__','piece-pair':'__IMG:piece-pair__',
      'piece-wall':'__IMG:piece-wall__','piece-beam':'__IMG:piece-beam__',
      'base-thin':'__IMG:base-thin__','base-wide':'__IMG:base-wide__','base-four':'__IMG:base-four__',
      'base-row':'__IMG:base-row__','base-pair':'__IMG:base-pair__',
      'base-wall':'__IMG:base-wall__','base-beam':'__IMG:base-beam__',
    },
  },
  voiceLead:true,
  cues:[cues,cues,cues],
  doneText:'每个缺口都补成完整的立体啦！',
  levels:[
    {bottom:[null,'base-wide',null,null,'base-thin',null],pieces:['piece-thin','piece-wide'],interval:1.69,pairs,hints},
    {bottom:[null,'base-pair',null,'base-four',null,'base-row'],pieces:['piece-four','piece-row','piece-pair'],interval:1.38,pairs,hints},
    {bottom:['base-wall',null,'base-four',null,'base-beam',null],pieces:['piece-wall','piece-four','piece-beam'],interval:1.08,pairs,hints},
  ],
});

const finished = Object.fromEntries(Object.entries({
  'piece-thin':'__IMG:built-thin__','piece-wide':'__IMG:built-wide__','piece-four':'__IMG:built-four__',
  'piece-row':'__IMG:built-row__','piece-pair':'__IMG:built-pair__',
  'piece-wall':'__IMG:built-wall__','piece-beam':'__IMG:built-beam__',
}).map(([key,src])=>{
  const result=new Image();
  result.src=src;
  return [key,result];
}));
options.drawTop=(game,canvas)=>{
  const progress=game.data.progress;
  if (!progress) return;
  const image=finished[game.data.level.pieces[progress-1]];
  canvas.fillStyle='#36574b';
  K.draw.rr(canvas,1056,401,134,134,18);
  canvas.fill();
  if(image.complete&&image.naturalWidth)canvas.drawImage(image,1064,409,117,117);
};
K.game(options);

const setTeacherState = K.onState;
K.onState = (state, content) => {
  setTeacherState(state, content);
  if (state.pause === false || state.demo === false) {
    for (const anchor of K.$$('.teach-hl')) anchor.classList.remove('teach-hl');
  }
};
