import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_button.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_surface.dart';

Future<T?> showAppBottomSheet<T>({
  required BuildContext context,
  required Widget child,
  double maxHeightFactor = 0.72,
}) {
  return showModalBottomSheet<T>(
    context: context,
    useRootNavigator: true,
    isScrollControlled: true,
    backgroundColor: AppColors.appBackgroundWarm,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
    ),
    builder: (context) {
      return AppBottomSheetFrame(
        maxHeightFactor: maxHeightFactor,
        child: child,
      );
    },
  );
}

Future<T?> showAppPickerSheet<T>({
  required BuildContext context,
  required String title,
  required List<AppPickerOption<T>> options,
  T? selected,
  String? subtitle,
  double maxHeightFactor = 0.68,
}) {
  return showAppBottomSheet<T>(
    context: context,
    maxHeightFactor: maxHeightFactor,
    child: AppPickerSheet<T>(
      title: title,
      subtitle: subtitle,
      options: options,
      selected: selected,
    ),
  );
}

Future<bool> showAppConfirmSheet({
  required BuildContext context,
  required String title,
  required String message,
  String confirmLabel = '确认',
  String cancelLabel = '取消',
  bool danger = false,
}) async {
  return await showAppBottomSheet<bool>(
        context: context,
        maxHeightFactor: 0.46,
        child: AppConfirmSheet(
          title: title,
          message: message,
          confirmLabel: confirmLabel,
          cancelLabel: cancelLabel,
          danger: danger,
        ),
      ) ??
      false;
}

class AppBottomSheetFrame extends StatelessWidget {
  const AppBottomSheetFrame({
    required this.child,
    this.maxHeightFactor = 0.72,
    super.key,
  });

  final Widget child;
  final double maxHeightFactor;

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.viewInsetsOf(context).bottom;
    final size = MediaQuery.sizeOf(context);
    final viewPadding = MediaQuery.viewPaddingOf(context);
    final topGap = viewPadding.top + 12;
    final availableHeight = math.max(280.0, size.height - bottomInset - topGap);
    final preferredHeight = size.height * maxHeightFactor.clamp(0.32, 0.94);
    final maxHeight = math.min(preferredHeight, availableHeight);
    return Padding(
      padding: EdgeInsets.only(bottom: bottomInset),
      child: SafeArea(
        top: false,
        bottom: true,
        child: ConstrainedBox(
          constraints: BoxConstraints(maxHeight: maxHeight),
          child: child,
        ),
      ),
    );
  }
}

class AppBottomSheetBody extends StatelessWidget {
  const AppBottomSheetBody({
    required this.title,
    required this.child,
    this.subtitle,
    this.scrollable = true,
    this.wrapScrollableChild = true,
    this.padding = const EdgeInsets.fromLTRB(20, 8, 20, 12),
    this.handleTitleGap = 10,
    this.headerBottomGap = 16,
    this.titleFontSize = 22,
    this.subtitleFontSize = 13,
    this.subtitleLineHeight = 1.45,
    this.footer,
    super.key,
  });

  final String title;
  final String? subtitle;
  final Widget child;
  final bool scrollable;
  final bool wrapScrollableChild;
  final EdgeInsetsGeometry padding;
  final double handleTitleGap;
  final double headerBottomGap;
  final double titleFontSize;
  final double subtitleFontSize;
  final double subtitleLineHeight;
  final Widget? footer;

  @override
  Widget build(BuildContext context) {
    final header = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const AppSheetHandle(),
        SizedBox(height: handleTitleGap),
        Text(
          title,
          style: TextStyle(
            color: AppColors.ink,
            fontFamily: AppTypography.systemFont,
            fontSize: titleFontSize,
            fontWeight: FontWeight.w900,
            letterSpacing: 0,
          ),
        ),
        if (subtitle != null) ...[
          const SizedBox(height: 6),
          Text(
            subtitle!,
            style: TextStyle(
              color: AppColors.muted,
              fontFamily: AppTypography.systemFont,
              fontSize: subtitleFontSize,
              fontWeight: FontWeight.w700,
              height: subtitleLineHeight,
              letterSpacing: 0,
            ),
          ),
        ],
        SizedBox(height: headerBottomGap),
      ],
    );

    final content = Padding(
      padding: padding,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          header,
          if (scrollable)
            Expanded(
              child: wrapScrollableChild
                  ? SingleChildScrollView(
                      keyboardDismissBehavior:
                          ScrollViewKeyboardDismissBehavior.onDrag,
                      padding: const EdgeInsets.only(bottom: 12),
                      child: child,
                    )
                  : child,
            )
          else
            child,
          if (footer != null) ...[const SizedBox(height: 12), footer!],
        ],
      ),
    );

    if (scrollable) return content;
    return SingleChildScrollView(
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      child: content,
    );
  }
}

class AppSheetHandle extends StatelessWidget {
  const AppSheetHandle({super.key});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 36,
      child: Stack(
        children: [
          Align(
            alignment: Alignment.center,
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: AppColors.muted.withValues(alpha: 0.54),
                borderRadius: BorderRadius.circular(AppRadii.full),
              ),
              child: const SizedBox(width: 36, height: 4),
            ),
          ),
          Align(
            alignment: Alignment.centerRight,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => Navigator.of(context).pop(),
              child: Semantics(
                button: true,
                label: '关闭',
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.72),
                    borderRadius: BorderRadius.circular(AppRadii.full),
                    border: Border.all(color: AppColors.borderSoft),
                  ),
                  child: const SizedBox(
                    width: 34,
                    height: 34,
                    child: Center(
                      child: Icon(
                        Icons.close,
                        color: AppColors.muted,
                        size: 18,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class AppSheetFooterActions extends StatelessWidget {
  const AppSheetFooterActions({required this.children, super.key});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (var index = 0; index < children.length; index++) ...[
          if (index > 0) const SizedBox(width: 10),
          Expanded(child: children[index]),
        ],
      ],
    );
  }
}

class AppSheetPrimaryButton extends StatelessWidget {
  const AppSheetPrimaryButton({
    required this.label,
    required this.onTap,
    this.loading = false,
    this.trailing,
    super.key,
  });

  final String label;
  final VoidCallback? onTap;
  final bool loading;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return AppPrimaryButton(
      label: label,
      loading: loading,
      trailing: trailing,
      onTap: onTap,
    );
  }
}

class AppSheetSecondaryButton extends StatelessWidget {
  const AppSheetSecondaryButton({
    required this.label,
    required this.onTap,
    this.trailing,
    super.key,
  });

  final String label;
  final VoidCallback? onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return AppSecondaryButton(
      label: label,
      height: AppControls.buttonHeight,
      trailing: trailing,
      onTap: onTap,
    );
  }
}

class AppSheetDangerButton extends StatelessWidget {
  const AppSheetDangerButton({
    required this.label,
    required this.onTap,
    super.key,
  });

  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return AppDangerButton(label: label, onTap: onTap);
  }
}

class AppPickerOption<T> {
  const AppPickerOption({
    required this.value,
    required this.label,
    this.description,
    this.icon,
  });

  final T value;
  final String label;
  final String? description;
  final IconData? icon;
}

class AppPickerSheet<T> extends StatelessWidget {
  const AppPickerSheet({
    required this.title,
    required this.options,
    this.selected,
    this.subtitle,
    super.key,
  });

  final String title;
  final String? subtitle;
  final List<AppPickerOption<T>> options;
  final T? selected;

  @override
  Widget build(BuildContext context) {
    return AppBottomSheetBody(
      title: title,
      subtitle: subtitle,
      child: Column(
        children: [
          for (final option in options)
            AppPickerTile<T>(
              option: option,
              selected: option.value == selected,
            ),
        ],
      ),
    );
  }
}

class AppPickerTile<T> extends StatelessWidget {
  const AppPickerTile({
    required this.option,
    required this.selected,
    super.key,
  });

  final AppPickerOption<T> option;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: AppSurface(
        radius: 18,
        color: selected ? AppColors.brandWash : AppColors.surfaceSoft,
        borderColor: selected
            ? AppColors.brand.withValues(alpha: 0.22)
            : AppColors.borderSoft,
        onTap: () => Navigator.of(context).pop(option.value),
        child: Row(
          children: [
            if (option.icon != null) ...[
              DecoratedBox(
                decoration: BoxDecoration(
                  color: AppColors.brand.withValues(alpha: 0.10),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: SizedBox(
                  width: 38,
                  height: 38,
                  child: Center(
                    child: Icon(option.icon, color: AppColors.brand, size: 19),
                  ),
                ),
              ),
              const SizedBox(width: 12),
            ],
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    option.label,
                    style: const TextStyle(
                      color: AppColors.ink,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 14,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 0,
                    ),
                  ),
                  if (option.description != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      option.description!,
                      style: const TextStyle(
                        color: AppColors.muted,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        height: 1.45,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            if (selected)
              const Icon(Icons.check_circle, color: AppColors.brand, size: 20),
          ],
        ),
      ),
    );
  }
}

class AppConfirmSheet extends StatelessWidget {
  const AppConfirmSheet({
    required this.title,
    required this.message,
    required this.confirmLabel,
    required this.cancelLabel,
    this.danger = false,
    super.key,
  });

  final String title;
  final String message;
  final String confirmLabel;
  final String cancelLabel;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    return AppBottomSheetBody(
      title: title,
      subtitle: message,
      scrollable: false,
      footer: AppSheetFooterActions(
        children: [
          AppSheetSecondaryButton(
            label: cancelLabel,
            onTap: () => Navigator.of(context).pop(false),
          ),
          danger
              ? AppSheetDangerButton(
                  label: confirmLabel,
                  onTap: () => Navigator.of(context).pop(true),
                )
              : AppSheetPrimaryButton(
                  label: confirmLabel,
                  onTap: () => Navigator.of(context).pop(true),
                ),
        ],
      ),
      child: const SizedBox.shrink(),
    );
  }
}
