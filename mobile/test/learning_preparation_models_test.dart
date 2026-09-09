import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/features/learning/domain/learning_preparation_models.dart';

import 'support/learning_preparation_v2_fixtures.dart';

void main() {
  group('LearningPreparationCurrentState', () {
    test('parses the exact primary_1 normal envelope', () {
      final state = LearningPreparationCurrentState.fromJson({
        'ok': true,
        'preparation': _payload(),
      });

      expect(state.preparation?.gradeCode, 'primary_1');
      expect(state.learningPreparationAvailability, isNull);

      final empty = LearningPreparationCurrentState.fromJson({
        'ok': true,
        'preparation': null,
      });
      expect(empty.preparation, isNull);
      expect(empty.learningPreparationAvailability, isNull);
    });

    test(
      'preserves exact unavailable state for primary_2 through primary_6',
      () {
        for (var grade = 2; grade <= 6; grade += 1) {
          final gradeCode = 'primary_$grade';
          final state = LearningPreparationCurrentState.fromJson({
            'ok': true,
            'preparation': null,
            'learningPreparationAvailability': {
              'status': 'unavailable',
              'gradeCode': gradeCode,
              'message': '该年级正式课程尚未开放',
            },
          });

          expect(state.preparation, isNull, reason: gradeCode);
          expect(
            state.learningPreparationAvailability?.status,
            'unavailable',
            reason: gradeCode,
          );
          expect(
            state.learningPreparationAvailability?.gradeCode,
            gradeCode,
            reason: gradeCode,
          );
          expect(
            state.learningPreparationAvailability?.message,
            '该年级正式课程尚未开放',
            reason: gradeCode,
          );
        }
      },
    );

    test('rejects ambiguous or non-exact current envelope variants', () {
      final malformed = <Object?>[
        null,
        const <Object?>[],
        {'ok': true},
        {'ok': false, 'preparation': null},
        {'ok': true, 'preparation': null, 'extra': true},
        {'ok': true, 'preparation': _payload(gradeCode: 'primary_2')},
        {
          'ok': true,
          'preparation': _payload(),
          'learningPreparationAvailability': const {
            'status': 'unavailable',
            'gradeCode': 'primary_2',
            'message': '该年级正式课程尚未开放',
          },
        },
        {
          'ok': true,
          'preparation': null,
          'learningPreparationAvailability': null,
        },
        {
          'ok': true,
          'preparation': null,
          'learningPreparationAvailability': const {
            'status': 'preparing',
            'gradeCode': 'primary_2',
            'message': '已开始准备',
          },
        },
        for (final gradeCode in const [
          'primary_1',
          'primary_7',
          'kindergarten_middle',
        ])
          {
            'ok': true,
            'preparation': null,
            'learningPreparationAvailability': {
              'status': 'unavailable',
              'gradeCode': gradeCode,
              'message': '该年级正式课程尚未开放',
            },
          },
        for (final availability in const <Object?>[
          {'status': 'unavailable', 'gradeCode': 'primary_2'},
          {'status': 'unavailable', 'gradeCode': 'primary_2', 'message': ''},
          {'status': 'unavailable', 'gradeCode': 'primary_2', 'message': '   '},
          {
            'status': 'unavailable',
            'gradeCode': 'primary_2',
            'message': '该年级正式课程尚未开放',
            'extra': true,
          },
        ])
          {
            'ok': true,
            'preparation': null,
            'learningPreparationAvailability': availability,
          },
      ];

      for (final value in malformed) {
        expect(
          () => LearningPreparationCurrentState.fromJson(value),
          throwsA(isA<LearningPreparationFormatException>()),
          reason: value.toString(),
        );
      }
    });
  });

  test(
    'parses the exact running preparation contract without normalization',
    () {
      final value = LearningPreparation.fromJson(
        _payload(
          id: ' lcp_1 ',
          childId: ' child_1 ',
          gradeCode: ' primary_1 ',
          gradeLabel: ' 一年级 ',
          message: ' 正在生成老师讲解语音 ',
          stage: 'generating_speech',
          status: 'running',
          progressPercent: 40,
          readyCourseCount: 12,
          retryAfterMs: 2500,
          lastProgressAt: 1787199999000,
        ),
      );

      expect(value.id, ' lcp_1 ');
      expect(value.childId, ' child_1 ');
      expect(value.gradeCode, ' primary_1 ');
      expect(value.gradeLabel, ' 一年级 ');
      expect(value.message, ' 正在生成老师讲解语音 ');
      expect(value.stage, LearningPreparationStage.generatingSpeech);
      expect(value.supportedStage, isTrue);
      expect(value.totalCourseCount, 30);
      expect(value.subjects[1].label, '数学');
      expect(value.subjects[1].totalCourseCount, 9);
      expect(value.retryAfter, const Duration(milliseconds: 2500));
      expect(value.shouldPoll, isTrue);
    },
  );

  test('unknown stage keeps queued display provenance and never polls', () {
    final value = LearningPreparation.fromJson(
      _payload(stage: 'future_stage', status: 'running'),
    );

    expect(value.stage, LearningPreparationStage.queued);
    expect(value.supportedStage, isFalse);
    expect(value.shouldPoll, isFalse);
    expect(value.isReady, isFalse);
  });

  test('terminal statuses never poll and retry delay is bounded', () {
    for (final status in ['ready', 'failed', 'superseded', 'future_status']) {
      final value = LearningPreparation.fromJson(
        _payload(status: status, stage: 'completed', retryAfterMs: 2500),
      );
      expect(value.shouldPoll, isFalse, reason: status);
    }

    expect(
      LearningPreparation.fromJson(_payload(retryAfterMs: 1)).retryAfter,
      const Duration(seconds: 2),
    );
    expect(
      LearningPreparation.fromJson(_payload(retryAfterMs: 2500)).retryAfter,
      const Duration(milliseconds: 2500),
    );
    expect(
      LearningPreparation.fromJson(_payload(retryAfterMs: 60000)).retryAfter,
      const Duration(seconds: 30),
    );
    expect(
      LearningPreparation.fromJson(_payload(retryAfterMs: null)).retryAfter,
      const Duration(seconds: 30),
    );
  });

  test(
    'ready requires the exact v1 terminal state and consistent subjects',
    () {
      final ready = LearningPreparation.fromJson(
        _payload(
          status: 'ready',
          stage: 'completed',
          progressPercent: 100,
          readyCourseCount: 30,
          subjects: _subjects(),
          retryAfterMs: null,
          completedAt: 1787200001000,
        ),
      );
      expect(ready.isReady, isTrue);

      final notReadyCases = <Map<String, dynamic>>[
        _payload(
          status: 'running',
          stage: 'completed',
          progressPercent: 100,
          readyCourseCount: 30,
        ),
        _payload(
          status: 'ready',
          stage: 'future_stage',
          progressPercent: 100,
          readyCourseCount: 30,
        ),
        _payload(
          status: 'ready',
          stage: 'completed',
          progressPercent: 99,
          readyCourseCount: 30,
        ),
        _payload(
          status: 'ready',
          stage: 'completed',
          progressPercent: 100,
          readyCourseCount: 29,
        ),
        _payload(
          status: 'ready',
          stage: 'completed',
          progressPercent: 100,
          readyCourseCount: 29,
          failedCourseCount: 1,
        ),
        _payload(
          status: 'ready',
          stage: 'completed',
          progressPercent: 100,
          totalCourseCount: 0,
          readyCourseCount: 0,
          subjects: _subjects(totals: [0, 0, 0], ready: [0, 0, 0]),
        ),
        _payload(
          status: 'ready',
          stage: 'completed',
          progressPercent: 100,
          readyCourseCount: 30,
          subjects: _subjects(ready: [12, 9, 8]),
        ),
        _payload(
          status: 'ready',
          stage: 'completed',
          progressPercent: 100,
          readyCourseCount: 30,
          subjects: _subjects(codes: ['chinese', 'math', 'math']),
        ),
        _payload(
          status: 'ready',
          stage: 'completed',
          progressPercent: 100,
          readyCourseCount: 30,
          subjects: _subjects(codes: ['chinese', 'math', 'science']),
        ),
        _payload(
          status: 'ready',
          stage: 'completed',
          progressPercent: 100,
          readyCourseCount: 30,
          subjects: _subjects(totals: [12, 9, 8], ready: [12, 9, 8]),
        ),
      ];

      for (final payload in notReadyCases) {
        expect(
          LearningPreparation.fromJson(payload).isReady,
          isFalse,
          reason: payload.toString(),
        );
      }
    },
  );

  test('v1 remains exact and exposes unknown content progress', () {
    final value = LearningPreparation.fromJson(_payload());

    expect(value.schemaVersion, LearningPreparation.schema);
    expect(value.contentProgress, isNull);

    final extraContent = _payload()
      ..['contentProgress'] = _contentProgress(candidateCount: 3);
    expect(
      () => LearningPreparation.fromJson(extraContent),
      throwsA(isA<LearningPreparationFormatException>()),
    );
  });

  test('v2 parses exact partial and handoff content progress', () {
    final partial = LearningPreparation.fromJson(
      _v2Payload(
        stage: 'generating_content',
        progressPercent: 8,
        candidateCount: 3,
        subjectCandidates: const [1, 1, 1],
      ),
    );

    expect(partial.schemaVersion, LearningPreparation.schemaV2);
    expect(partial.contentProgress?.candidateCount, 3);
    expect(partial.contentProgress?.failedCount, 0);
    expect(partial.contentProgress?.targetCount, 30);
    expect(partial.contentProgress?.canary.targetCount, 3);
    expect(partial.contentProgress?.canary.candidateCount, 3);
    expect(partial.contentProgress?.canary.failedCount, 0);
    expect(partial.contentProgress?.canary.passed, isTrue);
    expect(partial.subjects.map((subject) => subject.contentCandidateCount), [
      1,
      1,
      1,
    ]);
    expect(partial.isReady, isFalse);

    final handoff = LearningPreparation.fromJson(
      _v2Payload(
        stage: 'building_classrooms',
        progressPercent: 35,
        candidateCount: 30,
        subjectCandidates: const [12, 9, 9],
      ),
    );

    expect(handoff.contentProgress?.candidateCount, 30);
    expect(handoff.progressPercent, 35);
    expect(handoff.readyCourseCount, 0);
    expect(handoff.isReady, isFalse);
  });

  test('v2 formal readiness requires v1 readiness and sealed content', () {
    final ready = LearningPreparation.fromJson(
      _v2Payload(
        status: 'ready',
        stage: 'completed',
        progressPercent: 100,
        readyCourseCount: 30,
        subjectReady: const [12, 9, 9],
        candidateCount: 30,
        subjectCandidates: const [12, 9, 9],
        retryAfterMs: null,
        completedAt: 1787200001000,
      ),
    );
    expect(ready.isReady, isTrue);

    final notReady = <Map<String, dynamic>>[
      _v2Payload(
        status: 'ready',
        stage: 'completed',
        progressPercent: 100,
        readyCourseCount: 30,
        subjectReady: const [12, 9, 9],
        candidateCount: 29,
        subjectCandidates: const [11, 9, 9],
        retryAfterMs: null,
        completedAt: 1787200001000,
      ),
      _v2Payload(
        status: 'ready',
        stage: 'completed',
        progressPercent: 100,
        readyCourseCount: 29,
        subjectReady: const [11, 9, 9],
        candidateCount: 30,
        subjectCandidates: const [12, 9, 9],
        retryAfterMs: null,
        completedAt: 1787200001000,
      ),
    ];

    for (final payload in notReady) {
      expect(LearningPreparation.fromJson(payload).isReady, isFalse);
    }
  });

  test('v2 rejects malformed content shapes and inconsistent counts', () {
    for (final malformed in malformedPreparationV2Payloads()) {
      expect(
        () => LearningPreparation.fromJson(malformed.payload),
        throwsA(isA<LearningPreparationFormatException>()),
        reason: malformed.name,
      );
    }
  });

  test('failed and retryability require failed completed provenance', () {
    final retryable = LearningPreparation.fromJson(
      _payload(
        status: 'failed',
        stage: 'completed',
        canRetry: true,
        retryAfterMs: null,
        error: const {
          'code': 'preparation_validation_failed',
          'message': '部分课程未通过系统校验，请重新准备',
        },
      ),
    );
    expect(retryable.isFailed, isTrue);
    expect(retryable.canRetry, isTrue);
    expect(retryable.error?.code, 'preparation_validation_failed');

    expect(
      () => LearningPreparation.fromJson(
        _payload(status: 'running', stage: 'planning', canRetry: true),
      ),
      throwsA(isA<LearningPreparationFormatException>()),
    );
    expect(
      () => LearningPreparation.fromJson(
        _payload(status: 'failed', stage: 'future_stage', canRetry: true),
      ),
      throwsA(isA<LearningPreparationFormatException>()),
    );
  });

  test(
    'strict parser rejects wrong scalar, count, progress and schema types',
    () {
      final malformed = <Map<String, dynamic>>[
        _payload(schemaVersion: 'mira.learning.preparation.v3'),
        _payload(id: 1),
        _payload(canRetry: 0),
        _payload(progressPercent: 40.0),
        _payload(progressPercent: true),
        _payload(progressPercent: -1),
        _payload(progressPercent: 101),
        _payload(totalCourseCount: '30'),
        _payload(totalCourseCount: 30.0),
        _payload(readyCourseCount: -1),
        _payload(failedCourseCount: 31),
        _payload(readyCourseCount: 25, failedCourseCount: 6),
        _payload(attempt: -1),
        _payload(updatedAt: '1787200000000'),
        _payload(retryAfterMs: 2500.0),
        _payload(lastProgressAt: false),
        _payload(completedAt: '1787200001000'),
        _payload(error: const {'code': 'x', 'message': 1}),
        _payload(subjects: 'not-a-list'),
        _payload(subjects: _subjects()..[0]['readyCourseCount'] = '12'),
        _payload(subjects: _subjects()..[0]['failedCourseCount'] = -1),
        _payload(
          subjects: _subjects()
            ..[0]['readyCourseCount'] = 10
            ..[0]['failedCourseCount'] = 3,
        ),
      ];

      for (final payload in malformed) {
        expect(
          () => LearningPreparation.fromJson(payload),
          throwsA(isA<LearningPreparationFormatException>()),
          reason: payload.toString(),
        );
      }
    },
  );

  test('authority fields reject empty strings without trimming values', () {
    for (final payload in [
      _payload(id: ''),
      _payload(childId: ''),
      _payload(gradeCode: ''),
      _payload(gradeLabel: ''),
    ]) {
      expect(
        () => LearningPreparation.fromJson(payload),
        throwsA(isA<LearningPreparationFormatException>()),
        reason: payload.toString(),
      );
    }

    final spaced = LearningPreparation.fromJson(
      _payload(
        id: ' lcp_1 ',
        childId: ' child_1 ',
        gradeCode: ' primary_1 ',
        gradeLabel: ' 一年级 ',
      ),
    );
    expect(spaced.id, ' lcp_1 ');
    expect(spaced.childId, ' child_1 ');
    expect(spaced.gradeCode, ' primary_1 ');
    expect(spaced.gradeLabel, ' 一年级 ');
  });

  test('strict parser rejects missing or extra root and nested keys', () {
    final missingRoot = _payload()..remove('message');
    final extraRoot = _payload()..['startedAt'] = 1787200000000;
    final missingSubject = _payload();
    (missingSubject['subjects'] as List).first.remove('label');
    final extraSubject = _payload();
    (extraSubject['subjects'] as List).first['extra'] = true;
    final extraError = _payload(
      error: const {'code': 'x', 'message': 'safe', 'detail': 'private'},
    );

    for (final payload in [
      missingRoot,
      extraRoot,
      missingSubject,
      extraSubject,
      extraError,
    ]) {
      expect(
        () => LearningPreparation.fromJson(payload),
        throwsA(isA<LearningPreparationFormatException>()),
      );
    }
  });

  test('subjects are immutable', () {
    final value = LearningPreparation.fromJson(_payload());

    expect(
      () => value.subjects.add(value.subjects.first),
      throwsUnsupportedError,
    );
  });
}

Map<String, dynamic> _v2Payload({
  String status = 'running',
  String stage = 'generating_content',
  int progressPercent = 5,
  int readyCourseCount = 0,
  int failedCourseCount = 0,
  int candidateCount = 0,
  int contentFailedCount = 0,
  List<int> subjectReady = const [0, 0, 0],
  List<int> subjectFailed = const [0, 0, 0],
  List<int> subjectCandidates = const [0, 0, 0],
  List<int> subjectContentFailed = const [0, 0, 0],
  Object? retryAfterMs = 2500,
  Object? completedAt,
}) {
  return preparationV2Payload(
    id: 'lcp_1',
    childId: 'child_1',
    status: status,
    stage: stage,
    progressPercent: progressPercent,
    readyCourseCount: readyCourseCount,
    failedCourseCount: failedCourseCount,
    candidateCount: candidateCount,
    contentFailedCount: contentFailedCount,
    subjectReady: subjectReady,
    subjectFailed: subjectFailed,
    subjectCandidates: subjectCandidates,
    subjectContentFailed: subjectContentFailed,
    retryAfterMs: retryAfterMs,
    completedAt: completedAt,
  );
}

Map<String, dynamic> _contentProgress({
  required int candidateCount,
  int failedCount = 0,
}) {
  return <String, dynamic>{
    'candidateCount': candidateCount,
    'failedCount': failedCount,
    'targetCount': 30,
    'canary': <String, dynamic>{
      'targetCount': 3,
      'candidateCount': candidateCount >= 3 ? 3 : candidateCount,
      'failedCount': 0,
      'passed': candidateCount >= 3,
    },
  };
}

Map<String, dynamic> _payload({
  Object? schemaVersion = 'mira.learning.preparation.v1',
  Object? id = 'lcp_1',
  Object? childId = 'child_1',
  Object? gradeCode = 'primary_1',
  Object? gradeLabel = '一年级',
  Object? subjects,
  Object? status = 'queued',
  Object? stage = 'queued',
  Object? progressPercent = 0,
  Object? totalCourseCount = 30,
  Object? readyCourseCount = 0,
  Object? failedCourseCount = 0,
  Object? attempt = 1,
  Object? canRetry = false,
  Object? retryAfterMs = 2500,
  Object? message = '正在准备课程',
  Object? lastProgressAt,
  Object? updatedAt = 1787200000000,
  Object? completedAt,
  Object? error,
}) {
  return <String, dynamic>{
    'schemaVersion': schemaVersion,
    'id': id,
    'childId': childId,
    'gradeCode': gradeCode,
    'gradeLabel': gradeLabel,
    'subjects': subjects ?? _subjects(ready: [0, 0, 0]),
    'status': status,
    'stage': stage,
    'progressPercent': progressPercent,
    'totalCourseCount': totalCourseCount,
    'readyCourseCount': readyCourseCount,
    'failedCourseCount': failedCourseCount,
    'attempt': attempt,
    'canRetry': canRetry,
    'retryAfterMs': retryAfterMs,
    'message': message,
    'lastProgressAt': lastProgressAt,
    'updatedAt': updatedAt,
    'completedAt': completedAt,
    'error': error,
  };
}

List<Map<String, dynamic>> _subjects({
  List<String> codes = const ['chinese', 'math', 'english'],
  List<int> totals = const [12, 9, 9],
  List<int> ready = const [12, 9, 9],
  List<int> failed = const [0, 0, 0],
}) {
  const labels = ['语文', '数学', '英语'];
  return List.generate(codes.length, (index) {
    return <String, dynamic>{
      'code': codes[index],
      'label': labels[index],
      'readyCourseCount': ready[index],
      'failedCourseCount': failed[index],
      'totalCourseCount': totals[index],
    };
  });
}
