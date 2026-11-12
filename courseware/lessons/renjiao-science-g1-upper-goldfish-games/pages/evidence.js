K.ready({title: '整理飘过的观察卡', sub: '看上方这条鱼，划走不该放进记录的卡。'});

const orange = {image: '__IMG:fish-orange__', fallback: '橙色金鱼全身'};
const white = {image: '__IMG:fish-white__', fallback: '橙白金鱼全身'};
const carp = {image: '__IMG:fish-carp__', fallback: '灰色鲤鱼全身'};
const mouth = {image: '__IMG:mouth__', fallback: '鱼头的口'};
const scales = {image: '__IMG:scales__', fallback: '鱼身的鳞片'};
const tail = {image: '__IMG:tail__', fallback: '鱼尾末端的大鳍'};
const wings = {image: '__IMG:record-wings__', fallback: '画上了鸟翅膀的鱼'};
const legs = {image: '__IMG:record-legs__', fallback: '画上了脚的鱼'};

K.game(K.gameTemplates.slice({
  doneText: '记录里的每一样，都要有看到的证据。',
  levels: [
    {
      name: '辨认画错的细节',
      demoRounds: [{
        goal: white, options: [mouth, wings, white], matches: [1],
        hint: '想一想，哪张卡画了上面没有的部位？',
        hint2: '比一比鱼鳍和鸟的翅膀。',
        success: '画里多出来的部位划走了。'
      }],
      rounds: [{
        goal: orange, options: [orange, legs, scales], matches: [1],
        hint: '看看上面的鱼，再比一比卡片。',
        hint2: '找找画本在鱼身下面添了什么。',
        success: '留下的是实际能看见的。'
      }]
    },
    {
      name: '分清是哪条鱼',
      rounds: [{
        goal: orange, options: [scales, white, orange, wings], matches: [1, 3],
        hint: '局部可以留下，整条鱼要仔细比。',
        hint2: '看看整条鱼的颜色，再看画本多出的部分。',
        success: '看清了形状，也比了颜色。'
      }]
    },
    {
      name: '追查混进来的记录',
      rounds: [{
        goal: white, options: [mouth, orange, white, legs, tail], matches: [1, 3],
        hint: '看看上方的花纹，卡片别着急划。',
        hint2: '斑点和颜色得对得上，图画不能添脚。',
        success: '相似的两条鱼也没有弄混。'
      }, {
        goal: orange, options: [wings, tail, carp, orange, scales], matches: [0, 2],
        hint: '上方是哪条鱼？再看全身卡。',
        hint2: '比一比身形和颜色，画出来的部位也要核。',
        success: '观察卡整理好啦。'
      }]
    }
  ]
}));
