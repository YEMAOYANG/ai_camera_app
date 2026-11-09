const IMAGES = {"owner-left": "__IMG:owner-left__", "owner-right": "__IMG:owner-right__", "ruler-star": "__IMG:ruler-star__", "ruler-circle": "__IMG:ruler-circle__"};
const CLIPS = {"my-ruler": "__CLIP:my-ruler__", "owner-hint": "__CLIP:owner-hint__"};
let audio = null;
let failedImage = false;
function picture(key, label = key) {
  const image = document.createElement('img');
  image.alt = label;
  image.draggable = false;
  image.onerror = function () {
    if (failedImage) return;
    failedImage = true;
    stopSound();
    const alert = K.el('div', 'load-failed', null, K.stage());
    K.el('div', '', '图片暂时打不开', alert);
    const retry = K.el('button', 'btn', '重新加载', alert);
    retry.onclick = () => location.reload();
  };
  image.src = IMAGES[key];
  return image;
}
function stopSound() {
  if (audio) audio.pause();
  audio = null;
}
function speak(key) {
  stopSound();
  if (failedImage || !CLIPS[key] || CLIPS[key].startsWith('__CLIP:')) return;
  audio = new Audio(CLIPS[key]);
  audio.play().catch(() => K.say('请按播放键再听。', 'no'));
}
function button(parent, id, label, css = 'tile') {
  const control = K.el('button', css, '', parent);
  control.id = id;
  control.setAttribute('aria-label', label);
  return control;
}
function resetHud() {
  stopSound();
  K.stars = 0;
  K.$('#star-n').textContent = '0';
  K.$$('.teach-hl').forEach(element => element.classList.remove('teach-hl'));
}
window.addEventListener('pagehide', stopSound);
window.addEventListener('message', e => {
  if (e.data && e.data.type === 'SET_WIDGET_STATE') stopSound();
});
const rounds = ['right', 'left'];
const ruler = { left:'ruler-star', right:'ruler-circle' };
const tray = K.$('#return-tray');
const owners = {};
let round = 0;
let selected = null;
let busy = false;
let timer = 0;
for (const side of ['left','right']) {
  const card = K.el('div','owner-card',null,K.$('#return-owners'));
  card.id = 'owner-' + side;
  card.appendChild(picture('owner-' + side));
  card.appendChild(picture(ruler[side]));
  owners[side] = card;
}
function markSpeaker(side) {
  for (const [name, card] of Object.entries(owners)) {
    card.classList.toggle('is-speaking', name === side);
  }
}
function renderReturn() {
  selected = null;
  busy = false;
  tray.replaceChildren();
  markSpeaker(rounds[round]);
  K.$$('#return-items button').forEach(control => control.classList.remove('is-selected'));
  K.$('#return-board').dataset.round = String(round);
  K.levels(rounds.length,round);
  K.say('看谁在说，再还给本人。');
}
function resetReturn() {
  clearTimeout(timer);
  resetHud();
  round = 0;
  renderReturn();
}
function give(key) {
  if (busy || !key || failedImage) return;
  if (key !== ruler[rounds[round]]) {
    K.shake(tray);
    K.sfx.no();
    speak('owner-hint');
    K.say('看看正在说话的人。', 'no');
    return;
  }
  busy = true;
  tray.replaceChildren(picture(key));
  K.star(1,tray);
  K.sfx.ok();
  K.say('还到了说话人的托盘。','ok');
  timer = setTimeout(() => {
    round++;
    if (round === rounds.length) {
      stopSound();
      K.levels(rounds.length,round);
      K.finish({ title:'都归还了', sub:'My 指说话的人自己。', again:resetReturn });
    } else {
      renderReturn();
      speak('my-ruler');
    }
  },900);
}
for (const key of Object.values(ruler)) {
  const control = button(K.$('#return-items'),'return-' + key,key);
  control.appendChild(picture(key));
  control.onclick = () => {
    if (busy || failedImage) return;
    selected = key;
    K.$$('#return-items button').forEach(item => item.classList.toggle('is-selected',item === control));
  };
  K.drag(control,{ enabled:() => !busy && !failedImage, targets:() => [tray],
    onTap:() => control.click(), onDrop:(_,target) => { if (target) give(key); } });
}
tray.onclick = () => give(selected);
K.$('#return-repeat').onclick = () => speak('my-ruler');
K.hud({ title:'文具归还台', icon:'', levels:rounds.length });
K.owl();
K.ready({ title:'把文具还给说话的人', sub:'先看说话人，再找尺子。', emoji:'' });
K.onStart = resetReturn;
K.onState = state => {
  if (state.reset) resetReturn();
  if (state.demo === 'left') {
    resetReturn();
    markSpeaker('left');
    tray.replaceChildren(picture(ruler.left));
  }
};
renderReturn();
