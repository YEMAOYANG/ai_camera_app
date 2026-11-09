(function(){'use strict';
const names=['red','yellow','blue','green','black','white'];
const labels={red:'红色',yellow:'黄色',blue:'蓝色',green:'绿色',black:'黑色',white:'白色'};
const swatches={red:'#e5443e',yellow:'#f6d932',blue:'#367bd0',green:'#33934b',black:'#202126',white:'#fff'};
const pictures={red:'__IMG:umbrella-red__',yellow:'__IMG:umbrella-yellow__',blue:'__IMG:umbrella-blue__',green:'__IMG:umbrella-green__',black:'__IMG:umbrella-black__',white:'__IMG:umbrella-white__'};
let mode='standby',round=0,attempts=0,busy=false,timer=null,sound=null,userStart=false;
const order=['green','white','black'];let previous='yellow';
K.hud({icon:'●',title:'看现在的颜色',levels:3});K.owl();
function stopAudio(){if(sound){sound.pause();sound.currentTime=0;sound=null;}}
function replay(){if(mode!=='practice'||busy)return;stopAudio();sound=new Audio('/api/classroom-media/__STAGE__/media/tts-p08-4-733a74e64dc8b6892c1933f63281bf39fca1cc31a4be582cba27bc3e2a2d06e0.wav');sound.play().catch(function(){K.say('声音未能播放，请按重听后再选。');});}
function picture(colour,parent){const im=K.el('img','',null,parent);im.src=pictures[colour];im.alt=labels[colour]+'雨伞';im.onerror=function(){const f=K.el('div','now-fallback',null,parent);f.style.background=swatches[colour];f.setAttribute('role','img');f.setAttribute('aria-label',labels[colour]+'色块');f.setAttribute('data-semantic-diagram','colour');im.remove();};}
function draw(old,now){const a=K.$('#now-old-image'),b=K.$('#now-main-image');a.innerHTML='';b.innerHTML='';picture(old,a);picture(now,b);}
function palette(){const p=K.$('#now-palette');p.innerHTML='';names.forEach(function(c){const b=K.el('button','now-colour',null,p);b.setAttribute('aria-label',labels[c]);b.dataset.colour=c;const dot=K.el('span','',null,b);dot.style.background=swatches[c];b.onclick=function(){choose(c,b);};});}
function next(){clearTimeout(timer);stopAudio();attempts=0;busy=false;K.levels(3,round);draw(previous,order[round]);palette();K.say('看大的这把雨伞，现在是什么颜色？');if(userStart)replay();}
function choose(c,b){if(mode!=='practice'||busy)return;if(c!==order[round]){attempts++;K.shake(b);K.sfx.no();K.say(attempts===1?'再看一看大的这把雨伞。':'左边是先前，留意大的现在图。','no');return;}busy=true;stopAudio();b.classList.add('success');picture(c,K.$('#now-finished'));K.star(1,b);K.sfx.ok();K.say('你选的是现在的颜色，作品收好了。','ok');timer=setTimeout(function(){previous=c;round++;if(round===3){K.levels(3,3);K.finish({title:'现在的颜色找对了',sub:'描述变化时，记得看现在。',again:start});}else next();},750);}
function start(){clearTimeout(timer);stopAudio();mode='practice';round=0;previous='yellow';attempts=0;busy=false;K.stars=0;K.$('#star-n').textContent='0';K.$('#now-finished').innerHTML='';next();}
K.$('#now-repeat').onclick=replay;K.onStart=function(){if(userStart)start();};
K.onState=function(s){if(s.mode==='demo'){mode='demo';clearTimeout(timer);stopAudio();draw('red',s.demoColor||'red');palette();K.say('老师示范：小图先前，大图现在。');}else if(s.mode==='practice'){userStart=true;start();}};
K.ready({emoji:'颜色工坊',title:'找现在的颜色',sub:'看大图，选颜色，收好作品。'});
K.$('#start-btn').addEventListener('click',function(){userStart=true;mode='practice';},true);
window.addEventListener('pagehide',function(){clearTimeout(timer);stopAudio();});
window.nowGame={choose:function(c){choose(c,K.$('[data-colour="'+c+'"]'));},snapshot:function(){return {mode,round,attempts,busy,previous};}};
})();
