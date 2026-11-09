// Run through tools/task_tmp.py --name lesson28-browser --keep so browser files and screenshots share one private folder.
const {test,before,after} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {createRequire} = require('node:module');
const source = path.resolve(__dirname,'..');
const root = path.resolve(source,'../../..');
const build = path.resolve(process.env.GARDEN_BUILD_DIR || path.join(root,'output/courseware-lessons/g1-math-1c6c3e31475a2569/work-v1'));
const {chromium} = createRequire(path.join(root,'student-web/package.json'))('playwright-core');
let browser, body, temporary;

before(async()=>{
  temporary=process.env.MIRA_TASK_TMPDIR;
  assert.ok(temporary,'run via tools/task_tmp.py; do not scatter browser captures');
  if(process.env.GARDEN_DRAFT_ONLY==='1') {
    body=JSON.parse(fs.readFileSync(path.join(build,'draft.json'),'utf8')).body;
    console.log('Prepared-draft visual checks only; audio completion and a final G6 receipt are not asserted.');
  } else body=JSON.parse(fs.readFileSync(path.join(build,'body.json'),'utf8'));
  browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--allow-file-access-from-files','--autoplay-policy=no-user-gesture-required']});
});
after(async()=>{if(browser)await browser.close();});

async function load(page,key) {
  const scene=body.scenes.find(s=>s.outlineId===key);
  assert.ok(scene,`built ${key} exists`);
  const html=scene.content.html.replace(/\/api\/classroom-media\/[^/\s"'<>]+\/media\/[^\s"'<>+]+/g,url=>pathToFileURL(path.join(build,'media',url.split('/media/')[1])).href);
  const file=path.join(temporary,`${key}.html`);fs.writeFileSync(file,html);
  await page.goto(pathToFileURL(file).href);
  await page.waitForFunction(()=>[...document.images].every(im=>im.complete&&im.naturalWidth>0));
}
async function capture(page,key,size,state) {
  if(state==='wrong') await page.waitForTimeout(500);
  if(state==='correct'||state==='teacher') await page.waitForTimeout(300);
  await page.waitForFunction(()=>[...document.images].every(im=>im.complete&&im.naturalWidth>0));
  if(['wrong','correct','teacher'].includes(state)) {
    const moving=await page.evaluate(()=>K.drags.filter(d=>d.el.isConnected&&getComputedStyle(d.el).transform!=='none').length);
    assert.equal(moving,0,'capture a settled state after the drag return or wrong-answer animation');
  }
  if(state==='correct') assert.equal(await page.locator('.flystar').count(),0,'reward stays in the score area and cannot cover the turn prompt');
  await page.screenshot({path:path.join(temporary,`${key}-${size}-${state}.png`)});
}

async function demonstrate(page,states) {
  await page.reload();
  await page.waitForFunction(()=>!!window.K?.onState);
  await page.evaluate(states=>{K.begin();states.forEach(state=>K.onState(state));},states);
  assert.equal(await page.locator('#star-n').textContent(),'0','a fresh teacher demonstration does not award stars');
}

for(const [width,height] of [[1280,720],[1000,563],[640,360]])for(const key of ['p02','p06','p08']) {
  test(`${key} ${width}x${height}: real initial, wrong, correct and teacher states`,async()=>{
    const page=await browser.newPage({viewport:{width,height}}), errors=[];
    page.on('pageerror',e=>errors.push(String(e)));
    try {
      const size=`${width}x${height}`;
      await load(page,key);await capture(page,key,size,'ready');
      await page.locator('#start-btn').click();await capture(page,key,size,'initial');
      if(key==='p02') {
        await page.locator('[data-count="2"]').click();
        assert.equal(await page.locator('#garden-board img').count(),0);
        assert.doesNotMatch(await page.locator('#say').textContent(),/三|3|正确/);
        await capture(page,key,size,'wrong');
        await page.locator('[data-count="3"]').click();
        assert.equal(await page.locator('#garden-board img').count(),3);
        await capture(page,key,size,'correct');
        await demonstrate(page,[{demo:true},{demoPlaced:true}]);
        assert.equal(await page.locator('#garden-board img').count(),2);
      } else if(key==='p06') {
        await page.locator('[data-item="box"]').click();await page.locator('#garden-match').click();
        assert.equal(await page.locator('#garden-match img').count(),0);
        assert.doesNotMatch(await page.locator('#say').textContent(),/橘子|方盒|正确/);
        await capture(page,key,size,'wrong');
        await page.locator('[data-item="orange"]').dragTo(page.locator('#garden-match'));
        assert.equal(await page.locator('#garden-match img').count(),1);
        await capture(page,key,size,'correct');
        await demonstrate(page,[{demo:true},{demoMatch:true}]);
        assert.equal(await page.locator('#garden-match img').count(),1);
      } else {
        await page.locator('[data-material="ball"]').click();await page.locator('#garden-token').click();
        assert.equal(await page.locator('.garden-slot.filled').count(),1);
        await page.waitForFunction(()=>document.querySelectorAll('.garden-slot.filled').length===2);
        await page.locator('[data-slot="0"]').click();
        assert.match(await page.locator('#say').textContent(),/一格只放一个/);
        await capture(page,key,size,'wrong');
        await page.locator('#garden-token').dragTo(page.locator('[data-slot="2"]'));
        assert.equal(await page.locator('.garden-slot.filled').count(),3);
        await capture(page,key,size,'correct');
        await demonstrate(page,[{demo:true},{demoPlace:true}]);
        assert.equal(await page.locator('.garden-slot.filled').count(),1);
      }
      await capture(page,key,size,'teacher');
      assert.deepEqual(errors,[],'no browser JavaScript errors');
      const failedImages=await page.locator('.garden-image-failed,.garden-shape-failed,.garden-turn-image-failed').count();
      assert.equal(failedImages,0,'all formal lesson pictures load');
    } finally {await page.close();}
  });
}

test('shape round cues play to completion and the recovered third prompt replays', {skip:process.env.GARDEN_DRAFT_ONLY==='1'}, async()=>{
  const page=await browser.newPage({viewport:{width:1280,height:720}});
  try {
    await page.addInitScript(()=>{
      const NativeAudio=window.Audio;
      window.lessonAudio=[];
      window.Audio=function(...args){const clip=new NativeAudio(...args);window.lessonAudio.push(clip);return clip;};
      window.Audio.prototype=NativeAudio.prototype;
    });
    await load(page,'p06');await page.locator('#start-btn').click();
    await page.locator('[data-item="orange"]').click();await page.locator('#garden-match').click();
    await page.waitForFunction(()=>document.querySelector('#garden-shape-round').textContent==='第2轮'&&window.lessonAudio[0]?.ended);
    await page.locator('[data-item="box"]').click();await page.locator('#garden-match').click();
    await page.waitForFunction(()=>document.querySelector('#garden-shape-round').textContent==='第3轮'&&window.lessonAudio[1]?.ended);
    const finished=await page.evaluate(()=>window.lessonAudio.map(a=>({src:a.src,duration:a.duration,currentTime:a.currentTime})));
    assert.match(finished[0].src,/tts-p06-12-/);
    assert.match(finished[1].src,/tts-p06-13-/);
    assert.ok(finished.every(a=>a.duration>0.3&&a.currentTime>=a.duration-0.06));
    await page.locator('#garden-shape-listen').click();
    await page.waitForFunction(()=>window.lessonAudio[2]?.currentTime>0.05&&!window.lessonAudio[2].paused);
    assert.match(await page.evaluate(()=>window.lessonAudio[2].src),/tts-p06-13-/);
  } finally {await page.close();}
});
