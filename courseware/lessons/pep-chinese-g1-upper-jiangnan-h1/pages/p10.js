(function(){
var level=0,tries=0,drawing=false,last=null,enabled=true,busy=false;
var guide=K.$('#guide'),canvas=K.$('#trace'),g=guide.getContext('2d'),c=canvas.getContext('2d'),mask;
K.hud({icon:'🌿',title:'看一看，写一写',levels:2});K.owl();K.ready({emoji:'🌿',title:'看一看，写一写',sub:'观察字形，自由描画',btn:'start-btn'});
function clear(){c.clearRect(0,0,460,460)}
function render(){clear();g.clearRect(0,0,460,460);g.fillStyle='#d8e7d6';g.textAlign='center';g.textBaseline='middle';g.font='400px "PingFang SC", "Microsoft YaHei", sans-serif';g.fillText(level===0?'可':'叶',230,236);mask=g.getImageData(0,0,460,460).data;tries=0;enabled=true;busy=false;K.levels(2,level);K.say('沿着淡淡的字，自由描一描')}
function point(e){var r=canvas.getBoundingClientRect();return {x:(e.clientX-r.left)*460/r.width,y:(e.clientY-r.top)*460/r.height}}
function stroke(a,b){c.strokeStyle='#4c9c79';c.lineWidth=24;c.lineCap='round';c.lineJoin='round';c.beginPath();c.moveTo(a.x,a.y);c.lineTo(b.x,b.y);c.stroke()}
canvas.addEventListener('pointerdown',function(e){if(!K.started||!enabled||busy)return;e.preventDefault();drawing=true;last=point(e);stroke(last,last);canvas.setPointerCapture(e.pointerId);K.sfx.pick()});
canvas.addEventListener('pointermove',function(e){if(!drawing)return;var p=point(e);stroke(last,p);last=p});
function end(){drawing=false;last=null}canvas.addEventListener('pointerup',end);canvas.addEventListener('pointercancel',end);
function coverage(){var marks=c.getImageData(0,0,460,460).data,total=0,covered=0;for(var i=3;i<mask.length;i+=4){if(mask[i]>30){total++;if(marks[i]>30)covered++}}return total?covered/total:0}
function demo(){clear();var found=[];for(var y=60;y<400&&found.length<25;y++){for(var x=50;x<410&&found.length<25;x++){if(mask[(y*460+x)*4+3]>30)found.push({x:x,y:y})}}found.forEach(function(p){stroke(p,p)})}
K.$('#clear').addEventListener('click',function(){if(!K.started||busy)return;clear();K.sfx.pick();K.say('擦掉了，再试一试')});
K.$('#check').addEventListener('click',function(){if(!K.started||!enabled||busy)return;if(coverage()>=0.3){busy=true;K.sfx.ok();K.star(1,canvas);K.say('描过了淡字，接着试试。','ok');setTimeout(function(){if(level===0){level=1;render()}else{K.levels(2,2);K.finish({title:'描画完成',sub:'纸上写一写，请大人看看',again:reset})}},1200)}else{tries++;K.sfx.no();if(tries===1)K.say('看看淡色字的形状。','no');else if(tries===2)K.say('沿着淡色部分移动手指。','no');else{demo();K.say('看这一小段，剩下自己试。','no')}}});
function reset(){level=0;K.stars=0;K.$('#star-n').textContent='0';render()}
K.onState=function(state){if(state.demo==='trace'){level=0;render();enabled=false;demo();K.say('看老师描一小段。')}if(state.phase==='play'){clear();enabled=true;K.say('沿着淡淡的字，自由描一描')}};
render();
})();
