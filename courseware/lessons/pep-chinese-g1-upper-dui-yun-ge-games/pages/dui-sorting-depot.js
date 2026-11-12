K.ready({title:'推车送图卡',sub:'开到图卡后面，把它推到同类的托盘里。'});
K.$('#ready .card').prepend(K.$('#dui-depot-cover').content.cloneNode(true));

const hints = ['看看托盘里的图，和图卡是同一类吗？','换个位置，从图卡背后慢慢推。'];
const cues = {goal:'depot-goal',hint:'depot-hint',hint2:'depot-help',praise:'depot-praise'};
const labels = {flower:'花',tree:'树',bird:'鸟',insect:'虫',rain:'雨',wind:'风'};

K.game(K.gameTemplates.sortingDepot({
  art:{
    backdrop:'__IMG:trace-scene__',sticker:'__IMG:duet__',frames:['__IMG:trace-car__'],
    icons:{flower:'__IMG:flower__',tree:'__IMG:tree__',bird:'__IMG:bird__',insect:'__IMG:insect__',
      rain:'__IMG:rain__',wind:'__IMG:wind__'},
  },
  voiceLead:true,
  cues:[cues,cues,cues],
  doneText:'同类图卡都送回家啦！',
  levels:[
    {
      map:['########','#......#','#.S....#','#......#','########'],step:.33,hints,labels,
      items:[{x:3,y:2,token:'flower',group:'plant'},{x:3,y:3,token:'rain',group:'weather'}],
      docks:[{x:5,y:2,sample:'tree',group:'plant'},{x:6,y:3,sample:'wind',group:'weather'}],
    },
    {
      map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],step:.27,hints,labels,
      items:[{x:4,y:2,token:'bird',group:'animal'},{x:4,y:4,token:'wind',group:'weather'},
        {x:3,y:3,token:'tree',group:'plant'}],
      docks:[{x:6,y:2,sample:'insect',group:'animal'},{x:7,y:4,sample:'rain',group:'weather'},
        {x:6,y:3,sample:'flower',group:'plant'}],
    },
    {
      map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],step:.22,hints,labels,
      items:[{x:4,y:3,token:'flower',group:'plant'},{x:7,y:4,token:'tree',group:'plant'},
        {x:4,y:2,token:'insect',group:'animal'},{x:4,y:5,token:'rain',group:'weather'}],
      docks:[{x:7,y:3,sample:'tree',group:'plant'},{x:8,y:4,sample:'flower',group:'plant'},
        {x:8,y:2,sample:'bird',group:'animal'},{x:7,y:5,sample:'wind',group:'weather'}],
    },
  ],
}));

const setTeacherState = K.onState;
K.onState = (state, content) => {
  setTeacherState(state, content);
  if (state.demo === false) {
    for (const anchor of K.$$('.teach-hl')) anchor.classList.remove('teach-hl');
  } else if (state.pause === false) {
    K.$('#demo-flower').classList.remove('teach-hl');
  }
};
