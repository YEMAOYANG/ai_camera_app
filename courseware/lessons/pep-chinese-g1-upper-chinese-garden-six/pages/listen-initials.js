K.ready({"title": "听准开头再发泡泡", "sub": "听完整词，对准开头的声母卡。"});

K.game(K.gameTemplates.wordBubbles({
  "voiceLead": true,
  "stepVoiceLead": true,
  "art": {
    "backdrop": "__IMG:bubble-backdrop__",
    "frames": [
      "__IMG:bubble-boat__",
      "__IMG:bubble-boat-pop__"
    ],
    "icons": {
      "n": "__IMG:initial-n__",
      "l": "__IMG:initial-l__",
      "sh": "__IMG:initial-sh__",
      "s": "__IMG:initial-s__",
      "z": "__IMG:initial-z__",
      "zh": "__IMG:initial-zh__"
    },
    "sticker": "__IMG:garden-reward__"
  },
  "doneText": "你听清了每个词的开头！",
  "cues": [
    {
      "goal": "cow",
      "hint": "sound-hint",
      "hint2": "sound-help",
      "praise": "sound-praise",
      "steps": [
        "cow",
        "pear"
      ]
    },
    {
      "goal": "stone",
      "hint": "sound-hint",
      "hint2": "sound-help",
      "praise": "sound-praise",
      "steps": [
        "stone",
        "umbrella",
        "hand"
      ]
    },
    {
      "goal": "date",
      "hint": "sound-hint",
      "hint2": "sound-help",
      "praise": "sound-praise",
      "steps": [
        "date",
        "bell",
        "fall",
        "four"
      ]
    }
  ],
  "levels": [
    {
      "rounds": [
        {
          "target": "n",
          "cards": [
            "n",
            "l"
          ]
        },
        {
          "target": "l",
          "cards": [
            "n",
            "l"
          ]
        }
      ],
      "drift": 10,
      "pace": 0.55,
      "tolerance": 61,
      "hints": [
        "重听词语，找开头的声母。",
        "对准亮起来的声母，再发泡泡。"
      ]
    },
    {
      "rounds": [
        {
          "target": "sh",
          "cards": [
            "s",
            "sh",
            "n"
          ]
        },
        {
          "target": "s",
          "cards": [
            "l",
            "sh",
            "s"
          ]
        },
        {
          "target": "sh",
          "cards": [
            "sh",
            "l",
            "s"
          ]
        }
      ],
      "drift": 22,
      "pace": 0.76,
      "tolerance": 56,
      "hints": [
        "重听词语，找开头的声母。",
        "对准亮起来的声母，再发泡泡。"
      ]
    },
    {
      "rounds": [
        {
          "target": "z",
          "cards": [
            "zh",
            "z",
            "sh"
          ]
        },
        {
          "target": "zh",
          "cards": [
            "s",
            "z",
            "zh"
          ]
        },
        {
          "target": "l",
          "cards": [
            "l",
            "n",
            "zh"
          ]
        },
        {
          "target": "s",
          "cards": [
            "l",
            "sh",
            "s"
          ]
        }
      ],
      "drift": 32,
      "pace": 1.04,
      "tolerance": 51,
      "hints": [
        "重听词语，找开头的声母。",
        "对准亮起来的声母，再发泡泡。"
      ]
    }
  ]
}));
