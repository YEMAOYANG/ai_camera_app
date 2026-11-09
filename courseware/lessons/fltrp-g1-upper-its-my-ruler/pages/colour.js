const IMAGES = {"schoolbag-neutral": "__IMG:schoolbag-neutral__", "schoolbag-blue": "__IMG:schoolbag-blue__", "pencil-neutral": "__IMG:pencil-neutral__", "pencil-yellow": "__IMG:pencil-yellow__"};
const CLIPS = {"colour-pencil": "__CLIP:colour-pencil__", "colour-bag": "__CLIP:colour-bag__", "colour-hint": "__CLIP:colour-hint__"};
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
const rounds = [
  { object:'schoolbag', colour:'blue', sound:'colour-bag' },
  { object:'pencil', colour:'yellow', sound:'colour-pencil' }
];
const palette = { red:'#D94543', blue:'#2367C4', yellow:'#FFD648' };
const objects = {};
let round = 0;
let chosen = null;
let busy = false;
let timer = 0;
for (const { object } of rounds) {
  const control = button(K.$('#colour-objects'),'colour-' + object,object,'tile object');
  control.onclick = () => paintObject(object);
  objects[object] = control;
}
for (const [colour,value] of Object.entries(palette)) {
  const control = button(K.$('#colour-palette'),'colour-chip-' + colour,colour,'tile swatch');
  control.style.backgroundColor = value;
  control.onclick = () => {
    if (busy || failedImage) return;
    chosen = colour;
    K.$$('#colour-palette button').forEach(item => item.classList.toggle('is-selected',item === control));
    K.say('现在把颜料放到文具上。');
  };
}
function showObject(object,colour) {
  objects[object].replaceChildren(picture(object + '-' + colour));
  objects[object].dataset.colour = colour;
}
function renderColour() {
  chosen = null;
  busy = false;
  for (const object of Object.keys(objects)) showObject(object,'neutral');
  K.$$('#colour-palette button').forEach(item => item.classList.remove('is-selected'));
  K.$('#colour-board').dataset.round = String(round);
  K.levels(rounds.length,round);
  K.say('听物品和颜色。');
}
function resetColour() {
  clearTimeout(timer);
  resetHud();
  round = 0;
  renderColour();
}
function paintObject(object) {
  if (busy || !chosen || failedImage) return;
  const target = rounds[round];
  if (target.object !== object || target.colour !== chosen) {
    K.shake(objects[object]);
    K.sfx.no();
    speak('colour-hint');
    K.say('物品和颜色都要听清。','no');
    return;
  }
  busy = true;
  showObject(object,chosen);
  K.star(1,objects[object]);
  K.sfx.ok();
  K.say('这件文具上好色了。','ok');
  timer = setTimeout(() => {
    round++;
    if (round === rounds.length) {
      stopSound();
      K.levels(rounds.length,round);
      K.finish({ title:'文具上色完成', sub:'物品和颜色，两条线索。', again:resetColour });
    } else {
      renderColour();
      speak(rounds[round].sound);
    }
  },900);
}
K.$('#colour-repeat').onclick = () => { if (rounds[round]) speak(rounds[round].sound); };
K.hud({ title:'听音上色', icon:'', levels:rounds.length });
K.owl();
K.ready({ title:'听颜色给文具上色', sub:'先选颜料，再放到文具上。', emoji:'' });
K.onStart = resetColour;
K.onState = state => {
  if (state.reset) resetColour();
  if (state.demo === 'pencil') {
    resetColour();
    showObject('pencil','yellow');
  }
};
renderColour();
