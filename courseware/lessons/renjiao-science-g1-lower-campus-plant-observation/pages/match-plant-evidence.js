const groups = {
  jasmine: ['clue-jasmine','whole-jasmine','marble-jasmine'],
  forsythia: ['clue-forsythia','whole-forsythia','marble-forsythia'],
  willow: ['clue-willow','whole-willow','marble-willow'],
  pine: ['clue-pine','whole-pine','marble-pine'],
};
const rounds = [
  {targetWidth:172, targetHeight:120, speed:420, drift:0,
    queue:['jasmine','forsythia'], targets:[[397,'jasmine'],[640,'forsythia'],[886,'willow']]},
  {targetWidth:157, targetHeight:115, speed:475, drift:10,
    queue:['willow','jasmine','pine'], targets:[[355,'pine'],[545,'willow'],[735,'jasmine'],[925,'forsythia']]},
  {targetWidth:146, targetHeight:110, speed:524, drift:16,
    queue:['forsythia','pine','jasmine','willow'], targets:[[365,'forsythia'],[550,'pine'],[733,'jasmine'],[920,'willow']]},
];
const title = '植物线索对对碰';
const sub = '发射弹珠，把局部线索送回整株图。';
const hints = ['先看看弹珠上是哪一处。','两株同色时，再比一比枝条和花形。'];
K.ready({title,sub});
K.game(K.gameTemplates.magnetMarbles({
  title, sub, doneText:'每处线索都找到了自己的整株图。', voiceLead:true, stepVoiceLead:true,
  art:{
    backdrop:'__IMG:garden-background__', sticker:'__IMG:campus-plant-camera__',
    frames:['__IMG:observation-marble__'],
    icons:{
      'clue-jasmine':'__IMG:clue-jasmine__','whole-jasmine':'__IMG:whole-jasmine__',
      'clue-forsythia':'__IMG:clue-forsythia__','whole-forsythia':'__IMG:whole-forsythia__',
      'clue-willow':'__IMG:clue-willow__','whole-willow':'__IMG:whole-willow__',
      'clue-pine':'__IMG:clue-pine__','whole-pine':'__IMG:whole-pine__',
    },
  },
  levels:rounds.map(({queue,targets,...level})=>({
    ...level, hints, queue:queue.map(group=>groups[group][0]),
    targets:targets.map(([x,group])=>({x,value:groups[group][1]})),
    pairs:queue.map(group=>groups[group].slice(0,2)),
  })),
  cues:rounds.map(({queue})=>({
    goal:'marble-goal', hint:'marble-hint', hint2:'marble-help', praise:'marble-praise',
    steps:queue.map(group=>groups[group][2]),
  })),
}));
// Give the teacher the actual launch button, including its responsive position.
K.$('button[data-arc-input="action"]').id = 'plant-launch';
