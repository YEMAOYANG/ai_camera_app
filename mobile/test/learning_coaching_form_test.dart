import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/profile/domain/report_learning_models.dart';
import 'package:warm_sight/src/features/profile/presentation/widgets/learning_coaching_form.dart';
import 'support/parent_textbook_visual_capture.dart';

void main() {
  setUpAll(loadParentTextbookPreviewFont);
  testWidgets(
    'optional effort sends an explicit zero and recovers a version conflict without retrying',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final writes = <Map<String, dynamic>>[];
      var reads = 0;
      final dio = Dio(BaseOptions(baseUrl: 'http://local-test.invalid/api'));
      dio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (request, handler) {
            if (request.method == 'GET') {
              reads++;
              handler.resolve(
                Response(
                  requestOptions: request,
                  data: {
                    'coaching': {
                      'minutes': 5,
                      'reason': 'company',
                      'revision': 2,
                    },
                  },
                ),
              );
            } else {
              writes.add(Map<String, dynamic>.from(request.data as Map));
              if (writes.length == 2) {
                handler.reject(
                  DioException(
                    requestOptions: request,
                    response: Response(
                      requestOptions: request,
                      statusCode: 409,
                      data: {
                        'error': 'coaching_conflict',
                        'message': '家人已更新，请读取最新记录。',
                      },
                    ),
                  ),
                );
              } else {
                handler.resolve(
                  Response(
                    requestOptions: request,
                    data: {
                      'coaching': {
                        ...writes.last,
                        'revision': writes.last['revision'] + 1,
                      },
                    },
                  ),
                );
              }
            }
          },
        ),
      );
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            profileRepositoryProvider.overrideWithValue(
              ProfileRepository(apiClient: ApiClient(dio)),
            ),
            profileSummaryProvider.overrideWith(
              (ref) async => ProfileSummary.fromJson({
                'capabilities': ['manage_tasks'],
              }),
            ),
            dailyReportProvider.overrideWith(
              (ref) async => ReportData.fromJson({}),
            ),
            weeklyReportProvider.overrideWith(
              (ref) async => ReportData.fromJson({}),
            ),
          ],
          child: MaterialApp(
            theme: AppTheme.light,
            home: Scaffold(
              body: RepaintBoundary(
                key: parentTextbookPreviewKey,
                child: Material(
                  color: const Color(0xFFF8FAFD),
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(20),
                    child: LearningCoachingForm(
                      lesson: ReportLearningLesson.fromJson({
                        'learningSessionId': 'session-test',
                        'recordDate': '2026-09-29',
                      }),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(writes, isEmpty);
      await tester.tap(find.text('记录辅导用时（自愿）'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('没有辅导'));
      await tester.ensureVisible(find.text('保存记录'));
      await tester.tap(find.text('保存记录'));
      await tester.pumpAndSettle();
      expect(writes.single, {
        'recordDate': '2026-09-29',
        'minutes': 0,
        'usualMinutes': null,
        'reason': 'none',
        'revision': 0,
      });
      await tester.ensureVisible(find.text('2 分钟'));
      await tester.tap(find.text('2 分钟'));
      await tester.ensureVisible(find.text('保存记录'));
      await tester.tap(find.text('保存记录'));
      await tester.pumpAndSettle();
      expect(writes.length, 2);
      expect(find.text('家人已更新，请读取最新记录。'), findsOneWidget);
      await tester.ensureVisible(find.text('读取最新记录'));
      await tester.tap(find.text('读取最新记录'));
      await tester.pumpAndSettle();
      expect(reads, 1);
      await tester.tap(find.text('保存记录'));
      await tester.pumpAndSettle();
      expect(writes.last['revision'], 2);
      expect(writes.last['minutes'], 5);
      expect(tester.takeException(), isNull);
      await tester.ensureVisible(find.text('辅导用时 · 5 分钟'));
      await captureParentTextbookPreview(tester, 'parent-coaching-390');
    },
  );
}
