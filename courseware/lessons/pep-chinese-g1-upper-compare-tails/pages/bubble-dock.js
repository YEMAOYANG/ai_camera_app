const speech = (steps) => ({
  goal: steps[0], steps, hint: "word-hint", hint2: "word-help", praise: "word-praise"
});

K.ready({title: "听准了再吹泡泡", sub: "听词找字，移到下面，再吹泡泡。"});

const firstDrift = 9;
const firstPace = 0.53;
const boatConfig = K.gameTemplates.wordBubbles({
  voiceLead: true,
  stepVoiceLead: true,
  cues: [
    speech(["hear-bi", "hear-ba"]),
    speech(["hear-chang", "hear-duan", "hear-wei"]),
    speech(["hear-san", "hear-tu", "hear-ba-hold", "hear-gong"])
  ],
  art: {
    backdrop: "__IMG:river__", sticker: "__IMG:photo-badge__",
    frames: ["__IMG:boat__", "__IMG:boat-bubble__"],
    icons: {
      bi: "__IMG:char-bi__", ba: "__IMG:char-ba__",
      chang: "__IMG:char-chang__", duan: "__IMG:char-duan__", wei: "__IMG:char-wei__",
      san: "__IMG:char-san__", tu: "__IMG:char-tu__",
      "ba-hold": "__IMG:char-ba-hold__", gong: "__IMG:char-gong__"
    }
  },
  doneText: "每张听清的字卡都接住啦！",
  levels: [
    {
      rounds: [
        {target: "bi", cards: ["bi", "ba"]},
        {target: "ba", cards: ["bi", "ba"]}
      ],
      drift: firstDrift, pace: firstPace, tolerance: 62,
      hints: ["重听刚才的词，想想找哪一个字。", "看亮起来的字卡，移到它的下面。"]
    },
    {
      rounds: [
        {target: "chang", cards: ["wei", "chang", "duan"]},
        {target: "duan", cards: ["duan", "chang", "wei"]},
        {target: "wei", cards: ["duan", "chang", "wei"]}
      ],
      drift: 20, pace: 0.77, tolerance: 57,
      hints: ["重听刚才的词，想想找哪一个字。", "看亮起来的字卡，移到它的下面。"]
    },
    {
      rounds: [
        {target: "san", cards: ["gong", "tu", "san"]},
        {target: "tu", cards: ["tu", "ba-hold", "wei"]},
        {target: "ba-hold", cards: ["ba", "ba-hold", "duan"]},
        {target: "gong", cards: ["gong", "bi", "san"]}
      ],
      drift: 31, pace: 1.04, tolerance: 52,
      hints: ["重听刚才的词，想想找哪一个字。", "看亮起来的字卡，移到它的下面。"]
    }
  ]
});

boatConfig.onState = (_game, state) => {
  if (state.demo === false) {
    K.$$('.teach-hl').forEach(element => element.classList.remove('teach-hl'));
  }
};
const boat = K.game(boatConfig);

// Keep the teaching outline on 比 when the next target switches to 巴.
boat.follow("#bubble-first-word", (game) => {
  const time = game.data.w?.t ?? 0;
  const x = 485 + Math.sin(time * firstPace) * firstDrift;
  return {x: x - 56, y: 191, w: 112, h: 118};
});
