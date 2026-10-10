import '../../learning_review/domain/learning_review_models.dart';

class HomeworkSubmission {
  HomeworkSubmission(Json json)
    : data = json,
      pages = jsonList(json['pages']).map(HomeworkPage.new).toList(),
      items = jsonList(json['items']).map(HomeworkItem.new).toList();
  final Json data;
  final List<HomeworkPage> pages;
  final List<HomeworkItem> items;
  String get id => textValue(data['id']);
  String get childId => textValue(data['childId']);
  String get title => textValue(data['title']);
  bool get isEssay => data['analysisKind'] == 'essay';
  Json get essayReview => jsonMap(data['essayReview']);
  List<Json> get essaySuggestions => jsonList(essayReview['suggestions']);
  int get revision => number(data['revision']);
  String get status => textValue(data['status']);
  String get errorCode {
    final code = textValue(data['errorCode']);
    return code.isNotEmpty ? code : textValue(data['error']);
  }

  bool get recognitionResultNeedsReview => const {
    'homework_recognition_invalid_json',
    'homework_recognition_invalid_schema',
    'homework_recognition_truncated',
    'homework_recognition_over_limit',
    'homework_recognition_storage_failed',
  }.contains(errorCode);
  Json get summary => jsonMap(data['summary']);
  Json get originalPaperSummary {
    if (jsonMap(data['originalPaperSummary']).isEmpty) return const {};
    // Older Tencent responses may contain unreviewed summary counts. Derive
    // the visible formal totals from the same item authority as the markers.
    final correct = items.where((item) => item.paperStatus == 'correct').length;
    final incorrect = items
        .where((item) => item.paperStatus == 'incorrect')
        .length;
    return {
      'total': items.length,
      'correct': correct,
      'incorrect': incorrect,
      'blank': items.where((item) => item.paperStatus == 'blank').length,
      'unknown': items.length - correct - incorrect,
    };
  }

  Json get provisionalPaperSummary {
    final value = jsonMap(data['provisionalPaperSummary']);
    if (value['countsForAbility'] != false) return const {};
    if (items.isEmpty) return value;
    final unverified = items
        .where(
          (item) => !item.referenceAvailable && item.paperStatus != 'blank',
        )
        .toList();
    if (!unverified.any((item) => item.hasProvisionalVerdict)) return const {};
    final correct = unverified
        .where(
          (item) =>
              item.hasProvisionalVerdict &&
              item.displayPaperStatus == 'correct',
        )
        .length;
    final incorrect = unverified
        .where(
          (item) =>
              item.hasProvisionalVerdict &&
              item.displayPaperStatus == 'incorrect',
        )
        .length;
    return {
      'total': unverified.length,
      'correct': correct,
      'incorrect': incorrect,
      'unknown': unverified.length - correct - incorrect,
      'countsForAbility': false,
    };
  }

  Json get studentSummary => jsonMap(data['studentSummary']);
  int get studentCorrectionCount =>
      items.where((item) => item.status == 'incorrect').length;
  int get studentCorrectedCount => items
      .where(
        (item) =>
            item.status == 'incorrect' && item.correction.status == 'corrected',
      )
      .length;
  int get studentSelfReportedCompletedCount => items
      .where(
        (item) =>
            item.status == 'incorrect' && item.correction.selfReportedCompleted,
      )
      .length;
  int get studentReadyCount => items
      .where(
        (item) =>
            item.status == 'incorrect' &&
            item.data['readyForStudent'] == true &&
            item.correction.status != 'corrected' &&
            !item.correction.selfReportedCompleted,
      )
      .length;
  int get studentPreparingCount => studentSummary.containsKey('awaitingMedia')
      ? number(studentSummary['awaitingMedia'])
      : items
            .where(
              (item) =>
                  item.status == 'incorrect' &&
                  {
                    'picture_choice',
                    'numeric',
                  }.contains(item.data['answerMode']) &&
                  item.data['readyForStudent'] != true &&
                  item.data['correctionStatus'] != 'corrected',
            )
            .length;
  int get studentUnsupportedCount =>
      studentSummary.containsKey('unsupportedCorrection')
      ? number(studentSummary['unsupportedCorrection'])
      : items
            .where(
              (item) =>
                  item.status == 'incorrect' &&
                  item.data['readyForStudent'] != true &&
                  !{
                    'picture_choice',
                    'numeric',
                  }.contains(item.data['answerMode']),
            )
            .length;
  bool get analysisAvailable => data['analysisAvailable'] != false;
  bool get hasUnconfirmedProviderReceipt =>
      status == 'provider_unknown' ||
      (status != 'ready' &&
          const {
            'homework_provider_unknown',
            'homework_audio_unknown',
            'homework_tutor_unknown',
          }.contains(errorCode));
  bool get retryAllowed =>
      !hasUnconfirmedProviderReceipt &&
      !recognitionResultNeedsReview &&
      data['retryAllowed'] == true;
  bool get active =>
      !hasUnconfirmedProviderReceipt &&
      (data['processing'] is bool
          ? data['processing'] as bool
          : {
              'queued',
              'quality_check',
              'recognizing',
              'checking',
              'media_preparing',
            }.contains(status));
  bool get canAnalyze =>
      analysisAvailable &&
      !hasUnconfirmedProviderReceipt &&
      !active &&
      (status == 'received' || retryAllowed) &&
      pages.isNotEmpty;
  bool get canUpload => status == 'received' && !hasUnconfirmedProviderReceipt;
  bool get canEditPages => !active && !hasUnconfirmedProviderReceipt;
  String get statusLabel {
    if (hasUnconfirmedProviderReceipt) {
      return switch (errorCode) {
        'homework_provider_unknown' => '识别结果暂未确认',
        'homework_audio_unknown' => '教师语音暂未准备好',
        _ => '处理结果尚未确认',
      };
    }
    if (status == 'failed' && recognitionResultNeedsReview) {
      return '识别结果需要处理';
    }
    return status == 'received' && !analysisAvailable
        ? (pages.isEmpty ? '待添加照片' : '照片已保存')
        : const {
                'received': '待提交分析',
                'queued': '排队中',
                'quality_check': '检查照片清晰度',
                'recognizing': '正在识别题目',
                'checking': 'AI 正在批改',
                'media_preparing': '准备讲解',
                'ready': '分析完成',
                'needs_confirmation': '批改完成 · 部分题目待老师看原图',
                'failed': '分析未完成',
              }[status] ??
              '正在同步';
  }

  String? get analysisIssueMessage {
    if (hasUnconfirmedProviderReceipt) {
      return switch (errorCode) {
        'homework_provider_unknown' =>
          '照片已保存，不需要重新上传。题目识别结果暂未确认，需要人工检查处理；为避免重复计费，不会自动再次分析。可刷新查看处理结果。',
        'homework_audio_unknown' =>
          '作业识别结果和照片已保存，不需要重新上传。教师语音暂未准备好，需要人工检查处理；为避免重复计费，不会自动重新生成语音。可刷新查看处理结果。',
        _ => '上次分析未能确认结果，照片已保存，不需要重新上传。需要人工检查处理；为避免重复计费，不会自动再次分析。可刷新查看状态。',
      };
    }
    if (status != 'failed') return null;
    final reason = switch (errorCode) {
      'homework_recognition_invalid_json' => '这次返回的识别结果无法读取',
      'homework_recognition_invalid_schema' => '这次返回的题目内容不完整',
      'homework_recognition_truncated' => '这次返回的识别结果不完整',
      'homework_recognition_over_limit' => '这次返回的题目数量超出处理范围',
      'homework_recognition_storage_failed' => '识别结果保存未完成',
      _ => null,
    };
    return reason == null
        ? '这次分析未完成。请检查照片清晰度，可显式重试；不会在后台重复发起分析。'
        : '照片已保存，不需要重新上传。$reason，需要人工检查处理；不会自动重新分析。可刷新查看处理结果。';
  }
}

class HomeworkPage {
  const HomeworkPage(this.data);
  final Json data;
  String get id => textValue(data['id']);
  int get rotation => number(data['rotation']);
  double get aspectRatio {
    final w = number(data['width']), h = number(data['height']);
    return w > 0 && h > 0 ? w / h : 0.75;
  }

  Json get edit => {'id': id, 'rotation': rotation, 'crop': data['crop']};
}

class HomeworkItem {
  const HomeworkItem(this.data);
  final Json data;
  String get id => textValue(data['id']);
  String get pageId => textValue(data['pageId']);
  int get revision => number(data['revision']);
  String get prompt => textValue(data['prompt']);
  String get answer => textValue(data['studentAnswer']);
  String get status => textValue(data['status']);
  Json get gradingReference => jsonMap(data['gradingReference']);
  Json get referenceGate => jsonMap(gradingReference['referenceGate']);
  String get referenceGateStatus => textValue(referenceGate['status']);
  bool get referenceAvailable => referenceGate.isNotEmpty
      ? referenceGate['available'] == true &&
            const {
              'provider_consistent',
              'exact',
              'human_verified',
            }.contains(referenceGateStatus)
      : referenceVerified;
  HomeworkStudentCorrection get correction =>
      HomeworkStudentCorrection(jsonMap(data['studentCorrection']), data);
  Json get latestTutorTeachingQuality =>
      jsonMap(data['latestTutorTeachingQuality']);
  bool get hasSafeTutorGuidance =>
      const {
        'verified',
        'guidance',
      }.contains(latestTutorTeachingQuality['status']) &&
      latestTutorTeachingQuality['countsForAbility'] == false;
  String get latestTutorGuidance =>
      hasSafeTutorGuidance ? textValue(data['latestTutorTeacherText']) : '';
  String get paperStatus {
    final providerStatus = textValue(gradingReference['status']);
    if (referenceAvailable &&
        {'correct', 'incorrect'}.contains(providerStatus)) {
      return providerStatus;
    }
    if (gradingReference['answerState'] == 'blank') return 'blank';
    if (gradingReference.isNotEmpty &&
        !referenceAvailable &&
        {'correct', 'incorrect'}.contains(status)) {
      return 'pending';
    }
    return status;
  }

  bool get referenceVerified => referenceGate.isNotEmpty
      ? referenceGate['available'] == true &&
            const {'exact', 'human_verified'}.contains(referenceGateStatus)
      : gradingReference.isEmpty
      ? {'correct', 'incorrect'}.contains(status)
      : jsonMap(gradingReference['studentQuality'])['status'] == 'verified' &&
            jsonMap(gradingReference['studentQuality'])['countsForAbility'] ==
                false;

  bool get hasProvisionalVerdict {
    if (referenceAvailable ||
        {'correct', 'incorrect', 'blank'}.contains(paperStatus)) {
      return false;
    }
    final verdict = jsonMap(gradingReference['providerVerdict']);
    return verdict['source'] == 'tencent' &&
        verdict['provisional'] == true &&
        verdict['countsForAbility'] == false &&
        {'correct', 'incorrect'}.contains(verdict['status']);
  }

  String get displayPaperStatus => hasProvisionalVerdict
      ? textValue(jsonMap(gradingReference['providerVerdict'])['status'])
      : paperStatus;

  Json get region => gradingReference.isNotEmpty
      ? gradingReference['geometryVerified'] == true
            ? jsonMap(gradingReference['answerRegion'])
            : const <String, dynamic>{}
      : jsonMap(data['region']);
  String get statusLabel => hasProvisionalVerdict
      ? displayPaperStatus == 'correct'
            ? '腾讯初判正确'
            : '腾讯初判建议再看'
      : paperStatus == 'blank'
      ? '空白未作答'
      : gradingReference.isNotEmpty &&
            {'correct', 'incorrect'}.contains(paperStatus)
      ? paperStatus == 'correct'
            ? (gradingReference['provider'] == 'tencent' ? '腾讯批改正确' : '批改正确')
            : (gradingReference['provider'] == 'tencent' ? '腾讯批改建议订正' : '批改需订正')
      : const {
              'correct': '批改正确',
              'incorrect': '需要学生订正',
              'blank': '空白未作答',
              'pending': '待老师看原图',
              'unsupported': '暂不支持自动判定',
            }[status] ??
            '待老师看原图';
}

class HomeworkStudentCorrection {
  const HomeworkStudentCorrection(this.data, this.legacy);
  final Json data;
  final Json legacy;
  String get status => textValue(data['status']).isNotEmpty
      ? textValue(data['status'])
      : textValue(legacy['correctionStatus']);
  bool get selfReportedCompleted =>
      status == 'self_reported' &&
      data['selfReportedCompleted'] == true &&
      correct != true;
  int? get selfReportedCompletedAt => data['selfReportedCompletedAt'] is num
      ? (data['selfReportedCompletedAt'] as num).toInt()
      : null;
  String get lastAnswer => textValue(data['lastAnswer']);
  int get attempts => number(data['attempts']).clamp(0, 1000);
  bool? get correct => data['correct'] is bool ? data['correct'] as bool : null;
  bool get hintViewed =>
      data['hintViewed'] == true || legacy['hintViewed'] == true;
  bool get explanationViewed =>
      data['explanationViewed'] == true || legacy['explanationViewed'] == true;
  bool get tutorViewed => data['tutorViewed'] == true;
  bool get hasActivity =>
      selfReportedCompleted ||
      attempts > 0 ||
      lastAnswer.isNotEmpty ||
      hintViewed ||
      explanationViewed ||
      tutorViewed;
  String get answerStatus => correct == true
      ? '本次答对'
      : correct == false
      ? '还需再试'
      : '回答已保存';
}
