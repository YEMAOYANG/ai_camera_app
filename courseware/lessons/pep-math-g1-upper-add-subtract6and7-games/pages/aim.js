K.ready({
  title: '弹弓熄灯',
  sub: '看要灭哪一组灯，拉开弹弓瞄准，再松手。',
  img: '__IMG:studio__'
});

const orange = '#e57b37';
const blue = '#228caa';

function round(lamps, remove, success) {
  const matches = lamps.flatMap((color, index) => color === remove ? [index] : []);
  return {
    goal: {count: matches.length, color: remove},
    lamps: lamps.map(color => ({count: 1, color})),
    matches,
    hint: '对比上方圆点和灯的颜色，只熄灭指定的一组。',
    hint2: '瞄准同色灯的中心。另一组灯要保持亮着。',
    success
  };
}

K.game(K.gameTemplates.slingshot({
  doneText: '从所有亮灯里熄灭一部分，没熄灭的就是剩下的。',
  levels: [
    {
      name: '从七盏灯里拿走一组',
      demoRounds: [
        round([orange, orange, orange, blue, blue, blue, blue], orange, '七减三等于四，留下四盏蓝灯。')
      ],
      rounds: [
        round([blue, blue, blue, blue, orange, orange, orange], blue, '七减四等于三，留下三盏橙灯。')
      ]
    },
    {
      name: '从六盏灯里分辨两组',
      rounds: [
        round([orange, blue, blue, orange, blue, blue], orange, '六减二等于四，留下四盏蓝灯。'),
        round([blue, orange, orange, blue, orange, orange], orange, '六减四等于二，留下两盏蓝灯。')
      ]
    }
  ]
}));
