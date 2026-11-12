K.ready({title:'推来这道题用得上的线索',sub:'看这关问哪一组，再把线索推到合适的托盘。'});

const clueArt = {
  'whole-first':'__IMG:sort-whole-12__', 'leaf-first':'__IMG:sort-leaf-7__', people:'__IMG:sort-people-3__',
  'label-whole':'__IMG:sort-labels-15__', 'label-left':'__IMG:sort-remaining-8__', trays:'__IMG:sort-trays-2__',
  'this-whole':'__IMG:sort-whole-14__', 'this-leaf':'__IMG:sort-leaf-6__', 'other-wave':'__IMG:sort-other-5__',
  needed:'__IMG:magnifier__', aside:'__IMG:aside-shelf__'
};
const item = (x,y,token,group) => ({x,y,token,group});
const dock = (x,y,group) => ({x,y,group,sample:group});
const room = ['#########','#.......#','#.......#','#.S.....#','#.......#','#########'];
const levels = [
  {
    map:room,step:.31,
    items:[item(3,3,'whole-first','needed'),item(4,2,'leaf-first','needed'),item(4,4,'people','aside')],
    docks:[dock(6,3,'needed'),dock(6,2,'needed'),dock(7,4,'aside')],
    hints:['先想问题问的是哪一组。','用手比一比。是这架的书签线索吗？']
  },
  {
    map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],step:.26,
    items:[item(4,2,'trays','aside'),item(4,4,'label-left','needed'),item(3,3,'label-whole','needed')],
    docks:[dock(6,2,'aside'),dock(7,4,'needed'),dock(6,3,'needed')],
    hints:['这回问的是借出去多少张。','找标签原来有多少和还剩多少。']
  },
  {
    map:['##########','#........#','#..#.....#','#.S......#','#.#......#','#........#','##########'],step:.22,
    items:[item(4,3,'this-whole','needed'),item(6,3,'other-wave','aside'),item(4,2,'this-leaf','needed'),item(4,5,'people','aside')],
    docks:[dock(7,3,'needed'),dock(8,4,'aside'),dock(8,2,'needed'),dock(7,5,'aside')],
    hints:['两张都画书签。再看看是哪一架。','只问拱顶架。找这架的总量和已知一组。']
  }
];
const depot = K.game(K.gameTemplates.sortingDepot({
  voiceLead:true,doneText:'按这个问题，选出了能用的线索。',
  art:{backdrop:'__IMG:sort-backdrop__',frames:['__IMG:sort-cart__','__IMG:sort-push__'],sticker:'__IMG:leaf-sticker__',icons:clueArt},
  cues:[
    {goal:'sort-bookmark',hint:'sort-hint',hint2:'sort-help',praise:'sort-praise'},
    {goal:'sort-loan',hint:'sort-hint',hint2:'sort-help',praise:'sort-praise'},
    {goal:'sort-rack',hint:'sort-hint',hint2:'sort-help',praise:'sort-praise'}
  ],
  levels
}));
const gallery = K.$('#clue-gallery');
const question = K.$('#sort-question');
const images = [...gallery.querySelectorAll('.clue')];
const galleryOrder = [
  ['people','leaf-first','whole-first'], ['label-left','trays','label-whole'],
  ['other-wave','this-whole','people','this-leaf']
];
const ask = ['__IMG:drop-wave__','__IMG:drop-loan__','__IMG:drop-wave__'];
depot.follow(gallery, game => {
  const order = galleryOrder[game.level];
  if (question.getAttribute('src') !== ask[game.level]) question.setAttribute('src',ask[game.level]);
  images.forEach((image,i)=>{
    image.hidden = !order[i];
    if (order[i] && image.getAttribute('src') !== clueArt[order[i]]) image.setAttribute('src',clueArt[order[i]]);
  });
  return {x:20,y:153,w:229,h:21+(order.length+1)*62};
});
depot.follow('#first-total-card', () => ({x:527,y:346,w:70,h:70}));
depot.follow('#first-needed-dock', () => ({x:761,y:346,w:70,h:70}));
