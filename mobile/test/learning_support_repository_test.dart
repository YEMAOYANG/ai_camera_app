import 'dart:async';
import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/homework/application/homework_photo_picker.dart';
import 'package:warm_sight/src/features/homework/application/homework_repository.dart';
import 'package:warm_sight/src/features/homework/domain/homework_models.dart';
import 'package:warm_sight/src/features/learning_review/application/learning_review_repository.dart';
import 'package:warm_sight/src/features/learning_review/domain/learning_review_models.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Dio dio;
  late List<RequestOptions> requests;
  setUp(() {
    requests = [];
    dio = Dio(BaseOptions(baseUrl: 'https://unit-test.invalid/api'));
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (r, h) {
          requests.add(r);
          h.resolve(
            Response(
              requestOptions: r,
              data: r.responseType == ResponseType.bytes
                  ? <int>[1, 2, 3]
                  : {
                      'ok': true,
                      'submission': {'id': 'hw_1', 'revision': 4},
                      'preferences': r.data,
                    },
            ),
          );
        },
      ),
    );
  });
  test('essay selection reaches the durable submission contract', () async {
    await HomeworkRepository(ApiClient(dio)).create(
      'child_1',
      title: '我的作文',
      subject: 'chinese',
      analysisKind: 'essay',
      idempotencyKey: 'essay-create-once',
    );
    expect(requests.single.data, containsPair('analysisKind', 'essay'));
    expect(requests.single.data, containsPair('subject', 'chinese'));
    expect(
      requests.single.data,
      containsPair('idempotencyKey', 'essay-create-once'),
    );
  });
  test(
    'private image ignores server media URLs and uses encoded authenticated relative path',
    () async {
      final repo = HomeworkRepository(ApiClient(dio));
      expect(
        await repo.image('hw_1', 'page_1', original: true),
        Uint8List.fromList([1, 2, 3]),
      );
      expect(
        requests.single.path,
        '/homework-submissions/hw_1/pages/page_1/image',
      );
      expect(requests.single.queryParameters, {'original': '1'});
      expect(requests.single.responseType, ResponseType.bytes);
      expect(requests.single.followRedirects, false);
    },
  );
  test(
    'multipart uploads keep stable per-page key and optimistic revision',
    () async {
      final repo = HomeworkRepository(ApiClient(dio));
      await repo.upload(
        HomeworkSubmission({'id': 'hw_1', 'revision': 3}),
        bytes: Uint8List.fromList([1, 2]),
        idempotencyKey: 'same-upload-key',
      );
      final form = requests.single.data as FormData;
      expect(Map.fromEntries(form.fields), {
        'revision': '3',
        'idempotencyKey': 'same-upload-key',
      });
      expect(form.files.single.value.contentType.toString(), 'image/png');
      expect(requests.single.path, '/homework-submissions/hw_1/pages');
    },
  );
  test(
    'uncertain network outcome is surfaced without automatic paid analyze retry',
    () async {
      dio.interceptors.clear();
      dio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (r, h) {
            requests.add(r);
            h.reject(
              DioException(
                requestOptions: r,
                type: DioExceptionType.receiveTimeout,
              ),
            );
          },
        ),
      );
      await expectLater(
        HomeworkRepository(
          ApiClient(dio),
        ).analyze(HomeworkSubmission({'id': 'hw_1', 'revision': 3})),
        throwsA(isA<DioException>()),
      );
      expect(requests.length, 1);
    },
  );
  test(
    'schedule actions preserve appointment revision and request id',
    () async {
      await LearningReviewRepository(ApiClient(dio)).schedule(
        'child_1',
        const ReviewRun({'id': 'review_1', 'appointmentRevision': 7}),
        'pause',
        requestId: 'retained-id',
      );
      expect(requests.single.data, {
        'childId': 'child_1',
        'action': 'pause',
        'appointmentRevision': 7,
        'requestId': 'retained-id',
      });
    },
  );
  test(
    'pending uploads are isolated between signed in parents and discarded individually',
    () async {
      SharedPreferences.setMockInitialValues({
        'homework.pending.parent_a': jsonEncode({
          'hw_1': [
            {'path': 'unit-fixture-one', 'key': 'upload_a'},
            {'path': 'unit-fixture-two', 'key': 'upload_b'},
          ],
        }),
      });
      final prefs = await SharedPreferences.getInstance();
      var user = 'parent_a';
      final picker = HomeworkPhotoPicker(ImagePicker(), prefs, () => user);
      expect(picker.pending('hw_1').length, 2);
      user = 'parent_b';
      expect(picker.pending('hw_1'), isEmpty);
      user = 'parent_a';
      await picker.remove('hw_1', 'upload_a');
      expect(picker.pending('hw_1').single.key, 'upload_b');
      await picker.discard('hw_1');
      expect(picker.pending('hw_1'), isEmpty);
    },
  );
  test(
    'a parent change while gallery is open never saves photos for the next parent',
    () async {
      SharedPreferences.setMockInitialValues({});
      final preferences = await SharedPreferences.getInstance();
      var parent = 'parent_a';
      final platform = _DelayedPicker();
      final picker = HomeworkPhotoPicker(platform, preferences, () => parent);
      final operation = picker.pick(
        'submission_a',
        'child_a',
        camera: false,
        remaining: 10,
      );
      await platform.started.future;
      parent = 'parent_b';
      platform.result.complete([XFile('synthetic-test-photo')]);
      await expectLater(operation, throwsA(isA<HomeworkPhotoException>()));
      expect(picker.pending('submission_a'), isEmpty);
      parent = 'parent_a';
      expect(picker.pending('submission_a'), isEmpty);
    },
  );
  test(
    'discarding photos prevents a late picker result from restoring them',
    () async {
      SharedPreferences.setMockInitialValues({});
      final preferences = await SharedPreferences.getInstance();
      final platform = _DelayedPicker();
      final picker = HomeworkPhotoPicker(
        platform,
        preferences,
        () => 'parent_a',
      );
      final operation = picker.pick(
        'hw_1',
        'child_1',
        camera: false,
        remaining: 10,
      );
      await platform.started.future;
      await picker.discard('hw_1');
      platform.result.complete([XFile('synthetic-test-photo')]);
      await expectLater(operation, throwsA(isA<HomeworkPhotoException>()));
      expect(picker.pending('hw_1'), isEmpty);
      expect(preferences.getString('homework.capture.parent_a'), isNull);
    },
  );
  test(
    'discarding an Android capture prevents in-flight recovery from restoring it',
    () async {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      SharedPreferences.setMockInitialValues({
        'homework.capture.parent_a': jsonEncode({
          'submissionId': 'hw_1',
          'childId': 'child_1',
        }),
      });
      final preferences = await SharedPreferences.getInstance();
      final platform = _DelayedRecoveryPicker();
      final picker = HomeworkPhotoPicker(
        platform,
        preferences,
        () => 'parent_a',
      );
      final operation = picker.recover('child_1');
      await platform.started.future;
      await picker.discard('hw_1');
      platform.result.complete(
        LostDataResponse(files: [XFile('synthetic-test-photo')]),
      );
      expect(await operation, isNull);
      expect(picker.pending('hw_1'), isEmpty);
    },
  );
  test(
    'saved deletion wins over an in-flight or older revision refresh',
    () async {
      final old = {
        'id': 'hw_1',
        'revision': 1,
        'pages': [
          {'id': 'page_1'},
        ],
      };
      final delayed = Completer<void>(), started = Completer<void>();
      var reads = 0;
      dio.interceptors.clear();
      dio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (r, h) async {
            reads++;
            if (reads == 2) {
              started.complete();
              await delayed.future;
            }
            h.resolve(Response(requestOptions: r, data: {'submission': old}));
          },
        ),
      );
      final container = ProviderContainer(
        overrides: [
          homeworkRepositoryProvider.overrideWithValue(
            HomeworkRepository(ApiClient(dio)),
          ),
        ],
      );
      addTearDown(container.dispose);
      final provider = homeworkDetailProvider('hw_1');
      final listener = container.listen(provider, (_, _) {});
      addTearDown(listener.close);
      await container.read(provider.future);
      final controller = container.read(provider.notifier);
      final refresh = controller.refresh();
      await started.future;
      controller.beginMutation();
      controller.accept(
        HomeworkSubmission({'id': 'hw_1', 'revision': 2, 'pages': []}),
      );
      delayed.complete();
      await refresh;
      expect(container.read(provider).requireValue.pages, isEmpty);
      await controller.refresh();
      expect(container.read(provider).requireValue.revision, 2);
      expect(container.read(provider).requireValue.pages, isEmpty);
    },
  );
  test(
    'paused analysis keeps saved drafts editable without allowing dispatch',
    () {
      final draft = HomeworkSubmission({
        'status': 'received',
        'analysisAvailable': false,
        'processing': false,
        'retryAllowed': false,
        'pages': [
          {'id': 'page'},
        ],
      });
      expect(draft.canUpload, isTrue);
      expect(draft.active, isFalse);
      expect(draft.canAnalyze, isFalse);
      expect(
        HomeworkSubmission({
          ...draft.data,
          'analysisAvailable': true,
        }).canAnalyze,
        isTrue,
      );
    },
  );
  test('provider unknown and active statuses never enable analysis', () {
    final unknown = HomeworkSubmission({
      'status': 'provider_unknown',
      'processing': true,
      'retryAllowed': true,
      'pages': [
        {'id': 'page'},
      ],
    });
    expect(unknown.statusLabel, '处理结果尚未确认');
    expect(unknown.active, isFalse);
    expect(unknown.retryAllowed, isFalse);
    expect(unknown.canAnalyze, isFalse);
    expect(unknown.canUpload, isFalse);
    for (final status in [
      'provider_unknown',
      'queued',
      'quality_check',
      'recognizing',
      'checking',
      'media_preparing',
    ]) {
      expect(
        HomeworkSubmission({
          'status': status,
          'pages': [
            {'id': 'page'},
          ],
        }).canAnalyze,
        isFalse,
      );
    }
    expect(
      HomeworkSubmission({
        'status': 'failed',
        'retryAllowed': true,
        'pages': [
          {'id': 'page'},
        ],
      }).canAnalyze,
      isTrue,
    );
    final waitingAudio = HomeworkSubmission({
      'status': 'media_preparing',
      'processing': false,
      'retryAllowed': true,
      'pages': [
        {'id': 'page'},
      ],
    });
    expect(waitingAudio.active, isFalse);
    expect(waitingAudio.canAnalyze, isTrue);
    expect(
      HomeworkSubmission({'status': 'received', 'pages': []}).canAnalyze,
      isFalse,
    );
  });
  test(
    'unknown result identifies recognition or voice without allowing retry',
    () {
      for (final issue in [
        (
          code: 'homework_provider_unknown',
          label: '识别结果暂未确认',
          detail: '题目识别结果暂未确认',
        ),
        (
          code: 'homework_audio_unknown',
          label: '教师语音暂未准备好',
          detail: '作业识别结果和照片已保存',
        ),
      ]) {
        for (final errorField in ['error', 'errorCode']) {
          final submission = HomeworkSubmission({
            'status': 'provider_unknown',
            errorField: issue.code,
            'processing': true,
            'retryAllowed': true,
            'pages': [
              {'id': 'page'},
            ],
          });
          expect(submission.errorCode, issue.code);
          expect(submission.statusLabel, issue.label);
          expect(submission.analysisIssueMessage, contains(issue.detail));
          expect(submission.analysisIssueMessage, contains('不需要重新上传'));
          expect(submission.analysisIssueMessage, contains('需要人工检查处理'));
          expect(submission.active, isFalse);
          expect(submission.retryAllowed, isFalse);
          expect(submission.canAnalyze, isFalse);
        }
      }
    },
  );
  test(
    'returned recognition errors keep photos and block another paid dispatch',
    () {
      for (final code in [
        'homework_recognition_invalid_json',
        'homework_recognition_invalid_schema',
        'homework_recognition_truncated',
        'homework_recognition_over_limit',
        'homework_recognition_storage_failed',
      ]) {
        final submission = HomeworkSubmission({
          'status': 'failed',
          'error': code,
          'processing': false,
          'retryAllowed': true,
          'pages': [
            {'id': 'page'},
          ],
        });
        expect(submission.statusLabel, '识别结果需要处理');
        expect(submission.analysisIssueMessage, contains('照片已保存'));
        expect(submission.analysisIssueMessage, contains('不需要重新上传'));
        expect(submission.analysisIssueMessage, contains('需要人工检查处理'));
        expect(submission.analysisIssueMessage, isNot(contains('JSON')));
        expect(submission.analysisIssueMessage, isNot(contains('schema')));
        expect(submission.active, isFalse);
        expect(submission.retryAllowed, isFalse);
        expect(submission.canAnalyze, isFalse);
        expect(submission.pages.single.id, 'page');
      }
    },
  );
  test('a later successful state clears the previous result issue copy', () {
    final submission = HomeworkSubmission({
      'status': 'ready',
      'error': 'homework_provider_unknown',
    });
    expect(submission.statusLabel, '分析完成');
    expect(submission.analysisIssueMessage, isNull);
  });
  test(
    'student correction progress excludes uncertain and already finished tasks',
    () {
      final value = HomeworkSubmission({
        'items': [
          {'status': 'incorrect', 'readyForStudent': true},
          {
            'status': 'incorrect',
            'readyForStudent': true,
            'correctionStatus': 'corrected',
          },
          {
            'status': 'incorrect',
            'readyForStudent': false,
            'answerMode': 'picture_choice',
          },
          {'status': 'pending', 'readyForStudent': true},
          {'status': 'correct', 'readyForStudent': true},
        ],
      });
      expect(value.studentCorrectionCount, 3);
      expect(value.studentReadyCount, 1);
      expect(value.studentPreparingCount, 1);
      expect(value.studentCorrectedCount, 1);
      expect(value.studentUnsupportedCount, 0);
    },
  );
}

class _DelayedPicker extends ImagePicker {
  final started = Completer<void>();
  final result = Completer<List<XFile>>();
  @override
  Future<List<XFile>> pickMultiImage({
    double? maxWidth,
    double? maxHeight,
    int? imageQuality,
    bool requestFullMetadata = true,
    int? limit,
  }) {
    started.complete();
    return result.future;
  }
}

class _DelayedRecoveryPicker extends ImagePicker {
  final started = Completer<void>();
  final result = Completer<LostDataResponse>();
  @override
  Future<LostDataResponse> retrieveLostData() {
    started.complete();
    return result.future;
  }
}
