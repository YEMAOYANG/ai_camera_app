const config = {
  title: '听清用途，开车去送',
  sub: '先拿合用的物品，过车道，再送给等它的人。',
  doneText: '合用的东西送到手了。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:delivery-backdrop__',
    sticker: '__IMG:radio-sticker__',
    frames: ['__IMG:delivery-rover__', '__IMG:delivery-rover-load__', '__IMG:lane-van__'],
    icons: {
      comb: '__IMG:item-comb__', towel: '__IMG:item-towel__', brush: '__IMG:item-brush__',
      basin: '__IMG:item-basin__', soap: '__IMG:item-soap__',
      hair: '__IMG:recipient-hair__', hands: '__IMG:recipient-hands__', mouth: '__IMG:recipient-mouth__',
      face: '__IMG:recipient-face__', bath: '__IMG:recipient-bath__'
    }
  },
  levels: [
    {
      pickup: [['comb', 2], ['towel', 6]], drop: [['hair', 3], ['hands', 6]],
      orders: [['comb', 'hair']],
      lanes: [{row: 2, speed: .8, spacing: 5.8, phase: .8}], step: .34
    },
    {
      pickup: [['basin', 2], ['brush', 6], ['towel', 8]],
      drop: [['mouth', 1], ['face', 5], ['hands', 7]],
      orders: [['brush', 'mouth'], ['basin', 'face']],
      lanes: [{row: 1, speed: -.98, spacing: 5.4, phase: 1.2}, {row: 3, speed: 1.05, spacing: 5.6, phase: .6}],
      step: .30
    },
    {
      pickup: [['soap', 1], ['towel', 3], ['comb', 6], ['basin', 8]],
      drop: [['face', 0], ['hands', 2], ['bath', 4], ['hair', 7]],
      orders: [['towel', 'hands'], ['soap', 'bath'], ['comb', 'hair']],
      lanes: [{row: 1, speed: -1.18, spacing: 5.1, phase: .8}, {row: 3, speed: 1.14, spacing: 5.2, phase: 1.7}],
      step: .27
    }
  ].map(level => ({...level, hints: ['先重听，再看看要哪样东西。', '等车开过，再去发亮的位置。']})),
  cues: [
    ['get-comb', 'to-hair'],
    ['get-brush', 'to-mouth', 'get-basin', 'to-face'],
    ['get-towel', 'to-hands', 'get-soap', 'to-bath', 'get-comb', 'to-hair']
  ].map(steps => ({steps, goal: steps[0], hint: 'delivery-hint', hint2: 'delivery-help', praise: 'delivery-praise'}))
};

K.ready({title: config.title, sub: config.sub});
K.stage().append(K.$('#garden-seven-first-comb'), K.$('#garden-seven-first-hair'));
const activity = K.gameTemplates.listenDelivery(config);
activity.onState = (_, state) => {
  if (state.demo === false) K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
};
K.game(activity);
