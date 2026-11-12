K.ready({title:'工具送到工作台',sub:'看图里的任务，从工具卡后面推。'});
K.$('#ready .card').prepend(K.$('#sort-tools-opening').content.cloneNode(true));

const hints = ['先看看这张托盘图要做什么。','对一对工具的末端，再从后面慢慢推。'];
const labels = {
  scissors:'剪刀',tongs:'长夹',driver:'螺丝刀',stencil:'图形尺',
  cut:'剪纸',ring:'夹布环',screw:'拧螺丝',triangle:'画三角形',
};
const cue = {goal:'sort-goal',hint:'sort-hint',hint2:'sort-help',praise:'sort-praise'};

K.game(K.gameTemplates.sortingDepot({
  art:{
    frames:['__IMG:workshop-cart__'],sticker:'__IMG:workshop-cart__',
    icons:{scissors:'__IMG:scissors__',tongs:'__IMG:tongs-top__',driver:'__IMG:driver-icon__',
      stencil:'__IMG:stencil-top__',cut:'__IMG:paper-cut-task__',ring:'__IMG:ring-in-box__',
      screw:'__IMG:screw-task__',triangle:'__IMG:triangle-task__'},
  },
  voiceLead:true,
  cues:[cue,cue,cue],
  doneText:'每件工具都到需要它的工作台啦！',
  levels:[
    {
      map:['########','#......#','#.S....#','#......#','########'],step:.34,hints,labels,
      items:[{x:3,y:2,token:'scissors',group:'cut'},{x:3,y:3,token:'tongs',group:'grip'}],
      docks:[{x:5,y:2,sample:'cut',group:'cut'},{x:6,y:3,sample:'ring',group:'grip'}],
    },
    {
      map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],step:.28,hints,labels,
      items:[{x:4,y:2,token:'driver',group:'turn'},{x:4,y:4,token:'tongs',group:'grip'},
        {x:3,y:3,token:'scissors',group:'cut'}],
      docks:[{x:6,y:2,sample:'screw',group:'turn'},{x:7,y:4,sample:'ring',group:'grip'},
        {x:6,y:3,sample:'cut',group:'cut'}],
    },
    {
      map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],step:.22,hints,labels,
      items:[{x:4,y:3,token:'stencil',group:'trace'},{x:7,y:4,token:'scissors',group:'cut'},
        {x:4,y:2,token:'driver',group:'turn'},{x:4,y:5,token:'tongs',group:'grip'}],
      docks:[{x:7,y:3,sample:'triangle',group:'trace'},{x:8,y:4,sample:'cut',group:'cut'},
        {x:8,y:2,sample:'screw',group:'turn'},{x:7,y:5,sample:'ring',group:'grip'}],
    },
  ],
}));

const setTeacherState = K.onState;
K.onState = (state, content) => {
  setTeacherState(state, content);
  if (state.demo === false) {
    for (const anchor of K.$$('.teach-hl')) anchor.classList.remove('teach-hl');
  } else if (state.pause === false) {
    K.$('#sort-demo-tool').classList.remove('teach-hl');
  }
};
