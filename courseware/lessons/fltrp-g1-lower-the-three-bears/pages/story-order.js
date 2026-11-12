K.ready({title:'按听到的顺序连起画面',sub:'听到哪个动作，就开到那一张图。'});
const startPicture = K.$('#ready .pic');
startPicture.addEventListener('error', () => { startPicture.src = '__IMG:puppet-stage__'; }, {once:true});

const stationImages = {
  H:'__IMG:enter-house__', N:'__IMG:baby-noodles__', B:'__IMG:baby-bed__',
  R:'__IMG:bears-return__', L:'__IMG:girl-leaves__'
};
const hints = ['停在路上，重听这次说到的动作。','先听动作，再对照车边的画卡。'];
const levels = [
  {map:['#########','#....N..#','#.......#','#...#...#','#..H....#','#S....#E#','#########'],
    route:['H','N'], legend:['N','H'], listenOnly:true, step:.34, hints},
  {map:['#########','#..N..R.#','#.......#','#.#...#.#','#.....H.#','#S....#E#','#########'],
    route:['H','N','R'], legend:['N','R','H'], listenOnly:true, step:.28, hints},
  {map:['#########','#....L..#','#.B.....#','#..#..R.#','#..N....#','#S....#E#','#########'],
    route:['N','B','R','L'], legend:['R','B','L','N'], listenOnly:true, step:.23, hints}
];
const options = K.gameTemplates.bubbleMaze({
  art:{backdrop:'__IMG:forest-stage__',sticker:'__IMG:puppet-stage__',
    frames:['__IMG:cart__','__IMG:cart-angle__'],icons:stationImages},
  voiceLead:true,
  stepVoiceLead:true,
  levels,
  cues:[
    {goal:'enter-house',hint:'route-hint',hint2:'route-help',praise:'route-praise',steps:['enter-house','taste-noodles','route-exit']},
    {goal:'enter-house',hint:'route-hint',hint2:'route-help',praise:'route-praise',steps:['enter-house','taste-noodles','bears-return','route-exit']},
    {goal:'taste-noodles',hint:'route-hint',hint2:'route-help',praise:'route-praise',steps:['taste-noodles','try-bed','bears-return','girl-leaves','route-exit']}
  ],
  doneText:'故事画卡串好了。'
});
const gallery = Object.fromEntries(Object.entries(stationImages).map(([key, src]) => {
  const image = new Image();
  image.src = src;
  return [key, image];
}));
options.drawTop = (game, canvas) => {
  const legend = game.data.level?.legend;
  if (!legend) return;
  canvas.fillStyle = '#f6e5bd';
  K.draw.rr(canvas,977,117,252,274,18);
  canvas.fill();
  legend.forEach((key, index) => {
    const image = gallery[key];
    if (image.complete && image.naturalWidth) {
      canvas.drawImage(image, 986 + index % 2 * 122, 126 + Math.floor(index / 2) * 128, 112, 112);
    }
  });
};
options.onState = (_game, state) => {
  if (state.pause === false || state.demo === false) {
    for (const anchor of K.$$('.teach-hl')) anchor.classList.remove('teach-hl');
  }
};
K.game(options);
