import 'dart:async';

import 'package:flutter/material.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';

enum AppToastTone { neutral, success, warning, danger }

OverlayEntry? _currentToastEntry;

void showAppToast(
  BuildContext context,
  String title, {
  String? message,
  AppToastTone tone = AppToastTone.neutral,
  Duration duration = const Duration(milliseconds: 2400),
}) {
  final overlay = Overlay.maybeOf(context);
  if (overlay == null) return;

  _currentToastEntry?.remove();
  late final OverlayEntry entry;
  entry = OverlayEntry(
    builder: (context) {
      return _AppToastOverlay(
        title: title,
        message: message,
        tone: tone,
        duration: duration,
        onDismissed: () {
          if (_currentToastEntry == entry) {
            _currentToastEntry = null;
            entry.remove();
          }
        },
      );
    },
  );
  _currentToastEntry = entry;
  overlay.insert(entry);
}

class _AppToastOverlay extends StatefulWidget {
  const _AppToastOverlay({
    required this.title,
    required this.message,
    required this.tone,
    required this.duration,
    required this.onDismissed,
  });

  final String title;
  final String? message;
  final AppToastTone tone;
  final Duration duration;
  final VoidCallback onDismissed;

  @override
  State<_AppToastOverlay> createState() => _AppToastOverlayState();
}

class _AppToastOverlayState extends State<_AppToastOverlay>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _opacity;
  late final Animation<Offset> _slide;
  Timer? _timer;
  var _closing = false;

  @override
  void initState() {
    super.initState();
    final reduceMotion = WidgetsBinding
        .instance
        .platformDispatcher
        .accessibilityFeatures
        .disableAnimations;
    _controller = AnimationController(
      vsync: this,
      duration: reduceMotion
          ? Duration.zero
          : const Duration(milliseconds: 180),
      reverseDuration: reduceMotion
          ? Duration.zero
          : const Duration(milliseconds: 140),
    );
    final curve = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOutCubic,
    );
    _opacity = Tween<double>(begin: 0, end: 1).animate(curve);
    _slide = Tween<Offset>(
      begin: reduceMotion ? Offset.zero : const Offset(0, -0.18),
      end: Offset.zero,
    ).animate(curve);
    _controller.forward();
    _timer = Timer(widget.duration, _dismiss);
  }

  @override
  void dispose() {
    _timer?.cancel();
    _controller.dispose();
    super.dispose();
  }

  Future<void> _dismiss() async {
    if (_closing) return;
    _closing = true;
    _timer?.cancel();
    if (mounted) {
      await _controller.reverse();
    }
    widget.onDismissed();
  }

  @override
  Widget build(BuildContext context) {
    final semanticsLabel = [
      widget.title,
      if (widget.message != null && widget.message!.trim().isNotEmpty)
        widget.message!,
    ].join('，');

    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
          child: IgnorePointer(
            child: SlideTransition(
              position: _slide,
              child: FadeTransition(
                opacity: _opacity,
                child: Material(
                  color: Colors.transparent,
                  child: Align(
                    alignment: Alignment.topCenter,
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 520),
                      child: Semantics(
                        container: true,
                        liveRegion: true,
                        label: semanticsLabel,
                        child: _AppToastContent(
                          title: widget.title,
                          message: widget.message,
                          tone: widget.tone,
                        ),
                      ),
                    ),
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

class _AppToastContent extends StatelessWidget {
  const _AppToastContent({
    required this.title,
    required this.message,
    required this.tone,
  });

  final String title;
  final String? message;
  final AppToastTone tone;

  @override
  Widget build(BuildContext context) {
    final palette = tone._palette;
    final hasMessage = message != null && message!.trim().isNotEmpty;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.ink,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
        boxShadow: [
          BoxShadow(
            color: AppColors.ink.withValues(alpha: 0.22),
            blurRadius: 22,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: Row(
          crossAxisAlignment: hasMessage
              ? CrossAxisAlignment.start
              : CrossAxisAlignment.center,
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                color: palette.accent.withValues(alpha: 0.16),
                borderRadius: BorderRadius.circular(14),
              ),
              child: SizedBox(
                width: 36,
                height: 36,
                child: Icon(palette.icon, color: palette.accent, size: 19),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    maxLines: hasMessage ? 2 : 3,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Colors.white,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 13.5,
                      fontWeight: FontWeight.w800,
                      height: 1.25,
                      letterSpacing: 0,
                    ),
                  ),
                  if (hasMessage) ...[
                    const SizedBox(height: 4),
                    Text(
                      message!,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.72),
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
          ],
        ),
      ),
    );
  }
}

class _ToastPalette {
  const _ToastPalette({required this.accent, required this.icon});

  final Color accent;
  final IconData icon;
}

extension on AppToastTone {
  _ToastPalette get _palette {
    return switch (this) {
      AppToastTone.success => const _ToastPalette(
        accent: AppColors.success,
        icon: Icons.check_rounded,
      ),
      AppToastTone.warning => const _ToastPalette(
        accent: AppColors.warning,
        icon: Icons.priority_high_rounded,
      ),
      AppToastTone.danger => const _ToastPalette(
        accent: AppColors.danger,
        icon: Icons.error_outline_rounded,
      ),
      AppToastTone.neutral => const _ToastPalette(
        accent: AppColors.brandDeep,
        icon: Icons.info_outline_rounded,
      ),
    };
  }
}
