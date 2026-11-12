K.ready({title:'接住风筝卡', sub:'按住画面移动接物台，接住真正的风筝卡', emoji:'风筝展'});
(() => {
  // The builder resolves registered image tokens from literal source.
  const cards = {
    kite: {image:'__IMG:kite__', fallback:'kite'},
    catKite: {image:'__IMG:cat-kite__', fallback:'cat kite'},
    dogKite: {image:'__IMG:dog-kite__', fallback:'dog kite'},
    dog: {image:'__IMG:dog__', fallback:'dog'},
    cat: {image:'__IMG:cat__', fallback:'cat'},
    monkey: {image:'__IMG:monkey__', fallback:'monkey'},
    monster: {image:'__IMG:monster__', fallback:'monster'}
  };
  function wave(options, answer) {
    return {
      goal:'Is it a kite?', options:options.map(key => cards[key]), answer,
      hint:'先跟住一张卡，看看整件东西的边。',
      hint2:'找带着牵线和尾带的整件东西。',
      success:'Yes, it is. 接到了！'
    };
  }
  K.game(K.gameTemplates.parachute({
    levels:[
      {name:'接稳第一张', demoRounds:[wave(['kite','dog'],0)], rounds:[wave(['monkey','catKite'],1)]},
      {name:'看清图案和物品', rounds:[wave(['dogKite','monster','dog'],0)]},
      {name:'两个展位来送卡', rounds:[
        wave(['cat','monkey','dog','catKite'],3),
        wave(['monster','dogKite','dog','cat'],1)
      ]}
    ],
    doneText:'你看清整张卡，接到了真正的风筝。'
  }));
})();
