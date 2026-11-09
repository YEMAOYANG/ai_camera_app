const IMAGES = {"pen": "__IMG:pen__", "eraser": "__IMG:eraser__", "pencil-case": "__IMG:pencil-case__"};
const CLIPS = {"ask": "__CLIP:ask__", "pen-answer": "__CLIP:pen-answer__", "eraser-answer": "__CLIP:eraser-answer__", "case-answer": "__CLIP:case-answer__"};
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
const canvas = K.$('#draw-canvas');
const brush = canvas.getContext('2d');
const next = K.$('#draw-next');
const samples = { pen:'pen-answer', eraser:'eraser-answer', 'pencil-case':'case-answer' };
let sample = null;
let drawing = false;
let marked = false;
let passed = false;
function clearCanvas() {
  brush.clearRect(0,0,canvas.width,canvas.height);
  marked = false;
}
function resetDraw() {
  resetHud();
  sample = null;
  drawing = false;
  passed = false;
  canvas.classList.remove('passed');
  clearCanvas();
  K.$$('#draw-cards button').forEach(item => item.classList.remove('is-selected'));
  K.levels(2,0);
  next.setAttribute('aria-label','传画给搭档');
  K.say('选一张图，再自由画。');
}
for (const key of Object.keys(samples)) {
  const card = button(K.$('#draw-cards'),'draw-card-' + key,key);
  card.appendChild(picture(key));
  card.onclick = () => {
    if (passed || failedImage) return;
    sample = key;
    K.$$('#draw-cards button').forEach(item => item.classList.toggle('is-selected',item === card));
    K.say('看看它的样子，再画一画。','ok');
  };
}
function coord(event) {
  const rect = canvas.getBoundingClientRect();
  return [(event.clientX - rect.left) * canvas.width / rect.width, (event.clientY - rect.top) * canvas.height / rect.height];
}
canvas.onpointerdown = event => {
  if (!sample || passed || failedImage) return;
  drawing = true;
  canvas.setPointerCapture(event.pointerId);
  brush.lineWidth = 8;
  brush.strokeStyle = '#376B66';
  brush.lineCap = 'round';
  brush.beginPath();
  brush.moveTo(...coord(event));
};
canvas.onpointermove = event => {
  if (!drawing) return;
  brush.lineTo(...coord(event));
  brush.stroke();
  marked = true;
};
canvas.onpointerup = canvas.onpointercancel = () => { drawing = false; };
K.$('#draw-clear').onclick = () => { if (!passed) clearCanvas(); };
K.$('#draw-repeat').onclick = () => speak(passed && sample ? samples[sample] : 'ask');
next.onclick = () => {
  if (failedImage || !sample || !marked) {
    K.say('先选一张图，并在画板上画一笔。','no');
    return;
  }
  if (!passed) {
    passed = true;
    canvas.classList.add('passed');
    K.levels(2,1);
    next.setAttribute('aria-label','完成轮流问答');
    speak('ask');
    K.say('请搭档看画，试着回答。','ok');
    return;
  }
  stopSound();
  K.levels(2,2);
  K.finish({ title:'画和问答准备好了', sub:'请大人听听你的回答。', again:resetDraw });
};
K.hud({ title:'画后问答', icon:'', levels:2 });
K.owl();
K.ready({ title:'画一画再问答', sub:'选图、画一画、交给搭档。', emoji:'' });
K.onStart = resetDraw;
K.onState = state => {
  if (state.reset) resetDraw();
  if (state.demo === 'eraser') {
    resetDraw();
    K.$('#draw-card-eraser').click();
    brush.strokeStyle = '#376B66';
    brush.lineWidth = 8;
    brush.strokeRect(220,105,200,104);
  }
};
