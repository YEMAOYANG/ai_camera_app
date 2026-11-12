const config = {
  title: '跑一跑跳一跳，接好故事',
  sub: '先听这一幕，再看合适的故事台。',
  doneText: '从墙角到回家，借尾巴的故事接好了。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop:'__IMG:gecko-hop-backdrop__',
    sticker:'__IMG:gecko-sticker__',
    frames:['__IMG:gecko-ready__','__IMG:gecko-run__','__IMG:gecko-jump__'],
    icons:{
      scroll:'__IMG:gecko-scroll__',A:'__IMG:hop-escape-icon__',B:'__IMG:hop-fish-icon__',
      C:'__IMG:hop-cow-icon__',D:'__IMG:hop-swallow-icon__',E:'__IMG:hop-home-icon__',
      F:'__IMG:hop-mother-icon__',G:'__IMG:hop-tail-icon__'
    }
  },
  levels:[
    {
      speed:279,route:['A','B','C'],
      platforms:[[146,486,112,'start'],[44,484,82,'E'],[315,487,112,'A'],
        [497,473,106,'B'],[679,490,110,'C'],[855,499,89,'G']]
    },
    {
      speed:294,route:['C','D','E'],
      platforms:[[104,501,125,'start'],[285,472,106,'C'],[467,488,104,'D'],
        [644,463,103,'E'],[815,509,90,'F'],[972,457,90,'G']]
    },
    {
      speed:311,route:['D','E','F','G'],
      platforms:[[89,507,124,'start'],[272,468,99,'D'],[451,496,99,'E'],
        [627,454,98,'F'],[817,491,101,'G'],[1002,447,93,'B']]
    }
  ].map(level=>({...level,prompt:'scroll',hints:['先听下一幕发生什么。','从台边起跳，接亮起来的那张画。']})),
  cues:[
    ['hop-escape','hop-fish','hop-cow'],
    ['hop-cow','hop-swallow','hop-home'],
    ['hop-swallow','hop-home','hop-mother','hop-tail']
  ].map(steps=>({steps,goal:steps[0],hint:'hop-hint',hint2:'hop-help',praise:'hop-praise'}))
};

K.ready({title:config.title,sub:config.sub});
K.stage().append(K.$('#gecko-hop-listen'),K.$('#gecko-first-platform'));
const activity=K.gameTemplates.platformHop(config);
activity.onState=(_,state)=>{
  if(state.demo===false) K.$$('.teach-hl',K.stage()).forEach(anchor=>anchor.classList.remove('teach-hl'));
};
K.game(activity);
