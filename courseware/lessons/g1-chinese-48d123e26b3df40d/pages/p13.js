(function(){
'use strict';
var tasks=[{label:'n',pinyin:'',answer:'N',choices:['M','N','L']},{label:'d',pinyin:'',answer:'D',choices:['Q','B','D']},{label:'q',pinyin:'',answer:'Q',choices:['Q','G','P']},{label:'溪',pinyin:'xī',answer:'X',choices:['S','X','Q']},{label:'解',pinyin:'jiě',answer:'J',choices:['G','L','J']},{label:'准',pinyin:'zhǔn',answer:'Z',choices:['Z','H','N']},{label:'楼',pinyin:'lóu',answer:'L',choices:['N','R','L']}];
function create(){return {level:0,miss:0,done:[],demo:false,finished:false}}
function choose(s,c){if(s.demo||s.finished)return {ignored:true};var t=tasks[s.level];if(c!==t.answer){s.miss++;return {ok:false,hint:s.miss===1?'先看最开头的小写字母，再找大写伙伴。':'用字母表想一想大小写的对应，再试试。'}}s.done.push({target:t.label,capital:c});s.level++;s.miss=0;s.finished=s.level===tasks.length;return {ok:true,finished:s.finished}}
if(typeof module!=='undefined'&&module.exports)module.exports={tasks:tasks,create:create,choose:choose};
if(typeof window==='undefined'||!window.K)return;
var s=create(),busy=false,timer;
K.hud({icon:'字',title:'音序找大写伙伴',levels:7});K.owl();K.ready({emoji:'字',title:'给音序找大写伙伴',sub:'观察开头字母，配对后送进索引栏'});
function render(t,changed){K.$('#lookup-pinyin').textContent=t.pinyin;K.$('#lookup-target').textContent=t.label;K.$('#lookup-caption').textContent=t.pinyin?'看开头，找音序':'找大写伙伴';K.$('#sound-card').classList.toggle('filed',!!changed);K.$('#capital-options').innerHTML='';K.shuffle(t.choices).forEach(function(c,i){var b=K.el('button','capital-card'+(changed&&c===t.answer?' correct':''),c,K.$('#capital-options'));b.id='capital-choice-'+i;b.setAttribute('aria-label','目标大写字母'+c);b.onclick=function(){answer(c)}});K.$('#selected-index').textContent=changed?t.label+' → '+t.answer:'索引栏';var ledger=K.$('#index-ledger');ledger.innerHTML='';s.done.forEach(function(d){K.el('div','index-record',d.target+' → '+d.capital,ledger)});K.levels(7,Math.min(s.level,7))}
function reset(){clearTimeout(timer);s=create();busy=false;K.stars=0;K.$('#star-n').textContent='0';render(tasks[0],false);K.say('先给小写字母找大写伙伴，再练目标字音序。')}
function answer(c){if(busy)return;var t=tasks[s.level],r=choose(s,c);if(r.ignored)return;if(!r.ok){K.sfx.no();K.say(r.hint,'no');return}busy=true;render(t,true);K.star(1,K.$('#selected-index'));K.sfx.ok();K.say('字卡进入索引栏，大小写对应起来了。','ok');timer=setTimeout(function(){busy=false;if(s.finished){K.finish({title:'索引准备好了',sub:'再拿自己的字典查五个字，真实翻查留待观察。',again:reset})}else render(tasks[s.level],false)},1250)}
K.onStart=reset;K.onState=function(st){if(st.demo){clearTimeout(timer);s=create();s.demo=true;busy=false;render({label:'m',pinyin:'',answer:'M',choices:['N','M','T']},true);K.say('教师示范：同一个字母的大小写配在一起。')}if(st.play)reset()};reset();
K.test=async function(){if(!K.cp)return;reset();await K.cp('初始');answer('M');await K.cp('首次错误提示');K.onState({demo:true});await K.cp('教师示范');reset();for(var i=0;i<tasks.length;i++){answer(tasks[s.level].answer);await K.wait(1300)}await K.cp('答对完成');reset();await K.cp('重玩复位')};
})();
