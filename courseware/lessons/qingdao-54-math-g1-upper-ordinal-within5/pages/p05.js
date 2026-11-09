(() => {
  const names = ['大鼓', '小号', '钢琴', '竖琴', '铃鼓'];
  const instruments = ['drum', 'trumpet', 'piano', 'harp', 'tambourine'].map(name => K.$('#beam-' + name));
  const cue = K.$('#beam-cue');
  const choices = Array.from(K.$('#beam-choices').querySelectorAll('button'));
  const rounds = [
    { type: 'front', anchors: [2], sets: [[3, 4], [0, 1], [0, 1, 2]], answer: 1, hint: '照亮钢琴前面的乐器。' },
    { type: 'back', anchors: [3], sets: [[4], [2], [3, 4]], answer: 0, hint: '照亮竖琴后面的乐器。' },
    { type: 'between', anchors: [0, 2], sets: [[0, 1, 2], [3, 4], [1]], answer: 2, hint: '照亮大鼓和钢琴之间的乐器。' }
  ];
  const demonstrations = [
    { type: 'front', anchors: [1], sets: rounds[0].sets, hint: '小号前面' },
    { type: 'back', anchors: [2], sets: rounds[1].sets, hint: '钢琴后面' },
    { type: 'between', anchors: [1, 4], sets: rounds[2].sets, hint: '小号和铃鼓之间' }
  ];
  let level = 0;
  let mistakes = 0;
  let demo = false;
  let locked = false;
  let transition;

  function image(index) {
    return instruments[index].querySelector('img').cloneNode();
  }

  function draw(round, lit = [], marked = -1) {
    K.$('#beam-choices').style.visibility = demo ? 'hidden' : '';
    const anchors = round.anchors;
    instruments.forEach((instrument, index) => {
      instrument.classList.toggle('boundary', anchors.includes(index));
      instrument.classList.toggle('on', lit.includes(index));
    });
    const range = document.createElement('span');
    range.setAttribute('aria-hidden', 'true');
    range.textContent = round.type === 'between' ? '↔' : (round.type === 'front' ? '⟵' : '⟶');
    if (round.type === 'front') cue.replaceChildren(range, image(anchors[0]));
    else if (round.type === 'back') cue.replaceChildren(image(anchors[0]), range);
    else cue.replaceChildren(image(anchors[0]), range, image(anchors[1]));
    cue.setAttribute('aria-label', round.hint);
    choices.forEach((button, i) => {
      const set = round.sets[i];
      button.disabled = locked || demo;
      button.classList.toggle('success', i === marked);
      button.setAttribute('aria-label', '照亮' + set.map(index => names[index]).join('、'));
      button.replaceChildren(...instruments.map((_, index) => {
        const art = image(index);
        art.className = set.includes(index) ? 'on' : 'off';
        art.alt = '';
        return art;
      }));
    });
  }

  function reset() {
    clearTimeout(transition);
    level = 0;
    mistakes = 0;
    demo = false;
    locked = false;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(rounds.length, 0);
    draw(rounds[level]);
    K.say(rounds[level].hint);
  }

  function choose(index) {
    if (demo || locked) return;
    const round = rounds[level];
    if (index !== round.answer) {
      mistakes += 1;
      K.shake(choices[index]);
      K.sfx.no();
      if (mistakes > 1) K.highlight('#beam-cue');
      K.say(mistakes === 1 ? '看青色边框，先找用来分范围的乐器。' : '从边框旁开始看，边框里的乐器本身不算。', 'no');
      return;
    }
    locked = true;
    draw(round, round.sets[index], index);
    K.star(1);
    K.levels(rounds.length, level + 1);
    K.sfx.ok();
    K.say('灯光照对了。', 'ok');
    transition = setTimeout(() => {
      if (level === rounds.length - 1) {
        K.finish({ title: '每一段都照对了', sub: '先找界线，再数范围里的乐器。', again: reset });
      } else {
        level += 1;
        mistakes = 0;
        locked = false;
        draw(rounds[level]);
        K.say(rounds[level].hint);
      }
    }, 650);
  }

  choices.forEach((button, index) => button.addEventListener('click', () => choose(index)));
  K.hud({ icon: '◆', title: '灯光照到哪一段', levels: rounds.length });
  K.owl();
  K.onStart = reset;
  K.onState = state => {
    if (state.demo === false) return reset();
    if (state.demo === true && demonstrations[state.round]) {
      clearTimeout(transition);
      demo = true;
      draw(demonstrations[state.round], state.lit || []);
      K.say('看老师把青框定在界线上。');
    }
  };
  draw(rounds[0]);
  K.ready({ emoji: '◆', title: '灯光照到哪一段', sub: '把灯光投到指定的一段。' });
})();
