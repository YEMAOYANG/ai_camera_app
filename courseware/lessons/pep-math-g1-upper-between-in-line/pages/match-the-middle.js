K.ready({"title":"让点数配对落块","sub":"点数一样多，把两块放到一起。"});

K.game(K.gameTemplates.fallingTiles({
  "voiceLead": true,
  "art": {
    "backdrop": "__IMG:theatre-workroom__",
    "sticker": "__IMG:theatre-star__",
    "icons": {
      "int-2-6": "__IMG:int-2-6__",
      "int-7-12": "__IMG:int-7-12__",
      "int-14-17": "__IMG:int-14-17__",
      "int-3-7": "__IMG:int-3-7__",
      "int-9-14": "__IMG:int-9-14__",
      "int-6-8": "__IMG:int-6-8__",
      "int-9-13": "__IMG:int-9-13__",
      "int-16-17": "__IMG:int-16-17__",
      "int-1-5": "__IMG:int-1-5__",
      "count-0": "__IMG:count-0__",
      "count-1": "__IMG:count-1__",
      "count-2": "__IMG:count-2__",
      "count-3": "__IMG:count-3__",
      "count-4": "__IMG:count-4__",
      "tiles-rule": "__IMG:tiles-rule__"
    }
  },
  "doneText": "每张图都找到了同样多的点！",
  "cues": [
    {
      "goal": "tiles-goal",
      "hint": "tiles-hint",
      "hint2": "tiles-help",
      "praise": "tiles-praise"
    },
    {
      "goal": "tiles-goal",
      "hint": "tiles-hint",
      "hint2": "tiles-help",
      "praise": "tiles-praise"
    },
    {
      "goal": "tiles-goal",
      "hint": "tiles-hint",
      "hint2": "tiles-help",
      "praise": "tiles-praise"
    }
  ],
  "levels": [
    {
      "bottom": [
        "int-2-6",
        null,
        null,
        "int-7-12",
        null,
        "int-14-17"
      ],
      "pieces": [
        "count-3",
        "count-4",
        "count-2"
      ],
      "pairs": [
        [
          "count-3",
          "int-2-6"
        ],
        [
          "count-4",
          "int-7-12"
        ],
        [
          "count-2",
          "int-14-17"
        ]
      ],
      "interval": 1.36,
      "symbol": "tiles-rule",
      "hints": [
        "先找两面旗，只数夹在里面的点。",
        "点数相同，再把落块放到图块隔壁。"
      ]
    },
    {
      "bottom": [
        "int-3-7",
        null,
        "int-9-14",
        null,
        "int-6-8",
        null
      ],
      "pieces": [
        "count-4",
        "count-1",
        "count-3"
      ],
      "pairs": [
        [
          "count-3",
          "int-3-7"
        ],
        [
          "count-4",
          "int-9-14"
        ],
        [
          "count-1",
          "int-6-8"
        ]
      ],
      "interval": 1.09,
      "symbol": "tiles-rule",
      "hints": [
        "先找两面旗，只数夹在里面的点。",
        "点数相同，再把落块放到图块隔壁。"
      ]
    },
    {
      "bottom": [
        null,
        "int-9-13",
        null,
        "int-16-17",
        null,
        "int-1-5"
      ],
      "pieces": [
        "count-3",
        "count-0",
        "count-3"
      ],
      "pairs": [
        [
          "count-3",
          "int-9-13"
        ],
        [
          "count-0",
          "int-16-17"
        ],
        [
          "count-3",
          "int-1-5"
        ]
      ],
      "interval": 0.86,
      "symbol": "tiles-rule",
      "hints": [
        "先找两面旗，只数夹在里面的点。",
        "点数相同，再把落块放到图块隔壁。"
      ]
    }
  ]
}));
