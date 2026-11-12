const config = {
  "title": "金鱼快门观察站",
  "sub": "等金鱼和上面的小图角度一样，再按快门。",
  "doneText": "同一条金鱼的两种看法都留下来了。",
  "voiceLead": true,
  "stepVoiceLead": true,
  "art": {
    "backdrop": "__IMG:animal-workbench__",
    "sticker": "__IMG:animal-sticker__",
    "icons": {
      "goldfish-side": "__IMG:goldfish-side__",
      "goldfish-top": "__IMG:goldfish-top__"
    }
  },
  "levels": [
    {
      "rate": 0.58,
      "range": 106,
      "aperture": 149,
      "shots": [
        1,
        0
      ],
      "photoViews": {
        "top": "goldfish-top",
        "side": "goldfish-side"
      },
      "hints": [
        "先把整条金鱼放进虚线框。",
        "看上面的小图，等金鱼换成同一个角度。"
      ]
    },
    {
      "rate": 0.78,
      "range": 166,
      "aperture": 120,
      "shots": [
        0,
        1,
        0
      ],
      "photoViews": {
        "top": "goldfish-top",
        "side": "goldfish-side"
      },
      "hints": [
        "先把整条金鱼放进虚线框。",
        "看上面的小图，等金鱼换成同一个角度。"
      ]
    },
    {
      "rate": 1.02,
      "range": 216,
      "aperture": 104,
      "shots": [
        1,
        0,
        1,
        0
      ],
      "photoViews": {
        "top": "goldfish-top",
        "side": "goldfish-side"
      },
      "hints": [
        "先把整条金鱼放进虚线框。",
        "看上面的小图，等金鱼换成同一个角度。"
      ]
    }
  ],
  "cues": [
    {
      "goal": "fish-photo-goal",
      "hint": "fish-photo-goal",
      "hint2": "fish-photo-goal",
      "praise": "fish-photo-praise",
      "steps": [
        "fish-photo-top",
        "fish-photo-side"
      ]
    },
    {
      "goal": "fish-photo-goal",
      "hint": "fish-photo-goal",
      "hint2": "fish-photo-goal",
      "praise": "fish-photo-praise",
      "steps": [
        "fish-photo-side",
        "fish-photo-top",
        "fish-photo-side"
      ]
    },
    {
      "goal": "fish-photo-goal",
      "hint": "fish-photo-goal",
      "hint2": "fish-photo-goal",
      "praise": "fish-photo-praise",
      "steps": [
        "fish-photo-top",
        "fish-photo-side",
        "fish-photo-top",
        "fish-photo-side"
      ]
    }
  ],
  "observation": {
    "sceneId": "scene-p04",
    "trials": {
      "goldfish-views": {
        "top": [
          "goldfish-top"
        ],
        "side": [
          "goldfish-side"
        ]
      }
    }
  }
};
K.ready({title: config.title, sub: config.sub});
K.game(K.gameTemplates.shutterScout(config));
