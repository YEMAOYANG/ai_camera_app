const config = {
  "title": "苹果快门侦探",
  "sub": "把苹果框进去，等它和上面的小图一样再拍。",
  "doneText": "你留下了同一颗苹果从上面和侧面看见的样子。",
  "voiceLead": true,
  "stepVoiceLead": true,
  "art": {
    "backdrop": "__IMG:orchard-workbench__",
    "sticker": "__IMG:orchard-sticker__",
    "icons": {
      "apple-top": "__IMG:apple-top__",
      "apple-side": "__IMG:apple-side__"
    }
  },
  "levels": [
    {
      "rate": 0.58,
      "range": 112,
      "aperture": 148,
      "shots": [
        1,
        0
      ],
      "hints": [
        "先把苹果框在虚线框里。",
        "看上面的目标图，再等苹果换方向。"
      ],
      "photoViews": {
        "top": "apple-top",
        "side": "apple-side"
      }
    },
    {
      "rate": 0.79,
      "range": 176,
      "aperture": 120,
      "shots": [
        0,
        1,
        0
      ],
      "hints": [
        "先把苹果框在虚线框里。",
        "看上面的目标图，再等苹果换方向。"
      ],
      "photoViews": {
        "top": "apple-top",
        "side": "apple-side"
      }
    },
    {
      "rate": 1.04,
      "range": 228,
      "aperture": 101,
      "shots": [
        1,
        0,
        1,
        0
      ],
      "hints": [
        "先把苹果框在虚线框里。",
        "看上面的目标图，再等苹果换方向。"
      ],
      "photoViews": {
        "top": "apple-top",
        "side": "apple-side"
      }
    }
  ],
  "cues": [
    {
      "goal": "photo-goal",
      "hint": "photo-hint",
      "hint2": "photo-goal",
      "praise": "photo-praise",
      "steps": [
        "photo-top",
        "photo-side"
      ]
    },
    {
      "goal": "photo-goal",
      "hint": "photo-hint",
      "hint2": "photo-goal",
      "praise": "photo-praise",
      "steps": [
        "photo-side",
        "photo-top",
        "photo-side"
      ]
    },
    {
      "goal": "photo-goal",
      "hint": "photo-hint",
      "hint2": "photo-goal",
      "praise": "photo-praise",
      "steps": [
        "photo-top",
        "photo-side",
        "photo-top",
        "photo-side"
      ]
    }
  ],
  "observation": {
    "sceneId": "scene-p04",
    "trials": {
      "apple-views": {
        "top": [
          "apple-top"
        ],
        "side": [
          "apple-side"
        ]
      }
    }
  }
};
K.ready({title: config.title, sub: config.sub});
K.game(K.gameTemplates.shutterScout(config));
