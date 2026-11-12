K.ready({title:'接成十条', sub:'看条数，移到伙伴旁边，再让牌落下。'});

const stripArt = [null,
  '__IMG:fall-strips-1__', '__IMG:fall-strips-2__', '__IMG:fall-strips-3__',
  '__IMG:fall-strips-4__', '__IMG:fall-strips-5__', '__IMG:fall-strips-6__',
  '__IMG:fall-strips-7__', '__IMG:fall-strips-8__', '__IMG:fall-strips-9__',
];
const joinedArt = [null,
  '__IMG:fall-finished-1__', '__IMG:fall-finished-2__', '__IMG:fall-finished-3__',
  '__IMG:fall-finished-4__', '__IMG:fall-finished-5__',
];
const shared = {
  total: 10,
  symbol: 'ten',
  hints: ['先数条数，凑成十条。', '先左右移动，再在搭档的旁边落下。'],
};
const cues = {hint:'fall-hint', hint2:'fall-help', praise:'fall-praise'};
const game = K.game(K.gameTemplates.fallingTiles({
  voiceLead: true,
  doneText: '凑齐十条十连贴纸，就是一百枚。',
  art: {
    backdrop: '__IMG:fall-backdrop__',
    sticker: '__IMG:rosette-award__',
    icons: {
      1:stripArt[1], 2:stripArt[2], 3:stripArt[3],
      4:stripArt[4], 5:stripArt[5], 6:stripArt[6],
      7:stripArt[7], 8:stripArt[8], 9:stripArt[9],
      ten:'__IMG:fall-empty-ten__',
    },
  },
  cues: [
    {...cues, goal:'fall-first'},
    {...cues, goal:'fall-second'},
    {...cues, goal:'fall-third'},
  ],
  levels: [
    {...shared, bottom:[null,null,null,null,8,null], pieces:[2], interval:1.5},
    {...shared, bottom:[null,7,null,null,6,null], pieces:[3,4], interval:1.2},
    {...shared, bottom:[null,9,null,5,null,8], pieces:[1,5,2], interval:1},
  ],
}));

game.follow('#hundred-target', () => ({x:27,y:140,w:180,h:132}));
game.follow('#first-eight-strips', () => ({x:710,y:526,w:70,h:70}));

function followPreview(id, box, imageFor) {
  const image = K.$(id);
  game.follow(image, current => {
    const {w,level} = current.data;
    const src = w && imageFor(w,level);
    image.style.visibility = src ? 'visible' : 'hidden';
    if (!src) return null;
    if (image.getAttribute('src') !== src) image.setAttribute('src',src);
    return box;
  });
}

followPreview('#falling-strip-preview', {x:219,y:140,w:180,h:132},
  (w,level) => w.delay <= 0 ? stripArt[level.pieces[w.i]] : null);
['first','second','third','fourth','fifth','sixth'].forEach((name,index) => {
  followPreview('#floor-strip-'+name, {x:27+(index%3)*125,y:299+Math.floor(index/3)*111,w:117,h:106},
    w => stripArt[w.board[6].filter(value => value !== null)[index]]);
});
followPreview('#joined-hundred', {x:1085,y:175,w:168,h:136},
  (w,level) => joinedArt[level.pieces[w.i-1]]);
