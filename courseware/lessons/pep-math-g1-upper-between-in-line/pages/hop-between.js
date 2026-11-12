K.ready({"title":"跳过旗台，走中间","sub":"找到两面旗，按顺序跳到中间。"});

K.game(K.gameTemplates.platformHop({
  "voiceLead": true,
  "art": {
    "backdrop": "__IMG:theatre-lobby__",
    "sticker": "__IMG:theatre-star__",
    "frames": [
      "__IMG:usher-stand__",
      "__IMG:usher-run__",
      "__IMG:usher-hop__"
    ],
    "icons": {
      "flag-5": "__IMG:platform-flag-5__",
      "flag-8": "__IMG:platform-flag-8__",
      "flag-9": "__IMG:platform-flag-9__",
      "flag-12": "__IMG:platform-flag-12__",
      "flag-14": "__IMG:platform-flag-14__",
      "flag-18": "__IMG:platform-flag-18__",
      "hop-flags-5-9": "__IMG:hop-flags-5-9__",
      "hop-flags-8-14": "__IMG:hop-flags-8-14__",
      "hop-flags-12-18": "__IMG:hop-flags-12-18__",
      "theatre-star": "__IMG:theatre-star__"
    }
  },
  "doneText": "两旗中间的台子都到了！",
  "cues": [
    {
      "goal": "hop-goal",
      "hint": "hop-hint",
      "hint2": "hop-help",
      "praise": "hop-praise"
    },
    {
      "goal": "hop-goal",
      "hint": "hop-hint",
      "hint2": "hop-help",
      "praise": "hop-praise"
    },
    {
      "goal": "hop-goal",
      "hint": "hop-hint",
      "hint2": "hop-help",
      "praise": "hop-praise"
    }
  ],
  "levels": [
    {
      "speed": 265,
      "prompt": "hop-flags-5-9",
      "startLabel": "theatre-star",
      "route": [
        6,
        7,
        8
      ],
      "platforms": [
        [
          75,
          497,
          115,
          "start"
        ],
        [
          183,
          557,
          75,
          "flag-5"
        ],
        [
          250,
          495,
          104,
          6
        ],
        [
          410,
          465,
          94,
          7
        ],
        [
          565,
          488,
          105,
          8
        ],
        [
          733,
          490,
          82,
          "flag-9"
        ],
        [
          885,
          518,
          80,
          10
        ]
      ],
      "hints": [
        "两面旗只用来找位置，再试一跳。",
        "看亮起来的台子，它还在两旗之间。"
      ]
    },
    {
      "speed": 284,
      "prompt": "hop-flags-8-14",
      "startLabel": "theatre-star",
      "route": [
        9,
        10,
        11,
        12,
        13
      ],
      "platforms": [
        [
          65,
          495,
          105,
          "start"
        ],
        [
          148,
          365,
          72,
          7
        ],
        [
          176,
          560,
          72,
          "flag-8"
        ],
        [
          250,
          492,
          91,
          9
        ],
        [
          405,
          475,
          91,
          10
        ],
        [
          552,
          489,
          91,
          11
        ],
        [
          700,
          452,
          91,
          12
        ],
        [
          851,
          485,
          91,
          13
        ],
        [
          1002,
          513,
          80,
          "flag-14"
        ]
      ],
      "hints": [
        "两面旗只用来找位置，再试一跳。",
        "看亮起来的台子，它还在两旗之间。"
      ]
    },
    {
      "speed": 306,
      "prompt": "hop-flags-12-18",
      "startLabel": "theatre-star",
      "route": [
        13,
        14,
        15,
        16,
        17
      ],
      "platforms": [
        [
          70,
          502,
          108,
          "start"
        ],
        [
          192,
          555,
          72,
          "flag-12"
        ],
        [
          266,
          482,
          85,
          13
        ],
        [
          424,
          457,
          83,
          14
        ],
        [
          574,
          494,
          83,
          15
        ],
        [
          724,
          447,
          81,
          16
        ],
        [
          881,
          482,
          81,
          17
        ],
        [
          1025,
          514,
          76,
          "flag-18"
        ],
        [
          1154,
          532,
          73,
          19
        ]
      ],
      "hints": [
        "两面旗只用来找位置，再试一跳。",
        "看亮起来的台子，它还在两旗之间。"
      ]
    }
  ]
}));
