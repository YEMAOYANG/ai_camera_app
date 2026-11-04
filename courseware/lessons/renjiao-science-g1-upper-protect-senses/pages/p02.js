(function(){
var labels={vision:'cover-eye',hearing:'cover-ear',touch:'cover-hand'},clues={vision:'clue-vision',hearing:'clue-hearing',touch:'clue-touch'},levels=['hearing','touch'];
var level=0,cover=null,tries=0,locked=false,phase='play',selected=null;
K.hud({icon:'🔎',title:'少了哪种感觉',levels:2});K.owl();K.say('选一种遮挡，再找少掉的线索');
K.ready({emoji:'🔎',title:'少了哪种感觉',sub:'找一找线索',btn:'start-btn'});
var character=K.$('#character'),display=K.$('#cover-display'),zone=K.$('#drop-zone'),mark=K.$('#feedback-mark');
function setCover(type){cover=type;character.className=type?'cover-'+type:'';display.className=type||'';K.$$('#covers .cover').forEach(function(b){b.classList.toggle('selected',b.dataset.cover===type)});K.$$('#clues .clue').forEach(function(b){b.classList.remove('dim','selected')});mark.classList.remove('on');zone.classList.toggle('ready-drop',!!type);selected=null}
function setLevel(i){level=i;tries=0;locked=false;phase='play';setCover(null);K.levels(2,i);K.say(i===0?'给女孩戴上耳罩，再找声音线索':'给女孩戴上手套，再找触感线索')}
function answer(type,el){if(!K.started||locked||phase!=='play')return;if(!cover){K.say('先选一个遮挡物','no');K.shake(K.$('#covers'));return}K.sfx.pick();var want=levels[level];
 if(type===want){locked=true;phase='done';K.sfx.ok();K.star(tries===0?2:1,el);K.pop(character);mark.textContent='✓';mark.classList.add('on');K.say(level===0?'耳罩挡住声音线索':'手套挡住触感线索','ok');K.$('#'+clues[want]).classList.add('selected');setTimeout(function(){if(level<1)setLevel(1);else{K.levels(2,2);K.finish({title:'线索找到了',sub:'感觉器官帮助我们发现',again:function(){setLevel(0)}})}},1200);return}
 tries++;K.sfx.no();K.shake(el);K.$('#'+clues[type]).classList.add('dim');if(tries===1)K.say('回想一下，遮住了身体哪里','no');else if(tries===2)K.say('再看这个部位原来获得什么线索','no');else{K.say('老师示范：耳罩挡住声音线索','no');K.$('#clue-hearing').classList.add('selected');setTimeout(function(){K.$('#clue-hearing').classList.remove('selected')},850)}
}
K.$$('#covers .cover').forEach(function(b){b.addEventListener('click',function(){if(!K.started||locked||phase!=='play')return;K.sfx.pick();setCover(b.dataset.cover);K.say('看看遮住后，哪种线索少了')})});
K.$$('#clues .clue').forEach(function(b){b.addEventListener('click',function(){if(!K.started||locked||phase!=='play')return;selected=b.dataset.clue;K.$$('#clues .clue').forEach(function(c){c.classList.toggle('selected',c===b)});K.say('把线索放到女孩旁边');K.sfx.pick()})});
character.addEventListener('click',function(){if(selected)answer(selected,K.$('#'+clues[selected]))});
K.$$('#covers .cover').forEach(function(b){K.drag(b,{enabled:function(){return K.started&&!locked&&phase==='play'},targets:function(){return [zone]},onTap:function(){b.click()},onDrop:function(el,target){if(target){K.sfx.drop();setCover(el.dataset.cover)}}})});
K.$$('#clues .clue').forEach(function(b){K.drag(b,{enabled:function(){return K.started&&!locked&&phase==='play'},targets:function(){return [character]},onTap:function(){b.click()},onDrop:function(el,target){if(target)answer(el.dataset.clue,el)}})});
K.onState=function(state){if(state.demo==='vision'){phase='demo';locked=true;setCover('vision');K.$('#clue-vision').classList.add('dim');K.say('遮住眼睛后，颜色线索变淡','ok')}if(state.phase==='play')setLevel(0)};
})();
