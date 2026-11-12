K.ready({title:'比较卡找泊位', sub:'先看参照和方向，再看差得近还是远。'});

const icons = {
  'badge-25-27':'__IMG:badge-25-27__', 'badge-25-71':'__IMG:badge-25-71__',
  'badge-50-46':'__IMG:badge-50-46__', 'badge-50-13':'__IMG:badge-50-13__',
  'badge-50-54':'__IMG:badge-50-54__', 'badge-52-55':'__IMG:badge-52-55__',
  'badge-52-97':'__IMG:badge-52-97__', 'badge-52-48':'__IMG:badge-52-48__',
  'badge-52-11':'__IMG:badge-52-11__',
  moreNear:'__IMG:dock-morenear__', moreFar:'__IMG:dock-morefar__',
  lessNear:'__IMG:dock-lessnear__', lessFar:'__IMG:dock-lessfar__',
};
const badge = (ref,value,span,x,y) => ({
  x,y, token:'badge-'+ref+'-'+value,
  group:(value>ref?'more':'less')+span,
});
const dock = (group,x,y) => ({x,y,sample:group,group});
const hints = ['先从菱形参照看向圆形。往左还是往右？','再比箭头。哪一个方向和长短都对？'];
const cues = {hint:'depot-hint', hint2:'depot-help', praise:'depot-praise'};
const depot = K.game(K.gameTemplates.sortingDepot({
  voiceLead:true,
  doneText:'从参照出发，方向和远近都对，卡才进泊位。',
  art:{
    backdrop:'__IMG:depot-backdrop__',
    frames:['__IMG:cart-ready__','__IMG:cart-push__'],
    sticker:'__IMG:ticket-sticker__',
    icons,
  },
  cues:[
    {...cues,goal:'depot-right'},
    {...cues,goal:'depot-left'},
    {...cues,goal:'depot-all'},
  ],
  levels:[
    {
      map:['#########','#.......#','#.S.....#','#.......#','#.......#','#########'],
      step:.31,hints,
      items:[badge(25,27,'Near',3,2),badge(25,71,'Far',3,4)],
      docks:[dock('moreNear',6,2),dock('moreFar',6,4)],
    },
    {
      map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],
      step:.27,hints,
      items:[badge(50,46,'Near',4,2),badge(50,13,'Far',4,4),badge(50,54,'Near',3,3)],
      docks:[dock('lessNear',6,2),dock('lessFar',7,4),dock('moreNear',6,3)],
    },
    {
      map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],
      step:.23,hints,
      items:[badge(52,97,'Far',4,3),badge(52,11,'Far',7,4),badge(52,55,'Near',4,2),badge(52,48,'Near',4,5)],
      docks:[dock('moreFar',7,3),dock('lessFar',8,4),dock('moreNear',8,2),dock('lessNear',7,5)],
    },
  ],
}));

depot.follow('#badge-rules', () => ({x:22,y:141,w:235,h:108}));
depot.follow('#first-compared-card', () => ({x:527,y:268,w:70,h:70}));
depot.follow('#first-comparison-dock', () => ({x:761,y:268,w:70,h:70}));
for (let index=0;index<4;index++) {
  const image=K.$('#badge-view-'+(index+1));
  depot.follow(image, game => {
    const {w,level}=game.data;
    const pending=w && level.items[index] && w.state.items[index]>=0;
    image.style.visibility=pending?'visible':'hidden';
    if (!pending) return null;
    const src=icons[level.items[index].token];
    if (image.getAttribute('src')!==src) image.setAttribute('src',src);
    return {x:index%2===0?24:1023,y:279+Math.floor(index/2)*124,w:224,h:111};
  });
}
