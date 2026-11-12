K.ready({"title": "水面上的彩球口令", "sub": "听清数量和颜色，用泡泡接到那组图。"});

K.game(K.gameTemplates.wordBubbles({
  "art": {
    "backdrop": "__IMG:pond-background__",
    "sticker": "__IMG:ball-sticker__",
    "frames": [
      "__IMG:boat__",
      "__IMG:boat-pop__"
    ],
    "icons": {
      "b2p2": "__IMG:group-b2p2__",
      "b3u3": "__IMG:group-b3u3__",
      "b4u2": "__IMG:group-b4u2__",
      "b5p2": "__IMG:group-b5p2__",
      "p1b2": "__IMG:group-p1b2__",
      "p2b1": "__IMG:group-p2b1__",
      "p2b2": "__IMG:group-p2b2__",
      "p3b1": "__IMG:group-p3b1__",
      "p4b1": "__IMG:group-p4b1__",
      "p4b2": "__IMG:group-p4b2__",
      "p4u2": "__IMG:group-p4u2__",
      "p5b1": "__IMG:group-p5b1__",
      "p5b2": "__IMG:group-p5b2__",
      "p6b1": "__IMG:group-p6b1__",
      "u2p2": "__IMG:group-u2p2__",
      "u3b1": "__IMG:group-u3b1__",
      "u3p2": "__IMG:group-u3p2__",
      "u4p1": "__IMG:group-u4p1__",
      "u4p3": "__IMG:group-u4p3__",
      "u5b1": "__IMG:group-u5b1__",
      "u5p2": "__IMG:group-u5p2__",
      "u6b1": "__IMG:group-u6b1__"
    }
  },
  "doneText": "彩球都接住啦！",
  "voiceLead": true,
  "stepVoiceLead": true,
  "cues": [
    {
      "steps": [
        "two-pink",
        "two-brown"
      ],
      "goal": "two-pink",
      "hint": "bubble-hint",
      "hint2": "bubble-help",
      "praise": "bubble-praise"
    },
    {
      "steps": [
        "three-pink",
        "four-blue",
        "two-brown"
      ],
      "goal": "three-pink",
      "hint": "bubble-hint",
      "hint2": "bubble-help",
      "praise": "bubble-praise"
    },
    {
      "steps": [
        "five-pink",
        "four-brown",
        "five-blue",
        "six-pink"
      ],
      "goal": "five-pink",
      "hint": "bubble-hint",
      "hint2": "bubble-help",
      "praise": "bubble-praise"
    }
  ],
  "levels": [
    {
      "rounds": [
        {
          "target": "p2b1",
          "cards": [
            "p2b1",
            "p1b2"
          ]
        },
        {
          "target": "p1b2",
          "cards": [
            "p2b1",
            "p1b2"
          ]
        }
      ],
      "drift": 0,
      "pace": 0.55,
      "tolerance": 61,
      "hints": [
        "先听颜色，再数这一色的球。",
        "朝亮起来的那张图吹泡泡。"
      ]
    },
    {
      "rounds": [
        {
          "target": "p3b1",
          "cards": [
            "p2b2",
            "p3b1",
            "u3b1"
          ]
        },
        {
          "target": "u4p1",
          "cards": [
            "u3p2",
            "p4b1",
            "u4p1"
          ]
        },
        {
          "target": "b2p2",
          "cards": [
            "b2p2",
            "p3b1",
            "u2p2"
          ]
        }
      ],
      "drift": 16,
      "pace": 0.75,
      "tolerance": 56,
      "hints": [
        "先听颜色，再数这一色的球。",
        "朝亮起来的那张图吹泡泡。"
      ]
    },
    {
      "rounds": [
        {
          "target": "p5b1",
          "cards": [
            "p4b2",
            "p5b1",
            "u5b1"
          ]
        },
        {
          "target": "b4u2",
          "cards": [
            "b3u3",
            "p4u2",
            "b4u2"
          ]
        },
        {
          "target": "u5p2",
          "cards": [
            "u5p2",
            "u4p3",
            "b5p2"
          ]
        },
        {
          "target": "p6b1",
          "cards": [
            "p5b2",
            "p6b1",
            "u6b1"
          ]
        }
      ],
      "drift": 29,
      "pace": 1.0,
      "tolerance": 51,
      "hints": [
        "先听颜色，再数这一色的球。",
        "朝亮起来的那张图吹泡泡。"
      ]
    }
  ]
}));
