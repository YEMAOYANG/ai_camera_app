const config = {
  title: '泡泡车给故事排顺序',
  sub: '听线索，沿路接画面，接齐后去小旗。',
  doneText: '山脚的影偶故事接好了。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:maze-backdrop__',
    sticker: '__IMG:monkey-sticker__',
    frames: ['__IMG:maze-rover__', '__IMG:maze-rover-pop__'],
    icons: {
      A: '__IMG:map-corn-icon__', B: '__IMG:map-peach-icon__', C: '__IMG:map-melon-icon__',
      F: '__IMG:map-throw-icon__', G: '__IMG:map-pick-icon__', H: '__IMG:map-carry-icon__',
      I: '__IMG:map-hug-icon__', J: '__IMG:map-chase-icon__', K: '__IMG:map-woods-icon__',
      L: '__IMG:map-home-icon__'
    }
  },
  levels: [
    {
      map: ['#########', '#S.A...E#', '#..#.#..#', '#B...C..#', '#########'],
      route: ['A', 'B', 'C'],
      step: .33
    },
    {
      map: ['#########', '#S...H.E#', '#.###...#', '#F...G..#', '#.......#', '#########'],
      route: ['F', 'G', 'H'],
      step: .29,
      patrols: [{y: 4, from: 2, to: 6, speed: .92}]
    },
    {
      map: ['###########', '#S.I..+..E#', '#.#.###.#.#', '#J.......L#', '#...K.....#', '###########'],
      route: ['I', 'J', 'K', 'L'],
      step: .25,
      patrols: [{y: 3, from: 2, to: 7, speed: 1.23}]
    }
  ].map(level => ({
    ...level, listenOnly: true,
    hints: ['先听要找哪一幕。', '再听一遍，看看发亮的画面。']
  })),
  cues: [
    ['map-corn', 'map-peach', 'map-melon', 'map-exit'],
    ['map-throw', 'map-pick', 'map-carry', 'map-exit'],
    ['map-hug', 'map-chase', 'map-woods', 'map-home', 'map-exit']
  ].map(steps => ({steps, goal: steps[0], hint: 'map-hint', hint2: 'map-hint2', praise: 'map-praise'}))
};

K.ready({title: config.title, sub: config.sub});
const filmstrip = K.$('#monkey-filmstrip');
K.stage().append(K.$('#monkey-maze-listen'), K.$('#monkey-maze-first'), filmstrip);
const activity = K.gameTemplates.bubbleMaze(config);
const draw = activity.draw;
let shownRoute, shownCount;
activity.draw = (game, canvas) => {
  draw(game, canvas);
  const {level, w} = game.data;
  if (!w) return;
  const count = Math.min(w.i, level.route.length);
  if (level.route === shownRoute && count === shownCount) return;
  shownRoute = level.route;
  shownCount = count;
  filmstrip.replaceChildren(...level.route.slice(0, count).map(key => {
    const frame = document.createElement('img');
    frame.src = config.art.icons[key];
    frame.alt = '';
    return frame;
  }));
};
activity.onState = (_, state) => {
  if (state.demo === false) {
    K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
  }
};
K.game(activity);
