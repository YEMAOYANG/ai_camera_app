import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/app/realtime/app_realtime_helpers.dart';
import 'package:warm_sight/src/features/care/application/care_repository.dart';
import 'package:warm_sight/src/features/devices/application/device_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_preparation_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_repository.dart';
import 'package:warm_sight/src/features/learning/application/textbook_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_availability_models.dart';
import 'package:warm_sight/src/features/live_care/application/camera_repository.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/rewards/application/reward_repository.dart';
import 'package:warm_sight/src/features/student_access/application/student_access_availability.dart';
import 'package:warm_sight/src/features/tasks/application/task_repository.dart';
import 'support/fixed_textbook_fixtures.dart';

void main() {
  test(
    'concurrent refresh shares one current-profile, textbook and access read',
    () async {
      var profiles = 0, catalogs = 0, access = 0, legacy = 0;
      final container = ProviderContainer(
        overrides: [
          profileSummaryProvider.overrideWith((ref) async {
            profiles++;
            return _profile;
          }),
          schoolTextbooksProvider.overrideWith((ref, id) async {
            catalogs++;
            expect(id, _child.id);
            return fixtureCatalog();
          }),
          studentAccessAvailabilityProvider.overrideWith((ref, scope) async {
            access++;
            expect(scope.childId, _child.id);
            return _access;
          }),
          currentLearningPreparationProvider.overrideWith((ref, id) async {
            legacy++;
            throw StateError('legacy');
          }),
          todayLearningProvider.overrideWith((ref, id) async {
            legacy++;
            throw StateError('legacy');
          }),
          ..._quietHomeOverrides(),
        ],
      );
      addTearDown(container.dispose);
      await Future.wait([
        refreshHomeDataSilently(container),
        refreshHomeDataSilently(container),
        refreshHomeDataSilently(container),
      ]);
      expect([profiles, catalogs, access, legacy], [1, 1, 1, 0]);
    },
  );

  test(
    'failed fresh profile prevents reading stale child catalogs or permissions',
    () async {
      var calls = 0;
      final container = ProviderContainer(
        overrides: [
          profileSummaryProvider.overrideWith(
            (ref) async => throw StateError('offline'),
          ),
          schoolTextbooksProvider.overrideWith((ref, id) async {
            calls++;
            return fixtureCatalog();
          }),
          studentAccessAvailabilityProvider.overrideWith((ref, scope) async {
            calls++;
            return _access;
          }),
          ..._quietHomeOverrides(),
        ],
      );
      addTearDown(container.dispose);
      await refreshHomeDataSilently(container);
      expect(calls, 0);
    },
  );

  test(
    'slow profile refresh does not issue requests for the old child',
    () async {
      final pending = Completer<ProfileSummary>();
      var calls = 0;
      final container = ProviderContainer(
        overrides: [
          profileSummaryProvider.overrideWith((ref) => pending.future),
          schoolTextbooksProvider.overrideWith((ref, id) async {
            calls++;
            return fixtureCatalog();
          }),
          studentAccessAvailabilityProvider.overrideWith(
            (ref, scope) async => _access,
          ),
          ..._quietHomeOverrides(),
        ],
      );
      addTearDown(container.dispose);
      final operation = refreshHomeDataSilently(container);
      await Future<void>.delayed(Duration.zero);
      expect(calls, 0);
      pending.complete(_profile);
      await operation;
      expect(calls, 1);
    },
  );

  test(
    'a failed textbook read does not prevent access refresh or later retry',
    () async {
      var catalogs = 0, access = 0;
      final container = ProviderContainer(
        overrides: [
          profileSummaryProvider.overrideWith((ref) async => _profile),
          schoolTextbooksProvider.overrideWith((ref, id) async {
            if (++catalogs == 1) throw StateError('offline');
            return fixtureCatalog();
          }),
          studentAccessAvailabilityProvider.overrideWith((ref, scope) async {
            access++;
            return _access;
          }),
          ..._quietHomeOverrides(),
        ],
      );
      addTearDown(container.dispose);
      await refreshHomeDataSilently(container);
      await refreshHomeDataSilently(container);
      expect([catalogs, access], [2, 2]);
    },
  );
}

const _access = LearningAvailability(
  gradeCode: 'primary_1',
  hasActiveRelease: false,
  availableCourseCount: 0,
  canLearnNow: false,
  canAccessWorkspace: true,
);

dynamic _quietHomeOverrides() => [
  primaryDeviceOverviewProvider.overrideWith(
    (ref) async => throw StateError('quiet'),
  ),
  todayTasksProvider.overrideWith((ref) async => throw StateError('quiet')),
  rewardRedemptionsProvider.overrideWith(
    (ref) async => throw StateError('quiet'),
  ),
  cameraHealthProvider.overrideWith((ref) async => throw StateError('quiet')),
  cameraStatusProvider.overrideWith((ref) async => throw StateError('quiet')),
  cameraMonitorStatusProvider.overrideWith(
    (ref) async => throw StateError('quiet'),
  ),
  careSummaryProvider.overrideWith(
    (ref, childId) async => throw StateError('quiet'),
  ),
];

const _child = ChildProfile(
  id: 'child-1',
  name: '乐乐',
  nickname: '乐乐',
  gender: 'unspecified',
  birthday: '',
  sleepTime: '',
  ageStage: '小学 一年级',
  educationStage: '小学',
  grade: '一年级',
  gradeCode: 'primary_1',
  educationStageCode: 'primary',
  contentMode: 'primary_learning',
  schoolYearStartYear: 2026,
  schoolName: '',
  interests: [],
  taskPreferences: {},
);

const _profile = ProfileSummary(
  spaceTitle: '家庭',
  familyId: 'family-1',
  familyName: '家庭',
  displayName: '妈妈',
  phone: '13800000000',
  relationship: '妈妈',
  relationshipKey: 'mother',
  role: 'admin',
  roleLabel: '管理员',
  capabilities: [],
  avatarPersona: '',
  memberCount: 1,
  deviceCount: 0,
  pendingItemCount: 0,
  child: _child,
);
