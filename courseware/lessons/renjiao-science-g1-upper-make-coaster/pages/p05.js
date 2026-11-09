(function(){
var radii=[85,170,125],level=0,radius=125,phase='play',mode='size',done=[],tries=0,epoch=0,busy=false,missing=false;
var board=K.$('#circle-board'),ink=K.$('#circle-ink'),target=K.$('#circle-target'),line=K.$('#circle-line'),sizes=K.$$('#circle-sizes button'),center=K.$('#circle-center'),pen=K.$('#circle-pen');
K.hud({icon:'◉',title:'让笔绕一圈',levels:3});K.owl();K.ready({emoji:'◉',title:'让笔绕一圈',sub:'固定一点，保持距离，绕一圈',btn:'start-btn'});
for(var i=0;i<4;i++){var b=K.el('button','circle-point','●',K.$('#circle-waypoints'));b.dataset.part=i;b.setAttribute('aria-label','圆周笔点');b.addEventListener('click',function(){tapPoint(Number(this.dataset.part),this)})}
function waypoint(index) {
  return [[400, 260 - radius], [400 + radius, 260], [400, 260 + radius], [400 - radius, 260]][index];
}
function placePen(index) {
  var point = waypoint(index);
  line.setAttribute('x2', point[0]);
  line.setAttribute('y2', point[1]);
}
function position() {
  var arcs = done.map(function(index) {
    var from = waypoint((index + 3) % 4);
    var to = waypoint(index);
    return 'M ' + from.join(' ') + ' A ' + radius + ' ' + radius + ' 0 0 1 ' + to.join(' ');
  });
  ink.setAttribute('d', arcs.join(' '));
  placePen(0);
  K.$$('.circle-point').forEach(function(button, index) {
    var point = waypoint(index);
    var visited = done.indexOf(index) >= 0;
    button.style.left = (point[0] - 32) + 'px';
    button.style.top = (point[1] - 32) + 'px';
    button.classList.toggle('done', visited);
    button.style.visibility = mode === 'trace' ? 'visible' : 'hidden';
    button.disabled = visited;
  });
  sizes.forEach(function(button) {
    button.disabled = mode === 'trace' || phase !== 'play';
    button.classList.toggle('selected', Number(button.dataset.radius) === radius);
  });
  center.style.background = mode === 'trace' ? '#c4e0bf' : '#fff';
  center.disabled = mode === 'trace' || phase !== 'play';
}
function setup(){mode='size';radius=125;done=[];tries=0;busy=false;target.setAttribute('r',radii[level]);position();K.levels(3,level);K.say('看虚线圆的大小，选距离，再点中央固定点')}
function reset(){epoch++;level=0;phase='play';K.stars=0;K.$('#star-n').textContent='0';setup()}
function pick(r,b){if(!K.started||phase!=='play'||busy||missing||mode!=='size')return;radius=r;position();K.sfx.pick();K.say('距离换好了，点中央固定点试一试')}
function fix(){if(!K.started||phase!=='play'||busy||missing||mode!=='size')return;if(radius!==radii[level]){tries++;K.sfx.no();K.say(tries===1?'先比较虚线圈和你选的距离，再想一想':tries===2?'固定点到笔的距离决定圆的大小':'老师示范这次需要的距离，再由你选','no');if(tries>=3)K.highlight('#circle-sizes button[data-radius="'+radii[level]+'"]');return}mode='trace';tries=0;position();K.star(1,center);K.sfx.ok();K.say('固定好了，让笔点沿圆周走一圈','ok')}
function tapPoint(i,b){if(!K.started||phase!=='play'||busy||missing||mode!=='trace'||done.indexOf(i)>=0)return;done.push(i);K.star(1,b);position();placePen(i);K.sfx.tick(i);if(done.length<4){K.say('笔还在绕，找还没走过的圆周笔点');return}busy=true;K.sfx.ok();K.say('固定点没变，距离没变，圆完成了','ok');var token=epoch;setTimeout(function(){if(token!==epoch)return;level++;if(level===3){K.levels(3,3);K.finish({title:'画出不同大小的圆',sub:'距离不变绕一圈，换距离变大小',again:reset})}else setup()},700)}
sizes.forEach(function(b){K.drag(b,{enabled:function(){return phase==='play'&&!busy&&!missing&&mode==='size'},targets:function(){return[center]},onTap:function(){pick(Number(b.dataset.radius),b)},onDrop:function(_,target){if(target){pick(Number(b.dataset.radius),b);fix()}else K.say('把选好的距离送到中央固定点')}});b.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();pick(Number(b.dataset.radius),b)}})});center.addEventListener('click',fix);K.$('#circle-reset').addEventListener('click',reset);
K.$$('#play img').forEach(function(im){im.addEventListener('error',function(){missing=true;K.$('#circle-missing').classList.add('show');K.say('图片暂未载入，请重新打开')})});
K.onStart=reset;K.onState=function(s){if(s.demo){epoch++;phase='demo';mode='size';radius=s.demo==='small'?85:170;target.setAttribute('r',radius);done=[0,1,2,3];position()}if(s.phase==='play')reset()};reset();
window.__lessonTest=async function(){var out=[],test=function(n,v){out.push([n,!!v])};K.begin();reset();radius=170;fix();test('首次错距不公布答案',mode==='size'&&done.length===0&&tries===1);for(var l=0;l<3;l++){radius=radii[level];fix();K.$$('.circle-point').forEach(function(b,i){tapPoint(i,b);if(l===0&&i===0)test('弧线与所点笔点相接',ink.getAttribute('d')==='M 315 260 A 85 85 0 0 1 400 175'&&line.getAttribute('y2')==='175')});await K.wait(800)}test('三种距离可完成',level===3&&!K.$('#finish').classList.contains('gone'));K.$('#btn-again').click();test('重玩清空轨迹',level===0&&done.length===0&&K.stars===0);K.onState({demo:'large'});test('教师大圆示范',radius===170&&phase==='demo');K.onState({phase:'play'});return out};
})();
