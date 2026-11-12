const title = '把对齐卡送回托盘';
const legend = K.$('#pairing-legend');
const nearbyCard = K.$('#nearby-pairing-card');
const item = (x, y, token, group) => ({x, y, token, group});
const dock = (x, y, group) => ({x, y, sample: group === 'paired' ? 'tray-paired' : 'tray-gap', group});
const config = {
  title,
  sub: '用方向键推卡，把图卡送到框着同一段的托盘。',
  doneText: '配齐的一段和相差的一段都归位了。',
  voiceLead: true,
  art: {
    backdrop: '__IMG:camp-clearing__',
    sticker: '__IMG:camp-reward__',
    frames: ['__IMG:camp-cart__', '__IMG:camp-cart-moving__'],
    icons: {
      'tray-paired': '__IMG:tray-paired__',
      'tray-gap': '__IMG:tray-gap__',
      'pair-card-1-equal': '__IMG:pair-card-1-equal__',
      'pair-card-1-gap': '__IMG:pair-card-1-gap__',
      'pair-card-2-equal': '__IMG:pair-card-2-equal__',
      'pair-card-2-gap': '__IMG:pair-card-2-gap__',
      'pair-card-3-equal': '__IMG:pair-card-3-equal__',
      'pair-card-3-gap': '__IMG:pair-card-3-gap__',
      'pair-card-3-short': '__IMG:pair-card-3-short__'
    }
  },
  levels: [
    {
      map: ['########', '#......#', '#.S....#', '#......#', '########'],
      items: [item(3, 2, 'pair-card-1-equal', 'paired'), item(3, 3, 'pair-card-1-gap', 'gap')],
      docks: [dock(5, 2, 'paired'), dock(5, 3, 'gap')],
      step: .31
    },
    {
      map: ['#########', '#.......#', '#..#....#', '#.S.....#', '#.......#', '#########'],
      items: [item(4, 2, 'pair-card-2-gap', 'gap'), item(3, 3, 'pair-card-2-equal', 'paired'),
              item(4, 4, 'pair-card-2-gap', 'gap')],
      docks: [dock(6, 2, 'gap'), dock(6, 3, 'paired'), dock(7, 4, 'gap')],
      step: .27
    },
    {
      map: ['##########', '#........#', '#..#.....#', '#.S......#', '#....#...#', '#........#', '##########'],
      items: [item(4, 3, 'pair-card-3-short', 'gap'), item(5, 2, 'pair-card-3-equal', 'paired'),
              item(7, 4, 'pair-card-3-gap', 'gap'), item(4, 5, 'pair-card-3-equal', 'paired')],
      docks: [dock(8, 2, 'gap'), dock(5, 1, 'paired'), dock(8, 4, 'gap'), dock(7, 5, 'paired')],
      step: .24
    }
  ].map(level => ({
    ...level,
    hints: ['再看看框线从哪儿开始。', '看看亮起来的托盘，再走一小步。']
  })),
  cues: Array.from({length: 3}, () => ({
    goal: 'sort-goal', hint: 'sort-hint', hint2: 'sort-help', praise: 'sort-praise'
  }))
};

K.ready({title, sub: config.sub});
K.stage().append(legend, K.$('#first-paired-card'), K.$('#first-paired-dock'));
const game = K.gameTemplates.sortingDepot(config);
const draw = game.draw;
game.draw = (g, context) => {
  draw(g, context);
  const world = g.data.w;
  legend.hidden = !world || g.state === 'ready' || g.state === 'done';
  if (legend.hidden) return;

  const level = config.levels[g.level];
  const columns = level.map[0].length;
  const player = world.state.p;
  let nearest = null;
  let distance = Infinity;
  world.state.items.forEach((position, index) => {
    if (position < 0) return;
    const steps = Math.abs(position % columns - player % columns)
      + Math.abs(Math.floor(position / columns) - Math.floor(player / columns));
    if (steps < distance) {
      distance = steps;
      nearest = { position, token: level.items[index].token };
    }
  });
  if (!nearest) return;
  if (nearbyCard.dataset.card !== nearest.token) {
    nearbyCard.src = config.art.icons[nearest.token];
    nearbyCard.dataset.card = nearest.token;
  }
  context.save();
  context.strokeStyle = '#74a9a2';
  context.lineWidth = 4;
  context.strokeRect(world.ox + (nearest.position % columns + .15) * world.s,
    world.oy + (Math.floor(nearest.position / columns) + .15) * world.s, .7 * world.s, .7 * world.s);
  context.restore();
};
game.onState = (_, state) => {
  if (state.pause === false) K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
};
K.game(game);
