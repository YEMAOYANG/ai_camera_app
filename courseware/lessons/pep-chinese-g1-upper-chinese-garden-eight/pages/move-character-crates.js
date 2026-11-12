K.ready({title:'字卡推到合适的盘',sub:'先看字的结构，再从字卡后面推。'});
const opening = K.$('#ready .pic');
opening.style.objectFit = 'contain';
opening.addEventListener('error', () => { opening.src = '__IMG:structure-examples__'; }, {once:true});

const hints = ['先停一下。看看这张字卡的结构。','分不出两块的，看看整块图盘。也可退一步重新走。'];
const feedback = {goal:'crate-goal',hint:'crate-hint',hint2:'crate-help',praise:'crate-praise'};

K.game(K.gameTemplates.sortingDepot({
  art:{
    backdrop:'__IMG:exhibit-counter__',sticker:'__IMG:lantern-sticker__',
    frames:['__IMG:cart-rest__','__IMG:cart-push__'],
    icons:{
      ox:'__IMG:character-ox__',sheep:'__IMG:character-sheep__',
      dawn:'__IMG:character-dawn__',assemble:'__IMG:character-assemble__',bell:'__IMG:character-bell__',
      fruit:'__IMG:character-fruit__',white:'__IMG:character-white__',
      only:'__IMG:character-only__',leaf:'__IMG:character-leaf__',
      up:'__IMG:structure-up__',side:'__IMG:structure-side__',whole:'__IMG:structure-whole__',
    },
  },
  voiceLead:true,
  cues:[feedback,feedback,feedback],
  doneText:'字卡都在合适的盘里啦！',
  levels:[
    {
      map:['########','#......#','#.S....#','#......#','#......#','########'],step:.35,hints,
      items:[{x:3,y:2,token:'only',group:'up'},{x:5,y:3,token:'ox',group:'whole'}],
      docks:[{x:5,y:2,sample:'up',group:'up'},{x:6,y:3,sample:'whole',group:'whole'}],
    },
    {
      map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],step:.29,hints,
      items:[{x:4,y:2,token:'sheep',group:'whole'},{x:4,y:4,token:'dawn',group:'up'},
        {x:3,y:3,token:'assemble',group:'side'}],
      docks:[{x:6,y:2,sample:'whole',group:'whole'},{x:7,y:4,sample:'up',group:'up'},
        {x:6,y:3,sample:'side',group:'side'}],
    },
    {
      map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],step:.23,hints,
      items:[{x:4,y:3,token:'bell',group:'up'},{x:7,y:4,token:'white',group:'whole'},
        {x:4,y:2,token:'fruit',group:'whole'},{x:4,y:5,token:'leaf',group:'side'}],
      docks:[{x:7,y:3,sample:'up',group:'up'},{x:8,y:4,sample:'whole',group:'whole'},
        {x:8,y:2,sample:'whole',group:'whole'},{x:7,y:5,sample:'side',group:'side'}],
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
