K.ready({
  title: '雪球滑车找印记',
  sub: '看小画家的脚，开滑车碰一碰它留下的印记。',
  img: '__IMG:winter-yard__',
  emoji: '<img class="pic" src="__IMG:track-chick__" alt="雪地上的细脚印">'
});

const animals = {
  chick: {image: '__IMG:chick__', fallback: '小鸡'},
  dog: {image: '__IMG:dog__', fallback: '小狗'},
  duck: {image: '__IMG:duck__', fallback: '小鸭'},
  horse: {image: '__IMG:horse__', fallback: '小马'}
};
const tracks = {
  chick: {image: '__IMG:track-chick__', fallback: '细尖'},
  dog: {image: '__IMG:track-dog__', fallback: '圆印'},
  duck: {image: '__IMG:track-duck__', fallback: '宽扇'},
  horse: {image: '__IMG:track-horse__', fallback: '弯弧'}
};
const clues = {
  chick: ['再看看小脚，脚趾是尖还是圆？', '找向外分开的几条细线。', '细脚趾留下细细的印！'],
  dog: ['回看小脚，想想脚底是什么形状。', '找围着一个大印的小圆印。', '圆圆的脚垫留下圆印！'],
  duck: ['看看两只脚，脚趾之间是分开还是连着？', '找外边宽宽张开的印子。', '脚趾连着，雪印像张开的小扇！'],
  horse: ['小马用哪里碰雪？先看蹄子。', '找一条没有小圆点的弯弧。', '课文里的蹄印像月牙！']
};

function bumperRound(animal, order) {
  const [hint, hint2, success] = clues[animal];
  return {goal: animals[animal], options: order.map(key => tracks[key]),
    answer: order.indexOf(animal), hint, hint2, success};
}

K.game(K.gameTemplates.bumper({
  doneText: '看清小脚的形状，雪地里的四种印子就能分开。',
  levels: [
    {name: '看细尖和圆印',
      demoRounds: [bumperRound('chick', ['dog', 'chick'])],
      rounds: [bumperRound('dog', ['chick', 'dog']), bumperRound('chick', ['chick', 'dog'])]},
    {name: '四种印记一起找',
      rounds: [bumperRound('duck', ['chick', 'dog', 'horse', 'duck']),
        bumperRound('horse', ['horse', 'duck', 'chick', 'dog']),
        bumperRound('dog', ['duck', 'dog', 'horse', 'chick'])]
    }
  ]
}));
