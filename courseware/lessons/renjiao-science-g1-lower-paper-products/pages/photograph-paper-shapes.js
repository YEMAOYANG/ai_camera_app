const rounds = [
  {paper:'kraft',rate:.58,range:106,aperture:149,shots:[1,0]},
  {paper:'news',rate:.78,range:166,aperture:120,shots:[0,1,0]},
  {paper:'print',rate:1.02,range:216,aperture:104,shots:[1,0,1,0]},
];
const view = (direction,paper) => 'paper-'+direction+'-'+paper;
const title = '给同一张纸拍两个角度';
const hints = ['把整张纸放进虚线框。','再等等，让纸转到小图里的方向。'];
K.ready({title,sub:'看小图的角度，再对准取景。'});
const camera = K.gameTemplates.shutterScout({
  title,doneText:'三张纸揉过后的两种样子都拍到了。',voiceLead:true,stepVoiceLead:true,
  art:{
    backdrop:'__IMG:paper-camera-table__',sticker:'__IMG:paper-observer-camera__',
    icons:{
      'paper-top-kraft':'__IMG:paper-top-kraft__','paper-side-kraft':'__IMG:paper-side-kraft__',
      'paper-top-news':'__IMG:paper-top-news__','paper-side-news':'__IMG:paper-side-news__',
      'paper-top-print':'__IMG:paper-top-print__','paper-side-print':'__IMG:paper-side-print__',
    },
  },
  levels:rounds.map(({paper,...level})=>({...level,hints,photoViews:{top:view('top',paper),side:view('side',paper)}})),
  cues:rounds.map(({shots})=>({
    goal:'paper-photo-goal',hint:'paper-photo-hint',hint2:'paper-photo-help',praise:'paper-photo-praise',
    steps:shots.map(shot=>shot?'paper-photo-top':'paper-photo-side'),
  })),
  observation:{
    sceneId:'scene-photograph-paper-shapes',
    trials:{'same-paper-two-views':{top:rounds.map(r=>view('top',r.paper)),side:rounds.map(r=>view('side',r.paper))}},
  },
});
K.game({...camera, bubbleAt: () => ({x:640,y:36})});
