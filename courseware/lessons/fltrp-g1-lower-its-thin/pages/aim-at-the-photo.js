K.ready({   "title": "弹珠照相台",   "sub": "听一句，对准符合描述的照片。" });

K.game(K.gameTemplates.magnetMarbles({
  "art": {
    "backdrop": "__IMG:farm-photo-stage__",
    "sticker": "__IMG:farm-camera-sticker__",
    "frames": [
      "__IMG:farm-lens-ball__"
    ],
    "icons": {
      "thin": "__IMG:farm-shape-thin__",
      "fat": "__IMG:farm-shape-fat__",
      "big": "__IMG:farm-one-big__",
      "little": "__IMG:farm-one-little__",
      "two-little": "__IMG:farm-two-little__",
      "two-big": "__IMG:farm-two-big__"
    }
  },
  "voiceLead": true,
  "stepVoiceLead": true,
  "cues": [
    {
      "goal": "one-thin",
      "steps": [
        "one-thin",
        "one-fat"
      ],
      "hint": "aim-hint",
      "hint2": "aim-help",
      "praise": "aim-good"
    },
    {
      "goal": "one-big",
      "steps": [
        "one-big",
        "many-little",
        "one-little"
      ],
      "hint": "aim-hint",
      "hint2": "aim-help",
      "praise": "aim-good"
    },
    {
      "goal": "many-big",
      "steps": [
        "many-big",
        "one-big",
        "one-little",
        "many-little"
      ],
      "hint": "aim-hint",
      "hint2": "aim-help",
      "praise": "aim-good"
    }
  ],
  "levels": [
    {
      "targets": [
        {
          "x": 405,
          "value": "thin"
        },
        {
          "x": 640,
          "value": "fat"
        }
      ],
      "queue": [
        "one-thin",
        "one-fat"
      ],
      "pairs": [
        [
          "one-thin",
          "thin"
        ],
        [
          "one-fat",
          "fat"
        ]
      ],
      "speed": 405,
      "drift": 5,
      "targetWidth": 174,
      "targetHeight": 121,
      "listenOnly": true,
      "hints": [
        "先重听，听清是在说哪张图。",
        "看看提示的轮廓和大小，再慢慢瞄准。"
      ]
    },
    {
      "targets": [
        {
          "x": 419,
          "value": "big"
        },
        {
          "x": 640,
          "value": "little"
        },
        {
          "x": 860,
          "value": "two-little"
        }
      ],
      "queue": [
        "one-big",
        "many-little",
        "one-little"
      ],
      "pairs": [
        [
          "one-big",
          "big"
        ],
        [
          "many-little",
          "two-little"
        ],
        [
          "one-little",
          "little"
        ]
      ],
      "speed": 480,
      "drift": 14,
      "targetWidth": 153,
      "targetHeight": 111,
      "listenOnly": true,
      "hints": [
        "先重听，听清是在说哪张图。",
        "看看提示的轮廓和大小，再慢慢瞄准。"
      ]
    },
    {
      "targets": [
        {
          "x": 372,
          "value": "little"
        },
        {
          "x": 551,
          "value": "two-big"
        },
        {
          "x": 729,
          "value": "two-little"
        },
        {
          "x": 907,
          "value": "big"
        }
      ],
      "queue": [
        "many-big",
        "one-big",
        "one-little",
        "many-little"
      ],
      "pairs": [
        [
          "many-big",
          "two-big"
        ],
        [
          "one-big",
          "big"
        ],
        [
          "one-little",
          "little"
        ],
        [
          "many-little",
          "two-little"
        ]
      ],
      "speed": 544,
      "drift": 18,
      "targetWidth": 147,
      "targetHeight": 104,
      "listenOnly": true,
      "hints": [
        "先重听，听清是在说哪张图。",
        "看看提示的轮廓和大小，再慢慢瞄准。"
      ]
    }
  ],
  "doneText": "照片都拍好啦！"
}));
