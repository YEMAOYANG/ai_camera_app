// A lane crossing game. Each order requires a pickup followed by delivery.
// Goods, recipients and instructions are supplied by the authoring data.
K.gameTemplates.listenDelivery = config => {
  const {box, center, create, bot, ease, sprite, token, validToken} = Classic;
  const columns = 9;
  const lastRow = 4;
  const size = 86;
  const origin = [253, 149];
  const directions = [['up', 0, -1], ['left', -1, 0], ['right', 1, 0], ['down', 0, 1]];
  const models = new Map();
  const at = (col, row) => [origin[0] + (col + .5) * size, origin[1] + (row + .5) * size];
  const carPosition = world => {
    const [x, y] = at(world.vx, world.vy);
    return [x, y + 22 * Math.max(0, 1 - Math.min(world.vy, lastRow - world.vy))];
  };
  const modulo = (number, divisor) => (number % divisor + divisor) % divisor;

  function validate(level) {
    const {pickup, drop, orders, lanes, step} = level;
    function stations(values) {
      if (!Array.isArray(values) || values.length < 2 || values.length > 4 || values.some(station =>
        !Array.isArray(station) || station.length !== 2 || !validToken(station[0]) ||
        !Number.isInteger(station[1]) || station[1] < 0 || station[1] >= columns)) {
        throw new Error('invalid delivery stations');
      }
      const ids = new Map(values);
      if (ids.size !== values.length || new Set(ids.values()).size !== values.length) {
        throw new Error('duplicate delivery station');
      }
      return ids;
    }
    const goods = stations(pickup);
    const recipients = stations(drop);
    if (!Array.isArray(orders) || !orders.length || orders.length > 3 || orders.some(order =>
      !Array.isArray(order) || order.length !== 2 || !goods.has(order[0]) || !recipients.has(order[1]))) {
      throw new Error('invalid delivery order');
    }
    if (!(step >= .18 && step <= .42) || !Array.isArray(lanes) || lanes.length < 1 || lanes.length > 3 ||
      lanes.some(lane => !lane || !Number.isInteger(lane.row) || lane.row < 1 || lane.row >= lastRow ||
        !Number.isFinite(lane.phase) || !(Math.abs(lane.speed) >= .65 && Math.abs(lane.speed) <= 2.5) ||
        !(lane.spacing >= 3.2 && lane.spacing <= 6))) {
      throw new Error('invalid crossing lanes');
    }
    const roads = new Map(lanes.map(lane => [lane.row, lane]));
    if (roads.size !== lanes.length) throw new Error('duplicate crossing lane');
    models.set(level, {goods, recipients, roads});
  }

  function reset(level) {
    return {col: 4, row: lastRow, vx: 4, vy: lastRow, safeCol: 4, safeRow: lastRow, time: 0,
      cooldown: 0, order: 0, carried: null, delivered: new Map(), help: false, pulse: 0, heading: 'up',
      ...models.get(level)};
  }

  function target(world, level) {
    const order = level.orders[world.order];
    if (!order) return null;
    return world.carried === null
      ? {col: world.goods.get(order[0]), row: lastRow}
      : {col: world.recipients.get(order[1]), row: 0};
  }

  function offset(lane, time) {
    return modulo(lane.phase + time * lane.speed, lane.spacing);
  }

  function hits(world, col, row, time) {
    const lane = world.roads.get(row);
    if (!lane) return false;
    const distance = modulo(col - offset(lane, time) + lane.spacing / 2, lane.spacing) - lane.spacing / 2;
    return Math.abs(distance) < (world.help ? .46 : .57);
  }

  function stop(world, level, feedback) {
    const [x, y] = at(world.col, world.row);
    const goal = target(world, level);
    feedback.fx(x, y, '#ffe7ab');
    feedback.drop();
    if (!goal || goal.col !== world.col || goal.row !== world.row) {
      feedback.lost(x, y);
      return;
    }
    const [good, recipient] = level.orders[world.order];
    if (world.carried === null) {
      world.carried = good;
    } else {
      world.delivered.set(recipient, good);
      world.carried = null;
      world.order++;
    }
    world.pulse = .24;
    feedback.award(x, y);
  }

  function update(world, level, input, dt, feedback) {
    world.time += dt * (world.help ? .72 : 1);
    world.cooldown = Math.max(0, world.cooldown - dt);
    world.pulse = Math.max(0, world.pulse - dt);
    const direction = directions.find(([key]) => input.press(key) || input.held(key));
    if (input.press('action') && world.cooldown === 0) {
      stop(world, level, feedback);
      world.cooldown = level.step;
    } else if (direction && world.cooldown === 0) {
      const [key, dx, dy] = direction;
      const col = world.col + dx;
      const row = world.row + dy;
      if (col >= 0 && col < columns && row >= 0 && row <= lastRow) {
        world.col = col;
        world.row = row;
      }
      world.heading = key;
      world.cooldown = level.step;
      feedback.move();
      feedback.fx(...at(world.col, world.row));
    }
    if (hits(world, world.col, world.row, world.time)) {
      const position = at(world.col, world.row);
      world.col = world.safeCol;
      world.row = world.safeRow;
      world.vx = world.col;
      world.vy = world.row;
      world.cooldown = Math.max(world.cooldown, .32);
      feedback.lost(...position);
    } else if (!world.roads.has(world.row)) {
      world.safeCol = world.col;
      world.safeRow = world.row;
    }
    world.vx = ease(world.vx, world.col, dt, 22);
    world.vy = ease(world.vy, world.row, dt, 22);
  }

  function path(world, level, dt) {
    const goal = target(world, level);
    if (!goal) return undefined;
    if (goal.col === world.col && goal.row === world.row) return 'action';
    const wait = ['wait', 0, 0];
    const moves = [...directions, wait];
    const tick = (level.step + .034) * (world.help ? .72 : 1);
    const start = world.time + dt * (world.help ? .72 : 1);
    const queue = [{col: world.col, row: world.row, ticks: 0, first: null}];
    const seen = new Set();
    for (let i = 0; i < queue.length; i++) {
      const cell = queue[i];
      if (cell.ticks >= 22) continue;
      for (const [move, dx, dy] of moves) {
        const col = cell.col + dx;
        const row = cell.row + dy;
        if (col < 0 || col >= columns || row < 0 || row > lastRow) continue;
        const time = start + cell.ticks * tick;
        const key = (cell.ticks * (lastRow + 1) + row) * columns + col;
        if (seen.has(key)) continue;
        if ([0, .25, .5, .75, 1].some(part => hits(world, col, row, time + tick * part))) continue;
        const first = cell.first ?? move;
        if (col === goal.col && row === goal.row) return first;
        seen.add(key);
        queue.push({col, row, ticks: cell.ticks + 1, first});
      }
    }
    return undefined;
  }

  function draw(world, level, context, images) {
    box(context, 239, 135, 802, 458, 25, '#274c3e');
    context.save();
    context.beginPath();
    context.rect(origin[0], origin[1], columns * size, (lastRow + 1) * size);
    context.clip();
    for (let row = 0; row <= lastRow; row++) {
      const lane = world.roads.get(row);
      for (let col = 0; col < columns; col++) {
        const [x, y] = at(col, row);
        const colors = lane ? ['#66766d', '#5c6e64'] : ['#b8c990', '#c5d29d'];
        box(context, x - 42, y - 42, 84, 84, 8, colors[col % 2]);
        if (lane) box(context, x - 18, y + 32, 36, 4, 2, '#eadcb2');
      }
      if (lane) {
        for (let col = offset(lane, world.time) - lane.spacing; col < columns + 1; col += lane.spacing) {
          const [x, y] = at(col, row);
          if (!sprite(context, images.frames[2], x, y, 69, 64, {flip: lane.speed < 0})) {
            box(context, x - 33, y - 22, 66, 44, 12, '#ead395');
          }
        }
      }
    }
    context.restore();
    const goal = world.help ? target(world, level) : null;
    for (const [row, stations] of [[lastRow, world.goods], [0, world.recipients]]) {
      for (const [id, col] of stations) {
        const [x, y] = at(col, row);
        const highlighted = goal?.row === row && goal.col === col;
        box(context, x - 38, y - 39, 76, 78, 12, highlighted ? '#ffcf66' : '#fff1d0');
        token(context, images, id, x, y - 4, 65, 65, level.labels);
        if (row === 0 && world.delivered.has(id)) {
          box(context, x + 14, y + 12, 26, 25, 7, '#fff1d0');
          token(context, images, world.delivered.get(id), x + 27, y + 24, 22, 22, level.labels);
        }
      }
    }
    const [x, y] = carPosition(world);
    // Show both the station's picture and the car while the car is parked.
    if (!sprite(context, images.frames[world.pulse > 0 ? 1 : 0], x, y, 45, 45,
      {flip: world.heading === 'left'})) {
      box(context, x - 20, y - 20, 40, 40, 13, '#ca6b47');
    }
    box(context, 1082, 219, 116, 116, 21, '#2f5544');
    box(context, 1101, 238, 78, 78, 16, '#e1bd7e');
    if (world.carried !== null) token(context, images, world.carried, 1140, 277, 69, 69, level.labels);
  }

  return create(config, {
    controls: ['left', 'right', 'up', 'down', ['action', '▣', '拿取或交付']], backdrop: '#789c70',
    validate, reset, update, draw,
    goal: level => level.orders.length * 2,
    adapt(world, misses) { world.help = misses >= 2; },
    player: world => center(...carPosition(world), 58, 54),
    target(world, level) {
      const goal = target(world, level);
      return goal ? center(...at(goal.col, goal.row), 76, 78) : null;
    },
    pilot(world, level, dt) {
      if (world.cooldown > 0) return bot();
      const move = path(world, level, dt);
      return move && move !== 'wait' ? bot(move) : bot();
    },
  });
};
