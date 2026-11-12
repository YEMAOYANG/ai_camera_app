const config = {
  title: '听清故事，开车接图',
  sub: '听一句，接一张。接完这一组，再开到小旗。',
  doneText: '故事画面按先后接齐了。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:story-backdrop__',
    sticker: '__IMG:radio-sticker__',
    frames: ['__IMG:story-rover__', '__IMG:story-rover-pop__'],
    icons: {
      A: '__IMG:map-corn-seed__', B: '__IMG:map-corn-harvest__',
      C: '__IMG:map-peanut-seed__', D: '__IMG:map-peanut-harvest__',
      F: '__IMG:map-cat-pit__', G: '__IMG:map-cat-dream__',
      H: '__IMG:map-hat-park__', I: '__IMG:map-hat-wind__',
      J: '__IMG:map-hat-found__', K: '__IMG:map-hat-back__'
    }
  },
  levels: [
    {
      map: ['#########', '#S.A...E#', '#..#.#.D#', '#B...C..#', '#########'],
      route: ['A', 'B', 'C', 'D'], step: .34
    },
    {
      map: ['#########', '#S...F.E#', '#.###.G.#', '#C...D..#', '#.......#', '#########'],
      route: ['C', 'D', 'F', 'G'], step: .29,
      patrols: [{y: 4, from: 2, to: 6, speed: .96}]
    },
    {
      map: ['###########', '#S.H..+..E#', '#.#.###.#.#', '#I.......K#', '#...J.....#', '###########'],
      route: ['H', 'I', 'J', 'K'], step: .25,
      patrols: [{y: 3, from: 2, to: 7, speed: 1.21}]
    }
  ].map(level => ({
    ...level, listenOnly: true,
    hints: ['先停一停，再听这张发生了什么。', '重听，然后看看发亮的画面。']
  })),
  cues: [
    ['story-plant-corn', 'story-pick-corn', 'story-plant-peanut', 'story-pick-peanut', 'story-exit'],
    ['story-plant-peanut', 'story-pick-peanut', 'story-cat-pit', 'story-cat-dream', 'story-exit'],
    ['story-hat-park', 'story-hat-wind', 'story-hat-found', 'story-hat-back', 'story-exit']
  ].map(steps => ({steps, goal: steps[0], hint: 'story-hint', hint2: 'story-help', praise: 'story-praise'}))
};

K.ready({title: config.title, sub: config.sub});
const filmstrip = K.$('#garden-seven-filmstrip');
K.stage().append(K.$('#garden-seven-story-listen'), K.$('#garden-seven-story-first'), filmstrip);
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
  if (state.demo === false) K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
};
K.game(activity);
