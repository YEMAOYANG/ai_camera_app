from kit import page

SORT_CSS = '''
.pool{position:absolute;left:0;top:0;width:520px;height:552px;background:#fff;border:4px solid var(--line);border-radius:32px;padding:14px 16px}
#prog{display:flex;align-items:center;gap:12px;height:48px}
#prog-bar{flex:1;height:22px;border-radius:11px;background:#F1E3C6;overflow:hidden}
#prog-bar i{display:block;height:100%;width:0;background:var(--gr);transition:width .4s}
#prog-txt{font-size:26px;font-weight:800;color:var(--ink2);white-space:nowrap}
#cards{position:relative;height:340px;margin-top:12px}
.tk{position:absolute;width:148px;height:100px;border-radius:22px;font-size:46px;font-weight:900;display:flex;align-items:center;justify-content:center;color:#fff;box-shadow:0 7px 0 rgba(0,0,0,.2);cursor:grab;text-shadow:0 3px 0 rgba(0,0,0,.2)}
.tk.sel{outline:6px solid #FF6B35;outline-offset:4px}
#sbtns{position:absolute;left:16px;right:16px;bottom:14px;display:flex;gap:14px;justify-content:center}
.shelves{position:absolute;left:548px;top:0;width:684px;height:552px;display:flex;flex-direction:column;gap:10px}
.shelf{height:80px;display:flex;align-items:center;gap:14px;padding:0 14px;background:#fff;border:4px solid var(--line);border-radius:22px;cursor:pointer}
.shelf .chip{flex:none;width:72px;height:60px;border-radius:16px;background:var(--or);color:#fff;font-size:44px;font-weight:900;display:flex;align-items:center;justify-content:center;box-shadow:0 5px 0 var(--or2)}
.shelf .sl{width:72px;height:58px;border-radius:12px;border:3px dashed #E3C9A0;background:#FFF9EC;font-size:24px;font-weight:800;color:var(--ink2);display:flex;align-items:center;justify-content:center}
.shelf .sl.f{border-style:solid;border-color:#7CC77F;background:#E9F8E5;color:#2F7A36}
.shelf.ok{box-shadow:0 0 0 6px #BFE8B5}
'''

SORT_JS = r'''
(function(){
var MODE='__MODE__',PAL=['#E4572E','#F6A935','#58B45C','#4C8DDB','#8B5CF6','#E0508F'],OPS=MODE==='add'?'+':'−';
var ALL=[],queue,pool=[],placed=[],wrong={},helps=0,hints=0,sel=null,done=false;
for(var r=0;r<=5;r++){var n=MODE==='add'?r+1:6-r;for(var k=0;k<n;k++){var a,b;if(MODE==='add'){b=k;a=r-k}else{b=k;a=r+k}ALL.push({a:a,b:b,r:r,t:a+OPS+b})}}
function norm(t){return String(t).replace(/−/g,'-').replace(/＋/g,'+').replace(/\s/g,'')}
function cap(r){return MODE==='add'?r+1:6-r}
K.hud({icon:MODE==='add'?'🧾':'🧮',title:MODE==='add'?'整理加法卡':'整理减法卡',levels:3});K.owl();
K.ready({emoji:'📦',title:MODE==='add'?'整理加法卡':'整理减法卡',sub:'算出得数，把卡片送到有相同号码的家！',btn:'start-btn'});
var cards=K.$('#cards'),shelves=K.$('.shelves');
for(var r=0;r<6;r++){var sh=K.el('div','shelf','<div class="chip">'+r+'</div>',shelves);sh.id='row-'+r;sh.dataset.r=r;for(var k=0;k<cap(r);k++)K.el('div','sl','',sh);(function(r,sh){sh.addEventListener('click',function(){if(sel&&K.started){var c=sel;sel=null;attempt(c,r)}})})(r,sh)}
function reset(){queue=K.shuffle(ALL);pool=[];placed=[];wrong={};helps=0;hints=0;sel=null;done=false;cards.innerHTML='';K.$$('.sl').forEach(function(s){s.className='sl';s.textContent=''});refill();K.levels(3,0);prog();K.say('把卡片送到得数号码的家')}
function refill(){while(pool.length<6&&queue.length){var c=queue.shift();c.el=mk(c);pool.push(c)}layout()}
function mk(c){var e=K.el('div','tk',c.t,cards);e.style.background=PAL[c.a%6];e.dataset.t=c.t;
 K.drag(e,{enabled:function(){return K.started&&!done},targets:function(){return K.$$('.shelf')},onTap:function(){if(sel)sel.el.classList.remove('sel');sel=c;e.classList.add('sel');K.sfx.pick()},onDrop:function(el,t){if(t){if(sel)sel.el.classList.remove('sel');sel=null;attempt(c,+t.dataset.r)}}});return e}
function layout(){pool.forEach(function(c,i){c.el.style.left=((i%3)*164)+'px';c.el.style.top=(Math.floor(i/3)*118)+'px'})}
function prog(){var n=placed.length;K.$('#prog-txt').textContent='已整理 '+n+' / 21';K.$('#prog-bar i').style.width=(n/21*100)+'%'}
function put(c,r,demo){var sh=K.$('#row-'+r),sl=K.$$('.sl',sh).filter(function(s){return !s.classList.contains('f')})[0];if(!sl)return false;
 sl.classList.add('f');sl.textContent=c.t;K.pop(sl);var i=pool.indexOf(c);if(i>=0){pool.splice(i,1);c.el.remove()}else{var q=queue.indexOf(c);if(q>=0)queue.splice(q,1)}
 placed.push(c.t);K.sfx.drop();prog();refill();K.levels(3,Math.min(3,Math.floor(placed.length/7)));
 if(placed.length===21){done=true;setTimeout(function(){K.finish({title:'整理好啦！',sub:'21 张卡片都有了自己的家',again:reset});if(!helps)K.star(1)},500)}
 else if(!demo&&placed.length%7===0)K.star(1,sh);return true}
function attempt(c,r){if(!K.started||done)return;
 if(c.r===r){put(c,r,false);K.sfx.ok();K.say('对啦！'+c.t+' 等于 '+r+'，送到 '+r+' 号家','ok')}
 else{var n=wrong[c.t]=(wrong[c.t]||0)+1;K.sfx.no();K.shake(c.el);
  if(n===1)K.say('再算一算：'+c.t+' 等于几？','no');
  else if(n===2){K.say('算出得数，就去那个号码的家','no');K.highlight('.shelf .chip')}
  else{helps++;K.highlight('#row-'+c.r);K.say('我们一起算：'+c.t+' 等于 '+c.r+'，送到 '+c.r+' 号家','no');setTimeout(function(){if(pool.indexOf(c)>=0)put(c,c.r,true)},1300)}}}
function find(t){var x=pool.concat(queue).filter(function(c){return norm(c.t)===norm(t)})[0];return x}
K.$('#btn-hint').addEventListener('click',function(){if(!K.started)return;K.sfx.pick();hints++;if(hints%2===1)K.say('先算一算，得数是几，就去几号家');else{helps++;K.highlight('.shelf .chip');K.say('看，每个家门口都有一个号码')}});
K.$('#btn-check').addEventListener('click',function(){if(!K.started)return;K.sfx.pick();var n=21-placed.length;K.say(n?'已经送了 '+placed.length+' 张，还差 '+n+' 张':'都送到啦！',n?'':'ok')});
K.onState=function(s){if(s.placedCards){s.placedCards.forEach(function(p){var c=find(p.card),r=+String(p.row).replace('row-','');if(c)put(c,r,true)});K.say('老师先摆了几张，你接着来')}
 if(s.currentCard!==undefined&&s.targetRow!==undefined){var c2=find(s.currentCard);if(c2){K.highlight('#row-'+s.targetRow);put(c2,+s.targetRow,true)}}};
reset();
window.__test=async function(){var R=[],ok=function(n,v){K.check(R,n,v)};
 K.sim.click(K.$('#start-btn'));await K.cp('开始后');
 var c0=pool[0];K.sim.drag(c0.el,K.$('#row-'+((c0.r+1)%6)));await K.wait(100);ok('错了先提示再算',K.$('#say').className==='no'&&/再算一算/.test(K.$('#say').textContent));await K.cp('答错');
 var cnt=0;while(placed.length<10&&cnt++<40){var c=pool[0];K.sim.drag(c.el,K.$('#row-'+c.r))}ok('放了10张',placed.length===10);await K.cp('放了10张');
 K.sim.tap(pool[0].el);K.sim.click(K.$('#row-'+pool[0].r));await K.wait(100);ok('点选再点家也行',placed.length===11);
 K.sim.click(K.$('#btn-hint'));ok('提示',/先算一算/.test(K.$('#say').textContent));
 cnt=0;while(placed.length<21&&cnt++<60){var d=pool[0];K.sim.drag(d.el,K.$('#row-'+d.r))}await K.wait(900);ok('全部21张',placed.length===21);ok('完成页',!K.$('#finish').classList.contains('gone'));await K.cp('完成');
 K.$('#btn-again').click();await K.wait(100);ok('重玩',placed.length===0);
 __DEMO__
 return R};
})();
'''


def sort_page(mode):
    pool_id, shelf_id = ('card-pool', 'shelves') if mode == 'add' else ('card-pool-area', 'table-area')
    body = ('<div class="pool" id="%s"><div id="prog"><div id="prog-bar"><i></i></div><span id="prog-txt"></span></div><div id="cards"></div>'
            '<div id="sbtns"><button class="btn ghost sm" id="btn-hint">💡 提示</button><button class="btn green sm" id="btn-check">检查 ✔</button></div></div>'
            '<div class="shelves" id="%s"></div>') % (pool_id, shelf_id)
    if mode == 'add':
        demo = ("window.postMessage({type:'SET_WIDGET_STATE',state:{placedCards:[{row:'row-0',card:'0+0'},{row:'row-5',card:'0+5'}]}},'*');"
                "await K.wait(150);ok('老师先摆了两张',placed.length===2&&K.$('#row-5 .sl.f').textContent==='0+5');await K.cp('老师示范');")
    else:
        demo = ("window.postMessage({type:'SET_WIDGET_STATE',state:{targetRow:5,currentCard:'5-0'}},'*');"
                "await K.wait(150);ok('老师把5-0放进5号家',placed.length===1&&K.$('#row-5 .sl.f').textContent==='5−0');await K.cp('老师示范');")
    js = SORT_JS.replace('__MODE__', mode).replace('__DEMO__', demo)
    return page('整理加法卡' if mode == 'add' else '整理减法卡', body, SORT_CSS, js)


def p16():
    return sort_page('add')


def p22():
    return sort_page('sub')


def p25():
    body = '''<div id="board"><svg id="links" width="1224" height="462"></svg></div>
<div id="mbar"><button class="btn ghost sm" id="btn-undo">撤销连线 ↶</button><button class="btn ghost sm" id="btn-shuffle">重新摆 🔀</button><button class="btn blue sm" id="btn-idea">💡 想一想联系</button><div id="cnt">连线 <b id="cnt-n">0</b> 条</div></div>'''
    css = '''
#board{position:absolute;left:0;top:0;width:1232px;height:470px;background:#FFFBEF;border:4px solid var(--line);border-radius:32px;overflow:hidden}
#links{position:absolute;left:0;top:0}
#links line{stroke:#58B45C;stroke-width:8;stroke-linecap:round}
#links line.own{stroke:#4C8DDB}
.kc{position:absolute;width:200px;height:84px;border-radius:24px;display:flex;align-items:center;justify-content:center;gap:10px;font-size:32px;font-weight:900;color:#fff;box-shadow:0 7px 0 rgba(0,0,0,.2);cursor:grab;text-shadow:0 3px 0 rgba(0,0,0,.2);z-index:2}
.kc .ic{font-size:36px}
.kc.sel{outline:6px solid #FF6B35;outline-offset:4px}
.kc.center{width:300px;height:124px;font-size:34px;line-height:1.25;text-align:center;background:linear-gradient(180deg,#FFB94D,#F08A1D);z-index:1;cursor:default}
#mbar{position:absolute;left:0;top:486px;width:1232px;height:66px;display:flex;align-items:center;gap:18px;justify-content:center}
#cnt{margin-left:30px;font-size:32px;font-weight:800;color:var(--ink2)}
#cnt b{font-size:44px;color:var(--rd)}
'''
    js = r'''
(function(){
var CARDS=[['card-count','数一数','🍎','#E4572E',40,30],['card-zero','0的认识','0️⃣','#8B5CF6',40,190],['card-order','数序','🔢','#4C8DDB',40,350],
 ['card-compare','比一比','⚖️','#58B45C',992,30],['card-ordinal','第几','🥇','#F6A935',992,190],['card-split','分与合','🔴','#E0508F',992,350],
 ['card-add','加法','➕','#2FA39A',340,356],['card-sub','减法','➖','#C0572B',692,356]];
var REL={'card-order|card-zero':'0 是起点，数序从 0 开始','card-count|card-order':'数一数，数到后面，数就变大，有顺序','card-count|card-zero':'什么都没有，就是 0',
 'card-compare|card-count':'数一数，才知道谁多谁少','card-order|card-ordinal':'说第几，要看数的顺序','card-add|card-split':'几和几合成几，就是加法','card-split|card-sub':'合成的数拿走一部分，就是减法','card-add|card-sub':'加法和减法是好朋友：想加算减'};
var links=[],sel=null,own=0,canon=0,pos={},started=false,dots=0;
K.hud({icon:'🕸️',title:'摆出我的知识图',levels:3});K.owl();K.say('拖动卡片摆一摆，点两张卡片连一条线');
K.ready({emoji:'🕸️',title:'摆出我的知识图',sub:'把学过的知识连成一张网，没有唯一答案！',btn:'start-btn'});
var board=K.$('#board'),svg=K.$('#links');
var center=K.el('div','kc center','5以内数的认识<br>和加、减法',board);center.id='card-center';center.style.left='466px';center.style.top='170px';center.style.cursor='grab';
var els={'card-center':center};drag(center);
CARDS.forEach(function(c){var e=K.el('div','kc','<span class="ic">'+c[2]+'</span>'+c[1],board);e.id=c[0];e.style.background=c[3];e.style.left=c[4]+'px';e.style.top=c[5]+'px';els[c[0]]=e;pos[c[0]]=[c[4],c[5]];drag(e)});
function drag(e){e.addEventListener('pointerdown',function(ev){if(!K.started)return;ev.preventDefault();var k=K.scale||1,sx=ev.clientX,sy=ev.clientY,l0=parseFloat(e.style.left),t0=parseFloat(e.style.top),moved=false;
 function mv(m){var dx=(m.clientX-sx)/k,dy=(m.clientY-sy)/k;if(!moved&&Math.abs(dx)+Math.abs(dy)>8)moved=true;if(moved){e.style.left=Math.max(4,Math.min(1228-e.offsetWidth,l0+dx))+'px';e.style.top=Math.max(4,Math.min(466-e.offsetHeight,t0+dy))+'px';redraw()}}
 function up(){document.removeEventListener('pointermove',mv);document.removeEventListener('pointerup',up);if(!moved)tap(e.id)}
 document.addEventListener('pointermove',mv);document.addEventListener('pointerup',up)})}
function ctr(id){var e=els[id];return [parseFloat(e.style.left)+e.offsetWidth/2,parseFloat(e.style.top)+e.offsetHeight/2]}
function redraw(){links.forEach(function(l){var a=ctr(l.a),b=ctr(l.b);l.ln.setAttribute('x1',a[0]);l.ln.setAttribute('y1',a[1]);l.ln.setAttribute('x2',b[0]);l.ln.setAttribute('y2',b[1])});K.$('#cnt-n').textContent=links.length}
function key(a,b){return [a,b].sort().join('|')}
function find(a,b){return links.filter(function(l){return key(l.a,l.b)===key(a,b)})[0]}
function unsel(){if(sel){els[sel].classList.remove('sel');sel=null}}
function tap(id){if(id==='card-center'&&!sel&&false)return;K.sfx.pick();if(!sel){sel=id;els[id].classList.add('sel');return}if(sel===id){unsel();return}var a=sel;unsel();link(a,id,false)}
function link(a,b,demo){var ex=find(a,b);if(ex){ex.ln.remove();links.splice(links.indexOf(ex),1);redraw();K.say('取消了这条连线');return}
 var ln=document.createElementNS('http://www.w3.org/2000/svg','line'),k=key(a,b),msg=REL[k],isC=a==='card-center'||b==='card-center';
 var kind=msg?'canon':(isC?'center':'own');if(kind==='own')ln.setAttribute('class','own');svg.appendChild(ln);links.push({a:a,b:b,ln:ln,kind:kind,demo:demo});redraw();
 if(!demo){K.sfx.ok();if(kind==='canon'){canon++;K.star(1,els[b]);K.say(msg,'ok')}else if(kind==='center'){K.say('它也是 5 以内数的好朋友','ok')}else{own++;if(own<=2)K.star(1,els[b]);K.say('你想到了新的联系！说一说为什么吧','ok')}
  var n=links.length,d=n>=9?3:n>=6?2:n>=3?1:0;if(d>dots){dots=d;K.levels(3,d);K.confetti()}}
 else K.say(msg||'老师把它们连起来了')}
function reset(){links.forEach(function(l){l.ln.remove()});links=[];unsel();own=0;canon=0;dots=0;K.levels(3,0);Object.keys(pos).forEach(function(id){els[id].style.left=pos[id][0]+'px';els[id].style.top=pos[id][1]+'px'});redraw();K.say('拖动卡片摆一摆，点两张卡片连一条线')}
K.$('#btn-undo').addEventListener('click',function(){if(!K.started||!links.length)return;K.sfx.pick();var l=links.pop();l.ln.remove();redraw();K.say('撤销了一条连线')});
K.$('#btn-shuffle').addEventListener('click',function(){if(K.started){K.sfx.pick();reset()}});
K.$('#btn-idea').addEventListener('click',function(){if(!K.started)return;K.sfx.pick();var keys=Object.keys(REL).filter(function(k){var p=k.split('|');return !find(p[0],p[1])});if(!keys.length){K.say('好朋友都连好啦，再想想别的联系');return}
 var p=keys[K.rnd(keys.length)].split('|');K.highlight('#'+p[0]);K.highlight('#'+p[1]);K.say('想一想：'+els[p[0]].textContent.trim()+' 和 '+els[p[1]].textContent.trim()+' 有联系吗？')});
K.onState=function(s){if(s.connected&&s.connected.length>1){link(s.connected[0],s.connected[1],true)}};
redraw();
window.__test=async function(){var R=[],ok=function(n,v){K.check(R,n,v)};
 K.sim.click(K.$('#start-btn'));await K.cp('开始后');
 K.sim.tap(els['card-zero']);K.sim.tap(els['card-order']);ok('连了一条',links.length===1&&links[0].kind==='canon');ok('说明联系',/起点/.test(K.$('#say').textContent));await K.cp('连了0和数序');
 var before=els['card-count'].style.left;
 (function(){var e=els['card-count'],r=e.getBoundingClientRect();function ev(t,x,y){return new PointerEvent(t,{bubbles:true,cancelable:true,clientX:x,clientY:y,button:0,pointerId:1})}e.dispatchEvent(ev('pointerdown',r.left+20,r.top+20));document.dispatchEvent(ev('pointermove',r.left+120,r.top+90));document.dispatchEvent(ev('pointerup',r.left+120,r.top+90))})();
 ok('卡片能拖动',els['card-count'].style.left!==before);await K.cp('拖动后');
 K.sim.tap(els['card-compare']);K.sim.tap(els['card-add']);ok('自己的联系也接受',links.length===2&&links[1].kind==='own');
 K.sim.tap(els['card-add']);K.sim.tap(els['card-sub']);K.sim.tap(els['card-split']);K.sim.tap(els['card-add']);ok('四条',links.length===4);await K.cp('四条线');
 K.sim.tap(els['card-center']);K.sim.tap(els['card-count']);K.sim.tap(els['card-center']);K.sim.tap(els['card-order']);ok('连到中心',links.length===6);K.sim.tap(els['card-center']);K.sim.tap(els['card-zero']);await K.wait(100);ok('九条以内',links.length===7);
 K.sim.click(K.$('#btn-undo'));ok('撤销',links.length===6);K.sim.tap(els['card-zero']);K.sim.tap(els['card-order']);ok('再点同一对取消',links.length===5);
 K.sim.click(K.$('#btn-idea'));ok('想一想提示',/有联系吗/.test(K.$('#say').textContent));
 K.sim.click(K.$('#btn-shuffle'));ok('重新摆',links.length===0&&els['card-count'].style.left==='40px');
 window.postMessage({type:'SET_WIDGET_STATE',state:{connected:['card-zero','card-order']}},'*');await K.wait(100);ok('老师连线',links.length===1&&links[0].demo);await K.cp('老师示范');
 return R};
})();
'''
    return page('摆出我的知识图', body, css, js)


def p26():
    body = '''
<div id="guesses"><div class="gq">猜一猜，6~10 会学什么？</div><div class="gs">
<button class="gc" id="guess-1" data-t="1"><span>🔢</span>认识 6、7、8、9、10</button>
<button class="gc" id="guess-2" data-t="1"><span>⚖️</span>比大小、分与合</button>
<button class="gc" id="guess-3" data-t="1"><span>➕</span>加法和减法</button>
<button class="gc" id="guess-4" data-t="0"><span>🔤</span>学拼音</button>
<button class="gc" id="guess-5" data-t="0"><span>🎨</span>画图画</button>
<button class="gc" id="guess-6" data-t="0"><span>⚽</span>踢足球</button></div></div>
<div id="preview-card"><div class="face front"><img id="preview-img" alt="" src="/api/classroom-media/__STAGE__/media/__IMG__"></div>
<div class="face back" id="preview-text"><div class="pt">预告卡</div><div class="pl"><span>🔢</span>认识 6、7、8、9、10</div><div class="pl"><span>⚖️</span>比大小，分与合</div><div class="pl"><span>➕</span>加法和减法</div></div></div>
<div id="pbtns"><button class="btn red" id="btn-flip">翻开预告卡 🎁</button><button class="btn ghost" id="btn-reset">重玩 ↺</button></div>'''
    css = '''
#guesses{position:absolute;left:0;top:0;width:700px;height:552px;background:#fff;border:4px solid var(--line);border-radius:32px;padding:16px 20px}
.gq{font-size:36px;font-weight:900;color:var(--ink2);height:56px}
.gs{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.gc{height:130px;border-radius:26px;border:4px solid var(--line);background:#FFF9EC;font-family:inherit;font-size:30px;font-weight:800;color:var(--ink2);cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;position:relative;box-shadow:0 6px 0 #E3C9A0}
.gc span{font-size:46px;line-height:1}
.gc.on{background:#FFF1C9;border-color:var(--or);box-shadow:0 6px 0 var(--or2)}
.gc.right{background:#E9F8E5;border-color:#7CC77F;box-shadow:0 6px 0 #4FA55A}
.gc.right::after{content:'✓';position:absolute;right:12px;top:6px;font-size:40px;color:#2F7A36}
.gc.wrong{background:#FFF0E6;border-color:#F0A070;box-shadow:0 6px 0 #D77C4A}
.gc.wrong::after{content:'✗';position:absolute;right:12px;top:6px;font-size:40px;color:#B24A1C}
.gc.miss{border-style:dashed;border-color:#7CC77F}
#preview-card{position:absolute;left:730px;top:0;width:502px;height:420px;perspective:1000px}
.face{position:absolute;left:0;top:0;width:100%;height:100%;border-radius:32px;overflow:hidden;border:5px solid #D9A05B;backface-visibility:hidden;transition:transform .8s}
.front{background:#fff}.front img{width:100%;height:100%;object-fit:cover}
.back{background:linear-gradient(180deg,#FFF1C9,#FFE08A);transform:rotateY(180deg);padding:20px 26px}
#preview-card.flip .front{transform:rotateY(-180deg)}#preview-card.flip .back{transform:rotateY(0)}
.pt{font-size:40px;font-weight:900;color:var(--rd);text-align:center;height:60px}
.pl{display:flex;align-items:center;gap:14px;height:96px;font-size:32px;font-weight:900;color:var(--ink2);background:#fff;border-radius:22px;padding:0 18px;margin-bottom:12px}
.pl span{font-size:50px}
#pbtns{position:absolute;left:730px;top:440px;width:502px;display:flex;gap:16px;justify-content:center}
'''
    js = r'''
(function(){
var flipped=false,TRUE=['guess-1','guess-2','guess-3'];
K.hud({icon:'🔮',title:'猜一猜 6~10',levels:1});K.owl();K.say('先选一选你的猜测，再翻开预告卡');
K.ready({emoji:'🔮',title:'猜一猜，6~10 会学什么',sub:'先猜一猜，再翻开预告卡核对！',btn:'start-btn'});
var gcs=K.$$('.gc');
gcs.forEach(function(g){g.addEventListener('click',function(){if(!K.started||flipped)return;K.sfx.pick();g.classList.toggle('on')})});
function flip(){if(flipped)return;flipped=true;K.$('#preview-card').classList.add('flip');K.sfx.win();var good=0,bad=0,miss=0;
 gcs.forEach(function(g){var on=g.classList.contains('on'),t=g.dataset.t==='1';g.classList.remove('on');if(on&&t){g.classList.add('right');good++}else if(on&&!t){g.classList.add('wrong');bad++}else if(!on&&t){g.classList.add('miss');miss++}});
 K.levels(1,1);if(good-bad>0)K.star(Math.min(3,good-bad),K.$('#btn-flip'));
 K.say(good?('猜中了 '+good+' 个！'+(miss?'还有 '+miss+' 个没猜到，看看卡片':'一个不漏')):'没关系，看看预告卡上写了什么',good?'ok':'');
 if(good===3&&!bad)K.confetti()}
function reset(){flipped=false;K.$('#preview-card').classList.remove('flip');gcs.forEach(function(g){g.className='gc'});K.levels(1,0);K.say('先选一选你的猜测，再翻开预告卡')}
K.$('#btn-flip').addEventListener('click',function(){if(K.started)flip()});K.$('#btn-reset').addEventListener('click',function(){if(K.started){K.sfx.pick();reset()}});
K.onState=function(s){if(s.selectedGuess&&!flipped){gcs.forEach(function(g){g.classList.remove('on')});s.selectedGuess.forEach(function(t){var i=/认识|识/.test(t)?0:/大|比|分/.test(t)?1:/加|减/.test(t)?2:-1;if(i>=0)gcs[i].classList.add('on')})}};
K.onReveal=function(sel){if(sel==='#preview-text'||sel==='#preview-card')flip()};
window.__test=async function(){var R=[],ok=function(n,v){K.check(R,n,v)};
 K.sim.click(K.$('#start-btn'));await K.cp('开始后');
 K.sim.click(K.$('#guess-1'));K.sim.click(K.$('#guess-4'));ok('选了两个',K.$$('.gc.on').length===2);await K.cp('选了猜测');
 K.sim.click(K.$('#btn-flip'));await K.wait(900);ok('翻开了',K.$('#preview-card').classList.contains('flip'));ok('标出对错',K.$('#guess-1').classList.contains('right')&&K.$('#guess-4').classList.contains('wrong')&&K.$('#guess-2').classList.contains('miss'));await K.cp('翻开后');
 K.sim.click(K.$('#btn-reset'));ok('重玩',!K.$('#preview-card').classList.contains('flip')&&K.$$('.gc.on').length===0);
 window.postMessage({type:'SET_WIDGET_STATE',state:{currentStep:'guessing',selectedGuess:['认识6-10','学更大的数']}},'*');await K.wait(100);ok('老师示范选两个',K.$$('.gc.on').length===2);await K.cp('老师示范');
 window.postMessage({type:'REVEAL_ELEMENT',target:'#preview-text'},'*');await K.wait(900);ok('老师翻卡',K.$('#preview-card').classList.contains('flip'));await K.cp('老师翻开');
 return R};
})();
'''
    return page('猜一猜6到10', body, css, js)


PAGES = {'p16': p16, 'p22': p22, 'p25': p25, 'p26': p26}
