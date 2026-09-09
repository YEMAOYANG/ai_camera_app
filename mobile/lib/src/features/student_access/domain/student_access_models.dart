class StudentPairingCode {
  const StudentPairingCode({
    required this.code,
    required this.expiresAt,
    required this.child,
  });

  final String code;
  final DateTime expiresAt;
  final StudentPairingChild child;

  bool isExpiredAt(DateTime now) => !expiresAt.isAfter(now);

  Duration remainingAt(DateTime now) {
    if (isExpiredAt(now)) return Duration.zero;
    return expiresAt.difference(now);
  }

  static StudentPairingCode fromJson(Map<String, dynamic> json) {
    final expiresAtMs = _asInt(json['expiresAt']);
    if (expiresAtMs <= 0) {
      throw const FormatException('Missing pairing code expiry.');
    }
    return StudentPairingCode(
      code: _asString(json['pairingCode']),
      expiresAt: DateTime.fromMillisecondsSinceEpoch(expiresAtMs),
      child: StudentPairingChild.fromJson(_asMap(json['child'])),
    );
  }
}

class StudentPairingChild {
  const StudentPairingChild({
    required this.id,
    required this.name,
    required this.nickname,
  });

  final String id;
  final String name;
  final String nickname;

  String get displayName {
    final preferred = nickname.trim();
    if (preferred.isNotEmpty) return preferred;
    final fallback = name.trim();
    return fallback.isEmpty ? '孩子' : fallback;
  }

  static StudentPairingChild fromJson(Map<String, dynamic> json) {
    return StudentPairingChild(
      id: _asString(json['id']),
      name: _asString(json['name']),
      nickname: _asString(json['nickname']),
    );
  }
}

class StudentQrChallengeLink {
  const StudentQrChallengeLink({required this.challengeId});

  final String challengeId;

  static StudentQrChallengeLink? tryParse({
    required String rawValue,
    required String studentWebBaseUrl,
  }) {
    final scanned = Uri.tryParse(rawValue.trim());
    final configuredOrigin = Uri.tryParse(studentWebBaseUrl.trim());
    if (scanned == null || configuredOrigin == null) return null;
    if (!_sameOrigin(scanned, configuredOrigin) ||
        scanned.userInfo.isNotEmpty ||
        scanned.fragment.isNotEmpty ||
        scanned.path != '/pair/qr') {
      return null;
    }

    final parameters = scanned.queryParametersAll;
    if (parameters.length != 1 || !parameters.containsKey('challengeId')) {
      return null;
    }
    final values = parameters['challengeId'] ?? const <String>[];
    if (values.length != 1) return null;
    final challengeId = values.single.trim();
    if (!_challengeIdPattern.hasMatch(challengeId)) return null;
    return StudentQrChallengeLink(challengeId: challengeId);
  }
}

class StudentQrChallenge {
  const StudentQrChallenge({
    required this.id,
    required this.status,
    required this.displayCode,
    required this.requestedAt,
    required this.expiresAt,
    required this.requiresPin,
    required this.pinConfigured,
    required this.clientDevice,
  });

  final String id;
  final String status;
  final String displayCode;
  final DateTime requestedAt;
  final DateTime expiresAt;
  final bool requiresPin;
  final bool pinConfigured;
  final StudentQrClientDevice clientDevice;

  bool get canApprove => status == 'pending';

  bool isExpiredAt(DateTime now) => !expiresAt.isAfter(now);

  static StudentQrChallenge fromJson(Map<String, dynamic> json) {
    final id = _asString(json['id'] ?? json['challengeId']);
    final requestedAtMs = _asInt(json['requestedAt']);
    final expiresAtMs = _asInt(json['expiresAt']);
    final displayCode = _asString(json['displayCode']);
    if (id.isEmpty ||
        !_displayCodePattern.hasMatch(displayCode) ||
        requestedAtMs <= 0 ||
        expiresAtMs <= 0) {
      throw const FormatException('Invalid QR challenge payload.');
    }
    return StudentQrChallenge(
      id: id,
      status: _asString(json['status']).toLowerCase(),
      displayCode: displayCode,
      requestedAt: DateTime.fromMillisecondsSinceEpoch(requestedAtMs),
      expiresAt: DateTime.fromMillisecondsSinceEpoch(expiresAtMs),
      requiresPin: json['requiresPin'] == true,
      pinConfigured: json['pinConfigured'] == true || json['hasPin'] == true,
      clientDevice: StudentQrClientDevice.fromJson(
        _asMap(json['clientDevice'] ?? json['device']),
      ),
    );
  }
}

class StudentQrClientDevice {
  const StudentQrClientDevice({
    required this.label,
    required this.browser,
    required this.platform,
    required this.osVersion,
    this.osName = '',
  });

  final String label;
  final String browser;
  final String platform;
  final String osVersion;
  final String osName;

  String get browserLabel {
    if (browser.isNotEmpty) return browser;
    if (label.isNotEmpty) return label;
    return '学习网页';
  }

  String get systemLabel {
    final parts = [
      osName.isNotEmpty ? osName : platform,
      osVersion,
    ].where((value) => value.isNotEmpty);
    final result = parts.join(' ');
    return result.isEmpty ? '未知系统' : result;
  }

  static StudentQrClientDevice fromJson(Map<String, dynamic> json) {
    return StudentQrClientDevice(
      label: _asString(json['label']),
      browser: _asString(
        json['browser'] ?? json['browserLabel'] ?? json['browserName'],
      ),
      platform: _asString(
        json['platform'] ?? json['system'] ?? json['systemLabel'],
      ),
      osVersion: _asString(json['osVersion']),
      osName: _asString(json['osName']),
    );
  }
}

class StudentQrApproval {
  const StudentQrApproval({
    required this.challengeId,
    required this.status,
    required this.message,
    required this.approvalExpiresAt,
  });

  final String challengeId;
  final String status;
  final String message;
  final DateTime approvalExpiresAt;

  Duration remainingAt(DateTime now) {
    if (!approvalExpiresAt.isAfter(now)) return Duration.zero;
    return approvalExpiresAt.difference(now);
  }

  static StudentQrApproval fromJson(Map<String, dynamic> json) {
    final challenge = _asMap(json['challenge']);
    final source = challenge.isEmpty ? json : challenge;
    final challengeId = _asString(
      source['id'] ?? source['challengeId'] ?? json['challengeId'],
    );
    final status = _asString(source['status'] ?? json['status']).toLowerCase();
    final approvalExpiresAtMs = _asInt(
      source['approvalExpiresAt'] ??
          source['approvedExpiresAt'] ??
          json['approvalExpiresAt'] ??
          json['approvedExpiresAt'],
    );
    if (challengeId.isEmpty || status.isEmpty || approvalExpiresAtMs <= 0) {
      throw const FormatException('Invalid QR approval payload.');
    }
    return StudentQrApproval(
      challengeId: challengeId,
      status: status,
      message: _asString(json['message']),
      approvalExpiresAt: DateTime.fromMillisecondsSinceEpoch(
        approvalExpiresAtMs,
      ),
    );
  }
}

class StudentQrRejection {
  const StudentQrRejection({
    required this.challengeId,
    required this.status,
    required this.rejectedAt,
  });

  final String challengeId;
  final String status;
  final DateTime rejectedAt;

  static StudentQrRejection fromJson(Map<String, dynamic> json) {
    final challengeId = _asString(json['challengeId'] ?? json['id']);
    final status = _asString(json['status']).toLowerCase();
    final rejectedAtMs = _asInt(json['rejectedAt']);
    if (challengeId.isEmpty || status != 'rejected' || rejectedAtMs <= 0) {
      throw const FormatException('Invalid QR rejection payload.');
    }
    return StudentQrRejection(
      challengeId: challengeId,
      status: status,
      rejectedAt: DateTime.fromMillisecondsSinceEpoch(rejectedAtMs),
    );
  }
}

class StudentAuthorizationList {
  const StudentAuthorizationList({required this.childId, required this.items});

  final String childId;
  final List<StudentAuthorization> items;

  factory StudentAuthorizationList.fromJson(Map<String, dynamic> json) {
    final rawItems = json['authorizations'];
    return StudentAuthorizationList(
      childId: _asString(json['childId']),
      items: rawItems is List
          ? rawItems
                .map((item) => StudentAuthorization.fromJson(_asMap(item)))
                .where((item) => item.id.isNotEmpty)
                .toList(growable: false)
          : const [],
    );
  }
}

class StudentAuthorization {
  const StudentAuthorization({
    required this.id,
    required this.displayName,
    required this.deviceType,
    required this.platform,
    required this.status,
    required this.trustedUntil,
    required this.lastUsedAt,
    required this.createdAt,
    required this.sessions,
  });

  final String id;
  final String displayName;
  final String deviceType;
  final String platform;
  final String status;
  final DateTime trustedUntil;
  final DateTime lastUsedAt;
  final DateTime createdAt;
  final List<StudentAuthorizationSession> sessions;

  bool get isActive => status == 'active';

  factory StudentAuthorization.fromJson(Map<String, dynamic> json) {
    final rawSessions = json['sessions'];
    return StudentAuthorization(
      id: _asString(json['id']),
      displayName: _asString(json['displayName']),
      deviceType: _asString(json['deviceType']),
      platform: _asString(json['platform']),
      status: _asString(json['status']).toLowerCase(),
      trustedUntil: _dateTimeFromMilliseconds(json['trustedUntil']),
      lastUsedAt: _dateTimeFromMilliseconds(json['lastUsedAt']),
      createdAt: _dateTimeFromMilliseconds(json['createdAt']),
      sessions: rawSessions is List
          ? rawSessions
                .map(
                  (item) => StudentAuthorizationSession.fromJson(_asMap(item)),
                )
                .where((item) => item.id.isNotEmpty)
                .toList(growable: false)
          : const [],
    );
  }
}

class StudentAuthorizationSession {
  const StudentAuthorizationSession({
    required this.id,
    required this.status,
    required this.lastUsedAt,
    required this.createdAt,
  });

  final String id;
  final String status;
  final DateTime lastUsedAt;
  final DateTime createdAt;

  factory StudentAuthorizationSession.fromJson(Map<String, dynamic> json) {
    return StudentAuthorizationSession(
      id: _asString(json['id']),
      status: _asString(json['status']).toLowerCase(),
      lastUsedAt: _dateTimeFromMilliseconds(json['lastUsedAt']),
      createdAt: _dateTimeFromMilliseconds(json['createdAt']),
    );
  }
}

class StudentAuthorizationRevocation {
  const StudentAuthorizationRevocation({
    required this.authorizationId,
    required this.status,
    required this.alreadyRevoked,
    required this.revokedSessionCount,
    required this.revokedAt,
  });

  final String authorizationId;
  final String status;
  final bool alreadyRevoked;
  final int revokedSessionCount;
  final DateTime revokedAt;

  factory StudentAuthorizationRevocation.fromJson(Map<String, dynamic> json) {
    return StudentAuthorizationRevocation(
      authorizationId: _asString(json['authorizationId']),
      status: _asString(json['status']).toLowerCase(),
      alreadyRevoked: json['alreadyRevoked'] == true,
      revokedSessionCount: _asInt(json['revokedSessionCount']),
      revokedAt: _dateTimeFromMilliseconds(json['revokedAt']),
    );
  }
}

class StudentPinResetResult {
  const StudentPinResetResult({
    required this.childId,
    required this.updatedAt,
    required this.revokedSessionCount,
    required this.trustedDeviceCount,
    required this.existingDevicesRemainTrusted,
    required this.requiresUnlockWithNewPin,
  });

  final String childId;
  final DateTime updatedAt;
  final int revokedSessionCount;
  final int trustedDeviceCount;
  final bool existingDevicesRemainTrusted;
  final bool requiresUnlockWithNewPin;

  factory StudentPinResetResult.fromJson(Map<String, dynamic> json) {
    return StudentPinResetResult(
      childId: _asString(json['childId']),
      updatedAt: _dateTimeFromMilliseconds(json['pinUpdatedAt']),
      revokedSessionCount: _asInt(json['revokedSessionCount']),
      trustedDeviceCount: _asInt(json['trustedDeviceCount']),
      existingDevicesRemainTrusted:
          json['existingDevicesRemainTrusted'] == true,
      requiresUnlockWithNewPin: json['requiresUnlockWithNewPin'] == true,
    );
  }
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}

String _asString(dynamic value) => value?.toString().trim() ?? '';

int _asInt(dynamic value) {
  return switch (value) {
    int number => number,
    num number => number.toInt(),
    String text => int.tryParse(text.trim()) ?? 0,
    _ => 0,
  };
}

DateTime _dateTimeFromMilliseconds(dynamic value) {
  return DateTime.fromMillisecondsSinceEpoch(_asInt(value));
}

final _challengeIdPattern = RegExp(r'^msc_[A-Za-z0-9_-]{40,96}$');
final _displayCodePattern = RegExp(r'^\d{4}$');

bool _sameOrigin(Uri first, Uri second) {
  return first.scheme.toLowerCase() == second.scheme.toLowerCase() &&
      first.host.toLowerCase() == second.host.toLowerCase() &&
      _effectivePort(first) == _effectivePort(second);
}

int _effectivePort(Uri uri) {
  if (uri.hasPort) return uri.port;
  return uri.scheme.toLowerCase() == 'https' ? 443 : 80;
}
