const round = (target, ...cards) => ({target,cards});
const rounds = [
  [round('search','search','drink'),round('stone','search','stone')],
  [round('drop','take','drop','stone'),round('take','drop','stone','take'),round('stone','stone','search','drop')],
  [round('high','low','high','stone'),round('low','high','search','low'),round('drop','drop','take','drink')],
];
const speeds = [[0,.6,62],[21,.95,57],[36,1.23,52]];
const hints = ['重听一遍，再看看动作或水线。','对准亮起来的图，再按泡泡键。'];
const feedback = {hint:'crow-words-hint',hint2:'crow-words-help',praise:'crow-words-praise'};
const levels = rounds.map((items,index) => {
  const [drift,pace,tolerance] = speeds[index];
  return {rounds:items,drift,pace,tolerance,hints};
});
const cues = rounds.map(items => ({
  ...feedback,goal:'crow-word-'+items[0].target,steps:items.map(({target})=>'crow-word-'+target),
}));

const title = '词语泡泡船';
K.ready({title,sub:'听词看图，开船对准图卡，再吹泡泡。'});
K.game(K.gameTemplates.wordBubbles({
  art:{
    backdrop:'__IMG:channel-backdrop__',sticker:'__IMG:film-sticker__',
    frames:['__IMG:boat-right-idle__','__IMG:boat-right-blow__'],
    icons:{
      search:'__IMG:story-search__',drink:'__IMG:story-drink__',stone:'__IMG:stone-one__',
      drop:'__IMG:story-drop__',take:'__IMG:story-take__',high:'__IMG:vessel-high__',low:'__IMG:vessel-low__',
    },
  },
  title,levels,cues,voiceLead:true,stepVoiceLead:true,doneText:'词语和画面配上啦！',
}));
