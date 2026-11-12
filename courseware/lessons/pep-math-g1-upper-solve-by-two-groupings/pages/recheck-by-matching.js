K.ready({title:'对照原来一架盆栽', sub:'看左边原图，找每盆恰好出现一次的分组。'});

const rack = K.$('#source-rack');
const checkedGroup = K.$('#checked-group');
const rackPictures = ['__IMG:rack-a__', '__IMG:rack-b__', '__IMG:rack-c__'];
const targetPictures = {
  'a-tag': '__IMG:target-a-tag__', 'a-repeat': '__IMG:target-a-repeat__',
  'a-omit': '__IMG:target-a-omit__',
  'b-row': '__IMG:target-b-row__', 'b-tag': '__IMG:target-b-tag__',
  'b-mix': '__IMG:target-b-mix__',
  'c-row': '__IMG:target-c-row__', 'c-tag': '__IMG:target-c-tag__',
  'c-repeat': '__IMG:target-c-repeat__', 'c-extra': '__IMG:target-c-extra__'
};
const matcher = K.game(K.gameTemplates.magnetMarbles({
  voiceLead: true,
  doneText: '找到了完整分组，每盆都数到一次！',
  art: {
    backdrop: '__IMG:match-backdrop__',
    frames: ['__IMG:seed-marble__'],
    sticker: '__IMG:exhibit-sticker__',
    icons: targetPictures
  },
  cues: [
    {goal:'match-once',hint:'match-hint',hint2:'match-help',praise:'match-praise'},
    {goal:'match-two-views',hint:'match-hint',hint2:'match-help',praise:'match-praise'},
    {goal:'match-same-count',hint:'match-hint',hint2:'match-help',praise:'match-praise'}
  ],
  levels: [
    {
      listenOnly:true, targetWidth:192, targetHeight:128, speed:390, drift:0,
      queue:['whole-a'],
      targets:[{x:420,value:'a-tag'},{x:640,value:'a-repeat'},{x:861,value:'a-omit'}],
      pairs:[['whole-a','a-tag']],
      hints:['一盆一盆和左边对照。', '看看哪个分组没有重数，也没有漏数。']
    },
    {
      listenOnly:true, targetWidth:192, targetHeight:128, speed:455, drift:7,
      queue:['whole-b','whole-b'],
      targets:[{x:420,value:'b-mix'},{x:640,value:'b-row'},{x:861,value:'b-tag'}],
      pairs:[['whole-b','b-row'],['whole-b','b-tag']],
      hints:['每张图只用一种分法。', '刚才命中过的分组已经收好，再找另一张。']
    },
    {
      listenOnly:true, targetWidth:176, targetHeight:128, speed:515, drift:10,
      queue:['whole-c','whole-c'],
      targets:[{x:340,value:'c-row'},{x:540,value:'c-repeat'},{x:740,value:'c-tag'},{x:940,value:'c-extra'}],
      pairs:[['whole-c','c-row'],['whole-c','c-tag']],
      hints:['数目一样也要看看是哪些盆。', '用左边每一盆核对一次。']
    }
  ]
}));
matcher.follow('#source-rack', game => {
  const picture = rackPictures[game.level];
  if (rack.getAttribute('src') !== picture) rack.setAttribute('src', picture);
  return {x:15,y:151,w:196,h:214};
});
matcher.follow('#target-area', () => ({x:321,y:157,w:640,h:143}));
matcher.follow('#checked-group', game => {
  const selected = game.data.w?.locked?.value;
  checkedGroup.hidden = !selected;
  if (selected && checkedGroup.getAttribute('src') !== targetPictures[selected]) {
    checkedGroup.setAttribute('src', targetPictures[selected]);
  }
  return {x:15,y:395,w:196,h:120};
});
