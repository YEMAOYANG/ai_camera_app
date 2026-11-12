K.ready({title: '放大镜巡游', sub: '按住观察镜，顺着鱼从头看到尾。'});

const white = {image: '__IMG:fish-white__', fallback: '白底橙斑金鱼'};
const orange = {image: '__IMG:fish-orange__', fallback: '橙色金鱼'};
const carp = {image: '__IMG:fish-carp__', fallback: '灰色鲤鱼'};
const imageBox = [640, 460, 800, 450];

K.game(K.gameTemplates.trace({
  doneText: '先看整条，再看头、躯干和尾。',
  levels: [
    {
      name: '认路',
      demoRounds: [{
        goal: white, background: white, imageBox, vehicle: 'lens',
        strokes: [[[400, 454], [550, 445], [670, 451], [860, 452]]],
        hint: '先把镜头放回刚才的位置。', hint2: '沿鱼身慢慢移，别跳过中间。',
        success: '从头看到尾，没有漏过中间！'
      }],
      rounds: [{
        goal: orange, background: orange, imageBox, vehicle: 'lens',
        strokes: [[[394, 458], [510, 447], [651, 445], [796, 453], [872, 449]]],
        hint: '松开手，找到镜头的位置。', hint2: '让镜头沿鱼身一点一点地走。',
        success: '看到了整条鱼的细节！'
      }]
    },
    {
      name: '鱼转身了',
      rounds: [{
        goal: white, background: white, imageBox, vehicle: 'lens',
        mirrorImage: true, showRoute: false,
        strokes: [[[879, 450], [758, 448], [639, 448], [473, 450], [405, 452]]],
        hint: '找一找眼睛和嘴朝着哪边。', hint2: '先经过有鳞的鱼身，再到尾端。',
        success: '转身了，也能从头找到尾。'
      }]
    },
    {
      name: '换条鱼也会看',
      rounds: [{
        goal: carp, background: carp, imageBox, vehicle: 'lens', showRoute: false,
        strokes: [
          [[362, 466], [484, 467], [644, 457]],
          [[644, 457], [766, 457], [884, 453], [916, 446]]
        ],
        hint: '眼睛跟着镜头，看现在到哪了。', hint2: '看清鱼身再松手，接着往尾端看。',
        success: '换了鲤鱼，也找到了三部分。'
      }, {
        goal: orange, background: orange, imageBox, vehicle: 'lens',
        mirrorImage: true, showRoute: false,
        strokes: [
          [[886, 458], [770, 447], [629, 445]],
          [[629, 445], [484, 453], [407, 449]]
        ],
        hint: '看看这一回，鱼的头朝哪边。', hint2: '越过鳞片，再去找后面的大鳍。',
        success: '朝向变了，观察顺序没变。'
      }]
    }
  ]
}));
