import 'package:flutter/material.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/shared/domain/guardian_identity.dart';

class GuardianIdentityCardSelector extends StatelessWidget {
  const GuardianIdentityCardSelector({
    required this.options,
    required this.value,
    required this.onChanged,
    this.label = '显示称呼',
    this.keyPrefix = 'guardianIdentityCard',
    this.disabledKeys = const {},
    super.key,
  });

  final List<GuardianIdentityLabelOption> options;
  final String value;
  final ValueChanged<String> onChanged;
  final String label;
  final String keyPrefix;
  final Set<String> disabledKeys;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            color: AppColors.muted,
            fontFamily: AppTypography.systemFont,
            fontSize: 12,
            fontWeight: FontWeight.w800,
            letterSpacing: 0,
          ),
        ),
        const SizedBox(height: 9),
        LayoutBuilder(
          builder: (context, constraints) {
            if (options.isEmpty) return const _EmptyIdentityOptions();
            const gap = 10.0;
            final columns = constraints.maxWidth < 300 ? 1 : 2;
            final width =
                (constraints.maxWidth - gap * (columns - 1)) / columns;
            return Wrap(
              spacing: gap,
              runSpacing: gap,
              children: [
                for (final option in options)
                  SizedBox(
                    width: width,
                    child: _GuardianIdentityCard(
                      key: ValueKey('${keyPrefix}_${option.label}'),
                      option: option,
                      disabled: disabledKeys.contains(option.key),
                      selected:
                          value.trim() == option.key ||
                          value.trim() == option.label,
                      onTap: () => onChanged(option.key),
                    ),
                  ),
              ],
            );
          },
        ),
      ],
    );
  }
}

class _GuardianIdentityCard extends StatelessWidget {
  const _GuardianIdentityCard({
    required this.option,
    required this.selected,
    required this.disabled,
    required this.onTap,
    super.key,
  });

  final GuardianIdentityLabelOption option;
  final bool selected;
  final bool disabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final borderColor = selected ? AppColors.brandSoft : AppColors.borderSoft;

    return Semantics(
      button: true,
      enabled: !disabled,
      selected: selected,
      label: disabled ? '${option.label}已存在' : '选择${option.label}',
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(18),
          onTap: disabled ? null : onTap,
          child: AnimatedContainer(
            duration: AppMotion.duration(context, 180),
            curve: Curves.easeOutCubic,
            decoration: BoxDecoration(
              color: disabled
                  ? AppColors.surfaceSoft.withValues(alpha: 0.64)
                  : selected
                  ? AppColors.brandWash.withValues(alpha: 0.34)
                  : AppColors.surfaceElevated,
              borderRadius: BorderRadius.circular(18),
              border: Border.all(
                color: disabled ? AppColors.borderSoft : borderColor,
                width: selected ? 1.4 : 1,
              ),
            ),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(8, 8, 8, 10),
              child: Stack(
                children: [
                  Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      DecoratedBox(
                        decoration: BoxDecoration(
                          color: selected
                              ? AppColors.brandWash.withValues(alpha: 0.72)
                              : AppColors.surfaceTinted,
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: SizedBox(
                          height: 74,
                          width: double.infinity,
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(14),
                            child: Image.asset(
                              option.imageAsset,
                              fit: BoxFit.contain,
                              alignment: Alignment.bottomCenter,
                              opacity: disabled
                                  ? const AlwaysStoppedAnimation(0.42)
                                  : null,
                              filterQuality: FilterQuality.medium,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 9),
                      Text(
                        option.label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: AppColors.ink,
                          fontFamily: AppTypography.systemFont,
                          fontSize: 14,
                          fontWeight: FontWeight.w900,
                          letterSpacing: 0,
                        ),
                      ),
                    ],
                  ),
                  if (disabled)
                    Positioned(
                      right: 0,
                      top: 0,
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          color: AppColors.surface,
                          borderRadius: BorderRadius.circular(AppRadii.full),
                          border: Border.all(color: AppColors.borderSoft),
                        ),
                        child: const Padding(
                          padding: EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 4,
                          ),
                          child: Text(
                            '已存在',
                            style: TextStyle(
                              color: AppColors.muted,
                              fontFamily: AppTypography.systemFont,
                              fontSize: 10,
                              fontWeight: FontWeight.w800,
                              letterSpacing: 0,
                            ),
                          ),
                        ),
                      ),
                    )
                  else if (selected)
                    Positioned(
                      right: 2,
                      top: 2,
                      child: DecoratedBox(
                        decoration: const BoxDecoration(
                          color: AppColors.brand,
                          shape: BoxShape.circle,
                        ),
                        child: const SizedBox(
                          width: 24,
                          height: 24,
                          child: Center(
                            child: Icon(
                              Icons.check_rounded,
                              color: Colors.white,
                              size: 16,
                            ),
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _EmptyIdentityOptions extends StatelessWidget {
  const _EmptyIdentityOptions();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.borderSoft),
      ),
      child: const SizedBox(
        width: double.infinity,
        height: 54,
        child: Center(
          child: Text(
            '暂未配置可选称呼',
            style: TextStyle(
              color: AppColors.muted,
              fontFamily: AppTypography.systemFont,
              fontSize: 13,
              fontWeight: FontWeight.w700,
              letterSpacing: 0,
            ),
          ),
        ),
      ),
    );
  }
}
