K.ready({title:'礼物泡泡艇',sub:'先听清礼物，再移动小艇、吹泡泡。'});

const words = {pen:'gift-pen',pencil:'gift-pencil',ball:'gift-ball',book:'gift-book',bag:'gift-bag'};
const round = (target, ...cards) => ({target,cards});
const hints = ['重听一句。找老师说到的礼物。','亮起来的就是这件。等船对正再吹。'];
const feedback = {hint:'boat-hint',hint2:'boat-help',praise:'boat-praise'};
const rounds = [
  [round('pen','pen','pencil'),round('pencil','pen','pencil')],
  [round('pencil','ball','pencil','pen'),round('ball','pencil','pen','ball'),round('pen','pen','ball','pencil')],
  [round('book','ball','book','bag'),round('bag','bag','pen','book'),round('ball','book','bag','ball'),round('pencil','bag','pencil','pen')],
];

K.game(K.gameTemplates.wordBubbles({
  art:{
    backdrop:'__IMG:boat-backdrop__',sticker:'__IMG:birthday-sticker__',
    frames:['__IMG:boat-idle__','__IMG:boat-blow__'],
    icons:{pen:'__IMG:gift-pen__',pencil:'__IMG:gift-pencil__',ball:'__IMG:gift-ball__',book:'__IMG:gift-book__',bag:'__IMG:gift-bag__'},
  },
  voiceLead:true,stepVoiceLead:true,
  doneText:'给礼物找对泡泡啦！',
  cues:rounds.map(items=>({...feedback,goal:words[items[0].target],steps:items.map(({target})=>words[target])})),
  levels:[
    {rounds:rounds[0],drift:0,pace:.6,tolerance:62,hints},
    {rounds:rounds[1],drift:23,pace:1,tolerance:57,hints},
    {rounds:rounds[2],drift:39,pace:1.35,tolerance:50,hints},
  ],
}));
