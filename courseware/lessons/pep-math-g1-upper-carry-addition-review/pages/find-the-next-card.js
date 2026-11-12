K.ready({"title": "泡泡车按序找卡", "sub": "按听到的规则找下一张，找齐再去旗子。"});

K.game(K.gameTemplates.bubbleMaze({
  "art": {
    "backdrop": "__IMG:lantern-stage__",
    "sticker": "__IMG:lantern-sticker__",
    "frames": [
      "__IMG:lantern-rover__",
      "__IMG:lantern-rover-pop__"
    ],
    "icons": {
      "A": "__IMG:card-8-3__",
      "B": "__IMG:card-8-4__",
      "D": "__IMG:card-8-5__",
      "F": "__IMG:card-5-7__",
      "G": "__IMG:card-6-7__",
      "H": "__IMG:card-7-7__",
      "J": "__IMG:card-9-7__",
      "K": "__IMG:card-8-8__",
      "L": "__IMG:card-7-9__"
    }
  },
  "voiceLead": true,
  "doneText": "算式路线连起来啦！",
  "levels": [
    {
      "map": [
        "#########",
        "#S.A+..E#",
        "#..##...#",
        "#B....D.#",
        "#########"
      ],
      "route": [
        "A",
        "B",
        "D"
      ],
      "step": 0.33,
      "listenOnly": true,
      "patrols": [],
      "hints": [
        "先想刚才说的顺序，再选下一张。",
        "亮起的是下一站。先看数，再走。"
      ]
    },
    {
      "map": [
        "############",
        "#S.F+.....E#",
        "#..#..###..#",
        "#.G...H....#",
        "#..........#",
        "############"
      ],
      "route": [
        "F",
        "G",
        "H"
      ],
      "step": 0.27,
      "listenOnly": true,
      "patrols": [
        {
          "y": 4,
          "from": 3,
          "to": 8,
          "speed": 1.12
        }
      ],
      "hints": [
        "先想刚才说的顺序，再选下一张。",
        "亮起的是下一站。先看数，再走。"
      ]
    },
    {
      "map": [
        "#############",
        "#S..J+.....E#",
        "#.##.#####.##",
        "#..K..L.....#",
        "###.##.##.#.#",
        "#...........#",
        "#############"
      ],
      "route": [
        "J",
        "K",
        "L"
      ],
      "step": 0.22,
      "listenOnly": true,
      "patrols": [
        {
          "y": 1,
          "from": 6,
          "to": 10,
          "speed": 1.6
        }
      ],
      "hints": [
        "先想刚才说的顺序，再选下一张。",
        "亮起的是下一站。先看数，再走。"
      ]
    }
  ],
  "cues": [
    {
      "goal": "maze-left-eight",
      "hint": "maze-hint",
      "hint2": "maze-help",
      "praise": "maze-good"
    },
    {
      "goal": "maze-right-seven",
      "hint": "maze-hint",
      "hint2": "maze-help",
      "praise": "maze-good"
    },
    {
      "goal": "maze-row-sixteen",
      "hint": "maze-hint",
      "hint2": "maze-help",
      "praise": "maze-good"
    }
  ]
}));
