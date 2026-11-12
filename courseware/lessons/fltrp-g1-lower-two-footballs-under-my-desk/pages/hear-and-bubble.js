const placePictures = {
  deskBelowTwo: "__IMG:two-footballs-under-desk__",
  deskTopTwo: "__IMG:two-footballs-on-desk__",
  deskBelowOne: "__IMG:one-football-under-desk__",
  chairBasket: "__IMG:one-basketball-under-chair__",
  chairFoot: "__IMG:one-football-under-chair__",
  seatBasket: "__IMG:one-basketball-on-chair__",
  boxThree: "__IMG:three-ping-pong-in-box__",
  deskTopThree: "__IMG:three-ping-pong-on-desk__",
  boxFive: "__IMG:five-ping-pong-in-box__",
  deskBasketTwo: "__IMG:two-basketballs-under-desk__",
  deskBasketTop: "__IMG:two-basketballs-on-desk__"
};
const firstDrift = 7;
const firstPace = 0.52;
const hints = ["再听球在哪里。", "把船移到发亮的图卡下。"];
const cuesFor = (steps) => ({
  goal: steps[0], steps, hint: "bubble-hint", hint2: "bubble-help", praise: "bubble-praise"
});

K.ready({title: "听完整句话再碰泡泡", sub: "听球、几个、在哪儿，移到相符的图下，再吹泡泡。"});

const boat = K.game(K.gameTemplates.wordBubbles({
  voiceLead: true, stepVoiceLead: true,
  cues: [
    cuesFor(["bubble-under-two", "bubble-on-two"]),
    cuesFor(["bubble-chair-basket", "bubble-in-three", "bubble-chair-on"]),
    cuesFor(["bubble-desk-basket-two", "bubble-chair-foot", "bubble-in-five", "bubble-on-three"])
  ],
  art: {
    backdrop: "__IMG:equipment-corner__",
    frames: ["__IMG:boat__", "__IMG:boat__"],
    sticker: "__IMG:star__",
    icons: placePictures
  },
  doneText: "球、几个、在哪儿，都听清了！",
  levels: [
    {
      rounds: [
        {target: "deskBelowTwo", cards: ["deskBelowTwo", "deskTopTwo"]},
        {target: "deskTopTwo", cards: ["deskBelowTwo", "deskTopTwo"]}
      ],
      drift: firstDrift, pace: firstPace, tolerance: 62, hints
    },
    {
      rounds: [
        {target: "chairBasket", cards: ["seatBasket", "chairBasket", "chairFoot"]},
        {target: "boxThree", cards: ["boxThree", "boxFive", "deskTopThree"]},
        {target: "seatBasket", cards: ["chairBasket", "chairFoot", "seatBasket"]}
      ],
      drift: 17, pace: 0.72, tolerance: 58, hints
    },
    {
      rounds: [
        {target: "deskBasketTwo", cards: ["deskBelowTwo", "deskBasketTop", "deskBasketTwo"]},
        {target: "chairFoot", cards: ["chairFoot", "chairBasket", "deskBelowOne"]},
        {target: "boxFive", cards: ["boxThree", "boxFive", "deskTopThree"]},
        {target: "deskTopThree", cards: ["boxFive", "deskTopThree", "boxThree"]}
      ],
      drift: 27, pace: 0.94, tolerance: 54, hints
    }
  ]
}));
boat.follow("#first-place-card", ({data}) => {
  const time = data.w?.t ?? 0;
  const x = 485 + Math.sin(time * firstPace) * firstDrift;
  return {x: x - 56, y: 192, w: 112, h: 118};
});
