const rounds = [
  {object:'bag',rate:.58,range:106,aperture:149,shots:[1,0]},
  {object:'toybox',rate:.78,range:166,aperture:120,shots:[0,1,0]},
  {object:'tray',rate:1.02,range:216,aperture:104,shots:[1,0,1,0]},
];
const view = (direction,object) => 'storage-'+direction+'-'+object;
const title = '给同一处收纳拍两面';
const hints = ['把整件收纳用品放进虚线框。','等它转到和小图一样的角度。'];
K.ready({title,sub:'看小图的角度，对准再拍。'});
const camera = K.gameTemplates.shutterScout({
  title,doneText:'三件收纳用品的两个角度都拍到了。',voiceLead:true,stepVoiceLead:true,
  art:{
    backdrop:'__IMG:storage-camera-table__',sticker:'__IMG:storage-observer-camera__',
    icons:{
      'storage-top-bag':'__IMG:storage-top-bag__','storage-side-bag':'__IMG:storage-side-bag__',
      'storage-top-toybox':'__IMG:storage-top-toybox__','storage-side-toybox':'__IMG:storage-side-toybox__',
      'storage-top-tray':'__IMG:storage-top-tray__','storage-side-tray':'__IMG:storage-side-tray__',
    },
  },
  levels:rounds.map(({object,...level})=>({...level,hints,photoViews:{top:view('top',object),side:view('side',object)}})),
  cues:rounds.map(({shots})=>({
    goal:'storage-photo-goal',hint:'storage-photo-hint',hint2:'storage-photo-help',praise:'storage-photo-praise',
    steps:shots.map(shot=>shot?'storage-photo-top':'storage-photo-side'),
  })),
  observation:{
    sceneId:'scene-photograph-neat-storage',
    trials:{'same-storage-two-views':{top:rounds.map(r=>view('top',r.object)),side:rounds.map(r=>view('side',r.object))}},
  },
});
K.game({...camera, bubbleAt: () => ({x:640,y:36})});
