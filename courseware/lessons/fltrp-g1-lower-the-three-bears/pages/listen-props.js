K.ready({title:'听回答，给剧团送道具',sub:'听清楚喜欢哪件，再开车拿取和交付。'});
const startPicture = K.$('#ready .pic');
startPicture.addEventListener('error', () => { startPicture.src = '__IMG:puppet-stage__'; }, {once:true});

const hints = ['先停在岸边，重听说话的人和物品。','听到肯定再拿；也可以看一看亮起的图站。'];
const oneLane = [{row:2, speed:.78, spacing:5.4, phase:.4}];
const twoLanes = [{row:1, speed:.82, spacing:5.4, phase:.8},
  {row:3, speed:-.92, spacing:5.6, phase:2.1}];
const options = K.gameTemplates.listenDelivery({
  art:{
    backdrop:'__IMG:empty-theatre__', sticker:'__IMG:puppet-stage__',
    frames:['__IMG:cart__','__IMG:cart-angle__'],
    icons:{
      'mother-noodles':'__IMG:mother-noodles__', 'baby-noodles':'__IMG:baby-noodles__',
      'father-bed':'__IMG:father-bed__', 'mother-bed':'__IMG:mother-bed__', 'baby-bed':'__IMG:baby-bed__',
      father:'__IMG:father__', mother:'__IMG:mother__', baby:'__IMG:baby__', goldilocks:'__IMG:goldilocks__'
    }
  },
  voiceLead:true,
  stepVoiceLead:true,
  levels:[
    {pickup:[['mother-noodles',2],['baby-noodles',5]],drop:[['baby',2],['goldilocks',5]],
      orders:[['baby-noodles','goldilocks']], lanes:oneLane, step:.33, hints},
    {pickup:[['baby-bed',2],['mother-bed',6]],drop:[['goldilocks',2],['baby',6]],
      orders:[['baby-bed','goldilocks']], lanes:twoLanes, step:.30, hints},
    {pickup:[['father-bed',1],['baby-bed',4],['mother-noodles',7]],drop:[['mother',1],['goldilocks',4],['father',7]],
      orders:[['father-bed','father'],['mother-noodles','mother']], lanes:twoLanes, step:.24, hints}
  ],
  cues:[
    {goal:'delivery-goal',hint:'delivery-hint',hint2:'delivery-help',praise:'delivery-praise',steps:['pick-noodles','drop-noodles']},
    {goal:'delivery-goal',hint:'delivery-hint',hint2:'delivery-help',praise:'delivery-praise',steps:['pick-small-bed','drop-small-bed']},
    {goal:'delivery-goal',hint:'delivery-hint',hint2:'delivery-help',praise:'delivery-praise',steps:['pick-plaid-bed','drop-plaid-bed','pick-handles','drop-handles']}
  ],
  doneText:'道具都送给了说话的人。'
});
options.onState = (_game, state) => {
  if (state.pause === false || state.demo === false) {
    for (const anchor of K.$$('.teach-hl')) anchor.classList.remove('teach-hl');
  }
};
K.game(options);
