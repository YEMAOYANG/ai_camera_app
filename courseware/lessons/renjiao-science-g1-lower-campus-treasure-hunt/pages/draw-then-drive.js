const layouts=[
  {map:[
    '#########',
    '#########',
    '#....B.E#',
    '#.###.###',
    '#S...A###',
    '#########',
    '#########',
  ],route:['A','B'],step:.28,startIcon:'plant'},
  {map:[
    '#########',
    '##D...E##',
    '##.###.##',
    '##.....##',
    '##.###.##',
    '##C...S##',
    '#########',
  ],route:['C','D'],step:.23,startIcon:'book'},
  {map:[
    '#########',
    '##G...F##',
    '##.###.##',
    '##E....##',
    '#S....H##',
    '#########',
    '#########',
  ],route:['H','F','G'],step:.18,startIcon:'bench'},
];
const hints=['停一停，先看看上一站，再重听。','先回到最后一个对的地标，再找方向和下一站。'];
const cues=[
  ['hunt-plant-to-bucket','hunt-bucket-to-drum','hunt-drum-exit'],
  ['hunt-book-to-bench','hunt-turn-right-chime','hunt-chime-exit'],
  ['hunt-bench-to-palette','hunt-palette-to-tin','hunt-tin-to-board','hunt-board-exit'],
];
const startArt={plant:'__IMG:pot-plant__',book:'__IMG:blue-book__',bench:'__IMG:ochre-bench__'};
const starts=layouts.map(l=>{
  const y=l.map.findIndex(row=>row.includes('S'));
  const pic=new Image();pic.src=startArt[l.startIcon];
  return {x:l.map[y].indexOf('S'),y,pic};
});
const title='按寻宝卡走到下一站';
K.ready({title,sub:'先找起点，看方向标，再听每一段。'});
const compass=K.$('#hunt-compass');
K.stage().appendChild(compass);
const maze=K.gameTemplates.bubbleMaze({
  title,doneText:'起点、转弯和地标都核对过了。',
  voiceLead:true,stepVoiceLead:true,
  art:{
    backdrop:'__IMG:maze-background__',sticker:'__IMG:treasure-tin__',
    frames:['__IMG:scout-idle__','__IMG:scout-move__'],
    icons:{A:'__IMG:blue-bucket__',B:'__IMG:plum-drum__',C:'__IMG:ochre-bench__',D:'__IMG:wind-chime__',
      F:'__IMG:treasure-tin__',G:'__IMG:notice-board__',H:'__IMG:wood-palette__'},
  },
  levels:layouts.map(({startIcon,...level})=>({...level,hints,listenOnly:true})),
  cues:cues.map(steps=>({goal:steps[0],steps,hint:'hunt-hint',hint2:'hunt-help',praise:'hunt-praise'})),
});
const draw=maze.draw;
maze.draw=(g,c)=>{
  draw(g,c);
  compass.hidden=g.state==='ready'||g.state==='done';
  const w=g.data.w;
  if(!w||g.state==='done') return;
  const start=starts[g.level];
  const x=w.ox+start.x*67+16,y=w.oy+start.y*67+14;
  c.fillStyle='#fff5d5';
  K.draw.rr(c,x-15,y-14,31,28,8);
  c.fill();
  if (start.pic.complete && start.pic.naturalWidth) {
    const scale=Math.min(26/start.pic.naturalWidth,24/start.pic.naturalHeight);
    const width=start.pic.naturalWidth*scale,height=start.pic.naturalHeight*scale;
    c.drawImage(start.pic,x-width/2,y-height/2,width,height);
  }
};
K.game(maze);
