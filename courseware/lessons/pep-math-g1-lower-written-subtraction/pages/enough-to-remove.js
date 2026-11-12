K.ready({
  title: '小蛇比散袋',
  sub: '听比较口令，转弯去找合适的一组。',
});

K.game(K.gameTemplates.compareSnake({
  art: {
    backdrop: '__IMG:supply-backdrop__',
    frames: ['__IMG:park-snake__'],
    sticker: '__IMG:feather-sticker__',
  },
  voiceLead: true,
  stepVoiceLead: true,
  doneText: '三种比较都试过啦！',
  cues: [
    {goal: 'pick-less', steps: ['pick-less', 'pick-less'], hint: 'count-again', hint2: 'compare-lit', praise: 'nice-compare'},
    {goal: 'pick-same', steps: ['pick-same', 'pick-same'], hint: 'count-again', hint2: 'compare-lit', praise: 'nice-compare'},
    {goal: 'pick-more', steps: ['pick-more', 'pick-more'], hint: 'count-again', hint2: 'compare-lit', praise: 'nice-compare'},
  ],
  levels: [
    {
      start: 6, seconds: .58, display: 'dots',
      rounds: [
        {relation: 'lt', foods: [[5, 4, 6], [7, 4, 4], [3, 3, 8]]},
        {relation: 'lt', foods: [[5, 3, 7], [7, 3, 2], [3, 4, 4]]},
      ],
    },
    {
      start: 5, seconds: .52, display: 'dots', walls: [[4, 3]],
      rounds: [
        {relation: 'eq', foods: [[5, 4, 3], [6, 2, 5], [8, 4, 7]]},
        {relation: 'eq', foods: [[2, 4, 6], [5, 3, 5], [7, 4, 4]]},
      ],
    },
    {
      start: 2, seconds: .52, display: 'dots', walls: [[4, 2], [7, 3]],
      rounds: [
        {relation: 'gt', foods: [[5, 4, 2], [6, 2, 6], [8, 4, 1]]},
        {relation: 'gt', foods: [[5, 4, 6], [7, 2, 8], [3, 4, 3]]},
      ],
    },
  ],
}));
