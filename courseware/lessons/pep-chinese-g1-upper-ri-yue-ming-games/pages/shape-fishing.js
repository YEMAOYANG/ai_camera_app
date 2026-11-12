K.ready({title: '字义钓鱼船', sub: '用图找字，移船对准再放钩'});

const tilted = {
  goal: {image: '__IMG:tilted-frame__', fallback: '相框斜了'},
  hint: '看看框边和窗边的方向一样吗？', hint2: '上面的不，下面的正，合起来想想。',
  success: '没有摆正，画框就是歪的。'
};
const tears = {
  goal: {image: '__IMG:tears__', fallback: '眼睛流出水'},
  hint: '仔细看，水从哪儿流出来？', hint2: '找一找三点水和目挨在一起的字。',
  success: '水和眼睛给了我们泪的线索。'
};
const sprouts = {
  goal: {image: '__IMG:seedling-bed__', fallback: '田里的小植物'},
  hint: '看看地里新长出了什么。', hint2: '找上面像草，下面像田的字。',
  success: '草字头和田，能帮我们认苗。'
};

K.game(K.gameTemplates.fishing({
  goalHeight: 128,
  levels: [
    {
      name: '两张字牌，先看清图',
      demoRounds: [{...tilted, options: ['歪', '苗'], matches: [0]}],
      rounds: [{...tears, options: ['尘', '泪'], matches: [1]}]
    },
    {
      name: '三张字牌，连钓两回',
      rounds: [
        {...sprouts, options: ['苗', '歪', '泪'], matches: [0]},
        {...tilted, options: ['尖', '歪', '苗'], matches: [1]}
      ]
    },
    {
      name: '四张字牌，看清相近部件',
      rounds: [
        {...tears, options: ['苗', '尘', '尖', '泪'], matches: [3]},
        {...sprouts, options: ['尘', '苗', '泪', '歪'], matches: [1]}
      ]
    }
  ],
  doneText: '先用部件猜，再看生活里像不像。'
}));
