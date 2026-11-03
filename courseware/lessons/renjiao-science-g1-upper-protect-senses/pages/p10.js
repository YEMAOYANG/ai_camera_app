(function(){
K.hud({icon:'🔎',title:'安全小侦探',levels:2});K.owl();K.ready({emoji:'🔬',title:'安全小侦探',sub:'先安全，再行动',btn:'start-btn'});
var lab=K.$('#lab'),phase=0,misses=0,selected=null,done=false;
function feedback(text,kind){var f=K.$('#feedback');f.textContent=text;f.style.borderColor=kind==='ok'?'var(--gr)':'var(--line)';f.style.color=kind==='ok'?'var(--gr2)':'var(--ink2)';K.say(text,kind||'')}
function hint(){misses++;K.sfx.no();feedback(misses===1?'先看手和容器的距离':misses===2?'陌生用品先不要碰，找老师':'老师示范安全动作，再轮到你','no');if(misses>=3){K.highlight('#hand');misses=0}}
function completeOne(){misses=0;done=true;K.sfx.ok();K.star(1,K.$('#hand'));feedback('安全动作完成','ok');if(phase===0){K.levels(2,1);phase=1;done=false;lab.classList.remove('safe-waft');K.$('#unknown').classList.add('teach-hl');setTimeout(function(){K.$('#unknown').classList.remove('teach-hl')},1600)}else{K.levels(2,2);K.finish({title:'安全行动完成',sub:'陌生用品不随意碰',again:reset})}}
function choose(id){if(!K.started)return;if(phase===0){if(id==='waft'){lab.classList.add('safe-waft');completeOne()}else{hint()}return}if(id==='retreat'){lab.classList.add('safe-retreat');K.$('#unknown').classList.add('hide');K.$('#teacher').classList.add('teach-hl');setTimeout(function(){K.$('#teacher').classList.remove('teach-hl')},1200);feedback('退开后找老师','ok');selected='retreated';K.sfx.ok();return}if(id==='ask'&&selected==='retreated'){K.$('#teacher').classList.add('teach-hl');setTimeout(function(){K.$('#teacher').classList.remove('teach-hl')},1200);completeOne();return}if(id==='waft'){hint()}}
['waft','retreat','ask'].forEach(function(id){var b=K.$('#'+id);b.addEventListener('click',function(){choose(id)});K.drag(b,{enabled:function(){return K.started},targets:function(){return [K.$('#jar'),K.$('#unknown'),K.$('#teacher')]},onTap:function(){choose(id)},onDrop:function(el,target){if(id==='waft'&&target===K.$('#jar'))choose('waft');else if(id==='retreat'&&target===K.$('#unknown'))choose('retreat');else if(id==='ask'&&target===K.$('#teacher'))choose('ask');else hint()}})});
K.$('#hand').addEventListener('click',function(){choose('waft')});K.drag(K.$('#hand'),{enabled:function(){return K.started&&phase===0},targets:function(){return [K.$('#jar')]},onTap:function(){choose('waft')},onDrop:function(el,target){if(target)choose('waft');else hint()}});
function reset(){phase=0;misses=0;selected=null;done=false;lab.className='';K.$('#unknown').classList.remove('hide');K.$('#feedback').textContent='';K.levels(2,0)}
K.onStart=reset;
K.onState=function(state){if(state.demo==='waft'){K.begin();phase=0;K.levels(2,0);lab.classList.add('safe-waft');K.highlight('#hand');K.highlight('#jar');feedback('手在容器上方轻轻扇动','ok')}if(state.phase==='play'){K.begin();reset();feedback('请安排安全动作')}};
K.levels(2,0);
})();
