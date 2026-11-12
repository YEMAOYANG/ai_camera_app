const config = {
  "title": "把问题送去找办法",
  "sub": "按箭头推卡片，选能找到线索的托盘。",
  "doneText": "每张问题卡都找到了能帮忙的方法。",
  "voiceLead": true,
  "art": {
    "backdrop": "__IMG:science-workbench__",
    "sticker": "__IMG:depot-rover__",
    "frames": [
      "__IMG:depot-rover__"
    ],
    "icons": {
      "ask-look": "__IMG:ask-look__",
      "use-look": "__IMG:use-look__",
      "ask-measure": "__IMG:ask-measure__",
      "use-measure": "__IMG:use-measure__",
      "ask-test": "__IMG:ask-test__",
      "use-test": "__IMG:use-test__",
      "ask-make": "__IMG:ask-make__",
      "use-make": "__IMG:use-make__",
      "ask-lookup": "__IMG:ask-lookup__",
      "use-lookup": "__IMG:use-lookup__"
    }
  },
  "levels": [
    {
      "map": [
        "########",
        "#......#",
        "#.S....#",
        "#......#",
        "########"
      ],
      "step": 0.3,
      "items": [
        {
          "x": 3,
          "y": 2,
          "token": "ask-look",
          "group": "look"
        },
        {
          "x": 3,
          "y": 3,
          "token": "ask-measure",
          "group": "measure"
        }
      ],
      "docks": [
        {
          "x": 5,
          "y": 2,
          "sample": "use-look",
          "group": "look"
        },
        {
          "x": 5,
          "y": 3,
          "sample": "use-measure",
          "group": "measure"
        }
      ],
      "hints": [
        "先想你这张图要找什么。",
        "找细花纹用放大镜；差多少用尺。"
      ]
    },
    {
      "map": [
        "#########",
        "#.......#",
        "#..#....#",
        "#.S.....#",
        "#.......#",
        "#########"
      ],
      "step": 0.25,
      "items": [
        {
          "x": 4,
          "y": 2,
          "token": "ask-make",
          "group": "make"
        },
        {
          "x": 4,
          "y": 4,
          "token": "ask-lookup",
          "group": "lookup"
        },
        {
          "x": 3,
          "y": 3,
          "token": "ask-test",
          "group": "test"
        }
      ],
      "docks": [
        {
          "x": 6,
          "y": 2,
          "sample": "use-make",
          "group": "make"
        },
        {
          "x": 6,
          "y": 3,
          "sample": "use-test",
          "group": "test"
        },
        {
          "x": 7,
          "y": 4,
          "sample": "use-lookup",
          "group": "lookup"
        }
      ],
      "hints": [
        "先想你这张图要找什么。",
        "试一试、做一个、翻图册，帮的忙不一样。"
      ]
    },
    {
      "map": [
        "##########",
        "#........#",
        "#..#.....#",
        "#.S......#",
        "#....#...#",
        "#........#",
        "##########"
      ],
      "step": 0.21,
      "items": [
        {
          "x": 4,
          "y": 3,
          "token": "ask-look",
          "group": "look"
        },
        {
          "x": 7,
          "y": 4,
          "token": "ask-test",
          "group": "test"
        },
        {
          "x": 5,
          "y": 2,
          "token": "ask-measure",
          "group": "measure"
        },
        {
          "x": 4,
          "y": 5,
          "token": "ask-lookup",
          "group": "lookup"
        }
      ],
      "docks": [
        {
          "x": 8,
          "y": 4,
          "sample": "use-test",
          "group": "test"
        },
        {
          "x": 5,
          "y": 1,
          "sample": "use-look",
          "group": "look"
        },
        {
          "x": 8,
          "y": 2,
          "sample": "use-measure",
          "group": "measure"
        },
        {
          "x": 7,
          "y": 5,
          "sample": "use-lookup",
          "group": "lookup"
        }
      ],
      "hints": [
        "先想你这张图要找什么。",
        "看懂图上的问题，再挑能找出线索的托盘。"
      ]
    }
  ],
  "cues": [
    {
      "goal": "depot-goal-one",
      "hint": "depot-hint",
      "hint2": "depot-goal-one",
      "praise": "depot-praise"
    },
    {
      "goal": "depot-goal-two",
      "hint": "depot-hint",
      "hint2": "depot-goal-two",
      "praise": "depot-praise"
    },
    {
      "goal": "depot-goal-three",
      "hint": "depot-hint",
      "hint2": "depot-goal-three",
      "praise": "depot-praise"
    }
  ]
};
K.ready({title:config.title,sub:config.sub});
K.stage().append(K.$('#science-depot-demo-item'), K.$('#science-depot-demo-dock'));
K.game(K.gameTemplates.sortingDepot(config));
