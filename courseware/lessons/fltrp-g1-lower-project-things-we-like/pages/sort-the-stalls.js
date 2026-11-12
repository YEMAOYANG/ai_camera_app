const config = {
  title: '把图卡推到同类展台',
  sub: '用方向键推卡。看托盘画的是什么，把图卡放进同一类。',
  doneText: '四种喜好的图卡都送到展台了。',
  voiceLead: true,
  art: {
    backdrop: '__IMG:sort-backdrop__',
    sticker: '__IMG:project-sticker__',
    frames: ['__IMG:sort-cart__', '__IMG:sort-cart-push__'],
    icons: {
      rabbits: '__IMG:sort-rabbits__',
      football: '__IMG:sort-football__',
      robot: '__IMG:sort-robot__',
      yellow: '__IMG:sort-yellow__',
      ducks: '__IMG:sort-ducks__',
      skating: '__IMG:sort-skating__',
      blocks: '__IMG:sort-blocks__',
      purple: '__IMG:sort-purple__',
      animals: '__IMG:dock-animals__',
      sports: '__IMG:dock-sports__',
      toys: '__IMG:dock-toys__',
      colours: '__IMG:dock-colours__'
    }
  },
  levels: [
    {
      map: ['########', '#......#', '#.S....#', '#......#', '########'],
      items: [{x: 3, y: 2, token: 'rabbits', group: 'animals'}, {x: 3, y: 3, token: 'football', group: 'sports'}],
      docks: [{x: 5, y: 2, sample: 'animals', group: 'animals'}, {x: 5, y: 3, sample: 'sports', group: 'sports'}],
      step: .31
    },
    {
      map: ['#########', '#.......#', '#..#....#', '#.S.....#', '#.......#', '#########'],
      items: [
        {x: 4, y: 2, token: 'robot', group: 'toys'},
        {x: 3, y: 3, token: 'yellow', group: 'colours'},
        {x: 4, y: 4, token: 'ducks', group: 'animals'}
      ],
      docks: [
        {x: 6, y: 2, sample: 'toys', group: 'toys'},
        {x: 6, y: 3, sample: 'colours', group: 'colours'},
        {x: 7, y: 4, sample: 'animals', group: 'animals'}
      ],
      step: .26
    },
    {
      map: ['##########', '#........#', '#..#.....#', '#.S......#', '#....#...#', '#........#', '##########'],
      items: [
        {x: 4, y: 3, token: 'skating', group: 'sports'},
        {x: 5, y: 2, token: 'blocks', group: 'toys'},
        {x: 7, y: 4, token: 'purple', group: 'colours'},
        {x: 4, y: 5, token: 'rabbits', group: 'animals'}
      ],
      docks: [
        {x: 8, y: 2, sample: 'sports', group: 'sports'},
        {x: 5, y: 1, sample: 'toys', group: 'toys'},
        {x: 8, y: 4, sample: 'colours', group: 'colours'},
        {x: 7, y: 5, sample: 'animals', group: 'animals'}
      ],
      step: .22
    }
  ].map(level => ({...level, hints: ['想想图上的东西是哪一类。', '退一步，向发亮的同类展台推。']})),
  cues: ['sort-first', 'sort-next', 'sort-last'].map(goal =>
    ({goal, hint: 'sort-hint', hint2: 'sort-help', praise: 'sort-praise'}))
};

K.ready({title: config.title, sub: config.sub});
K.stage().append(K.$('#first-sort-card'), K.$('#first-sort-dock'));
const activity = K.gameTemplates.sortingDepot(config);
activity.onState = (_, state) => {
  if (state.demo === false) K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
};
K.game(activity);
