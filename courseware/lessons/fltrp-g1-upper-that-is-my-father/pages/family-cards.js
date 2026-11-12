K.ready({title:'欢迎台接访客卡',sub:'听称呼。移到对应图旁，再让卡落下。'});
const opening = K.$('#ready .pic');
opening.style.objectFit = 'contain';
opening.addEventListener('error', () => { opening.src = '__IMG:welcome__'; }, {once:true});

const pairs = [
  ['a-father','link-father-a'], ['a-mother','link-mother-a'],
  ['a-grandpa','link-grandpa-a'], ['a-grandma','link-grandma-a'],
  ['a-friend','link-friend-a'], ['mother-father','link-father-mother'],
  ['b-father','link-father-b'],
];
const hints = ['先重听。下落的图告诉你是谁在说。','看看底下的关系图，再把卡移到旁边。'];
const feedback = {goal:'family-goal',hint:'family-hint',hint2:'family-help',praise:'family-praise'};

K.game(K.gameTemplates.fallingTiles({
  art:{
    backdrop:'__IMG:lantern-hall__',sticker:'__IMG:friend-a__',
    icons:{
      'a-father':'__IMG:host-a__','a-mother':'__IMG:host-a__',
      'a-grandpa':'__IMG:host-a__','a-grandma':'__IMG:host-a__','a-friend':'__IMG:host-a__',
      'mother-father':'__IMG:mother-a__','b-father':'__IMG:host-b__',
      'link-father-a':'__IMG:tile-father-a__','link-mother-a':'__IMG:tile-mother-a__',
      'link-grandpa-a':'__IMG:tile-grandpa-a__','link-grandma-a':'__IMG:tile-grandma-a__',
      'link-friend-a':'__IMG:tile-friend-a__','link-father-mother':'__IMG:tile-father-mother__',
      'link-father-b':'__IMG:tile-father-b__',
    },
  },
  voiceLead:true,
  stepVoiceLead:true,
  doneText:'访客卡都接到对应图旁啦！',
  cues:[
    {...feedback,steps:['a-father','a-mother']},
    {...feedback,steps:['a-grandpa','a-grandma','a-friend']},
    {...feedback,steps:['mother-father','b-father','a-grandpa']},
  ],
  levels:[
    {bottom:[null,'link-mother-a',null,null,'link-father-a',null],
      pieces:['a-father','a-mother'],interval:1.68,pairs,hints},
    {bottom:[null,'link-grandpa-a',null,'link-grandma-a',null,'link-friend-a'],
      pieces:['a-grandpa','a-grandma','a-friend'],interval:1.35,pairs,hints},
    {bottom:['link-father-mother',null,'link-father-b',null,'link-grandpa-a',null],
      pieces:['mother-father','b-father','a-grandpa'],interval:1.04,pairs,hints},
  ],
}));

const setTeacherState = K.onState;
K.onState = (state, content) => {
  setTeacherState(state, content);
  if (state.pause === false || state.demo === false) {
    for (const anchor of K.$$('.teach-hl')) anchor.classList.remove('teach-hl');
  }
};
