const levels=[
  {group:'fan',rate:.58,range:106,aperture:149,shots:[1,0]},
  {group:'long',rate:.78,range:166,aperture:120,shots:[0,1,0]},
  {group:'broad',rate:1.02,range:216,aperture:104,shots:[1,0,1,0]},
];
const photo=(view,group)=>'view-'+view+'-'+group;
const hints=['把整片叶和周围的小框移到虚线框里。','等画面和上面的小图是同一个角度。'];
const title='给同一片叶拍两个角度';
K.ready({title,sub:'从上面和侧面各看一次，再按快门。'});
K.game(K.gameTemplates.shutterScout({
  title,doneText:'同一片叶从上面和侧面都拍到了。',
  voiceLead:true,stepVoiceLead:true,
  art:{
    backdrop:'__IMG:observe-backdrop__',sticker:'__IMG:leaf-camera__',
    icons:{
      'view-top-fan':'__IMG:view-top-fan__','view-side-fan':'__IMG:view-side-fan__',
      'view-top-long':'__IMG:view-top-long__','view-side-long':'__IMG:view-side-long__',
      'view-top-broad':'__IMG:view-top-broad__','view-side-broad':'__IMG:view-side-broad__',
    },
  },
  levels:levels.map(({group,...l})=>({...l,hints,photoViews:{top:photo('top',group),side:photo('side',group)}})),
  cues:levels.map(({shots})=>({goal:'leaf-photo-goal',hint:'leaf-photo-hint',hint2:'leaf-photo-help',
    praise:'leaf-photo-praise',steps:shots.map(s=>s?'leaf-photo-top':'leaf-photo-side')})),
  observation:{
    sceneId:'scene-paired-leaf-observations',
    trials:{'same-leaf-two-views':{top:levels.map(l=>photo('top',l.group)),side:levels.map(l=>photo('side',l.group))}},
  },
}));
