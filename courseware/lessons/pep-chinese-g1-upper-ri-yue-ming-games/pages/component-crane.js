K.ready({title: '部件吊车', sub: '看准部件，等吊臂对准字车'});

const demo = {
  goal: '日', cargo: '日', cars: ['明', '男'], drop: [0],
  hint: '先看方框里面是哪几笔。', hint2: '日的框里只有一道横。',
  success: '左日右月，日送对地方了。'
};

K.game(K.gameTemplates.crane({
  levels: [
    {
      name: '两辆车，送对一辆',
      demoRounds: [demo],
      rounds: [{
        goal: '土', cargo: '土', cars: ['尖', '尘'], drop: [1],
        hint: '两个字上面很像，换个地方看。', hint2: '到字的下半边找土。',
        success: '小在上，土在下。'
      }]
    },
    {
      name: '三辆车，换两种部件',
      rounds: [{
        goal: '力', cargo: '力', cars: ['众', '男', '尘'], drop: [1],
        hint: '看看哪辆字车藏着这个部件。', hint2: '到上下结构的字里找。',
        success: '上田下力，送到男字车。'
      }, {
        goal: '月', cargo: '月', cars: ['明', '林', '男'], drop: [0],
        hint: '看看字车的左右两边。', hint2: '认一认月里面的两小横。',
        success: '明的右边是月。'
      }]
    },
    {
      name: '四辆车，同部件送两处',
      rounds: [{
        goal: '木', cargo: '木', cars: ['林', '双', '森', '尘'], drop: [0, 2],
        hint: '送完一辆，还要再找一辆。', hint2: '找两个木并排和三个木相叠的样子。',
        success: '林和森都能找到木。'
      }, {
        goal: '人', cargo: '人', cars: ['林', '众', '从', '森'], drop: [1, 2],
        hint: '小部件有时会挨在一起，有时会上下放。', hint2: '找两个和三个像人的部件。',
        success: '从和众都能找到人。'
      }]
    }
  ],
  doneText: '能找到部件，也看清它的位置。'
}));
