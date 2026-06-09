import 'package:flutter/material.dart';
import 'package:guardian_parent_app/src/shared/domain/guardian_identity.dart';
import 'package:guardian_parent_app/src/shared/widgets/adaptive_select_field.dart';
import 'package:guardian_parent_app/src/shared/widgets/guardian_identity_card_selector.dart';

class GuardianIdentitySelector extends StatelessWidget {
  const GuardianIdentitySelector({
    required this.options,
    required this.value,
    required this.onChanged,
    this.groupKey,
    this.cardListKey,
    this.cardKeyPrefix = 'guardianIdentityCard',
    this.groupLabel = '家庭身份',
    this.cardLabel = '显示称呼',
    this.icon = Icons.family_restroom_outlined,
    this.spacing = 12,
    this.disabledKeys = const {},
    super.key,
  });

  final GuardianIdentityOptions options;
  final String value;
  final ValueChanged<String> onChanged;
  final Key? groupKey;
  final Key? cardListKey;
  final String cardKeyPrefix;
  final String groupLabel;
  final String cardLabel;
  final IconData icon;
  final double spacing;
  final Set<String> disabledKeys;

  @override
  Widget build(BuildContext context) {
    final valueKey = options.keyForValue(value);
    final selectedGroup = options.groupForValue(
      valueKey.isNotEmpty ? valueKey : options.defaultKey,
    );
    final groupKeyValue = selectedGroup?.key ?? options.defaultGroupKey;
    final selectedKey = valueKey.isNotEmpty
        ? valueKey
        : options.firstSelectableKeyForGroup(groupKeyValue, disabledKeys);

    return Column(
      children: [
        AdaptiveSelectField<String>(
          key: groupKey,
          icon: icon,
          label: groupLabel,
          value: groupKeyValue,
          options: [
            for (final option in options.identityGroups)
              AdaptiveSelectOption(value: option.key, label: option.label),
          ],
          onChanged: (nextGroupKey) {
            onChanged(
              options.firstSelectableKeyForGroup(nextGroupKey, disabledKeys),
            );
          },
        ),
        SizedBox(height: spacing),
        GuardianIdentityCardSelector(
          key: cardListKey,
          keyPrefix: cardKeyPrefix,
          label: cardLabel,
          options: selectedGroup?.labels ?? const [],
          value: selectedKey,
          disabledKeys: disabledKeys,
          onChanged: onChanged,
        ),
      ],
    );
  }
}
