(function(){
var left=1,saved=0,miss=0,demo=false,busy=false,timer;
K.hud({icon:'◉',title:'八片按顺序分',levels:7});K.owl();K.ready({emoji:'◉',title:'八片按顺序分',sub:'每次移动一片，把分法找全'});
function render(){var strip=K.$('#strip');strip.innerHTML='';for(var i=0;i<8;i++){var e=K.el('div','unit','<img src="__IMG:bead__" alt="">',strip);e.style.left=(i*96+(i>=left?90:0))+'px';e.querySelector('img').onerror=function(){this.style.visibility='hidden';this.parentElement.classList.add('fallback')}}var sep=K.el('div','separator','',strip);sep.style.left=(left*96+38)+'px';
K.$('#left-count').textContent=left;K.$('#right-count').textContent=8-left;K.$('#records').innerHTML='';for(var j=1;j<=7;j++){var card=K.el('div','record'+(j<=saved?' done':''),'',K.$('#records'));K.el('div','',j<=saved?j+' · '+(8-j):'?',card);if(j<=saved){var dots=K.el('div','quantity','',card);for(var n=0;n<8;n++)K.el('i',n>=j?'second':'','',dots)}}K.levels(7,saved);
K.$('#move-back').disabled=demo||busy||left<=1;K.$('#move-one').disabled=demo||busy||left>=7}
function reset(){clearTimeout(timer);left=1;saved=0;miss=0;demo=false;busy=false;K.stars=0;K.$('#star-n').textContent='0';render();K.say('先保存一和七，再每次只搬一片。')}
K.$('#move-one').onclick=function(){if(demo||busy||left>=7)return;left++;render();K.sfx.drop();K.say('左边多一片，右边少一片。')};K.$('#move-back').onclick=function(){if(demo||busy||left<=1)return;left--;render();K.sfx.pick()};
K.$('#save-way').onclick=function(){if(demo||busy)return;if(left!==saved+1){miss++;K.sfx.no();K.say(miss===1?'看看记录，下一种应该接在哪里？':miss===2?'从一和七开始，每次只搬一片。':'先回到下一行，再把这一行保存。','no');if(miss>=3){left=saved+1;render();K.highlight('#left-count');miss=0}return}saved++;miss=0;render();K.star(1,K.$('#save-way'));K.sfx.ok();K.say('这一行没有重复，八片全都还在。','ok');if(saved===7){busy=true;timer=setTimeout(function(){K.finish({title:'八的七种找全了',sub:'有顺序，就不会跳过中间。',again:reset})},900)}};
function teacherStart(){demo=true;miss=0;busy=false;K.stars=0;K.$('#star-n').textContent='0';document.querySelectorAll('.flystar,.cf').forEach(function(el){el.remove()});saved=0;}
K.onStart=reset;K.onState=function(state){clearTimeout(timer);if(typeof state.demoLeft==='number'){teacherStart();left=Math.max(1,Math.min(7,state.demoLeft));render();K.say('示范：左边'+left+'片，右边'+(8-left)+'片，总数仍是八片。')}if(state.play)reset()};render();
})();
