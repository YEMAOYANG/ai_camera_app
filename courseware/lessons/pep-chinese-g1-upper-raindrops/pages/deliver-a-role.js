const labels = {big:'大雨点儿', small:'小雨点儿', empty:'没有花草', plants:'有花有草'};
const config = {
  title: '给两位雨点送角色卡',
  sub: '先听要接谁，再把角色卡送到它选的地方。',
  doneText: '雨点儿的两处去向都找对啦。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    sticker: '__IMG:rain-mic__',
    frames: ['__IMG:rain-truck__', '__IMG:rain-truck-glow__', '__IMG:patrol-truck__'],
    icons: {
      big: '__IMG:drop-big__', small: '__IMG:drop-small__',
      empty: '__IMG:empty-station__', plants: '__IMG:green-station__'
    }
  },
  levels: [
    {
      labels, pickup:[['big',3],['small',6]], drop:[['empty',5],['plants',2]],
      orders:[['big','empty']], lanes:[{row:2,speed:.82,spacing:5.8,phase:0}],
      step:.34,
      hints:['重听口令，先分清自己在接谁。','看发亮的位置，等巡车过去再开。']
    },
    {
      labels, pickup:[['small',2],['big',6]], drop:[['plants',6],['empty',1]],
      orders:[['small','plants'],['big','empty']],
      lanes:[{row:1,speed:-1.16,spacing:4.7,phase:1.5},{row:3,speed:1.31,spacing:4.8,phase:.8}],
      step:.27,
      hints:['别只记上一关的左右，听清这一站。','看发亮的地方，等路空了再过。']
    },
    {
      labels, pickup:[['big',1],['small',7]], drop:[['empty',6],['plants',2]],
      orders:[['big','empty'],['small','plants'],['big','empty']],
      lanes:[
        {row:1,speed:-1.55,spacing:4.1,phase:.7},
        {row:2,speed:1.49,spacing:4.15,phase:1.4},
        {row:3,speed:-1.67,spacing:4.15,phase:2.1}
      ],
      step:.22,
      hints:['先辨角色，再看两处有没有花草。','停在安全的草地上，等前面的路让开。']
    }
  ],
  cues: [
    {goal:'pick-big', hint:'delivery-hint', hint2:'delivery-hint-again', praise:'delivery-praise',
      steps:['pick-big','send-empty']},
    {goal:'pick-small', hint:'delivery-hint', hint2:'delivery-hint-again', praise:'delivery-praise',
      steps:['pick-small','send-plants','pick-big','send-empty']},
    {goal:'pick-big', hint:'delivery-hint', hint2:'delivery-hint-again', praise:'delivery-praise',
      steps:['pick-big','send-empty','pick-small','send-plants','pick-big','send-empty']}
  ]
};

K.ready({title:config.title, sub:config.sub});
K.stage().append(K.$('#rain-first-pickup'), K.$('#rain-empty-destination'));
const activity = K.gameTemplates.listenDelivery(config);
activity.onState = (_, state) => {
  if (state.demo === false) {
    K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
  }
};
K.game(activity);
