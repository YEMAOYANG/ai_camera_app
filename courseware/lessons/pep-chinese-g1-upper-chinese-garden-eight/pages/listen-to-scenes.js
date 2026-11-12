K.ready({title:'小艇用泡泡接图',sub:'听清线索，移小艇到图下，再吹泡泡。'});
const opening = K.$('#ready .pic');
opening.style.objectFit = 'contain';
opening.addEventListener('error', () => { opening.src = '__IMG:fruit-peel__'; }, {once:true});

const hints = ['先重听。看看画的东西和声音合不合。','等那张图漂到小艇上方，再按一下。'];
const feedback = {goal:'bubbles-goal',hint:'bubbles-hint',hint2:'bubbles-help',praise:'bubbles-praise'};

K.game(K.gameTemplates.wordBubbles({
  art:{
    backdrop:'__IMG:exhibit-counter__',sticker:'__IMG:ripple-sticker__',
    frames:['__IMG:boat-rest__','__IMG:boat-blow__'],
    icons:{
      fruit:'__IMG:fruit-peel__',bark:'__IMG:tree-bark__',returning:'__IMG:return-to-door__',
      answering:'__IMG:answer-teacher__',many:'__IMG:many-lanterns__',stop:'__IMG:stop-at-rope__',
      leaves:'__IMG:game-autumn-gust__',flowers:'__IMG:spring-blossoms__',
      waves:'__IMG:game-river-waves__',bamboo:'__IMG:game-bamboo-gust__',
    },
  },
  voiceLead:true,
  stepVoiceLead:true,
  doneText:'听到的词和画面都接住啦！',
  cues:[
    {...feedback,steps:['peel','bark']},
    {...feedback,steps:['come-back','answer','many']},
    {...feedback,steps:['leaves','waves','bamboo','flowers']},
  ],
  levels:[
    {drift:10,pace:.51,tolerance:62,hints,
      rounds:[{target:'fruit',cards:['bark','fruit']},{target:'bark',cards:['bark','fruit']}]},
    {drift:32,pace:.95,tolerance:55,hints,
      rounds:[{target:'returning',cards:['answering','many','returning']},
              {target:'answering',cards:['answering','returning','stop']},
              {target:'many',cards:['fruit','many','stop']}]},
    {drift:49,pace:1.46,tolerance:47,hints,
      rounds:[{target:'leaves',cards:['leaves','flowers','bamboo']},
              {target:'waves',cards:['bamboo','waves','leaves']},
              {target:'bamboo',cards:['flowers','waves','bamboo']},
              {target:'flowers',cards:['waves','flowers','leaves']}]},
  ],
}));

K.$('[data-arc-input=action]').id = 'demo-bubble-control';
K.$('.arc-voice').id = 'demo-bubble-replay';

const setTeacherState = K.onState;
K.onState = (state, content) => {
  setTeacherState(state, content);
  if (state.pause === false || state.demo === false) {
    for (const anchor of K.$$('.teach-hl')) anchor.classList.remove('teach-hl');
  }
};
