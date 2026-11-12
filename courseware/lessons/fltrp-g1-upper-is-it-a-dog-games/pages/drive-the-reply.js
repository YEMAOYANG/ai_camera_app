K.ready({title:'开车送回话卡', sub:'按住画面开车，轻碰能说明答案的回话卡', emoji:'风筝展'});
(() => {
  const objects = {
    dog:{image:'__IMG:dog__',fallback:'dog'},
    monkey:{image:'__IMG:monkey__',fallback:'monkey'},
    dogKite:{image:'__IMG:dog-kite__',fallback:'dog kite'},
    cat:{image:'__IMG:cat__',fallback:'cat'}
  };
  const pairs = {
    dog:{image:'__IMG:game-pair-dog__',fallback:'dog / dog'},
    monkey:{image:'__IMG:game-pair-monkey__',fallback:'dog / monkey'},
    dogKite:{image:'__IMG:game-pair-dog-kite__',fallback:'dog / dog kite'},
    cat:{image:'__IMG:game-pair-cat__',fallback:'dog / cat'}
  };
  function road(revealed, cargo) {
    return {
      goal:objects[revealed], player:objects.dog, options:cargo.map(key => pairs[key]), answer:cargo.indexOf(revealed),
      hint:'回头看看上方的实物，再找能说明它的卡。',
      hint2:'每张卡左边是猜的小狗，右边要和上面的实物对上。',
      success:revealed === 'dog' ? 'Yes, it is.' : "No, it isn't."
    };
  }
  K.game(K.gameTemplates.bumper({
    levels:[
      {name:'看实物，碰回话卡', demoRounds:[road('dog',['monkey','dog'])], rounds:[road('monkey',['dog','monkey'])]},
      {name:'狗脸图案的线索', rounds:[road('dogKite',['dogKite','dog','monkey'])]},
      {name:'连送两次回话', rounds:[
        road('dog',['monkey','dogKite','dog','cat']),
        road('cat',['dogKite','cat','monkey','dog'])
      ]}
    ],
    doneText:'每次看清真实展品，再开车送回话卡。'
  }));
})();
