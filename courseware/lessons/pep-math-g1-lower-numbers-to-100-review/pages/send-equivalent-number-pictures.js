K.ready({title:'把同样多的数图放到一起', sub:'数十格条和散扣，再看展位上的珠子。'});

const loads={
  27:'__IMG:load-27__',52:'__IMG:load-52__',46:'__IMG:load-46__',64:'__IMG:load-64__',
  80:'__IMG:load-80__',35:'__IMG:load-35__',53:'__IMG:load-53__',90:'__IMG:load-90__',
  100:'__IMG:load-100__',
};
const docks={
  27:'__IMG:dock-27__',52:'__IMG:dock-52__',46:'__IMG:dock-46__',64:'__IMG:dock-64__',
  80:'__IMG:dock-80__',35:'__IMG:dock-35__',53:'__IMG:dock-53__',90:'__IMG:dock-90__',
  100:'__IMG:dock-100__',
};
const item=(group,x,y)=>({x,y,token:'load-'+group,group});
const dock=(group,x,y)=>({x,y,sample:'dock-'+group,group});
const hints=['先数满条，再数散扣。','十位一颗珠表示一条十扣，个位一颗表示一枚。再比对一下。'];
const cues={hint:'depot-hint',hint2:'depot-help',praise:'depot-praise'};
const icons=Object.fromEntries([
  ...Object.entries(loads).map(([n,url])=>['load-'+n,url]),
  ...Object.entries(docks).map(([n,url])=>['dock-'+n,url]),
]);
const depot=K.game(K.gameTemplates.sortingDepot({
  voiceLead:true,
  doneText:'展柜里不同的数图都配到同样多的木扣啦！',
  art:{
    backdrop:'__IMG:depot-backdrop__',
    frames:['__IMG:cart-ready__','__IMG:cart-push__'],
    sticker:'__IMG:exhibit-sticker__',
    icons,
  },
  cues:[{...cues,goal:'depot-two'},{...cues,goal:'depot-reverse'},{...cues,goal:'depot-hundred'}],
  levels:[
    {
      map:['#########','#.......#','#.S.....#','#.......#','#.......#','#########'],step:.31,hints,
      items:[item(27,3,2),item(52,3,4)],docks:[dock(27,6,2),dock(52,6,4)],
    },
    {
      map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#.......#','#########'],step:.27,hints,
      items:[item(46,4,2),item(64,4,4),item(80,3,3)],docks:[dock(64,6,2),dock(46,7,4),dock(80,6,3)],
    },
    {
      map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],step:.23,hints,
      items:[item(35,4,3),item(53,7,4),item(90,4,2),item(100,4,5)],
      docks:[dock(90,7,3),dock(53,8,4),dock(35,8,2),dock(100,7,5)],
    },
  ],
}));

depot.follow('#equivalence-guide',()=>({x:22,y:145,w:236,h:99}));
depot.follow('#first-load',()=>({x:527,y:268,w:70,h:70}));
depot.follow('#first-dock',()=>({x:761,y:268,w:70,h:70}));
for(let index=0;index<4;index++){
  const image=K.$('#load-view-'+(index+1));
  depot.follow(image,current=>{
    const {w,level}=current.data;
    const item=w&&level.items[index];
    const src=item&&w.state.items[index]>=0&&loads[item.group];
    image.style.visibility=src?'visible':'hidden';
    if(!src)return null;
    if(image.getAttribute('src')!==src)image.setAttribute('src',src);
    return {x:index%2===0?24:1023,y:274+Math.floor(index/2)*122,w:221,h:109};
  });
}
