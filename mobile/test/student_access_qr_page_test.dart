import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/config/app_environment.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/learning/application/learning_availability_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_availability_models.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/student_access/application/student_access_repository.dart';
import 'package:warm_sight/src/features/student_access/application/student_access_availability.dart';
import 'package:warm_sight/src/features/student_access/domain/student_access_models.dart';
import 'package:warm_sight/src/features/student_access/presentation/student_access_qr_page.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';

void main() {
  for (final confirming in [false, true]) {
    testWidgets(
      'course polling preserves ${confirming ? "confirmation focus and PIN" : "the mounted scanner"}',
      (tester) async {
        await _usePhoneViewport(tester);
        final gateway = _PollingAvailabilityGateway();
        final repository = _FakeStudentQrRepository(
          challenge: _challenge(requiresPin: true, pinConfigured: false),
        );
        await _pumpPage(
          tester,
          repository: repository,
          availabilityGateway: gateway,
        );
        if (confirming) {
          await tester.tap(find.byKey(const ValueKey('emitStudentQrValue')));
          await tester.pumpAndSettle();
          await tester.enterText(
            _textFieldInside(const ValueKey('studentQrPinField')),
            '24',
          );
          await tester.pump();
        }
        final stableFinder = confirming
            ? find.descendant(
                of: find.byKey(const ValueKey('studentQrPinField')),
                matching: find.byType(EditableText),
              )
            : find.byKey(const ValueKey('emitStudentQrValue'));
        final originalElement = tester.element(stableFinder);
        final container = ProviderScope.containerOf(
          tester.element(find.byType(StudentAccessQrPage)),
        );
        final courseProvider = currentLearningAvailabilityProvider(
          _primaryChild.id,
        );
        final subscription = container.listen(courseProvider, (_, _) {});
        addTearDown(subscription.close);
        await container.read(courseProvider.future);
        for (var cycle = 0; cycle < 5; cycle++) {
          final pending = Completer<LearningAvailability>();
          gateway.pending = pending;
          final refresh = container.refresh(courseProvider.future);
          await tester.pump(const Duration(milliseconds: 100));
          expect(
            stableFinder,
            findsOneWidget,
            reason: 'course refresh must not unmount the login flow',
          );
          expect(tester.element(stableFinder), same(originalElement));
          if (confirming) {
            final input = tester.widget<EditableText>(stableFinder);
            expect(input.controller.text, '24');
            expect(input.focusNode.hasFocus, isTrue);
          }
          gateway.pending = null;
          pending.complete(
            _availability(hasActiveRelease: false, canAccessWorkspace: true),
          );
          await refresh;
          await tester.pump(const Duration(milliseconds: 100));
          expect(tester.element(stableFinder), same(originalElement));
        }
        if (confirming) {
          await tester.enterText(
            _textFieldInside(const ValueKey('studentQrPinField')),
            '2468',
          );
          await tester.enterText(
            _textFieldInside(const ValueKey('studentQrPinConfirmField')),
            '2468',
          );
          await tester.pump();
          await tester.tap(
            find.byKey(const ValueKey('approveStudentQrChallenge')),
          );
          await tester.pumpAndSettle();
          expect(repository.approvedPin, '2468');
          expect(repository.previewCalls, 1);
        }
      },
    );
  }

  testWidgets('rejects a QR code outside the configured student web origin', (
    tester,
  ) async {
    await _usePhoneViewport(tester);
    final repository = _FakeStudentQrRepository(
      challenge: _challenge(requiresPin: true, pinConfigured: false),
    );
    await _pumpPage(
      tester,
      repository: repository,
      scanValue:
          'https://student.example.test.evil.test/pair/qr?challengeId=msc_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcd',
    );

    await tester.tap(find.byKey(const ValueKey('emitStudentQrValue')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('studentQrFailurePage')), findsOneWidget);
    expect(find.text('这不是有效的学习网页二维码'), findsOneWidget);
    expect(repository.previewCalls, 0);
  });

  testWidgets('previews the device and requires a confirmed PIN on first use', (
    tester,
  ) async {
    await _usePhoneViewport(tester);
    final repository = _FakeStudentQrRepository(
      challenge: _challenge(requiresPin: true, pinConfigured: false),
    );
    await _pumpPage(tester, repository: repository);

    await tester.tap(find.byKey(const ValueKey('emitStudentQrValue')));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('studentQrConfirmationPage')),
      findsOneWidget,
    );
    expect(find.text('Chrome 浏览器'), findsOneWidget);
    expect(find.text('macOS 15.0'), findsOneWidget);
    expect(find.text('3  8  1  6'), findsOneWidget);
    expect(find.text('乐乐 · 一年级'), findsOneWidget);
    expect(_approveButton(tester).onTap, isNull);

    await tester.enterText(
      _textFieldInside(const ValueKey('studentQrPinField')),
      '2468',
    );
    await tester.enterText(
      _textFieldInside(const ValueKey('studentQrPinConfirmField')),
      '2468',
    );
    await tester.pump();
    expect(_approveButton(tester).onTap, isNotNull);

    await tester.tap(find.byKey(const ValueKey('approveStudentQrChallenge')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('studentQrSuccessPage')), findsOneWidget);
    expect(repository.approvedChildId, 'child-primary');
    expect(repository.approvedPin, '2468');
    expect(tester.takeException(), isNull);
  });

  testWidgets('an existing PIN can be left blank and is not reset', (
    tester,
  ) async {
    await _usePhoneViewport(tester);
    final repository = _FakeStudentQrRepository(
      challenge: _challenge(requiresPin: false, pinConfigured: true),
    );
    await _pumpPage(tester, repository: repository);

    await tester.tap(find.byKey(const ValueKey('emitStudentQrValue')));
    await tester.pumpAndSettle();

    expect(find.text('学习 PIN（可选）'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('studentQrPinConfirmField')),
      findsNothing,
    );
    expect(_approveButton(tester).onTap, isNotNull);

    await tester.tap(find.byKey(const ValueKey('approveStudentQrChallenge')));
    await tester.pumpAndSettle();

    expect(repository.approvedPin, '');
    expect(find.byKey(const ValueKey('studentQrSuccessPage')), findsOneWidget);
  });

  testWidgets('a kindergarten family gets an explicit eligibility state', (
    tester,
  ) async {
    await _usePhoneViewport(tester);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          profileSummaryProvider.overrideWith(
            (ref) async => _profile(child: _kindergartenChild),
          ),
          appEnvironmentProvider.overrideWithValue(_environment),
        ],
        child: const MaterialApp(home: StudentAccessQrPage()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('当前年级暂不支持扫码登录'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('studentQrScannerViewport')),
      findsNothing,
    );
  });

  testWidgets('an unopened primary grade cannot reach the QR scanner', (
    tester,
  ) async {
    await _usePhoneViewport(tester);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          profileSummaryProvider.overrideWith(
            (ref) async => _profile(child: _primaryTwoChild),
          ),
          studentAccessAvailabilityProvider.overrideWith(
            (ref, childId) async =>
                _availability(gradeCode: 'primary_2', hasActiveRelease: false),
          ),
          appEnvironmentProvider.overrideWithValue(_environment),
        ],
        child: const MaterialApp(home: StudentAccessQrPage()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('当前暂不能登录学习空间'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('studentQrScannerViewport')),
      findsNothing,
    );
  });

  testWidgets(
    'direct QR route does not build a scanner without workspace permission',
    (tester) async {
      await _usePhoneViewport(tester);
      var scannerBuilds = 0;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            profileSummaryProvider.overrideWith(
              (ref) async => _profile(child: _primaryChild),
            ),
            studentAccessAvailabilityProvider.overrideWith(
              (ref, childId) async => _availability(hasActiveRelease: false),
            ),
            appEnvironmentProvider.overrideWithValue(_environment),
          ],
          child: MaterialApp(
            home: StudentAccessQrPage(
              scannerBuilder: (_, _) {
                scannerBuilds += 1;
                return const SizedBox(key: ValueKey('forbiddenScanner'));
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('当前暂不能登录学习空间'), findsOneWidget);
      expect(find.byKey(const ValueKey('studentQrScannerPage')), findsNothing);
      expect(find.byKey(const ValueKey('forbiddenScanner')), findsNothing);
      expect(scannerBuilds, 0);
    },
  );

  testWidgets(
    'direct QR route reports availability errors without enabling scanning',
    (tester) async {
      await _usePhoneViewport(tester);
      var scannerBuilds = 0;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            profileSummaryProvider.overrideWith(
              (ref) async => _profile(child: _primaryChild),
            ),
            studentAccessAvailabilityProvider.overrideWith(
              (ref, childId) async => throw StateError('offline'),
            ),
            appEnvironmentProvider.overrideWithValue(_environment),
          ],
          child: MaterialApp(
            home: StudentAccessQrPage(
              scannerBuilder: (_, _) {
                scannerBuilds += 1;
                return const SizedBox(key: ValueKey('forbiddenScanner'));
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('学习空间权限暂时无法同步'), findsOneWidget);
      expect(find.byKey(const ValueKey('studentQrScannerPage')), findsNothing);
      expect(find.byKey(const ValueKey('forbiddenScanner')), findsNothing);
      expect(scannerBuilds, 0);
    },
  );
}

Future<void> _pumpPage(
  WidgetTester tester, {
  required StudentAccessRepository repository,
  LearningAvailabilityGateway? availabilityGateway,
  String scanValue =
      'https://student.example.test/pair/qr?challengeId=msc_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcd',
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        profileSummaryProvider.overrideWith(
          (ref) async => _profile(child: _primaryChild),
        ),
        learningAvailabilityRepositoryProvider.overrideWithValue(
          availabilityGateway ?? _PollingAvailabilityGateway(),
        ),
        appEnvironmentProvider.overrideWithValue(_environment),
        studentAccessRepositoryProvider.overrideWithValue(repository),
      ],
      child: MaterialApp(
        home: StudentAccessQrPage(
          scannerBuilder: (_, onDetected) => ColoredBox(
            color: Colors.black,
            child: Center(
              child: TextButton(
                key: const ValueKey('emitStudentQrValue'),
                onPressed: () => onDetected(scanValue),
                child: const Text('模拟扫码'),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Finder _textFieldInside(ValueKey<String> key) {
  return find.descendant(of: find.byKey(key), matching: find.byType(TextField));
}

AppPrimaryButton _approveButton(WidgetTester tester) {
  return tester.widget<AppPrimaryButton>(
    find.byKey(const ValueKey('approveStudentQrChallenge')),
  );
}

Future<void> _usePhoneViewport(WidgetTester tester) async {
  await tester.binding.setSurfaceSize(const Size(390, 844));
  addTearDown(() => tester.binding.setSurfaceSize(null));
}

StudentQrChallenge _challenge({
  required bool requiresPin,
  required bool pinConfigured,
}) {
  final now = DateTime.now();
  return StudentQrChallenge(
    id: 'msc_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcd',
    status: 'pending',
    displayCode: '3816',
    requestedAt: now.subtract(const Duration(seconds: 10)),
    expiresAt: now.add(const Duration(minutes: 5)),
    requiresPin: requiresPin,
    pinConfigured: pinConfigured,
    clientDevice: const StudentQrClientDevice(
      label: 'Chrome 浏览器',
      browser: 'Chrome 浏览器',
      platform: 'macOS',
      osVersion: '15.0',
      osName: 'macOS',
    ),
  );
}

ProfileSummary _profile({required ChildProfile child}) {
  return ProfileSummary(
    spaceTitle: '乐乐家',
    familyId: 'family-1',
    familyName: '乐乐家',
    displayName: '妈妈',
    phone: '13800000000',
    relationship: '妈妈',
    relationshipKey: 'mom',
    role: 'admin',
    roleLabel: '管理员',
    capabilities: const ['manage_child_profile'],
    avatarPersona: '',
    memberCount: 2,
    deviceCount: 1,
    pendingItemCount: 0,
    child: child,
  );
}

final _environment = AppEnvironment(
  flavor: AppFlavor.test,
  apiBaseUrl: 'https://api.example.test/api',
  taskWebSocketBaseUrl: 'wss://api.example.test/api',
  studentWebBaseUrl: 'https://student.example.test',
);

final _primaryChild = ChildProfile.fromJson({
  'id': 'child-primary',
  'name': '乐乐',
  'nickname': '乐乐',
  'educationStage': '小学',
  'grade': '一年级',
  'gradeCode': 'primary_1',
});

final _primaryTwoChild = ChildProfile.fromJson({
  'id': 'child-primary-two',
  'name': '安安',
  'nickname': '安安',
  'educationStage': '小学',
  'grade': '二年级',
  'gradeCode': 'primary_2',
  'contentMode': 'primary_learning',
});

final _kindergartenChild = ChildProfile.fromJson({
  'id': 'child-kindergarten',
  'name': '安安',
  'nickname': '安安',
  'educationStage': '幼儿园',
  'grade': '中班',
  'gradeCode': 'kindergarten_middle',
});

LearningAvailability _availability({
  bool? canAccessWorkspace,
  String gradeCode = 'primary_1',
  bool hasActiveRelease = true,
  int? availableCourseCount,
}) {
  final count = availableCourseCount ?? (hasActiveRelease ? 30 : 0);
  return LearningAvailability(
    gradeCode: gradeCode,
    hasActiveRelease: hasActiveRelease,
    availableCourseCount: count,
    canLearnNow: hasActiveRelease || count > 0,
    canAccessWorkspace: canAccessWorkspace ?? (hasActiveRelease || count > 0),
  );
}

class _FakeStudentQrRepository extends StudentAccessRepository {
  _FakeStudentQrRepository({required this.challenge})
    : super(
        apiClient: ApiClient(Dio(BaseOptions(baseUrl: 'https://unused.test'))),
      );

  final StudentQrChallenge challenge;
  var previewCalls = 0;
  String? approvedChildId;
  String? approvedPin;

  @override
  Future<StudentQrChallenge> getQrChallenge({
    required String challengeId,
    required String childId,
  }) async {
    previewCalls++;
    expect(challengeId, challenge.id);
    expect(childId, 'child-primary');
    return challenge;
  }

  @override
  Future<StudentQrApproval> approveQrChallenge({
    required String challengeId,
    required String childId,
    String? pin,
  }) async {
    approvedChildId = childId;
    approvedPin = pin;
    return StudentQrApproval(
      challengeId: challengeId,
      status: 'approved',
      message: '已授权',
      approvalExpiresAt: DateTime.now().add(const Duration(seconds: 60)),
    );
  }
}

class _PollingAvailabilityGateway implements LearningAvailabilityGateway {
  Completer<LearningAvailability>? pending;

  @override
  Future<LearningAvailability> current(String childId) async {
    return pending != null
        ? pending!.future
        : _availability(hasActiveRelease: false, canAccessWorkspace: true);
  }
}
