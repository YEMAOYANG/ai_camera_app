import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/auth/application/session_data_invalidation.dart';
import 'package:warm_sight/src/features/learning/application/learning_preparation_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_preparation_models.dart';
import 'package:warm_sight/src/features/points/application/point_settings.dart';

final _invalidateSessionProvider = Provider<void Function()>((ref) {
  return () => invalidateAuthenticatedSessionDataFromRef(ref);
});

void main() {
  for (final delayedFirstRead in [false, true]) {
    test(
      'account switch reloads point settings ${delayedFirstRead ? 'and drops the old in-flight result' : 'instead of retaining another family cache'}',
      () async {
        final repository = _PointSettingsRepository(delayed: delayedFirstRead);
        final container = ProviderContainer(
          overrides: [
            pointRewardSettingsRepositoryProvider.overrideWithValue(repository),
          ],
        );
        addTearDown(container.dispose);
        final subscription = container.listen(
          pointRewardSettingsProvider,
          (_, _) {},
        );
        addTearDown(subscription.close);
        final firstRead = container.read(pointRewardSettingsProvider.future);
        if (!delayedFirstRead) expect((await firstRead).stageThreshold, 7);
        repository.threshold = 99;
        container.read(_invalidateSessionProvider)();
        expect(
          (await container.read(
            pointRewardSettingsProvider.future,
          )).stageThreshold,
          99,
        );
        if (delayedFirstRead) {
          repository.first.complete(_pointSettings(7));
          await firstRead;
          await container.pump();
        }
        expect(
          container
              .read(pointRewardSettingsProvider)
              .requireValue
              .stageThreshold,
          99,
        );
        expect(
          container.read(pointRewardSettingsProvider).requireValue.unitKey,
          'star',
        );
        expect(repository.calls, 2);
      },
    );
  }

  test(
    'session invalidation replaces retained preparation family state and drops stale in-flight data',
    () async {
      final householdA = _CompletingGateway();
      final householdB = _CompletingGateway();
      var activeGateway = householdA;
      final container = ProviderContainer(
        overrides: [
          learningPreparationRepositoryProvider.overrideWith(
            (ref) => activeGateway,
          ),
        ],
      );
      addTearDown(container.dispose);

      final observed = <AsyncValue<LearningPreparation?>>[];
      final subscription = container.listen(
        currentLearningPreparationProvider('same-child-id'),
        (_, next) => observed.add(next),
        fireImmediately: true,
      );
      addTearDown(subscription.close);
      final householdAFuture = container.read(
        currentLearningPreparationProvider('same-child-id').future,
      );

      activeGateway = householdB;
      container.read(_invalidateSessionProvider)();
      await container.pump();
      householdB.complete(_preparation(id: 'household-b-plan'));
      final current = await container.read(
        currentLearningPreparationProvider('same-child-id').future,
      );
      expect(current?.id, 'household-b-plan');

      householdA.complete(_preparation(id: 'household-a-plan'));
      expect((await householdAFuture)?.id, 'household-b-plan');
      await container.pump();

      expect(
        container
            .read(currentLearningPreparationProvider('same-child-id'))
            .requireValue
            ?.id,
        'household-b-plan',
      );
      expect(
        observed.where((value) => value.value?.id == 'household-a-plan'),
        isEmpty,
      );
      expect(householdA.requestedChildIds, ['same-child-id']);
      expect(householdB.requestedChildIds, ['same-child-id']);
    },
  );
}

class _PointSettingsRepository extends PointRewardSettingsRepository {
  _PointSettingsRepository({required this.delayed})
    : super(apiClient: ApiClient(Dio()));
  final bool delayed;
  final first = Completer<PointRewardSettings>();
  int threshold = 7;
  int calls = 0;

  @override
  Future<PointRewardSettings> fetch() async {
    calls++;
    if (calls == 1 && delayed) return first.future;
    return _pointSettings(threshold);
  }
}

PointRewardSettings _pointSettings(int threshold) {
  const star = PointRewardUnitOption(
    key: 'star',
    label: '星星',
    suffix: '颗星星',
    description: '',
    imageAsset: '',
  );
  return PointRewardSettings(
    stageThreshold: threshold,
    unit: threshold == 7 ? PointRewardUnitOption.fallback : star,
    unitOptions: [PointRewardUnitOption.fallback, star],
  );
}

class _CompletingGateway implements LearningPreparationGateway {
  final _current = Completer<LearningPreparation?>();
  final requestedChildIds = <String>[];

  void complete(LearningPreparation value) => _current.complete(value);

  @override
  Future<LearningPreparation?> current(String childId) {
    requestedChildIds.add(childId);
    return _current.future;
  }

  @override
  Future<LearningPreparation> retry({
    required String planId,
    required String requestId,
  }) {
    throw UnimplementedError();
  }
}

LearningPreparation _preparation({required String id}) {
  return LearningPreparation.fromJson({
    'schemaVersion': 'mira.learning.preparation.v1',
    'id': id,
    'childId': 'same-child-id',
    'gradeCode': 'primary_1',
    'gradeLabel': '一年级',
    'subjects': const [
      {
        'code': 'chinese',
        'label': '语文',
        'readyCourseCount': 0,
        'failedCourseCount': 0,
        'totalCourseCount': 12,
      },
      {
        'code': 'math',
        'label': '数学',
        'readyCourseCount': 0,
        'failedCourseCount': 0,
        'totalCourseCount': 9,
      },
      {
        'code': 'english',
        'label': '英语',
        'readyCourseCount': 0,
        'failedCourseCount': 0,
        'totalCourseCount': 9,
      },
    ],
    'status': 'queued',
    'stage': 'queued',
    'progressPercent': 0,
    'totalCourseCount': 30,
    'readyCourseCount': 0,
    'failedCourseCount': 0,
    'attempt': 1,
    'canRetry': false,
    'retryAfterMs': 2500,
    'message': '正在准备课程',
    'lastProgressAt': 1787200000000,
    'updatedAt': 1787200000000,
    'completedAt': null,
    'error': null,
  });
}
