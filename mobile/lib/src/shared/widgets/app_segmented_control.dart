import 'package:flutter/material.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';

class AppSegmentOption<T> {
  const AppSegmentOption({
    required this.value,
    required this.label,
    this.enabled = true,
    this.key,
  });

  final T value;
  final String label;
  final bool enabled;
  final Key? key;
}

class AppSegmentedControl<T> extends StatelessWidget {
  const AppSegmentedControl({
    required this.options,
    required this.value,
    required this.onChanged,
    this.semanticLabel,
    this.compact = false,
    this.scrollable = false,
    super.key,
  });

  final List<AppSegmentOption<T>> options;
  final T value;
  final ValueChanged<T>? onChanged;
  final String? semanticLabel;
  final bool compact;
  final bool scrollable;

  static const _indicatorInset = 3.0;
  static const _scrollableMinSegmentWidth = 72.0;

  @override
  Widget build(BuildContext context) {
    if (options.isEmpty) return const SizedBox.shrink();

    final selected = options.any((option) => option.value == value)
        ? value
        : options.first.value;
    final selectedIndex = options.indexWhere((option) => option.value == selected);
    final height = compact ? 38.0 : AppControls.minTouchTarget;
    final duration = AppMotion.duration(context, 220);
    final fontSize = compact ? 12.5 : 13.0;

    final track = _AppSegmentTrack<T>(
      options: options,
      selected: selected,
      selectedIndex: selectedIndex,
      height: height,
      duration: duration,
      fontSize: fontSize,
      onChanged: onChanged,
      scrollable: scrollable,
    );

    return Semantics(
      label: semanticLabel,
      child: scrollable
          ? SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              physics: const BouncingScrollPhysics(),
              child: track,
            )
          : SizedBox(width: double.infinity, height: height, child: track),
    );
  }
}

class _AppSegmentTrack<T> extends StatelessWidget {
  const _AppSegmentTrack({
    required this.options,
    required this.selected,
    required this.selectedIndex,
    required this.height,
    required this.duration,
    required this.fontSize,
    required this.onChanged,
    required this.scrollable,
  });

  final List<AppSegmentOption<T>> options;
  final T selected;
  final int selectedIndex;
  final double height;
  final Duration duration;
  final double fontSize;
  final ValueChanged<T>? onChanged;
  final bool scrollable;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final segmentWidths = scrollable
            ? List<double>.filled(
                options.length,
                AppSegmentedControl._scrollableMinSegmentWidth,
              )
            : List<double>.filled(
                options.length,
                constraints.maxWidth / options.length,
              );
        final trackWidth = segmentWidths.fold<double>(
          0,
          (total, width) => total + width,
        );
        final indicatorLeft = segmentWidths
                .take(selectedIndex)
                .fold<double>(0, (total, width) => total + width) +
            AppSegmentedControl._indicatorInset;
        final indicatorWidth =
            segmentWidths[selectedIndex] - AppSegmentedControl._indicatorInset * 2;
        final indicatorHeight =
            height - AppSegmentedControl._indicatorInset * 2;

        return SizedBox(
          width: scrollable ? trackWidth : constraints.maxWidth,
          height: height,
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: AppColors.surfaceStrong,
              borderRadius: BorderRadius.circular(AppRadii.full),
              border: Border.all(
                color: AppColors.borderSoft.withValues(alpha: 0.72),
              ),
            ),
            child: Stack(
              clipBehavior: Clip.antiAlias,
              children: [
                AnimatedPositioned(
                  duration: duration,
                  curve: Curves.easeOutCubic,
                  left: indicatorLeft,
                  top: AppSegmentedControl._indicatorInset,
                  width: indicatorWidth,
                  height: indicatorHeight,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: AppColors.surfaceElevated,
                      borderRadius: BorderRadius.circular(AppRadii.full),
                      border: Border.all(
                        color: AppColors.ink.withValues(alpha: 0.05),
                      ),
                    ),
                  ),
                ),
                Row(
                  children: [
                    for (var index = 0; index < options.length; index++)
                      SizedBox(
                        width: segmentWidths[index],
                        child: _AppSegmentTile<T>(
                          option: options[index],
                          selected: options[index].value == selected,
                          enabled:
                              options[index].enabled && onChanged != null,
                          fontSize: fontSize,
                          duration: duration,
                          onTap: onChanged == null
                              ? null
                              : () => onChanged!(options[index].value),
                        ),
                      ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _AppSegmentTile<T> extends StatelessWidget {
  const _AppSegmentTile({
    required this.option,
    required this.selected,
    required this.enabled,
    required this.fontSize,
    required this.duration,
    this.onTap,
  });

  final AppSegmentOption<T> option;
  final bool selected;
  final bool enabled;
  final double fontSize;
  final Duration duration;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final foreground = !enabled
        ? AppColors.disabledInk
        : selected
        ? AppColors.ink
        : AppColors.muted;

    return Semantics(
      button: true,
      selected: selected,
      enabled: enabled,
      label: option.label,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: enabled ? onTap : null,
        child: SizedBox(
          height: double.infinity,
          child: Center(
            child: AnimatedDefaultTextStyle(
              duration: duration,
              curve: Curves.easeOutCubic,
              style: TextStyle(
                color: foreground,
                fontFamily: AppTypography.systemFont,
                fontSize: fontSize,
                fontWeight: selected ? FontWeight.w700 : FontWeight.w600,
                letterSpacing: selected ? -0.1 : 0,
                height: 1.05,
              ),
              child: Text(
                option.label,
                key: option.key,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class AppFilterChipOption<T> {
  const AppFilterChipOption({required this.value, required this.label});

  final T value;
  final String label;
}

class AppFilterChipBar<T> extends StatelessWidget {
  const AppFilterChipBar({
    required this.options,
    required this.value,
    required this.onChanged,
    this.padding = EdgeInsets.zero,
    super.key,
  });

  final List<AppFilterChipOption<T>> options;
  final T value;
  final ValueChanged<T> onChanged;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    if (options.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: padding,
      child: AppSegmentedControl<T>(
        value: value,
        scrollable: true,
        compact: true,
        onChanged: onChanged,
        options: [
          for (final option in options)
            AppSegmentOption(value: option.value, label: option.label),
        ],
      ),
    );
  }
}
