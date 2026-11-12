K.ready({title:'小棒装箱',sub:'左右挪一挪，让合起来是十根的小棒挨在一起。'});

const bundlePhoto = new Image();
bundlePhoto.src = '__IMG:game-bundle__';
const crate = K.$('#bundle-crate');
const packing = K.gameTemplates.fallingTiles({
  art:{backdrop:'__IMG:arcade-kiln__', sticker:'__IMG:arcade-sticker__', icons:{
    1:'__IMG:game-rods-1__', 2:'__IMG:game-rods-2__', 3:'__IMG:game-rods-3__',
    4:'__IMG:game-rods-4__', 5:'__IMG:game-rods-5__', 6:'__IMG:game-rods-6__',
    7:'__IMG:game-rods-7__', 8:'__IMG:game-rods-8__', 9:'__IMG:game-rods-9__',
  }},
  doneText:'每捆十根，小棒收好啦！',
  levels:[
    {total:10, bottom:[4,null,null,7,null,2], pieces:[6,3], interval:1.36,
      hints:['落到旁边一格试试。','先数地上的小棒，再想还差几根。']},
    {total:10, bottom:[1,null,5,null,8,null], pieces:[2,9,5], interval:1.02,
      hints:['浅影子是小棒会落的地方。','数数两块小棒合在一起有几根。']},
    {total:10, bottom:[null,6,null,9,null,3], pieces:[7,4,1], interval:.74,
      hints:['别着急，先看它落在哪一格。','先认下面有几根，再找能补满十的。']},
  ],
  cues:Array.from({length:3},()=>({goal:'pack-goal',hint:'pack-hint',hint2:'pack-help',praise:'pack-done'})),
});

const drawPacking = packing.draw;
packing.draw = (game, canvas) => {
  drawPacking(game, canvas);
  if (!game.data.w) return;
  const box = (x,y,w,h,r,fill) => {
    K.draw.rr(canvas,x,y,w,h,r);canvas.fillStyle=fill;canvas.fill();
  };
  const done = game.data.progress;
  const capacity = game.data.level.pieces.length;
  if (done>Number(crate.dataset.bundles||0) && game.bubbleObj?.kind==='no') game.bubbleObj=null;
  if (crate.dataset.bundles!==String(done)) crate.dataset.bundles = String(done);
  box(44,165,320,390,26,'#2d4739');
  K.draw.text(canvas,'扎好的捆',204,211,32,'#fff4d8');
  for (let i=0; i<capacity; i++) {
    const y = 245 + i*96;
    box(78,y,252,80,15,i<done?'#f6d6a4':'#45614c');
    if (i>=done) continue;
    if (bundlePhoto.complete && bundlePhoto.naturalWidth) {
      const height = 124*bundlePhoto.naturalHeight/bundlePhoto.naturalWidth;
      canvas.drawImage(bundlePhoto,130,y+40-height/2,124,height);
    } else {
      for (let j=0;j<10;j++) box(123+j*14,y+12,10,56,4,'#376857');
      box(118,y+26,146,7,3,'#ab4e2f');
      box(118,y+52,146,7,3,'#ab4e2f');
    }
    K.draw.text(canvas,'10',294,y+40,31,'#4f3527');
  }
};

K.game(packing);
