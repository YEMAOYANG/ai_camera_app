K.ready({title:'落块接对子',sub:'看图找搭档，移到它旁边再落下。'});
K.$('#ready .card').prepend(K.$('#dui-pairs-cover').content.cloneNode(true));

const pairs = [
  ['flower','tree'], ['tree','flower'], ['bird','insect'], ['insect','bird'],
  ['rain','wind'], ['wind','rain'],
];
const hints = ['先看落下来的是哪张图。','从底下一排找和它意思配得上的图。'];
const cues = {goal:'pair-goal',hint:'pair-hint',hint2:'pair-help',praise:'pair-praise'};
const labels = {flower:'花',tree:'树',bird:'鸟',insect:'虫',rain:'雨',wind:'风'};

K.game(K.gameTemplates.fallingTiles({
  art:{
    backdrop:'__IMG:catch-scene__',sticker:'__IMG:duet__',
    icons:{flower:'__IMG:flower__',tree:'__IMG:tree__',bird:'__IMG:bird__',insect:'__IMG:insect__',
      rain:'__IMG:rain__',wind:'__IMG:wind__'},
  },
  voiceLead:true,
  cues:[cues,cues,cues],
  doneText:'图卡都接成对子啦！',
  levels:[
    {bottom:[null,'wind',null,null,'tree',null],pieces:['flower'],interval:1.60,pairs,hints,labels},
    {bottom:[null,'insect',null,null,'flower','rain'],pieces:['bird','tree'],interval:1.20,pairs,hints,labels},
    {bottom:[null,'wind',null,'bird',null,'tree'],pieces:['rain','insect','flower'],interval:.90,pairs,hints,labels},
  ],
}));

const setTeacherState = K.onState;
K.onState = (state, content) => {
  setTeacherState(state, content);
  if (state.demo === false) {
    for (const anchor of K.$$('.teach-hl')) anchor.classList.remove('teach-hl');
  }
};
