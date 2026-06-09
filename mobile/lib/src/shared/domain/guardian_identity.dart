class GuardianIdentityOptions {
  const GuardianIdentityOptions({
    required this.identityGroups,
    required this.familyRoles,
  });

  final List<GuardianIdentityGroupOption> identityGroups;
  final List<FamilyRoleOption> familyRoles;

  bool get isEmpty => identityGroups.isEmpty || familyRoles.isEmpty;

  List<GuardianIdentityLabelOption> get allLabels {
    return [for (final group in identityGroups) ...group.labels];
  }

  GuardianIdentityGroupOption? groupForKey(String key) {
    final normalized = key.trim();
    for (final group in identityGroups) {
      if (group.key == normalized) return group;
    }
    return null;
  }

  GuardianIdentityGroupOption? groupForLabel(String value) {
    final normalized = normalizeLabel(value);
    for (final group in identityGroups) {
      if (group.hasLabel(normalized)) return group;
    }
    return identityGroups.isEmpty ? null : identityGroups.first;
  }

  GuardianIdentityGroupOption? groupForValue(String value) {
    final trimmed = value.trim();
    for (final group in identityGroups) {
      if (group.labelFor(trimmed) != null) return group;
    }
    return identityGroups.isEmpty ? null : identityGroups.first;
  }

  GuardianIdentityLabelOption? optionForKey(String key) {
    final trimmed = key.trim();
    if (trimmed.isEmpty) return null;
    for (final group in identityGroups) {
      for (final option in group.labels) {
        if (option.key == trimmed) return option;
      }
    }
    return null;
  }

  GuardianIdentityLabelOption? optionForValue(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) return null;
    for (final group in identityGroups) {
      final option = group.labelFor(trimmed);
      if (option != null) return option;
    }
    return null;
  }

  String keyForValue(String value) {
    return optionForValue(value)?.key ?? '';
  }

  String labelForKey(String key) {
    return optionForKey(key)?.label ?? '';
  }

  String defaultLabelForGroupKey(String key) {
    return groupForKey(key)?.defaultLabel ?? defaultLabel;
  }

  String defaultKeyForGroupKey(String key) {
    return groupForKey(key)?.defaultKey ?? defaultKey;
  }

  String normalizeLabel(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) return defaultLabel;
    for (final group in identityGroups) {
      final option = group.labelFor(trimmed);
      if (option != null) return option.label;
    }
    return defaultLabel;
  }

  String labelForStoredValue(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) return '';
    for (final group in identityGroups) {
      if (group.key == trimmed || group.label == trimmed) {
        return group.defaultLabel;
      }
      final option = group.labelFor(trimmed);
      if (option != null) return option.label;
    }
    return trimmed;
  }

  String imageAssetForLabel(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) return '';
    for (final group in identityGroups) {
      final option = group.labelFor(trimmed);
      if (option != null) return option.imageAsset;
    }
    return '';
  }

  String imageAssetForKey(String key) {
    return optionForKey(key)?.imageAsset ?? '';
  }

  bool isExclusiveIdentityKey(String key) {
    return exclusiveGuardianIdentityKeys.contains(key.trim());
  }

  String firstSelectableKeyForGroup(
    String groupKey,
    Set<String> disabledKeys, {
    String preferredKey = '',
  }) {
    final group = groupForKey(groupKey);
    if (group == null) return defaultKey;
    final preferred = preferredKey.trim();
    if (preferred.isNotEmpty &&
        group.labelFor(preferred) != null &&
        !disabledKeys.contains(preferred)) {
      return preferred;
    }
    for (final option in group.labels) {
      if (!disabledKeys.contains(option.key)) return option.key;
    }
    return group.defaultKey;
  }

  String get defaultGroupKey {
    return identityGroups.isEmpty ? '' : identityGroups.first.key;
  }

  String get defaultLabel {
    if (identityGroups.isEmpty) return '';
    return identityGroups.first.defaultLabel;
  }

  String get defaultKey {
    if (identityGroups.isEmpty) return '';
    return identityGroups.first.defaultKey;
  }

  String get defaultRoleKey {
    return familyRoles.isEmpty ? '' : familyRoles.first.key;
  }

  String roleKeyFor(String value) {
    final normalized = value.trim();
    if (normalized.isEmpty) return defaultRoleKey;
    for (final role in familyRoles) {
      if (role.key == normalized || role.label == normalized) return role.key;
    }
    return defaultRoleKey;
  }

  String roleLabelFor(String key) {
    final normalized = key.trim();
    for (final role in familyRoles) {
      if (role.key == normalized || role.label == normalized) return role.label;
    }
    return normalized;
  }

  static GuardianIdentityOptions fromJson(Map<String, dynamic> json) {
    final groups = json['identityGroups'];
    final roles = json['familyRoles'];
    return GuardianIdentityOptions(
      identityGroups: groups is List
          ? groups
                .map(
                  (item) => GuardianIdentityGroupOption.fromJson(_asMap(item)),
                )
                .where((item) => item.labels.isNotEmpty)
                .toList()
          : const [],
      familyRoles: roles is List
          ? roles
                .map((item) => FamilyRoleOption.fromJson(_asMap(item)))
                .toList()
          : const [],
    );
  }
}

class GuardianIdentityGroupOption {
  const GuardianIdentityGroupOption({
    required this.key,
    required this.label,
    required this.defaultKey,
    required this.defaultLabel,
    required this.labels,
    this.description = '',
  });

  final String key;
  final String label;
  final String defaultKey;
  final String defaultLabel;
  final String description;
  final List<GuardianIdentityLabelOption> labels;

  bool hasLabel(String value) => labelFor(value) != null;

  GuardianIdentityLabelOption? labelFor(String value) {
    final normalized = value.trim();
    for (final option in labels) {
      if (option.label == normalized || option.key == normalized) return option;
    }
    return null;
  }

  static GuardianIdentityGroupOption fromJson(Map<String, dynamic> json) {
    final rawLabels = json['labels'];
    final labels = rawLabels is List
        ? rawLabels
              .map((item) => GuardianIdentityLabelOption.fromJson(_asMap(item)))
              .where((item) => item.label.isNotEmpty)
              .toList()
        : <GuardianIdentityLabelOption>[];
    final defaultLabel = _asString(json['defaultLabel']);
    final defaultKey = _asString(json['defaultKey']);
    final first = labels.isEmpty ? null : labels.first;
    return GuardianIdentityGroupOption(
      key: _asString(json['key']),
      label: _asString(json['label']),
      description: _asString(json['description']),
      defaultKey: defaultKey.isNotEmpty ? defaultKey : first?.key ?? '',
      defaultLabel: defaultLabel.isNotEmpty ? defaultLabel : first?.label ?? '',
      labels: labels,
    );
  }
}

class GuardianIdentityLabelOption {
  const GuardianIdentityLabelOption({
    required this.key,
    required this.label,
    required this.imageAsset,
    this.description = '',
  });

  final String key;
  final String label;
  final String imageAsset;
  final String description;

  static GuardianIdentityLabelOption fromJson(Map<String, dynamic> json) {
    return GuardianIdentityLabelOption(
      key: _asString(json['key']),
      label: _asString(json['label']),
      description: _asString(json['description']),
      imageAsset: _asString(json['imageAsset']),
    );
  }
}

class FamilyRoleOption {
  const FamilyRoleOption({
    required this.key,
    required this.label,
    this.description = '',
  });

  final String key;
  final String label;
  final String description;

  static FamilyRoleOption fromJson(Map<String, dynamic> json) {
    return FamilyRoleOption(
      key: _asString(json['key']),
      label: _asString(json['label']),
      description: _asString(json['description']),
    );
  }
}

const exclusiveGuardianIdentityKeys = {
  'mom',
  'dad',
  'maternal_grandpa',
  'maternal_grandma',
  'grandpa',
  'grandma',
};

String _asString(dynamic value, {String fallback = ''}) {
  return value is String && value.isNotEmpty ? value : fallback;
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}
