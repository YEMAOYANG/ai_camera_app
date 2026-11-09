(function(){
var scenes=['__IMG:chase__','__IMG:pull-wing__'],safe='__IMG:adult-watch__',level=0,tries=0,phase='play',busy=false,epoch=0,missing=false;
var photo=K.$('#care-photo'),record=K.$('#care-record'),choices=K.$$('#care-choices button');
K.hud({icon:'◉',title:'换成温柔观察',levels:2});K.owl();K.ready({emoji:'◉',title:'换成温柔观察',sub:'看清动作，换成合适的观察方法',btn:'start-btn'});
K.$$('#care-board img').forEach(function(im){im.onerror=function(){missing=true;im.style.visibility='hidden';K.say('图片暂未载入，请重新打开本页')}});
function view(src,alt){photo.style.visibility='visible';photo.src=src;photo.alt=alt}
function reset(){epoch++;level=0;tries=0;phase='play';busy=false;record.innerHTML='';K.shuffle(choices).forEach(function(b){K.$('#care-choices').appendChild(b)});view(scenes[0],'孩子追赶狗的不合适动作');K.stars=0;K.$('#star-n').textContent='0';K.levels(2,0);K.say('先看大画面，再换成合适的观察动作')}
function choose(action,button){if(!K.started||busy||phase!=='play'||missing)return;if(action!=='quiet'){tries++;K.sfx.no();K.shake(button);if(tries===1)K.say('再看看手和脚，动作会不会打扰动物','no');else if(tries===2)K.say('不追赶、不拉扯，请大人陪着安静看','no');else{K.highlight('#care-choice-quiet');K.say('老师示范合适的观察方法，再由你换一次','no')}return}
busy=true;view(safe,'成人陪同，保持距离安静观察');var im=K.el('img','',null,record);im.src=safe;im.alt='已经换好的安全观察方法';K.star(1,button);K.sfx.ok();K.say('大画面换成温柔观察，给动物自在活动的空间','ok');var token=epoch;setTimeout(function(){if(token!==epoch)return;if(level===1){K.levels(2,2);K.finish({title:'观察方法换好了',sub:'爱护动物，也注意自己的安全',again:reset});return}level++;tries=0;busy=false;K.levels(2,level);view(scenes[level],'伸手拉鸡翅的不合适动作');K.shuffle(choices).forEach(function(b){K.$('#care-choices').appendChild(b)});K.say('换一个新情境，也看看怎样观察更合适')},1000)}
choices.forEach(function(b){b.addEventListener('click',function(){choose(b.dataset.action,b)})});K.$('#care-reset').addEventListener('click',reset);K.onState=function(s){if(s.demo){phase='demo';view(s.demo==='quiet'?safe:scenes[1],s.demo==='quiet'?'教师示范安静观察':'需要停止的伸手拉翅动作')}if(s.phase==='play')reset()};K.onStart=reset;reset();
})();
