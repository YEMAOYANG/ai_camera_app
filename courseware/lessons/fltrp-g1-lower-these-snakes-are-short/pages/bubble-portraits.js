K.ready({"title": "听句子，接住动物组", "sub": "听它们是谁、什么样，再对准照片。"});

K.game(K.gameTemplates.wordBubbles({
  "art": {
    "backdrop": "__IMG:zoo-stage__",
    "sticker": "__IMG:zoo-bot__",
    "frames": [
      "__IMG:zoo-boat__",
      "__IMG:zoo-boat-action__"
    ],
    "icons": {
      "short": "__IMG:zoo-short-group__",
      "long": "__IMG:zoo-long-group__",
      "tall": "__IMG:zoo-tall-group__",
      "low": "__IMG:zoo-low-group__",
      "big": "__IMG:zoo-big-group__",
      "small": "__IMG:zoo-small-group__",
      "tiger": "__IMG:zoo-tiger-group__"
    }
  },
  "voiceLead": true,
  "stepVoiceLead": true,
  "cues": [
    {
      "goal": "hear-short",
      "steps": [
        "hear-short",
        "hear-long"
      ],
      "hint": "bubble-hint",
      "hint2": "bubble-help",
      "praise": "bubble-good"
    },
    {
      "goal": "hear-tall",
      "steps": [
        "hear-tall",
        "hear-low",
        "hear-big"
      ],
      "hint": "bubble-hint",
      "hint2": "bubble-help",
      "praise": "bubble-good"
    },
    {
      "goal": "hear-tiger",
      "steps": [
        "hear-tiger",
        "hear-short",
        "hear-tall",
        "hear-small"
      ],
      "hint": "bubble-hint",
      "hint2": "bubble-help",
      "praise": "bubble-good"
    }
  ],
  "doneText": "动物园的路线走完啦！",
  "levels": [
    {
      "rounds": [
        {
          "target": "short",
          "cards": [
            "short",
            "long"
          ]
        },
        {
          "target": "long",
          "cards": [
            "short",
            "long"
          ]
        }
      ],
      "drift": 7,
      "pace": 0.62,
      "tolerance": 62,
      "hints": [
        "先重听，再看这组的轮廓。",
        "看亮起的那组，慢一点对准。"
      ]
    },
    {
      "rounds": [
        {
          "target": "tall",
          "cards": [
            "tall",
            "low",
            "big"
          ]
        },
        {
          "target": "low",
          "cards": [
            "big",
            "low",
            "tall"
          ]
        },
        {
          "target": "big",
          "cards": [
            "low",
            "tall",
            "big"
          ]
        }
      ],
      "drift": 18,
      "pace": 0.86,
      "tolerance": 55,
      "hints": [
        "先重听，再看这组的轮廓。",
        "看亮起的那组，慢一点对准。"
      ]
    },
    {
      "rounds": [
        {
          "target": "tiger",
          "cards": [
            "big",
            "tiger",
            "long"
          ]
        },
        {
          "target": "short",
          "cards": [
            "long",
            "tiger",
            "short"
          ]
        },
        {
          "target": "tall",
          "cards": [
            "tall",
            "low",
            "small"
          ]
        },
        {
          "target": "small",
          "cards": [
            "big",
            "tiger",
            "small"
          ]
        }
      ],
      "drift": 34,
      "pace": 1.21,
      "tolerance": 50,
      "hints": [
        "先重听，再看这组的轮廓。",
        "看亮起的那组，慢一点对准。"
      ]
    }
  ]
}));
