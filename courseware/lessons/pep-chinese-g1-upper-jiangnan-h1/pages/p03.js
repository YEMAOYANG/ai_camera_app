(function(){
var shapes=[
'<path fill="#8bd2e6" d="M0 30h200v150H0z"/><path fill="none" stroke="white" stroke-width="7" d="M20 80q35 -18 70 0t90 0M20 120q35 -18 70 0t90 0"/>',
'<path fill="#d9e9bc" d="M0 0h200v180H0z"/><path fill="none" stroke="#95724a" stroke-width="12" d="M100 15v150"/><path fill="#e7a33c" d="M30 93h140l-70 65z"/><path fill="white" d="M89 104h22v23h17l-28 27-28-27h17z"/>',
'<ellipse cx="100" cy="145" rx="80" ry="20" fill="#a4d4e3"/><path fill="#e49a54" d="M30 95q70 95 140 0z"/><circle cx="75" cy="90" r="24" fill="#ef7160"/><circle cx="120" cy="86" r="26" fill="#f5be4d"/><path fill="#72b46b" d="M87 59q10-28 25-12-6 19-25 12"/>',
'<path fill="#8bd2e6" d="M0 105h200v75H0z"/><ellipse cx="100" cy="112" rx="80" ry="18" fill="#ab7b4b"/><circle cx="90" cy="55" r="20" fill="#f5c79b"/><path fill="#d97d62" d="M65 103l10-35h30l20 35z"/><path stroke="#8d6346" stroke-width="7" d="M105 75l50 40"/><ellipse cx="160" cy="116" rx="30" ry="10" fill="#63b776"/>',
'<path stroke="#58a96b" stroke-width="7" d="M100 165V80"/><ellipse cx="100" cy="150" rx="75" ry="18" fill="#70bb77"/><path fill="#ef9bb0" stroke="#cb738c" stroke-width="4" d="M100 108Q45 87 58 45Q80 48 100 82Q120 48 142 45Q155 87 100 108z"/><path fill="#f7c1ce" d="M100 100Q75 70 100 25Q125 70 100 100"/>',
'<path fill="#8bd2e6" d="M0 0h200v180H0z"/><g fill="#ed9964"><ellipse cx="70" cy="70" rx="38" ry="23"/><path d="M37 70L10 45v50z"/><ellipse cx="140" cy="120" rx="35" ry="21"/><path d="M169 120l25-23v46z"/></g><g fill="#604c3b"><circle cx="85" cy="65" r="4"/><circle cx="128" cy="115" r="4"/></g>',
'<path fill="#eee5ce" d="M0 0h200v180H0z"/><circle cx="35" cy="95" r="23" fill="#7b9fa0"/><circle cx="100" cy="95" r="28" fill="#e6ad4d"/><circle cx="165" cy="95" r="23" fill="#7b9fa0"/>',
'<path fill="#b8e2ed" d="M0 0h200v180H0z"/><path fill="#94c58c" d="M0 140q50-50 100 0 50-50 100 0v40H0z"/><circle cx="145" cy="100" r="35" fill="#f3b74b"/><path stroke="#f3b74b" stroke-width="6" d="M145 35v20M90 100h20M180 100h20"/>',
'<path fill="#d9e9bc" d="M0 0h200v180H0z"/><path fill="none" stroke="#95724a" stroke-width="12" d="M100 15v150"/><path fill="#e7a33c" d="M30 80h140l-70-65z"/><path fill="white" d="M89 65h22V42h17l-28-24-28 24h17z"/>'
];
var chars=['江','南','可','采','莲','戏','间','东','北'],level=0,miss=0,busy=false,timer,buttons=K.$$('.picture'),card=K.$('#character'),grass=K.$('#grass-radical'),answer=0;
K.hud({icon:'🌿',title:'给生字找家',levels:9});K.owl();K.ready({img:'__IMG:water-town__',emoji:'🌿',title:'给生字找家',sub:'听字音，找图画'});
function draw(indices){buttons.forEach(function(b,i){b.innerHTML='<svg viewBox="0 0 200 180" aria-hidden="true">'+shapes[indices[i]]+'</svg>';b.dataset.kind=indices[i];b.classList.remove('success','hint')})}
function round(){busy=false;miss=0;card.textContent=chars[level];grass.classList.remove('shown');var a=level,b=(level+2)%9,c=(level+5)%9;answer=level%3;var list=[b,c];list.splice(answer,0,a);draw(list);K.levels(9,level);K.say('看看图，把字送到图旁。')}
function reset(){clearTimeout(timer);level=0;K.stars=0;K.$('#star-n').textContent='0';round()}
function choose(b){if(busy)return;if(+b.dataset.kind!==level){miss++;K.sfx.no();K.shake(card);K.say(miss===1?'再听字音，看看图。':miss===2?'想想字对应的事物或位置。':'看一看字卡的家。','no');if(miss>=3){buttons[answer].classList.add('hint');timer=setTimeout(function(){buttons[answer].classList.remove('hint')},1800)}return}busy=true;b.classList.add('success');if(level===4)grass.classList.add('shown');K.sfx.ok();K.star(1,b);K.say(chars[level]+'，找到家了。','ok');timer=setTimeout(function(){level++;if(level===9){K.levels(9,9);K.finish({title:'字卡到家',sub:'再听一听字音',again:reset})}else round()},1500)}
card.addEventListener('click',function(){card.classList.toggle('selected')});K.drag(card,{targets:function(){return buttons},onDrop:function(el,target){if(target)choose(target)}});buttons.forEach(function(b){b.addEventListener('click',function(){choose(b)})});
K.onState=function(state){if(state.demo==='lotus'){clearTimeout(timer);busy=true;card.textContent='莲';draw([4,0,2]);buttons[0].classList.add('success');grass.classList.add('shown');K.say('莲花的莲，草字头。');timer=setTimeout(round,6500)}};K.onStart=function(){draw([4,0,2]);card.textContent='莲';K.say('看看图里的事物。')};
})();
