const config = {
  title: '跳上下一张故事牌',
  sub: '听这一幕的线索，跑跳到该去的故事台。',
  doneText: '故事画面按先后排好了。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:hop-backdrop__',
    sticker: '__IMG:meeting-sticker__',
    frames: ['__IMG:bear-ready__','__IMG:bear-run__','__IMG:bear-jump__'],
    icons: {
      scroll:'__IMG:story-scroll__', A:'__IMG:hop-tiger-icon__', B:'__IMG:hop-first-icon__',
      C:'__IMG:hop-fox-icon__', D:'__IMG:hop-day-icon__', E:'__IMG:hop-wolf-icon__',
      F:'__IMG:hop-eight-icon__', G:'__IMG:hop-deer-icon__', H:'__IMG:hop-plaza-icon__', I:'__IMG:hop-final-icon__'
    }
  },
  levels: [
    {
      speed: 282, route: ['A','B','C'],
      platforms: [[146,486,112,'start'],[44,484,82,'E'],[315,487,112,'A'],
        [497,473,106,'B'],[679,490,110,'C'],[855,499,89,'I']],
      hints: ['想想谁先把通知任务交了出去。','落在亮起来的台上。']
    },
    {
      speed: 296, route: ['C','D','E'],
      platforms: [[104,501,125,'start'],[285,472,106,'C'],[467,488,104,'D'],
        [644,463,103,'E'],[815,509,90,'G'],[972,457,90,'I']],
      hints: ['想想狐狸问完后，先补了什么。','接亮起来的这一幕。']
    },
    {
      speed: 314, route: ['F','G','H','I'],
      platforms: [[89,507,124,'start'],[272,468,99,'F'],[451,496,99,'G'],
        [627,454,98,'H'],[817,491,101,'I'],[1002,447,93,'D']],
      hints: ['再听一遍下一幕的线索。','可以从台边往亮起来的台跳。']
    }
  ].map(level => ({...level, prompt:'scroll'})),
  cues: [
    ['hop-tiger','hop-first','hop-fox'],
    ['hop-fox','hop-day','hop-wolf'],
    ['hop-eight','hop-deer','hop-plaza','hop-final']
  ].map(steps => ({steps,goal:steps[0],hint:'hop-hint',hint2:'hop-help',praise:'hop-praise'}))
};

K.ready({title:config.title,sub:config.sub});
K.stage().append(K.$('#meeting-hop-listen'),K.$('#meeting-first-platform'));
const activity=K.gameTemplates.platformHop(config);
activity.onState=(_,state)=>{
  if(state.demo===false) K.$$('.teach-hl',K.stage()).forEach(anchor=>anchor.classList.remove('teach-hl'));
};
K.game(activity);
