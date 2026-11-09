var IMAGES={"cat-black": "__IMG:cat-black__", "dog-white": "__IMG:dog-white__"};

var lessonAudio=null,assetFailed=false;
var CLIPS={"cat": "__CLIP:cat__", "dog": "__CLIP:dog__", "animal-hint": "__CLIP:animal-hint__"};
function listen(key){if(assetFailed)return;if(lessonAudio){lessonAudio.pause();lessonAudio.currentTime=0}var url=CLIPS[key];if(!url||url.indexOf('__CLIP:')===0){K.say('配音还没准备好，请稍后再试。','no');return}lessonAudio=new Audio(url);lessonAudio.play().catch(function(){K.say('请按再听按钮。')})}
window.addEventListener('pagehide', stopAudio);
window.addEventListener('message',function(e){if(e.data&&/^(SET_WIDGET_STATE|HIGHLIGHT_ELEMENT|ANNOTATE_ELEMENT|REVEAL_ELEMENT)$/.test(e.data.type)&&lessonAudio)lessonAudio.pause()});
function picture(key,alt){var im=document.createElement('img');im.src=IMAGES[key];im.alt=alt||'原创木制玩具图片';im.draggable=false;im.dataset.lessonPicture='true';return im}
function assetStop(){if(assetFailed)return;assetFailed=true;if(lessonAudio)lessonAudio.pause();var panel=K.el('div','asset-stop',null,K.stage());panel.id='asset-stop';K.el('div','','图片暂时没打开',panel);K.el('div','small-hint','请点大按钮，再试一次。',panel);var b=K.el('button','btn','重试图片',panel);b.id='asset-retry';b.onclick=function(){location.reload()}}
document.addEventListener('error',function(e){if(e.target&&e.target.tagName==='IMG')assetStop()},true);
var PALETTE={red:'#E23735',blue:'#2367CD',yellow:'#F4D323',green:'#269B55',black:'#272626',white:'#FFFFFF'};
function makeColors(parent,choose){Object.keys(PALETTE).forEach(function(c){var b=K.el('button','color-chip','',parent);b.id=parent.id+'-'+c;b.dataset.color=c;b.style.background=PALETTE[c];b.setAttribute('aria-label',c);b.onclick=function(){if(!assetFailed)choose(c,b)}})}
function stopAudio(){if(lessonAudio)lessonAudio.pause()}

var animalRound=0,animalBusy=false,animalWrong=0;
var animalRounds=['cat','dog','cat'];
function animalRender(){var options=K.$('#animal-options');options.replaceChildren();['cat','dog'].forEach(function(kind,i){var b=K.el('button','toy-card','',options);b.id=i?'animal-right':'animal-left';b.setAttribute('aria-label',kind==='cat'?'黑色猫玩具':'白色狗玩具');b.dataset.kind=kind;b.appendChild(picture(kind==='cat'?'cat-black':'dog-white'));b.onclick=function(){animalChoose(b,kind)}});var stage=K.$('#animal-stage');stage.replaceChildren();K.el('span','frame-label','展台',stage);K.$('#animal-board').dataset.round=String(animalRound);K.levels(animalRounds.length,animalRound);animalBusy=false;animalWrong=0;K.say('听名称，再点图片。')}
function animalChoose(button,kind){if(assetFailed||animalBusy)return;if(kind!==animalRounds[animalRound]){animalWrong++;listen('animal-hint');K.sfx.no();K.shake(button);K.say(animalWrong===1?'先听名称，再看猫狗的样子。':'尖耳朵和垂耳朵不同，再听一遍。','no');return}animalBusy=true;button.classList.add('placed');var frame=K.$('#animal-stage');frame.replaceChildren();frame.appendChild(button.querySelector('img'));K.star(1,frame);K.sfx.ok();K.say('你把听到的朋友送上展台了。','ok');setTimeout(function(){animalRound++;if(animalRound===animalRounds.length){K.levels(animalRounds.length,animalRound);stopAudio();K.finish({title:'朋友都到齐啦',sub:'听名称，对照图片。',again:animalReset})}else{animalRender();listen(animalRounds[animalRound])}},650)}
function animalReset(){stopAudio();animalRound=0;K.stars=0;K.$('#star-n').textContent='0';animalRender()}
K.hud({title:'听朋友',icon:'',levels:3});K.owl();K.ready({title:'送朋友上展台',sub:'听名称，点对应图片。',emoji:''});K.$('#animal-repeat').onclick=function(){listen(animalRounds[animalRound]||'cat')};K.onStart=animalReset;K.onState=function(s){if(s.reset){animalReset();return}if(s.demo){animalRender();var b=K.$(s.demo==='cat'?'#animal-left':'#animal-right'),f=K.$('#animal-stage');f.replaceChildren();f.appendChild(b.querySelector('img'));b.classList.add('placed');K.say('老师示范：名称要对应动物。')}};animalRender();
