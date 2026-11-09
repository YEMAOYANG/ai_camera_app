var IMAGES={"car-unpainted": "__IMG:car-unpainted__", "car-blue": "__IMG:car-blue__", "car-yellow": "__IMG:car-yellow__"};

var lessonAudio=null,assetFailed=false;
var CLIPS={"blue": "__CLIP:blue__", "yellow": "__CLIP:yellow__", "color-hint": "__CLIP:color-hint__", "blue-result": "__CLIP:blue-result__"};
function listen(key){if(assetFailed)return;if(lessonAudio){lessonAudio.pause();lessonAudio.currentTime=0}var url=CLIPS[key];if(!url||url.indexOf('__CLIP:')===0){K.say('配音还没准备好，请稍后再试。','no');return}lessonAudio=new Audio(url);lessonAudio.play().catch(function(){K.say('请按再听按钮。')})}
window.addEventListener('pagehide', stopAudio);
window.addEventListener('message',function(e){if(e.data&&/^(SET_WIDGET_STATE|HIGHLIGHT_ELEMENT|ANNOTATE_ELEMENT|REVEAL_ELEMENT)$/.test(e.data.type)&&lessonAudio)lessonAudio.pause()});
function picture(key,alt){var im=document.createElement('img');im.src=IMAGES[key];im.alt=alt||'原创木制玩具图片';im.draggable=false;im.dataset.lessonPicture='true';return im}
function assetStop(){if(assetFailed)return;assetFailed=true;if(lessonAudio)lessonAudio.pause();var panel=K.el('div','asset-stop',null,K.stage());panel.id='asset-stop';K.el('div','','图片暂时没打开',panel);K.el('div','small-hint','请点大按钮，再试一次。',panel);var b=K.el('button','btn','重试图片',panel);b.id='asset-retry';b.onclick=function(){location.reload()}}
document.addEventListener('error',function(e){if(e.target&&e.target.tagName==='IMG')assetStop()},true);
var PALETTE={red:'#E23735',blue:'#2367CD',yellow:'#F4D323',green:'#269B55',black:'#272626',white:'#FFFFFF'};
function makeColors(parent,choose){Object.keys(PALETTE).forEach(function(c){var b=K.el('button','color-chip','',parent);b.id=parent.id+'-'+c;b.dataset.color=c;b.style.background=PALETTE[c];b.setAttribute('aria-label',c);b.onclick=function(){if(!assetFailed)choose(c,b)}})}
function stopAudio(){if(lessonAudio)lessonAudio.pause()}

const carRounds = ['yellow', 'blue'];
let carIndex = 0;
let carSelected = null;
let carWaiting = false;
let carWrong = 0;
let carTimer = 0;
const car = K.$('#color-drop');
const carTray = K.$('#color-tray');

const carPictures = {
  unpainted: picture('car-unpainted', '还没上色的原木小车'),
  blue: picture('car-blue', '蓝色小车'),
  yellow: picture('car-yellow', '黄色小车')
};
for (const image of Object.values(carPictures)) {
  image.addEventListener('error', assetStop, { once: true });
}
function showCar(color) {
  car.replaceChildren(carPictures[color]);
  car.dataset.paint = color;
}
function renderCar() {
  carWaiting = false;
  carSelected = null;
  carWrong = 0;
  showCar('unpainted');
  K.$('#color-board').dataset.round = String(carIndex);
  K.$$('#color-tray .color-chip').forEach(chip => chip.classList.remove('selected'));
  K.levels(carRounds.length, carIndex);
  K.say('先听颜色，再选颜料。');
}
function resetCar() {
  clearTimeout(carTimer);
  K.$$('#color-board .teach-hl').forEach(element => element.classList.remove('teach-hl'));
  stopAudio();
  carIndex = 0;
  K.stars = 0;
  K.$('#star-n').textContent = '0';
  renderCar();
}
function paintCar(color) {
  if (!color || assetFailed || carWaiting) return;
  if (color !== carRounds[carIndex]) {
    carWrong++;
    K.sfx.no();
    K.shake(car);
    listen('color-hint');
    K.say(carWrong === 1 ? '重听颜色，再挑一块颜料。' : '只听颜色词，车身现在还没上色。', 'no');
    return;
  }
  carWaiting = true;
  showCar(color);
  K.star(1, car);
  K.sfx.ok();
  K.say('颜色涂到了车身上。', 'ok');
  if (color === 'blue') listen('blue-result');
  carTimer = setTimeout(function () {
    carIndex++;
    if (carIndex === carRounds.length) {
      K.levels(carRounds.length, carIndex);
      K.finish({ title: '小车都涂好啦', sub: '可以指着小车试说颜色。', again: resetCar });
      return;
    }
    renderCar();
    listen(carRounds[carIndex]);
  }, color === 'blue' ? 1650 : 850);
}
makeColors(carTray, function (color, chip) {
  if (carWaiting) return;
  carSelected = color;
  K.$$('#color-tray .color-chip').forEach(item => item.classList.toggle('selected', item === chip));
  K.say('选好了，再把颜料放到车身。');
});
K.$$('#color-tray .color-chip').forEach(chip => K.drag(chip, {
  enabled: () => !carWaiting && !assetFailed,
  targets: () => [car],
  onTap: () => chip.click(),
  onDrop: (element, target) => { if (target) paintCar(element.dataset.color); }
}));
car.onclick = () => paintCar(carSelected);
K.$('#color-repeat').onclick = () => { if (carIndex < carRounds.length) listen(carRounds[carIndex]); };
K.hud({ title: '听音给车上色', icon: '', levels: carRounds.length });
K.owl();
K.ready({ title: '听颜色给小车上色', sub: '听一听，选颜料，点车身。', emoji: '' });
K.onStart = resetCar;
K.onState = function (state) {
  if (state.reset) resetCar();
  if (state.demo === 'blue') {
    resetCar();
    showCar('blue');
    K.highlight('#color-tray-blue');
    K.say('老师示范：车身变成蓝色。');
  }
};
renderCar();
