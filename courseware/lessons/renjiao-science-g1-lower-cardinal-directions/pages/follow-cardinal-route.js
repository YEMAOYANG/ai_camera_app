const levels = [
  {map:[
    '#########',
    '#########',
    '#....B.E#',
    '#.###.###',
    '#S...A###',
    '#########',
    '#########',
  ],route:['A','B'],step:.28,patrols:[]},
  {map:[
    '#########',
    '##D...C##',
    '##.###.##',
    '##.....##',
    '##.###.##',
    '##E...S##',
    '#########',
  ],route:['C','D'],step:.22,patrols:[{y:3,from:3,to:5,speed:.76}]},
  {map:[
    '#########',
    '#########',
    '##F....S#',
    '##.####.#',
    '##.####.#',
    '##G...E.#',
    '#########',
  ],route:['F','G'],step:.17,patrols:[{y:5,from:3,to:5,speed:1.04}]},
];
const hints = ['先停一下，听清第一站和地图的方向标。','每到一站，再从现在的位置找下一个方向。'];
const cues = [
  ['route-east-chime','route-north-bench','route-east-exit'],
  ['route-north-tree','route-west-pond','route-south-exit'],
  ['route-west-gazebo','route-south-bridge','route-east-exit'],
];
const title='按方向给庭院送信';
K.ready({title,sub:'看方向标，听口令，按次序到站。'});
const compass=K.$('#maze-compass');
K.stage().appendChild(compass);
const maze=K.gameTemplates.bubbleMaze({
  title,doneText:'听清哪一站，再从那里往下走。',
  voiceLead:true,stepVoiceLead:true,
  art:{
    backdrop:'__IMG:maze-backdrop__',sticker:'__IMG:red-pennant__',
    frames:['__IMG:rover-idle__','__IMG:rover-move__'],
    icons:{A:'__IMG:wind-chime__',B:'__IMG:vermilion-bench__',C:'__IMG:elm-tree__',
      D:'__IMG:oval-pond__',F:'__IMG:garden-gazebo__',G:'__IMG:stone-bridge__'},
  },
  levels:levels.map(level=>({...level,listenOnly:true,hints})),
  cues:cues.map(steps=>({goal:steps[0],steps,hint:'route-hint',hint2:'route-help',praise:'route-praise'})),
});
const draw=maze.draw;
maze.draw=(g,canvas)=>{
  draw(g,canvas);
  compass.hidden=g.state==='ready'||g.state==='done';
};
K.game(maze);
