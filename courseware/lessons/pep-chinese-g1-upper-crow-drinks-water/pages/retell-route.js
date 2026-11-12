const levels = [
  {map:['#########','#S.A...E#','#.#.###.#','#....D..#','#########'],
   route:['A','D'],step:.34},
  {map:['###########','#S..A....E#','#.#.###.#.#','#..C...D..#','#.........#','###########'],
   route:['A','C','D'],step:.27},
  {map:['#############','#S..A+.....E#','#.##.#####.##','#..B..C..D..#','###.##.##.#.#','#...........#','#############'],
   route:['A','B','C','D'],step:.22},
];
const hints = ['重听一句，想想这会儿发生了什么。','找亮起来的那一站，再开过去。'];
const feedback = {hint:'crow-route-hint',hint2:'crow-route-help',praise:'crow-route-praise'};
const cards = {
  A:{audio:'crow-route-dry',src:'__IMG:story-dry__',alt:'乌鸦够不到瓶里的水'},
  B:{audio:'crow-route-stone',src:'__IMG:story-stone__',alt:'乌鸦发现小石子'},
  C:{audio:'crow-route-drop',src:'__IMG:story-drop__',alt:'石子从瓶口往里落'},
  D:{audio:'crow-route-drink',src:'__IMG:story-drink__',alt:'水线抬高，乌鸦喝到了'},
};
const cue = (code) => cards[code].audio;
const title = '开车找回故事卡';
K.ready({title,sub:'听一句，找一站。收齐卡片再去小旗。'});
const arcade = K.gameTemplates.bubbleMaze({
  art:{
    backdrop:'__IMG:projection-backdrop__',sticker:'__IMG:film-sticker__',frames:['__IMG:film-cart__'],
    icons:Object.fromEntries(Object.entries(cards).map(([id,card])=>[id,card.src])),
  },
  title,voiceLead:true,stepVoiceLead:true,doneText:'指着收到的卡片，讲一讲先后。',
  levels:levels.map(level=>({...level,hints,listenOnly:true})),
  cues:levels.map(({route})=>({...feedback,goal:cue(route[0]),steps:[...route.map(cue),'crow-route-exit']})),
});

const drawGame = arcade.draw;
arcade.draw = (g,canvas) => {
  drawGame(g,canvas);
  const route = g.data.level?.route;
  if (g.state !== 'done' || !route || g.data.progress <= route.length) return;
  const card = K.$('#finish .card');
  const replay = K.$('#btn-again',card);
  if (!replay || K.$('.crow-film-strip',card)) return;
  const strip = K.el('div','crow-film-strip');
  for (const id of route) {
    const picture = K.el('img','',null,strip);
    picture.src = cards[id].src;
    picture.alt = cards[id].alt;
  }
  card.insertBefore(strip,replay);
};
K.game(arcade);
