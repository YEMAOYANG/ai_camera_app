const config = {
  title: '跳上下一张故事牌',
  sub: '听这一幕的线索，看图，再跑跳。',
  doneText: '从叶上的小虫讲到棉花姑娘笑起来了。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:hop-backdrop__',
    sticker: '__IMG:cotton-sticker__',
    frames: ['__IMG:cotton-child-ready__','__IMG:cotton-child-run__','__IMG:cotton-child-jump__'],
    icons: {
      scroll:'__IMG:scroll-cotton__', A:'__IMG:hop-aphids__', B:'__IMG:hop-swallow__',
      C:'__IMG:hop-woodpecker__', D:'__IMG:hop-frog__', E:'__IMG:hop-ladybug__',
      F:'__IMG:hop-spots__', G:'__IMG:hop-end__'
    }
  },
  levels: [
    {
      speed: 279, route: ['A','B','C'],
      platforms: [[146,486,112,'start'],[44,484,82,'E'],[315,487,112,'A'],
        [497,473,106,'B'],[679,490,110,'C'],[855,499,89,'G']]
    },
    {
      speed: 294, route: ['C','D','E'],
      platforms: [[104,501,125,'start'],[285,472,106,'C'],[467,488,104,'D'],
        [644,463,103,'E'],[815,509,90,'F'],[972,457,90,'G']]
    },
    {
      speed: 311, route: ['D','E','F','G'],
      platforms: [[89,507,124,'start'],[272,468,99,'D'],[451,496,99,'E'],
        [627,454,98,'F'],[817,491,101,'G'],[1002,447,93,'B']]
    }
  ].map(level => ({
    ...level, prompt:'scroll', hints:['重听，想想下一幕。','到台边起跳，接亮起来的画。']
  })),
  cues: [
    ['stage-hop-aphids','stage-hop-swallow','stage-hop-woodpecker'],
    ['stage-hop-woodpecker','stage-hop-frog','stage-hop-ladybug'],
    ['stage-hop-frog','stage-hop-ladybug','stage-hop-spots','stage-hop-end']
  ].map(steps => ({steps,goal:steps[0],hint:'stage-hop-hint',hint2:'stage-hop-help',praise:'stage-hop-praise'}))
};

K.ready({title:config.title,sub:config.sub});
K.stage().append(K.$('#cotton-hop-listen'),K.$('#cotton-first-platform'));
const activity=K.gameTemplates.platformHop(config);
activity.onState=(_,state)=>{
  if(state.demo===false) K.$$('.teach-hl',K.stage()).forEach(anchor=>anchor.classList.remove('teach-hl'));
};
K.game(activity);
