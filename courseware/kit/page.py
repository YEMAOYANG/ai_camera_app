"""Shared page frame for interactive lesson pages.

A lesson page is a body, a stylesheet and a script written against the `K` object below, on a logical canvas of
1280 x 720 that is scaled to the player's frame. K gives every page the same start overlay, level dots, stars, sounds,
finish overlay, drag helper and the receivers for the teacher's page operations (highlight, annotate, reveal and set
state; the message types are in courseware/kit/contract.py). JS_TEST holds scripted-play helpers (K.sim, K.audit, K.cp,
K.check); they are only included when a page is built for a play-through (tests=True) and never ship to children.
"""
import html

CSS = r"""
:root{--ink:#6B4423;--ink2:#8A5A24;--paper:#FFFDF6;--line:#E8C48F;--or:#F6A935;--or2:#C47A12;--gr:#58B45C;--gr2:#2F8A3A;--rd:#E4572E;--rd2:#B23A17;--bl:#4C8DDB;--bl2:#2F66AE;--pu:#8B5CF6}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent;user-select:none;-webkit-user-select:none}
html,body{width:100%;height:100%;overflow:hidden;background:#FDE9C0;font-family:'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;color:var(--ink)}
#cv{position:absolute;left:50%;top:50%;width:1280px;height:720px;margin:-360px 0 0 -640px;transform:scale(var(--k,1));transform-origin:50% 50%;overflow:hidden;background:linear-gradient(180deg,#FFF5D8 0%,#FFE9B8 100%)}
#hud{position:absolute;left:24px;right:24px;top:14px;height:60px;display:flex;align-items:center;gap:18px;z-index:5}
#hud .chip{display:flex;align-items:center;gap:10px;height:56px;padding:0 26px 0 16px;border-radius:28px;background:#fff;border:3px solid var(--line);font-size:28px;font-weight:800;color:var(--ink2)}
#hud .ic{font-size:32px;line-height:1}
#dots{display:flex;gap:10px;margin-left:auto;align-items:center}
#dots i{display:block;width:22px;height:22px;border-radius:50%;background:#fff;border:3px solid var(--line)}
#dots i.cur{background:var(--or);border-color:var(--or2);transform:scale(1.25)}
#dots i.done{background:var(--gr);border-color:var(--gr2)}
#stars{display:flex;align-items:center;gap:8px;height:56px;padding:0 22px;border-radius:28px;background:#FFF7D6;border:3px solid #F2C94C;font-size:30px;font-weight:900;color:#B7791F}
#play{position:absolute;left:24px;top:86px;width:1232px;height:552px}
#owlbar{position:absolute;left:24px;top:650px;width:1232px;height:58px;display:flex;align-items:center;gap:14px;z-index:5}
#owlbar .owl{font-size:46px;line-height:1}
#say{flex:1;height:54px;line-height:48px;padding:0 26px;border-radius:27px;background:#fff;border:3px solid var(--line);font-size:26px;font-weight:700;color:var(--ink2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#say.ok{background:#E9F8E5;border-color:#7CC77F;color:#2F7A36}
#say.no{background:#FFF0E6;border-color:#F0A070;color:#B24A1C}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;border:0;border-radius:20px;padding:0 28px;height:62px;min-width:62px;font-family:inherit;font-size:28px;font-weight:800;color:#fff;background:var(--or);box-shadow:0 6px 0 var(--or2);cursor:pointer;transition:transform .08s}
.btn:active{transform:translateY(4px);box-shadow:0 2px 0 var(--or2)}
.btn.green{background:var(--gr);box-shadow:0 6px 0 var(--gr2)}
.btn.blue{background:var(--bl);box-shadow:0 6px 0 var(--bl2)}
.btn.red{background:var(--rd);box-shadow:0 6px 0 var(--rd2)}
.btn.ghost{background:#fff;color:var(--ink2);border:3px solid var(--line);box-shadow:0 5px 0 #E3C9A0}
.btn.sm{height:52px;font-size:24px;padding:0 20px;border-radius:16px}
.btn.xl{height:84px;font-size:38px;padding:0 54px;border-radius:28px}
.btn[disabled]{opacity:.45;filter:grayscale(.5);cursor:default;transform:none}
.hide{display:none!important}
#ready,#finish{position:absolute;left:0;top:0;right:0;bottom:0;z-index:20;background:rgba(255,238,196,.86);display:flex;align-items:center;justify-content:center;transition:opacity .35s}
#ready.gone,#finish.gone{opacity:0;visibility:hidden;pointer-events:none}
#ready .card,#finish .card{background:#fff;border:4px solid var(--line);border-radius:40px;padding:34px 70px 40px;text-align:center;box-shadow:0 20px 44px rgba(120,80,30,.24)}
#ready .pic{display:block;width:560px;height:315px;object-fit:cover;border-radius:26px;border:4px solid var(--line);margin:0 auto 10px}
#ready .big,#finish .big{font-size:120px;line-height:1.1}
#ready h1,#finish h1{font-size:58px;color:var(--ink2);margin-top:4px}
#ready p,#finish p{font-size:30px;margin:12px 0 26px;color:var(--ink)}
.teach-hl{outline:6px solid #FF6B35!important;outline-offset:5px;border-radius:16px;animation:tp .9s ease-in-out 4}
@keyframes tp{50%{outline-color:#FFD166;outline-offset:10px}}
#tip{position:absolute;z-index:30;display:none;max-width:440px;background:#5B3A1E;color:#fff;padding:12px 20px;border-radius:18px;font-size:24px;font-weight:700;line-height:1.35;pointer-events:none;box-shadow:0 8px 22px rgba(0,0,0,.3)}
@keyframes shake{0%,100%{transform:translateX(0)}20%{transform:translateX(-12px)}40%{transform:translateX(12px)}60%{transform:translateX(-8px)}80%{transform:translateX(8px)}}
.shake{animation:shake .45s}
@keyframes popk{0%{transform:scale(1)}40%{transform:scale(1.22)}100%{transform:scale(1)}}
.pop{animation:popk .35s}
@keyframes cfall{0%{transform:translateY(0) rotate(0)}100%{transform:translateY(780px) rotate(540deg);opacity:.9}}
.cf{position:absolute;top:-30px;width:14px;height:22px;border-radius:3px;animation:cfall 1.9s ease-in forwards;z-index:40;pointer-events:none}
.flystar{position:absolute;z-index:45;font-size:44px;line-height:1;pointer-events:none;transition:left .7s cubic-bezier(.3,.7,.3,1),top .7s cubic-bezier(.3,.7,.3,1),opacity .7s}
.truck{position:absolute;left:-160px;top:330px;font-size:100px;line-height:1;z-index:12;transition:left 1.5s ease-in}
.dragging{z-index:60!important;cursor:grabbing;filter:drop-shadow(0 12px 14px rgba(0,0,0,.25))}
"""

JS_HEAD = r"""
(function(){
var W=window,D=document;
var K=W.K={log:[],errs:[],problems:[],cps:[],started:false,scale:1,stars:0};
W.__errs=K.errs;
W.addEventListener('error',function(e){K.errs.push(String(e.message||e.type)+' @'+(e.lineno||0))});
W.addEventListener('unhandledrejection',function(e){K.errs.push('rej:'+String(e.reason))});
K.$=function(s,r){return (r||D).querySelector(s)};
K.$$=function(s,r){return Array.prototype.slice.call((r||D).querySelectorAll(s))};
K.el=function(tag,cls,html,parent){var e=D.createElement(tag);if(cls)e.className=cls;if(html!=null)e.innerHTML=html;if(parent)parent.appendChild(e);return e};
K.rnd=function(n){return Math.floor(Math.random()*n)};
K.shuffle=function(a){a=a.slice();for(var i=a.length-1;i>0;i--){var j=K.rnd(i+1),t=a[i];a[i]=a[j];a[j]=t}return a};
K.wait=function(ms){return new Promise(function(r){setTimeout(r,ms)})};
K.rm=function(a,x){var i=a.indexOf(x);if(i>=0)a.splice(i,1)};
function fit(){var k=Math.min(W.innerWidth/1280,W.innerHeight/720);if(!(k>0))k=1;D.documentElement.style.setProperty('--k',k);K.scale=k}
W.addEventListener('resize',fit);fit();
K.stage=function(){return K.$('#cv')};
K.pos=function(el){var s=K.stage().getBoundingClientRect(),r=el.getBoundingClientRect(),k=K.scale||1;return {x:(r.left-s.left)/k,y:(r.top-s.top)/k,w:r.width/k,h:r.height/k}};
K.hud=function(o){var h=K.el('div','',null,K.stage());h.id='hud';h.innerHTML='<div class="chip"><span class="ic">'+o.icon+'</span>'+o.title+'</div><div id="dots"></div><div id="stars"><span class="ic">⭐</span><b id="star-n">0</b></div>';K.levels(o.levels||0,0)};
K.levels=function(n,i){var d=K.$('#dots');if(!d)return;d.innerHTML='';for(var k=0;k<n;k++)K.el('i',k<i?'done':(k===i?'cur':''),'',d)};
K.owl=function(){var b=K.el('div','',null,K.stage());b.id='owlbar';b.innerHTML='<div class="owl">🦉</div><div id="say"></div>';var t=K.el('div','',null,K.stage());t.id='tip'};
K.say=function(t,kind){var s=K.$('#say');if(!s)return;s.className=kind||'';s.textContent=t||'';K.log.push('say:'+(kind||'')+':'+t)};
K.star=function(n,from){K.stars+=n;var b=K.$('#star-n');if(b)b.textContent=K.stars;var box=K.$('#stars');
 if(from&&box){var p=K.pos(from),q=K.pos(box);var f=K.el('div','flystar','⭐',K.stage());f.style.left=(p.x+p.w/2-20)+'px';f.style.top=(p.y+p.h/2-20)+'px';
  setTimeout(function(){f.style.left=(q.x+20)+'px';f.style.top=(q.y+4)+'px'},30);setTimeout(function(){f.remove();if(box){box.classList.remove('pop');void box.offsetWidth;box.classList.add('pop')}},780)}
 else if(box){box.classList.remove('pop');void box.offsetWidth;box.classList.add('pop')}};
K.confetti=function(){var st=K.stage();for(var i=0;i<44;i++){var c=K.el('i','cf','',st);c.style.left=(4+Math.random()*92)+'%';c.style.background=['#F6A935','#E4572E','#58B45C','#4C8DDB','#B06BD9'][i%5];c.style.animationDelay=(Math.random()*0.5)+'s';(function(c){setTimeout(function(){c.remove()},2600)})(c)}};
K.shake=function(el){if(!el)return;el.classList.remove('shake');void el.offsetWidth;el.classList.add('shake')};
K.pop=function(el){if(!el)return;el.classList.remove('pop');void el.offsetWidth;el.classList.add('pop')};
var ac;function A(){if(!ac){try{ac=new (W.AudioContext||W.webkitAudioContext)()}catch(e){}}if(ac&&ac.state==='suspended'){try{ac.resume()}catch(e){}}return ac}
function tone(f,t,d,type,v){try{var a=A();if(!a)return;var o=a.createOscillator(),g=a.createGain(),s=a.currentTime+t;o.type=type||'sine';o.frequency.value=f;g.gain.setValueAtTime(0.0001,s);g.gain.exponentialRampToValueAtTime(v||0.16,s+0.02);g.gain.exponentialRampToValueAtTime(0.0001,s+d);o.connect(g);g.connect(a.destination);o.start(s);o.stop(s+d+0.05)}catch(e){}}
K.sfx={tick:function(n){tone(392*Math.pow(1.122,(n||0)),0,0.14,'triangle')},pick:function(){tone(520,0,0.08,'triangle')},ok:function(){tone(523,0,0.12);tone(659,0.1,0.12);tone(784,0.2,0.2)},no:function(){tone(220,0,0.18,'sawtooth',0.07);tone(196,0.14,0.22,'sawtooth',0.06)},win:function(){[523,659,784,1047].forEach(function(f,i){tone(f,i*0.12,0.22,'triangle',0.18)})},drop:function(){tone(330,0,0.1,'square',0.06)}};
K.ready=function(o){var r=K.el('div','',null,K.stage());r.id='ready';r.innerHTML='<div class="card">'+(o.img?'<img class="pic" alt="" src="'+o.img+'">':'<div class="big">'+o.emoji+'</div>')+'<h1>'+o.title+'</h1><p>'+o.sub+'</p><button class="btn xl" id="'+(o.btn||'start-btn')+'">开始 ▶</button></div>';
 var im=K.$('.pic',r);if(im)im.addEventListener('error',function(){var d=K.el('div','big',o.emoji);im.replaceWith(d)});
 K.$('button',r).addEventListener('click',function(){K.sfx.pick();K.begin()})};
K.finish=function(o){var r=K.$('#finish')||K.el('div','',null,K.stage());r.id='finish';r.className='';r.innerHTML='<div class="card"><div class="big">🏆</div><h1>'+o.title+'</h1><p>'+o.sub+'</p><button class="btn xl green" id="btn-again">再玩一次 ↺</button></div>';K.$('button',r).addEventListener('click',function(){K.sfx.pick();r.classList.add('gone');if(o.again)o.again()});K.sfx.win();K.confetti()};
K.begin=function(){if(K.started)return;K.started=true;var r=K.$('#ready');if(r)r.classList.add('gone');if(K.onStart)K.onStart()};
K.highlight=function(sel){K.$$(sel).forEach(function(el){el.classList.remove('teach-hl');void el.offsetWidth;el.classList.add('teach-hl');setTimeout(function(){el.classList.remove('teach-hl')},3600)})};
K.annotate=function(sel,text){var el=K.$(sel),tip=K.$('#tip');if(!el||!text||!tip)return;var p=K.pos(el);tip.textContent=text;tip.style.display='block';
 var w=tip.offsetWidth,h=tip.offsetHeight;var x=Math.max(12,Math.min(1280-12-w,p.x+p.w/2-w/2));var y=p.y-h-14;if(y<80)y=p.y+p.h+14;if(y+h>712)y=Math.max(80,p.y+p.h/2-h/2);tip.style.left=x+'px';tip.style.top=y+'px';clearTimeout(K._tt);K._tt=setTimeout(function(){tip.style.display='none'},4600)};
K.reveal=function(sel){var el=K.$(sel);if(!el)return;el.classList.remove('hide','hidden');el.style.visibility='visible';el.style.opacity='1';if(K.onReveal)K.onReveal(sel,el);K.highlight(sel)};
W.addEventListener('message',function(e){var d=e.data||{};if(!d||typeof d!=='object')return;
 if(d.type==='SET_WIDGET_STATE'){K.begin();if(K.onState)K.onState(d.state||{},d.content)}
 else if(d.type==='HIGHLIGHT_ELEMENT'){var ht=K.$(d.target);if(!(ht&&ht.closest('#ready')))K.begin();K.highlight(d.target)}
 else if(d.type==='ANNOTATE_ELEMENT'){var at=K.$(d.target);if(!(at&&at.closest('#ready')))K.begin();K.annotate(d.target,d.content)}
 else if(d.type==='REVEAL_ELEMENT'){K.begin();K.reveal(d.target)}});
K.drag=function(el,o){el.style.touchAction='none';
 el.addEventListener('pointerdown',function(e){if(e.button&&e.button!==0)return;if(o.enabled&&!o.enabled(el))return;e.preventDefault();
  var sx=e.clientX,sy=e.clientY,moved=false,k=K.scale||1;el.style.transition='none';el.classList.add('dragging');
  function mv(ev){var dx=(ev.clientX-sx)/k,dy=(ev.clientY-sy)/k;if(!moved&&Math.abs(dx)+Math.abs(dy)>8)moved=true;el.style.transform='translate('+dx+'px,'+dy+'px)'}
  function up(ev){D.removeEventListener('pointermove',mv);D.removeEventListener('pointerup',up);D.removeEventListener('pointercancel',up);el.classList.remove('dragging');
   el.style.transition='transform .25s ease';el.style.transform='';
   if(!moved){if(o.onTap)o.onTap(el);return}
   var t=null;(o.targets?o.targets():[]).some(function(c){var r=c.getBoundingClientRect();if(ev.clientX>=r.left&&ev.clientX<=r.right&&ev.clientY>=r.top&&ev.clientY<=r.bottom){t=c;return true}return false});
   if(o.onDrop)o.onDrop(el,t,ev)}
  D.addEventListener('pointermove',mv);D.addEventListener('pointerup',up);D.addEventListener('pointercancel',up)})};
"""

JS_TEST = r"""K.sim={
 tap:function(el){if(!el)throw new Error('sim.tap: missing element');var r=el.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;function ev(t){return new PointerEvent(t,{bubbles:true,cancelable:true,clientX:x,clientY:y,button:0,pointerId:1,pointerType:'mouse'})}el.dispatchEvent(ev('pointerdown'));D.dispatchEvent(ev('pointerup'))},
 click:function(el){if(!el)throw new Error('sim.click: missing element');el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}))},
 drag:function(el,target){if(!el||!target)throw new Error('sim.drag: missing');var a=el.getBoundingClientRect(),b=target.getBoundingClientRect();
  var ax=a.left+a.width/2,ay=a.top+a.height/2,bx=b.left+b.width/2,by=b.top+b.height/2;
  function ev(t,x,y){return new PointerEvent(t,{bubbles:true,cancelable:true,clientX:x,clientY:y,button:0,pointerId:1,pointerType:'mouse'})}
  el.dispatchEvent(ev('pointerdown',ax,ay));D.dispatchEvent(ev('pointermove',(ax+bx)/2,(ay+by)/2));D.dispatchEvent(ev('pointermove',bx,by));D.dispatchEvent(ev('pointerup',bx,by))}};
K.audit=function(label){var st=K.stage(),sr=st.getBoundingClientRect(),k=K.scale||1,P=K.problems;
 function desc(e){return (e.id?'#'+e.id:'')+(e.className&&typeof e.className==='string'?'.'+e.className.split(' ')[0]:'')||e.tagName}
 function hidden(e){for(var n=e;n&&n!==D.body;n=n.parentElement){var cs=getComputedStyle(n);if(cs.display==='none'||cs.visibility==='hidden'||parseFloat(cs.opacity)<0.05)return true;if(n.classList&&(n.classList.contains('nocheck')||n.classList.contains('cf')||n.classList.contains('flystar')))return true}return false}
 var ov=K.$('#ready:not(.gone)')||K.$('#finish:not(.gone)');var texts=[];var tw=D.createTreeWalker(st,NodeFilter.SHOW_TEXT,null);var n;
 while((n=tw.nextNode())){if(!n.nodeValue.trim())continue;var par=n.parentElement;if(!par||hidden(par)||par.id==='tip'||(ov&&!ov.contains(par)))continue;var rg=D.createRange();rg.selectNodeContents(n);var r=rg.getBoundingClientRect();if(r.width<1||r.height<1)continue;var hh=r.height*0.15;texts.push({t:n.nodeValue.trim().slice(0,12),el:par,x0:(r.left-sr.left)/k,y0:(r.top+hh-sr.top)/k,x1:(r.right-sr.left)/k,y1:(r.bottom-hh-sr.top)/k})}
 texts.forEach(function(a){if(a.x0<-1||a.y0<-1||a.x1>1281||a.y1>721)P.push(label+' | 文字出界 '+a.t+' '+[a.x0,a.y0,a.x1,a.y1].map(Math.round));
  for(var p=a.el;p&&p!==st;p=p.parentElement){var cs=getComputedStyle(p);if(cs.overflow!=='visible'||cs.overflowX!=='visible'||cs.overflowY!=='visible'){var pr=p.getBoundingClientRect();var px0=(pr.left-sr.left)/k,py0=(pr.top-sr.top)/k,px1=(pr.right-sr.left)/k,py1=(pr.bottom-sr.top)/k;if(a.x0<px0-1.5||a.y0<py0-1.5||a.x1>px1+1.5||a.y1>py1+1.5){P.push(label+' | 文字被截 '+a.t+' in '+desc(p));break}}}});
 for(var i=0;i<texts.length;i++)for(var j=i+1;j<texts.length;j++){var a=texts[i],b=texts[j];if(a.el===b.el)continue;if(a.el.contains(b.el)&&false)continue;var ix=Math.min(a.x1,b.x1)-Math.max(a.x0,b.x0),iy=Math.min(a.y1,b.y1)-Math.max(a.y0,b.y0);if(ix>2&&iy>2){var sm=Math.min((a.x1-a.x0)*(a.y1-a.y0),(b.x1-b.x0)*(b.y1-b.y0));if(ix*iy>0.2*sm)P.push(label+' | 文字重叠 "'+a.t+'" / "'+b.t+'"')}}
 K.$$('button,[data-hit]').forEach(function(b){if(hidden(b)||b.disabled||(ov&&!ov.contains(b)))return;var r=b.getBoundingClientRect();if(r.width<2)return;var cx=r.left+r.width/2,cy=r.top+r.height/2;var top=D.elementFromPoint(cx,cy);if(top&&!b.contains(top)&&!top.contains(b)){P.push(label+' | 按钮被盖住 '+desc(b)+' 被 '+desc(top))}
  var x0=(r.left-sr.left)/k,y0=(r.top-sr.top)/k,x1=(r.right-sr.left)/k,y1=(r.bottom-sr.top)/k;if(x0<-1||y0<-1||x1>1281||y1>721)P.push(label+' | 按钮出界 '+desc(b));
  if(r.width/k<44||r.height/k<44)P.push(label+' | 按钮太小 '+desc(b)+' '+Math.round(r.width/k)+'x'+Math.round(r.height/k))});
 K.$$('#cv *').forEach(function(E){if(E.id==='cv'||E.id==='play'||hidden(E))return;var r=E.getBoundingClientRect();if(r.width<1||r.height<1)return;
  var x0=(r.left-sr.left)/k,y0=(r.top-sr.top)/k,x1=(r.right-sr.left)/k,y1=(r.bottom-sr.top)/k;if(x0<-2||y0<-2||x1>1282||y1>722)P.push(label+' | 元素出界 '+desc(E)+' '+[x0,y0,x1,y1].map(Math.round));
  var cs=getComputedStyle(E),bw=parseFloat(cs.borderTopWidth)+parseFloat(cs.borderLeftWidth),bg=cs.backgroundColor;var card=bw>0||(bg&&bg!=='rgba(0, 0, 0, 0)'&&bg!=='transparent')||cs.backgroundImage!=='none';
  if(!card||E.id==='ready'||E.id==='finish')return;var l=r.left+E.clientLeft*k,t=r.top+E.clientTop*k,rr=l+E.clientWidth*k,bb=t+E.clientHeight*k;
  Array.prototype.forEach.call(E.children,function(C){if(hidden(C))return;var cr=C.getBoundingClientRect();if(cr.width<1||cr.height<1)return;if(getComputedStyle(C).position==='fixed')return;
   if(cr.left<l-2*k||cr.top<t-2*k||cr.right>rr+2*k||cr.bottom>bb+2*k)P.push(label+' | 超出卡片 '+desc(C)+' 不在 '+desc(E)+' 内')})});
 var de=D.documentElement;if(de.scrollWidth>de.clientWidth+1||de.scrollHeight>de.clientHeight+1)P.push(label+' | 页面出现滚动');
 return P};
K.cp=function(name){K.cps.push(name);K.audit(name);if(K.stopAt&&K.cps.length>=K.stopAt)return new Promise(function(){});return K.wait(60)};
K.check=function(arr,name,ok){arr.push([name,!!ok]);return !!ok};"""

JS_TAIL = r"""
})();
"""


def page(title, body, css, js, css_extra="", *, tests=False):
    script = JS_HEAD + (JS_TEST if tests else "") + JS_TAIL
    return ('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + html.escape(title) + '</title><style>' + CSS + css + css_extra + '</style></head><body>'
            '<div id="cv"><div id="play">' + body + '</div></div>'
            '<script>' + script + '</script><script>' + js + '</script></body></html>')
