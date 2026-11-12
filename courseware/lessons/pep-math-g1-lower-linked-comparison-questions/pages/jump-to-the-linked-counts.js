K.ready({title:'沿着两问的顺序跳',sub:'已知的一队 → 另一队 → 两队合计'});
K.$('#ready .pic').style.objectFit='contain';

const problemBox={x:428,y:120,w:424,h:226};
const firstLanding={x:255,y:480,w:108,h:55};
const clues=['__IMG:hop-1__','__IMG:hop-2__','__IMG:hop-3__'].map(source=>{
  const image=new Image();
  image.src=source;
  return image;
});
const levels=[
  {
    speed:280,route:[8,5,13],prompt:null,
    platforms:[[82,480,126,'start'],[255,480,108,8],[440,487,108,5],[625,473,108,13],
      [153,372,79,3],[339,390,78,11],[797,515,100,10]],
    hints:['先找这一问需要的数，再跳。','看亮起来的台面，落稳再跳下一块。'],
  },
  {
    speed:294,route:[9,13,22],prompt:null,
    platforms:[[81,489,128,'start'],[257,466,104,9],[445,499,103,13],[641,458,106,22],
      [162,369,80,4],[354,369,78,5],[826,512,98,18]],
    hints:['橙队多四个，合计要用两队实有的数。','看亮起来的台面，落稳再跳下一块。'],
  },
  {
    speed:314,route:[20,26,46],prompt:null,
    platforms:[[87,495,130,'start'],[273,476,100,20],[466,501,100,26],[676,451,102,46],
      [175,368,80,6],[373,374,77,14],[866,526,95,40]],
    hints:['找到二十和另一队的瓶数，合计要用这两个数。','看亮起来的台面，落稳再跳下一块。'],
  },
];
const options=K.gameTemplates.platformHop({
  levels,
  art:{backdrop:'__IMG:patrol-platform-landscape__',sticker:'__IMG:patrol-sticker__',
    frames:['__IMG:rabbit-ready__','__IMG:rabbit-run__','__IMG:rabbit-jump__']},
  cues:['hop-one','hop-two','hop-three'].map(goal=>({goal,hint:'hop-hint',hint2:'hop-help',praise:'hop-praise'})),
  voiceLead:true,
  doneText:'你把两问接起来了！',
});
const drawGame=options.draw;
options.draw=(game,context)=>{
  drawGame(game,context);
  const image=clues[game.level];
  const {x,y,w,h}=problemBox;
  if(image?.complete&&image.naturalWidth)context.drawImage(image,x,y,w,h);
};
const game=K.game(options);
game.follow('#hop-problem',()=>problemBox);
game.follow('#hop-first',()=>firstLanding);
