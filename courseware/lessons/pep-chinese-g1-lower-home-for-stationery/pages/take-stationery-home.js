const config = {
  title: '听令送文具回家',
  sub: '听要拿的东西，开去拿，再送到文具盒。',
  doneText: '三样文具都回家了。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:delivery-backdrop__',
    sticker: '__IMG:stationery-sticker__',
    frames: ['__IMG:delivery-rover__', '__IMG:delivery-rover-load__'],
    icons: {
      pencil: '__IMG:pencil__', eraser: '__IMG:eraser__', sharpener: '__IMG:sharpener__',
      case: '__IMG:case__', cubby: '__IMG:cubby__', palette: '__IMG:palette__'
    }
  },
  levels: [
    {
      pickup: [['pencil', 2], ['eraser', 6]], drop: [['case', 3], ['cubby', 6]],
      orders: [['pencil', 'case']],
      lanes: [{row: 2, speed: .83, spacing: 5.8, phase: .8}],
      step: .34, hints: ['先听清要拿什么。', '可以去发亮的站点。']
    },
    {
      pickup: [['eraser', 2], ['pencil', 6], ['sharpener', 8]],
      drop: [['cubby', 1], ['case', 5], ['palette', 7]],
      orders: [['eraser', 'case'], ['pencil', 'case']],
      lanes: [{row: 1, speed: -.99, spacing: 5.2, phase: 1.2}, {row: 3, speed: 1.06, spacing: 5.6, phase: .6}],
      step: .30, hints: ['看清拿到的物品，再找它的家。', '亮的是该去的地方，先让车道空出来。']
    },
    {
      pickup: [['sharpener', 1], ['pencil', 3], ['eraser', 6]],
      drop: [['cubby', 2], ['palette', 4], ['case', 6]],
      orders: [['pencil', 'case'], ['eraser', 'case'], ['sharpener', 'case']],
      lanes: [{row: 1, speed: -1.32, spacing: 4.9, phase: .8}, {row: 3, speed: 1.21, spacing: 5, phase: 1.7}],
      step: .27, hints: ['在中间停一停，重听这一单。', '等车道空一些，再开去亮起的格。']
    }
  ],
  cues: [
    ['deliver-pencil', 'deliver-box'],
    ['deliver-eraser', 'deliver-box', 'deliver-pencil', 'deliver-box'],
    ['deliver-pencil', 'deliver-box', 'deliver-eraser', 'deliver-box', 'deliver-sharpener', 'deliver-box']
  ].map(steps => ({steps, goal: steps[0], hint: 'deliver-hint', hint2: 'deliver-help', praise: 'deliver-praise'}))
};

K.ready({title: config.title, sub: config.sub});
K.stage().append(K.$('#station-first-pencil'), K.$('#station-first-box'));
const activity = K.gameTemplates.listenDelivery(config);
activity.onState = (_, state) => {
  if (state.demo === false) K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
};
K.game(activity);
