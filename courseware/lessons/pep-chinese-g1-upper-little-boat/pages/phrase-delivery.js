K.ready({"title": "听清样子，邮车送对包裹", "sub": "近处拿，远处送。每一步听完再开车。"});

K.game(K.gameTemplates.listenDelivery({
  "voiceLead": true,
  "stepVoiceLead": true,
  "art": {
    "backdrop": "__IMG:delivery-backdrop__",
    "frames": [
      "__IMG:delivery-cart__",
      "__IMG:delivery-cart-load__",
      "__IMG:delivery-glider__"
    ],
    "icons": {
      "parcel-yellow-leaf": "__IMG:parcel-yellow-leaf__",
      "parcel-green-leaf": "__IMG:parcel-green-leaf__",
      "parcel-red-scarf": "__IMG:parcel-red-scarf__",
      "parcel-blue-scarf": "__IMG:parcel-blue-scarf__",
      "parcel-blue-cap": "__IMG:parcel-blue-cap__",
      "recipient-rabbit": "__IMG:recipient-rabbit__",
      "recipient-turtle": "__IMG:recipient-turtle__",
      "recipient-cat": "__IMG:recipient-cat__"
    },
    "sticker": "__IMG:boat-reward__"
  },
  "doneText": "每份东西都送对了！",
  "cues": [
    {
      "goal": "take-yellow",
      "hint": "parcel-hint",
      "hint2": "parcel-help",
      "praise": "parcel-praise",
      "steps": [
        "take-yellow",
        "give-rabbit"
      ]
    },
    {
      "goal": "take-red",
      "hint": "parcel-hint",
      "hint2": "parcel-help",
      "praise": "parcel-praise",
      "steps": [
        "take-red",
        "give-turtle",
        "take-yellow",
        "give-cat"
      ]
    },
    {
      "goal": "take-blue",
      "hint": "parcel-hint",
      "hint2": "parcel-help",
      "praise": "parcel-praise",
      "steps": [
        "take-blue",
        "give-cat",
        "take-cap",
        "give-turtle",
        "take-red",
        "give-rabbit"
      ]
    }
  ],
  "levels": [
    {
      "pickup": [
        [
          "parcel-yellow-leaf",
          5
        ],
        [
          "parcel-green-leaf",
          2
        ]
      ],
      "drop": [
        [
          "recipient-rabbit",
          5
        ],
        [
          "recipient-turtle",
          2
        ]
      ],
      "orders": [
        [
          "parcel-yellow-leaf",
          "recipient-rabbit"
        ]
      ],
      "lanes": [
        {
          "row": 2,
          "speed": 0.88,
          "spacing": 5.7,
          "phase": 0
        }
      ],
      "step": 0.34,
      "hints": [
        "重听一遍，听清样子和名字。",
        "看亮起来的地方，再慢慢靠近。"
      ],
      "labels": {
        "parcel-yellow-leaf": "黄叶",
        "parcel-green-leaf": "绿叶",
        "parcel-red-scarf": "红围巾",
        "parcel-blue-scarf": "蓝围巾",
        "parcel-blue-cap": "蓝圆帽",
        "recipient-rabbit": "小兔",
        "recipient-turtle": "乌龟",
        "recipient-cat": "小猫"
      }
    },
    {
      "pickup": [
        [
          "parcel-red-scarf",
          2
        ],
        [
          "parcel-blue-scarf",
          6
        ],
        [
          "parcel-yellow-leaf",
          8
        ]
      ],
      "drop": [
        [
          "recipient-turtle",
          1
        ],
        [
          "recipient-cat",
          5
        ],
        [
          "recipient-rabbit",
          7
        ]
      ],
      "orders": [
        [
          "parcel-red-scarf",
          "recipient-turtle"
        ],
        [
          "parcel-yellow-leaf",
          "recipient-cat"
        ]
      ],
      "lanes": [
        {
          "row": 1,
          "speed": -1.25,
          "spacing": 4.6,
          "phase": 2
        },
        {
          "row": 3,
          "speed": 1.36,
          "spacing": 4.6,
          "phase": 1
        }
      ],
      "step": 0.28,
      "hints": [
        "重听一遍，听清样子和名字。",
        "看亮起来的地方，再慢慢靠近。"
      ],
      "labels": {
        "parcel-yellow-leaf": "黄叶",
        "parcel-green-leaf": "绿叶",
        "parcel-red-scarf": "红围巾",
        "parcel-blue-scarf": "蓝围巾",
        "parcel-blue-cap": "蓝圆帽",
        "recipient-rabbit": "小兔",
        "recipient-turtle": "乌龟",
        "recipient-cat": "小猫"
      }
    },
    {
      "pickup": [
        [
          "parcel-blue-scarf",
          1
        ],
        [
          "parcel-blue-cap",
          4
        ],
        [
          "parcel-red-scarf",
          7
        ]
      ],
      "drop": [
        [
          "recipient-cat",
          6
        ],
        [
          "recipient-turtle",
          2
        ],
        [
          "recipient-rabbit",
          4
        ]
      ],
      "orders": [
        [
          "parcel-blue-scarf",
          "recipient-cat"
        ],
        [
          "parcel-blue-cap",
          "recipient-turtle"
        ],
        [
          "parcel-red-scarf",
          "recipient-rabbit"
        ]
      ],
      "lanes": [
        {
          "row": 1,
          "speed": -1.8,
          "spacing": 3.9,
          "phase": 0.7
        },
        {
          "row": 2,
          "speed": 1.65,
          "spacing": 4,
          "phase": 2.2
        },
        {
          "row": 3,
          "speed": -1.6,
          "spacing": 3.9,
          "phase": 1.4
        }
      ],
      "step": 0.22,
      "hints": [
        "重听一遍，听清样子和名字。",
        "看亮起来的地方，再慢慢靠近。"
      ],
      "labels": {
        "parcel-yellow-leaf": "黄叶",
        "parcel-green-leaf": "绿叶",
        "parcel-red-scarf": "红围巾",
        "parcel-blue-scarf": "蓝围巾",
        "parcel-blue-cap": "蓝圆帽",
        "recipient-rabbit": "小兔",
        "recipient-turtle": "乌龟",
        "recipient-cat": "小猫"
      }
    }
  ]
}));
