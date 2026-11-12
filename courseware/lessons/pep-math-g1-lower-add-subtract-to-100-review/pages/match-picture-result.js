K.ready({title: '把算式配给结果', sub: '先算左边，再瞄准结果图。'});

const operationPicture = K.$('#operation-picture');
const matchedResult = K.$('#matched-result');
const operations = {
  'more-tens': '__IMG:more-tens__', 'more-ones': '__IMG:more-ones__',
  'carry-first': '__IMG:carry-first__', 'carry-next': '__IMG:carry-next__',
  'borrow-first': '__IMG:borrow-first__', 'borrow-next': '__IMG:borrow-next__'
};
const pictures = {
  39: '__IMG:value-39__', 40: '__IMG:value-40__',
  48: '__IMG:value-48__', 58: '__IMG:value-58__',
  36: '__IMG:value-36__', 46: '__IMG:value-46__',
  54: '__IMG:value-54__', 64: '__IMG:value-64__',
  43: '__IMG:value-43__', 53: '__IMG:value-53__',
  63: '__IMG:value-63__', 68: '__IMG:value-68__', 78: '__IMG:value-78__'
};
const levels = [
  {
    listenOnly: true, targetWidth: 168, targetHeight: 122, speed: 388, drift: 0,
    queue: ['more-tens', 'more-ones'],
    targets: [{x: 341, value: 48}, {x: 530, value: 58}, {x: 727, value: 39}, {x: 914, value: 40}],
    pairs: [['more-tens', 58], ['more-ones', 39]],
    hints: ['看这次加的是几个十，还是几个一。', '把原来的十束和散件分开看。']
  },
  {
    listenOnly: true, targetWidth: 168, targetHeight: 122, speed: 460, drift: 7,
    queue: ['carry-first', 'carry-next'],
    targets: [{x: 341, value: 36}, {x: 530, value: 46}, {x: 727, value: 54}, {x: 914, value: 64}],
    pairs: [['carry-first', 36], ['carry-next', 64]],
    hints: ['先把个位上的两个数加一加。', '满十就换一束，再看看还剩几个一。']
  },
  {
    listenOnly: true, targetWidth: 148, targetHeight: 118, speed: 515, drift: 10,
    queue: ['borrow-first', 'borrow-next'],
    targets: [{x: 315, value: 43}, {x: 476, value: 53}, {x: 640, value: 63},
      {x: 804, value: 68}, {x: 965, value: 78}],
    pairs: [['borrow-first', 53], ['borrow-next', 68]],
    hints: ['先看看散件够不够取。', '拆一束后，再从现在的散件里取。']
  }
];
const matcher = K.game(K.gameTemplates.magnetMarbles({
  voiceLead: true,
  doneText: '每张算式都配到了相同数量的结果图。',
  art: {
    backdrop: '__IMG:match-backdrop__',
    frames: ['__IMG:ticket__'],
    sticker: '__IMG:microphone__',
    icons: pictures
  },
  cues: [
    {goal: 'match-same-place', hint: 'match-hint', hint2: 'match-help', praise: 'match-praise'},
    {goal: 'match-carry', hint: 'match-hint', hint2: 'match-help', praise: 'match-praise'},
    {goal: 'match-borrow', hint: 'match-hint', hint2: 'match-help', praise: 'match-praise'}
  ],
  levels
}));
matcher.follow(operationPicture, game => {
  const queue = levels[game.level].queue;
  const world = game.data.w;
  const index = (world?.i ?? 0) - (world?.locked && world.delay > 0 ? 1 : 0);
  const picture = operations[queue[Math.min(index, queue.length - 1)]];
  if (operationPicture.getAttribute('src') !== picture) operationPicture.setAttribute('src', picture);
  return {x: 10, y: 154, w: 212, h: 144};
});
matcher.follow(matchedResult, game => {
  const selected = game.data.w?.locked?.value;
  matchedResult.hidden = selected === undefined;
  if (selected !== undefined && matchedResult.getAttribute('src') !== pictures[selected]) {
    matchedResult.setAttribute('src', pictures[selected]);
  }
  return {x: 16, y: 329, w: 194, h: 135};
});
matcher.follow('#result-pictures', () => ({x: 250, y: 164, w: 757, h: 131}));
