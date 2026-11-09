(function(){
var words=['用','马','牙','竹','几'],level=0,busy=false,down=false,previous=null,mask=[],seen={},timer;
var guide=K.$('#trace-guide'),ink=K.$('#trace-ink'),g=guide.getContext('2d'),ctx=ink.getContext('2d'),next=K.$('#trace-next'),clear=K.$('#trace-reset'),fill=K.$('#trace-fill');
K.hud({icon:'笔',title:'五个字，慢慢描',levels:5});K.owl();K.ready({emoji:'◌',title:'五个字，慢慢描',sub:'沿淡字描画，纸上再练习'});
function paintGuide(){g.clearRect(0,0,440,440);g.strokeStyle='#c7dcd0';g.lineWidth=2;g.setLineDash([9,9]);g.beginPath();g.moveTo(220,0);g.lineTo(220,440);g.moveTo(0,220);g.lineTo(440,220);g.stroke();g.setLineDash([]);g.fillStyle='#d7ddd0';g.font='350px "Kaiti SC","STKaiti","KaiTi",serif';g.textAlign='center';g.textBaseline='middle';g.fillText(words[level],220,237);var m=document.createElement('canvas');m.width=m.height=440;var c=m.getContext('2d');c.font=g.font;c.textAlign='center';c.textBaseline='middle';c.fillText(words[level],220,237);var pixels=c.getImageData(0,0,440,440).data;mask=[];for(var y=14;y<426;y+=8)for(var x=14;x<426;x+=8)if(pixels[(y*440+x)*4+3]>50)mask.push([x,y,x+':'+y]);K.$('#trace-word').textContent=words[level];K.$$('.small-words span').forEach(function(s,i){s.classList.toggle('current',i===level);s.classList.toggle('done',i<level)})}
function erase(){down=false;previous=null;ctx.clearRect(0,0,440,440);seen={};fill.style.width='0%';next.disabled=true}
function show(){clearTimeout(timer);busy=false;paintGuide();erase();K.levels(5,level);K.say('沿着淡色字慢慢描，画错可以清除。')}
function reset(){level=0;K.stars=0;K.$('#star-n').textContent='0';show()}
function pos(e){var r=ink.getBoundingClientRect();return [(e.clientX-r.left)*440/r.width,(e.clientY-r.top)*440/r.height]}
function distance(p,a,b){var dx=b[0]-a[0],dy=b[1]-a[1],d=dx*dx+dy*dy,t=d?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/d)):0;return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)}
function line(a,b){ctx.strokeStyle='#398d85';ctx.lineWidth=18;ctx.lineCap='round';ctx.lineJoin='round';ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();mask.forEach(function(p){if(distance(p,a,b)<17)seen[p[2]]=true});var ratio=mask.length?Object.keys(seen).length/mask.length:0;fill.style.width=Math.min(100,Math.round(ratio*100))+'%';next.disabled=ratio<.18;if(!next.disabled)K.say('描迹已经留下了；对勾可进入下一个字。','ok')}
ink.addEventListener('pointerdown',function(e){if(!K.started||busy)return;e.preventDefault();down=true;previous=pos(e);line(previous,previous);try{ink.setPointerCapture(e.pointerId)}catch(ignore){}});
ink.addEventListener('pointermove',function(e){if(!down||busy)return;e.preventDefault();var p=pos(e);line(previous,p);previous=p});
function stop(){down=false;previous=null}ink.addEventListener('pointerup',stop);ink.addEventListener('pointercancel',stop);ink.addEventListener('lostpointercapture',stop);
clear.addEventListener('click',function(){if(!K.started||busy)return;erase();K.sfx.pick();K.say('清干净了，沿淡字再试一遍。')});
next.addEventListener('click',function(){if(next.disabled||busy)return;busy=true;K.star(1,next);K.sfx.ok();K.say('这里只记录描到的范围，纸笔书写还要观察。','ok');timer=setTimeout(function(){level++;if(level===5){K.levels(5,5);K.finish({title:'五个字都描过了',sub:'请大人看纸上的字形和笔顺',again:reset})}else show()},850)});
K.onStart=reset;K.onState=function(s){if(s.demo==='trace'){reset();busy=true;var first=mask[0],last=mask.find(function(p){return first&&Math.abs(p[1]-first[1])<4&&p[0]>first[0]+32});if(first&&last)line(first,last);K.say('这是一小段描迹，不是完整笔顺。')}if(s.phase==='play')reset()};
})();
