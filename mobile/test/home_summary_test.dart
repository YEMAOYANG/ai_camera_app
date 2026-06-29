import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/features/care/domain/care_models.dart';
import 'package:warm_sight/src/features/devices/domain/device_models.dart';
import 'package:warm_sight/src/features/home/application/home_summary.dart';
import 'package:warm_sight/src/features/home/domain/home_models.dart';
import 'package:warm_sight/src/features/live_care/domain/camera_models.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/tasks/domain/task_models.dart';
import 'package:warm_sight/src/shared/widgets/status_chip.dart';

void main() {
  final now = DateTime(2026, 6, 23, 19, 42);

  ProfileSummary profile({
    ChildProfile? child,
    int deviceCount = 1,
    List<String> capabilities = const ['manage_tasks', 'confirm_tasks'],
  }) {
    return ProfileSummary(
      spaceTitle: '家庭看护空间',
      familyId: 'family_1',
      familyName: '测试家庭',
      displayName: '妈妈',
      phone: '13800000000',
      relationship: '妈妈',
      relationshipKey: 'mother',
      role: 'admin',
      roleLabel: '管理员',
      capabilities: capabilities,
      avatarPersona: 'mother',
      memberCount: 1,
      deviceCount: deviceCount,
      pendingItemCount: 0,
      child: child,
    );
  }

  ChildProfile child() {
    return const ChildProfile(
      id: 'child_1',
      name: '小宇',
      nickname: '小宇',
      gender: 'boy',
      birthday: '2018-01-01',
      sleepTime: '21:30',
      ageStage: '幼儿园 中班',
      educationStage: '幼儿园',
      grade: '中班',
      schoolName: '',
      interests: [],
      taskPreferences: {},
    );
  }

  GuardianTask task({
    required String id,
    required GuardianTaskStatus status,
    String scheduledStart = '19:00',
    String aiObservationSummary = '',
    int nextReminderAtMs = 0,
    List<String> parentActions = const [],
  }) {
    return GuardianTask(
      id: id,
      familyId: 'family_1',
      childId: 'child_1',
      title: '睡前阅读',
      description: '',
      type: 'reading',
      scheduleType: 'daily',
      startAt: '',
      dueAt: '',
      repeatRule: null,
      status: status,
      priority: 1,
      scheduledDate: homeDateText(now),
      scheduledStart: scheduledStart,
      scheduledEnd: '20:00',
      rewardPoints: 5,
      requiresParentConfirmation: true,
      completionSource: 'camera',
      evidence: const {},
      evidenceSummary: '',
      aiObservationSummary: aiObservationSummary,
      rejectionReason: '',
      createdBy: 'system',
      createdAt: 0,
      updatedAt: 0,
      completedAt: null,
      startedAt: null,
      endedAt: null,
      missedAt: null,
      delayedAt: null,
      lastReminderAt: null,
      nextReminderAt: nextReminderAtMs == 0 ? null : nextReminderAtMs,
      delayReminderCount: 0,
      reminderMinutesBefore: 5,
      reminderStatus: 'idle',
      cameraObservationStatus: 'observed',
      deviceId: 'device_1',
      timezone: 'Asia/Shanghai',
      confirmedAt: null,
      rejectedAt: null,
      pointsGrantedAt: null,
      parentActions: parentActions,
    );
  }

  test('generic monitor activity falls back to calm home title', () {
    final summary = buildHomeSummary(
      HomeSummaryInput(
        now: now,
        profile: profile(child: child()),
        deviceOverview: _onlineDeviceOverview(),
        cameraMonitor: const CameraMonitorStatus(
          running: true,
          status: 'observing',
          message: '观察中',
          lastObservation: '画面记录到孩子正在进行：其他',
          lastReminder: '',
        ),
        tasks: const [],
      ),
    );

    expect(summary.habitFocus.title, '还没有最近画面');
    expect(summary.habitFocus.title, isNot('今天按作息轻声提醒'));
    expect(summary.recentObservation.detail, isNot(contains('其他')));
    expect(summary.recentObservation.visible, isTrue);
    expect(summary.recentObservation.headline, '暂时没有新的画面记录');
  });

  test('monitor status does not turn generic activity into normal state', () {
    final monitor = CameraMonitorStatus.fromJson({
      'monitor': {
        'running': true,
        'status': 'observing',
        'lastObservation': {'activity': '其他', 'has_person': true},
      },
    });

    expect(monitor.lastObservation, isEmpty);
  });

  test('presence without concrete activity does not fake child status', () {
    final monitor = CameraMonitorStatus.fromJson({
      'monitor': {
        'running': true,
        'status': 'observing',
        'lastObservation': {
          'has_person': true,
          'isReliable': true,
          'confidence': 0.82,
          'observedAt': DateTime.now().millisecondsSinceEpoch,
        },
      },
    });

    final summary = buildHomeSummary(
      HomeSummaryInput(
        now: now,
        profile: profile(child: child()),
        deviceOverview: _onlineDeviceOverview(),
        cameraMonitor: monitor,
        tasks: const [],
      ),
    );

    expect(monitor.lastObservation, '画面暂时无法判断');
    expect(summary.habitFocus.title, '画面暂时无法判断');
    expect(summary.recentObservation.visible, isFalse);
  });

  test(
    'no-person observation can be shown without claiming child is present',
    () {
      final monitor = CameraMonitorStatus.fromJson({
        'monitor': {
          'running': true,
          'status': 'observing',
          'lastObservation': {
            'has_person': false,
            'isReliable': true,
            'confidence': 0.88,
            'observedAt': DateTime.now().millisecondsSinceEpoch,
          },
        },
      });

      expect(monitor.lastObservation, '暂未看到孩子');
      expect(monitor.lastObservation, isNot(contains('看到孩子在画面里')));
    },
  );

  test(
    'buildHomeSummary shows monitor observation in hero without repeating card',
    () {
      final summary = buildHomeSummary(
        HomeSummaryInput(
          now: now,
          profile: profile(child: child()),
          deviceOverview: _onlineDeviceOverview(),
          cameraStatus: CameraStatus(
            connectionStatus: 'online',
            streamAvailable: true,
            snapshotAvailable: true,
            speakerAvailable: true,
            monitorAvailable: true,
            ptzAvailable: false,
            lastSeenAt: now.millisecondsSinceEpoch,
            runtimeProvider: 'mock',
            message: '摄像头在线',
            currentTask: task(
              id: 't_current',
              status: GuardianTaskStatus.inProgress,
              aiObservationSummary: '孩子已经开始翻书。',
            ),
          ),
          cameraHealth: const CameraHealth(
            ok: true,
            reachable: true,
            adapter: 'mock',
            serviceLabel: '摄像头服务',
            message: '在线',
          ),
          cameraMonitor: CameraMonitorStatus.fromJson({
            'monitor': {
              'running': true,
              'status': 'observing',
              'message': '观察中',
              'lastObservation': {
                'summary': '孩子正在阅读绘本',
                'activity': '阅读绘本',
                'hasPerson': true,
                'isReliable': true,
                'confidence': 0.88,
                'description': '孩子坐在地垫上，手里拿着绘本，正在低头翻页。',
                'observedAt': DateTime.now().millisecondsSinceEpoch,
              },
              'lastReminder': '已提醒坐好阅读',
            },
          }),
          tasks: [task(id: 't_current', status: GuardianTaskStatus.inProgress)],
        ),
      );

      expect(summary.habitFocus.title, '孩子正在阅读绘本');
      expect(summary.habitFocus.detail, contains('手里拿着绘本'));
      expect(summary.habitFocus.title, isNot(contains('刚刚看到：')));
      expect(summary.habitFocus.title, isNot(contains('最近看到：')));
      expect(summary.primaryCta.kind, HomePrimaryCtaKind.none);
      expect(summary.showLiveCareLink, isFalse);
      expect(summary.recentObservation.visible, isFalse);
      expect(summary.recentObservation.detail, isNot('正在看绘本。'));
      expect(summary.recentObservation.detail, isNot('孩子已经开始翻书。'));
    },
  );

  test('toy observation uses short hero copy', () {
    final monitor = CameraMonitorStatus.fromJson({
      'monitor': {
        'running': true,
        'status': 'observing',
        'lastObservation': {
          'summary': '孩子正在玩玩具',
          'activity': '玩玩具',
          'hasPerson': true,
          'isReliable': true,
          'confidence': 0.9,
          'description': '孩子坐在沙发上玩玩具，周围有积木。',
          'decisionReason': '孩子仍在玩玩具，暂不催收纳。',
          'observedAt': DateTime.now().millisecondsSinceEpoch,
        },
      },
    });
    final summary = buildHomeSummary(
      HomeSummaryInput(
        now: now,
        profile: profile(child: child()),
        deviceOverview: _onlineDeviceOverview(),
        cameraMonitor: monitor,
        tasks: const [],
      ),
    );

    expect(summary.habitFocus.title, '孩子正在玩玩具');
    expect(summary.habitFocus.detail, contains('沙发上玩玩具'));
    expect(summary.habitFocus.title, isNot(contains('刚刚看到：')));
    expect(monitor.lastObservationDescription, contains('沙发上玩玩具'));
    expect(monitor.lastObservationDecisionReason, contains('暂不催收纳'));
    expect(monitor.lastObservationConfidence, 0.9);
  });

  test('negated toy description does not show toy play in hero', () {
    final monitor = CameraMonitorStatus.fromJson({
      'monitor': {
        'running': true,
        'status': 'observing',
        'lastObservation': {
          'summary': '孩子正在玩玩具',
          'activity': '玩玩具',
          'hasPerson': true,
          'isReliable': true,
          'confidence': 0.82,
          'description': '一个人趴在桌上，头部埋在双臂之间，没有看到书本、手机或玩具等物品。',
          'observedAt': DateTime.now().millisecondsSinceEpoch,
        },
      },
    });
    final summary = buildHomeSummary(
      HomeSummaryInput(
        now: now,
        profile: profile(child: child()),
        deviceOverview: _onlineDeviceOverview(),
        cameraMonitor: monitor,
        tasks: const [],
      ),
    );

    expect(summary.habitFocus.title, isNot('孩子正在玩玩具'));
    expect(summary.habitFocus.title, '画面暂时无法判断');
    expect(summary.habitFocus.detail, contains('孩子低头靠近桌面'));
    expect(summary.habitFocus.detail, isNot(contains('一个人')));
  });

  test('parent-facing observation copy removes generic person wording', () {
    final monitor = CameraMonitorStatus.fromJson({
      'monitor': {
        'running': true,
        'status': 'observing',
        'lastObservation': {
          'summary': '孩子正在写作业/看书',
          'activity': '写作业/看书',
          'hasPerson': true,
          'isReliable': true,
          'confidence': 0.88,
          'description': '一个人低头趴在桌前，头部距离桌面很近，似乎在书写或阅读，桌上有键盘、计算器和手机。',
          'observedAt': DateTime.now().millisecondsSinceEpoch,
        },
      },
    });
    final summary = buildHomeSummary(
      HomeSummaryInput(
        now: now,
        profile: profile(child: child()),
        deviceOverview: _onlineDeviceOverview(),
        cameraMonitor: monitor,
        tasks: const [],
      ),
    );

    expect(summary.habitFocus.title, '孩子正在写作业/看书');
    expect(summary.habitFocus.detail, '孩子低头靠近桌面，注意坐姿。');
    expect(summary.habitFocus.detail, isNot(contains('一个人')));
    expect(monitor.lastObservationDescription, '孩子低头靠近桌面，注意坐姿。');
  });

  test('stale negative observation falls back to pending frame copy', () {
    final monitor = CameraMonitorStatus.fromJson({
      'monitor': {
        'running': true,
        'status': 'observing',
        'lastObservation': {
          'hasPerson': false,
          'isReliable': true,
          'confidence': 0.9,
          'observedAt': now
              .subtract(const Duration(minutes: 5))
              .millisecondsSinceEpoch,
        },
      },
    });
    final summary = buildHomeSummary(
      HomeSummaryInput(
        now: now,
        profile: profile(child: child()),
        deviceOverview: _onlineDeviceOverview(),
        cameraStatus: CameraStatus(
          connectionStatus: 'online',
          streamAvailable: true,
          snapshotAvailable: true,
          speakerAvailable: true,
          monitorAvailable: true,
          ptzAvailable: false,
          lastSeenAt: now.millisecondsSinceEpoch,
          runtimeProvider: 'mock',
          message: '摄像头在线',
        ),
        cameraMonitor: monitor,
        tasks: const [],
      ),
    );

    expect(monitor.lastObservation, isEmpty);
    expect(summary.habitFocus.title, '还没有最近画面');
    expect(summary.habitFocus.title, isNot(contains('暂未看到孩子')));
  });

  test('buildRhythmNodes marks in-progress task as current', () {
    final nodes = buildRhythmNodes([
      task(
        id: 't1',
        status: GuardianTaskStatus.scheduled,
        scheduledStart: '20:00',
      ),
      task(
        id: 't2',
        status: GuardianTaskStatus.inProgress,
        scheduledStart: '19:00',
      ),
    ], now);

    expect(nodes.length, 2);
    expect(nodes[0].state, RhythmNodeState.current);
    expect(nodes[1].state, RhythmNodeState.upcoming);
  });


  test('buildPendingItems includes pending parent review from camera', () {
    final pending = buildPendingItems(
      tasks: const [],
      redemptions: const [],
      deviceIssue: false,
      parentReviews: [
        ParentReviewItem(
          id: 'rev_1',
          childId: 'child_1',
          scenario: 'parent_notify',
          reviewType: 'parent_notify',
          status: 'pending',
          summary: '孩子玩手机时间较长',
          createdAt: 1,
        ),
      ],
    );

    expect(pending.length, 1);
    expect(pending.first.action, PendingItemAction.reviewCareNotify);
    expect(pending.first.routePath, liveRoutePath);
    expect(pending.first.title, contains('玩手机'));
  });

  test('buildPrimaryCta does not create a global pending action button', () {
    final pending = buildPendingItems(
      tasks: [
        task(
          id: 'task_pending',
          status: GuardianTaskStatus.awaitingParentConfirmation,
        ),
      ],
      redemptions: const [],
      deviceIssue: false,
      canConfirmTasks: true,
    );

    final cta = buildPrimaryCta(
      hasNoDevice: false,
      deviceIssue: false,
      pendingItems: pending,
      pendingCount: pending.length,
    );

    expect(cta.kind, HomePrimaryCtaKind.none);
    expect(cta.label, isEmpty);
    expect(cta.routePath, isNull);
  });

  test('buildPendingItems excludes missed task without available action', () {
    final pending = buildPendingItems(
      tasks: [task(id: 'task_missed', status: GuardianTaskStatus.missed)],
      redemptions: const [],
      deviceIssue: false,
    );

    expect(pending, isEmpty);
  });

  test(
    'buildPendingItems includes missed task only when actions are available',
    () {
      final pending = buildPendingItems(
        tasks: [
          task(
            id: 'task_missed',
            status: GuardianTaskStatus.missed,
            parentActions: const [
              'reschedule',
              'manual_complete',
              'acknowledge_missed',
            ],
          ),
        ],
        redemptions: const [],
        deviceIssue: false,
        canManageTasks: true,
        canConfirmTasks: true,
      );

      expect(pending, hasLength(1));
      expect(pending.first.action, PendingItemAction.reviewMissedTask);
      expect(pending.first.title, '本次没有看到完成结果');
      expect(pending.first.detail, contains('重新安排'));
      expect(pending.first.routePath, '$taskDetailRoutePrefix/task_missed');
    },
  );

  test('buildRhythmNodes shows latest five tasks as a timeline', () {
    final nodes = buildRhythmNodes([
      task(
        id: 'early_cleanup',
        status: GuardianTaskStatus.completed,
        scheduledStart: '08:30',
      ).copyWith(title: '整理小书桌', scheduledEnd: '08:45'),
      task(
        id: 'morning_drink',
        status: GuardianTaskStatus.completed,
        scheduledStart: '09:54',
      ).copyWith(title: '喝水', scheduledEnd: '10:00'),
      task(
        id: 'morning_read',
        status: GuardianTaskStatus.completed,
        scheduledStart: '10:14',
      ).copyWith(title: '自己阅读一本绘本', scheduledEnd: '10:30'),
      task(
        id: 'recent_toy',
        status: GuardianTaskStatus.completed,
        scheduledStart: '14:50',
      ).copyWith(title: '玩会儿玩具', scheduledEnd: '15:10'),
      task(
        id: 'current',
        status: GuardianTaskStatus.delayed,
        scheduledStart: '15:40',
      ).copyWith(title: '整理玩具', scheduledEnd: '16:00'),
      task(
        id: 'next',
        status: GuardianTaskStatus.scheduled,
        scheduledStart: '16:20',
      ).copyWith(title: '户外活动', scheduledEnd: '16:50'),
    ], DateTime(2026, 6, 23, 15, 53));

    expect(nodes.map((node) => node.taskId), [
      'morning_drink',
      'morning_read',
      'recent_toy',
      'current',
      'next',
    ]);
    expect(nodes[3].title, '整理玩具');
    expect(nodes[3].statusLabel, '需要提醒');
  });

  test('buildRhythmNodes includes missed awaiting and cancelled tasks', () {
    final nodes = buildRhythmNodes([
      task(
        id: 'missed',
        status: GuardianTaskStatus.missed,
        scheduledStart: '15:50',
      ).copyWith(title: '未完成安排', scheduledEnd: '16:00'),
      task(
        id: 'awaiting',
        status: GuardianTaskStatus.awaitingParentConfirmation,
        scheduledStart: '15:55',
      ).copyWith(title: '待确认安排', scheduledEnd: '16:05'),
      task(
        id: 'nearest',
        status: GuardianTaskStatus.scheduled,
        scheduledStart: '16:10',
      ).copyWith(title: '亲子阅读', scheduledEnd: '16:30'),
      task(
        id: 'cancelled',
        status: GuardianTaskStatus.cancelled,
        scheduledStart: '16:40',
      ).copyWith(title: '取消的安排', scheduledEnd: '16:50'),
    ], DateTime(2026, 6, 23, 15, 53));

    expect(nodes.map((node) => node.taskId), [
      'missed',
      'awaiting',
      'nearest',
      'cancelled',
    ]);
    expect(nodes.first.statusLabel, '未完成');
    expect(nodes.first.tone, StatusTone.danger);
    expect(nodes[1].statusLabel, '待确认');
    expect(nodes[1].tone, StatusTone.warning);
    expect(nodes.last.statusLabel, '已取消');
    expect(nodes.last.tone, StatusTone.neutral);
  });

  test('buildPrimaryCta does not duplicate no-device camera entry', () {
    final cta = buildPrimaryCta(
      hasNoDevice: true,
      deviceIssue: false,
      pendingItems: const [],
      pendingCount: 0,
    );

    expect(cta.kind, HomePrimaryCtaKind.none);
    expect(cta.label, isEmpty);
  });

  test('nextStepCountdown formats minutes until next reminder', () {
    final inTwelveMinutes = now.add(const Duration(minutes: 12));
    final countdown = nextStepCountdown(
      task(
        id: 't1',
        status: GuardianTaskStatus.inProgress,
        nextReminderAtMs: inTwelveMinutes.millisecondsSinceEpoch,
      ),
      now,
    );

    expect(countdown, '约 12 分钟后进入下一步');
  });

  test('buildRecentObservationCopy shows a light empty care overview', () {
    final copy = buildRecentObservationCopy(
      input: HomeSummaryInput(now: now),
      hasNoDevice: false,
      deviceIssue: false,
      heroObservation: null,
      currentTask: null,
      localTasks: const [],
      pendingCount: 2,
      isLoading: false,
    );

    expect(copy.visible, isTrue);
    expect(copy.showActions, isTrue);
    expect(copy.headline, '暂时没有新的画面记录');
    expect(copy.detail, contains('刷新观察'));
  });

  test('buildRecentObservationCopy falls back to recent event record', () {
    final copy = buildRecentObservationCopy(
      input: HomeSummaryInput(
        now: now,
        cameraMonitor: const CameraMonitorStatus(
          running: true,
          status: 'observing',
          message: '观察中',
          lastObservation: '旧观察',
          lastReminder: '',
        ),
      ),
      hasNoDevice: false,
      deviceIssue: false,
      heroObservation: null,
      currentTask: null,
      localTasks: const [],
      pendingCount: 0,
      isLoading: false,
      recentEvent: LiveCareEvent(
        id: 'evt_1',
        source: 'camera_observation',
        eventType: 'camera_observation',
        title: '玩玩具',
        message: '孩子在玩玩具。',
        displayTitle: '玩玩具',
        displayMessage: '孩子在玩玩具。',
        category: 'camera_observation',
        severity: 'info',
        taskTitle: '',
        evidenceSummary: '',
        hasReplay: false,
        status: 'ok',
        toneKey: 'info',
        createdAt: 1,
      ),
    );

    expect(copy.headline, '最近记录');
    expect(copy.detail, contains('玩玩具'));
  });

  test(
    'home summary switches to review mode when only completed tasks remain',
    () {
      final completedTasks = [
        task(
          id: 'morning_read',
          status: GuardianTaskStatus.completed,
          scheduledStart: '10:14',
        ).copyWith(title: '自己阅读一本绘本', scheduledEnd: '10:30'),
        task(
          id: 'recent_toy',
          status: GuardianTaskStatus.completed,
          scheduledStart: '14:50',
        ).copyWith(title: '玩会儿玩具', scheduledEnd: '15:10'),
      ];
      final nodes = buildRhythmNodes(
        completedTasks,
        DateTime(2026, 6, 23, 15, 53),
      );

      expect(resolveRhythmMode(const [], const []), HomeRhythmMode.empty);
      expect(resolveRhythmMode(completedTasks, nodes), HomeRhythmMode.review);
    },
  );

  test('home summary copy avoids brand and realtime wording', () {
    final summary = buildHomeSummary(
      HomeSummaryInput(
        now: now,
        profile: profile(child: child()),
        deviceOverview: _onlineDeviceOverview(),
        cameraMonitor: const CameraMonitorStatus(
          running: true,
          status: 'observing',
          message: '观察中',
          lastObservation: '饭后收好餐具。',
          lastReminder: '',
        ),
        tasks: [task(id: 't1', status: GuardianTaskStatus.scheduled)],
      ),
    );
    final visibleCopy = [
      summary.habitFocus.title,
      summary.habitFocus.detail,
      summary.recentObservation.headline,
      summary.recentObservation.detail,
      ...summary.habitFocus.chips.map((chip) => chip.label),
    ].join(' ');

    expect(visibleCopy, isNot(contains('\u7c73\u62c9')));
    expect(visibleCopy, isNot(contains('实时观察')));
    expect(visibleCopy, isNot(contains('实时同步')));
  });

  test('home hero time avoids exact minutes', () {
    expect(homeHeaderTimeText(DateTime(2026, 6, 24, 10, 7)), '今天上午');
    expect(homeHeaderTimeText(DateTime(2026, 6, 24, 19, 42)), '今天晚上');
    expect(
      homeHeaderTimeText(DateTime(2026, 6, 24, 10, 7)),
      isNot(contains(':')),
    );
  });

  test(
    'hero title prioritizes pending over recently completed rhythm tasks',
    () {
      final afternoon = DateTime(2026, 6, 24, 16, 28);
      final today = homeDateText(afternoon);
      final tasks = [
        task(
          id: 'toy',
          status: GuardianTaskStatus.completed,
          scheduledStart: '14:50',
        ).copyWith(
          title: '玩会儿玩具',
          scheduledDate: today,
          scheduledEnd: '15:10',
        ),
        task(
          id: 'read',
          status: GuardianTaskStatus.missed,
          scheduledStart: '10:14',
          parentActions: const [
            'reschedule',
            'manual_complete',
            'acknowledge_missed',
          ],
        ).copyWith(
          title: '自己阅读一本绘本',
          scheduledDate: today,
          scheduledEnd: '10:30',
        ),
      ];
      final pendingItems = buildPendingItems(
        tasks: tasks,
        redemptions: const [],
        deviceIssue: false,
        canManageTasks: true,
        canConfirmTasks: true,
      );

      expect(
        observationTitle(
          cameraStatus: null,
          cameraMonitor: null,
          currentTask: null,
          localTasks: tasks,
          pendingItems: pendingItems,
          childName: '小爱',
          now: afternoon,
        ),
        '有一项安排没有看到完成',
      );
      expect(
        observationDetail(
          cameraMonitor: null,
          currentTask: null,
          localTasks: tasks,
          pendingCount: pendingItems.length,
          now: afternoon,
        ),
        '1 件事等你处理，先看记录再决定。',
      );
    },
  );

  test('hero title summarizes completed day when nothing is pending', () {
    final afternoon = DateTime(2026, 6, 24, 16, 28);
    final today = homeDateText(afternoon);
    final summary = buildHomeSummary(
      HomeSummaryInput(
        now: afternoon,
        profile: profile(child: child()),
        deviceOverview: _onlineDeviceOverview(),
        cameraHealth: const CameraHealth(
          ok: true,
          reachable: true,
          adapter: 'mock',
          serviceLabel: '摄像头服务',
          message: '在线',
        ),
        cameraStatus: const CameraStatus(
          connectionStatus: 'online',
          streamAvailable: true,
          snapshotAvailable: true,
          speakerAvailable: true,
          monitorAvailable: true,
          ptzAvailable: false,
          lastSeenAt: 0,
          runtimeProvider: 'mock',
          message: '摄像头在线',
        ),
        tasks: [
          task(
            id: 'toy',
            status: GuardianTaskStatus.completed,
            scheduledStart: '14:50',
          ).copyWith(
            title: '玩会儿玩具',
            scheduledDate: today,
            scheduledEnd: '15:10',
          ),
          task(
            id: 'outdoor',
            status: GuardianTaskStatus.completed,
            scheduledStart: '10:39',
          ).copyWith(
            title: '户外运动',
            scheduledDate: today,
            scheduledEnd: '11:00',
          ),
          task(
            id: 'read',
            status: GuardianTaskStatus.completed,
            scheduledStart: '10:14',
          ).copyWith(
            title: '自己阅读一本绘本',
            scheduledDate: today,
            scheduledEnd: '10:30',
          ),
        ],
      ),
    );

    expect(summary.habitFocus.title, '今天已完成 3 项安排');
    expect(summary.habitFocus.title, isNot(contains('最近安排')));
    expect(summary.habitFocus.detail, '可以看看今天的记录，或安排下一步。');
  });

  _registerFreshnessTests(now);
}

DeviceOverview _onlineDeviceOverview() {
  return DeviceOverview(
    device: GuardianDevice(
      id: 'device_1',
      familyId: 'family_1',
      bindingCode: 'code',
      name: '客厅摄像头',
      wakeName: '小暖',
      location: '客厅',
      status: 'online',
      isDefault: true,
      createdAt: 0,
      updatedAt: 0,
      unboundAt: null,
    ),
    status: GuardianDeviceStatus(
      deviceId: 'device_1',
      connectionStatus: 'online',
      privacyMode: true,
      firmwareVersion: '1.0.0',
      networkType: 'wifi',
      networkQuality: 'good',
      snapshotSupported: true,
      streamSupported: true,
      twoWayAudioSupported: true,
      monitorSupported: true,
      otaSupported: true,
      adapter: 'mock',
      lastSeenAt: 0,
      message: '在线',
    ),
  );
}

void _registerFreshnessTests(DateTime now) {
  test('stale observation does not read as current reliable state', () {
    final observedAt = now.subtract(const Duration(minutes: 12)).millisecondsSinceEpoch;
    final monitor = CameraMonitorStatus.fromJson({
      'monitor': {
        'running': true,
        'status': 'observing',
        'lastObservation': {
          'has_person': true,
          'activity': '写字',
          'isReliable': false,
          'freshness': 'stale',
          'summary': '孩子正在写字',
          'observedAt': observedAt,
          'confidence': 0.9,
        },
      },
    });

    expect(monitor.hasCurrentReliableObservation, isFalse);
    expect(monitor.hasStaleObservation, isTrue);
    expect(
      monitor.displayObservationTitle(now: now),
      contains('分钟前观察到'),
    );
    expect(
      observationTitle(
        cameraStatus: null,
        cameraMonitor: monitor,
        currentTask: null,
        localTasks: const [],
        pendingItems: const [],
        childName: '小明',
        now: now,
      ),
      contains('分钟前观察到'),
    );
  });

  test('prefilter_only observation shows prefilter copy instead of kimi summary', () {
    final monitor = CameraMonitorStatus.fromJson({
      'monitor': {
        'running': true,
        'status': 'observing',
        'lastObservation': {
          'has_person': true,
          'freshness': 'prefilter_only',
          'observedAt': now.millisecondsSinceEpoch,
        },
      },
    });

    expect(monitor.hasCurrentReliableObservation, isFalse);
    expect(monitor.lastObservationFreshness, CameraObservationFreshness.prefilterOnly);
    expect(
      observationTitle(
        cameraStatus: null,
        cameraMonitor: monitor,
        currentTask: null,
        localTasks: const [],
        pendingItems: const [],
        childName: '小明',
        now: now,
      ),
      '画面已更新',
    );
    expect(
      observationDetail(
        cameraMonitor: monitor,
        currentTask: null,
        localTasks: const [],
        pendingCount: 0,
        now: now,
      ),
      contains('预检已更新'),
    );
  });

  test('fresh observation with explicit freshness stays current', () {
    final monitor = CameraMonitorStatus.fromJson({
      'monitor': {
        'running': true,
        'status': 'observing',
        'lastObservation': {
          'has_person': true,
          'activity': '写字',
          'isReliable': true,
          'freshness': 'fresh',
          'summary': '孩子正在写字',
          'observedAt': now.millisecondsSinceEpoch,
          'confidence': 0.9,
        },
      },
    });

    expect(monitor.hasCurrentReliableObservation, isTrue);
    expect(
      observationTitle(
        cameraStatus: null,
        cameraMonitor: monitor,
        currentTask: null,
        localTasks: const [],
        pendingItems: const [],
        childName: '小明',
        now: now,
      ),
      '孩子正在写字',
    );
  });
}
