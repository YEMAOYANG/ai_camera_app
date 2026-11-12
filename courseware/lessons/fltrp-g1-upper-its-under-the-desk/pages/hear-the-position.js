K.ready({title:'听位置，找对图',sub:'听完整一句，再让泡泡碰到对应的图。'});

const boat = K.game(K.gameTemplates.wordBubbles({
  voiceLead:true,
  stepVoiceLead:true,
  doneText:'听清了物品和它所在的位置。',
  art:{
    backdrop:'__IMG:pond-backdrop__',
    frames:['__IMG:boat-idle__','__IMG:boat-pop__'],
    sticker:'__IMG:sprout-sticker__',
    icons:{
      'clip-under-desk':'__IMG:clip-under-desk__', 'clip-on-desk':'__IMG:clip-on-desk__',
      'clip-in-bag':'__IMG:clip-in-bag__', 'clip-on-chair':'__IMG:clip-on-chair__',
      'clip-beside-bag':'__IMG:clip-beside-bag__', 'clip-under-chair':'__IMG:clip-under-chair__',
      'book-on-desk':'__IMG:book-on-desk__', 'book-under-desk':'__IMG:book-under-desk__',
      'pencil-under-desk':'__IMG:pencil-under-desk__', 'pencil-on-desk':'__IMG:pencil-on-desk__',
      'pencil-in-box':'__IMG:pencil-in-box__', 'book-in-box':'__IMG:book-in-box__'
    }
  },
  cues:[
    {goal:'clip-under-desk',hint:'bubble-hint',hint2:'bubble-help',praise:'bubble-praise',
      steps:['clip-under-desk','clip-on-desk']},
    {goal:'clip-in-bag',hint:'bubble-hint',hint2:'bubble-help',praise:'bubble-praise',
      steps:['clip-in-bag','clip-on-chair','clip-under-chair']},
    {goal:'book-under-desk',hint:'bubble-hint',hint2:'bubble-help',praise:'bubble-praise',
      steps:['book-under-desk','pencil-on-desk','pencil-in-box','book-in-box']}
  ],
  levels:[
    {
      rounds:[
        {target:'clip-under-desk',cards:['clip-under-desk','clip-on-desk']},
        {target:'clip-on-desk',cards:['clip-under-desk','clip-on-desk']}
      ],
      drift:0,pace:.53,tolerance:61,
      hints:['听是在桌面上，还是桌下。','重听一句，再找夹子碰没碰桌面。']
    },
    {
      rounds:[
        {target:'clip-in-bag',cards:['clip-in-bag','clip-on-chair','clip-beside-bag']},
        {target:'clip-on-chair',cards:['clip-in-bag','clip-on-chair','clip-under-chair']},
        {target:'clip-under-chair',cards:['clip-under-chair','clip-on-chair','clip-beside-bag']}
      ],
      drift:18,pace:.69,tolerance:57,
      hints:['先找袋子或椅子，再看夹子。','看边缘。夹子在里面，还是在外面？']
    },
    {
      rounds:[
        {target:'book-under-desk',cards:['book-on-desk','pencil-on-desk','book-under-desk']},
        {target:'pencil-on-desk',cards:['pencil-under-desk','pencil-on-desk','book-under-desk']},
        {target:'pencil-in-box',cards:['pencil-in-box','pencil-on-desk','book-in-box']},
        {target:'book-in-box',cards:['pencil-in-box','book-in-box','book-on-desk']}
      ],
      drift:26,pace:.9,tolerance:54,
      hints:['听清在找书，还是铅笔。','听清物品，再看桌面、桌下或盒里。']
    }
  ]
}));
boat.follow('#first-bubble', () => ({x:429,y:191,w:112,h:118}));
