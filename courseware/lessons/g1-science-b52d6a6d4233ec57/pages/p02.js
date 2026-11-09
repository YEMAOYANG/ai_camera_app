(function(){
const urls={eye:'__IMG:eye__',hand:'__IMG:hand__',nose:'__IMG:nose__',ear:'__IMG:ear__',adult:'__IMG:adult__',tongue:'__IMG:tongue__',apple:'__IMG:apple__',unknown:'__IMG:unknown__',bell:'__IMG:bell__'};
const labels={eye:'眼睛',hand:'手的皮肤',nose:'鼻子',ear:'耳朵',adult:'请大人',tongue:'舌头'};
const plans=[['eye','hand','nose','adult','tongue'],['eye','adult']];
let level=0,step=0,tries=0,busy=false,phase='play',timer=null;
const track=K.$('#plan-track'),picture=K.$('#plan-picture'),choices=K.$$('#plan-choices button');
K.hud({icon:'',title:'给观察排顺序',levels:2});K.owl();K.ready({emoji:'',title:'给观察排顺序',sub:'听老师讲，再把图片排进轨道'});
function image(el,key){el.src=urls[key];el.onerror=function(){el.parentElement.classList.add('image-error');K.say('图片未加载，请退出后再试','no')}}
function resetStars(){K.stars=0;K.$('#star-n').textContent='0'}
function rail(items,filled){track.innerHTML='';items.forEach(function(key,i){const slot=K.el('div','rail-slot','',track);if(i<filled){const im=K.el('img','','',slot);image(im,key);im.alt=labels[key]}if(i<items.length-1)K.el('span','arrow','→',track)})}
function render(i){clearTimeout(timer);level=i;step=0;tries=0;busy=false;phase='play';image(picture,i===0?'apple':'unknown');picture.alt=i===0?'熟悉的苹果':'未知瓶中物';rail(plans[i],0);choices.forEach(b=>{b.disabled=false;b.classList.remove('placed','selected')});K.levels(2,i);K.say(i===0?'这次计划：看、摸、闻、请大人、最后才尝':'未知物：先看外观，再请大人判断')}
function answer(key,el){if(!K.started||busy||phase!=='play'||plans[level].slice(0,step).includes(key))return;K.sfx.pick();const expected=plans[level][step];if(key!==expected){tries++;K.shake(el);K.sfx.no();if(tries===1)K.say('先想观察的顺序和安全条件','no');else if(tries===2)K.say('看外部在前，能不能尝先请大人','no');else{K.say('老师提示下一步，再由你放进轨道','no');K.highlight('#plan-'+expected)}return}tries=0;step++;el.disabled=true;el.classList.add('placed');K.sfx.ok();K.star(1,el);rail(plans[level],step);K.say('这一步已放好，继续按计划观察','ok');if(step===plans[level].length){busy=true;timer=setTimeout(function(){if(level===0)render(1);else{K.levels(2,2);K.finish({title:'观察计划排好了',sub:'有目的，有顺序，安全放在前面',again:function(){resetStars();render(0)}})}},850)}}
choices.forEach(function(b){b.addEventListener('click',()=>answer(b.dataset.key,b));K.drag(b,{enabled:()=>K.started&&!busy&&phase==='play'&&!b.disabled,targets:()=>[track],onDrop:(el,target)=>{if(target)answer(el.dataset.key,el)}})});
K.onStart=function(){render(0)};K.onState=function(state){if(state.demo==='bell'){clearTimeout(timer);phase='demo';busy=true;image(picture,'bell');rail(['eye','ear'],2);K.say('老师示范：先看外形，再听声音')}if(state.phase==='play'){resetStars();render(0)}};
K.lessonSnapshot=()=>({level,step,tries,busy,phase});K.$$('img').forEach(im=>im.onerror=function(){im.parentElement.classList.add('image-error');K.say('图片未加载，请退出后再试','no')});
document.addEventListener('error',function(event){const im=event.target;if(im&&im.tagName==='IMG'&&im.closest('#play')){im.parentElement.classList.add('image-error');K.say('图片未加载，请退出后再试','no')}},true);
})();