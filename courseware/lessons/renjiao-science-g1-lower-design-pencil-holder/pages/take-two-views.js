const levels = [
  {trial:1, rate:.58, range:103, aperture:149, shots:[1,0]},
  {trial:2, rate:.74, range:150, aperture:125, shots:[0,1]},
  {trial:3, rate:.89, range:182, aperture:111, shots:[1,0]},
];
const image = (view,trial) => 'trial-'+trial+'-'+view;
const hints = ['比一比小图。它是从上方看，还是从侧面看？', '把同一幅画面放进虚线框，再按快门。'];
const title = '给同一次试用拍两张';
K.ready({title, sub:'对上小图的角度，再按快门。'});
K.game(K.gameTemplates.shutterScout({
  title, doneText:'三次装笔，都拍到了两种角度。', voiceLead:true, stepVoiceLead:true,
  art:{
    backdrop:'__IMG:photo-workbench__', sticker:'__IMG:camera-badge__',
    icons:{
      'trial-1-top':'__IMG:trial-1-top__', 'trial-1-side':'__IMG:trial-1-side__',
      'trial-2-top':'__IMG:trial-2-top__', 'trial-2-side':'__IMG:trial-2-side__',
      'trial-3-top':'__IMG:trial-3-top__', 'trial-3-side':'__IMG:trial-3-side__',
    },
  },
  levels:levels.map(({trial,...level})=>({...level,hints,photoViews:{top:image('top',trial),side:image('side',trial)}})),
  cues:levels.map(({trial,shots})=>({
    goal:'photo-load-'+trial, hint:'photo-hint', hint2:'photo-help', praise:'photo-praise',
    steps:shots.map(shot=>shot?'photo-top':'photo-side'),
  })),
  observation:{
    sceneId:'scene-take-two-views',
    trials:{'same-load-views':{top:levels.map(l=>image('top',l.trial)),side:levels.map(l=>image('side',l.trial))}},
  },
}));
K.$('button[data-arc-input="action"]').id = 'pencil-shutter';
