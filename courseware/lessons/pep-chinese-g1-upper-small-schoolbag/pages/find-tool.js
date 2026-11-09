(function () {
  const tasks = [
    {id:'eraser', clue:'__IMG:task-erase__', alt:'纸上有多余的铅笔痕'},
    {id:'ruler', clue:'__IMG:task-line__', alt:'纸上有需要连成直线的两处记号'},
    {id:'pencilcase', clue:'__IMG:task-pens__', alt:'桌上有要一起带走的散笔'},
  ];
  const clue = K.$('#tool-clue-image');
  const drop = K.$('#tool-drop');
  const cards = K.$$('#tool-choices button');
  let index = 0;
  let phase = 'play';
  let wrong = 0;
  let epoch = 0;
  let busy = false;
  let imagesReady = true;
  K.hud({icon:'◇',title:document.title,levels:tasks.length});
  K.owl();
  K.ready({emoji:'◇',title:document.title,sub:'看桌面遇到什么，选出能帮忙的文具'});

  function watchImage(img) {
    img.addEventListener('error', () => {
      imagesReady = false;
      img.style.visibility = 'hidden';
      K.say('图片暂未载入，请重新打开本页', 'no');
    });
  }

  function showTask() {
    const task = tasks[index];
    clue.src = task.clue;
    clue.alt = task.alt;
    drop.replaceChildren();
  }

  function place(card) {
    const item = card.querySelector('img').cloneNode(false);
    watchImage(item);
    drop.replaceChildren(item);
    K.pop(item);
  }

  function reset() {
    epoch += 1;
    index = 0;
    wrong = 0;
    busy = false;
    phase = 'play';
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(tasks.length, 0);
    showTask();
    K.say('看图想一想，哪件文具能帮忙');
  }

  function choose(card) {
    if (!K.started || busy || phase !== 'play' || !imagesReady) return;
    const task = tasks[index];
    if (card.dataset.tool !== task.id) {
      wrong += 1;
      K.sfx.no();
      K.shake(card);
      if (wrong === 1) K.say('看看桌上的情境，再想这件文具的用处', 'no');
      else if (wrong === 2) K.say('先看清文具的样子，再选一件试试', 'no');
      else {
        K.highlight('#tool-' + task.id);
        K.say('看老师提示的图，再把文具送过去', 'no');
      }
      return;
    }
    busy = true;
    place(card);
    K.star(1, card);
    K.sfx.ok();
    K.levels(tasks.length, index + 1);
    K.say('选中的文具进到工作区了', 'ok');
    const ticket = epoch;
    setTimeout(() => {
      if (ticket !== epoch) return;
      if (index + 1 === tasks.length) {
        K.finish({title:'帮手都找到了',sub:'试着给家人说说文具的用处',again:reset});
      } else {
        index += 1;
        wrong = 0;
        busy = false;
        showTask();
        K.say('换一张图，看看这次遇到什么');
      }
    }, 880);
  }

  watchImage(clue);
  for (const card of cards) {
    watchImage(card.querySelector('img'));
    K.drag(card, {
      enabled: () => K.started && !busy && phase === 'play' && imagesReady,
      targets: () => [drop],
      onTap: () => choose(card),
      onDrop: (_, target) => { if (target) choose(card); },
    });
    card.addEventListener('click', event => { if (event.detail === 0) choose(card); });
  }
  K.onStart = reset;
  K.onState = state => {
    if (state.phase === 'play') { reset(); return; }
    const taskIndex = tasks.findIndex(task => task.id === state.task);
    if (taskIndex < 0) return;
    epoch += 1;
    index = taskIndex;
    phase = 'demo';
    showTask();
    if (state.placed) place(cards.find(card => card.dataset.tool === state.task));
  };
  reset();
})();
