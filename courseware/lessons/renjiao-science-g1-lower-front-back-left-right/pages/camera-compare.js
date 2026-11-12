const hints = ['把演员和道具放进虚线框。','等画面和上面的小图是同一个角度。'];
const levels = [
  {pose:'forward',rate:.58,range:106,aperture:149,shots:[1,0]},
  {pose:'turned',rate:.78,range:166,aperture:120,shots:[0,1,0]},
  {pose:'sideways',rate:1.02,range:216,aperture:104,shots:[1,0,1,0]},
];
const view = (side, pose) => 'stage-'+side+'-'+pose;
const title = '给同一幕拍两张照';
K.ready({title,sub:'对上小图和虚线框，再按快门。'});
K.game(K.gameTemplates.shutterScout({
  title, doneText:'照片里保留了同一幕的两个观察角度。',
  voiceLead:true,stepVoiceLead:true,
  art:{
    backdrop:'__IMG:camera-background__',sticker:'__IMG:camera-badge__',
    icons:{
      'stage-top-forward':'__IMG:stage-top-forward__','stage-side-forward':'__IMG:stage-side-forward__',
      'stage-top-turned':'__IMG:stage-top-turned__','stage-side-turned':'__IMG:stage-side-turned__',
      'stage-top-sideways':'__IMG:stage-top-sideways__','stage-side-sideways':'__IMG:stage-side-sideways__',
    },
  },
  levels:levels.map(({pose,...level})=>({...level,hints,photoViews:{top:view('top',pose),side:view('side',pose)}})),
  cues:levels.map(({shots})=>({
    goal:'camera-goal',hint:'camera-hint',hint2:'camera-help',praise:'camera-praise',
    steps:shots.map(shot=>shot?'camera-top':'camera-side'),
  })),
  observation:{
    sceneId:'scene-camera-compare',
    trials:{'stage-directions':{top:levels.map(l=>view('top',l.pose)),side:levels.map(l=>view('side',l.pose))}},
  },
}));
