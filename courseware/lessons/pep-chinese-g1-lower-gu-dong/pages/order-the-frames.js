const config = {
  title: '开泡泡车，按先后接画',
  sub: '听一句，接一张。接齐再去小旗。',
  doneText: '从听见咕咚到看清原因，故事接好了。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:film-backdrop__',
    sticker: '__IMG:gudong-sticker__',
    frames: ['__IMG:film-rover__','__IMG:film-rover-pop__'],
    icons: {
      A:'__IMG:film-splash-icon__', B:'__IMG:film-rabbit-icon__', C:'__IMG:film-monkey-icon__',
      D:'__IMG:film-group-icon__', F:'__IMG:film-buffalo-icon__', G:'__IMG:film-return-icon__',
      H:'__IMG:film-view-icon__', I:'__IMG:film-laugh-icon__'
    }
  },
  levels: [
    {
      map: ['#########','#S.A...E#','#..#.#..#','#B...C..#','#########'],
      route: ['A','B','C'], step:.34
    },
    {
      map: ['#########','#S...F.E#','#.###...#','#C...D..#','#.......#','#########'],
      route: ['C','D','F'], step:.29, patrols:[{y:4,from:2,to:6,speed:.96}]
    },
    {
      map: ['###########','#S.F..+..E#','#.#.###.#.#','#G.......I#','#...H.....#','###########'],
      route: ['F','G','H','I'], step:.25, patrols:[{y:3,from:2,to:7,speed:1.21}]
    }
  ].map(level=>({...level,listenOnly:true,hints:['先停一下，想想发生了什么。','重听，然后看发亮的画。']})),
  cues: [
    ['film-splash','film-rabbit','film-monkey','film-flag'],
    ['film-monkey','film-group','film-buffalo','film-flag'],
    ['film-buffalo','film-return','film-view','film-laugh','film-flag']
  ].map(steps=>({steps,goal:steps[0],hint:'film-hint',hint2:'film-help',praise:'film-praise'}))
};

K.ready({title:config.title,sub:config.sub});
const filmstrip=K.$('#gudong-filmstrip');
K.stage().append(K.$('#gudong-film-listen'),K.$('#gudong-film-first'),filmstrip);
const activity=K.gameTemplates.bubbleMaze(config);
const draw=activity.draw;
let shownRoute,shownCount;
activity.draw=(game,canvas)=>{
  draw(game,canvas);
  const {level,w}=game.data;
  if(!w) return;
  const count=Math.min(w.i,level.route.length);
  if(level.route===shownRoute&&count===shownCount) return;
  shownRoute=level.route;
  shownCount=count;
  filmstrip.replaceChildren(...level.route.slice(0,count).map(key=>{
    const frame=document.createElement('img');
    frame.src=config.art.icons[key];
    frame.alt='';
    return frame;
  }));
};
activity.onState=(_,state)=>{
  if(state.demo===false) K.$$('.teach-hl',K.stage()).forEach(anchor=>anchor.classList.remove('teach-hl'));
};
K.game(activity);
