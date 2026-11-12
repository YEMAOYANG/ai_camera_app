K.startPictureFallback=()=>{
  const picture=K.el('img','pic');
  picture.src='__IMG:exhibit-cover__';
  picture.alt='观察员在展桌上练习找线索';
  return picture;
};
K.ready({title:'跳到新的合计',sub:'每加一块，跳到此刻的合计。'});
K.$('#ready .pic').style.objectFit='contain';

const clueBox={x:403,y:115,w:474,h:170};
const firstTarget={x:255,y:480,w:108,h:54};
const clueImages=['__IMG:hop-clues-1__','__IMG:hop-clues-2__','__IMG:hop-clues-3__'].map(source=>{
  const image=new Image();
  image.src=source;
  return image;
});
const levels=[
  {speed:280,route:[1,3,8],prompt:null,startLabel:0,
    platforms:[[82,480,126,'start'],[255,480,108,1],[440,487,108,3],[625,473,108,8],
      [153,372,79,2],[339,390,78,5],[797,515,100,7]],
    hints:['一次只加一块，先找这一步的合计。','看亮起来的合计台，落稳再跳。']},
  {speed:294,route:[2,7,9],prompt:null,startLabel:0,
    platforms:[[81,489,128,'start'],[257,466,104,2],[445,499,103,7],[641,458,106,9],
      [162,369,80,3],[354,369,78,5],[826,512,98,10]],
    hints:['从已经落稳的数字开始，添上下一块。','看亮起来的合计台，落稳再跳。']},
  {speed:318,route:[5,7,9,11],prompt:null,startLabel:0,
    platforms:[[87,495,130,'start'],[273,476,100,5],[466,501,100,7],[676,451,102,9],[879,474,102,11],
      [175,368,80,2],[373,374,77,6],[1026,532,95,12]],
    hints:['又来一块二，就比当前合计多二。','看亮起来的合计台，落稳再跳。']},
];
const options=K.gameTemplates.platformHop({
  levels,
  art:{backdrop:'__IMG:gallery-backdrop__',sticker:'__IMG:exhibit-sticker__',
    frames:['__IMG:fox-ready__','__IMG:fox-run__','__IMG:fox-jump__']},
  cues:['hop-one','hop-two','hop-three'].map(goal=>({goal,hint:'hop-hint',hint2:'hop-help',praise:'hop-praise'})),
  voiceLead:true,
  doneText:'每加一块，你都找到了新的合计！',
});
const drawGame=options.draw;
options.draw=(game,context)=>{
  drawGame(game,context);
  const picture=clueImages[game.level];
  const {x,y,w,h}=clueBox;
  if(picture?.complete&&picture.naturalWidth)context.drawImage(picture,x,y,w,h);
};
options.onState=(game,state)=>{
  if(state.demo===false)for(const node of K.$$('.teach-hl'))node.classList.remove('teach-hl');
};
const game=K.game(options);
game.follow('#hop-clue',()=>clueBox);
game.follow('#hop-first',()=>firstTarget);
