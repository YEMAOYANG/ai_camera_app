const labels = {drop:'小水珠', fly:'小蜻蜓', frog:'小青蛙', fish:'小鱼儿',
  cradle:'摇篮', pad:'停机坪', stage:'歌台', shade:'凉伞'};
const config = {
  title:'把角色牌推到展位',
  sub:'先想它把荷叶当成什么，再把牌推到对应的图旁。',
  doneText:'四张角色展签都归好啦。',
  voiceLead:true,
  art:{
    sticker:'__IMG:lotus-sticker__',
    frames:['__IMG:pond-cart__','__IMG:pond-cart-flag__'],
    icons:{
      drop:'__IMG:drop-icon__',fly:'__IMG:fly-icon__',frog:'__IMG:frog-icon__',fish:'__IMG:fish-icon__',
      cradle:'__IMG:cradle-icon__',pad:'__IMG:pad-icon__',stage:'__IMG:stage-icon__',shade:'__IMG:shade-icon__'
    }
  },
  levels:[
    {
      labels,map:['########','#......#','#.S....#','#......#','########'],
      items:[{x:3,y:2,token:'drop',group:'cradle'},{x:3,y:3,token:'frog',group:'stage'}],
      docks:[{x:5,y:2,sample:'cradle',group:'cradle'},{x:5,y:3,sample:'stage',group:'stage'}],
      step:.30,
      hints:['想想这位朋友在荷叶上做了什么。','看一眼发亮的位置，再慢慢推过去。']
    },
    {
      labels,map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],
      items:[{x:4,y:2,token:'fly',group:'pad'},{x:4,y:4,token:'fish',group:'shade'},{x:3,y:3,token:'frog',group:'stage'}],
      docks:[{x:6,y:2,sample:'pad',group:'pad'},{x:6,y:3,sample:'stage',group:'stage'},{x:7,y:4,sample:'shade',group:'shade'}],
      step:.25,
      hints:['可以先看角色动作，再找展位。','想好站哪一边，小车才推得到。']
    },
    {
      labels,map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],
      items:[{x:4,y:3,token:'drop',group:'cradle'},{x:7,y:4,token:'fish',group:'shade'},
        {x:5,y:2,token:'fly',group:'pad'},{x:4,y:5,token:'frog',group:'stage'}],
      docks:[{x:8,y:4,sample:'shade',group:'shade'},{x:5,y:1,sample:'pad',group:'pad'},
        {x:8,y:2,sample:'cradle',group:'cradle'},{x:7,y:5,sample:'stage',group:'stage'}],
      step:.21,
      hints:['看清要推哪张牌，给转弯留点空。','可以退一步，再把牌推到亮着的位置。']
    }
  ],
  cues:Array.from({length:3},()=>({goal:'sort-goal',hint:'sort-hint',hint2:'sort-help',praise:'sort-praise'}))
};

K.ready({title:config.title,sub:config.sub});
K.stage().append(K.$('#lotus-first-role'),K.$('#lotus-first-cradle'));
const activity = K.gameTemplates.sortingDepot(config);
activity.onState = (_,state) => {
  if (state.demo === false) {
    K.$$('.teach-hl',K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
  }
};
K.game(activity);
