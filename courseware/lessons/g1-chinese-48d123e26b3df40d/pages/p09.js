(function(){
'use strict';
var tasks=[{phrase:'（　）草',answer:'青',options:['青','清'],kind:'grass'},{phrase:'（　）水',answer:'清',options:['清','青'],kind:'water'},{phrase:'（　）草地上',answer:'在',options:['再','在'],kind:'at'},{phrase:'（　）跑一次',answer:'再',options:['在','再'],kind:'again'}];
var demoTask = {phrase:'（　）饭桌旁', answer:'在', options:['在','再'], kind:'meal'};
function create(){return {level:0,miss:0,done:[],demo:false,finished:false}}
function choose(s,c){if(s.demo||s.finished)return {ignored:true};var t=tasks[s.level];if(c!==t.answer){s.miss++;return {ok:false,hint:s.miss===1?'想一想画面和句子说的意思，再试试。':'是颜色、水、位置，还是又一次？慢慢想。'}}s.done.push({phrase:t.phrase,chosen:c,visual:t.kind});s.level++;s.miss=0;s.finished=s.level===tasks.length;return {ok:true,finished:s.finished}}
if(typeof module!=='undefined'&&module.exports)module.exports={tasks:tasks,demoTask:demoTask,create:create,choose:choose};
if(typeof window==='undefined'||!window.K)return;
var s=create(),busy=false,timer,urls={grass:'__IMG:green-grass__',water:'__IMG:clear-stream__',run:'__IMG:child-run__',meal:'__IMG:full-meal__'};
K.hud({icon:'字',title:'听意思，让画面动',levels:4});K.owl();K.ready({emoji:'字',title:'听意思，让画面动起来',sub:'看生活图，选适合这个意思的字'});
function im(parent,key,cls,alt){var e=K.el('img',cls,null,parent);e.src=urls[key];e.alt=alt;e.onerror=function(){e.style.display='none';var box=K.el('div','context-failure','图片没有打开',parent),b=K.el('button','btn sm','重试图片',box);b.onclick=function(){box.remove();e.style.display='';e.src=urls[key]}};return e}
function render(t, changed) {
  var picture = K.$('#context-picture');
  picture.innerHTML = '';
  picture.className = changed ? 'changed' : '';
  if (t.kind === 'grass') im(picture, 'grass', changed ? '' : 'muted', '一片长满嫩草的草地');
  if (t.kind === 'water') {
    im(picture, 'water', '', '看得见水下石头的小溪');
    K.el('div', 'stream-veil', '', picture);
  }
  if (t.kind === 'at') im(picture, 'run', 'at-scene', '草地上的孩子');
  if (t.kind === 'meal') im(picture, 'meal', '', '坐在饭桌旁的孩子');
  if (t.kind === 'again') {
    var first = K.el('div', 'repeat-frame', '', picture);
    im(first, 'run', 'repeat-image', '第一次跑步');
    K.el('span', 'time-label', '1', first);
    K.el('div', 'repeat-arrow', '→', picture);
    var second = K.el('div', 'repeat-frame repeat-again', '', picture);
    im(second, 'run', 'repeat-image', '又跑一次步');
    K.el('span', 'time-label', '2', second);
  }
  K.$('#context-phrase').textContent = changed ? t.phrase.replace('（　）', t.answer) : t.phrase;
  var options = K.$('#word-options');
  options.innerHTML = '';
  t.options.forEach(function (word, index) {
    var button = K.el('button', 'word-card' + (changed && word === t.answer ? ' correct' : ''), word, options);
    button.id = 'word-choice-' + index;
    button.setAttribute('aria-label', '目标字' + word);
    button.onclick = function () { answer(word); };
  });
  K.levels(4, Math.min(s.level, 4));
}
function reset(){clearTimeout(timer);s=create();busy=false;K.stars=0;K.$('#star-n').textContent='0';render(tasks[0],false);K.$('#context-progress').textContent='先想意思，再选字';K.say('看画面，想句子说的是什么，再选字。')}
function answer(c){if(busy)return;var t=tasks[s.level],r=choose(s,c);if(r.ignored)return;if(!r.ok){K.say(r.hint,'no');K.sfx.no();return}busy=true;render(t,true);K.star(1,K.$('#context-picture'));K.sfx.ok();K.$('#context-progress').textContent='字放好了，画面也发生了变化';K.say('联系意思选字，声音相同也能分清。','ok');timer=setTimeout(function(){busy=false;if(s.finished){K.finish({title:'意思和字连起来啦',sub:'同音字要听懂语境，再选择。',again:reset})}else{render(tasks[s.level],false);K.$('#context-progress').textContent='先想意思，再选字';K.say('看新画面：联系颜色、水、位置或又一次。')}},1250)}
K.onStart = reset;
K.onState = function (state) {
  if (state.demo) {
    clearTimeout(timer);
    s = create();
    s.demo = true;
    busy = false;
    render(demoTask, true);
    K.$('#context-progress').textContent = '教师示范，不计入作答';
    K.say('教师示范：饭桌旁是孩子的位置。');
  }
  if (state.play) reset();
};
reset();
K.test=async function(){if(!K.cp)return;reset();await K.cp('初始');answer('清');await K.cp('首次错误提示');K.onState({demo:true});await K.cp('教师示范');reset();for(var i=0;i<4;i++){answer(tasks[s.level].answer);await K.wait(1300)}await K.cp('答对完成');reset();await K.cp('重玩复位')};
})();
