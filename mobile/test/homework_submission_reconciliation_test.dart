import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/features/homework/application/homework_photo_picker.dart';
import 'package:warm_sight/src/features/homework/application/homework_repository.dart';
import 'package:warm_sight/src/features/homework/presentation/homework_detail_page.dart';
import 'support/parent_textbook_visual_capture.dart';

void main() {
  setUpAll(loadParentTextbookPreviewFont);
  final png = base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC',
  );
  Map<String, Object?> detail(String status, {String? error}) => {
    'submission': {
      'id': 'hw_1',
      'childId': 'child_1',
      'title': '两页数学作业',
      'revision': 2,
      'status': status,
      'error': error,
      'analysisAvailable': true,
      'processing': status == 'queued',
      'retryAllowed': false,
      'pages': [
        {'id': 'page_1', 'width': 400, 'height': 200, 'rotation': 0},
      ],
      'items': [],
    },
  };

  Future<void> pump(
    WidgetTester tester,
    Dio dio, {
    bool pendingSecondPhoto = false,
  }) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    SharedPreferences.setMockInitialValues({
      if (pendingSecondPhoto)
        'homework.pending.test-parent': jsonEncode({
          'hw_1': [
            {'path': 'pending-second-photo', 'key': 'page-2-upload-key'},
          ],
        }),
    });
    final prefs = await SharedPreferences.getInstance();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          homeworkRepositoryProvider.overrideWithValue(
            HomeworkRepository(ApiClient(dio)),
          ),
          homeworkPhotoPickerProvider.overrideWithValue(
            HomeworkPhotoPicker(ImagePicker(), prefs, () => 'test-parent'),
          ),
        ],
        child: MaterialApp(
          theme: AppTheme.light,
          home: const HomeworkDetailPage(submissionId: 'hw_1'),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
  }

  testWidgets(
    'a pending second photo prevents analysis of only the first page',
    (tester) async {
      final requests = <RequestOptions>[];
      final dio = Dio(BaseOptions(baseUrl: 'https://unit-test.invalid/api'));
      dio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (request, handler) {
            if (request.responseType == ResponseType.bytes) {
              handler.resolve(Response(requestOptions: request, data: png));
            } else {
              requests.add(request);
              handler.resolve(
                Response(requestOptions: request, data: detail('received')),
              );
            }
          },
        ),
      );
      await pump(tester, dio, pendingSecondPhoto: true);
      await tester.pumpAndSettle();
      expect(find.textContaining('还有 1 张照片尚未上传'), findsOneWidget);
      expect(find.text('继续上传'), findsOneWidget);
      expect(find.text('提交分析'), findsNothing);
      expect(requests.map((request) => request.method), ['GET']);
      expect(tester.takeException(), isNull);
    },
  );

  for (final serverStatus in ['queued', 'provider_unknown']) {
    testWidgets(
      'analyze timeout reads $serverStatus once instead of resending the request',
      (tester) async {
        final requests = <RequestOptions>[];
        var submitted = false;
        final dio = Dio(BaseOptions(baseUrl: 'https://unit-test.invalid/api'));
        dio.interceptors.add(
          InterceptorsWrapper(
            onRequest: (request, handler) {
              if (request.responseType == ResponseType.bytes) {
                handler.resolve(Response(requestOptions: request, data: png));
                return;
              }
              requests.add(request);
              if (request.method == 'POST') {
                submitted = true;
                handler.reject(
                  DioException(
                    requestOptions: request,
                    type: DioExceptionType.receiveTimeout,
                  ),
                );
                return;
              }
              handler.resolve(
                Response(
                  requestOptions: request,
                  data: detail(
                    submitted ? serverStatus : 'received',
                    error: submitted && serverStatus == 'provider_unknown'
                        ? 'homework_provider_unknown'
                        : null,
                  ),
                ),
              );
            },
          ),
        );
        await pump(tester, dio);
        await tester.ensureVisible(find.text('提交分析'));
        await tester.tap(find.text('提交分析'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 250));
        expect(requests.map((request) => request.method), [
          'GET',
          'POST',
          'GET',
        ]);
        expect(find.text('提交分析'), findsNothing);
        expect(
          find.text(serverStatus == 'queued' ? '排队中' : '识别结果暂未确认'),
          findsOneWidget,
        );
        if (serverStatus == 'provider_unknown') {
          await tester.pump(const Duration(seconds: 8));
          expect(requests.map((request) => request.method), [
            'GET',
            'POST',
            'GET',
          ]);
          expect(find.text('刷新状态'), findsOneWidget);
        }
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox.shrink());
        await tester.pump();
      },
    );
  }

  testWidgets(
    'a failed status read keeps analysis locked until an explicit GET succeeds',
    (tester) async {
      final requests = <RequestOptions>[];
      var submitted = false;
      var failStatusRead = true;
      final dio = Dio(BaseOptions(baseUrl: 'https://unit-test.invalid/api'));
      dio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (request, handler) {
            if (request.responseType == ResponseType.bytes) {
              handler.resolve(Response(requestOptions: request, data: png));
              return;
            }
            requests.add(request);
            if (request.method == 'POST') {
              submitted = true;
              handler.reject(
                DioException(
                  requestOptions: request,
                  type: DioExceptionType.receiveTimeout,
                ),
              );
            } else if (submitted && failStatusRead) {
              handler.reject(
                DioException(
                  requestOptions: request,
                  type: DioExceptionType.connectionError,
                ),
              );
            } else {
              handler.resolve(
                Response(
                  requestOptions: request,
                  data: detail(submitted ? 'ready' : 'received'),
                ),
              );
            }
          },
        ),
      );
      await pump(tester, dio);
      await tester.ensureVisible(find.text('提交分析'));
      await tester.tap(find.text('提交分析'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 250));
      expect(requests.map((request) => request.method), ['GET', 'POST', 'GET']);
      expect(find.text('提交状态尚未确认'), findsOneWidget);
      expect(find.textContaining('提交结果暂未确认，照片已保存'), findsOneWidget);
      expect(find.text('提交分析'), findsNothing);
      expect(find.text('拍一页'), findsNothing);
      expect(find.text('刷新提交状态'), findsOneWidget);
      await tester.pump(const Duration(seconds: 8));
      expect(requests.map((request) => request.method), ['GET', 'POST', 'GET']);
      failStatusRead = false;
      await tester.ensureVisible(find.text('刷新提交状态'));
      await tester.tap(find.text('刷新提交状态'));
      await tester.pumpAndSettle();
      expect(requests.map((request) => request.method), [
        'GET',
        'POST',
        'GET',
        'GET',
      ]);
      expect(find.text('分析完成'), findsOneWidget);
      expect(find.textContaining('提交结果暂未确认'), findsNothing);
      expect(find.text('刷新提交状态'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('pending photos also prevent a safe media preparation retry', (
    tester,
  ) async {
    final requests = <RequestOptions>[];
    final dio = Dio(BaseOptions(baseUrl: 'https://unit-test.invalid/api'));
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (request, handler) {
          if (request.responseType == ResponseType.bytes) {
            handler.resolve(Response(requestOptions: request, data: png));
            return;
          }
          requests.add(request);
          final response = detail('media_preparing');
          (response['submission'] as Map<String, Object?>)['retryAllowed'] =
              true;
          handler.resolve(Response(requestOptions: request, data: response));
        },
      ),
    );
    await pump(tester, dio, pendingSecondPhoto: true);
    await tester.pumpAndSettle();
    expect(find.text('继续准备讲解'), findsNothing);
    expect(find.text('重试分析'), findsNothing);
    expect(find.textContaining('请先继续上传或移除，再提交分析'), findsOneWidget);
    expect(requests.map((request) => request.method), ['GET']);
    expect(tester.takeException(), isNull);
  });
}
