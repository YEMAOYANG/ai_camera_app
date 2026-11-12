// Lesson data for the approved platformHop v1 template.
K.ready({title:'积木跳跳台',sub:'听老师说要比什么，再按方向和跳跃。'});

const faceHopConfig = {
  "voiceLead": true,
  "stepVoiceLead": true,
  "art": {
    "backdrop": "__IMG:hop-workbench__",
    "sticker": "__IMG:hop-sticker__",
    "frames": [
      "__IMG:hop-rabbit-ready__",
      "__IMG:hop-rabbit-run__",
      "__IMG:hop-rabbit-jump__"
    ],
    "icons": {
      "l1-r1-wide-board": "__IMG:hop-wide-board__",
      "l1-r1-end-board": "__IMG:hop-end-board__",
      "l1-r2-end-brick": "__IMG:hop-end-brick__",
      "l1-r2-wide-brick": "__IMG:hop-wide-brick__",
      "l1-r3-wide-case": "__IMG:hop-wide-case__",
      "l1-r3-end-case": "__IMG:hop-end-case__",
      "l2-r1-edge-board": "__IMG:hop-edge-board__",
      "l2-r1-end-board": "__IMG:hop-end-board__",
      "l2-r1-wide-board": "__IMG:hop-wide-board__",
      "l2-r2-upright-cylinder": "__IMG:hop-upright-cylinder__",
      "l2-r2-side-cylinder": "__IMG:hop-side-cylinder__",
      "l2-r3-end-brick": "__IMG:hop-end-brick__",
      "l2-r3-wide-brick": "__IMG:hop-wide-brick__",
      "l2-r3-edge-brick": "__IMG:hop-edge-brick__",
      "l3-r1-edge-brick": "__IMG:hop-edge-brick__",
      "l3-r1-wide-brick": "__IMG:hop-wide-brick__",
      "l3-r1-end-brick": "__IMG:hop-end-brick__",
      "l3-r2-wide-board": "__IMG:hop-wide-board__",
      "l3-r2-edge-board": "__IMG:hop-edge-board__",
      "l3-r2-end-board": "__IMG:hop-end-board__",
      "l3-r3-side-cylinder": "__IMG:hop-side-cylinder__",
      "l3-r3-upright-cylinder": "__IMG:hop-upright-cylinder__",
      "l3-r4-wide-case": "__IMG:hop-wide-case__",
      "l3-r4-end-case": "__IMG:hop-end-case__"
    }
  },
  "doneText": "小兔选对了摆法，顺利到站！",
  "levels": [
    {
      "speed": 235,
      "platforms": [
        [
          578,
          550,
          124,
          "start"
        ],
        [
          502,
          475,
          124,
          "l1-r1-wide-board"
        ],
        [
          654,
          475,
          124,
          "l1-r1-end-board"
        ],
        [
          430,
          400,
          124,
          "l1-r2-end-brick"
        ],
        [
          574,
          400,
          124,
          "l1-r2-wide-brick"
        ],
        [
          502,
          325,
          124,
          "l1-r3-wide-case"
        ],
        [
          646,
          325,
          124,
          "l1-r3-end-case"
        ]
      ],
      "route": [
        "l1-r1-wide-board",
        "l1-r2-wide-brick",
        "l1-r3-wide-case"
      ],
      "prompt": null,
      "hints": [
        "先听清要比什么，再看积木下面和顶端。",
        "看一看贴着台子的面，或者用手比比高度。"
      ]
    },
    {
      "speed": 262,
      "platforms": [
        [
          595,
          550,
          90,
          "start"
        ],
        [
          471,
          475,
          90,
          "l2-r1-edge-board"
        ],
        [
          595,
          475,
          90,
          "l2-r1-end-board"
        ],
        [
          719,
          475,
          90,
          "l2-r1-wide-board"
        ],
        [
          621,
          400,
          90,
          "l2-r2-upright-cylinder"
        ],
        [
          817,
          400,
          90,
          "l2-r2-side-cylinder"
        ],
        [
          497,
          325,
          90,
          "l2-r3-end-brick"
        ],
        [
          621,
          325,
          90,
          "l2-r3-wide-brick"
        ],
        [
          745,
          325,
          90,
          "l2-r3-edge-brick"
        ]
      ],
      "route": [
        "l2-r1-wide-board",
        "l2-r2-upright-cylinder",
        "l2-r3-end-brick"
      ],
      "prompt": null,
      "hints": [
        "先听清要比什么，再看积木下面和顶端。",
        "看一看贴着台子的面，或者用手比比高度。"
      ]
    },
    {
      "speed": 298,
      "platforms": [
        [
          602,
          565,
          76,
          "start"
        ],
        [
          462,
          490,
          76,
          "l3-r1-edge-brick"
        ],
        [
          602,
          490,
          76,
          "l3-r1-wide-brick"
        ],
        [
          742,
          490,
          76,
          "l3-r1-end-brick"
        ],
        [
          462,
          415,
          76,
          "l3-r2-wide-board"
        ],
        [
          602,
          415,
          76,
          "l3-r2-edge-board"
        ],
        [
          742,
          415,
          76,
          "l3-r2-end-board"
        ],
        [
          617,
          340,
          76,
          "l3-r3-side-cylinder"
        ],
        [
          867,
          340,
          76,
          "l3-r3-upright-cylinder"
        ],
        [
          737,
          265,
          76,
          "l3-r4-wide-case"
        ],
        [
          997,
          265,
          76,
          "l3-r4-end-case"
        ]
      ],
      "route": [
        "l3-r1-wide-brick",
        "l3-r2-end-board",
        "l3-r3-upright-cylinder",
        "l3-r4-wide-case"
      ],
      "prompt": null,
      "hints": [
        "先听清要比什么，再看积木下面和顶端。",
        "看一看贴着台子的面，或者用手比比高度。"
      ]
    }
  ],
  "cues": [
    {
      "goal": "hop-contact",
      "steps": [
        "hop-contact",
        "hop-contact",
        "hop-contact"
      ],
      "hint": "hop-hint",
      "hint2": "hop-help",
      "praise": "hop-praise"
    },
    {
      "goal": "hop-contact",
      "steps": [
        "hop-contact",
        "hop-on-face",
        "hop-height"
      ],
      "hint": "hop-hint",
      "hint2": "hop-help",
      "praise": "hop-praise"
    },
    {
      "goal": "hop-contact",
      "steps": [
        "hop-contact",
        "hop-height",
        "hop-on-face",
        "hop-contact"
      ],
      "hint": "hop-hint",
      "hint2": "hop-help",
      "praise": "hop-praise"
    }
  ]
};

// The teacher points to the first landing even after the game advances its target.
const firstLevel = faceHopConfig.levels[0];
const [x, y, width] = firstLevel.platforms.find(platform => platform[3] === firstLevel.route[0]);
const demoAnchor = K.$('#face-hop-demo-wide');
K.stage().appendChild(demoAnchor);
Object.assign(demoAnchor.style, {
  left: x + 'px', top: (y - 9.5) + 'px', width: width + 'px', height: '45px',
});

K.game(K.gameTemplates.platformHop(faceHopConfig));
