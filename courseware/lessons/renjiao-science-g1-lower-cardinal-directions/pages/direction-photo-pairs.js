const phases = [
  {name:'morning',rate:.58,range:106,aperture:149,shots:[1,0]},
  {name:'noon-model',rate:.78,range:166,aperture:120,shots:[0,1,0]},
  {name:'evening',rate:1.02,range:216,aperture:104,shots:[1,0,1,0]},
];
const picture = (view,phase) => 'shadow-'+view+'-'+phase;
const hints = ['先把一整张模型图放进虚线框。','等画面和上面的小图角度一样。'];
const title='拍下庭院里的日影';
K.ready({title,sub:'等到同一个角度，把模型图拍下来。'});
K.game(K.gameTemplates.shutterScout({
  title,doneText:'同一庭院模型的两种角度拍好了。',
  voiceLead:true,stepVoiceLead:true,
  art:{
    backdrop:'__IMG:photo-backdrop__',sticker:'__IMG:courtyard-camera__',
    icons:{
      'shadow-top-morning':'__IMG:shadow-top-morning__','shadow-side-morning':'__IMG:shadow-side-morning__',
      'shadow-top-noon-model':'__IMG:shadow-top-noon-model__','shadow-side-noon-model':'__IMG:shadow-side-noon-model__',
      'shadow-top-evening':'__IMG:shadow-top-evening__','shadow-side-evening':'__IMG:shadow-side-evening__',
    },
  },
  levels:phases.map(({name,...level})=>({...level,hints,photoViews:{top:picture('top',name),side:picture('side',name)}})),
  cues:phases.map(({shots})=>({
    goal:'shadow-goal',hint:'shadow-hint',hint2:'shadow-help',praise:'shadow-praise',
    steps:shots.map(s=>s?'shadow-top':'shadow-side'),
  })),
  observation:{
    sceneId:'scene-direction-photo-pairs',
    trials:{'one-model-two-views':{top:phases.map(p=>picture('top',p.name)),side:phases.map(p=>picture('side',p.name))}},
  },
}));
