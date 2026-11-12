K.ready({title: '拉紧绳子画圆', sub: '按住笔尖，沿着圆边慢慢画。'});
K.hud({title: '拉紧绳子画圆', icon: '', levels: 3});
K.startPictureFallback = () => {
  const image = K.el('canvas','pic');
  image.width=560;image.height=315;
  const c=image.getContext('2d');
  c.fillStyle='#E4F0E8';
  c.fillRect(0,0,560,315);
  c.beginPath();c.arc(280,158,95,0,2*Math.PI);
  c.strokeStyle='#4A977F';c.lineWidth=8;c.stroke();
  c.beginPath();c.moveTo(280,158);c.lineTo(375,158);
  c.strokeStyle='#98664B';c.lineWidth=7;c.stroke();
  c.fillStyle='#2F846E';K.draw.circle(c,280,158,14);
  c.fillStyle='#F5AC52';K.draw.circle(c,375,158,14);
  return image;
};

const circleLevels = [
  {radius: 146, initial: 146, dash: [10, 8], name: '把圆线画合'},
  {radius: 188, initial: 121, dash: [10, 11], name: '换个大圆'},
  {radius: 119, initial: 174, dash: [7, 22], name: '再画个小圆'}
];
const center = {x: 783, y: 427};
const turn = 2 * Math.PI;
const gripRadius = 74;
const clamp = (n, a, b) => Math.max(a, Math.min(b, n));
const rimPoint = (r, angle) => ({x: center.x + r * Math.cos(angle), y: center.y + r * Math.sin(angle)});
const near = (a, b, gap) => Math.hypot(a.x - b.x, a.y - b.y) <= gap;
const region = (p, w) => ({x:p.x-w/2,y:p.y-w/2,w,h:w});
const pen = d => rimPoint(d.radius, d.sweep * d.direction);
const image = new Image();
image.src = '__IMG:round-lid__';

function circleHint(g, first, later) {
  if (g.data.hintDelay > 0) return;
  g.data.hintDelay = 1.8;
  g.say(g.levelMisses ? later : first, 'no', 2.3);
  g.miss();
  K.sfx.buzz();
}

function circleUpdate(g, dt) {
  const d = g.data;
  const cfg = circleLevels[g.level];
  d.hintDelay -= dt;
  const p = g.pointer;
  if (!p.down) {
    d.grip = null;
    d.blocked = false;
    return;
  }
  if (d.blocked) return;
  if (!d.grip) {
    const tip = pen(d);
    if (!near(p, tip, gripRadius)) {
      circleHint(g, '松开，看看笔停在哪里。', '从笔尖这里按住，沿圆边慢慢画。');
      d.blocked = true;
      return;
    }
    d.grip = {x: p.x - tip.x, y: p.y - tip.y};
    return;
  }
  const dx = p.x - d.grip.x - center.x;
  const dy = p.y - d.grip.y - center.y;
  if (!d.adjusted) {
    d.radius = clamp(dx, 98, 205);
    if (Math.abs(d.radius - cfg.radius) <= 14 && Math.abs(dy) <= 55) {
      d.radius = cfg.radius;
      d.adjusted = true;
      d.blocked = true;
      g.say('线长合适了！松手，再按笔尖绕。', 'ok', 2.4);
      K.sfx.pick();
    } else if (Math.abs(dy) > 70) {
      circleHint(g, '先看看笔尖离圆边多远。', '在起点推笔尖，对准虚线再绕。');
    }
    return;
  }
  const angle = Math.atan2(dy, dx);
  const previous = d.sweep * d.direction;
  const change = Math.atan2(Math.sin(angle - previous), Math.cos(angle - previous));
  if (Math.abs(Math.hypot(dx, dy) - cfg.radius) > 44 || Math.abs(change) > 0.74) {
    circleHint(g, '慢一点，看看笔和绳。', '回到笔尖，让绳拉直，再沿圆边走。');
    return;
  }
  if (d.sweep === 0 && Math.abs(change) > 0.035) d.direction = Math.sign(change);
  const progress = change * d.direction;
  if (progress <= 0) return;
  d.sweep = Math.min(turn, d.sweep + Math.min(progress, dt * 2.7));
  if (turn - d.sweep > 0.045) return;
  d.sweep = turn;
  g.say('从起点绕回来了，圆合上啦！', 'ok', 1.7);
  g.sparkle(pen(d).x, pen(d).y);
  g.win();
}

function circlePilot(g, dt) {
  const d = g.data;
  const cfg = circleLevels[g.level];
  const p = g.pointer;
  if (d.blocked) {
    p.down = false;
    return;
  }
  const tip = pen(d);
  const aim = !d.grip ? tip : d.adjusted
    ? rimPoint(d.radius, Math.min(turn, d.sweep + dt * 2.15 + 0.022) * (d.sweep ? d.direction : 1))
    : rimPoint(cfg.radius, 0);
  Object.assign(p, aim, {down: true, active: true});
}

function board(c,x,y,w,h,fill) {
  K.draw.rr(c,x,y,w,h,30);
  c.fillStyle=fill;
  c.fill();
}
function ring(c,r,start,end,color,width,dash=[]) {
  c.save();
  c.setLineDash(dash);
  c.beginPath();
  c.arc(center.x,center.y,r,start,end,end<start);
  c.strokeStyle=color;
  c.lineWidth=width;
  c.lineCap='round';
  c.stroke();
  c.restore();
}

K.game({
  levels: circleLevels.length,
  levelName: i => circleLevels[i].name,
  bannerTime: 0.85,
  winPause: 1.65,
  starsFor: g => g.autoLoop ? 0 : 3,
  winText: () => '把圆线画合了！',
  doneText: '定住一头，拉紧线，让笔绕一圈。',
  finishMark: '<img src="__IMG:round-lid__" alt="圆形盖子" style="width:120px;height:120px;object-fit:contain;border-radius:22px">',
  bubbleAt: () => ({x:642,y:151}),
  reset(g,i) {
    const cfg = circleLevels[i];
    g.pointer.down = false;
    g.data = {radius:cfg.initial,adjusted:cfg.initial===cfg.radius,direction:1,sweep:0,grip:null,blocked:false,hintDelay:0};
  },
  setup(g) {
    g.follow('#game-pivot', () => region(center,112));
    g.follow('#game-pen', () => region(g.data.radius ? pen(g.data) : rimPoint(circleLevels[0].radius,0),146));
    g.follow('#game-rim', () => region(rimPoint(circleLevels[g.level].radius, Math.PI/2),112));
  },
  autopilot: circlePilot,
  update: circleUpdate,
  draw(g,c) {
    const cfg = circleLevels[g.level];
    const d = g.data.radius ? g.data : {radius:cfg.initial,direction:1,sweep:0,adjusted:true};
    const p = pen(d);
    c.fillStyle='#E4F0E8';
    c.fillRect(0,0,1280,720);
    board(c,68,225,307,405,'#f9f6e6');
    board(c,405,194,798,471,'#fffcf0');
    if (image.complete && image.naturalWidth) {
      c.save();
      K.draw.rr(c,105,261,233,233,22);
      c.clip();
      c.drawImage(image,105,261,233,233);
      c.restore();
    } else {
      c.fillStyle='#84ad76';
      K.draw.circle(c,221,377,79);
      c.fillStyle='#bbdba1';
      K.draw.circle(c,221,377,67);
    }
    K.draw.text(c,'圆盖的边',222,551,29,'#456651');
    ring(c,cfg.radius,0,turn,'#88A99B',6,cfg.dash);
    if (d.sweep > 0) ring(c,cfg.radius,0,d.sweep*d.direction,'#127866',9);
    c.strokeStyle='#98664B';
    c.lineWidth=6;
    c.beginPath();
    c.moveTo(center.x,center.y);
    c.lineTo(p.x,p.y);
    c.stroke();
    c.fillStyle='#2F846E';
    K.draw.circle(c,center.x,center.y,18);
    c.fillStyle='#F8DC9D';
    K.draw.circle(c,center.x,center.y,7);
    const start = rimPoint(cfg.radius,0);
    c.strokeStyle='#4A977F';
    c.lineWidth=4;
    c.beginPath();
    c.arc(start.x,start.y,17,0,turn);
    c.stroke();
    c.save();
    c.translate(p.x,p.y);
    c.rotate(Math.PI/5);
    board(c,-12,-94,24,76,'#F5AC52');
    c.fillStyle='#c68b60';
    c.beginPath();
    c.moveTo(-11,-23);
    c.lineTo(11,-23);
    c.lineTo(0,0);
    c.fill();
    c.fillStyle='#33544E';
    K.draw.circle(c,0,0,5);
    c.restore();
    K.draw.text(c,d.adjusted?'按住笔尖，绕一圈':'先把笔尖推到虚线',788,644,27,'#365F52');
  }
});
