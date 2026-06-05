import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/core/config/app_environment.dart';
import 'package:guardian_parent_app/src/core/network/api_client.dart';
import 'package:guardian_parent_app/src/features/profile/domain/profile_models.dart';

final profileRepositoryProvider = Provider<ProfileRepository>((ref) {
  return ProfileRepository(
    environment: ref.watch(appEnvironmentProvider),
    apiClient: ref.watch(apiClientProvider),
  );
});

final profileSummaryProvider = FutureProvider<ProfileSummary>((ref) {
  return ref.watch(profileRepositoryProvider).summary();
});

final familyMembersProvider = FutureProvider<List<FamilyMember>>((ref) {
  return ref.watch(profileRepositoryProvider).familyMembers();
});

final familyInvitationsProvider = FutureProvider<List<FamilyInvitation>>((ref) {
  return ref.watch(profileRepositoryProvider).familyInvitations();
});

final currentChildProvider = FutureProvider<ChildProfile?>((ref) {
  return ref.watch(profileRepositoryProvider).currentChild();
});

final emergencyContactsProvider = FutureProvider<List<EmergencyContact>>((ref) {
  return ref.watch(profileRepositoryProvider).emergencyContacts();
});

final accountProfileProvider = FutureProvider<AccountProfile>((ref) {
  return ref.watch(profileRepositoryProvider).accountProfile();
});

final accountSecurityProvider = FutureProvider<AccountSecurity>((ref) {
  return ref.watch(profileRepositoryProvider).accountSecurity();
});

final subscriptionStatusProvider = FutureProvider<SubscriptionStatus>((ref) {
  return ref.watch(profileRepositoryProvider).subscriptionStatus();
});

final subscriptionPlansProvider = FutureProvider<List<SubscriptionPlan>>((ref) {
  return ref.watch(profileRepositoryProvider).subscriptionPlans();
});

final subscriptionEntitlementsProvider =
    FutureProvider<List<SubscriptionFeatureComparison>>((ref) {
      return ref.watch(profileRepositoryProvider).subscriptionEntitlements();
    });

final dailyReportProvider = FutureProvider<ReportData>((ref) {
  return ref.watch(profileRepositoryProvider).dailyReport();
});

final weeklyReportProvider = FutureProvider<ReportData>((ref) {
  return ref.watch(profileRepositoryProvider).weeklyReport();
});

final growthMomentsProvider = FutureProvider<List<GrowthMoment>>((ref) {
  return ref.watch(profileRepositoryProvider).growthMoments();
});

final aboutInfoProvider = FutureProvider<AboutInfo>((ref) {
  return ref.watch(profileRepositoryProvider).aboutInfo();
});

final profileSettingProvider = FutureProvider.family<ProfileSetting, String>((
  ref,
  key,
) {
  return ref.watch(profileRepositoryProvider).setting(key);
});

final legalDocumentProvider = FutureProvider.family<LegalDocumentData, String>((
  ref,
  key,
) {
  return ref.watch(profileRepositoryProvider).legalDocument(key);
});

class ProfileRepository {
  const ProfileRepository({
    required AppEnvironment environment,
    required ApiClient apiClient,
  }) : _environment = environment,
       _apiClient = apiClient;

  final AppEnvironment _environment;
  final ApiClient _apiClient;

  Future<ProfileSummary> summary() async {
    if (_environment.useMockData) return _mockSummary;
    final response = await _get('/profile/summary');
    return ProfileSummary.fromJson(_asMap(_asMap(response.data)['summary']));
  }

  Future<List<FamilyMember>> familyMembers() async {
    if (_environment.useMockData) return _mockMembers;
    final response = await _get('/family/members');
    final raw = _asMap(response.data)['members'];
    if (raw is! List) return const [];
    return raw.map((item) => FamilyMember.fromJson(_asMap(item))).toList();
  }

  Future<List<FamilyInvitation>> familyInvitations() async {
    if (_environment.useMockData) return const [];
    final response = await _get('/family/invitations');
    final raw = _asMap(response.data)['invitations'];
    if (raw is! List) return const [];
    return raw.map((item) => FamilyInvitation.fromJson(_asMap(item))).toList();
  }

  Future<FamilyInvitation> sendFamilyInvitation({
    required String name,
    required String phone,
    required String role,
  }) async {
    final body = {'name': name, 'phone': phone, 'role': role};
    if (_environment.useMockData) {
      return FamilyInvitation.fromJson({
        'id': 'invite_mock_new',
        ...body,
        'status': 'pending',
      });
    }
    final response = await _post('/family/invitations', data: body);
    return FamilyInvitation.fromJson(
      _asMap(_asMap(response.data)['invitation']),
    );
  }

  Future<FamilyInvitation> resendFamilyInvitation(String id) async {
    if (_environment.useMockData) {
      return FamilyInvitation.fromJson({
        'id': id,
        'name': '家庭成员',
        'phone': '',
        'role': 'guardian',
        'status': 'pending',
      });
    }
    final response = await _post('/family/invitations/$id/resend');
    return FamilyInvitation.fromJson(
      _asMap(_asMap(response.data)['invitation']),
    );
  }

  Future<void> cancelFamilyInvitation(String id) async {
    if (_environment.useMockData) return;
    await _post('/family/invitations/$id/cancel');
  }

  Future<FamilyMember> saveFamilyMember({
    String? id,
    required String name,
    required String phone,
    required String role,
    String status = 'active',
    bool notifyEnabled = true,
  }) async {
    final body = {
      'name': name,
      'phone': phone,
      'role': role,
      'status': status,
      'notifyEnabled': notifyEnabled,
    };
    if (_environment.useMockData) {
      return FamilyMember.fromJson({
        'id': id ?? 'member_mock_new',
        ...body,
        'userId': '',
      });
    }
    final response = id == null
        ? await _post('/family/members', data: body)
        : await _patch('/family/members/$id', data: body);
    return FamilyMember.fromJson(_asMap(_asMap(response.data)['member']));
  }

  Future<void> deleteFamilyMember(String id) async {
    if (_environment.useMockData) return;
    await _delete('/family/members/$id');
  }

  Future<ChildProfile?> currentChild() async {
    if (_environment.useMockData) return _mockChild;
    final response = await _get('/children/current');
    final child = _asMap(response.data)['child'];
    return child is Map ? ChildProfile.fromJson(_asMap(child)) : null;
  }

  Future<ChildProfile> updateChild(ChildProfile child) async {
    final body = {
      'name': child.name,
      'nickname': child.nickname,
      'birthday': child.birthday,
      'ageStage': child.ageStage,
      'educationStage': child.educationStage,
      'grade': child.grade,
      'schoolName': child.schoolName,
      'interests': child.interests,
      'taskPreferences': child.taskPreferences,
    };
    if (_environment.useMockData) return child;
    final response = await _patch('/children/${child.id}', data: body);
    return ChildProfile.fromJson(_asMap(_asMap(response.data)['child']));
  }

  Future<List<EmergencyContact>> emergencyContacts() async {
    if (_environment.useMockData) return _mockContacts;
    final response = await _get('/contacts/emergency');
    final raw = _asMap(response.data)['contacts'];
    if (raw is! List) return const [];
    return raw.map((item) => EmergencyContact.fromJson(_asMap(item))).toList();
  }

  Future<EmergencyContact> saveEmergencyContact({
    String? id,
    required String name,
    required String phone,
    required String relationship,
    required bool defaultNotify,
  }) async {
    final body = {
      'name': name,
      'phone': phone,
      'relationship': relationship,
      'defaultNotify': defaultNotify,
    };
    if (_environment.useMockData) {
      return EmergencyContact.fromJson({
        'id': id ?? 'contact_mock_new',
        ...body,
      });
    }
    final response = id == null
        ? await _post('/contacts/emergency', data: body)
        : await _patch('/contacts/emergency/$id', data: body);
    return EmergencyContact.fromJson(_asMap(_asMap(response.data)['contact']));
  }

  Future<void> deleteEmergencyContact(String id) async {
    if (_environment.useMockData) return;
    await _delete('/contacts/emergency/$id');
  }

  Future<AccountProfile> accountProfile() async {
    if (_environment.useMockData) return _mockAccountProfile;
    final response = await _get('/account/profile');
    return AccountProfile.fromJson(_asMap(_asMap(response.data)['profile']));
  }

  Future<AccountProfile> updateAccountProfile({
    required String displayName,
    required String familyName,
    required String relationship,
  }) async {
    if (_environment.useMockData) {
      return AccountProfile(
        userId: _mockAccountProfile.userId,
        phone: _mockAccountProfile.phone,
        displayName: displayName,
        familyName: familyName,
        relationship: relationship,
        role: _mockAccountProfile.role,
      );
    }
    final response = await _patch(
      '/account/profile',
      data: {
        'displayName': displayName,
        'familyName': familyName,
        'relationship': relationship,
      },
    );
    return AccountProfile.fromJson(_asMap(_asMap(response.data)['profile']));
  }

  Future<AccountSecurity> accountSecurity() async {
    if (_environment.useMockData) return _mockSecurity;
    final response = await _get('/account/security');
    return AccountSecurity.fromJson(_asMap(_asMap(response.data)['security']));
  }

  Future<ProfileSetting> setting(String key) async {
    if (_environment.useMockData) {
      return ProfileSetting(key: key, value: _mockSetting(key));
    }
    final response = await _get('/settings/$key');
    return ProfileSetting.fromJson(_asMap(_asMap(response.data)['setting']));
  }

  Future<ProfileSetting> updateSetting(
    String key,
    Map<String, dynamic> value,
  ) async {
    if (_environment.useMockData) return ProfileSetting(key: key, value: value);
    final response = await _patch('/settings/$key', data: {'value': value});
    return ProfileSetting.fromJson(_asMap(_asMap(response.data)['setting']));
  }

  Future<SubscriptionStatus> subscriptionStatus() async {
    if (_environment.useMockData) return _mockSubscription;
    final response = await _get('/subscription/status');
    return SubscriptionStatus.fromJson(
      _asMap(_asMap(response.data)['subscription']),
    );
  }

  Future<List<SubscriptionPlan>> subscriptionPlans() async {
    if (_environment.useMockData) return _mockSubscriptionPlans;
    final response = await _get('/subscriptions/plans');
    final raw = _asMap(response.data)['plans'];
    if (raw is! List) return const [];
    return raw.map((item) => SubscriptionPlan.fromJson(_asMap(item))).toList();
  }

  Future<List<SubscriptionFeatureComparison>> subscriptionEntitlements() async {
    if (_environment.useMockData) return _mockSubscriptionEntitlements;
    final response = await _get('/subscriptions/entitlements');
    final raw = _asMap(response.data)['entitlements'];
    if (raw is! List) return const [];
    return raw
        .map((item) => SubscriptionFeatureComparison.fromJson(_asMap(item)))
        .toList();
  }

  Future<SubscriptionCheckoutResult> startSubscriptionCheckout(
    String planId,
  ) async {
    if (_environment.useMockData) {
      final plan = _mockSubscriptionPlans.firstWhere(
        (item) => item.id == planId,
        orElse: () => _mockSubscriptionPlans[1],
      );
      return SubscriptionCheckoutResult(
        planId: plan.id,
        planTitle: plan.title,
        status: 'pending_payment',
        message: '在线付款入口暂未开放。你可以先查看套餐权益。',
      );
    }
    final response = await _post(
      '/subscriptions/checkout-session',
      data: {'planId': planId},
    );
    return SubscriptionCheckoutResult.fromJson(
      _asMap(_asMap(response.data)['checkout']),
    );
  }

  Future<SubscriptionRestoreResult> restoreSubscription() async {
    if (_environment.useMockData) {
      return const SubscriptionRestoreResult(
        status: 'no_previous_purchase',
        message: '暂未找到可恢复的订阅记录。',
      );
    }
    final response = await _post('/subscriptions/restore');
    return SubscriptionRestoreResult.fromJson(
      _asMap(_asMap(response.data)['restore']),
    );
  }

  Future<ReportData> dailyReport() async {
    if (_environment.useMockData) return _mockReport('今日报告');
    final response = await _get('/reports/daily');
    return ReportData.fromJson(_asMap(_asMap(response.data)['report']));
  }

  Future<ReportData> weeklyReport() async {
    if (_environment.useMockData) return _mockReport('周报');
    final response = await _get('/reports/weekly');
    return ReportData.fromJson(_asMap(_asMap(response.data)['report']));
  }

  Future<List<GrowthMoment>> growthMoments() async {
    if (_environment.useMockData) return const [];
    final response = await _get('/growth/moments');
    final raw = _asMap(response.data)['moments'];
    if (raw is! List) return const [];
    return raw.map((item) => GrowthMoment.fromJson(_asMap(item))).toList();
  }

  Future<LegalDocumentData> legalDocument(String key) async {
    if (_environment.useMockData) return _mockLegal(key);
    final response = await _get('/legal/$key');
    return LegalDocumentData.fromJson(
      _asMap(_asMap(response.data)['document']),
    );
  }

  Future<AboutInfo> aboutInfo() async {
    if (_environment.useMockData) return _mockAbout;
    final response = await _get('/app/about');
    return AboutInfo.fromJson(_asMap(_asMap(response.data)['about']));
  }

  Future<void> submitFeedback({
    required String category,
    required String content,
  }) async {
    if (_environment.useMockData) return;
    await _post('/feedback', data: {'category': category, 'content': content});
  }

  Future<Response<dynamic>> _get(String path) async {
    try {
      return await _apiClient.get(path);
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<Response<dynamic>> _post(String path, {Object? data}) async {
    try {
      return await _apiClient.post(path, data: data);
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<Response<dynamic>> _patch(String path, {Object? data}) async {
    try {
      return await _apiClient.patch(path, data: data);
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<Response<dynamic>> _delete(String path, {Object? data}) async {
    try {
      return await _apiClient.delete(path, data: data);
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  ProfileException _fromDio(DioException error) {
    final data = error.response?.data;
    if (data is Map) {
      final message = data['message'];
      final code = data['error'];
      if (message is String && message.isNotEmpty) {
        return ProfileException(
          message,
          code: code is String ? code : 'profile_error',
        );
      }
    }
    return const ProfileException('家庭空间暂时无法同步，请稍后重试。');
  }
}

final _mockChild = ChildProfile.fromJson({
  'id': 'mock_child',
  'name': '孩子',
  'nickname': '',
  'birthday': '',
  'ageStage': '小学',
  'educationStage': '小学',
  'grade': '一年级',
  'schoolName': '',
  'interests': ['阅读', '手工'],
  'taskPreferences': {'pace': 'gentle'},
});

final _mockSummary = ProfileSummary.fromJson({
  'spaceTitle': '家庭看护空间',
  'familyId': 'mock_family',
  'familyName': '我的家庭空间',
  'displayName': '家长',
  'phone': '13800002026',
  'roleLabel': '管理员',
  'memberCount': 1,
  'deviceCount': 1,
  'pendingItemCount': 0,
  'child': {
    'id': _mockChild.id,
    'name': _mockChild.name,
    'educationStage': _mockChild.educationStage,
    'grade': _mockChild.grade,
  },
});

final _mockMembers = [
  FamilyMember.fromJson({
    'id': 'member_mock_admin',
    'name': '家长',
    'phone': '13800002026',
    'role': 'admin',
    'status': 'active',
    'notifyEnabled': true,
    'userId': 'mock_parent',
  }),
];

final _mockContacts = [
  EmergencyContact.fromJson({
    'id': 'contact_mock',
    'name': '紧急联系人',
    'phone': '13900002026',
    'relationship': '家人',
    'defaultNotify': true,
  }),
];

const _mockAccountProfile = AccountProfile(
  userId: 'mock_parent',
  phone: '13800002026',
  displayName: '家长',
  familyName: '我的家庭空间',
  relationship: '监护人',
  role: 'admin',
);

const _mockSecurity = AccountSecurity(
  phone: '13800002026',
  loginMethod: 'sms',
  accountStatus: 'active',
  loginDevices: [],
);

const _mockSubscription = SubscriptionStatus(
  planId: 'basic',
  planLabel: '基础版',
  status: 'active',
  statusLabel: '已启用',
  renewalText: '随设备提供基础看护能力',
  entitlements: [
    SubscriptionEntitlement(key: 'task_reminders', name: '任务提醒', enabled: true),
    SubscriptionEntitlement(key: 'live_care', name: '实时看护', enabled: true),
    SubscriptionEntitlement(
      key: 'local_daily_report',
      name: '本地日报',
      enabled: true,
    ),
    SubscriptionEntitlement(
      key: 'long_term_reports',
      name: '长期云端报告',
      enabled: false,
    ),
  ],
);

const _mockSubscriptionPlans = [
  SubscriptionPlan(
    id: 'basic',
    title: '基础版',
    subtitle: '随设备提供基础看护能力，适合先完成家庭任务闭环。',
    price: '随设备提供',
    billing: '无需额外订阅',
    recommended: false,
    ctaLabel: '当前套餐',
    features: ['任务提醒', '实时看护', '本地日报', '隐私控制'],
    highlights: ['基础提醒', '实时查看', '本地日报', '隐私控制'],
  ),
  SubscriptionPlan(
    id: 'member',
    title: '会员版',
    subtitle: '给需要长期报告和学习辅助额度的家庭。',
    price: '¥29',
    billing: '/月',
    recommended: true,
    ctaLabel: '开通会员版',
    features: ['云端长期报告', '高级趋势', '题目辅导颗粒度', '更多提醒基线'],
    highlights: ['长期报告', '趋势洞察', '提醒升级', '辅导额度'],
  ),
  SubscriptionPlan(
    id: 'family_plus',
    title: '家庭高级版',
    subtitle: '适合多孩子、多设备和多人协作的家庭空间。',
    price: '¥59',
    billing: '/月起',
    recommended: false,
    ctaLabel: '查看家庭高级版',
    features: ['多孩子与多设备', '多联系人协作', '长期成长档案', '合作内容包'],
    highlights: ['多设备', '多人协作', '成长档案', '内容包'],
  ),
];

const _mockSubscriptionEntitlements = [
  SubscriptionFeatureComparison(
    key: 'task_reminders',
    name: '任务提醒',
    basic: true,
    member: true,
    familyPlus: true,
  ),
  SubscriptionFeatureComparison(
    key: 'live_care',
    name: '实时看护',
    basic: true,
    member: true,
    familyPlus: true,
  ),
  SubscriptionFeatureComparison(
    key: 'local_daily_report',
    name: '本地日报',
    basic: true,
    member: true,
    familyPlus: true,
  ),
  SubscriptionFeatureComparison(
    key: 'long_term_reports',
    name: '长期云端报告',
    basic: false,
    member: true,
    familyPlus: true,
  ),
  SubscriptionFeatureComparison(
    key: 'advanced_trends',
    name: '高级趋势',
    basic: false,
    member: true,
    familyPlus: true,
  ),
  SubscriptionFeatureComparison(
    key: 'multi_device_family',
    name: '多孩子与多设备',
    basic: false,
    member: false,
    familyPlus: true,
  ),
];

Map<String, dynamic> _mockSetting(String key) {
  return switch (key) {
    'notifications' => {
      'taskReminder': true,
      'taskEndReminder': true,
      'deviceOfflineReminder': true,
      'pointsRewardReminder': true,
    },
    'privacy' => {
      'cameraCollectionAuthorized': false,
      'voiceBroadcastAuthorized': false,
      'childPrivacyAuthorized': false,
      'remoteViewingNoticeEnabled': true,
    },
    'conversation' => {
      'wakeName': '看护助手',
      'voiceStyle': '温和女声',
      'boundaryLevel': 'balanced',
      'freeChatEnabled': true,
    },
    'education' => {'schoolbagEnabled': true, 'schoolStage': 'primary'},
    _ => {
      'taskObservationEnabled': true,
      'voiceReminderEnabled': true,
      'delayReminderEnabled': true,
    },
  };
}

ReportData _mockReport(String title) {
  return ReportData(
    title: title,
    summary: '任务记录会在这里生成。',
    taskTotal: 0,
    taskCompleted: 0,
    pointsEarned: 0,
    pendingItems: 0,
  );
}

LegalDocumentData _mockLegal(String key) {
  return LegalDocumentData(
    key: key,
    title: switch (key) {
      'privacy-policy' => '隐私政策',
      'child-privacy-authorization' => '儿童隐私授权说明',
      _ => '用户协议',
    },
    summary: '请阅读家庭看护空间的使用和隐私说明。',
    sections: const [
      LegalDocumentSectionData(
        title: '说明',
        paragraphs: ['关键决定由家长确认，儿童数据按最小必要原则处理。'],
      ),
    ],
    version: '1.0',
    effectiveDate: '2026-06-04',
  );
}

const _mockAbout = AboutInfo(
  appName: '家庭看护',
  displayName: '家庭看护',
  version: '1.0.0',
  description: '面向家长的家庭 AI 看护与成长记录 App。',
  principles: ['儿童隐私优先', '关键决定由家长确认'],
);

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}
