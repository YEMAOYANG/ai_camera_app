K.hud({icon:'◆',title:"给图案盖印",levels:4});K.owl();
function cleanStars(){K.stars=0;K.$('#star-n').textContent='0';}
function finished(){K.finish({title:'活动完成',sub:'记录的是这次动手过程',again:reset});}

var types=['circle','triangle','square','rectangle'],targets=['triangle','rectangle','square','circle'],level=0,wrong=0,timer=null,busy=false,current='triangle';
function svg(kind,fill){var x=kind==='circle'?'<circle cx="100" cy="80" r="60"/>':kind==='triangle'?'<path d="M100 15L180 145H20Z"/>':kind==='square'?'<rect x="40" y="20" width="120" height="120"/>':'<rect x="15" y="40" width="170" height="80"/>';return '<svg viewBox="0 0 200 160" xmlns="http://www.w3.org/2000/svg"><g fill="'+fill+'" stroke="#6B4423" stroke-width="5">'+x+'</g></svg>';}
function draw(){busy=false;wrong=0;current=targets[level];K.$('#shape-target').innerHTML=svg(current,'none');K.levels(4,level);K.say('沿着轮廓观察，把同外形的印章放进来。');}
function reset(){clearTimeout(timer);level=0;cleanStars();draw();}
function stamp(kind,el){if(busy)return;if(kind!==current){wrong++;K.sfx.no();K.shake(el);K.say(wrong===1?'沿着边看一圈，先比较整个外形。':'留意弯边、直边和角，再试一枚印章。','no');if(wrong>=3)K.highlight('#shape-stamp-'+current);return;}busy=true;K.$('#shape-target').innerHTML=svg(current,'#F6A935');K.star(1,el);K.sfx.ok();K.say('印迹留下来了，和轮廓合在一起。','ok');level++;K.levels(4,level);timer=setTimeout(function(){if(level===4)finished();else draw();},650);}
types.forEach(function(k){var b=K.$('#shape-stamp-'+k);b.innerHTML=svg(k,'#A6D18C');K.drag(b,{enabled:function(){return !busy;},targets:function(){return [K.$('#shape-target')];},onTap:function(){stamp(k,b);},onDrop:function(el,target){if(target)stamp(k,el);else{K.say('把印章放到上面的轮廓里。');K.sfx.drop();}}});});
K.onState=function(state){if(state.demo){reset();current=state.shape||'circle';K.$('#shape-target').innerHTML=svg(current,'#F6A935');}else if(state.demo===false){reset();}};
K.onStart=reset;K.ready({emoji:'◆',title:'给图案盖印',sub:'观察印章接触面的外形'});
