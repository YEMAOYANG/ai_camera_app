K.ready({title:'滑动捆卡和散杆卡',sub:'对准右边的订单量，整盘滑，让两张卡碰在一起。'});

const results = {
  23:'__IMG:merge-result-23__',35:'__IMG:merge-result-35__',57:'__IMG:merge-result-57__',
  72:'__IMG:merge-result-72__',84:'__IMG:merge-result-84__',90:'__IMG:merge-result-90__'
};
const pair = (tens,ones) => tens.flatMap(t=>ones.map(u=>['t'+t,'u'+u,t*10+u]));
const levels = [
  {
    board:[[null,null,null,null],['t2',null,'u3',null],[null,null,null,null],[null,null,null,null]],
    pairs:pair([2],[3]),targets:[23],seconds:.35,
    hints:['捆卡和散杆卡要碰在一起。','看看两张卡是不是在同一条滑道。']
  },
  {
    board:[['t3',null,'t5',null],[null,null,'u5',null],['u7',null,null,null],[null,null,null,null]],
    walls:[5],pairs:pair([3,5],[5,7]),targets:[35,57],seconds:.28,
    hints:['这两张能组成右边的订单吗？','再数有几捆和几根，试试换方向。']
  },
  {
    board:[[null,null,'t8','u0'],[null,null,null,null],['t7','t9','u4','u2'],[null,null,null,null]],
    walls:[6,7],pairs:pair([7,8,9],[0,2,4]),targets:[72,84,90],seconds:.22,
    hints:['空盘表示没有散根。再看看右边。','沿着空格换方向，让需要的两张碰头。']
  }
];
const merge=K.game(K.gameTemplates.slideMerge({
  voiceLead:true,doneText:'用几捆和几根合成了订单量。',
  art:{
    backdrop:'__IMG:merge-backdrop__',frames:['__IMG:squirrel-ready__','__IMG:squirrel-hop__'],sticker:'__IMG:rosette-sticker__',
    icons:{
      ...results,
      t2:'__IMG:merge-t-2__',t3:'__IMG:merge-t-3__',t5:'__IMG:merge-t-5__',
      t7:'__IMG:merge-t-7__',t8:'__IMG:merge-t-8__',t9:'__IMG:merge-t-9__',
      u0:'__IMG:merge-u-0__',u2:'__IMG:merge-u-2__',u3:'__IMG:merge-u-3__',
      u4:'__IMG:merge-u-4__',u5:'__IMG:merge-u-5__',u7:'__IMG:merge-u-7__'
    }
  },
  cues:[
    {goal:'merge-one',hint:'merge-hint',hint2:'merge-help',praise:'merge-praise'},
    {goal:'merge-two',hint:'merge-hint',hint2:'merge-help',praise:'merge-praise'},
    {goal:'merge-zero',hint:'merge-hint',hint2:'merge-help',praise:'merge-praise'}
  ],
  levels
}));
const orders=K.$('#merge-order-strip');
const orderImages=[...orders.querySelectorAll('img')];
merge.follow(orders, game => {
  const targets=levels[game.level].targets;
  orderImages.forEach((image,i)=>{
    image.hidden=i>=targets.length;
    if (targets[i] && image.getAttribute('src')!==results[targets[i]]) image.setAttribute('src',results[targets[i]]);
  });
  return {x:21,y:126,w:240,h:15+targets.length*66};
});
merge.follow('#first-bundle', () => ({x:318,y:236,w:88,h:80}));
merge.follow('#first-singles', () => ({x:526,y:236,w:88,h:80}));
merge.follow('#first-result', () => ({x:824,y:191,w:96,h:78}));
