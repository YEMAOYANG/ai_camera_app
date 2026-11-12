const title = '把数量图送回托盘';
const preview = K.$('#unknown-preview');
const nearbyPicture = K.$('#nearby-quantity-card');
const item = (x, y, token, group) => ({x, y, token, group});
const dock = (x, y, group) => ({x, y, sample: 'tray-' + group, group});
const config = {
  title,
  sub: '用方向键推动数量卡，把问号位置相同的图送回托盘。',
  doneText: '合计、另一部分和相差三类数量图都归位了。',
  voiceLead: true,
  art: {
    backdrop: '__IMG:community-garden__',
    sticker: '__IMG:garden-reward__',
    frames: ['__IMG:garden-cart__', '__IMG:garden-cart-moving__'],
    icons: {
      'tray-whole': '__IMG:tray-whole__',
      'tray-part': '__IMG:tray-part__',
      'tray-gap': '__IMG:tray-gap__',
      'card-seeds-total': '__IMG:card-seeds-total__',
      'card-seeds-gap': '__IMG:card-seeds-gap__',
      'card-seeds-part': '__IMG:card-seeds-part__',
      'card-pots-gap': '__IMG:card-pots-gap__',
      'card-markers-total': '__IMG:card-markers-total__',
      'part-card-20': '__IMG:card-twenty-part__',
      'gap-card-23': '__IMG:card-twenty-three-gap__',
      'whole-card-19': '__IMG:card-nineteen-total__',
      'part-card-24': '__IMG:card-twenty-four-part__'
    }
  },
  levels: [
    {
      map: ['########', '#......#', '#.S....#', '#......#', '########'],
      items: [item(3, 2, 'card-seeds-total', 'whole'), item(3, 3, 'card-seeds-gap', 'gap')],
      docks: [dock(5, 2, 'whole'), dock(5, 3, 'gap')],
      step: .31
    },
    {
      map: ['#########', '#.#.....#', '#..#....#', '#.S.....#', '#.......#', '#########'],
      items: [item(4, 2, 'card-seeds-part', 'part'), item(3, 3, 'card-pots-gap', 'gap'),
              item(4, 4, 'card-markers-total', 'whole')],
      docks: [dock(6, 2, 'part'), dock(6, 3, 'gap'), dock(7, 4, 'whole')],
      step: .27
    },
    {
      map: ['##########', '#.#......#', '#..#.....#', '#.S......#', '#....#...#', '#.#......#', '##########'],
      items: [item(4, 3, 'part-card-20', 'part'), item(5, 2, 'whole-card-19', 'whole'),
              item(7, 4, 'part-card-24', 'part'), item(4, 5, 'gap-card-23', 'gap')],
      docks: [dock(8, 2, 'part'), dock(5, 1, 'whole'), dock(8, 4, 'part'), dock(7, 5, 'gap')],
      step: .24
    }
  ].map(level => ({
    ...level,
    hints: ['先找这张图上的问号。', '看看亮起来的托盘，再推一步。']
  })),
  cues: Array.from({length: 3}, () => ({
    goal: 'sort-unknown-goal', hint: 'sort-unknown-hint', hint2: 'sort-unknown-help', praise: 'sort-unknown-praise'
  }))
};

K.ready({title, sub: config.sub});
K.stage().append(preview, K.$('#first-quantity-card'), K.$('#first-quantity-dock'));
const game = K.gameTemplates.sortingDepot(config);
const draw = game.draw;
game.draw = (g, context) => {
  draw(g, context);
  const world = g.data.w;
  preview.hidden = !world || g.state === 'ready' || g.state === 'done';
  if (preview.hidden) return;
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
      nearest = {position, token: level.items[index].token};
    }
  });
  if (!nearest) return;
  if (nearbyPicture.dataset.card !== nearest.token) {
    nearbyPicture.src = config.art.icons[nearest.token];
    nearbyPicture.dataset.card = nearest.token;
  }
  context.save();
  context.strokeStyle = '#75b0a4';
  context.lineWidth = 4;
  context.strokeRect(world.ox + (nearest.position % columns + .15) * world.s,
    world.oy + (Math.floor(nearest.position / columns) + .15) * world.s, .7 * world.s, .7 * world.s);
  context.restore();
};
game.onState = (_, state) => {
  if (state.pause === false) K.$$('.teach-hl', K.stage()).forEach(el => el.classList.remove('teach-hl'));
};
K.game(game);
