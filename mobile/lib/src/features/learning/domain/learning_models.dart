enum LearningTodayState {
  unavailable,
  preparing,
  recommended,
  scheduled,
  inProgress,
  completed;

  static LearningTodayState fromValue(String value) {
    return switch (value.trim().toLowerCase()) {
      'preparing' => preparing,
      'recommended' || 'recommendation' || 'ready' => recommended,
      'scheduled' || 'assigned' || 'pending' => scheduled,
      'in_progress' || 'inprogress' || 'active' || 'started' => inProgress,
      'completed' || 'finished' => completed,
      _ => unavailable,
    };
  }
}

class LearningToday {
  const LearningToday({
    required this.state,
    this.slot = 'core',
    this.lesson,
    this.task,
    this.session,
    this.report,
    this.items = const [],
    this.message = '',
    this.preparationError = '',
  });

  final LearningTodayState state;
  final String slot;
  final LearningLesson? lesson;
  final LearningTask? task;
  final LearningSession? session;
  final LearningReport? report;
  final List<LearningToday> items;
  final String message;
  final String preparationError;

  bool get needsPreparationRetry =>
      state == LearningTodayState.recommended && preparationError.isNotEmpty;

  LearningToday withPreparationError(String value) {
    return LearningToday(
      state: state,
      slot: slot,
      lesson: lesson,
      task: task,
      session: session,
      report: report,
      items: items,
      message: message,
      preparationError: value,
    );
  }

  factory LearningToday.fromJson(Map<String, dynamic> json) {
    final root = _unwrapMap(json, const ['today']);
    final rawItems = root['items'];
    final items = rawItems is List
        ? rawItems
              .map(learningResponseMap)
              .where((item) => item.isNotEmpty)
              .map(LearningToday._fromSingleJson)
              .toList(growable: false)
        : const <LearningToday>[];
    final single = LearningToday._fromSingleJson(root);
    if (items.isEmpty) return single;
    return LearningToday(
      state: single.state,
      slot: single.slot,
      lesson: single.lesson,
      task: single.task,
      session: single.session,
      report: single.report,
      items: items,
      message: single.message,
    );
  }

  factory LearningToday._fromSingleJson(Map<String, dynamic> root) {
    final lessonMap = _firstMap(root, const ['lesson', 'recommendation']);
    final taskMap = _firstMap(root, const ['task', 'assignment']);
    final sessionMap = _firstMap(root, const ['session']);
    final reportMap = _firstMap(root, const [
      'latestReport',
      'report',
      'latest_report',
    ]);
    final lesson = lessonMap == null
        ? null
        : LearningLesson.fromJson(lessonMap);
    final task = taskMap == null ? null : LearningTask.fromJson(taskMap);
    final session = sessionMap == null
        ? null
        : LearningSession.fromJson(sessionMap);
    final report = reportMap == null
        ? null
        : LearningReport.fromJson(reportMap);

    var state = LearningTodayState.fromValue(
      _string(root['state'], fallback: _string(root['status'])),
    );
    if (state == LearningTodayState.unavailable) {
      if (report != null ||
          session?.isCompleted == true ||
          task?.isCompleted == true) {
        state = LearningTodayState.completed;
      } else if (session != null && session.isActive) {
        state = LearningTodayState.inProgress;
      } else if (task != null) {
        state = LearningTodayState.scheduled;
      } else if (lesson != null) {
        state = LearningTodayState.recommended;
      }
    }

    return LearningToday(
      state: state,
      slot: _string(root['slot'], fallback: 'core'),
      lesson: lesson ?? task?.lesson,
      task: task,
      session: session,
      report: report,
      message: _string(root['message'], fallback: _string(root['reason'])),
    );
  }
}

class LearningLesson {
  const LearningLesson({
    required this.id,
    required this.title,
    required this.subject,
    required this.skill,
    required this.gradeLabel,
    required this.estimatedMinutes,
    required this.questionCount,
    required this.introduction,
    this.subjectCode = '',
    this.sessionKind = 'lesson',
    this.outcomeMode = 'scored_deterministic',
    this.teachingFlow,
  });

  final String id;
  final String title;
  final String subject;
  final String skill;
  final String gradeLabel;
  final int estimatedMinutes;
  final int questionCount;
  final String introduction;
  final String subjectCode;
  final String sessionKind;
  final String outcomeMode;
  final LearningTeachingFlow? teachingFlow;

  bool get isScored => outcomeMode == 'scored_deterministic';

  factory LearningLesson.fromJson(Map<String, dynamic> json) {
    final skillMap = _mapOrNull(json['skill']);
    return LearningLesson(
      id: _string(
        json['id'],
        fallback: _string(
          json['lessonId'],
          fallback: _string(json['courseId']),
        ),
      ),
      title: _string(json['title'], fallback: _string(json['name'])),
      subject: _string(
        json['subjectLabel'],
        fallback: _string(json['subject']),
      ),
      subjectCode: _string(json['subject']),
      skill: _string(
        json['skillTitle'],
        fallback: _string(
          json['knowledgePoint'],
          fallback: _string(
            skillMap?['title'],
            fallback: _string(
              json['skill'],
              fallback: _string(json['objective']),
            ),
          ),
        ),
      ),
      gradeLabel: _string(json['gradeLabel'], fallback: _string(json['grade'])),
      estimatedMinutes: _integer(
        json['estimatedMinutes'],
        fallback: _integer(json['durationMinutes']),
      ),
      questionCount: _integer(
        json['questionCount'],
        fallback: _listLength(json['questions']),
      ),
      introduction: _string(
        json['introduction'],
        fallback: _string(json['intro'], fallback: _string(json['summary'])),
      ),
      sessionKind: _string(json['sessionKind'], fallback: 'lesson'),
      outcomeMode: _string(
        json['outcomeMode'],
        fallback: 'scored_deterministic',
      ),
      teachingFlow: _teachingFlowOrNull(json['teachingFlow']),
    );
  }
}

class LearningTeachingFlow {
  const LearningTeachingFlow({
    required this.teach,
    required this.workedExample,
    required this.recap,
    this.guidedQuestionIds = const [],
    this.independentQuestionIds = const [],
  });

  final LearningTeachStep teach;
  final LearningWorkedExample workedExample;
  final String recap;
  final List<String> guidedQuestionIds;
  final List<String> independentQuestionIds;

  bool get isRunnable => teach.hasContent && workedExample.hasContent;

  bool isGuidedQuestion(String questionId) =>
      guidedQuestionIds.contains(questionId);

  bool isIndependentQuestion(String questionId) =>
      independentQuestionIds.contains(questionId);

  factory LearningTeachingFlow.fromJson(Map<String, dynamic> json) {
    final teach = _mapOrNull(json['teach']) ?? const <String, dynamic>{};
    final workedExample =
        _mapOrNull(json['workedExample']) ??
        _mapOrNull(json['example']) ??
        const <String, dynamic>{};
    final recapValue = json['recap'];
    final recapMap = _mapOrNull(recapValue);
    return LearningTeachingFlow(
      teach: LearningTeachStep.fromJson(teach),
      workedExample: LearningWorkedExample.fromJson(workedExample),
      recap: recapMap == null
          ? _string(recapValue)
          : _string(
              recapMap['sayText'],
              fallback: _string(
                recapMap['displayText'],
                fallback: _string(recapMap['text']),
              ),
            ),
      guidedQuestionIds: _idList(
        json['guidedQuestionIds'] ??
            json['interactionQuestionIds'] ??
            json['guidedQuestions'],
      ),
      independentQuestionIds: _idList(
        json['independentQuestionIds'] ??
            json['practiceQuestionIds'] ??
            json['independentQuestions'],
      ),
    );
  }
}

class LearningTeachStep {
  const LearningTeachStep({
    required this.title,
    required this.sayText,
    this.keyPoints = const [],
  });

  final String title;
  final String sayText;
  final List<String> keyPoints;

  bool get hasContent => sayText.isNotEmpty || keyPoints.isNotEmpty;

  factory LearningTeachStep.fromJson(Map<String, dynamic> json) {
    return LearningTeachStep(
      title: _string(json['title']),
      sayText: _string(
        json['sayText'],
        fallback: _string(json['displayText'], fallback: _string(json['text'])),
      ),
      keyPoints: _stringList(json['keyPoints']),
    );
  }
}

class LearningWorkedExample {
  const LearningWorkedExample({
    required this.prompt,
    required this.type,
    required this.answerText,
    required this.explanation,
    this.choices = const [],
  });

  final String prompt;
  final String type;
  final List<LearningChoice> choices;
  final String answerText;
  final String explanation;

  bool get hasContent => prompt.isNotEmpty && answerText.isNotEmpty;

  factory LearningWorkedExample.fromJson(Map<String, dynamic> json) {
    return LearningWorkedExample(
      prompt: _string(
        json['prompt'],
        fallback: _string(json['question'], fallback: _string(json['stem'])),
      ),
      type: _string(json['type'], fallback: 'exact_text'),
      choices: _choiceList(json['choices'] ?? json['options']),
      answerText: _string(
        json['answerDisplayText'],
        fallback: _string(
          json['answerText'],
          fallback: _string(json['answer']),
        ),
      ),
      explanation: _string(json['explanation']),
    );
  }
}

class LearningTask {
  const LearningTask({
    required this.id,
    required this.status,
    required this.scheduledStart,
    this.lesson,
  });

  final String id;
  final String status;
  final String scheduledStart;
  final LearningLesson? lesson;

  bool get isCompleted =>
      status == 'completed' || status == 'finished' || status == 'confirmed';

  factory LearningTask.fromJson(Map<String, dynamic> json) {
    final lessonMap = _firstMap(json, const ['lesson']);
    return LearningTask(
      id: _string(json['id'], fallback: _string(json['taskId'])),
      status: _string(json['status']).toLowerCase(),
      scheduledStart: _string(
        json['scheduledStart'],
        fallback: _string(json['startAt']),
      ),
      lesson: lessonMap == null ? null : LearningLesson.fromJson(lessonMap),
    );
  }
}

class LearningQuestion {
  const LearningQuestion({
    required this.id,
    required this.prompt,
    required this.options,
    this.type = 'numeric',
    this.inputMode = 'number',
    this.choices = const [],
  });

  final String id;
  final String prompt;
  final List<String> options;
  final String type;
  final String inputMode;
  final List<LearningChoice> choices;

  bool get isSingleChoice => type == 'single_choice';
  bool get isSequence => type == 'sequence';
  bool get usesNumericKeyboard => type == 'numeric' || inputMode == 'number';

  factory LearningQuestion.fromJson(Map<String, dynamic> json) {
    return LearningQuestion(
      id: _string(json['id'], fallback: _string(json['questionId'])),
      prompt: _string(
        json['prompt'],
        fallback: _string(json['question'], fallback: _string(json['stem'])),
      ),
      options: _stringList(json['options'] ?? json['choices']),
      type: _string(json['type'], fallback: 'numeric'),
      inputMode: _string(json['inputMode'], fallback: 'text'),
      choices: _choiceList(json['choices'] ?? json['options']),
    );
  }
}

class LearningChoice {
  const LearningChoice({required this.id, required this.label});

  final String id;
  final String label;
}

class LearningStructuredResponse {
  const LearningStructuredResponse._({
    required this.kind,
    this.optionId,
    this.items = const [],
  });

  factory LearningStructuredResponse.singleChoice(String optionId) {
    return LearningStructuredResponse._(
      kind: 'single_choice',
      optionId: optionId,
    );
  }

  factory LearningStructuredResponse.sequence(List<String> items) {
    return LearningStructuredResponse._(
      kind: 'sequence',
      items: List.unmodifiable(items),
    );
  }

  final String kind;
  final String? optionId;
  final List<String> items;

  Map<String, dynamic> toJson() => {
    'kind': kind,
    if (optionId != null) 'optionId': optionId,
    if (items.isNotEmpty) 'items': items,
  };
}

class LearningSession {
  const LearningSession({
    required this.id,
    required this.taskId,
    required this.status,
    required this.currentIndex,
    required this.totalQuestions,
    required this.correctCount,
    required this.hintCount,
    this.currentQuestion,
    this.teachingFlow,
  });

  final String id;
  final String taskId;
  final String status;
  final int currentIndex;
  final int totalQuestions;
  final int correctCount;
  final int hintCount;
  final LearningQuestion? currentQuestion;
  final LearningTeachingFlow? teachingFlow;

  bool get isCompleted => status == 'completed' || status == 'finished';
  bool get isActive => !isCompleted && status != 'cancelled';

  factory LearningSession.fromJson(Map<String, dynamic> json) {
    final questionMap = _firstMap(json, const [
      'currentQuestion',
      'question',
      'nextQuestion',
    ]);
    return LearningSession(
      id: _string(json['id'], fallback: _string(json['sessionId'])),
      taskId: _string(json['taskId']),
      status: _string(json['status'], fallback: 'in_progress').toLowerCase(),
      currentIndex: _integer(
        json['currentIndex'],
        fallback: _integer(
          json['currentQuestionIndex'],
          fallback: _integer(json['questionIndex']),
        ),
      ),
      totalQuestions: _integer(
        json['totalQuestions'],
        fallback: _integer(json['questionCount']),
      ),
      correctCount: _integer(json['correctCount']),
      hintCount: _integer(json['hintCount']),
      currentQuestion: questionMap == null
          ? null
          : LearningQuestion.fromJson(questionMap),
      teachingFlow: _teachingFlowOrNull(json['teachingFlow']),
    );
  }
}

class LearningEvaluation {
  const LearningEvaluation({
    required this.isCorrect,
    required this.feedback,
    required this.hint,
    required this.hintLevel,
    required this.canRetry,
    this.status = '',
  });

  final bool isCorrect;
  final String feedback;
  final String hint;
  final int hintLevel;
  final bool canRetry;
  final String status;

  bool get isCompletedActivity => status == 'completed';

  factory LearningEvaluation.fromJson(Map<String, dynamic> json) {
    return LearningEvaluation(
      isCorrect: _boolean(
        json['isCorrect'],
        fallback: _boolean(json['correct']),
      ),
      feedback: _string(json['feedback'], fallback: _string(json['message'])),
      hint: _string(json['hint'], fallback: _string(json['nextHint'])),
      hintLevel: _integer(json['hintLevel'], fallback: _integer(json['level'])),
      canRetry: _boolean(
        json['canRetry'],
        fallback: !_boolean(json['completed']),
      ),
      status: _string(
        json['evaluationStatus'],
        fallback: _string(json['status']),
      ),
    );
  }
}

class LearningAnswerResult {
  const LearningAnswerResult({
    required this.session,
    required this.evaluation,
    this.nextQuestion,
    this.report,
  });

  final LearningSession session;
  final LearningEvaluation evaluation;
  final LearningQuestion? nextQuestion;
  final LearningReport? report;

  factory LearningAnswerResult.fromJson(Map<String, dynamic> json) {
    final root = _unwrapMap(json, const ['result', 'answerResult']);
    final sessionMap = _firstMap(root, const ['session']) ?? const {};
    final evaluationMap =
        _firstMap(root, const ['evaluation', 'judgement', 'judgment']) ?? root;
    final nextQuestionMap = _firstMap(root, const ['nextQuestion']);
    final reportMap = _firstMap(root, const ['report', 'latestReport']);
    return LearningAnswerResult(
      session: LearningSession.fromJson(sessionMap),
      evaluation: LearningEvaluation.fromJson(evaluationMap),
      nextQuestion: nextQuestionMap == null
          ? null
          : LearningQuestion.fromJson(nextQuestionMap),
      report: reportMap == null ? null : LearningReport.fromJson(reportMap),
    );
  }
}

class LearningReport {
  const LearningReport({
    required this.id,
    required this.summary,
    required this.totalQuestions,
    required this.correctCount,
    required this.independentCorrectCount,
    required this.hintCount,
    required this.masteryLabel,
    required this.nextSuggestion,
    this.subject = '',
    this.outcomeMode = 'scored_deterministic',
    this.childId = '',
    this.taskId = '',
    this.sessionId = '',
    this.courseId = '',
    this.courseVersion = '',
    this.courseTitle = '',
    this.learningDate = '',
    this.createdAtMilliseconds = 0,
    this.gradeCode = '',
    this.subjectCode = '',
    this.score = 0,
    this.strengths = const [],
  });

  final String id;
  final String summary;
  final int totalQuestions;
  final int correctCount;
  final int independentCorrectCount;
  final int hintCount;
  final String masteryLabel;
  final String nextSuggestion;
  final String subject;
  final String outcomeMode;
  final String childId;
  final String taskId;
  final String sessionId;
  final String courseId;
  final String courseVersion;
  final String courseTitle;
  final String learningDate;
  final int createdAtMilliseconds;
  final String gradeCode;
  final String subjectCode;
  final int score;
  final List<String> strengths;

  bool get isScored => outcomeMode == 'scored_deterministic';

  String get masteryDisplayLabel {
    return switch (masteryLabel.toLowerCase()) {
      'mastered' => '已掌握',
      'developing' => '巩固中',
      'needs_practice' => '需要练习',
      _ => masteryLabel,
    };
  }

  factory LearningReport.fromJson(Map<String, dynamic> json) {
    return LearningReport(
      id: _string(json['id'], fallback: _string(json['reportId'])),
      summary: _string(json['summary'], fallback: _string(json['conclusion'])),
      totalQuestions: _integer(json['totalQuestions']),
      correctCount: _integer(json['correctCount']),
      independentCorrectCount: _integer(
        json['independentCorrectCount'],
        fallback: _integer(json['independentCorrect']),
      ),
      hintCount: _integer(
        json['hintCount'],
        fallback: _integer(json['hintsUsed']),
      ),
      masteryLabel: _string(
        json['masteryLabel'],
        fallback: _string(
          json['masteryLevel'],
          fallback: _string(json['mastery']),
        ),
      ),
      nextSuggestion: _string(
        json['nextSuggestion'],
        fallback: _string(
          json['nextStep'],
          fallback: _string(json['recommendation']),
        ),
      ),
      subject: _string(
        json['subjectLabel'],
        fallback: _string(json['subject']),
      ),
      outcomeMode: _string(
        json['outcomeMode'],
        fallback: 'scored_deterministic',
      ),
      childId: _string(json['childId']),
      taskId: _string(json['taskId']),
      sessionId: _string(json['sessionId']),
      courseId: _string(json['courseId']),
      courseVersion: _string(json['courseVersion']),
      courseTitle: _string(json['courseTitle']),
      learningDate: _string(json['date']),
      createdAtMilliseconds: _integer(json['createdAt']),
      gradeCode: _string(json['gradeCode']),
      subjectCode: _string(json['subject']),
      score: _integer(json['score']),
      strengths: _stringList(json['strengths']),
    );
  }
}

class LearningReportPage {
  const LearningReportPage({
    required this.childId,
    required this.items,
    required this.nextCursor,
    this.subject,
  });

  final String childId;
  final String? subject;
  final List<LearningReport> items;
  final String? nextCursor;

  factory LearningReportPage.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'];
    final cursor = _string(json['nextCursor']);
    final subject = _string(json['subject']);
    return LearningReportPage(
      childId: _string(json['childId']),
      subject: subject.isEmpty ? null : subject,
      items: rawItems is List
          ? rawItems
                .map(learningResponseMap)
                .where((item) => item.isNotEmpty)
                .map(LearningReport.fromJson)
                .toList(growable: false)
          : const [],
      nextCursor: cursor.isEmpty ? null : cursor,
    );
  }
}

Map<String, dynamic> learningResponseMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) {
    return value.map((key, item) => MapEntry(key.toString(), item));
  }
  return const {};
}

Map<String, dynamic> _unwrapMap(
  Map<String, dynamic> json,
  List<String> preferredKeys,
) {
  final data = _mapOrNull(json['data']);
  final root = data ?? json;
  return _firstMap(root, preferredKeys) ?? root;
}

Map<String, dynamic>? _firstMap(Map<String, dynamic> json, List<String> keys) {
  for (final key in keys) {
    final value = _mapOrNull(json[key]);
    if (value != null) return value;
  }
  return null;
}

Map<String, dynamic>? _mapOrNull(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) {
    return value.map((key, item) => MapEntry(key.toString(), item));
  }
  return null;
}

String _string(dynamic value, {String fallback = ''}) {
  if (value == null) return fallback;
  if (value is String) return value.trim().isEmpty ? fallback : value.trim();
  if (value is num || value is bool) return value.toString();
  return fallback;
}

int _integer(dynamic value, {int fallback = 0}) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}

bool _boolean(dynamic value, {bool fallback = false}) {
  if (value is bool) return value;
  if (value is num) return value != 0;
  return switch (value?.toString().toLowerCase()) {
    'true' || '1' || 'yes' => true,
    'false' || '0' || 'no' => false,
    _ => fallback,
  };
}

List<String> _stringList(dynamic value) {
  if (value is! List) return const [];
  return value
      .map((item) {
        if (item is Map) {
          return _string(item['text'], fallback: _string(item['label']));
        }
        return _string(item);
      })
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

List<LearningChoice> _choiceList(dynamic value) {
  if (value is! List) return const [];
  final choices = <LearningChoice>[];
  for (var index = 0; index < value.length; index++) {
    final item = value[index];
    if (item is Map) {
      final id = _string(
        item['id'],
        fallback: _string(item['value'], fallback: '${index + 1}'),
      );
      final label = _string(item['label'], fallback: _string(item['text']));
      if (label.isNotEmpty) choices.add(LearningChoice(id: id, label: label));
      continue;
    }
    final label = _string(item);
    if (label.isNotEmpty) {
      choices.add(LearningChoice(id: label, label: label));
    }
  }
  return List.unmodifiable(choices);
}

LearningTeachingFlow? _teachingFlowOrNull(dynamic value) {
  final source = _mapOrNull(value);
  if (source == null) return null;
  final flow = LearningTeachingFlow.fromJson(source);
  return flow.isRunnable ? flow : null;
}

List<String> _idList(dynamic value) {
  if (value is! List) return const [];
  return value
      .map((item) {
        if (item is Map) {
          return _string(item['id'], fallback: _string(item['questionId']));
        }
        return _string(item);
      })
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

int _listLength(dynamic value) => value is List ? value.length : 0;
