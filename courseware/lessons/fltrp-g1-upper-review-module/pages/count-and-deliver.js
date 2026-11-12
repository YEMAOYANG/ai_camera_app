const cuesFor = (steps) => ({
  goal: steps[0], steps, hint: "order-hint", hint2: "order-help", praise: "order-praise"
});
const hints = ["再听要拿哪一种、有几个。", "找发亮的格子，等车过去。"];
const icons = {
  "ball-5": "__IMG:ball-5__", "ball-3": "__IMG:ball-3__", "book-4": "__IMG:book-4__",
  "schoolbag-2": "__IMG:schoolbag-2__", "schoolbag-4": "__IMG:schoolbag-4__",
  "pencil-6": "__IMG:pencil-6__", "pencil-7": "__IMG:pencil-7__", "book-6": "__IMG:book-6__",
  milo: "__IMG:badge-star__", nia: "__IMG:badge-sun__", kai: "__IMG:badge-leaf__"
};

K.ready({title: "听清数量再送货", sub: "先点拍手图听次数，再把同样多的球送给对应的人。"});

const options = K.gameTemplates.listenDelivery({
  voiceLead: true, stepVoiceLead: true,
  cues: [
    cuesFor(["clap-pickup", "deliver-milo"]),
    cuesFor(["pickup-books-four", "deliver-nia", "pickup-bags-two", "deliver-milo"]),
    cuesFor(["pickup-pencils-six", "deliver-kai", "pickup-pencils-seven",
             "deliver-milo", "pickup-books-six", "deliver-nia"])
  ],
  art: {
    backdrop: "__IMG:delivery-path__", sticker: "__IMG:badge-star__",
    frames: ["__IMG:toy-van__", "__IMG:toy-van__", "__IMG:toy-van__"], icons
  },
  doneText: "每张订单都送到啦！",
  levels: [
    {
      pickup: [["ball-5", 4], ["ball-3", 6]], drop: [["milo", 4], ["nia", 6]],
      orders: [["ball-5", "milo"]],
      lanes: [{row: 2, speed: 0.81, spacing: 5.7, phase: 1.3}], step: 0.34, hints
    },
    {
      pickup: [["book-4", 2], ["schoolbag-2", 5], ["schoolbag-4", 8]],
      drop: [["nia", 1], ["milo", 5], ["kai", 8]],
      orders: [["book-4", "nia"], ["schoolbag-2", "milo"]],
      lanes: [{row: 1, speed: -1.14, spacing: 4.8, phase: 2.1},
              {row: 3, speed: 1.23, spacing: 4.9, phase: 1.1}], step: 0.27, hints
    },
    {
      pickup: [["pencil-6", 1], ["pencil-7", 4], ["book-6", 7]],
      drop: [["nia", 2], ["milo", 5], ["kai", 8]],
      orders: [["pencil-6", "kai"], ["pencil-7", "milo"], ["book-6", "nia"]],
      lanes: [{row: 1, speed: -1.65, spacing: 4.3, phase: 0.9},
              {row: 2, speed: 1.53, spacing: 4.5, phase: 2.2},
              {row: 3, speed: -1.53, spacing: 4.3, phase: 1.5}], step: 0.23, hints
    }
  ]
});

const art = Object.fromEntries(Object.entries(icons).map(([key, url]) => {
  const img = new Image();
  img.src = url;
  return [key, img];
}));
const claps = new Audio("__AUDIO:five-claps__");
claps.preload = "none";
const button = K.$("#listen-claps");
K.stage().appendChild(button);
let heard = false, playing = false, speaking = false, visible = true, restoreMusic = false;
const firstClue = (g) => g.state === "play" && g.level === 0 &&
  g.data.progress === 0 && !g.auto && !g.paused;

function stopClaps() {
  if (!playing) return;
  playing = false;
  claps.pause();
  // The shared controls clear their held and queued inputs when focus is lost.
  // Flush presses made during the listening cue before handing control back.
  window.dispatchEvent(new Event("blur"));
  const music = K.$(".arc-music");
  const replay = K.$(".arc-voice");
  music.disabled = false;
  replay.disabled = false;
  if (restoreMusic) music.click();
  restoreMusic = false;
}
claps.addEventListener("ended", () => {
  heard = true;
  stopClaps();
});
claps.addEventListener("error", () => {
  if (!playing) return;
  stopClaps();
  K.game.current.say("声音没有播完。请再点一次。", "no", 2);
});
window.addEventListener("mira-narration-state", ({detail}) => {
  if (detail?.status === "playing") {
    speaking = true;
    stopClaps();
  }
  if (["ready", "hidden", "error", "missing"].includes(detail?.status)) speaking = false;
});
window.addEventListener("message", (event) => {
  if (event.source !== window.parent || event.data?.type !== "MIRA_NARRATION_VISIBILITY") return;
  visible = event.data.visible === true;
  if (!visible) stopClaps();
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) stopClaps();
});

button.addEventListener("click", () => {
  const game = K.game.current;
  if (!firstClue(game) || speaking || playing || !visible || document.hidden) return;
  playing = true;
  const music = K.$(".arc-music");
  restoreMusic = music.getAttribute("aria-pressed") === "true";
  if (restoreMusic) music.click();
  music.disabled = true;
  K.$(".arc-voice").disabled = true;
  claps.currentTime = 0;
  claps.play().catch(() => {
    if (!playing) return;
    stopClaps();
    game.say("声音没有播完。请再点一次。", "no", 2);
  });
});

const reset = options.reset;
options.reset = (game, level) => {
  stopClaps();
  heard = false;
  reset(game, level);
};
const update = options.update;
options.update = (game, dt) => {
  if (firstClue(game) && (!heard || playing)) return;
  update(game, dt);
};
const draw = options.draw;
options.draw = (game, context) => {
  draw(game, context);
  const show = firstClue(game);
  button.hidden = !show;
  button.disabled = speaking || playing || !visible;
  if (show && (!heard || playing)) {
    for (const control of K.$$(".arc-pad button")) control.disabled = true;
  }
  const world = game.data.w;
  if (!world || world.row !== 4) return;
  const selected = game.data.level.pickup.find(([, col]) => col === world.col);
  const img = selected && art[selected[0]];
  if (img?.complete && img.naturalWidth) context.drawImage(img, 33, 268, 168, 168);
};
const courier = K.game(options);
courier.follow("#first-order", () => ({x: 602, y: 497, w: 76, h: 78}));
courier.follow("#receiving-windows", () => ({x: 592, y: 151, w: 268, h: 78}));
