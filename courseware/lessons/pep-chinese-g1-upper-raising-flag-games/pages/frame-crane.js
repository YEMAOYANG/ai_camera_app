K.ready({title: '国字框运输站', sub: '等吊车对准，再放下框牌'});

const frame = {
  goal: '囗', cargo: '囗',
  hint: '沿四边看，里面的部分有没有穿出来？',
  hint2: '小口在一侧，跟从四面围住不一样。'
};

K.game(K.gameTemplates.crane({
  levels: [
    {
      name: '看看四边里面',
      demoRounds: [{...frame, cars: ['国', '中'], drop: [0], success: '玉留在四边里面。'}],
      rounds: [{...frame, cars: ['叶', '国'], drop: [1], success: '叶的口只在左边。'}]
    },
    {
      name: '看准两个新位置',
      rounds: [
        {...frame, cars: ['中', '回', '向'], drop: [1], success: '回的里面有个小口。'},
        {...frame, cars: ['国', '叶', '问'], drop: [0], engine: 'right',
          success: '国的外面四边合起来。'}
      ]
    },
    {
      name: '这一趟送两辆',
      rounds: [
        {...frame, cars: ['中', '回', '叶', '国'], drop: [1, 3],
          success: '国和回的外面都是国字框。'},
        {...frame, cars: ['国', '问', '回', '向'], drop: [0, 2], engine: 'right',
          success: '换了位置，还是看四边围住什么。'}
      ]
    }
  ],
  doneText: '四边围住里面，找到国字框。'
}));
