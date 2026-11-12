const config = {
  "title": "图卡小蛇",
  "sub": "听这回的分法，带小蛇去找图卡伙伴。",
  "doneText": "你试过了按形状和按颜色分图卡。",
  "voiceLead": true,
  "art": {
    "backdrop": "__IMG:orchard-workbench__",
    "sticker": "__IMG:orchard-sticker__",
    "frames": [
      "__IMG:snake-head__",
      "__IMG:snake-body__",
      "__IMG:snake-tail__"
    ],
    "icons": {
      "round-apricot": "__IMG:round-apricot__",
      "round-sage": "__IMG:round-sage__",
      "round-sage-small": "__IMG:round-sage-small__",
      "square-apricot": "__IMG:square-apricot__",
      "square-sage": "__IMG:square-sage__",
      "triangle-apricot": "__IMG:triangle-apricot__",
      "triangle-sage": "__IMG:triangle-sage__",
      "triangle-apr-turn": "__IMG:triangle-apr-turn__",
      "rectangle-apricot": "__IMG:rectangle-apricot__"
    }
  },
  "levels": [
    {
      "start": "round-apricot",
      "seconds": 0.83,
      "groups": {
        "round-apricot": "round",
        "round-sage": "round",
        "round-sage-small": "round",
        "square-apricot": "square",
        "square-sage": "square",
        "triangle-apricot": "triangle",
        "triangle-sage": "triangle",
        "triangle-apr-turn": "triangle",
        "rectangle-apricot": "rectangle"
      },
      "walls": [],
      "rounds": [
        {
          "relation": "match",
          "foods": [
            [
              5,
              4,
              "round-sage"
            ],
            [
              7,
              4,
              "square-apricot"
            ]
          ]
        },
        {
          "relation": "match",
          "foods": [
            [
              5,
              2,
              "round-apricot"
            ],
            [
              7,
              3,
              "square-sage"
            ]
          ]
        }
      ],
      "hints": [
        "看右边图卡的外边是什么形状。",
        "按形状，找外边一样的卡。"
      ]
    },
    {
      "start": "square-sage",
      "seconds": 0.72,
      "groups": {
        "round-apricot": "apricot",
        "round-sage": "sage",
        "round-sage-small": "sage",
        "square-apricot": "apricot",
        "square-sage": "sage",
        "triangle-apricot": "apricot",
        "triangle-sage": "sage",
        "triangle-apr-turn": "apricot",
        "rectangle-apricot": "apricot"
      },
      "walls": [
        [
          3,
          3
        ],
        [
          7,
          2
        ]
      ],
      "rounds": [
        {
          "relation": "match",
          "foods": [
            [
              4,
              4,
              "triangle-sage"
            ],
            [
              6,
              4,
              "square-apricot"
            ]
          ]
        },
        {
          "relation": "match",
          "foods": [
            [
              3,
              2,
              "round-sage"
            ],
            [
              5,
              2,
              "triangle-apricot"
            ],
            [
              6,
              3,
              "round-apricot"
            ]
          ]
        },
        {
          "relation": "match",
          "foods": [
            [
              6,
              1,
              "square-sage"
            ],
            [
              8,
              2,
              "triangle-apr-turn"
            ]
          ]
        }
      ],
      "hints": [
        "听清了，这一回只看颜色。",
        "找和右边一样颜色的卡，形状可以不一样。"
      ]
    },
    {
      "start": "triangle-apricot",
      "seconds": 0.64,
      "groups": {
        "round-apricot": "round",
        "round-sage": "round",
        "round-sage-small": "round",
        "square-apricot": "square",
        "square-sage": "square",
        "triangle-apricot": "triangle",
        "triangle-sage": "triangle",
        "triangle-apr-turn": "triangle",
        "rectangle-apricot": "rectangle"
      },
      "walls": [
        [
          3,
          4
        ],
        [
          6,
          3
        ],
        [
          2,
          2
        ],
        [
          8,
          2
        ]
      ],
      "rounds": [
        {
          "relation": "match",
          "foods": [
            [
              6,
              4,
              "triangle-apr-turn"
            ],
            [
              4,
              4,
              "round-apricot"
            ]
          ]
        },
        {
          "relation": "match",
          "foods": [
            [
              7,
              3,
              "triangle-sage"
            ],
            [
              5,
              2,
              "square-sage"
            ],
            [
              8,
              4,
              "rectangle-apricot"
            ]
          ]
        },
        {
          "relation": "match",
          "foods": [
            [
              6,
              1,
              "triangle-apricot"
            ],
            [
              4,
              3,
              "round-sage-small"
            ],
            [
              7,
              1,
              "rectangle-apricot"
            ]
          ]
        },
        {
          "relation": "match",
          "foods": [
            [
              4,
              1,
              "triangle-apr-turn"
            ],
            [
              5,
              2,
              "round-sage"
            ],
            [
              6,
              2,
              "square-apricot"
            ]
          ]
        }
      ],
      "hints": [
        "转了方向，也可以是同一种形状。",
        "看看有几条边、几个角，再找伙伴。"
      ]
    }
  ],
  "cues": [
    {
      "goal": "snake-shape",
      "hint": "snake-look",
      "hint2": "snake-hint",
      "praise": "snake-praise"
    },
    {
      "goal": "snake-color",
      "hint": "snake-look",
      "hint2": "snake-color",
      "praise": "snake-praise"
    },
    {
      "goal": "snake-shape-again",
      "hint": "snake-reset",
      "hint2": "snake-shape-again",
      "praise": "snake-praise"
    }
  ]
};
K.ready({title: config.title, sub: config.sub});
K.game(K.gameTemplates.compareSnake(config));
