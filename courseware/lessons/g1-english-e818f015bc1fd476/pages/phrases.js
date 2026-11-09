var IMAGES={"cat-black": "__IMG:cat-black__", "dog-white": "__IMG:dog-white__", "animal-panda": "__IMG:animal-panda__", "animal-bird": "__IMG:animal-bird__", "cat-yellow": "__IMG:cat-yellow__", "cat-green": "__IMG:cat-green__", "dog-red": "__IMG:dog-red__", "dog-green": "__IMG:dog-green__"};

var lessonAudio=null,assetFailed=false;
var CLIPS={"cat": "__CLIP:cat__", "dog": "__CLIP:dog__", "panda": "__CLIP:panda__", "bird": "__CLIP:bird__", "phrase-hint": "__CLIP:phrase-hint__", "phrase-color": "__CLIP:phrase-color__", "phrase-say": "__CLIP:phrase-say__", "red-dog": "__CLIP:red-dog__", "green-dog": "__CLIP:green-dog__"};
function listen(key){if(assetFailed)return;if(lessonAudio){lessonAudio.pause();lessonAudio.currentTime=0}var url=CLIPS[key];if(!url||url.indexOf('__CLIP:')===0){K.say('配音还没准备好，请稍后再试。','no');return}lessonAudio=new Audio(url);lessonAudio.play().catch(function(){K.say('请按再听按钮。')})}
window.addEventListener('pagehide', stopAudio);
window.addEventListener('message',function(e){if(e.data&&/^(SET_WIDGET_STATE|HIGHLIGHT_ELEMENT|ANNOTATE_ELEMENT|REVEAL_ELEMENT)$/.test(e.data.type)&&lessonAudio)lessonAudio.pause()});
function picture(key,alt){var im=document.createElement('img');im.src=IMAGES[key];im.alt=alt||'原创木制玩具图片';im.draggable=false;im.dataset.lessonPicture='true';return im}
function assetStop(){if(assetFailed)return;assetFailed=true;if(lessonAudio)lessonAudio.pause();var panel=K.el('div','asset-stop',null,K.stage());panel.id='asset-stop';K.el('div','','图片暂时没打开',panel);K.el('div','small-hint','请点大按钮，再试一次。',panel);var b=K.el('button','btn','重试图片',panel);b.id='asset-retry';b.onclick=function(){location.reload()}}
document.addEventListener('error',function(e){if(e.target&&e.target.tagName==='IMG')assetStop()},true);
var PALETTE={red:'#E23735',blue:'#2367CD',yellow:'#F4D323',green:'#269B55',black:'#272626',white:'#FFFFFF'};
function makeColors(parent,choose){Object.keys(PALETTE).forEach(function(c){var b=K.el('button','color-chip','',parent);b.id=parent.id+'-'+c;b.dataset.color=c;b.style.background=PALETTE[c];b.setAttribute('aria-label',c);b.onclick=function(){if(!assetFailed)choose(c,b)}})}
function stopAudio(){if(lessonAudio)lessonAudio.pause()}

const phraseCards = { cat: 'cat-black', dog: 'dog-white', panda: 'animal-panda', bird: 'animal-bird' };
const phrasePaint = { cat: { yellow: 'cat-yellow', green: 'cat-green' }, dog: { red: 'dog-red', green: 'dog-green' } };
const phraseRounds = ['panda', 'bird', 'cat', 'dog'];
const phraseOptions = K.$('#phrase-options');
const phraseFrame = K.$('#phrase-frame');
const phrasePalette = K.$('#phrase-palette');
const phraseNext = K.$('#phrase-next');
const phraseRepeat = K.$('#phrase-repeat');
let phraseIndex = 0;
let phraseAnimal = null;
let phraseWaiting = false;
let phraseWrong = 0;

function showPhraseAnimal(animal, color) {
  const painted = phrasePaint[animal] && phrasePaint[animal][color];
  phraseFrame.replaceChildren(picture(painted || phraseCards[animal], animal));
  if (color && !painted) {
    const swatch = K.el('span', 'paint-plan', '', phraseFrame);
    swatch.style.background = PALETTE[color];
    swatch.dataset.semanticDiagram = 'planned-color';
    swatch.setAttribute('aria-label', '想画的颜色');
  }
}
function phraseFinishColor(color) {
  if (!phraseAnimal || phraseWaiting || assetFailed) return;
  const animal = phraseAnimal;
  phraseWaiting = true;
  showPhraseAnimal(animal, color);
  K.star(1, phraseFrame);
  K.sfx.ok();
  K.say(phrasePaint[animal] ? '看成品，试着完整介绍。' : '看色卡，试着说你想画的玩具。', 'ok');
  phrasePalette.hidden = true;
  phraseRepeat.disabled = true;
  phraseNext.hidden = false;
  if (animal === 'dog' && (color === 'red' || color === 'green')) listen(color + '-dog');
  else listen('phrase-say');
}
phraseNext.onclick = function () {
  if (!phraseWaiting || assetFailed || phraseNext.disabled) return;
  phraseNext.disabled = true;
  const round = phraseIndex;
  const finishCurrent = function () {
    if (phraseIndex !== round || !phraseWaiting || !phraseNext.disabled) return;
    phraseNext.hidden = true;
    phraseIndex++;
    if (phraseIndex === phraseRounds.length) {
      K.levels(phraseRounds.length, phraseIndex);
      K.finish({ title: '展签都做好啦', sub: '可以把你的作品说给大人听。', again: phraseReset });
      return;
    }
    phraseRender();
    listen(phraseRounds[phraseIndex]);
  };
  const feedback = lessonAudio;
  if (feedback && !feedback.paused && !feedback.ended) {
    feedback.addEventListener('ended', finishCurrent, { once: true });
    feedback.addEventListener('error', finishCurrent, { once: true });
    return;
  }
  finishCurrent();
};
function pickPhraseAnimal(animal, card) {
  if (assetFailed || phraseWaiting || phraseAnimal) return;
  if (animal !== phraseRounds[phraseIndex]) {
    phraseWrong++;
    K.shake(card);
    K.sfx.no();
    listen('phrase-hint');
    K.say(phraseWrong === 1 ? '再听名字，看看卡片上的动物。' : '先听一个动物的名字，再选图卡。', 'no');
    return;
  }
  phraseAnimal = animal;
  card.classList.add('is-chosen');
  showPhraseAnimal(animal);
  phrasePalette.hidden = false;
  phrasePalette.replaceChildren();
  const colors = phrasePaint[animal] ? Object.keys(phrasePaint[animal]) : ['red', 'green', 'blue', 'yellow'];
  colors.forEach(function (color) {
    const button = K.el('button', 'color-chip', '', phrasePalette);
    button.id = 'phrase-palette-' + color;
    button.dataset.color = color;
    button.style.background = PALETTE[color];
    button.setAttribute('aria-label', color);
    button.onclick = () => phraseFinishColor(color);
  });
  K.say('接着选一块颜色。');
  listen('phrase-color');
}
function phraseRender() {
  phraseAnimal = null;
  phraseWaiting = false;
  phraseWrong = 0;
  phrasePalette.hidden = true;
  phraseNext.hidden = true;
  phraseNext.disabled = false;
  phraseRepeat.disabled = false;
  phrasePalette.replaceChildren();
  phraseFrame.replaceChildren();
  K.el('span', 'frame-label', '作品展台', phraseFrame);
  phraseOptions.replaceChildren();
  Object.keys(phraseCards).forEach(function (animal) {
    const card = K.el('button', 'toy-card', '', phraseOptions);
    card.id = 'phrase-choice-' + animal;
    card.dataset.animal = animal;
    card.setAttribute('aria-label', animal);
    card.appendChild(picture(phraseCards[animal], animal));
    card.onclick = () => pickPhraseAnimal(animal, card);
  });
  K.$('#phrase-board').dataset.round = String(phraseIndex);
  K.levels(phraseRounds.length, phraseIndex);
  K.say('先听动物，再选颜色。');
}
function phraseReset() {
  stopAudio();
  phraseIndex = 0;
  K.stars = 0;
  K.$('#star-n').textContent = '0';
  phraseRender();
}
phraseRepeat.onclick = () => { if (phraseIndex < phraseRounds.length) listen(phraseRounds[phraseIndex]); };
K.hud({ title: '选卡做展签', icon: '', levels: phraseRounds.length });
K.owl();
K.ready({ title: '选卡给动物做展签', sub: '先选一张动物卡，再配一种颜色。', emoji: '' });
K.onStart = phraseReset;
K.onState = function (state) {
  if (state.reset) phraseReset();
  if (state.demo === 'dog') {
    phraseReset();
    showPhraseAnimal('dog', 'red');
    K.highlight('#phrase-choice-dog');
    K.say('老师示范：红色的狗玩具。');
  }
};
phraseRender();
