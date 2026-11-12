// Real Chrome regression for the shipped inline examples. Use virtual game
// time for repeatable physics, but enter actions through browser input events.
const assert = require('node:assert/strict');
const { readdirSync } = require('node:fs');
const { join } = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require(join(process.env.PW_DIR, 'node_modules/playwright-core'));
const [folder, chrome] = process.argv.slice(2);
const state = page => page.evaluate(() => K.game.status());

async function opened(browser, name, width=640, height=360) {
  const page = await browser.newPage({viewport:{width,height},hasTouch:true});
  const errors=[];
  page.on('pageerror', error => errors.push(String(error)));
  await page.clock.install();
  await page.goto(pathToFileURL(join(folder,name)).href);
  assert.equal((await state(page)).state,'ready',name);
  const advance = ms => page.clock.runFor(ms);
  const set = async (state) => {
    await page.evaluate(state => window.postMessage({type:'SET_WIDGET_STATE',state}, '*'), state);
    await advance(34);
  };
  const keys = async (key, ms) => {
    await page.keyboard.down(key);
    await advance(ms);
    await page.keyboard.up(key);
  };
  return {page,errors,advance,set,keys};
}

async function complete({page,advance}, name) {
  for (let i=0;i<9 && (await state(page)).state!=='done';i++)await advance(5000);
  assert.equal((await state(page)).state,'done',name+' did not finish');
  assert.equal((await state(page)).stars.length,3,name+' missed a level');
  assert.match(await page.locator('#finish p').textContent(), /得分 [1-9]/);
}

async function playTwice(browser,name){
  const fixture=await opened(browser,name);
  const {page,errors,advance,set}=fixture;
  try{
    await page.locator('#start-btn').tap();
    await advance(400);
    assert.equal((await state(page)).state,'play');
    assert.equal(await page.locator('.arc-node:visible').count(),3);
    for(const [width,height] of [[640,360],[1000,563],[1280,720]]){
      await page.setViewportSize({width,height});await advance(34);
      assert.equal(await page.evaluate(() => [...document.querySelectorAll('.arc-key:not([hidden])')].every(
        b=>b.getBoundingClientRect().width>=44&&b.getBoundingClientRect().height>=44)),true);
      assert.deepEqual(await page.evaluate(() => K.audit('start')), [], name+' audit '+width);
    }
    await page.setViewportSize({width:640,height:360});await advance(34);
    await page.locator('.arc-music').tap();
    assert.equal(await page.locator('.arc-music').getAttribute('aria-pressed'),'false');
    await set({demo:true,level:1});
    for(let i=0;i<9&&!await page.evaluate(()=>K.log.some(x=>x.startsWith('win:1:')));i++)await advance(1000);
    assert.ok(await page.evaluate(()=>K.log.some(x=>x.startsWith('win:1:'))),name+' demo did not act');
    assert.equal((await state(page)).level,1,name+' demo left the first level');
    await set({demo:false,level:1});
    assert.equal((await state(page)).auto,false);
    assert.deepEqual(await page.evaluate(()=>({p:K.game.current.data.progress,s:K.game.current.data.total})),{p:0,s:0});
    await page.evaluate(()=>{K.game.autoplay(true);K.onState({level:1});});
    const firstFrom = await page.evaluate(() => K.log.length);
    await complete(fixture,name);
    assert.equal(await page.evaluate(from=>K.log.slice(from).filter(x=>x.startsWith('win:')).length, firstFrom),3);
    await page.locator('#btn-again').tap();
    assert.equal((await state(page)).level,1);
    const replayFrom = await page.evaluate(() => K.log.length);
    await complete(fixture,name+' replay');
    assert.equal(await page.evaluate(from=>K.log.slice(from).filter(x=>x.startsWith('win:')).length, replayFrom),3);
    assert.deepEqual(await page.evaluate(() => K.errs),[],name);
    assert.deepEqual(errors,[],name);
    console.log(name+': demo, first clear, replay clear, and 640px touch targets pass');
  }finally{await page.close();}
}

async function playerInputs(browser){
  const {page,advance,keys}=await opened(browser,'falling-tiles.html',1280,720);
  try{
    await page.locator('#start-btn').tap();
    // Move 8 to the far right so it lands beside 4 rather than beside 2.
    await keys('ArrowRight',510);
    await keys('Space',33);
    assert.equal((await state(page)).misses,1);
    assert.equal(await page.evaluate(()=>K.game.current.data.progress),0);
    await advance(510);
    await keys('ArrowRight',510);await keys('Space',33);
    assert.equal((await state(page)).misses,2);
    assert.equal(await page.evaluate(()=>K.game.current.data.w.failureCount),2);
    await advance(510);
    // Touch the same action as Space: column 3 is adjacent to the 2.
    await page.locator('[data-arc-input="action"]').tap();
    await advance(100);
    assert.equal(await page.evaluate(()=>K.game.current.data.progress),1);
    assert.deepEqual(await page.evaluate(()=>K.errs),[]);
  }finally{await page.close();}
  const fixture=await opened(browser,'platform-hop.html',1000,563);
  try{
    const {page,advance,keys}=fixture;
    await page.locator('#start-btn').tap();
    await page.keyboard.down('ArrowRight');
    await keys('Space',30);
    await advance(575);
    await page.keyboard.up('ArrowRight');
    await advance(520);
    assert.equal(await page.evaluate(()=>K.game.current.data.w.checkpoint[3]),1);
    assert.deepEqual(await page.evaluate(()=>K.audit('player landing')),[]);
  }finally{await fixture.page.close();}
  for(const [name,play] of [
    ['magnet-marbles.html',async ({keys,advance})=>{await keys('ArrowRight',105);await keys('Space',32);await advance(1040);}],
    ['firefly-swing.html',async ({keys,advance})=>{await advance(2910);await keys('Space',32);await advance(710);}],
    ['shutter-scout.html',async ({page,advance})=>{await page.locator('[data-arc-input="action"]').tap();await advance(180);}],
  ]){
    const sample=await opened(browser,name);
    try{
      await sample.page.locator('#start-btn').tap();
      await play(sample);
      assert.equal(await sample.page.evaluate(()=>K.game.current.data.progress),1,name+' actual first action');
    }finally{await sample.page.close();}
  }
  console.log('keyboard, touch, adaptive retry, and actual first shot/swing/photo pass');
}

(async()=>{
  const browser=await chromium.launch({executablePath:chrome});
  try{
    const examples = readdirSync(folder).filter(p=>p.endsWith('.html')&&p!=='index.html');
    assert.equal(examples.length,8);
    await playerInputs(browser);
    for(let i=0;i<examples.length;i+=2)await Promise.all(examples.slice(i,i+2).map(p=>playTwice(browser,p)));
    for(const name of ['tiles','marbles']){
      const sample=await opened(browser,'pairing/'+name+'.html');
      try{
        await sample.page.locator('#start-btn').tap();
        await sample.page.evaluate(()=>K.game.autoplay(true));
        await complete(sample,name+' word/picture pairing');
        assert.equal((await state(sample.page)).misses,0);
        assert.deepEqual(sample.errors,[]);
      }finally{await sample.page.close();}
    }
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
