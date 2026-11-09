(function(){'use strict';
const names=['red','yellow','blue','green','black','white'];
const labels={red:'红色',yellow:'黄色',blue:'蓝色',green:'绿色',black:'黑色',white:'白色'};
const swatches={red:'#e5443e',yellow:'#f6d932',blue:'#367bd0',green:'#33934b',black:'#202126',white:'#fff'};
const pictures={red:'__IMG:umbrella-red__',yellow:'__IMG:umbrella-yellow__',blue:'__IMG:umbrella-blue__',green:'__IMG:umbrella-green__',black:'__IMG:umbrella-black__',white:'__IMG:umbrella-white__'};
const clips={red:'/api/classroom-media/__STAGE__/media/tts-p02-4-9070ed52a5616670a98cfba322b1b94b988d60dafd57fdd81b6cb7f4f172d103.wav',yellow:'/api/classroom-media/__STAGE__/media/tts-p02-13-6d6aed50ffb29da1d1976a6b100ef8bf845160bcaa6fa6872d5435a5f667816b.wav',blue:'/api/classroom-media/__STAGE__/media/tts-p03-4-b0b0ff3a14c670890999d47810bbd4c17a686eee8697a041a08c468aa0c618b0.wav',green:'/api/classroom-media/__STAGE__/media/tts-p03-12-01a5b6afe7395a8a36a798db56102a6c1470e829616a6b72ef20f3f5e96f7197.wav',black:'/api/classroom-media/__STAGE__/media/tts-p04-4-b2448b4e841f8e2094da18c455bc1cc85f60b95bd3644a188f1188fb8227223c.wav',white:'/api/classroom-media/__STAGE__/media/tts-p04-12-03b1c9e98a71c602a8bc8b7516b31d7318ca4bea19fc08c6a11ceca83d2d3103.wav'};
let mode='standby',round=0,attempts=0,busy=false,timer=null,sound=null,userStart=false;
const order=['blue','red','white','yellow','black','green'];
K.hud({icon:'●',title:'颜色小工坊',levels:6});K.owl();
function stopAudio(){if(sound){sound.pause();sound.currentTime=0;sound=null;}}
function replay(){if(mode!=='practice'||busy)return;stopAudio();sound=new Audio(clips[order[round]]);sound.play().catch(function(){K.say('声音未能播放，请按重听后再选。');});}
function picture(colour,parent){const im=K.el('img','',null,parent);im.src=pictures[colour];im.alt=labels[colour]+'雨伞';im.onerror=function(){const fallback=K.el('div','colour-fallback',null,parent);fallback.style.background=swatches[colour];fallback.setAttribute('role','img');fallback.setAttribute('aria-label',labels[colour]+'色块');fallback.setAttribute('data-semantic-diagram','colour');im.remove();};return im;}
function show(colour){const d=K.$('#colour-display');d.innerHTML='';if(colour)picture(colour,d);}
function next(){clearTimeout(timer);stopAudio();busy=false;attempts=0;K.levels(6,round);K.$('#colour-word').textContent=order[round];show(null);
const tray=K.$('#colour-tray');tray.innerHTML='';const target=order[round];const distractors=K.shuffle(names.filter(c=>c!==target)).slice(0,2);K.shuffle([target].concat(distractors)).forEach(function(c){const button=K.el('button','colour-choice',null,tray);button.setAttribute('aria-label',labels[c]+'雨伞');button.dataset.colour=c;picture(c,button);button.onclick=function(){choose(c,button);};});K.say('听颜色，点一把雨伞。');if(userStart)replay();}
function choose(colour,button){if(mode!=='practice'||busy)return;if(colour!==order[round]){attempts++;K.shake(button);K.sfx.no();K.say(attempts===1?'再试一次，先听清颜色。':'按重听，再看每把雨伞的伞面。','no');return;}busy=true;stopAudio();button.classList.add('success');show(colour);K.star(1,button);K.sfx.ok();K.say('这把雨伞的颜色和录音相同。','ok');timer=setTimeout(function(){round++;if(round===order.length){K.levels(6,6);K.finish({title:'六色雨伞集齐了',sub:'图音选择已完成，口语请家人继续观察。',again:start});}else next();},750);}
function start(){clearTimeout(timer);mode='practice';round=0;attempts=0;busy=false;K.stars=0;K.$('#star-n').textContent='0';next();}
K.$('#colour-repeat').onclick=replay;
K.onStart=function(){if(userStart)start();};
K.onState=function(state){if(state.mode==='demo'){mode='demo';clearTimeout(timer);stopAudio();show(state.demoColor||'red');K.$('#colour-word').textContent=state.demoColor||'red';K.$('#colour-tray').innerHTML='';names.slice(0,3).forEach(function(c){const b=K.el('button','colour-choice',null,K.$('#colour-tray'));b.disabled=true;picture(c,b);});K.say('老师先示范，等会儿你来。');}else if(state.mode==='practice'){userStart=true;start();}};
K.ready({emoji:'颜色工坊',title:'听颜色选雨伞',sub:'先听一听，再选图片。'});
K.$('#start-btn').addEventListener('click',function(){userStart=true;mode='practice';},true);
window.addEventListener('pagehide',function(){clearTimeout(timer);stopAudio();});
window.colourGame={choose:function(c){choose(c,K.$('[data-colour="'+c+'"]'));},snapshot:function(){return {mode,round,attempts,busy,display:K.$('#colour-display').textContent};}};
})();
