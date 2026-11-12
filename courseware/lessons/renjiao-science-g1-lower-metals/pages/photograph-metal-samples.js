const rounds = [
  {sample:'copper',rate:.58,range:106,aperture:149,shots:[1,0]},
  {sample:'iron',rate:.78,range:166,aperture:120,shots:[0,1,0]},
  {sample:'aluminum',rate:1.02,range:216,aperture:104,shots:[1,0,1,0]},
];
const view = (direction,sample) => 'metal-'+direction+'-'+sample;
const title = '给同一根样条拍两面';
const hints = ['把整根样条放进虚线框。','再等等，让样条转到小图的方向。'];
K.ready({title,sub:'等样条的角度和小图一样，再按快门。'});
const camera = K.gameTemplates.shutterScout({
  title,doneText:'三根样条的两面都拍好了。',voiceLead:true,stepVoiceLead:true,
  art:{
    backdrop:'__IMG:metal-camera-bench__',sticker:'__IMG:metal-observation-camera__',
    icons:{
      'metal-top-copper':'__IMG:metal-top-copper__','metal-side-copper':'__IMG:metal-side-copper__',
      'metal-top-iron':'__IMG:metal-top-iron__','metal-side-iron':'__IMG:metal-side-iron__',
      'metal-top-aluminum':'__IMG:metal-top-aluminum__','metal-side-aluminum':'__IMG:metal-side-aluminum__',
    },
  },
  levels:rounds.map(({sample,...level})=>({...level,hints,photoViews:{top:view('top',sample),side:view('side',sample)}})),
  cues:rounds.map(({shots})=>({
    goal:'sample-photo-goal',hint:'sample-photo-hint',hint2:'sample-photo-help',praise:'sample-photo-praise',
    steps:shots.map(shot=>shot?'sample-photo-top':'sample-photo-side'),
  })),
  observation:{
    sceneId:'scene-photograph-metal-samples',
    trials:{'same-metal-two-views':{top:rounds.map(r=>view('top',r.sample)),side:rounds.map(r=>view('side',r.sample))}},
  },
});
K.game({...camera, bubbleAt: () => ({x:640,y:36})});
