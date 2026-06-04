import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/core/config/app_environment.dart';
import 'package:mira_guardian_app/src/core/network/api_client.dart';
import 'package:mira_guardian_app/src/features/profile/domain/profile_models.dart';

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

final legalDocumentProvider =
    FutureProvider.family<LegalDocumentData, String>((ref, key) {
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
      return EmergencyContact.fromJson({'id': id ?? 'contact_mock_new', ...body});
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
    final response = await _patch('/account/profile', data: {
      'displayName': displayName,
      'familyName': familyName,
      'relationship': relationship,
    });
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
    return LegalDocumentData.fromJson(_asMap(_asMap(response.data)['document']));
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
  planLabel: '基础版',
  statusLabel: '已启用',
  renewalText: '随设备提供基础看护能力',
  entitlements: [
    SubscriptionEntitlement(name: '任务提醒', enabled: true),
    SubscriptionEntitlement(name: '实时看护', enabled: true),
    SubscriptionEntitlement(name: '积分与奖励', enabled: true),
  ],
);

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
      'wakeName': '米拉',
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
  appName: 'Mira Guardian',
  displayName: '米拉家庭看护',
  version: '1.0.0',
  description: '面向家长的家庭 AI 看护与成长记录 App。',
  principles: ['儿童隐私优先', '关键决定由家长确认'],
);

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}
