K.ready({title:'工具相机找线索',sub:'把工具移进框里，等它和小图一样，再拍。'});
K.$('#ready .card').prepend(K.$('#tool-camera-opening').content.cloneNode(true));

const hints = ['先把工具跟在取景框里。','看上面的小图，等它转到那个方向再拍。'];
const cue = {goal:'camera-goal',hint:'camera-hint',hint2:'camera-help',praise:'camera-praise'};

K.game(K.gameTemplates.shutterScout({
  art:{
    sticker:'__IMG:stencil-top__',
    icons:{
      'stencil-top':'__IMG:stencil-top__','stencil-side':'__IMG:stencil-side__',
      'tongs-top':'__IMG:tongs-top__','tongs-side':'__IMG:tongs-side__',
      'driver-top':'__IMG:driver-top__','driver-side':'__IMG:driver-side__',
    },
  },
  observation:{sceneId:'scene-tool-camera',trials:{'tool-pair':{
    top:['stencil-top','tongs-top','driver-top'],side:['stencil-side','tongs-side','driver-side'],
  }}},
  voiceLead:true,stepVoiceLead:true,
  cues:[
    {...cue,steps:['camera-top','camera-side']},
    {...cue,steps:['camera-side','camera-top','camera-side']},
    {...cue,steps:['camera-top','camera-side','camera-top','camera-side']},
  ],
  doneText:'同一件工具的两个方向都拍下来啦！',
  levels:[
    {rate:.58,range:106,aperture:150,shots:[1,0],hints,photoViews:{top:'stencil-top',side:'stencil-side'}},
    {rate:.79,range:162,aperture:126,shots:[0,1,0],hints,photoViews:{top:'tongs-top',side:'tongs-side'}},
    {rate:1.02,range:222,aperture:106,shots:[1,0,1,0],hints,photoViews:{top:'driver-top',side:'driver-side'}},
  ],
}));

const setTeacherState = K.onState;
K.onState = (state, content) => {
  setTeacherState(state, content);
  if (state.demo === false) {
    for (const anchor of K.$$('.teach-hl')) anchor.classList.remove('teach-hl');
  } else if (state.pause === false) {
    K.$('#camera-demo-view').classList.remove('teach-hl');
  }
};
