import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/learning/application/learning_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_models.dart';
import 'package:warm_sight/src/features/student_access/application/student_access_repository.dart';
import 'package:warm_sight/src/features/student_access/domain/student_access_models.dart';
import 'package:warm_sight/src/features/student_access/presentation/student_access_management_panel.dart';

void main() {
  testWidgets(
    'management panel exposes lazy loading then real device and report data',
    (tester) async {
      await _usePhoneViewport(tester);
      final authorizations = Completer<StudentAuthorizationList>();
      final reports = Completer<LearningReportPage>();
      await _pumpPanel(
        tester,
        student: _FakeStudentAccessRepository(
          onList: (_) => authorizations.future,
        ),
        reports: _FakeReportsGateway(onList: (_) => reports.future),
      );

      expect(find.text('设备授权与学习报告'), findsOneWidget);
      expect(find.text('客厅学习平板'), findsNothing);
      await tester.tap(
        find.byKey(const ValueKey('openStudentAccessManagement')),
      );
      await tester.pump();
      expect(
        find.byKey(const ValueKey('studentAccessManagementLoading')),
        findsOneWidget,
      );

      authorizations.complete(_authorizationList());
      reports.complete(_reportPage());
      await tester.pumpAndSettle();

      expect(find.text('客厅学习平板'), findsOneWidget);
      expect(find.text('1 个有效会话'), findsOneWidget);
      expect(find.text('20 以内加减法'), findsOneWidget);
      expect(find.text('已掌握'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('management panel renders empty and retryable error states', (
    tester,
  ) async {
    await _usePhoneViewport(tester);
    var attempts = 0;
    final student = _FakeStudentAccessRepository(
      onList: (_) async {
        attempts += 1;
        if (attempts == 1) {
          throw const StudentAccessException('网络暂时不可用');
        }
        return const StudentAuthorizationList(childId: 'child-1', items: []);
      },
    );
    final reports = _FakeReportsGateway(
      onList: (_) async => const LearningReportPage(
        childId: 'child-1',
        items: [],
        nextCursor: null,
      ),
    );
    await _pumpPanel(tester, student: student, reports: reports);

    await tester.tap(find.byKey(const ValueKey('openStudentAccessManagement')));
    await tester.pumpAndSettle();
    expect(find.text('网络暂时不可用'), findsOneWidget);

    await tester.tap(
      find.byKey(const ValueKey('retryStudentAccessManagement')),
    );
    await tester.pumpAndSettle();
    expect(find.text('还没有已授权设备'), findsOneWidget);
    expect(find.text('还没有学习报告'), findsOneWidget);
    expect(find.byKey(const ValueKey('resetStudentPin')), findsOneWidget);
  });

  testWidgets('revoke requires confirmation and removes the authorization', (
    tester,
  ) async {
    await _usePhoneViewport(tester);
    var revokeCalls = 0;
    final student = _FakeStudentAccessRepository(
      onList: (_) async => _authorizationList(),
      onRevoke: ({required childId, required authorizationId}) async {
        revokeCalls += 1;
        return StudentAuthorizationRevocation(
          authorizationId: authorizationId,
          status: 'revoked',
          alreadyRevoked: false,
          revokedSessionCount: 1,
          revokedAt: DateTime(2026, 8, 25, 12),
        );
      },
    );
    await _pumpPanel(
      tester,
      student: student,
      reports: _FakeReportsGateway(onList: (_) async => _reportPage()),
    );
    await tester.tap(find.byKey(const ValueKey('openStudentAccessManagement')));
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const ValueKey('revokeStudentAuthorization-device-1')),
    );
    await tester.pumpAndSettle();
    expect(find.text('撤销这台设备的学习授权？'), findsOneWidget);
    expect(revokeCalls, 0);
    await tester.tap(
      find.byKey(const ValueKey('confirmRevokeStudentAuthorization')),
    );
    await tester.pumpAndSettle();

    expect(revokeCalls, 1);
    expect(find.text('客厅学习平板'), findsNothing);
    expect(find.text('还没有已授权设备'), findsOneWidget);
  });

  testWidgets('PIN reset never echoes PIN and explains session invalidation', (
    tester,
  ) async {
    await _usePhoneViewport(tester);
    String? submittedPin;
    final student = _FakeStudentAccessRepository(
      onList: (_) async => _authorizationList(),
      onReset: ({required childId, required pin}) async {
        submittedPin = pin;
        return StudentPinResetResult(
          childId: childId,
          updatedAt: DateTime(2026, 8, 25, 12),
          revokedSessionCount: 1,
          trustedDeviceCount: 1,
          existingDevicesRemainTrusted: true,
          requiresUnlockWithNewPin: true,
        );
      },
    );
    await _pumpPanel(
      tester,
      student: student,
      reports: _FakeReportsGateway(onList: (_) async => _reportPage()),
    );
    await tester.tap(find.byKey(const ValueKey('openStudentAccessManagement')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('resetStudentPin')));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.descendant(
        of: find.byKey(const ValueKey('studentPinResetField')),
        matching: find.byType(TextField),
      ),
      '2468',
    );
    await tester.enterText(
      find.descendant(
        of: find.byKey(const ValueKey('studentPinResetConfirmField')),
        matching: find.byType(TextField),
      ),
      '2468',
    );
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('confirmStudentPinReset')));
    await tester.pumpAndSettle();

    expect(submittedPin, '2468');
    expect(
      find.byKey(const ValueKey('studentPinResetSuccess')),
      findsOneWidget,
    );
    expect(find.textContaining('现有会话已退出'), findsOneWidget);
    expect(find.text('2468'), findsNothing);
  });

  testWidgets(
    'report card opens owned report detail with loading and evidence',
    (tester) async {
      await _usePhoneViewport(tester);
      final detail = Completer<LearningReport>();
      final gateway = _FakeReportsGateway(
        onList: (_) async => _reportPage(),
        onDetail: ({required childId, required reportId}) => detail.future,
      );
      await _pumpPanel(
        tester,
        student: _FakeStudentAccessRepository(
          onList: (_) async => _authorizationList(),
        ),
        reports: gateway,
      );
      await tester.tap(
        find.byKey(const ValueKey('openStudentAccessManagement')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('learningReport-report-1')));
      await tester.pump();
      expect(
        find.byKey(const ValueKey('learningReportDetailLoading')),
        findsOneWidget,
      );

      detail.complete(_reportPage().items.single);
      await tester.pumpAndSettle();
      expect(find.text('学习报告详情'), findsOneWidget);
      expect(find.text('计算准确'), findsOneWidget);
      expect(find.text('继续下一能力点。'), findsOneWidget);
    },
  );
}

Future<void> _pumpPanel(
  WidgetTester tester, {
  required StudentAccessRepository student,
  required ParentLearningReportsGateway reports,
}) {
  return tester.pumpWidget(
    ProviderScope(
      overrides: [
        studentAccessRepositoryProvider.overrideWithValue(student),
        parentLearningReportsRepositoryProvider.overrideWithValue(reports),
      ],
      child: const MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: Padding(
              padding: EdgeInsets.all(16),
              child: StudentAccessManagementPanel(childId: 'child-1'),
            ),
          ),
        ),
      ),
    ),
  );
}

Future<void> _usePhoneViewport(WidgetTester tester) async {
  await tester.binding.setSurfaceSize(const Size(390, 844));
  addTearDown(() => tester.binding.setSurfaceSize(null));
}

StudentAuthorizationList _authorizationList() {
  final now = DateTime(2026, 8, 25, 12);
  return StudentAuthorizationList(
    childId: 'child-1',
    items: [
      StudentAuthorization(
        id: 'device-1',
        displayName: '客厅学习平板',
        deviceType: 'tablet',
        platform: 'android',
        status: 'active',
        trustedUntil: now.add(const Duration(days: 30)),
        lastUsedAt: now,
        createdAt: now.subtract(const Duration(days: 5)),
        sessions: [
          StudentAuthorizationSession(
            id: 'session-1',
            status: 'active',
            lastUsedAt: now,
            createdAt: now.subtract(const Duration(hours: 1)),
          ),
        ],
      ),
    ],
  );
}

LearningReportPage _reportPage() {
  return const LearningReportPage(
    childId: 'child-1',
    nextCursor: null,
    items: [
      LearningReport(
        id: 'report-1',
        childId: 'child-1',
        sessionId: 'session-1',
        courseTitle: '20 以内加减法',
        learningDate: '2026-08-25',
        subject: '数学',
        subjectCode: 'math',
        score: 100,
        summary: '独立检查全部正确。',
        totalQuestions: 4,
        correctCount: 4,
        independentCorrectCount: 2,
        hintCount: 0,
        masteryLabel: 'mastered',
        nextSuggestion: '继续下一能力点。',
        strengths: ['计算准确'],
      ),
    ],
  );
}

typedef _ListAuthorizations =
    Future<StudentAuthorizationList> Function(String childId);
typedef _RevokeAuthorization =
    Future<StudentAuthorizationRevocation> Function({
      required String childId,
      required String authorizationId,
    });
typedef _ResetPin =
    Future<StudentPinResetResult> Function({
      required String childId,
      required String pin,
    });

class _FakeStudentAccessRepository extends StudentAccessRepository {
  _FakeStudentAccessRepository({
    required this.onList,
    this.onRevoke,
    this.onReset,
  }) : super(
         apiClient: ApiClient(Dio(BaseOptions(baseUrl: 'https://unused.test'))),
       );

  final _ListAuthorizations onList;
  final _RevokeAuthorization? onRevoke;
  final _ResetPin? onReset;

  @override
  Future<StudentAuthorizationList> listAuthorizations(String childId) =>
      onList(childId);

  @override
  Future<StudentAuthorizationRevocation> revokeAuthorization({
    required String childId,
    required String authorizationId,
  }) => onRevoke!(childId: childId, authorizationId: authorizationId);

  @override
  Future<StudentPinResetResult> resetPin({
    required String childId,
    required String pin,
  }) => onReset!(childId: childId, pin: pin);
}

typedef _ListReports = Future<LearningReportPage> Function(String? cursor);
typedef _ReportDetail =
    Future<LearningReport> Function({
      required String childId,
      required String reportId,
    });

class _FakeReportsGateway implements ParentLearningReportsGateway {
  _FakeReportsGateway({required this.onList, this.onDetail});

  final _ListReports onList;
  final _ReportDetail? onDetail;

  @override
  Future<LearningReportPage> reports({
    required String childId,
    String? subject,
    String? cursor,
    int limit = 20,
  }) => onList(cursor);

  @override
  Future<LearningReport> reportDetail({
    required String childId,
    required String reportId,
  }) => onDetail!(childId: childId, reportId: reportId);
}
