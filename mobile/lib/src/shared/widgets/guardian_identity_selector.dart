import 'package:flutter/material.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/shared/domain/guardian_identity.dart';
import 'package:warm_sight/src/shared/widgets/app_segmented_control.dart';
import 'package:warm_sight/src/shared/widgets/guardian_identity_card_selector.dart';

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
        GuardianIdentityGroupSegmentedControl(
          key: groupKey,
          label: groupLabel,
          groups: options.identityGroups,
          selectedKey: groupKeyValue,
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

class GuardianIdentityGroupSegmentedControl extends StatelessWidget {
  const GuardianIdentityGroupSegmentedControl({
    required this.groups,
    required this.selectedKey,
    required this.onChanged,
    this.label = '家庭身份',
    super.key,
  });

  final List<GuardianIdentityGroupOption> groups;
  final String selectedKey;
  final ValueChanged<String> onChanged;
  final String label;

  @override
  Widget build(BuildContext context) {
    if (groups.isEmpty) return const SizedBox.shrink();
    final selectedIndex = groups
        .indexWhere((group) => group.key == selectedKey)
        .clamp(0, groups.length - 1)
        .toInt();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            color: AppColors.ink,
            fontFamily: AppTypography.systemFont,
            fontSize: 12.5,
            fontWeight: FontWeight.w900,
            letterSpacing: 0,
            height: 1.1,
          ),
        ),
        const SizedBox(height: 7),
        AppSegmentedControl<String>(
          value: groups[selectedIndex].key,
          semanticLabel: label,
          compact: true,
          onChanged: onChanged,
          options: [
            for (final group in groups)
              AppSegmentOption<String>(
                value: group.key,
                label: group.label,
                key: ValueKey('guardianIdentityGroupOption_${group.key}'),
              ),
          ],
        ),
      ],
    );
  }
}
