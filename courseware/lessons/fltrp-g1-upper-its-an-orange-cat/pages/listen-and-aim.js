K.ready({title: '听清再发射', sub: '听颜色和物名，再瞄准那件展品。'});

const displayItems = {
  'blue-pencil': '__IMG:blue-pencil__',
  'red-pencil': '__IMG:red-pencil__',
  'blue-book': '__IMG:blue-book__',
  'yellow-cat': '__IMG:yellow-cat__',
  'black-cat': '__IMG:black-cat__',
  'black-bird': '__IMG:black-bird__',
  'yellow-bird': '__IMG:yellow-bird__',
  'red-book': '__IMG:red-book__',
  'red-ball': '__IMG:red-ball__',
  'green-book': '__IMG:green-book__',
  'green-ball': '__IMG:green-ball__',
};

function round(queue, values, positions, speed, drift, targetWidth) {
  return {
    queue,
    targets: values.map((value, i) => ({value, x: positions[i]})),
    pairs: queue.map(value => [value, value]),
    speed, drift, targetWidth, targetHeight: 112, listenOnly: true,
    hints: ['先重听颜色，再听物名。', '让瞄准线朝着亮起来的图片。'],
  };
}

K.game(K.gameTemplates.magnetMarbles({
  art: {
    backdrop: '__IMG:display-backdrop__',
    sticker: '__IMG:gallery-sticker__',
    frames: ['__IMG:amber-marble__'],
    icons: displayItems,
  },
  doneText: '展品都摆好啦！',
  voiceLead: true,
  stepVoiceLead: true,
  cues: [
    {steps: ['blue-pencil', 'blue-book'], hint: 'aim-hint', hint2: 'aim-help', praise: 'aim-praise'},
    {steps: ['black-bird', 'yellow-cat', 'black-cat'], hint: 'aim-hint', hint2: 'aim-help', praise: 'aim-praise'},
    {steps: ['green-ball', 'red-book', 'green-book'], hint: 'aim-hint', hint2: 'aim-help', praise: 'aim-praise'},
  ],
  levels: [
    round(['blue-pencil', 'blue-book'], ['blue-pencil', 'red-pencil', 'blue-book'], [410, 640, 870], 355, 0, 168),
    round(['black-bird', 'yellow-cat', 'black-cat'], ['yellow-cat', 'black-cat', 'black-bird', 'yellow-bird'], [350, 545, 735, 930], 400, 7, 154),
    round(['green-ball', 'red-book', 'green-book'], ['red-book', 'red-ball', 'green-book', 'green-ball'], [350, 545, 735, 930], 445, 14, 152),
  ],
}));
