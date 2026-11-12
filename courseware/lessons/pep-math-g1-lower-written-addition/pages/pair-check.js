const pictures = {
  'p14-21': '__IMG:p14-21__', 'p23-44': '__IMG:p23-44__',
  'p27-16': '__IMG:p27-16__', 'p29-34': '__IMG:p29-34__',
  'p46-14': '__IMG:p46-14__', 'p9-53': '__IMG:p9-53__'
};
const results = {
  '35':'__IMG:result-35__', '67':'__IMG:result-67__', '37':'__IMG:result-37__',
  '43':'__IMG:result-43__', '63':'__IMG:result-63__', '53':'__IMG:result-53__',
  '60':'__IMG:result-60__', '62':'__IMG:result-62__', '50':'__IMG:result-50__'
};

function level(queue, totals, pairs, speed, drift) {
  return {
    queue,
    targets: totals.map((value, index) => ({x:[369,640,911][index],value})),
    pairs, speed, drift, targetWidth:188, targetHeight:110, listenOnly:true,
    hints: ['先分开数整条和散枚。', '散枚满十时，先换成一条，再重数。']
  };
}

const config = {
  title: '弹珠找总量',
  sub: '看左边两组徽章，瞄准对应的总量图。',
  doneText: '每张记录都找到了对应的总量图。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop:'__IMG:workshop-floor__',
    frames:['__IMG:apron-marble__'],
    sticker:'__IMG:badge-sticker__',
    icons: results
  },
  levels: [
    level(['p14-21','p23-44'], ['37','35','67'], [['p14-21','35'],['p23-44','67']], 385, 0),
    level(['p27-16','p29-34'], ['43','53','63'], [['p27-16','43'],['p29-34','63']], 465, 9),
    level(['p46-14','p9-53'], ['62','50','60'], [['p46-14','60'],['p9-53','62']], 555, 18)
  ],
  cues: [
    {goal:'match-goal',steps:['match-goal','match-next'],hint:'match-hint',hint2:'match-help',praise:'match-praise'},
    {goal:'match-carry',steps:['match-carry','match-next'],hint:'match-hint',hint2:'match-help',praise:'match-praise'},
    {goal:'match-zero',steps:['match-zero','match-single'],hint:'match-hint',hint2:'match-help',praise:'match-praise'}
  ]
};

K.ready({title:config.title,sub:config.sub,img:'__IMG:workshop-cover__'});
K.stage().append(K.$('#marble-badge-card'),K.$('#marble-first-target'));
const picture = K.$('#marble-badge-picture');
const activity = K.gameTemplates.magnetMarbles(config);
activity.onState = (_, state) => {
  if (state.demo === false) {
    K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
  }
};
K.game(activity);

function showProblem() {
  const game = K.game.current;
  const visible = game.state === 'play' || (game.auto && game.state === 'between');
  const queue = config.levels[game.level].queue;
  const index = game.auto && game.state === 'between' ? 0 : Math.min(game.data.w?.i ?? 0, queue.length - 1);
  const image = pictures[queue[index]];
  if (picture.getAttribute('src') !== image) picture.src = image;
  picture.hidden = !visible;
  requestAnimationFrame(showProblem);
}
requestAnimationFrame(showProblem);
