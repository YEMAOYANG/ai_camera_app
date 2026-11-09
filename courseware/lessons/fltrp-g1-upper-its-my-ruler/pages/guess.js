const IMAGES = {"book": "__IMG:book__", "desk": "__IMG:desk__", "chair": "__IMG:chair__", "schoolbag-neutral": "__IMG:schoolbag-neutral__"};
const CLIPS = {"ask": "__CLIP:ask__", "guess-hint": "__CLIP:guess-hint__", "book-answer": "__CLIP:book-answer__"};
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
const rounds = ['chair', 'desk', 'schoolbag-neutral'];
const choices = ['book', ...rounds];
const clue = K.$('#guess-clue');
const tray = K.$('#guess-tray');
let round = 0;
let active = false;
let timer = 0;
function showClue(key) { clue.replaceChildren(picture(key)); }
function paintRound() {
  clue.replaceChildren(K.el('span', '', '↗'));
  tray.replaceChildren();
  active = false;
  K.$('#guess-board').dataset.round = String(round);
  K.levels(rounds.length, round);
  K.say('打开线索窗，猜这是什么。');
}
function resetGuess() {
  clearTimeout(timer);
  resetHud();
  round = 0;
  paintRound();
}
function chooseGuess(key, card) {
  if (failedImage || !active) return;
  if (key !== rounds[round]) {
    K.shake(card);
    K.sfx.no();
    speak('guess-hint');
    K.say('再看露出来的部分。', 'no');
    return;
  }
  active = false;
  tray.replaceChildren(picture(key));
  K.star(1, tray);
  K.sfx.ok();
  K.say('物品放到展示台上了。', 'ok');
  timer = setTimeout(() => {
    round++;
    if (round === rounds.length) {
      stopSound();
      K.levels(rounds.length, round);
      K.finish({ title:'文具都找到了', sub:'打开线索，再选物品。', again:resetGuess });
    } else paintRound();
  }, 900);
}
for (const key of choices) {
  const card = button(K.$('#guess-choices'), 'guess-item-' + key, key);
  card.appendChild(picture(key));
  card.onclick = () => chooseGuess(key, card);
}
clue.onclick = () => {
  if (failedImage || round >= rounds.length || tray.childElementCount) return;
  showClue(rounds[round]);
  active = true;
  speak('ask');
};
K.$('#guess-repeat').onclick = () => speak('ask');
K.hud({ title:'看线索猜物', icon:'', levels:rounds.length });
K.owl();
K.ready({ title:'看线索猜物', sub:'先打开线索，再找图。', emoji:'' });
K.onStart = resetGuess;
K.onState = state => {
  if (state.reset) resetGuess();
  if (state.demo === 'book') {
    resetGuess();
    showClue('book');
    tray.replaceChildren(picture('book'));
  }
};
paintRound();
