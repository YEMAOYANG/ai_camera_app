const levels=[
  {group:'trumpet',rate:.58,range:106,aperture:149,shots:[1,0]},
  {group:'cross',rate:.78,range:166,aperture:120,shots:[0,1,0]},
  {group:'peach',rate:1.02,range:216,aperture:104,shots:[1,0,1,0]},
];
const photo=(view,group)=>'flower-'+view+'-'+group;
const hints=['把整朵花的画面移进虚线框。','等画面和上面的小图是同一个角度。'];
const title='给同一朵花拍两张照';
K.ready({title,sub:'对上小图的角度，再拍一张。'});
K.game(K.gameTemplates.shutterScout({
  title,doneText:'同一朵花从上面和侧面都拍到了。',
  voiceLead:true,stepVoiceLead:true,
  art:{
    backdrop:'__IMG:photo-backdrop__',sticker:'__IMG:flower-camera__',
    icons:{
      'flower-top-trumpet':'__IMG:flower-top-trumpet__','flower-side-trumpet':'__IMG:flower-side-trumpet__',
      'flower-top-cross':'__IMG:flower-top-cross__','flower-side-cross':'__IMG:flower-side-cross__',
      'flower-top-peach':'__IMG:flower-top-peach__','flower-side-peach':'__IMG:flower-side-peach__',
    },
  },
  levels:levels.map(({group,...l})=>({...l,hints,photoViews:{top:photo('top',group),side:photo('side',group)}})),
  cues:levels.map(({shots})=>({goal:'flower-photo-goal',hint:'flower-photo-hint',hint2:'flower-photo-help',
    praise:'flower-photo-praise',steps:shots.map(s=>s?'flower-photo-top':'flower-photo-side')})),
  observation:{
    sceneId:'scene-flower-photo-pairs',
    trials:{'same-flower-two-views':{top:levels.map(l=>photo('top',l.group)),side:levels.map(l=>photo('side',l.group))}},
  },
}));
