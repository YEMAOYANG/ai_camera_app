K.ready({title:'空杯试放台',sub:'把空杯移到垫子中间，试过再换。'});
K.hud({title:'空杯试放台',icon:'',levels:3});
K.startPictureFallback=()=>{
  const image=K.el('canvas','pic');
  image.width=560;image.height=315;
  const c=image.getContext('2d');
  const center={x:280,y:157};
  c.fillStyle='#E8F1E8';
  c.fillRect(0,0,560,315);
  disc(c,center,106,'#ACD4B3','#5e9a7a',6);
  cupTop(c,center);
  return image;
};

const tests = [
  {name:'杯底放不下',wide:false,flat:true},
  {name:'杯垫翘边了',wide:true,flat:false},
  {name:'仔细查两处',wide:false,flat:false}
];
const home = {x:378,y:441};
const bench = {x:718,y:367};
const cupRadius = 58;
const stock = {
  wide: {x:1080,y:337},
  flat: {x:1080,y:548}
};
const ref = new Image();
ref.src = '__IMG:wide-coaster__';
const distance = (a,b) => Math.hypot(a.x-b.x,a.y-b.y);
const box = (p,w,h=w) => ({x:p.x-w/2,y:p.y-h/2,w,h});
const radius = wide => wide ? 91 : 44;

function coverage(wide, offset) {
  return radius(wide) >= cupRadius + offset;
}

function plate(c,rect,fill,outline) {
  K.draw.rr(c,rect.x,rect.y,rect.w,rect.h,24);
  c.fillStyle=fill;
  c.fill();
  if (outline) {
    c.strokeStyle=outline;
    c.lineWidth=4;
    c.stroke();
  }
}
function disc(c,p,r,fill,outline,width=4) {
  c.beginPath();
  c.arc(p.x,p.y,r,0,2*Math.PI);
  c.fillStyle=fill;
  c.fill();
  if (outline) {
    c.strokeStyle=outline;
    c.lineWidth=width;
    c.stroke();
  }
}
function drawProfile(c,x,y,w,flat) {
  const lift = flat ? 0 : 25;
  c.beginPath();
  c.moveTo(x-w/2,y);
  c.lineTo(x+w/2-30,y);
  c.quadraticCurveTo(x+w/2-8,y,x+w/2,y-lift);
  c.lineTo(x+w/2,y-lift+9);
  c.quadraticCurveTo(x+w/2-12,y+9,x+w/2-30,y+9);
  c.lineTo(x-w/2,y+9);
  c.closePath();
  c.fillStyle=flat?'#8fbea2':'#efbc77';
  c.strokeStyle=flat?'#437f69':'#a36d45';
  c.lineWidth=4;
  c.fill();
  c.stroke();
}

function checkCup(g) {
  const d = g.data;
  const offset = distance(d,bench);
  const covers = coverage(d.wide,offset);
  d.observed=true;
  d.observation={covers,flat:d.flat};
  if (covers && d.flat) {
    g.say('杯底都垫住了，杯垫也放得平！','ok',1.7);
    g.sparkle(bench.x,bench.y);
    g.win();
    return;
  }
  d.returning=true;
  if (g.levelMisses === 0) g.say('看杯底四周，再看看垫边。','no',2.4);
  else if (!covers && !d.flat) g.say('看看伸出去的杯底和翘起的垫边。','no',2.4);
  else if (!covers) g.say('垫边要能绕在杯底的外面。','no',2.4);
  else g.say('侧面这一边翘起来了，再看看材料。','no',2.4);
  g.miss();
  K.sfx.buzz();
}

function cupUpdate(g,dt) {
  const d = g.data;
  const p = g.pointer;
  const tap = g.taps[0];
  const closeToHome = distance(d,home) <= 55;
  if (tap && closeToHome && d.observed) {
    for (const key of Object.keys(stock)) {
      if (Math.abs(tap.x-stock[key].x)<=88 && Math.abs(tap.y-stock[key].y)<=77) {
        d[key] = !d[key];
        d.observation = null;
        d.settle = 0;
        d.canTest = true;
        g.say('换好了，用同一只空杯再试。','ok',1.7);
        K.sfx.pick();
        return;
      }
    }
  }
  if (!p.down) {
    d.grip=null;
    if (d.returning && closeToHome) {
      d.returning=false;
      d.canTest=true;
      d.settle=0;
    }
  }
  else if (!d.grip && tap && distance(tap,d)<=82) {
    d.grip={x:p.x-d.x,y:p.y-d.y};
    d.observation=null;
    d.settle=0;
  }
  if (d.grip) {
    const tx=Math.max(330,Math.min(840,p.x-d.grip.x));
    const ty=Math.max(258,Math.min(490,p.y-d.grip.y));
    const mix=Math.min(1,dt*10);
    d.x+=(tx-d.x)*mix;
    d.y+=(ty-d.y)*mix;
    return;
  }
  if (d.returning || !d.canTest || distance(d,bench)>37) {
    d.settle=0;
    return;
  }
  // Settle the cup in the shallow test mark before taking a top and side reading.
  d.x+=(bench.x-d.x)*Math.min(1,dt*12);
  d.y+=(bench.y-d.y)*Math.min(1,dt*12);
  d.settle+=dt;
  if (d.settle<0.48) return;
  d.canTest=false;
  checkCup(g);
}

function press(g,p,down) {
  if (down && !g.pointer.down) g.taps.push({x:p.x,y:p.y});
  Object.assign(g.pointer,{x:p.x,y:p.y,down,active:true});
}
function cupPilot(g) {
  const d=g.data;
  const p=g.pointer;
  if (d.observed && distance(d,home)<=43 && (!d.wide || !d.flat) && !d.grip) {
    if (p.down) press(g,d,false);
    else press(g,stock[!d.wide?'wide':'flat'],true);
    return;
  }
  if (!d.returning && (!d.canTest || d.settle>0)) return;
  const target=d.returning?home:bench;
  if (d.grip) {
    press(g,target,distance(d,target)>7);
  } else if (distance(d,target)>8) {
    if (p.down) press(g,d,false);
    else press(g,d,true);
  }
}

function cupTop(c,d) {
  c.beginPath();
  c.arc(d.x+58,d.y,23,-1.45,1.45);
  c.strokeStyle='#52677D';
  c.lineWidth=10;
  c.stroke();
  disc(c,d,58,'#eef5f9','#52677D',7);
  disc(c,d,45,'#c4e0eb','#8cb0bd',3);
  if (d.observation && !d.observation.covers) {
    disc(c,d,cupRadius,'#f5b49b40','#cc714e',6);
    // The dotted outline shows the actual pad under the cup's footprint.
    c.save();
    c.setLineDash([8,5]);
    c.beginPath();
    c.arc(bench.x,bench.y,radius(d.wide),0,2*Math.PI);
    c.strokeStyle=d.flat?'#4a906f':'#ab824d';
    c.lineWidth=5;
    c.stroke();
    c.restore();
  }
}
function movementCue(c,returning) {
  c.save();
  c.translate(543,405);
  c.rotate(returning?Math.PI-0.21:-0.21);
  c.strokeStyle='#80a894';
  c.lineWidth=6;
  c.lineCap=c.lineJoin='round';
  c.beginPath();
  c.moveTo(-44,0);c.lineTo(44,0);
  c.moveTo(29,-13);c.lineTo(44,0);c.lineTo(29,13);
  c.stroke();
  c.restore();
}
function sideView(c,d) {
  const y=641;
  const x=674;
  const profileScale=1.15;
  const halfFootprint=cupRadius*profileScale;
  c.strokeStyle='#baa487';
  c.lineWidth=4;
  c.beginPath();c.moveTo(x-158,y+12);c.lineTo(x+160,y+12);c.stroke();
  drawProfile(c,x,y,radius(d.wide)*2*profileScale,d.flat);
  if (!d.observation) return;
  c.save();
  c.translate(x,y);
  c.beginPath();
  c.moveTo(-halfFootprint-7,-66);
  c.quadraticCurveTo(-halfFootprint-6,-32,-halfFootprint,-1);
  c.lineTo(halfFootprint,-1);
  c.quadraticCurveTo(halfFootprint+6,-36,halfFootprint+7,-66);
  c.closePath();
  c.fillStyle='#adcde385';
  c.strokeStyle='#52677D';
  c.lineWidth=4;
  c.fill();c.stroke();
  c.restore();
}

K.game({
  levels:tests.length,
  levelName:i=>tests[i].name,
  bannerTime:0.85,
  winPause:1.6,
  starsFor:g=>g.autoLoop?0:3,
  winText:()=>'杯底垫住了，垫子也平了。',
  doneText:'试一试，记下来，改好再试。',
  finishMark:'<img src="__IMG:wide-coaster__" alt="杯底完全落在圆杯垫上" style="width:120px;height:120px;object-fit:contain;border-radius:22px">',
  bubbleAt:()=>({x:675,y:150}),
  reset(g,i) {
    const {wide,flat}=tests[i];
    g.data={...home,wide,flat,grip:null,settle:0,canTest:true,observed:false,returning:false,observation:null};
    g.pointer.down=false;
  },
  setup(g) {
    g.follow('#game-cup',()=>box(g.data.x?g.data:home,150));
    g.follow('#game-mat',()=>box(bench,214));
    g.follow('#game-samples',()=>box({x:1080,y:443},200,387));
  },
  autopilot:cupPilot,
  update:cupUpdate,
  draw(g,c) {
    const d=g.data.x?g.data:{...home,...tests[0],observed:false};
    c.fillStyle='#E8F1E8';
    c.fillRect(0,0,1280,720);
    plate(c,{x:60,y:225,w:195,h:403},'#fffae8');
    plate(c,{x:278,y:205,w:637,h:473},'#fffdf0');
    plate(c,{x:940,y:205,w:286,h:473},'#f9f3dc');
    K.draw.text(c,'对照图',157,264,27,'#456651');
    if (ref.complete && ref.naturalWidth) {
      c.save();
      K.draw.rr(c,78,291,160,172,18);c.clip();
      c.drawImage(ref,78,291,160,172);
      c.restore();
    } else {
      disc(c,{x:156,y:370},69,'#a8c89b','#63866a');
      disc(c,{x:156,y:370},45,'#eee3b7','#63866a');
    }
    K.draw.text(c,'把杯底垫住',158,512,22,'#456651');
    K.draw.text(c,'空杯',home.x,541,25,'#456651');
    disc(c,home,75,'#E5F0EC','#b5cdc1',3);
    disc(c,bench,radius(d.wide),d.flat?'#ACD4B3':'#F2CB8D',d.flat?'#5e9a7a':'#bc8a56');
    disc(c,bench,7,'#6f9b83');
    if (g.state==='play' && !d.grip && (d.returning || distance(d,home)<=55)) movementCue(c,d.returning);
    cupTop(c,d);
    sideView(c,d);
    K.draw.text(c,'侧面看',453,640,26,'#456651');
    for (const key of Object.keys(stock)) {
      const p=stock[key];
      const enabled=d.observed&&distance(d,home)<=55;
      plate(c,box(p,176,154),enabled?'#fffef7':'#efe8cf',enabled?'#77a88a':'#ddd5b4');
      if (key==='wide') {
        disc(c,{x:p.x,y:p.y-14},radius(!d.wide)*0.58,'#b0d0a7','#759f80',4);
        K.draw.text(c,d.wide?'换小一点':'换大一点',p.x,p.y+54,24,'#456651');
      } else {
        drawProfile(c,p.x,p.y-3,126,!d.flat);
        K.draw.text(c,d.flat?'换张翘边的':'换张平整的',p.x,p.y+54,23,'#456651');
      }
    }
  }
});
