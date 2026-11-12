const levels=[
  {room:'reading',rate:.58,range:106,aperture:149,shots:[1,0]},
  {room:'music',rate:.78,range:166,aperture:120,shots:[0,1,0]},
  {room:'studio',rate:1.02,range:216,aperture:104,shots:[1,0,1,0]},
];
const topView=room=>'checkpoint-top-'+room;
const side=room=>'checkpoint-front-'+room;
const hints=['先把完整的门口画面移进框。','等画面和上面的小图一样，再拍。'];
const title='在同一扇门前拍两张照';
K.ready({title,sub:'先对上小图的角度，再按快门。'});
K.game(K.gameTemplates.shutterScout({
  title,doneText:'同一扇门的两种看法都拍到了。',
  voiceLead:true,stepVoiceLead:true,
  art:{
    backdrop:'__IMG:camera-background__',sticker:'__IMG:campus-camera__',
    icons:{
      'checkpoint-top-reading':'__IMG:checkpoint-top-reading__','checkpoint-front-reading':'__IMG:checkpoint-front-reading__',
      'checkpoint-top-music':'__IMG:checkpoint-top-music__','checkpoint-front-music':'__IMG:checkpoint-front-music__',
      'checkpoint-top-studio':'__IMG:checkpoint-top-studio__','checkpoint-front-studio':'__IMG:checkpoint-front-studio__',
    },
  },
  levels:levels.map(({room,...l})=>({...l,hints,photoViews:{top:topView(room),side:side(room)}})),
  cues:levels.map(({shots})=>({
    goal:'door-goal',hint:'door-hint',hint2:'door-help',praise:'door-praise',
    steps:shots.map(s=>s?'door-top':'door-front'),
  })),
  observation:{
    sceneId:'scene-verify-the-door',
    trials:{'one-door-two-views':{top:levels.map(l=>topView(l.room)),side:levels.map(l=>side(l.room))}},
  },
}));
