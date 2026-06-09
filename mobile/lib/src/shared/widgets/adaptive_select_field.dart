import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';

class AdaptiveSelectOption<T> {
  const AdaptiveSelectOption({required this.value, required this.label});

  final T value;
  final String label;
}

class AdaptiveSelectField<T> extends StatelessWidget {
  const AdaptiveSelectField({
    required this.label,
    required this.value,
    required this.options,
    required this.onChanged,
    this.icon,
    this.subtitle,
    this.enabled = true,
    super.key,
  });

  final String label;
  final T value;
  final List<AdaptiveSelectOption<T>> options;
  final ValueChanged<T> onChanged;
  final IconData? icon;
  final String? subtitle;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final option = _selectedOption;
    final platform = Theme.of(context).platform;
    final useCupertino =
        platform == TargetPlatform.iOS || platform == TargetPlatform.macOS;

    if (useCupertino) {
      return _SelectShell(
        label: label,
        value: option.label,
        icon: icon,
        subtitle: subtitle,
        enabled: enabled,
        onTap: enabled ? () => _showCupertinoPicker(context) : null,
      );
    }

    return _SelectShell(
      label: label,
      value: option.label,
      icon: icon,
      subtitle: subtitle,
      enabled: enabled,
      onTap: enabled ? () => _showMaterialMenu(context) : null,
    );
  }

  AdaptiveSelectOption<T> get _selectedOption {
    for (final option in options) {
      if (option.value == value) return option;
    }
    return options.first;
  }

  Future<void> _showCupertinoPicker(BuildContext context) async {
    var selectedIndex = options.indexWhere((option) => option.value == value);
    if (selectedIndex < 0) selectedIndex = 0;
    var pendingIndex = selectedIndex;
    await showCupertinoModalPopup<void>(
      context: context,
      builder: (context) {
        return Container(
          height: 304,
          color: CupertinoColors.systemBackground.resolveFrom(context),
          child: Column(
            children: [
              SizedBox(
                height: 48,
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    CupertinoButton(
                      padding: const EdgeInsets.symmetric(horizontal: 18),
                      onPressed: () {
                        Navigator.of(context).pop();
                        onChanged(options[pendingIndex].value);
                      },
                      child: const Text('完成'),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: CupertinoPicker(
                  scrollController: FixedExtentScrollController(
                    initialItem: selectedIndex,
                  ),
                  itemExtent: 44,
                  onSelectedItemChanged: (index) => pendingIndex = index,
                  children: [
                    for (final option in options)
                      Center(
                        child: Text(
                          option.label,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Future<void> _showMaterialMenu(BuildContext context) async {
    final renderBox = context.findRenderObject() as RenderBox?;
    final overlay =
        Navigator.of(context).overlay?.context.findRenderObject() as RenderBox?;
    if (renderBox == null || overlay == null) return;
    final topLeft = renderBox.localToGlobal(Offset.zero, ancestor: overlay);
    final bottomRight = renderBox.localToGlobal(
      renderBox.size.bottomRight(Offset.zero),
      ancestor: overlay,
    );
    final selected = await showMenu<T>(
      context: context,
      position: RelativeRect.fromRect(
        Rect.fromPoints(topLeft, bottomRight),
        Offset.zero & overlay.size,
      ),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      items: [
        for (final option in options)
          PopupMenuItem<T>(
            value: option.value,
            child: Text(
              option.label,
              style: const TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 14,
                fontWeight: FontWeight.w800,
                letterSpacing: 0,
              ),
            ),
          ),
      ],
    );
    if (selected != null) onChanged(selected);
  }
}

class _SelectShell extends StatelessWidget {
  const _SelectShell({
    required this.label,
    required this.value,
    required this.enabled,
    this.icon,
    this.subtitle,
    this.onTap,
  });

  final String label;
  final String value;
  final bool enabled;
  final IconData? icon;
  final String? subtitle;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final content = Row(
      children: [
        if (icon != null) ...[
          DecoratedBox(
            decoration: BoxDecoration(
              color: AppColors.brand.withValues(alpha: 0.10),
              borderRadius: BorderRadius.circular(14),
            ),
            child: SizedBox(
              width: 38,
              height: 38,
              child: Center(
                child: Icon(icon, color: AppColors.brand, size: 19),
              ),
            ),
          ),
          const SizedBox(width: 11),
        ],
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: const TextStyle(
                  color: AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0,
                ),
              ),
              const SizedBox(height: 5),
              Text(
                value,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: AppColors.ink,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 15,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
              if (subtitle != null) ...[
                const SizedBox(height: 5),
                Text(
                  subtitle!,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    height: 1.35,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(width: 8),
        Icon(
          Icons.keyboard_arrow_down_rounded,
          color: enabled ? AppColors.subtle : AppColors.muted,
          size: 22,
        ),
      ],
    );

    return Semantics(
      button: true,
      enabled: enabled,
      label: '$label，当前$value',
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(18),
          onTap: onTap,
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: AppColors.borderSoft),
            ),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(13, 12, 12, 12),
              child: content,
            ),
          ),
        ),
      ),
    );
  }
}
