const pictures = {
  ny1: '__IMG:sort-ny1__', cy1: '__IMG:sort-cy1__', cj1: '__IMG:sort-cj1__',
  ny5: '__IMG:sort-ny5__', cj5: '__IMG:sort-cj5__', cf5: '__IMG:sort-cf5__',
  nj1: '__IMG:sort-nj1__', cf2: '__IMG:sort-cf2__', ny20: '__IMG:sort-ny20__',
  ny10: '__IMG:sort-ny10__',
};
const labels = {
  ny1: '1元', cy1: '1元', cj1: '1角', ny5: '5元', cj5: '5角', cf5: '5分',
  nj1: '1角', cf2: '2分', ny20: '20元', ny10: '10元',
};
const cues = goal => ({goal, hint:'sort-hint', hint2:'sort-help', praise:'sort-praise'});
const levels = [
  {
    map: ['########','#......#','#S.....#','#......#','########'], step:.34,
    items: [{x:2,y:2,token:'ny1',group:'yuan'},{x:5,y:3,token:'cj1',group:'jiao'}],
    docks: [{x:3,y:2,sample:'ny10',group:'yuan'},{x:2,y:3,sample:'cj5',group:'jiao'}],
  },
  {
    map: ['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'], step:.28,
    items: [{x:4,y:2,token:'cj5',group:'jiao'},{x:4,y:4,token:'cf5',group:'fen'},{x:3,y:3,token:'ny5',group:'yuan'}],
    docks: [{x:6,y:2,sample:'nj1',group:'jiao'},{x:7,y:4,sample:'cf2',group:'fen'},{x:6,y:3,sample:'cy1',group:'yuan'}],
  },
  {
    map: ['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'], step:.23,
    items: [{x:4,y:3,token:'cy1',group:'yuan'},{x:7,y:4,token:'nj1',group:'jiao'},
      {x:4,y:2,token:'cf2',group:'fen'},{x:4,y:5,token:'ny20',group:'yuan'}],
    docks: [{x:7,y:3,sample:'ny5',group:'yuan'},{x:8,y:4,sample:'cj5',group:'jiao'},
      {x:8,y:2,sample:'cf5',group:'fen'},{x:7,y:5,sample:'ny1',group:'yuan'}],
  },
].map(level=>({
  ...level, labels, hints:['先看图牌和盒子上的单位。','从钱牌背后推，看看有没有亮起的同单位盒子。'],
}));

const title = '把钱牌送到同单位的盒子';
K.ready({title,sub:'看钱牌的数字和单位。绕过挡板，把钱牌推入同单位的盒子。'});
const activity = K.gameTemplates.sortingDepot({
  title, voiceLead:true, cues:[cues('sort-first'),cues('sort-two'),cues('sort-three')],
  art:{backdrop:'__IMG:reading-fair-table__',sticker:'__IMG:book-badge__',
    frames:['__IMG:book-cart__','__IMG:book-cart-moving__'],icons:pictures},
  doneText:'元、角、分的钱牌进了对应的盒子。',levels,
});
activity.onState = (_, state) => {
  if(state.demo===false) K.$$('.teach-hl',K.stage()).forEach(el=>el.classList.remove('teach-hl'));
};
const game = K.game(activity);
function firstCell(frame,point){
  const board=frame.data.w;
  if(!board||frame.level!==0)return null;
  const half=board.s*.45;
  return {x:board.ox+(point.x+.5)*board.s-half,y:board.oy+(point.y+.5)*board.s-half,w:half*2,h:half*2};
}
game.follow('#first-money-card',frame=>firstCell(frame,levels[0].items[0]));
game.follow('#first-unit-tray',frame=>firstCell(frame,levels[0].docks[0]));
