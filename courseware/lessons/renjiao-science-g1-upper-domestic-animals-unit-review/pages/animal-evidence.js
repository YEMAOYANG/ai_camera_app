const config = {
  "title": "把同类线索配起来",
  "sub": "发射弹珠，配出不同动物的同一类生活线索。",
  "doneText": "进食、运动、生长和有下一代，都找到同类线索了。",
  "voiceLead": true,
  "stepVoiceLead": true,
  "art": {
    "backdrop": "__IMG:animal-workbench__",
    "sticker": "__IMG:animal-sticker__",
    "frames": [
      "__IMG:evidence-marble__"
    ],
    "icons": {
      "goldfish-swims": "__IMG:goldfish-swims__",
      "rabbit-hops": "__IMG:rabbit-hops__",
      "rabbit-eats": "__IMG:rabbit-eats__",
      "hen-eats": "__IMG:hen-eats__",
      "chick-grows": "__IMG:chick-grows__",
      "dog-grows": "__IMG:dog-grows__",
      "hen-offspring": "__IMG:hen-offspring__",
      "cat-offspring": "__IMG:cat-offspring__"
    }
  },
  "levels": [
    {
      "targetWidth": 172,
      "targetHeight": 120,
      "speed": 420,
      "drift": 0,
      "queue": [
        "goldfish-swims",
        "rabbit-eats"
      ],
      "targets": [
        {
          "x": 397,
          "value": "hen-eats"
        },
        {
          "x": 640,
          "value": "rabbit-hops"
        },
        {
          "x": 886,
          "value": "hen-offspring"
        }
      ],
      "pairs": [
        [
          "goldfish-swims",
          "rabbit-hops"
        ],
        [
          "rabbit-eats",
          "hen-eats"
        ]
      ],
      "hints": [
        "先看弹珠上的动物图想一想。",
        "想想哪幅图做的是同一类事。"
      ]
    },
    {
      "targetWidth": 157,
      "targetHeight": 115,
      "speed": 475,
      "drift": 10,
      "queue": [
        "hen-eats",
        "rabbit-hops",
        "chick-grows"
      ],
      "targets": [
        {
          "x": 356,
          "value": "rabbit-eats"
        },
        {
          "x": 544,
          "value": "cat-offspring"
        },
        {
          "x": 734,
          "value": "dog-grows"
        },
        {
          "x": 925,
          "value": "goldfish-swims"
        }
      ],
      "pairs": [
        [
          "hen-eats",
          "rabbit-eats"
        ],
        [
          "rabbit-hops",
          "goldfish-swims"
        ],
        [
          "chick-grows",
          "dog-grows"
        ]
      ],
      "hints": [
        "先看弹珠上的动物图想一想。",
        "想想哪幅图做的是同一类事。"
      ]
    },
    {
      "targetWidth": 146,
      "targetHeight": 110,
      "speed": 524,
      "drift": 18,
      "queue": [
        "hen-offspring",
        "dog-grows",
        "goldfish-swims",
        "rabbit-eats"
      ],
      "targets": [
        {
          "x": 352,
          "value": "hen-eats"
        },
        {
          "x": 546,
          "value": "chick-grows"
        },
        {
          "x": 736,
          "value": "cat-offspring"
        },
        {
          "x": 926,
          "value": "rabbit-hops"
        }
      ],
      "pairs": [
        [
          "hen-offspring",
          "cat-offspring"
        ],
        [
          "dog-grows",
          "chick-grows"
        ],
        [
          "goldfish-swims",
          "rabbit-hops"
        ],
        [
          "rabbit-eats",
          "hen-eats"
        ]
      ],
      "hints": [
        "先看弹珠上的动物图想一想。",
        "想想哪幅图做的是同一类事。"
      ]
    }
  ],
  "cues": [
    {
      "goal": "evidence-hint",
      "hint": "evidence-hint",
      "hint2": "evidence-hint",
      "praise": "evidence-praise",
      "steps": [
        "evidence-move",
        "evidence-eat"
      ]
    },
    {
      "goal": "evidence-hint",
      "hint": "evidence-hint",
      "hint2": "evidence-hint",
      "praise": "evidence-praise",
      "steps": [
        "evidence-eat",
        "evidence-move",
        "evidence-grow"
      ]
    },
    {
      "goal": "evidence-hint",
      "hint": "evidence-hint",
      "hint2": "evidence-hint",
      "praise": "evidence-praise",
      "steps": [
        "evidence-next",
        "evidence-grow",
        "evidence-move",
        "evidence-eat"
      ]
    }
  ]
};
K.ready({title: config.title, sub: config.sub});
K.game(K.gameTemplates.magnetMarbles(config));
