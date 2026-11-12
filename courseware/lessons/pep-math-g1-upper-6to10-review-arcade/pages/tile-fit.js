K.ready({"title": "落块配对工坊", "sub": "先算清两块的关系，再让它们在同一行挨着。"});

K.game(K.gameTemplates.fallingTiles({
  "art": {
    "backdrop": "__IMG:kiln__",
    "sticker": "__IMG:sticker__"
  },
  "voiceLead": true,
  "cues": [
    {
      "goal": "tiles-eight",
      "hint": "tiles-hint",
      "hint2": "tiles-help",
      "praise": "tiles-good"
    },
    {
      "goal": "tiles-add",
      "hint": "tiles-hint",
      "hint2": "tiles-help",
      "praise": "tiles-good"
    },
    {
      "goal": "tiles-mix",
      "hint": "tiles-hint",
      "hint2": "tiles-help",
      "praise": "tiles-good"
    }
  ],
  "doneText": "算式卡都找到搭档啦！",
  "levels": [
    {
      "total": 8,
      "bottom": [
        null,
        1,
        null,
        5,
        null,
        4
      ],
      "pieces": [
        4,
        3,
        7
      ],
      "interval": 1.35,
      "hints": [
        "先算清两块的关系。看淡淡的影子，想想落在哪儿。",
        "要在同一行相邻。卡在上面了，换一处再试。"
      ]
    },
    {
      "pairs": [
        [
          "2+5",
          7
        ],
        [
          "3+3",
          6
        ],
        [
          "1+4",
          5
        ]
      ],
      "symbol": "＝",
      "bottom": [
        7,
        null,
        6,
        null,
        5,
        null
      ],
      "pieces": [
        "3+3",
        "1+4",
        "2+5"
      ],
      "interval": 1.04,
      "hints": [
        "先算清两块的关系。看淡淡的影子，想想落在哪儿。",
        "要在同一行相邻。卡在上面了，换一处再试。"
      ]
    },
    {
      "pairs": [
        [
          "9−5",
          4
        ],
        [
          "2+3",
          5
        ],
        [
          "10−1",
          9
        ],
        [
          "9−1",
          8
        ]
      ],
      "symbol": "＝",
      "bottom": [
        null,
        4,
        5,
        null,
        9,
        8
      ],
      "pieces": [
        "9−5",
        "2+3",
        "10−1",
        "9−1"
      ],
      "interval": 0.82,
      "hints": [
        "先算清两块的关系。看淡淡的影子，想想落在哪儿。",
        "要在同一行相邻。卡在上面了，换一处再试。"
      ]
    }
  ]
}));
