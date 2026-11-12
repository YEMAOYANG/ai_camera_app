K.ready({title:'兔兔数线跳',sub:'跑起来，再跳到下一站。每两站之间的一格都一样长。'});

const spacing = 146;
const midpoint = platform => platform[0] + platform[2]/2;

function track({start,end,origin,direction,steps,speed,width,prompt,hints}) {
  const count = end-start+1;
  const platforms = Array.from({length:count},(_,index)=>[
    640 + spacing*(index-(count-1)/2) - width/2, 443, width,
    start+index===origin ? 'start' : start+index,
  ]);
  return {platforms,startLabel:origin,prompt,speed,hints,route:Array.from({length:steps},
    (_,index)=>origin + direction*(index+1))};
}

const trackGame = K.gameTemplates.platformHop({
  art:{backdrop:'__IMG:arcade-clouds__',sticker:'__IMG:arcade-sticker__',frames:[
    '__IMG:arcade-rabbit-ready__','__IMG:arcade-rabbit-run__','__IMG:arcade-rabbit-jump__',
  ]},
  doneText:'数对了每一格，兔兔到站！',
  levels:[
    track({start:10,end:16,origin:11,direction:1,steps:3,speed:255,width:116,prompt:'+1',
      hints:['从脚下的数接着往大了数。','先看相邻两站，落到台面边上也行。']}),
    track({start:12,end:18,origin:17,direction:-1,steps:4,speed:282,width:104,prompt:'−1',
      hints:['倒着数，找小一格的台子。','先看脚下，再找左边紧挨着的一站。']}),
    track({start:11,end:18,origin:14,direction:-1,steps:3,speed:313,width:94,prompt:'↔',
      hints:['数清两头各隔着几个小格。','手指按一格一步数，找脚步更少的一边。']}),
  ],
  cues:[
    {goal:'track-up',hint:'track-hint',hint2:'track-help',praise:'track-done'},
    {goal:'track-down',hint:'track-hint',hint2:'track-help',praise:'track-done'},
    {goal:'track-near',hint:'track-steps',hint2:'track-compare',praise:'track-done'},
  ],
});

const drawTrack = trackGame.draw;
let previousSteps = 0;
trackGame.draw = (game, canvas) => {
  drawTrack(game, canvas);
  const {level,w,progress} = game.data;
  if (!w) return;
  if (progress>previousSteps && game.bubbleObj?.kind==='no') game.bubbleObj=null;
  previousSteps = progress;
  const first = midpoint(level.platforms[0]);
  const last = midpoint(level.platforms.at(-1));
  const origin = midpoint(level.platforms.find(p=>p[3]==='start'));
  const reached = midpoint(w.checkpoint);
  K.draw.rr(canvas,first-44,530,last-first+88,72,18);
  canvas.fillStyle='#233f35';canvas.fill();
  canvas.lineCap='round';
  const segment = (a,b,y,color,width) => {
    canvas.beginPath();canvas.moveTo(a,y);canvas.lineTo(b,y);
    canvas.strokeStyle=color;canvas.lineWidth=width;canvas.stroke();
  };
  segment(first,last,561,'#fff0d4',4);
  if (reached!==origin) segment(origin,reached,561,'#f1a75d',8);
  for (const platform of level.platforms) {
    const x = midpoint(platform);
    const n = platform[3]==='start' ? level.startLabel : platform[3];
    canvas.fillStyle='#fff0d4';canvas.fillRect(x-3,551,6,20);
    K.draw.text(canvas,String(n),x,585,25,x===reached?'#ffd389':'#fff0d4');
  }
};

K.game(trackGame);
