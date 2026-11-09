(function(){
var left=1,records=[],miss=0,demo=false;
K.hud({icon:'◉',title:'每次只搬一个',levels:5});K.owl();K.ready({emoji:'◉',title:'每次只搬一个',sub:'从少到多，保存每一种'});
function dots(parent,n){parent.innerHTML='';for(var i=0;i<n;i++){var b=K.el('span','small-bead bead','<img src="__IMG:bead__" alt="">',parent);b.querySelector('img').onerror=function(){this.style.visibility='hidden';this.parentElement.classList.add('fallback')}}}
function render(){K.$('#ordered-left-count').textContent=left;K.$('#ordered-right-count').textContent=6-left;dots(K.$('#ordered-left-beads'),left);dots(K.$('#ordered-right-beads'),6-left);K.$('#record-wall').innerHTML='';for(var i=1;i<=5;i++)K.el('div','saved-card'+(records.indexOf(i)>=0?' filled':''),records.indexOf(i)>=0?i+' · '+(6-i):'? · ?',K.$('#record-wall'));K.levels(5,records.length);K.$('#move-next').disabled=demo||left>=5;K.$('#move-back').disabled=demo||left<=1;K.$('#record-next').disabled=demo}
function reset(){left=1;records=[];miss=0;demo=false;K.stars=0;K.$('#star-n').textContent='0';render();K.say('先保存一和五，再每次搬一颗。')}
K.$('#move-next').onclick=function(){if(demo||left>=5)return;left++;render();K.sfx.drop();K.say('左边多了一颗，右边少了一颗。')};
K.$('#move-back').onclick=function(){if(demo||left<=1)return;left--;render();K.sfx.pick();K.say('可以改回来，再接着找。')};
K.$('#record-next').onclick=function(){if(demo)return;if(left!==records.length+1){miss++;K.sfx.no();K.highlight(miss===1?'#record-wall':'#ordered-left');K.say(miss===1?'对照记录墙，看看中间有没有跳过。':miss===2?'从左边较少的开始，每次只多一颗。':'看下一行的摆法，再确认两边数量。','no');if(miss>=3){left=records.length+1;render();K.highlight('#ordered-left');miss=0}return}records.push(left);miss=0;render();K.star(1,K.$('#record-next'));K.sfx.ok();K.say('这一行保存好了，总数仍是六。','ok');if(records.length===5)K.finish({title:'五种分法找全了',sub:'按顺序，不重复也不遗漏。',again:reset})};
K.onStart=reset;K.onState=function(state){if(typeof state.demoLeft==='number'){demo=true;left=Math.max(1,Math.min(5,state.demoLeft));records=[];for(var i=1;i<left;i++)records.push(i);render();K.say('看老师按顺序搬，每次只搬一颗。')}if(state.play)reset()};render();
})();
