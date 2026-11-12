K.ready({title:'推车找同类立体',sub:'看整块的形状，从后面推到同类图盘。'});
const opening = K.$('#ready .pic');
opening.style.objectFit = 'contain';
opening.addEventListener('error', () => { opening.src = '__IMG:sample-build__'; }, {once:true});

const hints = ['先停一下，看看整块的形状。','再对照托盘图，找相同的面。也能退一步。'];
const cues = {goal:'sort-goal',hint:'sort-hint',hint2:'sort-help',praise:'sort-praise'};
const sample = {long:'long-box',cube:'cube-box',cyl:'cyl-box',ball:'ball-box'};

K.game(K.gameTemplates.sortingDepot({
  art:{
    backdrop:'__IMG:lab-background__',sticker:'__IMG:kite-sticker__',
    frames:['__IMG:cart-rest__','__IMG:cart-push__'],
    icons:{
      long:'__IMG:token-long__',cube:'__IMG:token-cube__',cyl:'__IMG:token-cylinder__',
      ball:'__IMG:token-ball__','long-box':'__IMG:sample-long__','cube-box':'__IMG:sample-cube__',
      'cyl-box':'__IMG:sample-cylinder__','ball-box':'__IMG:sample-ball__',
    },
  },
  voiceLead:true,
  cues:[cues,cues,cues],
  doneText:'四种立体都有自己的位置啦！',
  levels:[
    {
      map:['########','#......#','#.S....#','#......#','#......#','########'],step:.35,hints,
      items:[{x:3,y:2,token:'long',group:'long'},{x:5,y:3,token:'cube',group:'cube'}],
      docks:[{x:5,y:2,sample:sample.long,group:'long'},{x:6,y:3,sample:sample.cube,group:'cube'}],
    },
    {
      map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],step:.29,hints,
      items:[{x:4,y:2,token:'cube',group:'cube'},{x:4,y:4,token:'cyl',group:'cyl'},
        {x:3,y:3,token:'long',group:'long'}],
      docks:[{x:6,y:2,sample:sample.cube,group:'cube'},{x:7,y:4,sample:sample.cyl,group:'cyl'},
        {x:6,y:3,sample:sample.long,group:'long'}],
    },
    {
      map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],step:.23,hints,
      items:[{x:4,y:3,token:'ball',group:'ball'},{x:7,y:4,token:'cube',group:'cube'},
        {x:4,y:2,token:'cyl',group:'cyl'},{x:4,y:5,token:'long',group:'long'}],
      docks:[{x:7,y:3,sample:sample.ball,group:'ball'},{x:8,y:4,sample:sample.cube,group:'cube'},
        {x:8,y:2,sample:sample.cyl,group:'cyl'},{x:7,y:5,sample:sample.long,group:'long'}],
    },
  ],
}));

const setTeacherState = K.onState;
K.onState = (state, content) => {
  setTeacherState(state, content);
  if (state.pause === false || state.demo === false) {
    for (const anchor of K.$$('.teach-hl')) anchor.classList.remove('teach-hl');
  }
};
