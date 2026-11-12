K.ready({"title": "听情境，瞄准可能的心情", "sub": "先听事情和动作，再选图发射。"});

K.game(K.gameTemplates.magnetMarbles({
  "art": {
    "backdrop": "__IMG:garden8-stage__",
    "sticker": "__IMG:garden8-sticker__",
    "frames": [
      "__IMG:garden8-launch-ball__"
    ],
    "icons": {
      "happy": "__IMG:garden8-mood-happy__",
      "sad": "__IMG:garden8-mood-sad__",
      "angry": "__IMG:garden8-mood-angry__",
      "scared": "__IMG:garden8-mood-scared__"
    }
  },
  "voiceLead": true,
  "stepVoiceLead": true,
  "doneText": "找到了情境里的心情！",
  "cues": [
    {
      "goal": "hear-happy-a",
      "steps": [
        "hear-happy-a",
        "hear-sad-a"
      ],
      "hint": "mood-hint",
      "hint2": "mood-help",
      "praise": "mood-good"
    },
    {
      "goal": "hear-angry-a",
      "steps": [
        "hear-angry-a",
        "hear-scared-a",
        "hear-happy-b"
      ],
      "hint": "mood-hint",
      "hint2": "mood-help",
      "praise": "mood-good"
    },
    {
      "goal": "hear-angry-b",
      "steps": [
        "hear-angry-b",
        "hear-scared-b",
        "hear-sad-b",
        "hear-happy-a"
      ],
      "hint": "mood-hint",
      "hint2": "mood-help",
      "praise": "mood-good"
    }
  ],
  "levels": [
    {
      "targets": [
        {
          "x": 412,
          "value": "happy"
        },
        {
          "x": 640,
          "value": "sad"
        }
      ],
      "queue": [
        "hear-happy-a",
        "hear-sad-a"
      ],
      "pairs": [
        [
          "hear-happy-a",
          "happy"
        ],
        [
          "hear-sad-a",
          "sad"
        ]
      ],
      "listenOnly": true,
      "targetWidth": 200,
      "targetHeight": 126,
      "speed": 414,
      "drift": 5,
      "hints": [
        "想一想先发生什么，再想她做了什么。",
        "重听后看亮起的图，再慢慢瞄准。"
      ]
    },
    {
      "targets": [
        {
          "x": 390,
          "value": "happy"
        },
        {
          "x": 640,
          "value": "angry"
        },
        {
          "x": 890,
          "value": "scared"
        }
      ],
      "queue": [
        "hear-angry-a",
        "hear-scared-a",
        "hear-happy-b"
      ],
      "pairs": [
        [
          "hear-angry-a",
          "angry"
        ],
        [
          "hear-scared-a",
          "scared"
        ],
        [
          "hear-happy-b",
          "happy"
        ]
      ],
      "listenOnly": true,
      "targetWidth": 194,
      "targetHeight": 126,
      "speed": 469,
      "drift": 10,
      "hints": [
        "想一想先发生什么，再想她做了什么。",
        "重听后看亮起的图，再慢慢瞄准。"
      ]
    },
    {
      "targets": [
        {
          "x": 325,
          "value": "scared"
        },
        {
          "x": 535,
          "value": "sad"
        },
        {
          "x": 745,
          "value": "angry"
        },
        {
          "x": 955,
          "value": "happy"
        }
      ],
      "queue": [
        "hear-angry-b",
        "hear-scared-b",
        "hear-sad-b",
        "hear-happy-a"
      ],
      "pairs": [
        [
          "hear-angry-b",
          "angry"
        ],
        [
          "hear-scared-b",
          "scared"
        ],
        [
          "hear-sad-b",
          "sad"
        ],
        [
          "hear-happy-a",
          "happy"
        ]
      ],
      "listenOnly": true,
      "targetWidth": 184,
      "targetHeight": 126,
      "speed": 530,
      "drift": 13,
      "hints": [
        "想一想先发生什么，再想她做了什么。",
        "重听后看亮起的图，再慢慢瞄准。"
      ]
    }
  ]
}));
