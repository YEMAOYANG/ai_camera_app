K.ready({title:'贝壳送船队',sub:'听清要找几只船，瞄准那一队发射。'});

const boatPictures={1:'__IMG:boat-target-1__',2:'__IMG:boat-target-2__',3:'__IMG:boat-target-3__',
  4:'__IMG:boat-target-4__',6:'__IMG:boat-target-6__',8:'__IMG:boat-target-8__'};

function courseLeg(queue, targets, speed, drift) {
  return {queue,targets:targets.map((value,i)=>({value,x:[370,640,910][i]})),speed,drift,
    matches:(spoken,count)=>spoken===count,listenOnly:true,
    targetFallbackCounts:{1:1,2:2,3:3,4:4,6:6,8:8},
    targetWidth:184,targetHeight:112,hints:['从左往右，把船一只只数到。','先看亮起来的一队，再慢慢瞄准。']};
}

K.game(K.gameTemplates.magnetMarbles({
  art:{backdrop:'__IMG:game-harbor__',sticker:'__IMG:game-shell__',frames:['__IMG:game-shell__'],icons:boatPictures},
  doneText:'贝壳都送到啦！',
  cues:[
    {steps:['word-two','word-three'],hint:'count-hint',hint2:'count-help',praise:'count-praise'},
    {steps:['word-four','word-six'],hint:'count-hint',hint2:'count-help',praise:'count-praise'},
    {steps:['word-eight','word-one','word-six'],hint:'count-hint',hint2:'count-help',praise:'count-praise'},
  ],
  levels:[courseLeg([2,3],[2,1,3],350,0),courseLeg([4,6],[6,3,4],430,8),
          courseLeg([8,1,6],[6,8,1],515,15)],
}));
