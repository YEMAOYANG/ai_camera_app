K.ready({"title": "云梯按数序跳", "sub": "听方向，从现在的数往下一块跳。"});

K.game(K.gameTemplates.platformHop({
  "art": {
    "backdrop": "__IMG:clouds__",
    "sticker": "__IMG:sticker__",
    "frames": [
      "__IMG:rabbit-ready__",
      "__IMG:rabbit-run__",
      "__IMG:rabbit-jump__"
    ]
  },
  "voiceLead": true,
  "cues": [
    {
      "goal": "route-up",
      "hint": "route-hint",
      "hint2": "route-help",
      "praise": "route-good"
    },
    {
      "goal": "route-down",
      "hint": "route-hint",
      "hint2": "route-help",
      "praise": "route-good"
    },
    {
      "goal": "route-long",
      "hint": "route-hint",
      "hint2": "route-help",
      "praise": "route-good"
    }
  ],
  "doneText": "云梯顺序都走对啦！",
  "levels": [
    {
      "speed": 280,
      "startLabel": 6,
      "prompt": "↗",
      "route": [
        7,
        8,
        9
      ],
      "platforms": [
        [
          70,
          479,
          135,
          "start"
        ],
        [
          175,
          365,
          78,
          10
        ],
        [
          258,
          479,
          112,
          7
        ],
        [
          440,
          468,
          114,
          8
        ],
        [
          620,
          480,
          110,
          9
        ],
        [
          810,
          458,
          112,
          5
        ]
      ],
      "hints": [
        "脚踩空了。回到刚才那块，再想下一个数。",
        "看看亮起的落脚处。认准数字，再按跳跃。"
      ]
    },
    {
      "speed": 295,
      "startLabel": 10,
      "prompt": "↘",
      "route": [
        9,
        8,
        7,
        6
      ],
      "platforms": [
        [
          76,
          490,
          126,
          "start"
        ],
        [
          260,
          464,
          99,
          9
        ],
        [
          437,
          497,
          97,
          8
        ],
        [
          508,
          369,
          74,
          3
        ],
        [
          612,
          470,
          96,
          7
        ],
        [
          792,
          500,
          94,
          6
        ],
        [
          989,
          456,
          97,
          5
        ]
      ],
      "hints": [
        "脚踩空了。回到刚才那块，再想下一个数。",
        "看看亮起的落脚处。认准数字，再按跳跃。"
      ]
    },
    {
      "speed": 318,
      "startLabel": 5,
      "prompt": "↗",
      "route": [
        6,
        7,
        8,
        9,
        10
      ],
      "platforms": [
        [
          75,
          500,
          128,
          "start"
        ],
        [
          266,
          457,
          90,
          6
        ],
        [
          438,
          501,
          89,
          7
        ],
        [
          507,
          379,
          76,
          4
        ],
        [
          608,
          441,
          90,
          8
        ],
        [
          796,
          485,
          86,
          9
        ],
        [
          999,
          424,
          88,
          10
        ],
        [
          1097,
          540,
          78,
          3
        ]
      ],
      "hints": [
        "脚踩空了。回到刚才那块，再想下一个数。",
        "看看亮起的落脚处。认准数字，再按跳跃。"
      ]
    }
  ]
}));
