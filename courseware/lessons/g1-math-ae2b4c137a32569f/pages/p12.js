K.hud({icon:'◆',title:"沿着箭头走",levels:3});K.owl();
function cleanStars(){K.stars=0;K.$('#star-n').textContent='0';}
function finished(){K.finish({title:'活动完成',sub:'记录的是这次动手过程',again:reset});}

var plans=[['u','u','r','r'],['r','u','u','u'],['u','r','r','r']],level=0,step=0,row=3,col=0,wrong=0,timer=null,busy=false;
function render(){K.$('#route-grid').innerHTML='';var target=plans[level].reduce(function(p,a){return [p[0]-(a==='u'?1:0),p[1]+(a==='r'?1:0)]},[3,0]);for(var r=0;r<4;r++)for(var c=0;c<5;c++){var cell=K.el('div','route-cell'+(r===target[0]&&c===target[1]?' goal':''),'',K.$('#route-grid'));if(r===row&&c===col)K.el('i','route-person','',cell);}K.$('#route-plan').innerHTML='';var segment=null,last=null;plans[level].forEach(function(a,i){if(a!==last){segment=K.el('div','route-segment','',K.$('#route-plan'));last=a;}var arrow=K.el('i',i<step?'done':i===step?'current':'',a==='u'?'↑':'→',segment);});K.levels(3,level);}
function startLevel(){step=0;row=3;col=0;wrong=0;busy=false;render();K.say('从橙点开始，按左边的箭头依次走。');}
function reset(){clearTimeout(timer);level=0;cleanStars();startLevel();}
function move(dir){if(busy)return;if(dir!==plans[level][step]){wrong++;K.sfx.no();K.say(wrong===1?'先看当前这段箭头，按顺序走。':'前一段走完，才开始后一段。','no');K.shake(K.$('#route-plan'));if(wrong>=3)K.highlight('#route-plan');return;}row-=dir==='u'?1:0;col+=dir==='r'?1:0;step++;K.star(1,K.$('#route-grid'));K.sfx.tick(step);render();if(step===plans[level].length){busy=true;K.say('方向、步数和先后顺序都对上了。','ok');level++;K.levels(3,level);timer=setTimeout(function(){if(level===plans.length)finished();else startLevel();},650);}else K.say('这一格已经走好，再看接下来的箭头。','ok');}
K.$('#route-up').onclick=function(){move('u')};K.$('#route-right').onclick=function(){move('r')};K.$('#route-reset').onclick=function(){clearTimeout(timer);K.stars=level*4;K.$('#star-n').textContent=String(K.stars);startLevel()};
K.onState=function(state){if(state.demo){reset();step=Math.max(0,Math.min(2,Number(state.step)||0));row=3-step;col=0;render();}else if(state.demo===false){reset();}};K.onStart=reset;K.ready({emoji:'◆',title:'沿着箭头走',sub:'一格一步，方向和顺序都要看'});
