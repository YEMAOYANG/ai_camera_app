K.ready({
  title: '雪圈套进形状展',
  sub: '沿着雪印看一圈，瞄准像它的画，再送出雪圈。',
  img: '__IMG:winter-yard__',
  emoji: '<img class="pic" src="__IMG:crescent__" alt="一弯月牙形的画">'
});

const prints = {
  chick: {image: '__IMG:track-chick__', fallback: '细尖的雪印'},
  dog: {image: '__IMG:track-dog__', fallback: '圆圆的雪印'},
  duck: {image: '__IMG:track-duck__', fallback: '宽扇的雪印'},
  horse: {image: '__IMG:track-horse__', fallback: '弯弧的雪印'}
};
const pictures = {
  chick: {image: '__IMG:bamboo-leaf__', fallback: '竹叶'},
  dog: {image: '__IMG:plum-blossom__', fallback: '梅花'},
  duck: {image: '__IMG:maple-leaf__', fallback: '枫叶'},
  horse: {image: '__IMG:crescent__', fallback: '月牙'}
};
const clues = {
  chick: ['看雪印外边，尖尖的地方往哪边伸？', '找细细的尖，不找宽宽的一大片。', '细尖的竹叶和细细的印子很像！'],
  dog: ['沿着雪印的外边看一圈。', '看哪幅画像一圈小圆瓣围在中间。', '一圈圆圆的小印让人想到梅花！'],
  duck: ['再比比外边，窄窄的还是宽宽的？', '找像扇子那样往两边展开的画。', '雪印和枫叶都宽宽地张开！'],
  horse: ['先看整条边，再看看两头。', '找一条长弧，两头收得尖一点。', '弯弯的蹄印让人想到月牙！']
};

function ringRound(print, order) {
  const [hint, hint2, success] = clues[print];
  return {goal: prints[print], targets: order.map(key => pictures[key]), rings: 1,
    matches: [order.indexOf(print)], hint, hint2, success};
}

K.game(K.gameTemplates.ring({
  doneText: '先看雪印的外边，再想像什么，形状展布置好了。',
  levels: [
    {name: '先比两种轮廓',
      demoRounds: [ringRound('horse', ['chick', 'horse'])],
      rounds: [ringRound('chick', ['dog', 'chick']), ringRound('dog', ['dog', 'horse'])]},
    {name: '从四张画里找',
      rounds: [ringRound('duck', ['chick', 'horse', 'duck', 'dog']),
        ringRound('horse', ['dog', 'duck', 'chick', 'horse']),
        ringRound('chick', ['chick', 'duck', 'horse', 'dog'])]
    }
  ]
}));
