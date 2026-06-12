class ProfileSummary {
  const ProfileSummary({
    required this.spaceTitle,
    required this.familyId,
    required this.familyName,
    required this.displayName,
    required this.phone,
    required this.relationship,
    required this.relationshipKey,
    required this.role,
    required this.roleLabel,
    required this.capabilities,
    required this.avatarPersona,
    required this.memberCount,
    required this.deviceCount,
    required this.pendingItemCount,
    required this.child,
  });

  final String spaceTitle;
  final String familyId;
  final String familyName;
  final String displayName;
  final String phone;
  final String relationship;
  final String relationshipKey;
  final String role;
  final String roleLabel;
  final List<String> capabilities;
  final String avatarPersona;
  final int memberCount;
  final int deviceCount;
  final int pendingItemCount;
  final ChildProfile? child;

  static ProfileSummary fromJson(Map<String, dynamic> json) {
    return ProfileSummary(
      spaceTitle: _asString(json['spaceTitle'], fallback: '家庭看护空间'),
      familyId: _asString(json['familyId']),
      familyName: _asString(json['familyName'], fallback: '我的家庭空间'),
      displayName: _asString(json['displayName'], fallback: '家长'),
      phone: _asString(json['phone']),
      relationship: _asString(json['relationship']),
      relationshipKey: _asString(json['relationshipKey']),
      role: _asString(json['role']),
      roleLabel: _asString(json['roleLabel']),
      capabilities: _asStringList(json['capabilities']),
      avatarPersona: _asString(json['avatarPersona']),
      memberCount: _asInt(json['memberCount']),
      deviceCount: _asInt(json['deviceCount']),
      pendingItemCount: _asInt(json['pendingItemCount']),
      child: json['child'] is Map
          ? ChildProfile.fromJson(_asMap(json['child']))
          : null,
    );
  }

  bool can(String capability) => capabilities.contains(capability);
}

class FamilyMember {
  const FamilyMember({
    required this.id,
    required this.name,
    required this.relationshipKey,
    required this.phone,
    required this.role,
    required this.status,
    required this.notifyEnabled,
    required this.userId,
  });

  final String id;
  final String name;
  final String relationshipKey;
  final String phone;
  final String role;
  final String status;
  final bool notifyEnabled;
  final String userId;

  String get roleLabel {
    return role;
  }

  String get statusLabel {
    return switch (status) {
      'active' => '已加入',
      'invited' => '待加入',
      'disabled' => '已停用',
      _ => '未知',
    };
  }

  static FamilyMember fromJson(Map<String, dynamic> json) {
    return FamilyMember(
      id: _asString(json['id']),
      name: _asString(json['name'], fallback: '家庭成员'),
      relationshipKey: _asString(json['relationshipKey']),
      phone: _asString(json['phone']),
      role: _asString(json['role']),
      status: _asString(json['status'], fallback: 'active'),
      notifyEnabled: json['notifyEnabled'] == true,
      userId: _asString(json['userId']),
    );
  }
}

class FamilyInvitation {
  const FamilyInvitation({
    required this.id,
    required this.name,
    required this.relationshipKey,
    required this.phone,
    required this.role,
    required this.status,
    required this.createdAt,
    required this.expiresAt,
    required this.deliveryStatus,
    required this.deliveryNotice,
  });

  final String id;
  final String name;
  final String relationshipKey;
  final String phone;
  final String role;
  final String status;
  final int createdAt;
  final int? expiresAt;
  final String deliveryStatus;
  final String deliveryNotice;

  String get roleLabel {
    return role;
  }

  String get statusLabel {
    return switch (status) {
      'pending' => '待接受',
      'accepted' => '已接受',
      'cancelled' => '已取消',
      'expired' => '已过期',
      _ => '待接受',
    };
  }

  static FamilyInvitation fromJson(Map<String, dynamic> json) {
    return FamilyInvitation(
      id: _asString(json['id']),
      name: _asString(json['name'], fallback: '家庭成员'),
      relationshipKey: _asString(json['relationshipKey']),
      phone: _asString(json['phone']),
      role: _asString(json['role']),
      status: _asString(json['status'], fallback: 'pending'),
      createdAt: _asInt(json['createdAt']),
      expiresAt: _asNullableInt(json['expiresAt']),
      deliveryStatus: _asString(json['deliveryStatus']),
      deliveryNotice: _asString(json['deliveryNotice']),
    );
  }
}

class ChildProfile {
  const ChildProfile({
    required this.id,
    required this.name,
    required this.nickname,
    required this.gender,
    required this.birthday,
    required this.sleepTime,
    required this.ageStage,
    required this.educationStage,
    required this.grade,
    required this.schoolName,
    required this.interests,
    required this.taskPreferences,
  });

  final String id;
  final String name;
  final String nickname;
  final String gender;
  final String birthday;
  final String sleepTime;
  final String ageStage;
  final String educationStage;
  final String grade;
  final String schoolName;
  final List<String> interests;
  final Map<String, dynamic> taskPreferences;

  String get displayStage {
    final parts = [
      if (educationStage.isNotEmpty) educationStage,
      if (grade.isNotEmpty) grade,
    ];
    return parts.isEmpty ? '阶段待完善' : parts.join(' · ');
  }

  static ChildProfile fromJson(Map<String, dynamic> json) {
    return ChildProfile(
      id: _asString(json['id']),
      name: _asString(json['name'], fallback: '孩子'),
      nickname: _asString(json['nickname']),
      gender: _asString(json['gender'], fallback: 'unspecified'),
      birthday: _asString(json['birthday']),
      sleepTime: _asString(json['sleepTime']),
      ageStage: _asString(json['ageStage']),
      educationStage: _asString(json['educationStage']),
      grade: _asString(json['grade']),
      schoolName: _asString(json['schoolName']),
      interests: _asStringList(json['interests']),
      taskPreferences: _asMap(json['taskPreferences']),
    );
  }
}

class EmergencyContact {
  const EmergencyContact({
    required this.id,
    required this.name,
    required this.phone,
    required this.relationship,
    required this.relationshipKey,
    required this.defaultNotify,
  });

  final String id;
  final String name;
  final String phone;
  final String relationship;
  final String relationshipKey;
  final bool defaultNotify;

  static EmergencyContact fromJson(Map<String, dynamic> json) {
    return EmergencyContact(
      id: _asString(json['id']),
      name: _asString(json['name'], fallback: '联系人'),
      phone: _asString(json['phone']),
      relationship: _asString(json['relationship']),
      relationshipKey: _asString(json['relationshipKey']),
      defaultNotify: json['defaultNotify'] == true,
    );
  }
}

class AccountProfile {
  const AccountProfile({
    required this.userId,
    required this.phone,
    required this.displayName,
    required this.familyName,
    required this.relationship,
    required this.relationshipKey,
    required this.role,
    required this.roleLabel,
    required this.capabilities,
    required this.avatarPersona,
    required this.gender,
    required this.ageGroup,
  });

  final String userId;
  final String phone;
  final String displayName;
  final String familyName;
  final String relationship;
  final String relationshipKey;
  final String role;
  final String roleLabel;
  final List<String> capabilities;
  final String avatarPersona;
  final String gender;
  final String ageGroup;

  static AccountProfile fromJson(Map<String, dynamic> json) {
    return AccountProfile(
      userId: _asString(json['userId']),
      phone: _asString(json['phone']),
      displayName: _asString(json['displayName'], fallback: '家长'),
      familyName: _asString(json['familyName'], fallback: '我的家庭空间'),
      relationship: _asString(json['relationship']),
      relationshipKey: _asString(json['relationshipKey']),
      role: _asString(json['role']),
      roleLabel: _asString(json['roleLabel']),
      capabilities: _asStringList(json['capabilities']),
      avatarPersona: _asString(json['avatarPersona']),
      gender: _asString(json['gender']),
      ageGroup: _asString(json['ageGroup']),
    );
  }

  bool can(String capability) => capabilities.contains(capability);
}

class FamilyCodeInfo {
  const FamilyCodeInfo({
    required this.familyId,
    required this.familyName,
    required this.code,
    required this.updatedAt,
  });

  final String familyId;
  final String familyName;
  final String code;
  final int? updatedAt;

  static FamilyCodeInfo fromJson(Map<String, dynamic> json) {
    return FamilyCodeInfo(
      familyId: _asString(json['familyId']),
      familyName: _asString(json['familyName']),
      code: _asString(json['code']),
      updatedAt: _asNullableInt(json['updatedAt']),
    );
  }
}

class FamilyCodePreview {
  const FamilyCodePreview({
    required this.familyId,
    required this.familyName,
    required this.familyCode,
    required this.role,
    required this.roleLabel,
    required this.message,
  });

  final String familyId;
  final String familyName;
  final String familyCode;
  final String role;
  final String roleLabel;
  final String message;

  static FamilyCodePreview fromJson(Map<String, dynamic> json) {
    return FamilyCodePreview(
      familyId: _asString(json['familyId']),
      familyName: _asString(json['familyName']),
      familyCode: _asString(json['familyCode']),
      role: _asString(json['role']),
      roleLabel: _asString(json['roleLabel']),
      message: _asString(json['message']),
    );
  }
}

class AccountSecurity {
  const AccountSecurity({
    required this.phone,
    required this.loginMethod,
    required this.accountStatus,
    required this.loginDevices,
  });

  final String phone;
  final String loginMethod;
  final String accountStatus;
  final List<LoginDevice> loginDevices;

  static AccountSecurity fromJson(Map<String, dynamic> json) {
    final devices = json['loginDevices'];
    return AccountSecurity(
      phone: _asString(json['phone']),
      loginMethod: _asString(json['loginMethod'], fallback: 'sms'),
      accountStatus: _asString(json['accountStatus'], fallback: 'active'),
      loginDevices: devices is List
          ? devices.map((item) => LoginDevice.fromJson(_asMap(item))).toList()
          : const [],
    );
  }
}

class PhoneChangeCodeResult {
  const PhoneChangeCodeResult({
    required this.codeSent,
    required this.expiresAt,
    required this.message,
    this.debugCode = '',
  });

  final bool codeSent;
  final int expiresAt;
  final String message;
  final String debugCode;

  static PhoneChangeCodeResult fromJson(Map<String, dynamic> json) {
    return PhoneChangeCodeResult(
      codeSent: json['codeSent'] == true,
      expiresAt: _asInt(json['expiresAt']),
      message: _asString(json['message'], fallback: '验证码已发送'),
      debugCode: _asString(json['debugCode']),
    );
  }
}

class LoginDevice {
  const LoginDevice({
    required this.id,
    required this.label,
    required this.deviceType,
    required this.model,
    required this.hardware,
    required this.platform,
    required this.osVersion,
    required this.appVersion,
    required this.active,
    required this.current,
    required this.createdAt,
    required this.lastActiveAt,
    required this.rotatedAt,
  });

  final String id;
  final String label;
  final String deviceType;
  final String model;
  final String hardware;
  final String platform;
  final String osVersion;
  final String appVersion;
  final bool active;
  final bool current;
  final int createdAt;
  final int lastActiveAt;
  final int? rotatedAt;

  static LoginDevice fromJson(Map<String, dynamic> json) {
    return LoginDevice(
      id: _asString(json['id']),
      label: _asString(json['label'], fallback: '已登录设备'),
      deviceType: _asString(json['deviceType'], fallback: 'unknown'),
      model: _asString(json['model']),
      hardware: _asString(json['hardware']),
      platform: _asString(json['platform'], fallback: 'unknown'),
      osVersion: _asString(json['osVersion']),
      appVersion: _asString(json['appVersion']),
      active: json['active'] == true,
      current: json['current'] == true,
      createdAt: _asInt(json['createdAt']),
      lastActiveAt: _asInt(json['lastActiveAt']),
      rotatedAt: _asNullableInt(json['rotatedAt']),
    );
  }
}

class AccountDeletionResult {
  const AccountDeletionResult({
    required this.status,
    required this.requestedAt,
    required this.message,
  });

  final String status;
  final int requestedAt;
  final String message;

  static AccountDeletionResult fromJson(Map<String, dynamic> json) {
    final request = _asMap(json['deletionRequest']);
    return AccountDeletionResult(
      status: _asString(request['status'], fallback: 'requested'),
      requestedAt: _asInt(request['requestedAt']),
      message: _asString(json['message'], fallback: '账号注销申请已提交'),
    );
  }
}

class ProfileSetting {
  const ProfileSetting({required this.key, required this.value});

  final String key;
  final Map<String, dynamic> value;

  static ProfileSetting fromJson(Map<String, dynamic> json) {
    return ProfileSetting(
      key: _asString(json['key']),
      value: _asMap(json['value']),
    );
  }
}

class LegalDocumentData {
  const LegalDocumentData({
    required this.key,
    required this.title,
    required this.summary,
    required this.sections,
    required this.version,
    required this.effectiveDate,
  });

  final String key;
  final String title;
  final String summary;
  final List<LegalDocumentSectionData> sections;
  final String version;
  final String effectiveDate;

  static LegalDocumentData fromJson(Map<String, dynamic> json) {
    final sections = json['sections'];
    return LegalDocumentData(
      key: _asString(json['key']),
      title: _asString(json['title']),
      summary: _asString(json['summary']),
      sections: sections is List
          ? sections
                .map((item) => LegalDocumentSectionData.fromJson(_asMap(item)))
                .toList()
          : const [],
      version: _asString(json['version']),
      effectiveDate: _asString(json['effectiveDate']),
    );
  }
}

class LegalDocumentSectionData {
  const LegalDocumentSectionData({
    required this.title,
    required this.paragraphs,
  });

  final String title;
  final List<String> paragraphs;

  static LegalDocumentSectionData fromJson(Map<String, dynamic> json) {
    return LegalDocumentSectionData(
      title: _asString(json['title']),
      paragraphs: _asStringList(json['paragraphs']),
    );
  }
}

class AboutInfo {
  const AboutInfo({
    required this.appName,
    required this.displayName,
    required this.version,
    required this.build,
    required this.appUpdate,
    required this.description,
    required this.principles,
  });

  final String appName;
  final String displayName;
  final String version;
  final String build;
  final AppUpdateInfo appUpdate;
  final String description;
  final List<String> principles;

  static AboutInfo fromJson(Map<String, dynamic> json) {
    return AboutInfo(
      appName: _asString(json['appName'], fallback: '家庭看护'),
      displayName: _asString(json['displayName'], fallback: '家庭看护'),
      version: _asString(json['version']),
      build: _asString(json['build']),
      appUpdate: AppUpdateInfo.fromJson(_asMap(json['appUpdate'])),
      description: _asString(json['description']),
      principles: _asStringList(json['principles']),
    );
  }
}

class AppUpdateInfo {
  const AppUpdateInfo({
    required this.status,
    required this.latestVersion,
    required this.latestBuild,
    required this.releaseDate,
    required this.notes,
  });

  final String status;
  final String latestVersion;
  final String latestBuild;
  final String releaseDate;
  final String notes;

  bool get updateAvailable => status == 'available';

  String get statusLabel => updateAvailable ? '发现新版本' : '当前已是最新';

  static AppUpdateInfo fromJson(Map<String, dynamic> json) {
    return AppUpdateInfo(
      status: _asString(json['status'], fallback: 'latest'),
      latestVersion: _asString(json['latestVersion']),
      latestBuild: _asString(json['latestBuild']),
      releaseDate: _asString(json['releaseDate']),
      notes: _asString(json['notes']),
    );
  }
}

class SubscriptionStatus {
  const SubscriptionStatus({
    required this.planId,
    required this.planLabel,
    required this.status,
    required this.statusLabel,
    required this.renewalText,
    required this.entitlements,
  });

  final String planId;
  final String planLabel;
  final String status;
  final String statusLabel;
  final String renewalText;
  final List<SubscriptionEntitlement> entitlements;

  static SubscriptionStatus fromJson(Map<String, dynamic> json) {
    final entitlements = json['entitlements'];
    return SubscriptionStatus(
      planId: _asString(json['planId'], fallback: _asString(json['plan'])),
      planLabel: _asString(json['planLabel']),
      status: _asString(json['status']),
      statusLabel: _asString(json['statusLabel']),
      renewalText: _asString(json['renewalText']),
      entitlements: entitlements is List
          ? entitlements
                .map((item) => SubscriptionEntitlement.fromJson(_asMap(item)))
                .toList()
          : const [],
    );
  }
}

class SubscriptionEntitlement {
  const SubscriptionEntitlement({
    required this.name,
    required this.enabled,
    this.key = '',
  });

  final String key;
  final String name;
  final bool enabled;

  static SubscriptionEntitlement fromJson(Map<String, dynamic> json) {
    return SubscriptionEntitlement(
      key: _asString(json['key']),
      name: _asString(json['name']),
      enabled: json['enabled'] == true,
    );
  }
}

class SubscriptionPlan {
  const SubscriptionPlan({
    required this.id,
    required this.title,
    required this.subtitle,
    required this.price,
    required this.billing,
    required this.recommended,
    required this.ctaLabel,
    required this.features,
    required this.highlights,
  });

  final String id;
  final String title;
  final String subtitle;
  final String price;
  final String billing;
  final bool recommended;
  final String ctaLabel;
  final List<String> features;
  final List<String> highlights;

  static SubscriptionPlan fromJson(Map<String, dynamic> json) {
    return SubscriptionPlan(
      id: _asString(json['id']),
      title: _asString(json['title']),
      subtitle: _asString(json['subtitle']),
      price: _asString(json['price']),
      billing: _asString(json['billing']),
      recommended: json['recommended'] == true,
      ctaLabel: _asString(json['ctaLabel']),
      features: _asStringList(json['features']),
      highlights: _asStringList(json['highlights']),
    );
  }
}

class SubscriptionFeatureComparison {
  const SubscriptionFeatureComparison({
    required this.key,
    required this.name,
    required this.basic,
    required this.member,
    required this.familyPlus,
  });

  final String key;
  final String name;
  final bool basic;
  final bool member;
  final bool familyPlus;

  static SubscriptionFeatureComparison fromJson(Map<String, dynamic> json) {
    return SubscriptionFeatureComparison(
      key: _asString(json['key']),
      name: _asString(json['name']),
      basic: json['basic'] == true,
      member: json['member'] == true,
      familyPlus: json['family_plus'] == true || json['familyPlus'] == true,
    );
  }
}

class SubscriptionCheckoutResult {
  const SubscriptionCheckoutResult({
    required this.planId,
    required this.planTitle,
    required this.status,
    required this.message,
  });

  final String planId;
  final String planTitle;
  final String status;
  final String message;

  static SubscriptionCheckoutResult fromJson(Map<String, dynamic> json) {
    return SubscriptionCheckoutResult(
      planId: _asString(json['planId']),
      planTitle: _asString(json['planTitle']),
      status: _asString(json['status']),
      message: _asString(json['message']),
    );
  }
}

class SubscriptionRestoreResult {
  const SubscriptionRestoreResult({
    required this.status,
    required this.message,
  });

  final String status;
  final String message;

  static SubscriptionRestoreResult fromJson(Map<String, dynamic> json) {
    return SubscriptionRestoreResult(
      status: _asString(json['status']),
      message: _asString(json['message']),
    );
  }
}

class ReportData {
  const ReportData({
    required this.title,
    required this.summary,
    required this.taskTotal,
    required this.taskCompleted,
    required this.pointsEarned,
    required this.pendingItems,
  });

  final String title;
  final String summary;
  final int taskTotal;
  final int taskCompleted;
  final int pointsEarned;
  final int pendingItems;

  static ReportData fromJson(Map<String, dynamic> json) {
    return ReportData(
      title: _asString(json['title']),
      summary: _asString(json['summary']),
      taskTotal: _asInt(json['taskTotal']),
      taskCompleted: _asInt(json['taskCompleted']),
      pointsEarned: _asInt(json['pointsEarned']),
      pendingItems: _asInt(json['pendingItems']),
    );
  }
}

class GrowthMoment {
  const GrowthMoment({required this.id, required this.title});

  final String id;
  final String title;

  static GrowthMoment fromJson(Map<String, dynamic> json) {
    return GrowthMoment(
      id: _asString(json['id']),
      title: _asString(json['title']),
    );
  }
}

class ProfileException implements Exception {
  const ProfileException(this.message, {this.code = 'profile_error'});

  final String message;
  final String code;
}

String _asString(dynamic value, {String fallback = ''}) {
  return value is String && value.isNotEmpty ? value : fallback;
}

int _asInt(dynamic value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value) ?? 0;
  return 0;
}

int? _asNullableInt(dynamic value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}

List<String> _asStringList(dynamic value) {
  if (value is! List) return const [];
  return value
      .map((item) => '$item'.trim())
      .where((item) => item.isNotEmpty)
      .toList();
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}
