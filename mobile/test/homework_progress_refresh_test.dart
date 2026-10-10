import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/features/homework/application/homework_photo_picker.dart';
import 'package:warm_sight/src/features/homework/application/homework_repository.dart';
import 'package:warm_sight/src/features/homework/domain/homework_models.dart';
import 'package:warm_sight/src/features/homework/presentation/homework_detail_page.dart';
import 'package:warm_sight/src/features/learning_review/application/learning_review_repository.dart';
import 'package:warm_sight/src/features/learning_review/presentation/learning_center_page.dart';

Map<String, dynamic> submission(String status) => {
  'id': 'hw_1',
  'childId': 'child_1',
  'title': '两页数学作业',
  'revision': 3,
  'status': status,
  'processing': status == 'recognizing',
  'analysisAvailable': true,
  'pages': [],
  'items': [],
};

void main() {
  Dio server(Object Function(RequestOptions) response) {
    final dio = Dio(BaseOptions(baseUrl: 'https://unit-test.invalid/api'));
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (request, handler) => handler.resolve(
          Response(requestOptions: request, data: response(request)),
        ),
      ),
    );
    return dio;
  }

  Future<ProviderContainer> container(Dio dio) async {
    SharedPreferences.setMockInitialValues({});
    final preferences = await SharedPreferences.getInstance();
    final result = ProviderContainer(
      overrides: [
        homeworkRepositoryProvider.overrideWithValue(
          HomeworkRepository(ApiClient(dio)),
        ),
        learningReviewRepositoryProvider.overrideWithValue(
          LearningReviewRepository(ApiClient(dio)),
        ),
        homeworkPhotoPickerProvider.overrideWithValue(
          HomeworkPhotoPicker(ImagePicker(), preferences, () => 'parent-test'),
        ),
        homeworkPhotoRecoveryProvider.overrideWith(
          (ref, childId) async => null,
        ),
      ],
    );
    addTearDown(result.dispose);
    return result;
  }

  Future<void> pump(
    WidgetTester tester,
    ProviderContainer scope,
    Widget app,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      UncontrolledProviderScope(container: scope, child: app),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
  }

  for (final list in [false, true]) {
    testWidgets(
      '${list ? 'list' : 'detail'} refresh shares initial and concurrent GET requests',
      (tester) async {
        final pending = <(RequestOptions, RequestInterceptorHandler)>[];
        final dio = Dio(BaseOptions(baseUrl: 'https://unit-test.invalid/api'));
        dio.interceptors.add(
          InterceptorsWrapper(
            onRequest: (request, handler) => pending.add((request, handler)),
          ),
        );
        final scope = await container(dio);
        Future<Object?> refresh() => list
            ? scope.read(homeworkListProvider('child_1').notifier).refresh()
            : scope.read(homeworkDetailProvider('hw_1').notifier).refresh();
        final keepAlive = list
            ? scope.listen(homeworkListProvider('child_1'), (_, _) {})
            : scope.listen(homeworkDetailProvider('hw_1'), (_, _) {});
        addTearDown(keepAlive.close);
        final initial = refresh();
        final sharedInitial = refresh();
        await tester.pump(const Duration(milliseconds: 50));
        expect(pending.length, 1);
        void complete(String status) {
          final (request, handler) = pending.last;
          expectSync(request.method, 'GET');
          handler.resolve(
            Response(
              requestOptions: request,
              data: list
                  ? {
                      'submissions': [submission(status)],
                    }
                  : {'submission': submission(status)},
            ),
          );
        }

        complete('recognizing');
        await tester.pump(const Duration(milliseconds: 50));
        await initial;
        await sharedInitial;
        await tester.pump(const Duration(milliseconds: 50));
        final first = refresh(), second = refresh();
        await tester.pump(const Duration(milliseconds: 50));
        expect(pending.length, 2);
        complete('needs_confirmation');
        await tester.pump(const Duration(milliseconds: 50));
        await first;
        await second;
        await tester.pump();
        final value = list
            ? scope.read(homeworkListProvider('child_1')).requireValue.single
            : scope.read(homeworkDetailProvider('hw_1')).requireValue;
        expect(value.status, 'needs_confirmation');
        expect(value.active, isFalse);
      },
    );
  }

  testWidgets('a completed detail wins over an older in-flight list read', (
    tester,
  ) async {
    RequestOptions? delayedRequest;
    RequestInterceptorHandler? delayedHandler;
    var reads = 0;
    final dio = Dio(BaseOptions(baseUrl: 'https://unit-test.invalid/api'));
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (request, handler) {
          reads++;
          if (reads == 2) {
            delayedRequest = request;
            delayedHandler = handler;
            return;
          }
          handler.resolve(
            Response(
              requestOptions: request,
              data: {
                'submissions': [submission('recognizing')],
              },
            ),
          );
        },
      ),
    );
    final scope = await container(dio);
    final provider = homeworkListProvider('child_1');
    final listener = scope.listen(provider, (_, _) {});
    addTearDown(listener.close);
    final loaded = scope.read(provider.future);
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pump(const Duration(milliseconds: 50));
    await loaded;
    final controller = scope.read(provider.notifier);
    final reading = controller.refresh();
    await tester.pump(const Duration(milliseconds: 50));
    controller.acceptFromDetail(
      HomeworkSubmission(submission('needs_confirmation')),
    );
    delayedHandler!.resolve(
      Response(
        requestOptions: delayedRequest!,
        data: {
          'submissions': [submission('recognizing')],
        },
      ),
    );
    await tester.pump(const Duration(milliseconds: 50));
    await reading;
    expect(
      scope.read(provider).requireValue.single.status,
      'needs_confirmation',
    );
  });

  testWidgets(
    'cached active detail starts polling and stops after completion',
    (tester) async {
      var reads = 0;
      final dio = server((request) {
        expectSync(request.method, 'GET');
        reads++;
        return {
          'submission': submission(
            reads == 1 ? 'recognizing' : 'needs_confirmation',
          ),
        };
      });
      final scope = await container(dio);
      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: scope,
          child: Consumer(
            builder: (context, ref, child) {
              ref.watch(homeworkDetailProvider('hw_1'));
              return const SizedBox();
            },
          ),
        ),
      );
      final listener = scope.listen(homeworkDetailProvider('hw_1'), (_, _) {});
      addTearDown(listener.close);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.pump(const Duration(milliseconds: 50));
      expect(reads, 1, reason: 'preloaded detail GET must complete');
      expect(scope.read(homeworkDetailProvider('hw_1')).hasValue, isTrue);
      await pump(
        tester,
        scope,
        MaterialApp(
          theme: AppTheme.light,
          home: const HomeworkDetailPage(submissionId: 'hw_1'),
        ),
      );
      expect(reads, 1);
      expect(find.text('刷新状态'), findsOneWidget);
      await tester.pump(const Duration(seconds: 4));
      await tester.pump();
      expect(reads, 2);
      expect(find.text('批改完成 · 部分题目待老师看原图'), findsOneWidget);
      await tester.pump(const Duration(seconds: 12));
      expect(reads, 2);
      expect(find.byType(LinearProgressIndicator), findsNothing);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'active list polls, pauses in background and reads completion on resume',
    (tester) async {
      var reads = 0;
      final dio = server((request) {
        expectSync(request.method, 'GET');
        if (request.path.endsWith('/homework-submissions')) {
          reads++;
          return {
            'submissions': [
              submission(reads < 3 ? 'recognizing' : 'needs_confirmation'),
            ],
          };
        }
        return {'reviews': [], 'weaknesses': []};
      });
      final scope = await container(dio);
      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: scope,
          child: Consumer(
            builder: (context, ref, child) {
              ref.watch(homeworkListProvider('child_1'));
              return const SizedBox();
            },
          ),
        ),
      );
      final listener = scope.listen(homeworkListProvider('child_1'), (_, _) {});
      addTearDown(listener.close);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.pump(const Duration(milliseconds: 50));
      await pump(
        tester,
        scope,
        MaterialApp(
          theme: AppTheme.light,
          home: const LearningCenterPage(childId: 'child_1'),
        ),
      );
      expect(reads, 1);
      await tester.pump(const Duration(seconds: 4));
      await tester.pump();
      expect(reads, 2);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.pump(const Duration(milliseconds: 50));
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pump(const Duration(seconds: 12));
      expect(reads, 2);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      for (var frame = 0; frame < 6; frame++) {
        await tester.pump(const Duration(milliseconds: 50));
      }
      expect(reads, 3);
      expect(find.textContaining('批改完成 · 部分题目待老师看原图'), findsOneWidget);
      await tester.pump(const Duration(seconds: 12));
      expect(reads, 3);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'covered list pauses its timer and refreshes on returning from detail',
    (tester) async {
      var listReads = 0;
      final dio = server((request) {
        expectSync(request.method, 'GET');
        if (request.path == '/homework-submissions/hw_1') {
          return {'submission': submission('needs_confirmation')};
        }
        if (request.path.endsWith('/homework-submissions')) {
          listReads++;
          return {
            'submissions': [
              submission(listReads == 1 ? 'recognizing' : 'needs_confirmation'),
            ],
          };
        }
        return {'reviews': [], 'weaknesses': []};
      });
      final scope = await container(dio);
      final router = GoRouter(
        initialLocation: '/center',
        routes: [
          GoRoute(
            path: '/center',
            builder: (context, state) =>
                const LearningCenterPage(childId: 'child_1'),
          ),
          GoRoute(
            path: '/learning-center/homework/:id',
            builder: (context, state) =>
                HomeworkDetailPage(submissionId: state.pathParameters['id']!),
          ),
        ],
      );
      addTearDown(router.dispose);
      await pump(
        tester,
        scope,
        MaterialApp.router(theme: AppTheme.light, routerConfig: router),
      );
      await tester.ensureVisible(find.text('两页数学作业'));
      await tester.tap(find.text('两页数学作业'));
      await tester.pumpAndSettle();
      await tester.pump(const Duration(seconds: 12));
      expect(listReads, 1);
      router.pop();
      await tester.pumpAndSettle();
      expect(listReads, 2);
      expect(find.textContaining('批改完成 · 部分题目待老师看原图'), findsOneWidget);
      await tester.pump(const Duration(seconds: 12));
      expect(listReads, 2);
      await tester.pumpWidget(const SizedBox());
    },
  );
}
