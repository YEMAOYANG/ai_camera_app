K.ready({title: '文具空投', sub: '想想图里需要什么，移动篮子来接'});

const ruler = {image: '__IMG:ruler__', fallback: '尺子'};
const eraser = {image: '__IMG:eraser__', fallback: '橡皮'};
const pouch = {image: '__IMG:pencilcase__', fallback: '笔袋'};

const needsLine = {
  goal: {image: '__IMG:task-line__', fallback: '连直线'},
  hint: '两个点要连起来，线得是直的。',
  hint2: '找一找，哪件东西有长长的直边？',
  success: '有了直边，铅笔就能画直线。'
};
const needsErase = {
  goal: {image: '__IMG:task-erase__', fallback: '去掉笔迹'},
  hint: '想想怎样让纸面重新空出来。',
  hint2: '哪件东西一擦，铅笔痕就会变淡？',
  success: '擦掉笔迹，就有地方重新写了。'
};
const needsPacking = {
  goal: {image: '__IMG:task-pens__', fallback: '收好散笔'},
  hint: '笔容易滚，想想怎么把它们一起带走。',
  hint2: '找一个有开口，能装好几支笔的用品。',
  success: '几支笔可以装在一起带走。'
};

K.game(K.gameTemplates.parachute({
  goalHeight: 128,
  levels: [
    {
      name: '两把伞，接对一件',
      demoRounds: [{...needsLine, options: [eraser, ruler], answer: 1}],
      rounds: [{...needsErase, options: [eraser, pouch], answer: 0}]
    },
    {
      name: '三把伞，换两项任务',
      rounds: [
        {...needsPacking, options: [ruler, eraser, pouch], answer: 2},
        {...needsLine, options: [ruler, pouch, eraser], answer: 0}
      ]
    },
    {
      name: '伞落得快，接连送对三件',
      rounds: [
        {...needsErase, options: [ruler, pouch, eraser], answer: 2},
        {...needsLine, options: [eraser, ruler, pouch], answer: 1},
        {...needsPacking, options: [pouch, eraser, ruler], answer: 0}
      ]
    }
  ],
  doneText: '看清要做的事，就能找对文具。'
}));
