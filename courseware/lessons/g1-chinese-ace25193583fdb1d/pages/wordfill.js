(function(){
K.hud({icon:'字',title:'看图补词语',levels:8});K.owl();
var data=[
{pre:'春风',post:'',answer:'吹',image:'__IMG:spring-wind__',choices:['吹','游','池']},
{pre:'夏雨',post:'',answer:'落',image:'__IMG:summer-rain__',choices:['入','落','霜']},
{pre:'秋霜',post:'',answer:'降',image:'__IMG:autumn-frost__',choices:['飘','降','游']},
{pre:'冬雪',post:'',answer:'飘',image:'__IMG:winter-snow__',choices:['飘','池','吹']},
{pre:'',post:'鱼',answer:'游',image:'__IMG:red-fish__',choices:['落','游','降']},
{pre:'',post:'草青',answer:'池',image:'__IMG:pond-park__',choices:['霜','吹','池']},
{pre:'鸟',post:'林',answer:'入',image:'__IMG:pond-park__',choices:['游','入','落']},
{pre:'秋',post:'',answer:'霜',image:'__IMG:autumn-frost__',choices:['降','霜','飘']}];
var level=0,miss=0,locked=false,selected=null,timer=null;
function paint(){var d=data[level];miss=0;locked=false;selected=null;var pic=K.$('#wordfill-picture');pic.src=d.image;pic.alt=d.pre+'空位'+d.post;pic.classList.remove('placed');K.$('#wordfill-context').innerHTML=d.pre+'<span id="wordfill-slot">＿</span>'+d.post;var opts=K.$('#wordfill-options');opts.innerHTML='';K.shuffle(d.choices).forEach(function(ch,i){var e=K.el('button','fill-choice',ch,opts);e.id='fill-choice-'+(i+1);e.setAttribute('aria-label',ch);K.drag(e,{enabled:function(){return!locked},targets:function(){return[K.$('#wordfill-slot')]},onTap:function(){choose(e)},onDrop:function(el,t){if(t)answer(el)}})});K.$('#wordfill-slot').onclick=function(){if(selected)answer(selected)};K.levels(8,level)}
function choose(e){if(locked)return;selected=e;K.$$('.fill-choice').forEach(function(x){x.classList.toggle('selected',x===e)});K.sfx.pick()}
function answer(e){if(locked)return;var d=data[level];if(e.textContent!==d.answer){miss++;K.shake(e);K.sfx.no();K.say(miss===1?'看看图，再想一想词语。':miss===2?'把空位前后连起来想。':'看老师的词语示范。','no');if(miss>=3){K.$('#wordfill-demo').textContent=d.pre+d.answer+d.post;K.$('#wordfill-demo').classList.add('shown')}return}
locked=true;K.$('#wordfill-demo').classList.remove('shown');K.$('#wordfill-slot').textContent=d.answer;K.$('#wordfill-picture').classList.add('placed');K.star(1,e);K.sfx.ok();K.levels(8,level+1);K.say('字放回词语里面了。','ok');timer=setTimeout(function(){level++;if(level===data.length){K.finish({title:'词语补完整了',sub:'图片和字形联系起来。',again:reset})}else paint()},650)}
function reset(){if(timer)clearTimeout(timer);level=0;K.stars=0;K.$('#star-n').textContent='0';K.$('#wordfill-demo').classList.remove('shown');paint();K.say('看图，把缺少的字送进空位。')}
K.onState=function(state){if(typeof state.demo==='boolean'){K.$('#wordfill-demo').textContent='春风吹';K.$('#wordfill-demo').classList.toggle('shown',state.demo)}};
K.onStart=reset;K.ready({emoji:'✦',title:'把词语补完整',sub:'看图片，送字入词。'});reset();
})();
