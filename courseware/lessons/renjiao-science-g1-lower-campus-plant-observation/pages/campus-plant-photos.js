const levels = [
  {group:'jasmine', rate:.58, range:106, aperture:149, shots:[1,0]},
  {group:'forsythia', rate:.78, range:166, aperture:120, shots:[0,1,0]},
  {group:'willow', rate:1.02, range:216, aperture:104, shots:[1,0,1,0]},
];
const photo = (view, group) => 'plant-'+view+'-'+group;
const title = '给同一枝拍两种角度';
const hints = ['把这一根枝移进虚线框。','等枝条转到小图里的角度。'];
K.ready({title, sub:'对上小图的角度，再按快门。'});
const camera = K.gameTemplates.shutterScout({
  title, doneText:'三根枝的俯视和侧视都记录好了。', voiceLead:true, stepVoiceLead:true,
  art:{
    backdrop:'__IMG:cork-background__', sticker:'__IMG:campus-plant-camera__',
    icons:{
      'plant-top-jasmine':'__IMG:plant-top-jasmine__', 'plant-side-jasmine':'__IMG:plant-side-jasmine__',
      'plant-top-forsythia':'__IMG:plant-top-forsythia__', 'plant-side-forsythia':'__IMG:plant-side-forsythia__',
      'plant-top-willow':'__IMG:plant-top-willow__', 'plant-side-willow':'__IMG:plant-side-willow__',
    },
  },
  levels:levels.map(({group,...level})=>({...level,hints,photoViews:{top:photo('top',group),side:photo('side',group)}})),
  cues:levels.map(({shots})=>({
    goal:'plant-photo-goal', hint:'plant-photo-hint', hint2:'plant-photo-help',
    praise:'plant-photo-praise', steps:shots.map(shot=>shot?'plant-photo-top':'plant-photo-side'),
  })),
  observation:{
    sceneId:'scene-campus-plant-photos',
    trials:{'same-branch-two-views':{top:levels.map(l=>photo('top',l.group)),side:levels.map(l=>photo('side',l.group))}},
  },
});
K.game({...camera, bubbleAt: () => ({x:640,y:36})});
