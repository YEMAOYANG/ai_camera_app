from kit import page

APPLE = ('<svg viewBox="0 0 100 100"><path d="M50 30C36 16 10 24 12 52c2 22 18 40 32 38 3 0 4-2 6-2s3 2 6 2c14 2 30-16 32-38 2-28-24-36-38-22z" fill="#E4372E"/>'
         '<path d="M50 30c-2-12 4-22 16-26-1 12-6 22-16 26z" fill="#4CAF50"/><ellipse cx="32" cy="48" rx="7" ry="12" fill="#fff" opacity=".35" transform="rotate(20 32 48)"/></svg>')


def p04():
    body = '''
<div id="apples"><div id="basket"></div></div><div id="basket-front"></div>
<div id="side">
  <div id="count-card"><div id="count-num">0</div><div id="count-hint">数到几<br>就是几</div></div>
  <div id="order-card" class="hide"><div id="ticket"><div class="t-top">送货单</div><div class="t-num" id="order-num">3</div><div class="t-sub">个苹果</div></div><div id="deliver"></div></div>
  <div id="btns"><button class="btn green hide" id="btn-next">去送货 ➜</button><button class="btn hide" id="btn-send">送货 🚚</button><button class="btn ghost" id="btn-reset">重置 ↺</button></div>
</div>'''
    css = '''
#apples{position:absolute;left:0;top:0;width:700px;height:552px}
#basket{position:absolute;left:20px;top:300px;width:660px;height:236px;border-radius:30px 30px 70px 70px;background:repeating-linear-gradient(90deg,#D9A25B 0 26px,#C98B43 26px 30px);border:5px solid #A86B2A;box-shadow:inset 0 18px 24px rgba(0,0,0,.2)}
#basket-front{position:absolute;left:20px;top:372px;width:660px;height:164px;border-radius:0 0 70px 70px;background:repeating-linear-gradient(0deg,#E0AA62 0 24px,#C98B43 24px 28px);border:5px solid #A86B2A;border-top:8px solid #8E5820;pointer-events:none;z-index:3}
.apple{position:absolute;width:124px;height:124px;cursor:pointer;transition:transform .15s;z-index:2}
.apple svg{width:100%;height:100%;filter:drop-shadow(0 8px 6px rgba(0,0,0,.25))}
.apple .badge{position:absolute;right:-8px;top:-10px;width:56px;height:56px;border-radius:50%;background:#fff;border:4px solid var(--gr);color:var(--gr2);font-size:34px;font-weight:900;display:none;align-items:center;justify-content:center}
.apple.counted .badge{display:flex}
.apple.counted{transform:translateY(-16px)}
.apple.picked{transform:translateY(-16px) scale(.92);opacity:.55}
.apple.picked::after{content:'✓';position:absolute;left:36px;top:30px;font-size:60px;font-weight:900;color:#fff;text-shadow:0 3px 6px rgba(0,0,0,.4)}
#side{position:absolute;left:730px;top:0;width:502px;height:552px}
#count-card{display:flex;align-items:center;gap:22px;background:#fff;border:4px solid var(--line);border-radius:36px;padding:0 26px;height:232px}
#count-num{flex:none;width:180px;height:180px;border-radius:50%;background:radial-gradient(circle at 35% 30%,#FFE08A,#F6A935);border:8px solid #fff;box-shadow:0 0 0 6px #F6A935;display:flex;align-items:center;justify-content:center;font-size:120px;font-weight:900;color:#fff;text-shadow:0 4px 0 #C47A12}
#count-hint{font-size:36px;font-weight:800;color:var(--ink2);line-height:1.35}
#order-card{margin-top:16px;display:flex;gap:14px;height:176px}
#ticket{flex:none;width:190px;background:#FFFDF0;border:4px dashed #D9A05B;border-radius:18px;padding:6px 8px;text-align:center}
.t-top{font-size:24px;font-weight:800;color:var(--rd);line-height:1.2}
.t-num{font-size:86px;font-weight:900;line-height:1.05;color:var(--ink2)}
.t-sub{font-size:24px;font-weight:700;line-height:1.2}
#deliver{flex:1;background:repeating-linear-gradient(90deg,#EDBF7C 0 22px,#DDA55B 22px 26px);border:5px solid #A86B2A;border-radius:18px;padding:10px;display:flex;flex-wrap:wrap;gap:6px;align-content:flex-start}
#deliver .mini{width:56px;height:56px}
#deliver .mini svg{width:100%;height:100%}
#btns{position:absolute;left:0;bottom:0;width:100%;display:flex;gap:16px;justify-content:center}
'''
    js = r'''
(function(){
var APPLE='''+repr(APPLE)+''';
var IDS=['item-1','item-2','item-3','item-4','item-5'],ORD=[3,5,0,4],POS=[[40,150],[290,150],[540,150],[165,250],[415,250]];
var phase='count',counted=[],picked=[],oi=0,tries=0,locked=false,auto=false;
K.hud({icon:'🍎',title:'数一数货篮',levels:5});K.owl();K.say('点苹果，一个一个数');
K.ready({emoji:'🍎',title:'数一数货篮',sub:'点苹果，数到几就是几！',btn:'start-btn'});
var apples=K.$('#apples');
IDS.forEach(function(id,i){var a=K.el('div','apple',APPLE+'<span class="badge"></span>',apples);a.id=id;a.style.left=POS[i][0]+'px';a.style.top=POS[i][1]+'px';a.addEventListener('click',function(){tap(id)})});
function num(){K.$('#count-num').textContent=phase==='count'?counted.length:picked.length}
function clearApples(){IDS.forEach(function(id){var a=K.$('#'+id);a.classList.remove('counted','picked');K.$('.badge',a).textContent=''})}
function tap(id){if(!K.started||locked)return;var a=K.$('#'+id);
 if(phase==='count'){if(counted.indexOf(id)>=0)return;counted.push(id);a.classList.add('counted');K.$('.badge',a).textContent=counted.length;K.sfx.tick(counted.length);K.pop(a);num();
  if(counted.length===5)doneCount();else K.say('数到 '+counted.length+'，接着数下一个')}
 else{var i=picked.indexOf(id);if(i>=0){picked.splice(i,1);a.classList.remove('picked')}else{picked.push(id);a.classList.add('picked')}K.sfx.pick();renderCrate();num()}}
function renderCrate(){var d=K.$('#deliver');d.innerHTML='';picked.forEach(function(){K.el('div','mini',APPLE,d)})}
function doneCount(){K.say('最后数到 5，一共 5 个！','ok');K.sfx.ok();K.star(1,K.$('#count-num'));K.levels(5,1);K.$('#btn-next').classList.remove('hide')}
function toOrder(){phase='order';K.$('#btn-next').classList.add('hide');K.$('#btn-send').classList.remove('hide');K.$('#order-card').classList.remove('hide');K.$('#count-hint').innerHTML='篮子里<br>有几个？';oi=0;newOrder()}
function newOrder(){tries=0;auto=false;locked=false;picked=[];clearApples();renderCrate();K.$('#order-num').textContent=ORD[oi];K.levels(5,oi+1);num();
 K.say(ORD[oi]===0?'送货单上是 0，想一想怎么送':'送货单上是几，就送几个苹果')}
function send(){if(!K.started||phase!=='order'||locked)return;var n=picked.length,t=ORD[oi];
 if(n===t){locked=true;K.sfx.win();K.confetti();var tr=K.el('div','truck','🚚',K.$('#play'));setTimeout(function(){tr.style.left='1300px'},40);setTimeout(function(){tr.remove()},1700);
  K.star(auto?0:(tries===0?2:1),K.$('#btn-send'));K.say(t===0?'0 个：一个也不用送，对啦！':'对啦！送了 '+t+' 个。','ok');
  setTimeout(function(){if(oi<ORD.length-1){oi++;newOrder()}else finish()},1900)}
 else{tries++;K.sfx.no();K.shake(K.$('#deliver'));
  if(tries===1)K.say(t===0?'0 表示没有，想一想要不要放':'再数一数，对照送货单上的数字','no');
  else if(tries===2)K.say(n>t?'多了，拿掉一个试试':'少了，再放一个试试','no');
  else{auto=true;picked=IDS.slice(0,t);clearApples();picked.forEach(function(id){K.$('#'+id).classList.add('picked')});renderCrate();num();K.say('我们一起数 '+(t?'1 到 '+t:'0 个')+'，再点送货','no')}}}
function finish(){K.levels(5,5);K.finish({title:'全部送完啦！',sub:'你送了 '+ORD.length+' 张送货单，真能干！',again:reset})}
function reset(){phase='count';counted=[];picked=[];oi=0;locked=false;clearApples();renderCrate();K.$('#order-card').classList.add('hide');K.$('#btn-send').classList.add('hide');K.$('#btn-next').classList.add('hide');K.$('#count-hint').innerHTML='数到几<br>就是几';num();K.levels(5,0);K.say('点苹果，一个一个数')}
K.$('#btn-next').addEventListener('click',toOrder);K.$('#btn-send').addEventListener('click',send);K.$('#btn-reset').addEventListener('click',function(){K.sfx.pick();reset()});
K.onState=function(s){if(phase!=='count')return;if(s.completedIds){counted=[];clearApples();s.completedIds.forEach(function(id){var a=K.$('#'+id);if(!a)return;counted.push(id);a.classList.add('counted');K.$('.badge',a).textContent=counted.length});}
 if(typeof s.currentCount==='number'){K.$('#count-num').textContent=s.currentCount;K.pop(K.$('#count-num'))}else num()};
window.__test=async function(){var R=[],ok=function(n,v){K.check(R,n,v)};
 window.postMessage({type:'HIGHLIGHT_ELEMENT',target:'#start-btn',content:'先点开始'},'*');await K.wait(120);ok('老师指开始按钮时不抢先开始',!K.started&&K.$('#start-btn').classList.contains('teach-hl'));await K.cp('老师指开始');
 K.sim.click(K.$('#start-btn'));await K.cp('开始后');
 for(var i=1;i<=5;i++){K.sim.click(K.$('#item-'+i));await K.wait(90)}
 ok('数到5',K.$('#count-num').textContent==='5');ok('出现去送货',!K.$('#btn-next').classList.contains('hide'));await K.cp('数完');
 K.sim.click(K.$('#btn-next'));await K.cp('送货单1');
 [1,2,3].forEach(function(i){K.sim.click(K.$('#item-'+i))});ok('篮子里3个',K.$('#count-num').textContent==='3');await K.cp('放了3个');
 K.sim.click(K.$('#btn-send'));await K.wait(2300);ok('进入第2单',K.$('#order-num').textContent==='5');
 [1,2,3,4].forEach(function(i){K.sim.click(K.$('#item-'+i))});K.sim.click(K.$('#btn-send'));ok('少了-先提示再数',K.$('#say').className==='no'&&/再数/.test(K.$('#say').textContent));await K.cp('第一次错');
 K.sim.click(K.$('#btn-send'));ok('第二次提示方向',/少了/.test(K.$('#say').textContent));
 K.sim.click(K.$('#item-5'));K.sim.click(K.$('#btn-send'));await K.wait(2300);ok('进入第3单',K.$('#order-num').textContent==='0');
 await K.cp('0的送货单');K.sim.click(K.$('#btn-send'));await K.wait(2300);ok('0个也能送',K.$('#order-num').textContent==='4');
 [2,3,4,5].forEach(function(i){K.sim.click(K.$('#item-'+i))});K.sim.click(K.$('#btn-send'));await K.wait(2300);
 ok('出现完成页',!K.$('#finish').classList.contains('gone'));await K.cp('完成');
 K.$('#btn-again').click();ok('可以再玩一次',K.$('#count-num').textContent==='0'&&K.$('#order-card').classList.contains('hide'));
 window.postMessage({type:'SET_WIDGET_STATE',state:{completedIds:['item-1','item-2','item-3'],currentCount:3}},'*');await K.wait(100);ok('老师示范数到3',K.$('#count-num').textContent==='3');await K.cp('老师示范');
 return R};
})();
'''
    return page('数一数货篮', body, css, js)


PAGES = {'p04': p04}
