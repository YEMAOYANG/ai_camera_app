from kit import page

TABLE_CSS = '''
#board{position:absolute;left:0;top:0;width:720px;height:476px}
#colheads{position:absolute;left:104px;top:0;height:56px;width:616px}
#rowheads{position:absolute;left:0;top:64px;width:96px;height:412px}
.colh,.rowh{position:absolute;display:flex;align-items:center;justify-content:center;border-radius:16px;font-weight:900;color:var(--ink2);cursor:pointer;background:#FFE3B3;border:3px solid #E8B877;font-size:30px;font-family:inherit;transition:background .2s}
.colh{top:0;width:96px;height:56px}
.rowh{left:0;width:96px;height:62px;background:#FFF0D6;border-color:#E8C48F}
.colh.on,.rowh.on{background:var(--or);color:#fff;border-color:var(--or2)}
#grid{position:absolute;left:104px;top:64px;width:616px;height:412px}
.cell{position:absolute;width:96px;height:62px;border-radius:14px;border:3px solid #EBCB96;background:#FFF9EC;display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:900;color:#7A4A1A;cursor:pointer;transition:left .7s ease,top .7s ease,background .2s,opacity .2s,transform .2s}
.cell.hl{background:#FFC65C;border-color:#E8902A;box-shadow:0 0 0 4px #FFE1A6;transform:scale(1.05);z-index:2}
.cell.hl2{background:#CDEFC8;border-color:#58B45C;box-shadow:0 0 0 4px #E3F6DF;z-index:2}
.cell.dim{opacity:.35}
.cell.sel{outline:5px solid #FF6B35;outline-offset:2px;z-index:3}
#side{position:absolute;left:748px;top:0;width:484px;height:552px}
#ctl{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;height:124px}
#ctl .btn{height:56px;font-size:24px;padding:0;border-radius:16px}
#pat{position:absolute;left:0;top:136px;width:484px;height:212px;background:#fff;border:4px solid var(--line);border-radius:28px;padding:10px 20px}
#pat .ph{font-size:30px;font-weight:900;color:var(--ink2);height:44px;line-height:44px;white-space:nowrap}
#pat .pr{display:flex;align-items:center;justify-content:space-between;height:46px;font-size:26px;font-weight:800;color:var(--ink)}
#pat .pc{padding:0 16px;height:38px;line-height:36px;border-radius:19px;font-size:26px;font-weight:900;color:#fff}
.pc.up{background:var(--rd)}.pc.dn{background:var(--bl)}.pc.eq{background:var(--gr)}
#mission{position:absolute;left:0;top:362px;width:484px;height:180px;background:#FFF1C9;border:4px solid var(--or);border-radius:28px;padding:12px 18px}
#m-q{font-size:27px;font-weight:900;color:var(--ink2);line-height:1.3;height:72px}
#m-o{display:flex;gap:10px;justify-content:space-between;margin-top:6px}
#m-o .btn{flex:1;height:64px;padding:0;font-size:25px;border-radius:16px}
'''

TABLE_JS = r'''
(function(){
var PAGE='__PAGE__',CW=96,CH=62,G=8;
var S={layout:'stair',mode:null,arg:null,solved:0,asked:null,tries:0,found:{},phase:'',sel:null,partName:0};
var cells=[],colh=[],rowh=[],CYC={col:[1,2,3,4,5,0],row:{stair:[4,3,5,2,1,0],byFirst:[1,2,0,3,4,5]},diag:{stair:[0,1,2,3,4],byFirst:[4,5,3,2,1]}},ix={col:0,row:0,diag:0};
K.hud({icon:'🧮',title:'__TITLE__',levels:3});K.owl();K.say('__SAY__');
K.ready({emoji:'🧮',title:'__TITLE__',sub:'__SUB__',btn:'start-btn'});
var grid=K.$('#grid'),ch=K.$('#colheads'),rh=K.$('#rowheads');
for(var s=0;s<=5;s++)for(var b=0;b<=s;b++){var a=s-b,e=K.el('div','cell',a+'+'+b+'='+s,grid);e.id='cell-'+a+'-'+b;var c={a:a,b:b,s:s,el:e};cells.push(c);(function(c){c.el.addEventListener('click',function(){cellTap(c)})})(c)}
for(var j=0;j<6;j++){(function(j){var x=K.el('button','colh','＋'+j,ch);x.id='colhead-'+j;x.style.left=(j*(CW+G))+'px';x.addEventListener('click',function(){mine(function(){setMode('col',j)})});colh.push(x);
 var y=K.el('button','rowh','得'+j,rh);y.id='rowhead-'+j;y.style.top=(j*(CH+G))+'px';y.addEventListener('click',function(){mine(function(){setMode('row',j)})});rowh.push(y)})(j)}
function mine(f){if(!K.started)return;K.sfx.pick();f()}
function place(){cells.forEach(function(c){var r=S.layout==='stair'?c.s:c.a;c.el.style.left=(c.b*(CW+G))+'px';c.el.style.top=(r*(CH+G))+'px'});rowh.forEach(function(y,j){y.textContent=S.layout==='stair'?'得'+j:j+'＋'})}
function match(c){var m=S.mode,v=S.arg;if(m==='col')return c.b===v;if(m==='row')return S.layout==='stair'?c.s===v:c.a===v;if(m==='diag')return S.layout==='stair'?c.a===v:c.s===v;if(m==='zero')return c.a===0;return false}
function match2(c){return S.mode==='zero'&&c.b===0&&c.a!==0}
function paint(){cells.forEach(function(c){var h=match(c),h2=match2(c);c.el.classList.toggle('hl',h);c.el.classList.toggle('hl2',h2);c.el.classList.toggle('dim',!!S.mode&&!h&&!h2);c.el.classList.toggle('sel',!!S.found[c.a+'-'+c.b])});
 colh.forEach(function(x,j){x.classList.toggle('on',S.mode==='col'&&S.arg===j)});rowh.forEach(function(y,j){y.classList.toggle('on',S.mode==='row'&&S.arg===j)})}
function pat(){var m=S.mode,v=S.arg,st=S.layout==='stair';
 if(!m)return {t:'点列标、行标或按钮，找规律',rows:[]};
 if(m==='col')return {t:'竖着看：后面的数都是 '+v,rows:[['前面的数','每格 ＋1','up'],['后面的数','不变 ＝'+v,'eq'],['得数','每格 ＋1','up']]};
 if(m==='row'&&st)return {t:'横着看：得数都是 '+v,rows:[['前面的数','每格 －1','dn'],['后面的数','每格 ＋1','up'],['得数','不变 ＝'+v,'eq']]};
 if(m==='row')return {t:'横着看：前面的数都是 '+v,rows:[['前面的数','不变 ＝'+v,'eq'],['后面的数','每格 ＋1','up'],['得数','每格 ＋1','up']]};
 if(m==='diag'&&st)return {t:'斜着看：前面的数都是 '+v,rows:[['前面的数','不变 ＝'+v,'eq'],['后面的数','每格 ＋1','up'],['得数','每格 ＋1','up']]};
 if(m==='diag')return {t:'斜着看：得数都是 '+v,rows:[['前面的数','每格 －1','dn'],['后面的数','每格 ＋1','up'],['得数','不变 ＝'+v,'eq']]};
 return {t:'0 的加法',rows:[['0 ＋ 一个数','还是这个数','eq'],['一个数 ＋ 0','还是这个数','eq']]}}
function renderPat(){var p=pat(),h='<div class="ph">'+p.t+'</div>';p.rows.forEach(function(r){h+='<div class="pr"><span>'+r[0]+'</span><span class="pc '+r[2]+'">'+r[1]+'</span></div>'});K.$('#pat').innerHTML=h}
var LAB={up:'＋1 变大 ⬆',eq:'不变 ＝',dn:'－1 变小 ⬇'},ZLAB={eq:'还是这个数',up:'变大了',dn:'变小了'};
function ask(demo){var m=S.mode;if(!m){K.$('#m-q').textContent='先点一点列标、行标或按钮';K.$('#m-o').innerHTML='';return}S.asked=null;S.tries=0;var o=K.$('#m-o');o.innerHTML='';
 if(m==='zero'&&PAGE==='zero'&&!S.found.done){S.phase='find';S.found={};K.$('#m-q').innerHTML='把每个 <b style="color:#E4572E">0＋？</b> 的格子都点一遍';paint();return}
 S.phase='pick';var p=pat();var k=S.partName%p.rows.length;S.partName++;var row=p.rows[k];S.asked={ans:row[2]};
 if(m==='zero'){K.$('#m-q').textContent='0 加一个数，得数怎么样？'}else K.$('#m-q').textContent='看亮着的格子，「'+row[0]+'」一格一格看，怎么变？';
 ['up','eq','dn'].forEach(function(t){var b=K.el('button','btn'+(t==='up'?' red':t==='dn'?' blue':' green'),m==='zero'?ZLAB[t]:LAB[t],o);b.dataset.k=t;b.addEventListener('click',function(){answer(t,b)})})}
function answer(t,b){if(!K.started||!S.asked)return;K.sfx.pick();
 if(t===S.asked.ans){K.sfx.ok();K.star(S.tries?1:2,b);S.solved++;K.levels(3,Math.min(3,S.solved));K.say('对啦！'+(S.mode==='zero'?'0 加一个数，还是这个数':'找到规律啦'),'ok');S.asked=null;
  if(S.solved===3){K.confetti();K.say('三个规律都找到啦，你真会观察！','ok')}
  setTimeout(function(){if(K.$('#m-q'))ask()},1500)}
 else{S.tries++;K.sfx.no();K.shake(b);if(S.tries===1)K.say('再看看亮着的格子，想想变化','no');
  else if(S.tries===2){var hs=cells.filter(match).slice(0,2);hs.forEach(function(c){K.highlight('#'+c.el.id)});K.say('比一比这两格，数怎么变了？','no')}
  else{K.say('看，答案是：'+(S.mode==='zero'?ZLAB[S.asked.ans]:LAB[S.asked.ans]),'no')}}}
function setMode(m,v,teacher){S.mode=m;S.arg=v;S.found=m==='zero'?S.found:{};if(m!=='zero')S.found={};place();paint();renderPat();var p=pat();K.say(p.t);if(!teacher||true)ask(teacher);K.sfx.tick(2)}
function cyc(m){var l=CYC[m];var arr=Array.isArray(l)?l:l[S.layout];var v=arr[ix[m]%arr.length];ix[m]++;setMode(m,v)}
function cellTap(c){if(!K.started)return;K.sfx.pick();K.pop(c.el);
 if(S.mode==='zero'&&S.phase==='find'){var key=c.a+'-'+c.b;if(c.a===0){if(!S.found[key]){S.found[key]=true;K.sfx.tick(Object.keys(S.found).length)}paint();var n=Object.keys(S.found).length;K.say('找到 '+n+' 个 0＋？ 啦','ok');
   if(n===6){S.found.done=true;K.sfx.ok();K.star(2,c.el);S.solved++;K.levels(3,Math.min(3,S.solved));K.say('六个都找到了：0 加一个数，还是这个数','ok');setTimeout(function(){S.phase='';ask()},1600)}}
  else{K.sfx.no();K.shake(c.el);K.say(c.b===0?c.a+'＋0 也等于 '+c.s+'，不过先找 0 开头的':'这一格不是 0 开头，再找找','no')}return}
 K.say(c.a+'＋'+c.b+'＝'+c.s)}
function setLayout(l,teacher){S.layout=l;ix.row=0;ix.diag=0;place();paint();renderPat();K.sfx.tick(5);K.say(l==='byFirst'?'同样的 21 张卡，换成第一个加数相同的排一行':'换回按得数排的阶梯表','ok');
 if(PAGE==='switch'&&!S.sw&&l==='byFirst'){S.sw=true;S.solved++;K.levels(3,Math.min(3,S.solved));if(!teacher)K.star(1,K.$('#btn-switch'))}}
K.$('#btn-col').addEventListener('click',function(){mine(function(){cyc('col')})});
K.$('#btn-row').addEventListener('click',function(){mine(function(){cyc('row')})});
K.$('#btn-diag').addEventListener('click',function(){mine(function(){cyc('diag')})});
K.$('#btn-zero').addEventListener('click',function(){mine(function(){S.found={};setMode('zero',0)})});
K.$('#btn-switch').addEventListener('click',function(){mine(function(){setLayout(S.layout==='stair'?'byFirst':'stair')})});
K.$('#btn-reset').addEventListener('click',function(){mine(function(){S.mode=null;S.arg=null;S.found={};S.phase='';S.asked=null;paint();renderPat();K.$('#m-q').textContent='点一点列标、行标或按钮';K.$('#m-o').innerHTML='';K.say('__SAY__')})});
K.onState=function(s){if('layout' in s)setLayout(s.layout==='byFirst'?'byFirst':'stair',true);if('col' in s)setMode('col',+s.col,true);if('row' in s)setMode('row',+s.row,true);if('diag' in s)setMode('diag',+String(s.diag).replace(/\D/g,''),true);if(s.zero){S.found={};setMode('zero',0,true)}};
place();paint();renderPat();K.$('#m-q').textContent='点一点列标、行标或按钮';
window.__test=async function(){var R=[],ok=function(n,v){K.check(R,n,v)};
 K.sim.click(K.$('#start-btn'));await K.cp('开始后');
 ok('阶梯形',K.$('#cell-0-0').style.top==='0px'&&K.$('#cell-0-5').style.top==='350px'&&K.$$('.cell').length===21);
 K.sim.click(K.$('#btn-col'));ok('竖看高亮5格',K.$$('.cell.hl').length===5);ok('出现选项',K.$$('#m-o .btn').length===3);await K.cp('竖着看');
 var wrong=K.$$('#m-o .btn').filter(function(b){return b.dataset.k!==S.asked.ans})[0];K.sim.click(wrong);ok('答错提示',K.$('#say').className==='no');await K.cp('答错');
 K.sim.click(K.$$('#m-o .btn').filter(function(b){return b.dataset.k===S.asked.ans})[0]);ok('答对',S.solved===1);await K.wait(1700);
 K.sim.click(K.$('#btn-row'));ok('横看高亮',K.$$('.cell.hl').length===5);K.sim.click(K.$$('#m-o .btn').filter(function(b){return b.dataset.k===S.asked.ans})[0]);await K.wait(1700);
 K.sim.click(K.$('#btn-diag'));ok('斜看高亮',K.$$('.cell.hl').length===6);await K.cp('斜着看');
 K.sim.click(K.$$('#m-o .btn').filter(function(b){return b.dataset.k===S.asked.ans})[0]);await K.wait(1700);ok('三个规律',S.solved===3);
 K.sim.click(K.$('#btn-zero'));ok('0的加法高亮6格',K.$$('.cell.hl').length===6&&K.$$('.cell.hl2').length===5);await K.cp('0的加法');
 if(PAGE==='zero'){K.sim.click(K.$('#cell-1-1'));ok('点错有提示',K.$('#say').className==='no');cells.filter(function(c){return c.a===0}).forEach(function(c){K.sim.click(c.el)});await K.wait(1800);ok('找全后进入提问',S.phase==='pick')}
 K.sim.click(K.$('#btn-switch'));await K.wait(900);ok('换排法后位置变化',K.$('#cell-0-5').style.top==='0px'&&K.$('#rowhead-1').textContent==='1＋');await K.cp('换排法');
 K.sim.click(K.$('#btn-row'));ok('新排法横看',K.$$('.cell.hl').length===5);await K.cp('新排法横看');
 K.sim.click(K.$('#btn-switch'));await K.wait(900);ok('换回',K.$('#cell-0-5').style.top==='350px');
 K.sim.click(K.$('#btn-reset'));ok('清除',K.$$('.cell.hl').length===0);
 window.postMessage({type:'SET_WIDGET_STATE',state:{col:1}},'*');await K.wait(100);ok('老师竖看',K.$$('.cell.hl').length===5);
 window.postMessage({type:'ANNOTATE_ELEMENT',target:'#cell-2-1',content:'2+1=3，再往下3+1=4'},'*');await K.wait(100);ok('老师批注',K.$('#tip').style.display==='block');await K.cp('老师示范');
 window.postMessage({type:'SET_WIDGET_STATE',state:{layout:'byFirst'}},'*');await K.wait(900);ok('老师换排法',S.layout==='byFirst');
 return R};
})();
'''


def table_page(pid, title, sub, say, key):
    body = ('<div id="board"><div id="colheads"></div><div id="rowheads"></div><div id="grid"></div></div>'
            '<div id="side"><div id="ctl"><button class="btn" id="btn-col">竖着看</button><button class="btn" id="btn-row">横着看</button><button class="btn" id="btn-diag">斜着看</button>'
            '<button class="btn green" id="btn-zero">0的加法</button><button class="btn blue" id="btn-switch">换排法 🔄</button><button class="btn ghost" id="btn-reset">清除</button></div>'
            '<div id="pat"></div><div id="mission"><div id="m-q"></div><div id="m-o"></div></div></div>')
    js = TABLE_JS.replace('__PAGE__', key).replace('__TITLE__', title).replace('__SUB__', sub).replace('__SAY__', say)
    return page(title, body, TABLE_CSS, js)


def p17():
    return table_page('p17', '加法表：竖着看', '竖着看一列，数是怎么变的？', '点一点上面的列标，竖着看规律', 'col')


def p18():
    return table_page('p18', '加法表：横着看', '横着看一行，数是怎么变的？', '点一点左边的行标，横着看规律', 'row')


def p19():
    return table_page('p19', '加法表：斜着看', '斜着看一条线，数是怎么变的？', '点一点“斜着看”，找斜线上的规律', 'diag')


def p20():
    return table_page('p20', '0的加法', '0 加一个数，会是几？', '点一点“0的加法”，找找 0 的秘密', 'zero')


def p21():
    return table_page('p21', '换一种排法再看', '同样的卡片，换个排法再找规律！', '点一点“换排法”，看看卡片怎么搬家', 'switch')


def p23():
    body = '''
<div id="titles"><div class="tt" id="t-sub">减法表</div><div class="tt" id="t-add">加法表</div></div>
<div id="grid-sub" class="tb"></div><div id="grid" class="tb"></div>
<div id="bar"><div id="bq">点一个减法算式，看右边对应的加法</div><button class="btn green sm" id="btn-quest">来闯关 ➜</button></div>'''
    css = '''
#titles{position:absolute;left:0;top:0;width:1232px;height:52px}
.tt{position:absolute;top:0;width:584px;height:50px;line-height:50px;text-align:center;font-size:32px;font-weight:900;color:var(--ink2);background:#FFE3B3;border:3px solid #E8B877;border-radius:25px}
#t-sub{left:0}#t-add{left:648px}
#btn-quest{margin-left:auto;display:none;height:46px;font-size:24px}
.tb{position:absolute;top:60px;width:584px;height:424px}
#grid-sub{left:0}#grid{left:648px}
.ch,.rh{position:absolute;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:24px;color:var(--ink2);background:#FFE3B3;border:3px solid #E8B877;border-radius:12px}
.ch{top:0;width:82px;height:42px}.rh{left:0;width:64px;height:58px;background:#FFF0D6;border-color:#E8C48F}
.c{position:absolute;width:82px;height:58px;border-radius:12px;border:3px solid #EBCB96;background:#FFF9EC;display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:900;color:#7A4A1A;cursor:pointer;transition:background .2s,opacity .2s,transform .2s}
.c.hl{background:#FFC65C;border-color:#E8902A;box-shadow:0 0 0 4px #FFE1A6;transform:scale(1.06);z-index:2}
.c.hl2{background:#CDEFC8;border-color:#58B45C;box-shadow:0 0 0 4px #E3F6DF;z-index:2}
.c.ask{background:#FFE1D6;border-color:var(--rd);box-shadow:0 0 0 4px #FFC7B5;z-index:2}
.c.dim{opacity:.4}
#bar{position:absolute;left:0;top:492px;width:1232px;height:58px;background:#fff;border:4px solid var(--line);border-radius:29px;display:flex;align-items:center;padding:0 28px}
#bq{font-size:30px;font-weight:900;color:var(--ink2);white-space:nowrap}#bq b{color:var(--rd)}
'''
    js = r'''
(function(){
var CW=82,CH=58,G=6,subs=[],adds=[],sel=null,mode='explore',qi=0,tries=0,lock=false,Q=[[4,1],[5,2],[3,0]];
K.hud({icon:'🧮',title:'想加算减',levels:3});K.owl();K.say('点一个减法算式，看右边对应的加法');
K.ready({emoji:'🧮',title:'想加算减',sub:'减法和加法是好朋友：想加算减！',btn:'start-btn'});
var gs=K.$('#grid-sub'),ga=K.$('#grid');
function heads(box,pre,lab){for(var j=0;j<6;j++){var c=K.el('div','ch',lab(j),box);c.style.left=(70+j*(CW+G))+'px';var r=K.el('div','rh',pre(j),box);r.style.top=(48+j*(CH+G))+'px'}}
heads(gs,function(j){return j+'－'},function(j){return '－'+j});heads(ga,function(j){return '得'+j},function(j){return '＋'+j});
for(var A=0;A<=5;A++)for(var B=0;B<=A;B++){(function(A,B){var C=A-B,e=K.el('div','c',A+'−'+B+'='+C,gs);e.id='sub-'+A+'-'+B;e.style.left=(70+B*(CW+G))+'px';e.style.top=(48+A*(CH+G))+'px';var o={A:A,B:B,C:C,el:e};subs.push(o);e.addEventListener('click',function(){subTap(o)})})(A,B)}
for(var s=0;s<=5;s++)for(var b=0;b<=s;b++){(function(a,b,s){var e=K.el('div','c',a+'+'+b+'='+s,ga);e.id='cell-'+a+'-'+b;e.style.left=(70+b*(CW+G))+'px';e.style.top=(48+s*(CH+G))+'px';var o={a:a,b:b,s:s,el:e};adds.push(o);e.addEventListener('click',function(){addTap(o)})})(s-b,b,s)}
function clear(){subs.concat(adds).forEach(function(o){o.el.classList.remove('hl','hl2','dim','ask')})}
function show(o){clear();sel=o;o.el.classList.add('hl');adds.forEach(function(x){if(x.a===o.B&&x.b===o.C)x.el.classList.add('hl');else if(x.a===o.C&&x.b===o.B)x.el.classList.add('hl2')})}
function subTap(o){if(!K.started)return;K.sfx.pick();K.pop(o.el);if(mode==='quest'){K.shake(o.el);K.say('先在右边找一找，哪个加法是它的好朋友','no');return}
 show(o);K.say(o.A+'－'+o.B+'＝'+o.C+'，因为 '+o.B+'＋'+o.C+'＝'+o.A,'ok');K.$('#bq').innerHTML=o.A+'－'+o.B+'＝'+o.C+'　想：<b>'+o.B+'＋'+o.C+'＝'+o.A+'</b>';K.sfx.tick(o.C)}
function ask(){var q=Q[qi],o=subs.filter(function(x){return x.A===q[0]&&x.B===q[1]})[0];clear();sel=o;tries=0;lock=false;o.el.classList.add('ask');K.levels(3,qi);K.$('#bq').innerHTML='右边哪个加法，和 <b>'+o.A+'－'+o.B+'＝'+o.C+'</b> 是好朋友？';K.say('在右边点一点，找到好朋友')}
function addTap(o){if(!K.started)return;K.sfx.pick();K.pop(o.el);
 if(mode!=='quest'){K.say(o.a+'＋'+o.b+'＝'+o.s);return}
 if(lock)return;var q=sel;if((o.a===q.B&&o.b===q.C)||(o.a===q.C&&o.b===q.B)){lock=true;K.sfx.ok();K.star(tries?1:2,o.el);o.el.classList.add('hl');K.say('对啦！因为 '+q.B+'＋'+q.C+'＝'+q.A+'，所以 '+q.A+'－'+q.B+'＝'+q.C,'ok');
  setTimeout(function(){if(qi<Q.length-1){qi++;ask()}else{K.levels(3,3);K.finish({title:'想加算减，你学会啦！',sub:'减法的得数，可以想加法来算',again:restart})}},1800)}
 else{tries++;K.sfx.no();K.shake(o.el);K.say(tries===1?'不对哦，加起来要等于 '+q.A+'：再找找':'想一想：哪两个数合成 '+q.A+'，其中一个是 '+q.B+'？','no');
  if(tries>=3){adds.forEach(function(x){if(x.a===q.B&&x.b===q.C)K.highlight('#'+x.el.id)})}}}
function restart(){mode='explore';qi=0;sel=null;clear();K.levels(3,0);K.$('#btn-quest').style.display='inline-flex';K.$('#bq').textContent='点一个减法算式，看右边对应的加法';K.say('点一个减法算式，看右边对应的加法')}
K.$('#btn-quest').addEventListener('click',function(){if(!K.started)return;K.sfx.pick();mode='quest';K.$('#btn-quest').style.display='none';qi=0;ask()});
K.onState=function(s){if(s.sel){var p=String(s.sel).split(/[-−]/);var o=subs.filter(function(x){return x.A===+p[0]&&x.B===+p[1]})[0];if(o){mode='explore';show(o);K.$('#bq').innerHTML=o.A+'－'+o.B+'＝'+o.C+'　想：<b>'+o.B+'＋'+o.C+'＝'+o.A+'</b>'}}};
K.onStart=function(){K.$('#btn-quest').style.display='inline-flex'};
window.__test=async function(){var R=[],ok=function(n,v){K.check(R,n,v)};
 K.sim.click(K.$('#start-btn'));await K.cp('开始后');
 ok('两张表',K.$$('#grid-sub .c').length===21&&K.$$('#grid .c').length===21);
 K.sim.click(K.$('#sub-4-1'));ok('4-1对应1+3',K.$('#cell-1-3').classList.contains('hl')&&K.$('#cell-3-1').classList.contains('hl2'));await K.cp('点了4-1');
 window.postMessage({type:'SET_WIDGET_STATE',state:{sel:'5-2'}},'*');await K.wait(100);ok('老师示范5-2',K.$('#cell-2-3').classList.contains('hl'));await K.cp('老师示范');
 K.sim.click(K.$('#btn-quest'));await K.cp('闯关1');ok('出题4-1',K.$('#sub-4-1').classList.contains('ask'));
 K.sim.click(K.$('#cell-2-2'));ok('答错提示',K.$('#say').className==='no');K.sim.click(K.$('#cell-3-1'));await K.wait(2000);ok('第2题',qi===1);await K.cp('闯关2');
 K.sim.click(K.$('#cell-3-2'));K.sim.click(K.$('#cell-2-3'));await K.wait(2000);ok('连点两次只算一次',qi===2);K.sim.click(K.$('#cell-0-3'));await K.wait(2000);ok('完成页',!K.$('#finish').classList.contains('gone'));await K.cp('完成');
 K.$('#btn-again').click();await K.wait(100);ok('重玩',mode==='explore');
 return R};
})();
'''
    return page('想加算减', body, css, js)


PAGES = {'p17': p17, 'p18': p18, 'p19': p19, 'p20': p20, 'p21': p21, 'p23': p23}
