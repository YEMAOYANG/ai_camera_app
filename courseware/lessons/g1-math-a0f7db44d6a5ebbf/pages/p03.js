(function(){
var tasks=[[6,5],[8,6],[9,3]],lev=0,a=6,b=5,moved=0,demo=false,busy=false,miss=0,timer;
K.hud({icon:'＋',title:'接着数，走几步',levels:tasks.length});K.owl();K.ready({emoji:'＋',title:'沿数线接着走',sub:'每点一次，向前走一步'});
for(var n=0;n<=20;n++){var e=K.el('b','tick',String(n),K.$('#line-ticks'));e.style.left=(n*5)+'%'}
function draw(){K.$('#add-a').textContent=a;K.$('#add-b').textContent=b;K.$('#sum-blank').textContent=(busy||demo)&&moved===b?a+b:'?';K.$('#walk-dot').style.left=((a+moved)*5)+'%';K.$('#step-dots').innerHTML='';for(var i=0;i<b;i++)K.el('i',i<moved?'filled':'','',K.$('#step-dots'));K.$('#walk-result').textContent=(busy||demo)&&moved===b?a+'＋'+b+'＝'+(a+b):'＋'+moved;K.$('#reset-walk').classList.toggle('hide',moved<=b);K.levels(tasks.length,lev)}
function load(){a=tasks[lev][0];b=tasks[lev][1];moved=0;busy=false;miss=0;draw();K.say('从'+a+'出发，再向前走'+b+'步。')}
function reset(){clearTimeout(timer);demo=false;busy=false;lev=0;K.stars=0;K.$('#star-n').textContent='0';load()}
function step(){if(demo||busy)return;if(a+moved<20){moved++;K.sfx.tick(moved);draw()}}
function check(){if(demo||busy)return;if(moved!==b){miss++;K.sfx.no();K.say(miss===1?'添几个就走几步，先看看上面的步数记录。':'走少了可以继续，走过头点回转重走。','no');return}if(moved===b){busy=true;draw();K.star(1,K.$('#walk-dot'));K.sfx.ok();K.say('添几个就走几步，落点就是总数。','ok');timer=setTimeout(function(){lev++;if(lev===tasks.length)K.finish({title:'接着数走对啦',sub:'从第一个数后面接着走。',again:reset});else load()},1000)}}
K.$('#go-one').onclick=step;K.$('#check-walk').onclick=check;K.$('#reset-walk').onclick=function(){if(demo||busy)return;moved=0;draw()};K.onStart=reset;K.onState=function(state){if(state.demo){clearTimeout(timer);var finish=K.$("#finish");if(finish)finish.classList.add("gone");K.stars=0;K.$("#star-n").textContent="0";demo=true;busy=false;lev=0;K.say("先看老师示范，再轮到你。");a=7;b=6;moved=0;draw()}if(state.step!==undefined&&demo){moved=Math.max(0,Math.min(b,state.step));draw()}if(state.play)reset()};load();
})();