import 'package:flutter/material.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';

class AppCompactToggle extends StatelessWidget {
  const AppCompactToggle({
    required this.value,
    required this.onChanged,
    this.label,
    super.key,
  });

  final bool value;
  final ValueChanged<bool>? onChanged;
  final String? label;

  @override
  Widget build(BuildContext context) {
    final enabled = onChanged != null;
    final trackColor = !enabled
        ? AppColors.disabledBg
        : value
        ? AppColors.primary
        : AppColors.disabledBg;
    final borderColor = value
        ? AppColors.primary.withValues(alpha: 0.22)
        : AppColors.border;
    final thumbColor = enabled ? Colors.white : AppColors.surfaceSoft;

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: enabled ? () => onChanged!(!value) : null,
      child: Semantics(
        button: true,
        toggled: value,
        label: label,
        onTap: enabled ? () => onChanged!(!value) : null,
        child: SizedBox(
          width: 50,
          height: 36,
          child: Center(
            child: AnimatedContainer(
              duration: AppMotion.duration(context, 160),
              curve: Curves.easeOutCubic,
              width: 42,
              height: 24,
              decoration: BoxDecoration(
                color: trackColor,
                borderRadius: BorderRadius.circular(AppRadii.full),
                border: Border.all(color: borderColor),
              ),
              child: AnimatedAlign(
                duration: AppMotion.duration(context, 160),
                curve: Curves.easeOutCubic,
                alignment: value ? Alignment.centerRight : Alignment.centerLeft,
                child: Padding(
                  padding: const EdgeInsets.all(2),
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: thumbColor,
                      borderRadius: BorderRadius.circular(AppRadii.full),
                      boxShadow: [
                        BoxShadow(
                          color: AppColors.primaryButtonShadow.withValues(
                            alpha: value ? 0.12 : 0.05,
                          ),
                          blurRadius: value ? 5 : 3,
                          offset: const Offset(0, 1.5),
                        ),
                      ],
                    ),
                    child: const SizedBox(width: 18, height: 18),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
