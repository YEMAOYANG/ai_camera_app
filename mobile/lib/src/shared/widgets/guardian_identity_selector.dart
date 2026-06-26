import 'package:flutter/material.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/shared/domain/guardian_identity.dart';
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
        LayoutBuilder(
          builder: (context, constraints) {
            final width = constraints.maxWidth;
            final segmentWidth = width / groups.length;
            return SizedBox(
              height: AppControls.minTouchTarget,
              child: Center(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: AppColors.surfaceStrong.withValues(alpha: 0.62),
                    borderRadius: BorderRadius.circular(AppRadii.full),
                    border: Border.all(color: AppColors.borderSoft),
                  ),
                  child: SizedBox(
                    height: 36,
                    child: Stack(
                      children: [
                        AnimatedPositioned(
                          duration: AppMotion.duration(context, 190),
                          curve: Curves.easeOutCubic,
                          left: selectedIndex * segmentWidth + 3,
                          top: 3,
                          width: segmentWidth - 6,
                          height: 30,
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              color: AppColors.brandDeep,
                              borderRadius: BorderRadius.circular(
                                AppRadii.full,
                              ),
                              boxShadow: [
                                BoxShadow(
                                  color: AppColors.brandDeep.withValues(
                                    alpha: 0.16,
                                  ),
                                  blurRadius: 8,
                                  offset: const Offset(0, 3),
                                ),
                              ],
                            ),
                          ),
                        ),
                        Row(
                          children: [
                            for (final group in groups)
                              Expanded(
                                child: _GuardianIdentityGroupSegmentButton(
                                  key: ValueKey(
                                    'guardianIdentityGroupOption_${group.key}',
                                  ),
                                  label: group.label,
                                  selected: group.key == selectedKey,
                                  onTap: () => onChanged(group.key),
                                ),
                              ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ],
    );
  }
}

class _GuardianIdentityGroupSegmentButton extends StatelessWidget {
  const _GuardianIdentityGroupSegmentButton({
    required this.label,
    required this.selected,
    required this.onTap,
    super.key,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      label: '家庭身份，$label',
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Center(
          child: AnimatedDefaultTextStyle(
            duration: AppMotion.duration(context, 160),
            curve: Curves.easeOutCubic,
            style: TextStyle(
              color: selected ? Colors.white : AppColors.muted,
              fontFamily: AppTypography.systemFont,
              fontSize: 13,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
              height: 1,
            ),
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
            ),
          ),
        ),
      ),
    );
  }
}
