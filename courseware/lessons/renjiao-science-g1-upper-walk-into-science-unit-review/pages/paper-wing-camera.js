const config = {
  "title": "拍下纸翼的变化",
  "sub": "让纸翼留在框里，等它和小图一个样再拍。",
  "doneText": "把纸翼看起来宽和窄的样子留下来啦。",
  "voiceLead": true,
  "stepVoiceLead": true,
  "art": {
    "sticker": "__IMG:paper-wing__",
    "icons": {
      "paper-wing": "__IMG:paper-wing__",
      "paper-wing-side": "__IMG:paper-wing-side__"
    }
  },
  "levels": [
    {
      "rate": 0.6,
      "range": 115,
      "aperture": 145,
      "shots": [
        1,
        0
      ],
      "hints": [
        "先把纸翼放进虚线框。",
        "看上面的小图，等纸翼换到对应的方向。"
      ],
      "photoViews": {
        "top": "paper-wing",
        "side": "paper-wing-side"
      }
    },
    {
      "rate": 0.8,
      "range": 177,
      "aperture": 120,
      "shots": [
        0,
        1,
        0
      ],
      "hints": [
        "先把纸翼放进虚线框。",
        "看上面的小图，等纸翼换到对应的方向。"
      ],
      "photoViews": {
        "top": "paper-wing",
        "side": "paper-wing-side"
      }
    },
    {
      "rate": 1.04,
      "range": 232,
      "aperture": 102,
      "shots": [
        1,
        0,
        1,
        0
      ],
      "hints": [
        "先把纸翼放进虚线框。",
        "看上面的小图，等纸翼换到对应的方向。"
      ],
      "photoViews": {
        "top": "paper-wing",
        "side": "paper-wing-side"
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
        "photo-wide",
        "photo-narrow"
      ]
    },
    {
      "goal": "photo-goal",
      "hint": "photo-hint",
      "hint2": "photo-goal",
      "praise": "photo-praise",
      "steps": [
        "photo-narrow",
        "photo-wide",
        "photo-narrow"
      ]
    },
    {
      "goal": "photo-goal",
      "hint": "photo-hint",
      "hint2": "photo-goal",
      "praise": "photo-praise",
      "steps": [
        "photo-wide",
        "photo-narrow",
        "photo-wide",
        "photo-narrow"
      ]
    }
  ],
  "observation": {
    "sceneId": "scene-p06",
    "trials": {
      "paper-wing-pair": {
        "top": [
          "paper-wing"
        ],
        "side": [
          "paper-wing-side"
        ]
      }
    }
  }
};
K.ready({title:config.title,sub:config.sub});
K.stage().append(K.$('#science-shutter-goal'));
K.game(K.gameTemplates.shutterScout(config));
