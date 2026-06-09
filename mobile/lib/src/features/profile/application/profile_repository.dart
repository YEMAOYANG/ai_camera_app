import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/core/network/api_client.dart';
import 'package:guardian_parent_app/src/features/profile/domain/profile_models.dart';
import 'package:guardian_parent_app/src/shared/domain/guardian_identity.dart';

final profileRepositoryProvider = Provider<ProfileRepository>((ref) {
  return ProfileRepository(apiClient: ref.watch(apiClientProvider));
});

final profileSummaryProvider = FutureProvider<ProfileSummary>((ref) {
  return ref.watch(profileRepositoryProvider).summary();
});

final guardianIdentityOptionsProvider = FutureProvider<GuardianIdentityOptions>(
  (ref) {
    return ref.watch(profileRepositoryProvider).guardianIdentityOptions();
  },
);

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
  const ProfileRepository({required ApiClient apiClient})
    : _apiClient = apiClient;

  final ApiClient _apiClient;

  Future<ProfileSummary> summary() async {
    final response = await _get('/profile/summary');
    return ProfileSummary.fromJson(_asMap(_asMap(response.data)['summary']));
  }

  Future<GuardianIdentityOptions> guardianIdentityOptions() async {
    final response = await _get('/profile/guardian-identity-options');
    return GuardianIdentityOptions.fromJson(
      _asMap(_asMap(response.data)['options']),
    );
  }

  Future<List<FamilyMember>> familyMembers() async {
    final response = await _get('/family/members');
    final raw = _asMap(response.data)['members'];
    if (raw is! List) return const [];
    return raw.map((item) => FamilyMember.fromJson(_asMap(item))).toList();
  }

  Future<List<FamilyInvitation>> familyInvitations() async {
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
    final response = await _post('/family/invitations', data: body);
    return FamilyInvitation.fromJson(
      _asMap(_asMap(response.data)['invitation']),
    );
  }

  Future<FamilyInvitation> resendFamilyInvitation(String id) async {
    final response = await _post('/family/invitations/$id/resend');
    return FamilyInvitation.fromJson(
      _asMap(_asMap(response.data)['invitation']),
    );
  }

  Future<void> cancelFamilyInvitation(String id) async {
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
    final response = id == null
        ? await _post('/family/members', data: body)
        : await _patch('/family/members/$id', data: body);
    return FamilyMember.fromJson(_asMap(_asMap(response.data)['member']));
  }

  Future<void> deleteFamilyMember(String id) async {
    await _delete('/family/members/$id');
  }

  Future<ChildProfile?> currentChild() async {
    final response = await _get('/children/current');
    final child = _asMap(response.data)['child'];
    return child is Map ? ChildProfile.fromJson(_asMap(child)) : null;
  }

  Future<ChildProfile> updateChild(ChildProfile child) async {
    final body = {
      'name': child.name,
      'nickname': child.nickname,
      'gender': child.gender,
      'birthday': child.birthday,
      'ageStage': child.ageStage,
      'educationStage': child.educationStage,
      'grade': child.grade,
      'schoolName': child.schoolName,
      'interests': child.interests,
      'taskPreferences': child.taskPreferences,
    };
    final response = await _patch('/children/${child.id}', data: body);
    return ChildProfile.fromJson(_asMap(_asMap(response.data)['child']));
  }

  Future<List<EmergencyContact>> emergencyContacts() async {
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
    required String relationshipKey,
    required bool defaultNotify,
  }) async {
    final body = {
      'name': name,
      'phone': phone,
      'relationship': relationship,
      'relationshipKey': relationshipKey,
      'defaultNotify': defaultNotify,
    };
    final response = id == null
        ? await _post('/contacts/emergency', data: body)
        : await _patch('/contacts/emergency/$id', data: body);
    return EmergencyContact.fromJson(_asMap(_asMap(response.data)['contact']));
  }

  Future<void> deleteEmergencyContact(String id) async {
    await _delete('/contacts/emergency/$id');
  }

  Future<AccountProfile> accountProfile() async {
    final response = await _get('/account/profile');
    return AccountProfile.fromJson(_asMap(_asMap(response.data)['profile']));
  }

  Future<AccountProfile> updateAccountProfile({
    String? displayName,
    String? familyName,
    String? relationship,
    String? relationshipKey,
  }) async {
    final data = <String, String>{};
    if (displayName != null) data['displayName'] = displayName;
    if (familyName != null) data['familyName'] = familyName;
    if (relationship != null) data['relationship'] = relationship;
    if (relationshipKey != null) data['relationshipKey'] = relationshipKey;
    final response = await _patch('/account/profile', data: data);
    return AccountProfile.fromJson(_asMap(_asMap(response.data)['profile']));
  }

  Future<AccountSecurity> accountSecurity() async {
    final response = await _get('/account/security');
    return AccountSecurity.fromJson(_asMap(_asMap(response.data)['security']));
  }

  Future<AccountSecurity> revokeLoginDevice(String sessionId) async {
    final response = await _post('/account/sessions/$sessionId/revoke');
    return AccountSecurity.fromJson(_asMap(_asMap(response.data)['security']));
  }

  Future<AccountDeletionResult> requestAccountDeletion({
    String reason = 'user_requested',
  }) async {
    final response = await _post('/account/deletion', data: {'reason': reason});
    return AccountDeletionResult.fromJson(_asMap(response.data));
  }

  Future<PhoneChangeCodeResult> requestAccountPhoneCode(String phone) async {
    final response = await _post('/account/phone/code', data: {'phone': phone});
    return PhoneChangeCodeResult.fromJson(_asMap(response.data));
  }

  Future<AccountProfile> updateAccountPhone({
    required String phone,
    required String code,
  }) async {
    final response = await _patch(
      '/account/phone',
      data: {'phone': phone, 'code': code},
    );
    return AccountProfile.fromJson(_asMap(_asMap(response.data)['profile']));
  }

  Future<ProfileSetting> setting(String key) async {
    final response = await _get('/settings/$key');
    return ProfileSetting.fromJson(_asMap(_asMap(response.data)['setting']));
  }

  Future<ProfileSetting> updateSetting(
    String key,
    Map<String, dynamic> value,
  ) async {
    final response = await _patch('/settings/$key', data: {'value': value});
    return ProfileSetting.fromJson(_asMap(_asMap(response.data)['setting']));
  }

  Future<SubscriptionStatus> subscriptionStatus() async {
    final response = await _get('/subscription/status');
    return SubscriptionStatus.fromJson(
      _asMap(_asMap(response.data)['subscription']),
    );
  }

  Future<List<SubscriptionPlan>> subscriptionPlans() async {
    final response = await _get('/subscriptions/plans');
    final raw = _asMap(response.data)['plans'];
    if (raw is! List) return const [];
    return raw.map((item) => SubscriptionPlan.fromJson(_asMap(item))).toList();
  }

  Future<List<SubscriptionFeatureComparison>> subscriptionEntitlements() async {
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
    final response = await _post(
      '/subscriptions/checkout-session',
      data: {'planId': planId},
    );
    return SubscriptionCheckoutResult.fromJson(
      _asMap(_asMap(response.data)['checkout']),
    );
  }

  Future<SubscriptionRestoreResult> restoreSubscription() async {
    final response = await _post('/subscriptions/restore');
    return SubscriptionRestoreResult.fromJson(
      _asMap(_asMap(response.data)['restore']),
    );
  }

  Future<ReportData> dailyReport() async {
    final response = await _get('/reports/daily');
    return ReportData.fromJson(_asMap(_asMap(response.data)['report']));
  }

  Future<ReportData> weeklyReport() async {
    final response = await _get('/reports/weekly');
    return ReportData.fromJson(_asMap(_asMap(response.data)['report']));
  }

  Future<List<GrowthMoment>> growthMoments() async {
    final response = await _get('/growth/moments');
    final raw = _asMap(response.data)['moments'];
    if (raw is! List) return const [];
    return raw.map((item) => GrowthMoment.fromJson(_asMap(item))).toList();
  }

  Future<LegalDocumentData> legalDocument(String key) async {
    final response = await _get('/legal/$key');
    return LegalDocumentData.fromJson(
      _asMap(_asMap(response.data)['document']),
    );
  }

  Future<AboutInfo> aboutInfo() async {
    final response = await _get('/app/about');
    return AboutInfo.fromJson(_asMap(_asMap(response.data)['about']));
  }

  Future<void> submitFeedback({
    required String category,
    required String content,
  }) async {
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

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}
