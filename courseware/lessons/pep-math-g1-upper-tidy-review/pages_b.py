from kit import page


def p05():
    body = '''
<div id="train" class="nocheck"><div id="loco">🚂</div><div id="wagons"></div></div><div id="rail"></div>
<div id="station"><div id="numberTray"></div><button class="btn green" id="btn-check" disabled>检查 ✔</button></div>'''
    css = '''
#train{position:absolute;left:10px;top:60px;width:1200px;height:200px;display:flex;align-items:flex-end;gap:10px;transition:transform 1.6s ease-in}
#loco{width:130px;font-size:118px;line-height:1;text-align:center;padding-bottom:14px}
#wagons{display:flex;gap:10px}
.wagon{position:relative;width:150px;height:178px;border-radius:18px;border:5px solid rgba(0,0,0,.18);display:flex;align-items:center;justify-content:center}
.wagon::before,.wagon::after{content:'';position:absolute;bottom:-20px;width:38px;height:38px;border-radius:50%;background:#5B3A1E;border:6px solid #C9A36A}
.wagon::before{left:20px}.wagon::after{right:20px}
.wagon .slot{width:116px;height:116px;border-radius:20px;border:4px dashed rgba(255,255,255,.9);background:rgba(255,255,255,.28);display:flex;align-items:center;justify-content:center}
.wagon.bad{animation:shake .45s}
#rail{position:absolute;left:0;top:270px;width:1232px;height:14px;border-radius:7px;background:#8E5820;box-shadow:0 8px 0 #C99A5A}
#station{position:absolute;left:0;top:330px;width:1232px;height:222px;display:flex;align-items:center;gap:30px;padding:0 30px;background:#FFF9E8;border:4px solid var(--line);border-radius:36px}
#numberTray{flex:1;height:170px;display:flex;gap:20px;align-items:center;justify-content:center;border-radius:28px;background:repeating-linear-gradient(90deg,#F4D9A8 0 30px,#EBC98F 30px 34px);padding:0 20px}
.ncard{width:118px;height:118px;border-radius:26px;display:flex;align-items:center;justify-content:center;font-size:84px;font-weight:900;color:#fff;text-shadow:0 4px 0 rgba(0,0,0,.25);box-shadow:0 8px 0 rgba(0,0,0,.2);cursor:grab;position:relative}
.ncard.sel{outline:6px solid #FF6B35;outline-offset:4px}
.ncard.lock{cursor:default;opacity:.92}
#btn-check{height:84px;font-size:34px;padding:0 34px}
'''
    js = r'''
(function(){
var COL=['#E4572E','#F6A935','#58B45C','#4C8DDB','#8B5CF6','#E0508F'],WC=['#FFD6A5','#FDFFB6','#CAFFBF','#9BF6FF','#BDB2FF','#FFC6FF'];
var level=0,tries=0,sel=null,wag=[],cards=[];
K.hud({icon:'🚂',title:'数字小火车',levels:2});K.owl();K.say('把数字卡片排成队，从 0 开始');
K.ready({emoji:'🚂',title:'数字小火车',sub:'把数字宝宝送上车厢，从 0 开始排队！',btn:'start-btn'});
var wagons=K.$('#wagons'),tray=K.$('#numberTray');
for(var i=0;i<6;i++){var w=K.el('div','wagon','<div class="slot" data-i="'+i+'"></div>',wagons);w.style.background=WC[i];w.id='wagon-'+i;wag.push(w)}
for(var n=0;n<6;n++){var c=K.el('div','ncard',String(n));c.id='num-card-'+n;c.dataset.v=n;c.style.background=COL[n];cards.push(c)}
function slotOf(i){return K.$('.slot',wag[i])}
function val(i){var s=slotOf(i),c=s.firstElementChild;return c?+c.dataset.v:null}
function refresh(){var full=true;for(var i=0;i<6;i++)if(val(i)===null)full=false;K.$('#btn-check').disabled=!full}
function toTray(c){c.classList.remove('sel');tray.appendChild(c)}
function place(c,i,force){var s=slotOf(i),old=s.firstElementChild;if(old&&old!==c){if(old.classList.contains('lock')&&!force)return false;toTray(old)}c.classList.remove('sel');s.appendChild(c);K.sfx.drop();refresh();return true}
function setup(lv){level=lv;tries=0;sel=null;K.levels(2,lv);cards.forEach(function(c){c.classList.remove('lock');toTray(c)});wag.forEach(function(w){w.classList.remove('bad')});
 K.$('#train').style.transition='none';K.$('#train').style.transform='';void K.$('#train').offsetWidth;K.$('#train').style.transition='';
 tray.innerHTML='';
 if(lv===0){K.shuffle(cards).forEach(function(c){tray.appendChild(c)});K.say('把数字卡片排成队，从 0 开始')}
 else{var fixed=[0,1,3,5];cards.forEach(function(c){if(fixed.indexOf(+c.dataset.v)>=0){place(c,+c.dataset.v,true);c.classList.add('lock')}else tray.appendChild(c)});K.say('车厢里少了数字，把它们补上')}
 refresh()}
cards.forEach(function(c){K.drag(c,{enabled:function(el){return K.started&&!el.classList.contains('lock')},targets:function(){return K.$$('.slot')},
 onTap:function(el){if(!K.started||el.classList.contains('lock'))return;K.sfx.pick();if(sel)sel.classList.remove('sel');sel=el;el.classList.add('sel')},
 onDrop:function(el,t){if(t){place(el,+t.dataset.i)}}})});
K.$$('.slot').forEach(function(s){s.addEventListener('click',function(){if(sel&&K.started){place(sel,+s.dataset.i);sel=null}})});
tray.addEventListener('click',function(e){if(e.target===tray&&sel){toTray(sel);sel=null;refresh()}});
function check(){if(!K.started)return;var bad=[];for(var i=0;i<6;i++)if(val(i)!==i)bad.push(i);
 if(!bad.length){K.sfx.win();K.confetti();K.star(level===0?2:1,K.$('#btn-check'));K.say(level===0?'排对了！0 是起点，一个比一个多 1':'补齐了！火车出发','ok');K.$('#train').style.transform='translateX(1300px)';
  setTimeout(function(){if(level===0)setup(1);else{K.levels(2,2);K.finish({title:'火车开走啦！',sub:'数字从 0 开始，一个比一个多 1',again:function(){setup(0)}})}},2100);return}
 tries++;K.sfx.no();bad.forEach(function(i){var w=wag[i];w.classList.remove('bad');void w.offsetWidth;w.classList.add('bad');var c=slotOf(i).firstElementChild;if(c&&!c.classList.contains('lock'))toTray(c)});refresh();
 if(tries===1)K.say(val(0)!==0&&bad.indexOf(0)>=0?'0 表示没有，是数字队伍的起点，排最前面':'再想想：数字一个比一个多 1','no');
 else if(tries===2)K.say('车厢抖动的，是放错的位置','no');
 else{var i0=bad[0],c0=cards[i0];place(c0,i0,true);c0.classList.add('lock');K.say('老师帮你放好了第一个，接着排','no')}}
K.$('#btn-check').addEventListener('click',check);
K.onState=function(s){if(s.completedSteps){s.completedSteps.forEach(function(i){var c=K.$('#num-card-'+i);if(c&&c.parentNode===tray)place(c,i)})}};
K.onReveal=function(){};
setup(0);
window.__test=async function(){var R=[],ok=function(n,v){K.check(R,n,v)};
 K.sim.click(K.$('#start-btn'));await K.cp('开始后');
 var order=[3,1,0,2,5,4];order.forEach(function(v,i){K.sim.drag(K.$('#num-card-'+v),K.$('.slot[data-i="'+i+'"]'))});await K.wait(100);
 ok('放满后可检查',!K.$('#btn-check').disabled);await K.cp('排错的火车');
 K.sim.click(K.$('#btn-check'));await K.wait(300);ok('错误提示',K.$('#say').className==='no');ok('错牌回托盘',tray.children.length>=4);await K.cp('检查后');
 for(var i=0;i<6;i++)K.sim.drag(K.$('#num-card-'+i),K.$('.slot[data-i="'+i+'"]'));await K.wait(100);
 K.sim.click(K.$('#btn-check'));await K.wait(2400);ok('进入第2关',level===1);await K.cp('第2关');
 K.sim.drag(K.$('#num-card-2'),K.$('.slot[data-i="2"]'));K.sim.drag(K.$('#num-card-4'),K.$('.slot[data-i="4"]'));await K.wait(100);
 K.sim.click(K.$('#btn-check'));await K.wait(2400);ok('完成页',!K.$('#finish').classList.contains('gone'));await K.cp('完成');
 K.$('#btn-again').click();await K.wait(100);ok('再玩一次',level===0);
 window.postMessage({type:'SET_WIDGET_STATE',state:{currentStep:1,completedSteps:[0]}},'*');await K.wait(100);ok('老师示范放0',val(0)===0);await K.cp('老师示范');
 return R};
})();
'''
    return page('数字小火车', body, css, js)


def p08():
    body = '''
<div id="gl" class="panel"><div class="gt">左边</div><div id="left-group"></div></div>
<div id="lane"><svg id="lines" viewBox="0 0 560 420"></svg><div id="feedback"></div><div id="eq"></div></div>
<div id="gr" class="panel"><div class="gt">右边</div><div id="right-group"></div></div>
<div id="bar"><button class="btn blue" id="btn-pair">连一连 🔗</button>
<div id="croc"><div class="eyes nocheck"><i></i><i></i></div><div id="mouth">?</div></div>
<div id="sign-buttons"><button class="btn red" id="sg-lt" data-s="lt">＜</button><button class="btn green" id="sg-eq" data-s="eq">＝</button><button class="btn" id="sg-gt" data-s="gt">＞</button></div></div>'''
    css = '''
.panel{position:absolute;top:0;width:300px;height:420px;background:#fff;border:4px solid var(--line);border-radius:32px;padding:14px}
#gl{left:20px}#gr{right:20px}
.gt{font-size:24px;font-weight:800;color:#B79565;text-align:center;height:30px}
#left-group,#right-group{position:relative;height:340px}
.it{position:absolute;width:76px;height:76px;font-size:62px;line-height:76px;text-align:center;transition:transform .3s,opacity .4s}
.it.extra{animation:ext .9s ease-in-out infinite}
@keyframes ext{50%{transform:scale(1.25)}}
.it.eaten{transform:scale(0);opacity:0}
#lane{position:absolute;left:340px;top:0;width:560px;height:420px}
#lines{position:absolute;left:0;top:0;width:560px;height:420px}
#lines line{stroke:#58B45C;stroke-width:6;stroke-linecap:round;stroke-dasharray:480;stroke-dashoffset:480;animation:dr .35s forwards}
@keyframes dr{to{stroke-dashoffset:0}}
#feedback{position:absolute;left:30px;right:30px;top:18px;min-height:64px;line-height:1.3;padding:10px 18px;border-radius:24px;text-align:center;font-size:28px;font-weight:800;color:var(--ink2);background:#FFF7D6;border:3px solid #F2C94C;visibility:hidden}
#feedback.on{visibility:visible}
#feedback.ok{background:#E9F8E5;border-color:#7CC77F;color:#2F7A36}
#feedback.no{background:#FFF0E6;border-color:#F0A070;color:#B24A1C}
#eq{position:absolute;left:0;right:0;top:250px;text-align:center;font-size:96px;font-weight:900;color:var(--ink2);letter-spacing:10px;height:110px;line-height:110px}
#bar{position:absolute;left:0;top:432px;width:1232px;height:120px;display:flex;align-items:center;justify-content:center;gap:50px}
#croc{position:relative;width:170px;height:110px;border-radius:50px 50px 40px 40px;background:#6CC24A;border:5px solid #3E8E2A;display:flex;align-items:flex-end;justify-content:center}
#croc .eyes{position:absolute;top:-22px;left:0;right:0;display:flex;justify-content:space-around;padding:0 18px}
#croc .eyes i{width:38px;height:38px;border-radius:50%;background:#fff;border:5px solid #3E8E2A;position:relative}
#croc .eyes i::after{content:'';position:absolute;left:11px;top:11px;width:10px;height:10px;border-radius:50%;background:#222}
#mouth{font-size:72px;font-weight:900;color:#fff;text-shadow:0 3px 0 #2d6a1f;line-height:96px}
#sign-buttons{display:flex;gap:18px}
#sign-buttons .btn{width:110px;height:96px;font-size:60px;padding:0}
'''
    js = r'''
(function(){
var R=[{l:['🦆',3],r:['🥕',4]},{l:['🐰',5],r:['🥕',2]},{l:['🍎',4],r:['🍎',4]},{l:['🐟',2],r:['🐱',3]}];
var ri=0,tries=0,locked=false,paired=false,SG={lt:'＜',eq:'＝',gt:'＞'};
K.hud({icon:'🐊',title:'饿鳄鱼比大小',levels:4});K.owl();K.say('先数一数，再请鳄鱼张嘴');
K.ready({emoji:'🐊',title:'饿鳄鱼比大小',sub:'鳄鱼的大嘴，总是朝着多的那一边！',btn:'start-btn'});
function items(box,e,n){box.innerHTML='';for(var i=0;i<n;i++){var d=K.el('div','it',e,box);d.id=box.id.charAt(0)+'-it-'+i;d.style.left=(110)+'px';d.style.top=(i*66)+'px'}}
function sign(){var q=R[ri],a=q.l[1],b=q.r[1];return a>b?'gt':(a<b?'lt':'eq')}
function load(i){ri=i;tries=0;locked=false;paired=false;var q=R[i];items(K.$('#left-group'),q.l[0],q.l[1]);items(K.$('#right-group'),q.r[0],q.r[1]);K.$('#lines').innerHTML='';
 K.$('#mouth').textContent='?';K.$('#eq').textContent='';var f=K.$('#feedback');f.className='';f.textContent='';K.levels(4,i);K.$('#btn-pair').disabled=false;K.say('先数一数，再请鳄鱼张嘴')}
function pair(){if(!K.started||paired)return;paired=true;K.$('#btn-pair').disabled=true;var q=R[ri],m=Math.min(q.l[1],q.r[1]),svg=K.$('#lines');
 for(var i=0;i<m;i++){(function(i){setTimeout(function(){K.sfx.tick(i);var ln=document.createElementNS('http://www.w3.org/2000/svg','line');var y=40+i*66;ln.setAttribute('x1',0);ln.setAttribute('y1',y);ln.setAttribute('x2',560);ln.setAttribute('y2',y);svg.appendChild(ln)},i*320)})(i)}
 setTimeout(function(){var big=q.l[1]>q.r[1]?'l':(q.l[1]<q.r[1]?'r':null);if(big){for(var k=m;k<Math.max(q.l[1],q.r[1]);k++){var e=K.$('#'+big+'-it-'+k);if(e)e.classList.add('extra')}K.say('多出来的，是不是在更多的那一边？')}else K.say('一个对一个，正好都连上了')},m*320+200)}
function say(t,k){var f=K.$('#feedback');f.className='on '+(k||'');f.textContent=t}
function choose(s,demo,fb){var q=R[ri];K.$('#mouth').textContent=SG[s];K.pop(K.$('#croc'));
 var a=q.l[1],b=q.r[1];if(s===sign()){locked=true;var big=a>b?'l':(a<b?'r':null);K.sfx.ok();
  var txt=fb||('选对了！'+a+(s==='lt'?'小于':s==='gt'?'大于':'等于')+b+'。');say(txt,'ok');K.$('#eq').textContent=a+' '+SG[s]+' '+b;
  if(big){var n=Math.min(a,b);for(var k=n;k<Math.max(a,b);k++){var ex=K.$('#'+big+'-it-'+k);if(ex)ex.classList.add('extra')}}
  if(demo)return;K.confetti();K.star(tries===0?2:1,K.$('#croc'));K.say('对啦！鳄鱼最爱吃多的那边','ok');
  setTimeout(function(){if(ri<R.length-1)load(ri+1);else{K.levels(4,4);K.finish({title:'鳄鱼吃饱啦！',sub:'张嘴的方向，总是朝着多的那一边',again:function(){load(0)}})}},2300)}
 else{if(demo)return;tries++;K.sfx.no();K.shake(K.$('#croc'));say('不对哦，再看一眼','no');
  if(tries===1){K.say('先点“连一连”，看看哪边多出来','no');K.highlight('#btn-pair')}
  else if(tries===2){K.say('多出来的那边更多，鳄鱼要朝着它','no');if(!paired)pair()}
  else{K.say('看，这个符号的大嘴朝着多的那边','no');K.highlight('#sg-'+sign())}}}
K.$$('#sign-buttons .btn').forEach(function(b){b.addEventListener('click',function(){if(!K.started||locked)return;K.sfx.pick();choose(b.dataset.s)})});
K.$('#btn-pair').addEventListener('click',pair);
load(0);
K.onState=function(s){if('selectedSign' in s){if(s.selectedSign===null){load(ri)}else{locked=false;choose(s.selectedSign,true,s.feedback);locked=true}}};
window.__test=async function(){var R2=[],ok=function(n,v){K.check(R2,n,v)};
 K.sim.click(K.$('#start-btn'));await K.cp('开始后');
 K.sim.click(K.$('#btn-pair'));await K.wait(1600);ok('连线数=3',K.$$('#lines line').length===3);ok('多出来的闪动',K.$$('.it.extra').length===1);await K.cp('连一连');
 K.sim.click(K.$('#sg-gt'));ok('先提示连一连',/连一连/.test(K.$('#say').textContent));await K.cp('选错');
 K.sim.click(K.$('#sg-lt'));await K.wait(200);ok('选对反馈',/选对了/.test(K.$('#feedback').textContent));ok('等式3＜4',/3 ＜ 4/.test(K.$('#eq').textContent));await K.cp('选对');await K.wait(2600);
 ok('下一题',ri===1);K.sim.click(K.$('#sg-gt'));await K.wait(2600);ok('第三题',ri===2);K.sim.click(K.$('#sg-eq'));await K.wait(2600);ok('第四题',ri===3);
 K.sim.click(K.$('#sg-lt'));await K.wait(2600);ok('完成页',!K.$('#finish').classList.contains('gone'));await K.cp('完成');
 K.$('#btn-again').click();await K.wait(100);ok('重玩',ri===0);
 window.postMessage({type:'SET_WIDGET_STATE',state:{selectedSign:'lt',feedback:'选对了！3小于4。'}},'*');await K.wait(100);ok('老师示范',/选对了！3小于4/.test(K.$('#feedback').textContent));await K.cp('老师示范');
 window.postMessage({type:'SET_WIDGET_STATE',state:{selectedSign:null,feedback:''}},'*');await K.wait(100);ok('老师重置',K.$('#mouth').textContent==='?');
 return R2};
})();
'''
    return page('饿鳄鱼比大小', body, css, js)


PAGES = {'p05': p05, 'p08': p08}
