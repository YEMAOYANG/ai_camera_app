K.ready({"title": "交换落块", "sub": "只换两堆顺序，横移后落在底牌旁。"});

K.game(K.gameTemplates.fallingTiles({
  "art": {
    "backdrop": "__IMG:workshop-stage__",
    "sticker": "__IMG:kite-sticker__",
    "icons": {
      "t3-9": "__IMG:t3-9__",
      "t4-7": "__IMG:t4-7__",
      "t4-8": "__IMG:t4-8__",
      "t5-7": "__IMG:t5-7__",
      "t5-8": "__IMG:t5-8__",
      "t5-9": "__IMG:t5-9__",
      "t6-6r": "__IMG:t6-6r__",
      "t7-4r": "__IMG:t7-4r__",
      "t7-5r": "__IMG:t7-5r__",
      "t8-4r": "__IMG:t8-4r__",
      "t8-5r": "__IMG:t8-5r__",
      "t9-3r": "__IMG:t9-3r__",
      "t9-5r": "__IMG:t9-5r__"
    },
    "frames": []
  },
  "voiceLead": true,
  "doneText": "纸鸢材料准备好啦！",
  "cues": [
    {
      "goal": "swap-pair-play-goal",
      "hint": "swap-pair-play-hint",
      "hint2": "swap-pair-play-hint2",
      "praise": "swap-pair-play-praise"
    },
    {
      "goal": "swap-pair-play-goal",
      "hint": "swap-pair-play-hint",
      "hint2": "swap-pair-play-hint2",
      "praise": "swap-pair-play-praise"
    },
    {
      "goal": "swap-pair-play-goal",
      "hint": "swap-pair-play-hint",
      "hint2": "swap-pair-play-hint2",
      "praise": "swap-pair-play-praise"
    }
  ],
  "levels": [
    {
      "bottom": [
        "t9-3r",
        null,
        null,
        null,
        "t8-5r",
        null
      ],
      "pieces": [
        "t3-9",
        "t5-8"
      ],
      "pairs": [
        [
          "t3-9",
          "t9-3r"
        ],
        [
          "t5-8",
          "t8-5r"
        ]
      ],
      "interval": 1.24,
      "symbol": "↔",
      "hints": [
        "先比原来两堆的数，再看落点。",
        "把块挪到配对底牌旁边。看浅色落点。"
      ]
    },
    {
      "bottom": [
        null,
        "t7-4r",
        null,
        "t7-5r",
        null,
        "t8-4r"
      ],
      "pieces": [
        "t4-7",
        "t5-7",
        "t4-8"
      ],
      "pairs": [
        [
          "t4-7",
          "t7-4r"
        ],
        [
          "t5-7",
          "t7-5r"
        ],
        [
          "t4-8",
          "t8-4r"
        ]
      ],
      "interval": 0.91,
      "symbol": "↔",
      "hints": [
        "先比原来两堆的数，再看落点。",
        "把块挪到配对底牌旁边。看浅色落点。"
      ]
    },
    {
      "bottom": [
        null,
        "t8-4r",
        "t9-5r",
        "t7-5r",
        null,
        "t6-6r"
      ],
      "pieces": [
        "t4-8",
        "t5-7",
        "t5-9"
      ],
      "pairs": [
        [
          "t4-8",
          "t8-4r"
        ],
        [
          "t5-7",
          "t7-5r"
        ],
        [
          "t5-9",
          "t9-5r"
        ]
      ],
      "interval": 0.65,
      "symbol": "↔",
      "hints": [
        "先比原来两堆的数，再看落点。",
        "把块挪到配对底牌旁边。看浅色落点。"
      ]
    }
  ]
}));
