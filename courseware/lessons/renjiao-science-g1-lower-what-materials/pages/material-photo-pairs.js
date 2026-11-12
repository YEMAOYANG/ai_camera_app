const rounds = [
  {object:'stool',rate:.58,range:106,aperture:149,shots:[1,0]},
  {object:'case',rate:.78,range:166,aperture:120,shots:[0,1,0]},
  {object:'clipboard',rate:1.02,range:216,aperture:104,shots:[1,0,1,0]},
];
const title = '给同一件物品拍两种角度';
const hints = ['把整件物品移进虚线框。','等物品转到小图里的角度。'];
const view = (direction,object) => 'material-'+direction+'-'+object;
K.ready({title,sub:'看小图需要哪个角度，对准再拍。'});
const camera = K.gameTemplates.shutterScout({
  title,doneText:'三件物品的两种观察照片都收好了。',voiceLead:true,stepVoiceLead:true,
  art:{
    backdrop:'__IMG:camera-workbench__',sticker:'__IMG:material-camera__',
    icons:{
      'material-top-stool':'__IMG:material-top-stool__','material-side-stool':'__IMG:material-side-stool__',
      'material-top-case':'__IMG:material-top-case__','material-side-case':'__IMG:material-side-case__',
      'material-top-clipboard':'__IMG:material-top-clipboard__','material-side-clipboard':'__IMG:material-side-clipboard__',
    },
  },
  levels:rounds.map(({object,...level})=>({...level,hints,photoViews:{top:view('top',object),side:view('side',object)}})),
  cues:rounds.map(({shots})=>({
    goal:'photo-goal',hint:'photo-hint',hint2:'photo-help',praise:'photo-praise',
    steps:shots.map(shot=>shot?'photo-top':'photo-side'),
  })),
  observation:{
    sceneId:'scene-material-photo-pairs',
    trials:{'same-object-two-views':{top:rounds.map(r=>view('top',r.object)),side:rounds.map(r=>view('side',r.object))}},
  },
});
K.game({...camera, bubbleAt: () => ({x:640,y:36})});
