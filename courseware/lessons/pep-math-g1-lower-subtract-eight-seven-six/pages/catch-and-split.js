K.ready({title:'接好灯片，分进两篮',sub:'听订单。左右移动接，按换篮键选送出或留下。'});

const catchGame = K.game(K.gameTemplates.orchardCatch({
  voiceLead: true,
  doneText: '送出的恰好够订单，其余灯片都留下了。',
  art: {
    backdrop: '__IMG:catch-backdrop__',
    frames: ['__IMG:catch-cart__'],
    sticker: '__IMG:rosette-sticker__',
    icons: {fruit:'__IMG:light-piece__'}
  },
  cues: [
    {goal:'catch-eight',hint:'catch-hint',hint2:'catch-help',praise:'catch-praise'},
    {goal:'catch-seven',hint:'catch-hint',hint2:'catch-help',praise:'catch-praise'},
    {goal:'catch-six',hint:'catch-hint',hint2:'catch-help',praise:'catch-praise'}
  ],
  levels: [
    {
      capacity:[8,4],batches:[[4,1],[2,0],[4,2],[2,1]],seconds:3.7,catchRadius:145,
      hints:['看看落点和这串有几片。','数当前篮的空格。放不下，就换另一个篮。']
    },
    {
      capacity:[7,6],batches:[[3,0],[4,2],[3,1],[2,0],[1,2]],seconds:3.35,catchRadius:128,wind:57,
      hints:['先看哪一边还有足够的空格。','这串不能拆开。数一数够放在哪一篮。']
    },
    {
      capacity:[6,8],batches:[[4,1],[3,2],[1,0],[2,1],[4,0]],seconds:3.05,catchRadius:111,wind:76,
      hints:['看看选中的是哪一个篮。','给后面的整串留够空格，再接这一串。']
    }
  ]
}));
catchGame.follow('#first-order-basket', () => ({x:44,y:96,w:310,h:132}));
