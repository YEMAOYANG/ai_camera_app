class ProfileSummary {
  const ProfileSummary({
    required this.spaceTitle,
    required this.familyId,
    required this.familyName,
    required this.displayName,
    required this.phone,
    required this.roleLabel,
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
  final String roleLabel;
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
      roleLabel: _asString(json['roleLabel'], fallback: '管理员'),
      avatarPersona: _asString(json['avatarPersona']),
      memberCount: _asInt(json['memberCount']),
      deviceCount: _asInt(json['deviceCount']),
      pendingItemCount: _asInt(json['pendingItemCount']),
      child: json['child'] is Map
          ? ChildProfile.fromJson(_asMap(json['child']))
          : null,
    );
  }
}

class FamilyMember {
  const FamilyMember({
    required this.id,
    required this.name,
    required this.phone,
    required this.role,
    required this.status,
    required this.notifyEnabled,
    required this.userId,
  });

  final String id;
  final String name;
  final String phone;
  final String role;
  final String status;
  final bool notifyEnabled;
  final String userId;

  String get roleLabel {
    return switch (role) {
      'admin' => '管理员',
      'guardian' => '监护人',
      'caregiver' => '照护人',
      'viewer' => '查看者',
      _ => '成员',
    };
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
      phone: _asString(json['phone']),
      role: _asString(json['role'], fallback: 'guardian'),
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
    required this.phone,
    required this.role,
    required this.status,
    required this.createdAt,
    required this.expiresAt,
  });

  final String id;
  final String name;
  final String phone;
  final String role;
  final String status;
  final int createdAt;
  final int? expiresAt;

  String get roleLabel {
    return switch (role) {
      'admin' => '管理员',
      'guardian' => '监护人',
      'viewer' => '仅接收通知',
      'caregiver' => '照护人',
      _ => '成员',
    };
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
      phone: _asString(json['phone']),
      role: _asString(json['role'], fallback: 'guardian'),
      status: _asString(json['status'], fallback: 'pending'),
      createdAt: _asInt(json['createdAt']),
      expiresAt: _asNullableInt(json['expiresAt']),
    );
  }
}

class ChildProfile {
  const ChildProfile({
    required this.id,
    required this.name,
    required this.nickname,
    required this.birthday,
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
  final String birthday;
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
      birthday: _asString(json['birthday']),
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
    required this.defaultNotify,
  });

  final String id;
  final String name;
  final String phone;
  final String relationship;
  final bool defaultNotify;

  static EmergencyContact fromJson(Map<String, dynamic> json) {
    return EmergencyContact(
      id: _asString(json['id']),
      name: _asString(json['name'], fallback: '联系人'),
      phone: _asString(json['phone']),
      relationship: _asString(json['relationship']),
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
    required this.role,
    required this.avatarPersona,
    required this.gender,
    required this.ageGroup,
  });

  final String userId;
  final String phone;
  final String displayName;
  final String familyName;
  final String relationship;
  final String role;
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
      role: _asString(json['role'], fallback: 'admin'),
      avatarPersona: _asString(json['avatarPersona']),
      gender: _asString(json['gender']),
      ageGroup: _asString(json['ageGroup']),
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

class LoginDevice {
  const LoginDevice({
    required this.id,
    required this.label,
    required this.active,
    required this.createdAt,
    required this.rotatedAt,
  });

  final String id;
  final String label;
  final bool active;
  final int createdAt;
  final int? rotatedAt;

  static LoginDevice fromJson(Map<String, dynamic> json) {
    return LoginDevice(
      id: _asString(json['id']),
      label: _asString(json['label'], fallback: '已登录设备'),
      active: json['active'] == true,
      createdAt: _asInt(json['createdAt']),
      rotatedAt: _asNullableInt(json['rotatedAt']),
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
    required this.description,
    required this.principles,
  });

  final String appName;
  final String displayName;
  final String version;
  final String description;
  final List<String> principles;

  static AboutInfo fromJson(Map<String, dynamic> json) {
    return AboutInfo(
      appName: _asString(json['appName'], fallback: '家庭看护'),
      displayName: _asString(json['displayName'], fallback: '家庭看护'),
      version: _asString(json['version']),
      description: _asString(json['description']),
      principles: _asStringList(json['principles']),
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
