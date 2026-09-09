Map<String, dynamic> preparationV2Payload({
  String id = 'plan-v2',
  String childId = 'child-1',
  String status = 'running',
  String stage = 'generating_content',
  int progressPercent = 8,
  int readyCourseCount = 0,
  int failedCourseCount = 0,
  int candidateCount = 3,
  int contentFailedCount = 0,
  List<int> subjectReady = const [0, 0, 0],
  List<int> subjectFailed = const [0, 0, 0],
  List<int>? subjectCandidates,
  List<int> subjectContentFailed = const [0, 0, 0],
  Object? retryAfterMs = 2500,
  Object? completedAt,
}) {
  final candidates = subjectCandidates ?? _partition(candidateCount);
  final canaryCandidates = candidateCount >= 3 ? 3 : candidateCount;
  const codes = ['chinese', 'math', 'english'];
  const labels = ['语文', '数学', '英语'];
  const totals = [12, 9, 9];
  return <String, dynamic>{
    'schemaVersion': 'mira.learning.preparation.v2',
    'id': id,
    'childId': childId,
    'gradeCode': 'primary_1',
    'gradeLabel': '一年级',
    'subjects': List.generate(3, (index) {
      return <String, dynamic>{
        'code': codes[index],
        'label': labels[index],
        'readyCourseCount': subjectReady[index],
        'failedCourseCount': subjectFailed[index],
        'totalCourseCount': totals[index],
        'contentCandidateCount': candidates[index],
        'contentFailedCount': subjectContentFailed[index],
      };
    }),
    'status': status,
    'stage': stage,
    'progressPercent': progressPercent,
    'totalCourseCount': 30,
    'readyCourseCount': readyCourseCount,
    'failedCourseCount': failedCourseCount,
    'attempt': 1,
    'canRetry': false,
    'retryAfterMs': retryAfterMs,
    'message': '正在准备课程',
    'lastProgressAt': 1787200000000,
    'updatedAt': 1787200000000,
    'completedAt': completedAt,
    'error': null,
    'contentProgress': <String, dynamic>{
      'candidateCount': candidateCount,
      'failedCount': contentFailedCount,
      'targetCount': 30,
      'canary': <String, dynamic>{
        'targetCount': 3,
        'candidateCount': canaryCandidates,
        'failedCount': 0,
        'passed': canaryCandidates == 3,
      },
    },
  };
}

List<({String name, Map<String, dynamic> payload})>
malformedPreparationV2Payloads({String childId = 'child-1'}) {
  final malformed = <({String name, Map<String, dynamic> payload})>[];

  void add(String name, void Function(Map<String, dynamic>) mutation) {
    final payload = preparationV2Payload(childId: childId);
    mutation(payload);
    malformed.add((name: name, payload: payload));
  }

  add(
    'missing contentProgress',
    (payload) => payload.remove('contentProgress'),
  );
  add('extra root key', (payload) => payload['extra'] = true);
  add('contentProgress non-object', (payload) {
    payload['contentProgress'] = const [];
  });
  add('missing content candidate', (payload) {
    _content(payload).remove('candidateCount');
  });
  add('extra content key', (payload) => _content(payload)['extra'] = true);
  add('missing canary passed', (payload) => _canary(payload).remove('passed'));
  add('extra canary key', (payload) => _canary(payload)['extra'] = true);
  add('canary non-object', (payload) {
    _content(payload)['canary'] = const [];
  });

  const invalidCounts = <Object?>[3.0, '3', true, null, -1];
  for (final field in ['candidateCount', 'failedCount', 'targetCount']) {
    for (final value in invalidCounts) {
      add('content $field ${value.runtimeType}', (payload) {
        _content(payload)[field] = value;
      });
    }
  }
  for (final field in ['candidateCount', 'failedCount', 'targetCount']) {
    for (final value in invalidCounts) {
      add('canary $field ${value.runtimeType}', (payload) {
        _canary(payload)[field] = value;
      });
    }
  }
  for (final value in <Object?>[1, 'true', null]) {
    add('canary passed ${value.runtimeType}', (payload) {
      _canary(payload)['passed'] = value;
    });
  }
  for (final field in ['contentCandidateCount', 'contentFailedCount']) {
    for (final value in <Object?>[1.0, '1', true, null, -1]) {
      add('subject $field ${value.runtimeType}', (payload) {
        _firstSubject(payload)[field] = value;
      });
    }
  }

  add('content target not 30', (payload) {
    _content(payload)['targetCount'] = 29;
  });
  add('content sum exceeds target', (payload) {
    _content(payload)['failedCount'] = 28;
  });
  add('canary target not 3', (payload) {
    _canary(payload)['targetCount'] = 2;
  });
  add('canary false despite passing counts', (payload) {
    _canary(payload)['passed'] = false;
  });
  add('canary true despite incomplete counts', (payload) {
    _canary(payload)['candidateCount'] = 2;
  });
  add('missing subject content candidate', (payload) {
    _firstSubject(payload).remove('contentCandidateCount');
  });
  add('missing subject content failed', (payload) {
    _firstSubject(payload).remove('contentFailedCount');
  });
  add('extra subject key', (payload) {
    _firstSubject(payload)['extra'] = true;
  });
  add('subject content exceeds total', (payload) {
    _firstSubject(payload)['contentCandidateCount'] = 13;
  });
  add('subject candidate sum below global', (payload) {
    _firstSubject(payload)['contentCandidateCount'] = 0;
  });
  add('root target differs from content target', (payload) {
    payload['totalCourseCount'] = 31;
  });
  add('subject total sum above root', (payload) {
    _firstSubject(payload)['totalCourseCount'] = 13;
  });
  add('subject total sum below root', (payload) {
    _firstSubject(payload)['totalCourseCount'] = 11;
  });
  add('subject failed sum differs from global', (payload) {
    _firstSubject(payload)['contentFailedCount'] = 1;
  });
  add('canary candidate exceeds global', (payload) {
    _content(payload)['candidateCount'] = 2;
    _firstSubject(payload)['contentCandidateCount'] = 0;
  });
  add('canary sum exceeds target', (payload) {
    _content(payload)['failedCount'] = 1;
    _firstSubject(payload)['contentFailedCount'] = 1;
    _canary(payload)['failedCount'] = 1;
  });
  add('canary failed exceeds global', (payload) {
    _canary(payload)
      ..['candidateCount'] = 2
      ..['failedCount'] = 1
      ..['passed'] = false;
  });
  add('subject local content sum exceeds total', (payload) {
    _content(payload)
      ..['candidateCount'] = 12
      ..['failedCount'] = 1;
    _firstSubject(payload)
      ..['contentCandidateCount'] = 12
      ..['contentFailedCount'] = 1;
    final subjects = payload['subjects'] as List;
    for (var index = 1; index < subjects.length; index += 1) {
      (subjects[index] as Map<String, dynamic>)['contentCandidateCount'] = 0;
    }
    _canary(payload)
      ..['candidateCount'] = 2
      ..['failedCount'] = 1
      ..['passed'] = false;
  });

  return malformed;
}

List<int> _partition(int candidateCount) {
  var remaining = candidateCount;
  final result = <int>[];
  for (final capacity in const [12, 9, 9]) {
    final value = remaining.clamp(0, capacity);
    result.add(value);
    remaining -= value;
  }
  return result;
}

Map<String, dynamic> _content(Map<String, dynamic> payload) =>
    payload['contentProgress'] as Map<String, dynamic>;

Map<String, dynamic> _canary(Map<String, dynamic> payload) =>
    _content(payload)['canary'] as Map<String, dynamic>;

Map<String, dynamic> _firstSubject(Map<String, dynamic> payload) =>
    (payload['subjects'] as List).first as Map<String, dynamic>;
