const pictures = {
  loose2:"__IMG:sort-loose-2__", loose3:"__IMG:sort-loose-3__", loose4:"__IMG:sort-loose-4__",
  loose6:"__IMG:sort-loose-6__", loose7:"__IMG:sort-loose-7__",
  strips1:"__IMG:sort-strip-1__", strips2:"__IMG:sort-strip-2__", strips3:"__IMG:sort-strip-3__",
  strips4:"__IMG:sort-strip-4__",
  dock1:"__IMG:one-unit-marker__", dock10:"__IMG:ten-unit-marker__"
};
const fallback={loose2:"2",loose3:"3",loose4:"4",loose6:"6",loose7:"7",
  strips1:"10",strips2:"20",strips3:"30",strips4:"40",dock1:"1",dock10:"10"};
const hints=["先看它是成条，还是散的。","看托盘图，从卡后面推。"];
const cues=(goal)=>({goal,hint:"sort-hint",hint2:"sort-help",praise:"sort-praise"});

K.ready({title:"整条散贴分开送",sub:"先看是一条条还是一枚枚。从图卡背后推，送到同类托盘。"});

const levels=[
  {
    map:["########","#......#","#S.....#","#......#","########"],step:.34,hints,labels:fallback,
    items:[{x:2,y:2,token:"loose2",group:"ones"},{x:5,y:3,token:"strips1",group:"tens"}],
    docks:[{x:3,y:2,sample:"dock1",group:"ones"},{x:2,y:3,sample:"dock10",group:"tens"}]
  },
  {
    map:["#########","#.......#","#..#....#","#.S.....#","#.......#","#########"],step:.28,hints,labels:fallback,
    items:[{x:4,y:2,token:"loose3",group:"ones"},
      {x:4,y:4,token:"strips2",group:"tens"},{x:3,y:3,token:"loose4",group:"ones"}],
    docks:[{x:6,y:2,sample:"dock1",group:"ones"},
      {x:7,y:4,sample:"dock10",group:"tens"},{x:6,y:3,sample:"dock1",group:"ones"}]
  },
  {
    map:["##########","#........#","#..#.....#","#.S......#","#....#...#","#........#","##########"],step:.23,hints,labels:fallback,
    items:[{x:4,y:3,token:"loose6",group:"ones"},{x:7,y:4,token:"strips4",group:"tens"},
      {x:4,y:2,token:"strips3",group:"tens"},{x:4,y:5,token:"loose7",group:"ones"}],
    docks:[{x:7,y:3,sample:"dock1",group:"ones"},{x:8,y:4,sample:"dock10",group:"tens"},
      {x:8,y:2,sample:"dock10",group:"tens"},{x:7,y:5,sample:"dock1",group:"ones"}]
  }
];

const options=K.gameTemplates.sortingDepot({
  voiceLead:true,
  cues:[cues("sort-first"),cues("sort-two"),cues("sort-three")],
  art:{
    backdrop:"__IMG:sort-yard__",sticker:"__IMG:craft-sticker-badge__",
    frames:["__IMG:craft-cart__","__IMG:craft-cart-push__"],icons:pictures
  },
  doneText:"整条和散贴各归各位！",
  levels
});

options.bubbleAt=()=>({x:640,y:98});
options.onState=(_game,state)=>{
  if (state.demo===false) K.$$(".teach-hl").forEach((element)=>element.classList.remove("teach-hl"));
};

const game=K.game(options);
function firstCell(frame,point){
  const board=frame.data.w;
  if (!board||frame.level!==0) return null;
  const half=board.s*.45;
  return {x:board.ox+(point.x+.5)*board.s-half,y:board.oy+(point.y+.5)*board.s-half,w:half*2,h:half*2};
}
game.follow("#first-loose-card",frame=>firstCell(frame,levels[0].items[0]));
game.follow("#first-one-dock",frame=>firstCell(frame,levels[0].docks[0]));
