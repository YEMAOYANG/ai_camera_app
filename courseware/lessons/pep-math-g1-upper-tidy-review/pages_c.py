from kit import page

ANIMAL_CSS = '''
#stage{position:absolute;left:0;top:118px;width:1232px;height:262px}
.an{position:absolute;top:0;width:190px;height:250px;border-radius:30px;background:#fff;border:5px solid var(--line);box-shadow:0 8px 0 #E3C9A0;cursor:pointer;transition:transform .15s,background .2s}
.an .em{position:absolute;left:0;right:0;bottom:16px;text-align:center;font-size:124px;line-height:1.1}
.an .bd{position:absolute;left:50%;top:12px;margin-left:-38px;width:76px;height:76px;border-radius:50%;background:var(--or);border:5px solid #fff;box-shadow:0 0 0 4px var(--or2);color:#fff;font-size:48px;font-weight:900;line-height:66px;text-align:center;visibility:hidden}
.an .bd.on{visibility:visible;animation:popk .35s}
.an.sel{background:#FFF1C9;border-color:var(--or);transform:translateY(-10px)}
.an.glow{background:#E9F8E5;border-color:var(--gr)}
'''


def p09():
    body = '''
<div id="pos-indicator"><span id="pi-flag">🚩</span><span id="pi-dir">从 左 数起</span><span id="pi-num"></span></div>
<button class="btn blue" id="btn-dir">换一边 ⇄</button><button class="btn green" id="btn-quest">去闯关 ➜</button>
<div id="stage"></div>
<div id="quest"><div id="q-ic">🚩</div><div id="q-txt"></div></div>'''
    css = ANIMAL_CSS + '''
#pos-indicator{position:absolute;left:0;top:6px;width:760px;height:92px;display:flex;align-items:center;gap:18px;padding:0 28px;background:#fff;border:4px solid var(--line);border-radius:46px;font-size:40px;font-weight:900;color:var(--ink2)}
#pi-flag{font-size:56px}
#pi-num{margin-left:auto;font-size:44px;color:var(--or2)}
#btn-dir{position:absolute;left:790px;top:16px}
#btn-quest{position:absolute;left:1010px;top:16px}
#quest{position:absolute;left:0;top:408px;width:1232px;height:136px;display:flex;align-items:center;gap:26px;padding:0 40px;background:#fff;border:4px solid var(--line);border-radius:36px;font-size:44px;font-weight:900;color:var(--ink2)}
#q-ic{font-size:76px}
#q-txt b{color:var(--rd);font-size:64px}
'''
    js = r'''
(function(){
var EM=['🐰','🐱','🐶','🐼','🦊'],NM=['小兔','小猫','小狗','熊猫','狐狸'];
var from=0,mode='explore',qi=0,tries=0,busy=0,QS=[{f:0,k:3},{f:1,k:2},{f:0,k:5},{f:1,k:4}],cur=-1,sels=0;
K.hud({icon:'🐰',title:'排排队数第几',levels:4});K.owl();
K.ready({emoji:'🐰',title:'排排队，数第几',sub:'先看从哪边数起，再数第几个！',btn:'start-btn'});
var stg=K.$('#stage'),ans=[];
for(var i=0;i<5;i++){(function(i){var a=K.el('div','an','<div class="bd"></div><div class="em">'+EM[i]+'</div>',stg);a.id='animal-'+(i+1);a.style.left=(61+i*230)+'px';a.addEventListener('click',function(){tap(i)});ans.push(a)})(i)}
function ord(i){return from===0?i+1:5-i}
function dirTxt(){return from===0?'左':'右'}
function render(){K.$('#pi-flag').textContent='🚩';K.$('#pi-dir').textContent='从 '+dirTxt()+' 数起';K.$('#pi-flag').style.transform=from===0?'':'scaleX(-1)'}
function clearB(){ans.forEach(function(a){var b=K.$('.bd',a);b.classList.remove('on');b.textContent='';a.classList.remove('sel','glow')})}
async function countTo(i,done){busy++;var seq=[];if(from===0){for(var k=0;k<=i;k++)seq.push(k)}else{for(var k2=4;k2>=i;k2--)seq.push(k2)}
 clearB();for(var s=0;s<seq.length;s++){var b=K.$('.bd',ans[seq[s]]);b.textContent=ord(seq[s]);b.classList.remove('on');void b.offsetWidth;b.classList.add('on');K.sfx.tick(s);await K.wait(380)}
 busy--;if(done)done()}
function setQuest(){var q=QS[qi];K.$('#q-ic').textContent='🚩';K.$('#q-ic').style.transform=q.f===0?'':'scaleX(-1)';K.$('#q-txt').innerHTML='找一找：从 '+(q.f===0?'左':'右')+' 数，第 <b>'+q.k+'</b> 个是谁？';from=q.f;render();clearB();K.levels(4,qi);tries=0;K.say('点一点，你找到的小动物')}
function tap(i){if(!K.started||busy)return;K.sfx.pick();
 if(mode==='explore'){cur=i;sels++;countTo(i,function(){ans[i].classList.add('sel');K.$('#pi-num').textContent=NM[i]+'：第 '+ord(i)+' 个';K.say('从'+dirTxt()+'边数，'+NM[i]+'是第 '+ord(i)+' 个','ok')})}
 else{var q=QS[qi],t=q.f===0?q.k-1:5-q.k;
  if(i===t){busy++;ans[i].classList.add('glow');K.sfx.ok();K.star(tries===0?2:1,ans[i]);K.say('对啦！从'+dirTxt()+'数，第 '+q.k+' 个是'+NM[i],'ok');busy--;countTo(i,function(){setTimeout(function(){if(qi<3){qi++;setQuest()}else{K.levels(4,4);K.finish({title:'数得真准！',sub:'数第几，先看从哪边数起',again:function(){qi=0;startExplore()}})}},900)})}
  else{tries++;K.sfx.no();K.shake(ans[i]);
   if(tries===1)K.say('再数一遍，先看清从哪边数起','no');else if(tries===2){K.say('看，红旗在这一边，从这里开始数','no');K.highlight('#pi-flag')}else{K.say('我们一起数：从红旗开始','no');countTo(t)}}}}
function startExplore(){mode='explore';from=0;qi=0;clearB();render();K.$('#pi-num').textContent='';K.$('#q-ic').textContent='👆';K.$('#q-ic').style.transform='';K.$('#q-txt').textContent='点一点小动物，看它排第几';K.$('#btn-quest').classList.remove('hide');K.$('#btn-dir').classList.remove('hide');K.levels(4,0);K.say('点小动物，看看它排第几')}
K.$('#btn-dir').addEventListener('click',function(){if(!K.started||busy||mode!=='explore')return;K.sfx.pick();from=1-from;render();clearB();K.$('#pi-num').textContent='';K.say('现在从'+dirTxt()+'边数起，再点一点')});
K.$('#btn-quest').addEventListener('click',function(){if(!K.started||busy)return;K.sfx.pick();mode='quest';K.$('#btn-quest').classList.add('hide');K.$('#btn-dir').classList.add('hide');qi=0;setQuest()});
K.onState=function(s){if('from' in s){from=s.from?1:0;render();clearB();K.$('#pi-num').textContent='';if(mode==='explore')K.say('现在从'+dirTxt()+'边数起')}};
startExplore();
window.__test=async function(){var R=[],ok=function(n,v){K.check(R,n,v)};
 K.sim.click(K.$('#start-btn'));await K.cp('开始后');
 K.sim.click(K.$('#animal-3'));await K.wait(1800);ok('左数第3个',/第 3 个/.test(K.$('#pi-num').textContent));await K.cp('点了小狗');
 K.sim.click(K.$('#btn-dir'));await K.wait(100);K.sim.click(K.$('#animal-3'));await K.wait(1800);ok('右数也是第3个',/第 3 个/.test(K.$('#pi-num').textContent));
 K.sim.click(K.$('#animal-2'));await K.wait(2200);ok('右数小猫第4个',/第 4 个/.test(K.$('#pi-num').textContent));await K.cp('右边数');
 K.sim.click(K.$('#btn-quest'));await K.cp('闯关1');
 K.sim.click(K.$('#animal-1'));await K.wait(200);ok('错了先提示再数',K.$('#say').className==='no');await K.cp('闯关答错');
 K.sim.click(K.$('#animal-3'));await K.wait(3600);ok('第2关',qi===1);await K.cp('闯关2');
 K.sim.click(K.$('#animal-4'));await K.wait(3600);ok('第3关',qi===2);K.sim.click(K.$('#animal-5'));await K.wait(4200);ok('第4关',qi===3);
 K.sim.click(K.$('#animal-2'));await K.wait(4000);ok('完成页',!K.$('#finish').classList.contains('gone'));await K.cp('完成');
 K.$('#btn-again').click();await K.wait(100);ok('回到探索',mode==='explore');
 window.postMessage({type:'SET_WIDGET_STATE',state:{from:1}},'*');await K.wait(100);ok('老师切到右边',from===1&&/右/.test(K.$('#pi-dir').textContent));await K.cp('老师示范');
 return R};
})();
'''
    return page('排排队数第几', body, css, js)


def p10():
    body = '''
<div id="direction-label">现在：从 左 边数</div><div id="pos-box"><span class="pl">它是第</span><b id="pos-num">?</b><span class="pl">个</span></div>
<div id="stage"></div>
<div id="dirs"><button class="btn blue" id="arrow-left">⬅ 从左数</button><button class="btn red" id="arrow-right">从右数 ➡</button></div>
<div id="quest"><div id="q-txt"></div><div id="opts"></div></div>'''
    css = ANIMAL_CSS + '''
#stage{top:116px;height:240px}
.an{height:226px}
.an .em{font-size:108px}
#direction-label{position:absolute;left:0;top:8px;width:640px;height:86px;line-height:78px;padding:0 30px;background:#fff;border:4px solid var(--line);border-radius:43px;font-size:40px;font-weight:900;color:var(--ink2)}
#pos-box{position:absolute;left:670px;top:8px;width:562px;height:86px;display:flex;align-items:center;justify-content:center;gap:14px;background:#FFF1C9;border:4px solid var(--or);border-radius:43px;font-size:36px;font-weight:800;color:var(--ink2)}
#pos-box b{font-size:60px;line-height:1;color:var(--rd);min-width:60px;text-align:center}
#dirs{position:absolute;left:0;top:362px;width:1232px;display:flex;gap:40px;justify-content:center}
#dirs .btn{width:330px;height:70px}
#dirs .btn.on{outline:6px solid #FFD166;outline-offset:3px}
#quest{position:absolute;left:0;top:452px;width:1232px;height:100px;display:none;align-items:center;gap:30px;padding:0 36px;background:#fff;border:4px solid var(--line);border-radius:36px;font-size:36px;font-weight:900;color:var(--ink2)}
#quest.on{display:flex}
#q-txt{flex:1;line-height:1.25}
#opts{display:flex;gap:16px}
#opts .btn{width:100px;height:72px;font-size:44px;padding:0}
'''
    js = r'''
(function(){
var EM=['🐰','🐱','🐶','🐼','🦊'],NM=['小兔','小猫','小狗','熊猫','狐狸'];
var dir='left',sel=-1,qi=0,busy=false,tries=0,inq=false,QS=[{i:1,ask:'right'},{i:3,ask:'left'},{i:2,ask:'right'}];
K.hud({icon:'🦊',title:'方向变了，第几也变',levels:3});K.owl();K.say('点小动物，再点方向箭头');
K.ready({emoji:'🦊',title:'方向变了，第几也变',sub:'同一只小动物，换个方向数，第几会变吗？',btn:'start-btn'});
var stg=K.$('#stage'),ans=[];
for(var i=0;i<5;i++){(function(i){var a=K.el('div','an','<div class="bd on"></div><div class="em">'+EM[i]+'</div>',stg);a.id='animal-'+(i+1);a.style.left=(61+i*230)+'px';a.addEventListener('click',function(){tap(i)});ans.push(a)})(i)}
function ord(i,d){return (d||dir)==='left'?i+1:5-i}
function render(flip){K.$('#direction-label').textContent='现在：从 '+(dir==='left'?'左':'右')+' 边数';K.$('#arrow-left').classList.toggle('on',dir==='left');K.$('#arrow-right').classList.toggle('on',dir==='right');
 ans.forEach(function(a,i){var b=K.$('.bd',a);b.textContent=ord(i);if(flip){b.classList.remove('on');void b.offsetWidth;b.classList.add('on')}});
 K.$('#pos-num').textContent=sel>=0?ord(sel):'?'}
function pick(i){sel=i;ans.forEach(function(a,k){a.classList.toggle('sel',k===i)});render(false);K.pop(K.$('#pos-box'))}
function setDir(d){dir=d;render(true);K.sfx.tick(d==='left'?1:4);if(sel>=0)K.say(NM[sel]+'：从'+(d==='left'?'左':'右')+'边数是第 '+ord(sel)+' 个','ok');else K.say('现在从'+(d==='left'?'左':'右')+'边数')}
function tap(i){if(!K.started||busy)return;K.sfx.pick();if(inq)return;pick(i);K.say(NM[i]+'：从'+(dir==='left'?'左':'右')+'边数是第 '+ord(i)+' 个','ok')}
function setQuest(){var q=QS[qi];inq=true;tries=0;K.levels(3,qi);pick(q.i);var d=q.ask==='left'?'right':'left';dir=d;render(true);
 var have=ord(q.i,d),want=ord(q.i,q.ask);K.$('#q-txt').innerHTML='从'+(d==='left'?'左':'右')+'数，'+NM[q.i]+'是第 '+have+' 个。<br>从'+(q.ask==='left'?'左':'右')+'数，它是第几个？';
 var o=K.$('#opts');o.innerHTML='';var set=[want];while(set.length<3){var x=1+K.rnd(5);if(set.indexOf(x)<0)set.push(x)}K.shuffle(set).forEach(function(n){var b=K.el('button','btn',String(n),o);b.dataset.n=n;b.addEventListener('click',function(){answer(n,b)})});
 K.$('#quest').classList.add('on');K.$('#pos-num').textContent='?';K.say('想一想，换个方向数，它是第几')}
function answer(n,b){if(busy)return;var q=QS[qi],want=ord(q.i,q.ask);K.sfx.pick();
 if(n===want){busy=true;dir=q.ask;render(true);K.sfx.ok();K.star(tries===0?2:1,b);K.say('对啦！换成从'+(q.ask==='left'?'左':'右')+'数，是第 '+want+' 个','ok');
  setTimeout(function(){busy=false;if(qi<QS.length-1){qi++;setQuest()}else{K.levels(3,3);K.finish({title:'方向和第几，你都懂啦！',sub:'同一只小动物，换个方向数，第几也会变',again:restart})}},1900)}
 else{tries++;K.sfx.no();K.shake(b);if(tries===1)K.say('再想一想：先看清从哪边数','no');else if(tries===2){K.say('点一点方向箭头，看看它变成几','no');K.highlight(q.ask==='left'?'#arrow-left':'#arrow-right')}else{dir=q.ask;render(true);K.say('看，从这边数，它是第 '+want+' 个','no')}}}
function restart(){qi=0;inq=false;sel=-1;dir='left';K.$('#quest').classList.remove('on');ans.forEach(function(a){a.classList.remove('sel')});render(true);K.levels(3,0);K.say('点小动物，再点方向箭头')}
K.$('#arrow-left').addEventListener('click',function(){if(K.started&&!busy)setDir('left')});K.$('#arrow-right').addEventListener('click',function(){if(K.started&&!busy)setDir('right')});
K.onState=function(s){if('direction' in s){dir=s.direction==='right'?'right':'left';render(true)}};
K.onReveal=function(sel){if(sel==='#pos-num'||sel==='#direction-label')render(false)};
render(false);
K.$('#stage').insertAdjacentHTML('beforeend','');
window.__test=async function(){var R=[],ok=function(n,v){K.check(R,n,v)};
 K.sim.click(K.$('#start-btn'));await K.cp('开始后');
 K.sim.click(K.$('#animal-2'));ok('左数小猫第2',K.$('#pos-num').textContent==='2');K.sim.click(K.$('#arrow-right'));await K.wait(80);ok('右数变成第4',K.$('#pos-num').textContent==='4');await K.cp('换成从右数');
 K.$('#arrow-left').click();K.$('#animal-4').click();K.$('#arrow-right').click();ok('熊猫右数第2',K.$('#pos-num').textContent==='2');await K.cp('熊猫');
 await K.$('#arrow-left').click();
 var q=K.$('#quest');
 window.__q=function(){qi=0;setQuest()};
 inq=false;setQuest();await K.cp('闯关1');ok('出现选项',K.$$('#opts .btn').length===3);
 var wrong=K.$$('#opts .btn').filter(function(b){return +b.dataset.n!==4})[0];K.sim.click(wrong);ok('错了提示',K.$('#say').className==='no');await K.cp('闯关答错');
 K.sim.click(K.$$('#opts .btn').filter(function(b){return +b.dataset.n===4})[0]);await K.wait(2200);ok('第2题',qi===1);await K.cp('闯关2');
 var w2=ord(3,'left');K.sim.click(K.$$('#opts .btn').filter(function(b){return +b.dataset.n===w2})[0]);await K.wait(2200);ok('第3题',qi===2);
 var w3=ord(2,'right');K.sim.click(K.$$('#opts .btn').filter(function(b){return +b.dataset.n===w3})[0]);await K.wait(2200);ok('完成页',!K.$('#finish').classList.contains('gone'));await K.cp('完成');
 K.$('#btn-again').click();await K.wait(100);ok('重玩',!K.$('#quest').classList.contains('on'));
 window.postMessage({type:'SET_WIDGET_STATE',state:{direction:'right'}},'*');await K.wait(100);ok('老师切到右',/右/.test(K.$('#direction-label').textContent));await K.cp('老师示范');
 return R};
})();
'''
    return page('方向变了第几也变', body, css, js)


def p13():
    body = '''
<div id="split-txt"></div>
<div id="simCanvas"><div class="tray" id="trayA"><div class="tl">左堆</div><div class="dz" id="zoneA"></div></div><div id="plus">＋</div><div class="tray" id="trayB"><div class="tl">右堆</div><div class="dz" id="zoneB"></div></div></div>
<div id="found"><button class="pre" id="preset-1-4">1和4</button><button class="pre" id="preset-2-3">2和3</button><button class="pre" id="preset-3-2">3和2</button><button class="pre" id="preset-4-1">4和1</button></div>
<div id="acts"><button class="btn blue" id="btn-merge">合起来 🤝</button><button class="btn ghost" id="btn-reset">重来 ↺</button></div>
<div id="ask"><div id="ask-q"></div><div id="ask-o"></div></div>'''
    css = '''
#split-txt{position:absolute;left:0;top:0;width:1232px;height:92px;display:flex;align-items:center;justify-content:center;gap:16px;background:#fff;border:4px solid var(--line);border-radius:46px;font-size:54px;font-weight:900;color:var(--ink2)}
#split-txt .a{color:var(--or2)}#split-txt .b{color:var(--bl2)}#split-txt .t{color:var(--rd)}
#simCanvas{position:absolute;left:0;top:110px;width:1232px;height:316px;display:flex;align-items:center;justify-content:center;gap:24px}
.tray{width:520px;height:300px;border-radius:32px;padding:8px 20px;border:5px dashed #D9A05B;background:#FFFBEF;position:relative}
#trayA{border-color:#F0B35B;background:#FFF4DC}#trayB{border-color:#7FB2EA;background:#EAF4FF}
.tl{font-size:28px;font-weight:800;color:#B79565;text-align:center;height:36px}
.dz{display:flex;flex-wrap:wrap;gap:16px;justify-content:center;align-content:flex-start;height:230px;padding-top:6px}
#plus{font-size:64px;font-weight:900;color:var(--ink2)}
.disc{width:86px;height:86px;border-radius:50%;cursor:grab;background:radial-gradient(circle at 35% 30%,#FFD36B,#F08A1D);border:5px solid #fff;box-shadow:0 0 0 4px #D9791A,0 8px 0 rgba(0,0,0,.18)}
.disc.b{background:radial-gradient(circle at 35% 30%,#9CC8FF,#3C7FD6);box-shadow:0 0 0 4px #2F66AE,0 8px 0 rgba(0,0,0,.18)}
#found{position:absolute;left:0;top:446px;width:760px;height:92px;display:flex;gap:16px;align-items:center}
.pre{width:170px;height:84px;border-radius:24px;border:4px solid var(--line);background:#fff;font-family:inherit;font-size:34px;font-weight:900;color:var(--ink2);cursor:pointer;position:relative}
.pre.found{background:#E9F8E5;border-color:#7CC77F;color:#2F7A36}
.pre.found::after{content:'⭐';position:absolute;right:-8px;top:-16px;font-size:34px}
#acts{position:absolute;left:800px;top:452px;width:432px;display:flex;gap:16px;justify-content:flex-end}
#ask{position:absolute;left:0;top:446px;width:1232px;height:100px;background:#fff;border:4px solid var(--line);border-radius:36px;display:none;align-items:center;gap:30px;padding:0 36px;font-size:32px;font-weight:900;color:var(--ink2)}
#ask.on{display:flex}#ask-q{flex:1}
#ask-o{display:flex;gap:16px}#ask-o .btn{width:100px;height:72px;font-size:44px;padding:0}
'''
    js = r'''
(function(){
var N=5,side=[],discs=[],found={},manual=false,phase='play',tries=0,K1=null;
K.hud({icon:'🔴',title:'分一分，合一合',levels:2});K.owl();K.say('点一点圆片，把它们分成两堆');
K.ready({emoji:'🔴',title:'分一分，合一合',sub:'把 5 个圆片分成两堆，看看有几种分法！',btn:'start-btn'});
var zA=K.$('#zoneA'),zB=K.$('#zoneB');
for(var i=0;i<N;i++){(function(i){var d=K.el('div','disc','');d.id='disc-'+(i+1);d.dataset.i=i;side.push('A');discs.push(d);
 K.drag(d,{enabled:function(){return K.started&&phase==='play'},targets:function(){return [K.$('#trayA'),K.$('#trayB')]},
  onTap:function(){toggle(i)},onDrop:function(el,t){if(t){move(i,t.id==='trayA'?'A':'B')}}})})(i)}
function counts(){var a=side.filter(function(s){return s==='A'}).length;return [a,N-a]}
function render(){zA.innerHTML='';zB.innerHTML='';discs.forEach(function(d,i){d.classList.toggle('b',side[i]==='B');(side[i]==='A'?zA:zB).appendChild(d)});
 var c=counts();K.$('#split-txt').innerHTML='<span class="a">'+c[0]+'</span> 和 <span class="b">'+c[1]+'</span> 合成 <span class="t">'+N+'</span>';
 ['1-4','2-3','3-2','4-1'].forEach(function(k){var p=K.$('#preset-'+k);p.classList.toggle('found',!!found[k])})}
function key(){var c=counts();return c[0]+'-'+c[1]}
function after(){var k=key(),c=counts();K.sfx.drop();
 if(manual&&c[0]>0&&c[1]>0&&!found[k]){found[k]=true;K.sfx.ok();K.star(1,K.$('#split-txt'));K.say(c[0]+' 和 '+c[1]+' 合成 '+N+'，发现新分法！','ok');K.pop(K.$('#preset-'+k));K.levels(2,Object.keys(found).length>=4?1:0);render();
  if(Object.keys(found).length>=4)setTimeout(toAsk,1400)}
 else if(c[0]===0||c[1]===0)K.say(c[0]+' 和 '+c[1]+'，也合成 '+N+'：把一堆全放到另一边')
 else if(found[k])K.say('这种分法找到过啦，再试试别的');
 render()}
function move(i,s){if(side[i]===s)return;side[i]=s;manual=true;after()}
function toggle(i){side[i]=side[i]==='A'?'B':'A';manual=true;K.pop(discs[i]);after()}
function arrange(a,demo){side=side.map(function(_,i){return i<a?'A':'B'});manual=!demo;render();K.say(a+' 和 '+(N-a)+'：合起来还是 '+N)}
function toAsk(){phase='ask';K.levels(2,1);K.$('#found').classList.add('hide');K.$('#acts').classList.add('hide');K.$('#ask').classList.add('on');
 arrange(3,true);manual=false;var b=side.filter(function(s){return s==='B'}).length;
 K.$('#ask-q').innerHTML='左边有 <span style="color:#C47A12">3</span> 个，右边再放几个，才能合成 <span style="color:#E4572E">5</span>？';
 var o=K.$('#ask-o');o.innerHTML='';[1,2,3,4].forEach(function(n){var bt=K.el('button','btn',String(n),o);bt.dataset.n=n;bt.addEventListener('click',function(){ask(n,bt)})});
 zB.innerHTML='';discs.forEach(function(d,i){if(i<3)zA.appendChild(d)});K.$('#split-txt').innerHTML='<span class="a">3</span> 和 <span class="b">？</span> 合成 <span class="t">5</span>';K.say('想一想，右边要放几个')}
function ask(n,b){K.sfx.pick();if(n===2){K.sfx.win();K.confetti();K.star(2,b);side=side.map(function(_,i){return i<3?'A':'B'});render();K.say('对啦！3 和 2 合成 5','ok');
  setTimeout(function(){K.levels(2,2);K.finish({title:'分与合真简单！',sub:'几和几合成几，你都会找啦',again:reset})},1700)}
 else{tries++;K.sfx.no();K.shake(b);K.say(tries===1?'再数一数，右边再放几个？':'左边 3 个，合成 5，还差几个呀？','no')}}
function reset(){phase='play';found={};manual=false;tries=0;side=side.map(function(){return 'A'});K.$('#found').classList.remove('hide');K.$('#acts').classList.remove('hide');K.$('#ask').classList.remove('on');K.levels(2,0);render();K.say('点一点圆片，把它们分成两堆')}
['1-4','2-3','3-2','4-1'].forEach(function(k){K.$('#preset-'+k).addEventListener('click',function(){if(!K.started||phase!=='play')return;K.sfx.pick();arrange(+k.charAt(0),true)})});
K.$('#btn-reset').addEventListener('click',function(){if(K.started){K.sfx.pick();reset()}});
K.$('#btn-merge').addEventListener('click',function(){if(!K.started||phase!=='play')return;K.sfx.pick();side=side.map(function(){return 'A'});manual=false;render();K.say('合起来：一共 '+N+' 个','ok')});
K.onState=function(s){if(typeof s.pileA==='number'&&phase==='play'){arrange(s.pileA,true)}};
reset();
window.__test=async function(){var R=[],ok=function(n,v){K.check(R,n,v)};
 K.sim.click(K.$('#start-btn'));await K.cp('开始后');
 K.sim.tap(K.$('#disc-5'));ok('5个里分出1个',K.$('#split-txt').textContent.replace(/\s/g,'')==='4和1合成5');ok('发现4和1',K.$('#preset-4-1').classList.contains('found'));await K.cp('分出1个');
 K.sim.drag(K.$('#disc-4'),K.$('#trayB'));ok('拖到右堆',K.$('#split-txt').textContent.replace(/\s/g,'')==='3和2合成5');
 K.sim.tap(K.$('#disc-3'));K.sim.tap(K.$('#disc-2'));await K.wait(100);ok('四种分法都找到',['1-4','2-3','3-2','4-1'].every(function(k){return found[k]}));await K.cp('找全了');
 await K.wait(1800);ok('进入考考你',phase==='ask');await K.cp('考考你');
 K.sim.click(K.$$('#ask-o .btn')[0]);ok('答错提示',K.$('#say').className==='no');K.sim.click(K.$$('#ask-o .btn')[1]);await K.wait(2000);ok('完成页',!K.$('#finish').classList.contains('gone'));await K.cp('完成');
 K.$('#btn-again').click();await K.wait(100);ok('重玩',phase==='play');
 window.postMessage({type:'SET_WIDGET_STATE',state:{pileA:2,total:5}},'*');await K.wait(100);ok('老师示范2和3',K.$('#split-txt').textContent.replace(/\s/g,'')==='2和3合成5');ok('示范不算孩子发现',!K.$('#preset-2-3').classList.contains('found'));await K.cp('老师示范');
 return R};
})();
'''
    return page('分一分合一合', body, css, js)


PAGES = {'p09': p09, 'p10': p10, 'p13': p13}
