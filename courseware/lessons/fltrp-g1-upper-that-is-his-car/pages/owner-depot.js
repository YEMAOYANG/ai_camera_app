K.ready({
  title: '招领台，把物品还回去',
  sub: '听是谁的，再推到主人的照片托盘。'
});

const depotGame = K.game(K.gameTemplates.sortingDepot({
  voiceLead: true,
  doneText: '每件东西都回到主人手里啦！',
  art: {
    backdrop: '__IMG:depot-backdrop__',
    frames: ['__IMG:depot-cart__', '__IMG:depot-cart-push__'],
    sticker: '__IMG:home-sticker__',
    icons: {
      ben: '__IMG:owner-ben__',
      lili: '__IMG:owner-lili__',
      book: '__IMG:item-book__',
      pen: '__IMG:item-pen__',
      desk: '__IMG:item-desk__',
      bag: '__IMG:item-bag__'
    }
  },
  cues: [
    {goal:'owners-one', hint:'owners-hint', hint2:'owners-help', praise:'owners-praise'},
    {goal:'owners-two', hint:'owners-hint', hint2:'owners-help', praise:'owners-praise'},
    {goal:'owners-three', hint:'owners-hint', hint2:'owners-help', praise:'owners-praise'}
  ],
  levels: [
    {
      map: ['########', '#......#', '#.S....#', '#......#', '########'],
      step: 0.31,
      items: [
        {x:3, y:2, token:'book', group:'ben'},
        {x:3, y:3, token:'pen', group:'lili'}
      ],
      docks: [
        {x:5, y:2, sample:'ben', group:'ben'},
        {x:5, y:3, sample:'lili', group:'lili'}
      ],
      hints: ['重听是谁的，再看看照片。', '看看亮起来的托盘，绕到物品后面。']
    },
    {
      map: ['#########', '#.......#', '#..#....#', '#.S.....#', '#.......#', '#########'],
      step: 0.24,
      items: [
        {x:4, y:2, token:'desk', group:'lili'},
        {x:4, y:4, token:'bag', group:'ben'},
        {x:3, y:3, token:'pen', group:'ben'}
      ],
      docks: [
        {x:6, y:2, sample:'lili', group:'lili'},
        {x:7, y:4, sample:'ben', group:'ben'},
        {x:6, y:3, sample:'ben', group:'ben'}
      ],
      hints: ['听完物品词，再找对应的主人。', '绕到物品另一侧，或者先撤回一步。']
    },
    {
      map: ['##########', '#........#', '#..#.....#', '#.S......#', '#....#...#', '#........#', '##########'],
      step: 0.20,
      items: [
        {x:4, y:3, token:'desk', group:'ben'},
        {x:7, y:4, token:'bag', group:'ben'},
        {x:4, y:2, token:'book', group:'lili'},
        {x:4, y:5, token:'pen', group:'lili'}
      ],
      docks: [
        {x:7, y:3, sample:'ben', group:'ben'},
        {x:8, y:4, sample:'ben', group:'ben'},
        {x:8, y:2, sample:'lili', group:'lili'},
        {x:7, y:5, sample:'lili', group:'lili'}
      ],
      hints: ['东西换了主人，可以重听。', '先留一条能绕过去的路，再推动。']
    }
  ]
}));
depotGame.follow('#first-owner', () => ({x:739,y:300,w:84,h:84}));
