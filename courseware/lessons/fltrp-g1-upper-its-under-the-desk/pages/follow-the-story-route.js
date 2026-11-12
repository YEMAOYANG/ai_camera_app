K.ready({title:'按听到的顺序找布偶',sub:'沿着小路找图，最后去小旗。'});

const positions = {
  A:'__IMG:hazel-on-chair__', B:'__IMG:hazel-under-desk__',
  C:'__IMG:hazel-on-desk__', D:'__IMG:hazel-in-bag__', F:'__IMG:hazel-under-chair__',
  G:'__IMG:hazel-under-desk__', H:'__IMG:hazel-in-box__',
  J:'__IMG:hazel-on-chair__', K:'__IMG:hazel-in-bag__'
};
const routes = [
  {map:['#########','#.......#','#S.A.B.E#','#.......#','#########'],
    route:['A','B'],listenOnly:true,step:.30,
    hints:['先找刚刚听到的位置。','回到正确的图站，再接着走。']},
  {map:['##########','#..C.....#','#S...+..E#','#..D...F.#','##########'],
    route:['C','D','F'],listenOnly:true,step:.24,
    hints:['布偶换位置了，重听现在在哪。','对照台面、袋口或椅脚再走。']},
  {map:['###########','#..G......#','#S...#..H.#','#..J..+...#','#....K...E#','###########'],
    route:['H','J','G','K'],listenOnly:true,step:.20,
    hints:['找到同一只布偶现在所在的地方。','看左边找到过的图，再听下一句。']}
];
const trail = K.$('#story-trail');
const gallery = K.$('#station-gallery');
const trailCards = [...trail.querySelectorAll('img')];
const galleryCards = [...gallery.querySelectorAll('img')];
const galleryOrders = [['B','A'],['D','F','C'],['J','K','H','G']];
function showPositions(cards, order) {
  cards.forEach((card, i) => {
    const picture = positions[order[i]];
    card.hidden = !picture;
    if (picture && card.getAttribute('src') !== picture) card.setAttribute('src',picture);
  });
}
const maze = K.game(K.gameTemplates.bubbleMaze({
  voiceLead:true,
  stepVoiceLead:true,
  doneText:'你找到同一只布偶先后去过的地方。',
  art:{
    backdrop:'__IMG:library-backdrop__',
    frames:['__IMG:maze-cart-idle__','__IMG:maze-cart-pop__'],
    sticker:'__IMG:sprout-sticker__',
    icons:positions
  },
  cues:[
    {goal:'hazel-on-chair',hint:'maze-hint',hint2:'maze-help',praise:'maze-praise',
      steps:['hazel-on-chair','hazel-under-desk','maze-exit']},
    {goal:'hazel-on-desk',hint:'maze-hint',hint2:'maze-help',praise:'maze-praise',
      steps:['hazel-on-desk','hazel-in-bag','hazel-under-chair','maze-exit']},
    {goal:'hazel-in-box',hint:'maze-hint',hint2:'maze-help',praise:'maze-praise',
      steps:['hazel-in-box','hazel-on-chair','hazel-under-desk','hazel-in-bag','maze-exit']}
  ],
  levels:routes
}));
maze.follow('#first-story-stop', () => ({x:539.5,y:314,w:67,h:67}));
maze.follow('#story-exit', () => ({x:807.5,y:314,w:67,h:67}));
maze.follow('#story-trail', game => {
  const order = routes[game.level].route;
  const found = game.data.w?.i ?? 0;
  trail.hidden = found === 0;
  showPositions(trailCards, order.slice(0, found));
  return {x:27,y:171,w:199,h:189};
});
maze.follow('#station-gallery', game => {
  showPositions(galleryCards, galleryOrders[game.level]);
  return {x:1019,y:171,w:230,h:221};
});
