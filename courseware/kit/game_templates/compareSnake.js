// Snake with a rolling reference: only a food that satisfies this round's
// relation grows the snake, and its value becomes the next reference.
K.gameTemplates.compareSnake = config => {
  const {box, center, create, bot, sprite, text, token, validToken} = Classic;
  const cols = 10;
  const rows = 6;
  const cell = 80;
  const origin = [194, 96];
  const vectors = {up: [0, -1], right: [1, 0], down: [0, 1], left: [-1, 0]};
  const directions = Object.keys(vectors);
  const rotation = {up: -Math.PI / 2, right: 0, down: Math.PI / 2, left: Math.PI};
  const marks = {gt: '>', lt: '<', eq: '=', match: '='};
  const kinds = new Set(['circle', 'triangle', 'square', 'rectangle']);
  const models = new Map();
  const encode = (x, y) => y * cols + x;
  const at = position => [origin[0] + (position % cols + .5) * cell,
    origin[1] + (Math.floor(position / cols) + .5) * cell];
  const validCell = (x, y) => Number.isInteger(x) && x >= 0 && x < cols &&
    Number.isInteger(y) && y >= 0 && y < rows - 1;
  const number = value => Number.isInteger(value) && value >= 0 && value <= 10;
  const spawn = length => Array.from({length}, (_, i) => encode(5 - i, rows - 1));

  function accepts(model, relation, candidate, ref) {
    if (relation === 'match') return (model.groups.get(String(candidate)) ?? candidate) === (model.groups.get(String(ref)) ?? ref);
    if (relation === 'gt') return candidate > ref;
    if (relation === 'lt') return candidate < ref;
    return candidate === ref;
  }

  function step(model, round, ref, body, direction) {
    const [dx, dy] = vectors[direction];
    const x = body[0] % cols + dx;
    const y = Math.floor(body[0] / cols) + dy;
    const position = encode(x, y);
    if (x < 0 || x >= cols || y < 0 || y >= rows || model.walls.has(position)) {
      return {failure: 'wall', position: body[0]};
    }
    const food = round.foods.get(position);
    const eating = food !== undefined;
    const occupied = body.indexOf(position);
    if (occupied >= 0 && (occupied === 1 || eating || occupied !== body.length - 1)) return {failure: 'tail', position};
    if (eating && !accepts(model, round.relation, food, ref)) return {failure: 'food', position};
    const next = [position, ...body];
    if (!eating) next.pop();
    return {body: next, food, position};
  }

  function findMove(model, round, ref, body) {
    const queue = [{body, first: null}];
    const seen = new Set([body.join(',')]);
    for (let i = 0; i < queue.length && i < 6500; i++) {
      const state = queue[i];
      for (const direction of directions) {
        const next = step(model, round, ref, state.body, direction);
        if (next.failure) continue;
        const first = state.first ?? direction;
        if (next.food !== undefined) return first;
        const key = next.body.join(',');
        if (seen.has(key)) continue;
        seen.add(key);
        queue.push({body: next.body, first});
      }
    }
    return null;
  }

  function validate(level, index) {
    const {start, seconds, display, walls = [], groups = {}, diagrams = {}, rounds} = level;
    const valid = display === 'dots' ? number : validToken;
    if (!valid(start) || !(seconds >= .3 && seconds <= .9) || !Array.isArray(walls) || walls.length > 12 ||
      !Array.isArray(rounds) || rounds.length < 1 || rounds.length > 4) {
      throw new Error('invalid snake level');
    }
    const barriers = new Set();
    for (const wall of walls) {
      if (!Array.isArray(wall) || wall.length !== 2 || !validCell(...wall)) throw new Error('invalid snake wall');
      barriers.add(encode(...wall));
    }
    if (barriers.size !== walls.length) throw new Error('duplicate snake wall');
    for (const diagram of Object.values(diagrams)) {
      if (!diagram || !kinds.has(diagram.kind) || !Number.isFinite(diagram.degrees ?? 0)) {
        throw new Error('invalid snake diagram');
      }
    }
    const model = {walls: barriers, groups: new Map(Object.entries(groups)), rounds: []};
    let refs = new Set([start]);
    for (const [i, round] of rounds.entries()) {
      if (!round || !Object.hasOwn(marks, round.relation) || !Array.isArray(round.foods) ||
        round.foods.length < 2 || round.foods.length > 4) throw new Error('invalid snake round');
      const foods = new Map();
      for (const food of round.foods) {
        if (!Array.isArray(food) || food.length !== 3) throw new Error('invalid snake food');
        const [x, y, value] = food;
        const position = encode(x, y);
        if (!validCell(x, y) || !valid(value) || barriers.has(position) || foods.has(position) ||
          (round.relation !== 'match' && !Number.isFinite(value))) throw new Error('invalid snake food');
        foods.set(position, value);
      }
      const compiled = {relation: round.relation, foods};
      const nextRefs = new Set();
      for (const ref of refs) {
        const candidates = [...foods.values()].filter(value => accepts(model, round.relation, value, ref));
        if ((round.relation !== 'match' && !Number.isFinite(ref)) || !candidates.length || candidates.length === foods.size ||
          !findMove(model, compiled, ref, spawn(2 + i))) {
          throw new Error(`snake level ${index + 1}, round ${i + 1} needs reachable right and wrong choices`);
        }
        candidates.forEach(value => nextRefs.add(value));
      }
      refs = nextRefs;
      model.rounds.push(compiled);
    }
    models.set(level, model);
  }

  function resetBody(world) {
    world.body = spawn(2 + world.round);
    world.previous = world.body;
    world.direction = 'right';
    world.cooldown = 0;
    world.moving = false;
    world.startedAt = -Infinity;
  }

  function reset(level) {
    const world = {model: models.get(level), round: 0, ref: level.start, help: false};
    resetBody(world);
    return world;
  }

  function update(world, level, input, dt, feedback) {
    if (input.press('action')) {
      resetBody(world);
      feedback.move();
      feedback.fx(...at(world.body[0]));
      return;
    }
    const move = directions.find(key => input.press(key));
    if (move) {
      const [dx, dy] = vectors[move];
      if (world.body[0] + dx + dy * cols !== world.body[1]) {
        if (move !== world.direction || !world.moving) {
          feedback.move();
          feedback.fx(...at(world.body[0]), '#c8e4a0');
        }
        world.direction = move;
        world.moving = true;
      }
    }
    if (!world.moving) return;
    world.cooldown = Math.max(0, world.cooldown - dt);
    if (world.cooldown > 0) return;
    world.cooldown = level.seconds * (world.help ? 1.25 : 1);
    const round = world.model.rounds[world.round];
    const result = step(world.model, round, world.ref, world.body, world.direction);
    if (result.failure) {
      if (result.failure !== 'food') resetBody(world);
      world.cooldown = 0;
      world.moving = false;
      feedback.lost(...at(result.position));
      return;
    }
    world.previous = world.body;
    world.body = result.body;
    world.startedAt = null;
    if (result.food === undefined) return;
    world.ref = result.food;
    world.round++;
    world.moving = false;
    world.cooldown = 0;
    feedback.award(...at(result.position));
  }

  function drawValue(context, level, images, value, x, y, width) {
    if (level.display === 'dots') {
      const spacing = width / 6;
      const radius = spacing * .33;
      for (let i = 0; i < 10; i++) {
        const cx = x + (i % 5 - 2) * spacing;
        const cy = y + (Math.floor(i / 5) - .5) * spacing;
        context.fillStyle = i < value ? '#9c4b2a' : '#e3cfa7';
        K.draw.circle(context, cx, cy, radius);
      }
      return;
    }
    const diagram = Object.hasOwn(level.diagrams ?? {}, value) ? level.diagrams[value] : null;
    if (!diagram) {
      token(context, images, value, x, y, width, width, level.labels);
      return;
    }
    const radius = width * .34;
    context.save();
    context.translate(x, y);
    context.rotate((diagram.degrees ?? 0) * Math.PI / 180);
    context.fillStyle = '#a25730';
    if (diagram.kind === 'circle') {
      K.draw.circle(context, 0, 0, radius);
    } else if (diagram.kind === 'triangle') {
      context.beginPath();
      context.moveTo(0, -radius);
      context.lineTo(radius * .88, radius * .51);
      context.lineTo(-radius * .88, radius * .51);
      context.closePath();
      context.fill();
    } else {
      const height = radius * (diagram.kind === 'square' ? 1.48 : .92);
      context.fillRect(-radius * .74, -height / 2, radius * 1.48, height);
    }
    context.restore();
  }

  function draw(world, level, context, images, game) {
    box(context, 178, 81, 832, 510, 24, '#27483b');
    for (let i = 0; i < cols * rows; i++) {
      const [x, y] = at(i);
      const wall = world.model.walls.has(i);
      box(context, x - 38, y - 38, 76, 76, 8, wall ? '#60796b' : i >= cols * (rows - 1) ? '#9bad7a' : '#bad29b');
      if (wall) box(context, x - 28, y - 30, 56, 6, 3, '#8ca292');
    }
    const round = world.model.rounds[world.round];
    function drawFood(position, value, crowded) {
      const [x, y] = at(position);
      const centerY = y - (crowded ? 18 : 0);
      const height = crowded ? 38 : 54;
      const glow = world.help && accepts(world.model, round.relation, value, world.ref);
      box(context, x - 35, centerY - height / 2, 70, height, 11, glow ? '#ffd067' : '#fff0cc');
      drawValue(context, level, images, value, x, centerY, crowded ? 60 : 68);
    }
    if (round) for (const [position, value] of round.foods) {
      if (!world.body.includes(position)) drawFood(position, value, false);
    }
    box(context, 1048, 176, 157, 164, 24, '#325747');
    if (round) text(context, marks[round.relation], 1127, 208, 38, '#ffe3a3');
    box(context, 1058, 233, 137, 90, 17, '#fff0cc');
    drawValue(context, level, images, world.ref, 1127, 277, 122);
    if (world.startedAt === null) world.startedAt = game.t;
    const blend = Math.min(1, (game.t - world.startedAt) / .16);
    const segments = world.body.map((position, i) => {
      const [x, y] = at(position);
      const [ox, oy] = at(world.previous[i] ?? world.previous.at(-1));
      return [ox + (x - ox) * blend, oy + (y - oy) * blend];
    });
    context.save();
    context.beginPath();
    context.moveTo(...segments[0]);
    for (const point of segments.slice(1)) context.lineTo(...point);
    context.strokeStyle = '#518048';
    context.lineWidth = 24;
    context.lineCap = 'round';
    context.lineJoin = 'round';
    context.stroke();
    context.restore();
    for (let i = segments.length - 1; i >= 0; i--) {
      const [px, py] = segments[i];
      const head = i === 0;
      const tail = i === segments.length - 1;
      const angle = head ? rotation[world.direction] : tail ? Math.atan2(
        segments[i - 1][1] - py, segments[i - 1][0] - px) : 0;
      const frame = head ? 0 : tail ? 2 : 1;
      if (!sprite(context, images.frames[frame], px, py, head ? 72 : 62, 64, {angle})) {
        context.fillStyle = head ? '#336c4b' : '#60905f';
        K.draw.circle(context, px, py, head ? 24 : 20);
      }
    }
    if (round) for (const [position, value] of round.foods) {
      if (world.body.includes(position)) drawFood(position, value, true);
    }
  }

  return create(config, {
    controls: ['left', 'right', 'up', 'down', ['action', '↶', '回安全起点']], backdrop: '#779a68',
    validate, reset, update, draw, goal: level => level.rounds.length,
    adapt(world, misses) { world.help = misses >= 2; },
    player: world => center(...at(world.body[0]), 72, 64),
    goalAnchor: () => center(1127, 277, 135, 90),
    target(world) {
      const round = world.model.rounds[world.round];
      if (!round) return null;
      for (const [position, value] of round.foods) {
        if (accepts(world.model, round.relation, value, world.ref)) {
          const [x, y] = at(position);
          const covered = world.body.includes(position);
          return center(x, y - (covered ? 18 : 0), 70, covered ? 38 : 54);
        }
      }
      return null;
    },
    pilot(world, level, dt) {
      if (world.cooldown > dt || world.round >= world.model.rounds.length) return bot();
      const move = findMove(world.model, world.model.rounds[world.round], world.ref, world.body);
      return bot(move ?? 'action');
    },
  });
};
