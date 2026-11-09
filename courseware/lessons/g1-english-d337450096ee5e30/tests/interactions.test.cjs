const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {createRequire}=require('node:module');
const source=path.resolve(__dirname,'..');
const {JSDOM}=createRequire(path.resolve(source,'../../../student-web/package.json'))('jsdom');
function page(id){
 const dom=new JSDOM('<b id="star-n">0</b>'+fs.readFileSync(path.join(source,'pages',id+'.html'),'utf8'),{runScripts:'outside-only'});
 const w=dom.window,d=w.document,timers=new Map();let tick=0;
 w.setTimeout=fn=>{timers.set(++tick,fn);return tick};w.clearTimeout=id=>timers.delete(id);
 w.K={$:s=>d.querySelector(s),$$:s=>[...d.querySelectorAll(s)],el(tag,cls,html,parent){let e=d.createElement(tag);e.className=cls;if(html!=null)e.innerHTML=html;if(parent)parent.appendChild(e);return e},hud(){},owl(){},ready(){},levels(){},say(text){w.lastSay=text},highlight(target){w.highlighted=target},shake(){},stars:0,star(n){this.stars+=n},sfx:{ok(){},no(){},pick(){}},finish(o){w.finish=o},drag(el,o){w.drag=o}};
 w.eval(fs.readFileSync(path.join(source,'pages',id+'.js'),'utf8'));
 return {w,d,flush(){const [id,fn]=timers.entries().next().value||[];assert.ok(fn,'a successful move advances');timers.delete(id);fn()},close(){w.close()}};
}
for(const [id,answers,wrong] of [['p03',['clinic-place','bus-place'],'bus-place'],['p05',['he-page','she-page','she-page','he-page'],'she-page'],['p08',['mother-page','father-page'],'father-page'],['p11',['pick-pupil','pick-pupil'],'pick-driver']]){
 test(id+': first wrong reveals no answer, all correct moves finish, replay fully resets',()=>{
  const p=page(id);try{
   p.w.K.onStart();p.d.getElementById(wrong).click();assert.equal(p.d.querySelectorAll('.token-result').length,0);assert.equal(p.w.K.stars,0);assert.equal(p.w.highlighted,undefined);
   for(const a of answers){p.d.getElementById(a).click();assert.equal(p.d.querySelectorAll('.token-result').length>0,true);p.flush()}
   assert.ok(p.w.finish);assert.equal(p.w.K.stars,answers.length);p.w.finish.again();assert.equal(p.d.querySelectorAll('.token-result').length,0);assert.equal(p.w.K.stars,0);assert.equal(p.d.getElementById('activity-board').dataset.level,'0');
  }finally{p.close()}
 });
 test(id+': teacher demonstration cannot score and play state removes demonstration',()=>{
  const p=page(id);try{p.w.K.onState({mode:'demo'});assert.equal(p.d.querySelectorAll('.token-result').length,1);p.d.getElementById(answers[0]).click();assert.equal(p.w.K.stars,0);p.w.K.onState({mode:'play'});assert.equal(p.d.querySelectorAll('.token-result').length,0);p.d.getElementById(answers[0]).click();assert.equal(p.w.K.stars,1)}finally{p.close()}
 });
}
test('policewoman and nurse are sorted to she, both male professions to he',()=>{const p=page('p05');try{p.w.K.onStart();for(const [target,count] of [['he-page',1],['she-page',1],['she-page',2],['he-page',2]]){p.d.getElementById(target).click();assert.equal(p.d.getElementById(target).querySelectorAll('.token-result').length,count);p.flush()}}finally{p.close()}});
