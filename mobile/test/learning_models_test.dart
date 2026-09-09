import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/features/learning/domain/learning_models.dart';

void main() {
  test('parses two daily subject items and stable choice ids', () {
    final day = LearningToday.fromJson({
      'state': 'scheduled',
      'recommendation': {
        'courseId': 'math-1',
        'subject': 'math',
        'title': '数学课',
      },
      'task': {'id': 'task-main', 'status': 'scheduled'},
      'items': [
        {
          'slot': 'core',
          'state': 'scheduled',
          'recommendation': {
            'courseId': 'math-1',
            'subject': 'math',
            'subjectLabel': '数学',
            'title': '数学课',
          },
          'task': {'id': 'task-main', 'status': 'scheduled'},
        },
        {
          'slot': 'rotation',
          'state': 'scheduled',
          'recommendation': {
            'courseId': 'english-1',
            'subject': 'english',
            'subjectLabel': '英语',
            'title': '英语课',
          },
          'task': {'id': 'task-rotation', 'status': 'scheduled'},
        },
      ],
    });
    final question = LearningQuestion.fromJson({
      'id': 'q-choice',
      'type': 'single_choice',
      'inputMode': 'choice',
      'prompt': '选择正确答案',
      'choices': [
        {'id': 'a', 'label': 'A'},
        {'id': 'b', 'label': 'B'},
      ],
    });

    expect(day.items, hasLength(2));
    expect(day.items.first.slot, 'core');
    expect(day.items.last.slot, 'rotation');
    expect(day.items.last.lesson?.subjectCode, 'english');
    expect(question.isSingleChoice, isTrue);
    expect(question.choices.map((choice) => choice.id), ['a', 'b']);
  });

  test('parses stable preparing slots without a lesson payload', () {
    final day = LearningToday.fromJson({
      'state': 'scheduled',
      'items': [
        {
          'slot': 'core',
          'state': 'recommended',
          'recommendation': {'courseId': 'chinese-1', 'title': '识字课'},
        },
        {
          'slot': 'rotation',
          'state': 'preparing',
          'message': '数学课程正在发布。',
          'lesson': null,
          'task': null,
        },
      ],
    });

    expect(day.items, hasLength(2));
    expect(day.items.last.state, LearningTodayState.preparing);
    expect(day.items.last.lesson, isNull);
    expect(day.items.last.message, '数学课程正在发布。');
  });

  test('parses exact today recommendation contract', () {
    final today = LearningToday.fromJson({
      'ok': true,
      'date': '2026-08-12',
      'childId': 'child-1',
      'recommendation': {
        'courseId': 'course-3-math-1',
        'courseVersion': 2,
        'gradeCode': 'primary_3',
        'subject': 'math',
        'nodeCode': 'addition.carry',
        'title': '三位数加法',
        'objective': '理解并正确完成连续进位',
        'estimatedMinutes': 12,
        'questionCount': 4,
        'intro': '从位值开始理解进位。',
      },
      'task': null,
      'session': null,
      'latestReport': null,
    });

    expect(today.state, LearningTodayState.recommended);
    expect(today.lesson?.id, 'course-3-math-1');
    expect(today.lesson?.title, '三位数加法');
    expect(today.lesson?.skill, '理解并正确完成连续进位');
    expect(today.lesson?.estimatedMinutes, 12);
    expect(today.lesson?.questionCount, 4);
    expect(today.lesson?.introduction, '从位值开始理解进位。');
  });

  test('parses teaching flow from session with guided and independent ids', () {
    final session = LearningSession.fromJson({
      'id': 'session-pinyin',
      'taskId': 'task-pinyin',
      'status': 'in_progress',
      'currentQuestionIndex': 0,
      'totalQuestions': 5,
      'correctCount': 0,
      'hintCount': 0,
      'currentQuestion': {'id': 'q-guided-1', 'prompt': 'b 和 a 拼成什么？'},
      'teachingFlow': {
        'teach': {
          'title': '声母在前，韵母在后',
          'sayText': '先读声母，再读韵母，把它们连起来。',
          'keyPoints': ['先看声母', '再看韵母'],
        },
        'workedExample': {
          'prompt': 'b 和 a 怎样拼？',
          'type': 'single_choice',
          'choices': [
            {'id': 'A', 'label': 'ba'},
            {'id': 'B', 'label': 'ab'},
          ],
          'answerDisplayText': 'ba',
          'explanation': '声母 b 在前，韵母 a 在后。',
        },
        'guidedQuestionIds': ['q-guided-1', 'q-guided-2'],
        'independentQuestionIds': ['q-practice-1', 'q-practice-2'],
        'recap': '声母在前、韵母在后，连起来读成音节。',
      },
    });

    final flow = session.teachingFlow;
    expect(flow, isNotNull);
    expect(flow?.teach.title, '声母在前，韵母在后');
    expect(flow?.teach.keyPoints, ['先看声母', '再看韵母']);
    expect(flow?.workedExample.choices.first.label, 'ba');
    expect(flow?.workedExample.answerText, 'ba');
    expect(flow?.isGuidedQuestion('q-guided-1'), isTrue);
    expect(flow?.isIndependentQuestion('q-practice-2'), isTrue);
    expect(flow?.recap, '声母在前、韵母在后，连起来读成音节。');
  });

  test('keeps legacy sessions without teaching flow compatible', () {
    final session = LearningSession.fromJson({
      'id': 'legacy-session',
      'taskId': 'legacy-task',
      'status': 'in_progress',
      'currentQuestionIndex': 0,
      'totalQuestions': 1,
      'currentQuestion': {'id': 'q-1', 'prompt': '1 + 1 = ?'},
    });

    expect(session.teachingFlow, isNull);
    expect(session.currentQuestion?.prompt, '1 + 1 = ?');
  });

  test('rejects a teaching flow whose teach step only has a title', () {
    final session = LearningSession.fromJson({
      'id': 'malformed-session',
      'taskId': 'task-1',
      'status': 'in_progress',
      'currentQuestion': {'id': 'q-1', 'prompt': '1 + 1 = ?'},
      'teachingFlow': {
        'teach': {'title': '只有标题', 'sayText': '', 'keyPoints': []},
        'workedExample': {'prompt': '1 + 1 = ?', 'answerDisplayText': '2'},
      },
    });

    expect(session.teachingFlow, isNull);
    expect(session.currentQuestion?.prompt, '1 + 1 = ?');
  });

  test('infers in-progress session and never needs an answer in question', () {
    final today = LearningToday.fromJson({
      'recommendation': {
        'courseId': 'course-1',
        'title': '口算巩固',
        'objective': '准确口算',
      },
      'task': {'id': 'task-1', 'status': 'in_progress'},
      'session': {
        'id': 'session-1',
        'taskId': 'task-1',
        'status': 'in_progress',
        'currentQuestionIndex': 1,
        'totalQuestions': 3,
        'correctCount': 1,
        'attemptedCount': 1,
        'currentQuestion': {
          'id': 'q-2',
          'index': 1,
          'type': 'oral',
          'prompt': '36 + 27 等于多少？',
          'choices': ['53', '63', '73'],
          'skill': '两位数进位加法',
          'attemptNumber': 1,
        },
      },
    });

    expect(today.state, LearningTodayState.inProgress);
    expect(today.session?.currentIndex, 1);
    expect(today.session?.currentQuestion?.prompt, '36 + 27 等于多少？');
    expect(today.session?.currentQuestion?.options, ['53', '63', '73']);
  });

  test('parses exact answer result and completed report contract', () {
    final result = LearningAnswerResult.fromJson({
      'ok': true,
      'correct': true,
      'feedback': '回答正确。',
      'hint': '',
      'nextQuestion': null,
      'completed': true,
      'session': {
        'id': 'session-1',
        'taskId': 'task-1',
        'status': 'completed',
        'currentQuestionIndex': 4,
        'totalQuestions': 4,
        'correctCount': 3,
        'attemptedCount': 4,
        'currentQuestion': null,
      },
      'report': {
        'id': 'report-1',
        'childId': 'child-1',
        'taskId': 'task-1',
        'score': 75,
        'correctCount': 3,
        'totalQuestions': 4,
        'masteryLevel': 'developing',
        'summary': '连续进位还需要一次复习。',
        'strengths': ['位值理解正确'],
        'nextStep': '明天复习同能力点。',
      },
    });

    expect(result.evaluation.isCorrect, isTrue);
    expect(result.session.isCompleted, isTrue);
    expect(result.report?.masteryLabel, 'developing');
    expect(result.report?.masteryDisplayLabel, '巩固中');
    expect(result.report?.summary, '连续进位还需要一次复习。');
    expect(result.report?.nextSuggestion, '明天复习同能力点。');
  });
}
