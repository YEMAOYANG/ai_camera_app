K.ready({
  title: '沿笔画开雪道',
  sub: '从车头出发，按笔画的方向走，经过每一个转弯。',
  img: '__IMG:winter-yard__',
  emoji: '<img class="pic" src="__IMG:track-horse__" alt="雪地上的弯弯印记">'
});

// Routes are original diagrams of individual strokes, cross-checked against
// the print textbook page 65 and official first-period slides 26–27.
// They do not represent the stroke order of a complete character.
const verticalFold = {
  goal: '牙 · 竖折',
  strokes: [[[444, 287], [434, 463], [832, 430]]],
  hint: '先稳住车，再看下一段路往哪边。',
  hint2: '从上往下，到拐角才向右。',
  success: '先竖后折，车走到了终点！'
};
const doubleFoldHook = {
  goal: '马 · 竖折折钩',
  strokes: [[[463, 259], [449, 431], [857, 397], [821, 560], [800, 582], [758, 552]]],
  hint: '沿路慢一点，看看有几次转弯。',
  hint2: '往下、向右、再往下，最后收小钩。',
  success: '走过两次折，最后转出了钩！'
};
const horizontalFoldHook = {
  goal: '用 · 横折钩',
  strokes: [[[446, 285], [838, 258], [836, 528], [827, 568], [780, 543]]],
  hint: '先看起点朝哪边，再找角上的转弯。',
  hint2: '先向右，到角上向下，末尾向里收。',
  success: '先横再折，末尾带上小钩！'
};

K.game(K.gameTemplates.trace({
  doneText: '三个笔形走过了。拿起笔，请家人陪你照课本练一练。',
  levels: [
    {name: '一竖一折',
      demoRounds: [{...verticalFold, strokes: [[[464, 280], [451, 484], [854, 455]]]}],
      rounds: [verticalFold]},
    {name: '再走两条带钩的路', rounds: [doubleFoldHook, horizontalFoldHook]}
  ]
}));
