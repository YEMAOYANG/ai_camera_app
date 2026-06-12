import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:guardian_parent_app/src/core/theme/app_system_ui.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_background.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_button.dart';

class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({this.onComplete, super.key});

  final Future<void> Function()? onComplete;

  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen>
    with SingleTickerProviderStateMixin {
  static const _slides = [
    _WelcomeSlide(
      image: 'assets/images/welcome/welcome-parent-phone.png',
      alt: '家长在手机上查看孩子状态，旁边有小型 AI 摄像头',
      badge: '家庭看护',
      icon: _WelcomeIcon.sparkles,
      title: '少盯一点，也能知道孩子现在怎么样。',
      desc: '看护助手会把观察、任务、提醒和证据整理好，让家长先看到孩子状态，再处理真正需要判断的事。',
    ),
    _WelcomeSlide(
      image: 'assets/images/welcome/welcome-child-study.png',
      alt: '孩子在书桌前学习，AI 摄像头以克制方式辅助观察',
      badge: '任务陪伴',
      icon: _WelcomeIcon.book,
      title: 'AI 负责安静观察，孩子保留自己的节奏。',
      desc: '作业、阅读、小书包和睡前任务都按孩子档案组织，只给温和提醒，不把 App 做成打分后台。',
    ),
    _WelcomeSlide(
      image: 'assets/images/welcome/welcome-parent-confirm.png',
      alt: '家长收到确认提醒，关键决定由家长处理',
      badge: '家长确认',
      icon: _WelcomeIcon.shield,
      title: '关键决定由家长确认，AI 不替你承诺。',
      desc: '奖励申请、任务证据、安全提醒会说明来源和建议，家长可以确认、改判或暂缓。',
    ),
    _WelcomeSlide(
      image: 'assets/images/welcome/welcome-family-room.png',
      alt: '温暖家庭客厅和书房中的 AI 摄像头看护场景',
      badge: '家庭空间',
      icon: _WelcomeIcon.home,
      title: '看护要有科技感，也要有家的温度。',
      desc: '实时看护、隐私提示、日报和家庭协作都收在一个安静可靠的家长端 App 里。',
    ),
  ];

  late final AnimationController _floatController;
  int _step = 0;
  bool _loading = false;
  bool _didPrecacheImages = false;

  @override
  void initState() {
    super.initState();
    _floatController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 7),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _floatController.dispose();
    super.dispose();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_didPrecacheImages) return;
    _didPrecacheImages = true;
    for (final slide in _slides) {
      unawaited(precacheImage(AssetImage(slide.image), context));
    }
  }

  void _jumpTo(int step) {
    setState(() {
      _step = step.clamp(0, _slides.length - 1);
      _loading = false;
    });
  }

  Future<void> _next() async {
    final isLast = _step == _slides.length - 1;
    if (!isLast) {
      _jumpTo(_step + 1);
      return;
    }

    await _finishOnboarding();
  }

  Future<void> _finishOnboarding() async {
    if (_loading) return;

    setState(() => _loading = true);
    await Future<void>.delayed(const Duration(milliseconds: 220));
    await widget.onComplete?.call();
    if (mounted) {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    final compact = size.height < 760 || size.width < 370;
    final artHeight = compact
        ? (size.height * 0.45).clamp(300.0, 376.0).toDouble()
        : (size.height * 0.41).clamp(286.0, 360.0).toDouble();
    final pagePadding = EdgeInsets.fromLTRB(
      18,
      compact ? 38 : 54,
      18,
      bottomInset + (compact ? 14 : 24),
    );
    final slide = _slides[_step];
    final isLast = _step == _slides.length - 1;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppSystemUi.light(),
      child: Scaffold(
        backgroundColor: AppColors.appBackground,
        body: AppBackground(
          child: LayoutBuilder(
            builder: (context, constraints) {
              final viewportHeight = constraints.maxHeight.isFinite
                  ? constraints.maxHeight
                  : size.height;
              final contentMinHeight = math.max<double>(
                0,
                viewportHeight - pagePadding.vertical,
              );

              return SingleChildScrollView(
                padding: pagePadding,
                child: ConstrainedBox(
                  constraints: BoxConstraints(minHeight: contentMinHeight),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _WelcomeArt(
                        slide: slide,
                        height: artHeight,
                        floatController: _floatController,
                      ),
                      Padding(
                        padding: EdgeInsets.only(top: compact ? 10 : 14),
                        child: _WelcomeCopy(
                          slide: slide,
                          currentStep: _step,
                          slideCount: _slides.length,
                          isLast: isLast,
                          loading: _loading,
                          onDotTap: _jumpTo,
                          onNext: _next,
                          onLogin: _finishOnboarding,
                          compact: compact,
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

class _WelcomeCopy extends StatelessWidget {
  const _WelcomeCopy({
    required this.slide,
    required this.currentStep,
    required this.slideCount,
    required this.isLast,
    required this.loading,
    required this.onDotTap,
    required this.onNext,
    required this.onLogin,
    required this.compact,
  });

  final _WelcomeSlide slide;
  final int currentStep;
  final int slideCount;
  final bool isLast;
  final bool loading;
  final ValueChanged<int> onDotTap;
  final VoidCallback onNext;
  final VoidCallback onLogin;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final motion = AppMotion.duration(context, 300);

    return _Reveal(
      animateUpdates: false,
      child: SizedBox(
        width: double.infinity,
        child: _CopyAtmosphere(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              AnimatedSwitcher(
                duration: motion,
                switchInCurve: Curves.easeOutCubic,
                switchOutCurve: Curves.easeInCubic,
                transitionBuilder: (child, animation) {
                  return FadeTransition(
                    opacity: animation,
                    child: SlideTransition(
                      position: Tween<Offset>(
                        begin: const Offset(0, 0.035),
                        end: Offset.zero,
                      ).animate(animation),
                      child: child,
                    ),
                  );
                },
                child: _WelcomeTextBlock(
                  key: ValueKey(slide.title),
                  slide: slide,
                  compact: compact,
                ),
              ),
              SizedBox(height: compact ? 14 : 22),
              _WelcomeProgress(
                currentStep: currentStep,
                slideCount: slideCount,
                onDotTap: onDotTap,
              ),
              SizedBox(height: compact ? 16 : 22),
              AppPrimaryButton(
                label: isLast ? '开始设置' : '继续',
                loading: loading,
                trailing: AppButtonGlyph(
                  icon: isLast ? Icons.arrow_forward : Icons.chevron_right,
                ),
                onTap: loading ? null : onNext,
              ),
              SizedBox(height: compact ? 8 : 12),
              AppSecondaryButton(
                label: '登录或创建家庭',
                onTap: loading ? null : onLogin,
                trailing: const Icon(
                  Icons.person_add_alt_1_outlined,
                  color: AppColors.ink,
                  size: 16,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CopyAtmosphere extends StatelessWidget {
  const _CopyAtmosphere({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Positioned(
          left: -26,
          right: -26,
          top: -34,
          height: 210,
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: RadialGradient(
                center: const Alignment(-0.18, -0.24),
                radius: 0.9,
                colors: [
                  Colors.white.withValues(alpha: 0.78),
                  AppColors.appBackgroundMid.withValues(alpha: 0.46),
                  Colors.white.withValues(alpha: 0),
                ],
                stops: const [0, 0.46, 1],
              ),
            ),
          ),
        ),
        Positioned(
          left: 4,
          right: 32,
          top: -12,
          height: 1,
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  Colors.white.withValues(alpha: 0),
                  Colors.white.withValues(alpha: 0.82),
                  Colors.white.withValues(alpha: 0),
                ],
              ),
            ),
          ),
        ),
        Padding(padding: const EdgeInsets.fromLTRB(2, 0, 2, 0), child: child),
      ],
    );
  }
}

class _WelcomeTextBlock extends StatelessWidget {
  const _WelcomeTextBlock({
    required this.slide,
    required this.compact,
    super.key,
  });

  final _WelcomeSlide slide;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            _Pill(icon: slide.icon, label: slide.badge),
            const Spacer(),
            const Flexible(
              child: Align(
                alignment: Alignment.centerRight,
                child: Text(
                  'AI 看护 · 家长确认',
                  overflow: TextOverflow.ellipsis,
                  maxLines: 1,
                  style: TextStyle(
                    color: Color(0x9A526579),
                    fontFamily: AppTypography.systemFont,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    height: 1,
                    letterSpacing: 0,
                  ),
                ),
              ),
            ),
          ],
        ),
        SizedBox(height: compact ? 12 : 18),
        Text(
          slide.title,
          style: TextStyle(
            color: AppColors.ink,
            fontFamily: AppTypography.systemFont,
            fontSize: compact ? 28 : 32,
            fontWeight: FontWeight.w700,
            height: compact ? 1.08 : 1.11,
            letterSpacing: 0,
          ),
        ),
        SizedBox(height: compact ? 10 : 15),
        _DescriptionBlock(text: slide.desc, compact: compact),
      ],
    );
  }
}

class _DescriptionBlock extends StatelessWidget {
  const _DescriptionBlock({required this.text, required this.compact});

  final String text;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 2,
          height: compact ? 34 : 44,
          margin: const EdgeInsets.only(top: 5, right: 12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppRadii.full),
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                AppColors.brand.withValues(alpha: 0),
                AppColors.brand.withValues(alpha: 0.42),
                AppColors.brand.withValues(alpha: 0),
              ],
            ),
          ),
        ),
        Expanded(
          child: Text(
            text,
            maxLines: compact ? 2 : 3,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: AppColors.muted,
              fontFamily: AppTypography.systemFont,
              fontSize: compact ? 14 : 15,
              fontWeight: FontWeight.w500,
              height: compact ? 1.5 : 1.72,
              letterSpacing: 0,
            ),
          ),
        ),
      ],
    );
  }
}

class _WelcomeArt extends StatelessWidget {
  const _WelcomeArt({
    required this.slide,
    required this.height,
    required this.floatController,
  });

  final _WelcomeSlide slide;
  final double height;
  final AnimationController floatController;

  @override
  Widget build(BuildContext context) {
    return _Reveal(
      animateUpdates: false,
      child: SizedBox(
        width: double.infinity,
        height: height,
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppRadii.welcomeArt),
            color: const Color(0xFFEDF3FB),
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [Color(0xB8FFFFFF), Color(0xBDE6EEFD)],
            ),
            boxShadow: const [
              BoxShadow(
                color: Color(0x1430204C),
                blurRadius: 18,
                offset: Offset(0, 12),
              ),
            ],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(AppRadii.welcomeArt),
            child: Stack(
              children: [
                Positioned(
                  left: 0,
                  right: 0,
                  top: -14,
                  bottom: -14,
                  child: AnimatedBuilder(
                    animation: floatController,
                    builder: (context, child) {
                      final y = -7 * math.sin(floatController.value * math.pi);
                      return Transform.translate(
                        offset: Offset(0, y),
                        child: child,
                      );
                    },
                    child: SizedBox.expand(
                      child: AnimatedSwitcher(
                        duration: AppMotion.duration(context, 260),
                        switchInCurve: Curves.easeOutCubic,
                        switchOutCurve: Curves.easeInCubic,
                        layoutBuilder: (currentChild, previousChildren) {
                          return Stack(
                            fit: StackFit.expand,
                            children: [...previousChildren, ?currentChild],
                          );
                        },
                        transitionBuilder: (child, animation) {
                          return FadeTransition(
                            opacity: animation,
                            child: ScaleTransition(
                              scale: Tween<double>(
                                begin: 1.006,
                                end: 1,
                              ).animate(animation),
                              child: child,
                            ),
                          );
                        },
                        child: Image.asset(
                          slide.image,
                          key: ValueKey(slide.image),
                          width: double.infinity,
                          height: double.infinity,
                          fit: BoxFit.cover,
                          semanticLabel: slide.alt,
                        ),
                      ),
                    ),
                  ),
                ),
                const Positioned.fill(child: _ArtOverlay()),
                Positioned.fill(
                  child: Padding(
                    padding: const EdgeInsets.all(15),
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(24),
                        border: Border.all(color: const Color(0x52FFFFFF)),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill({required this.icon, required this.label});

  final _WelcomeIcon icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xC7FFFFFF),
        borderRadius: BorderRadius.circular(AppRadii.full),
        border: Border.all(color: const Color(0x0F2C3E5C)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12),
        child: SizedBox(
          height: 30,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              _SmallIcon(icon: icon),
              const SizedBox(width: 6),
              Text(
                label,
                style: const TextStyle(
                  color: AppColors.ink,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _WelcomeProgress extends StatelessWidget {
  const _WelcomeProgress({
    required this.currentStep,
    required this.slideCount,
    required this.onDotTap,
  });

  final int currentStep;
  final int slideCount;
  final ValueChanged<int> onDotTap;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(AppRadii.full),
        color: Colors.white.withValues(alpha: 0.28),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF4C6685).withValues(alpha: 0.04),
            blurRadius: 14,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 5),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (var index = 0; index < slideCount; index++) ...[
              _WelcomeDot(
                active: index == currentStep,
                onTap: () => onDotTap(index),
              ),
              if (index != slideCount - 1) const SizedBox(width: 7),
            ],
          ],
        ),
      ),
    );
  }
}

class _WelcomeDot extends StatelessWidget {
  const _WelcomeDot({required this.active, required this.onTap});

  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: AnimatedContainer(
        duration: AppMotion.duration(context, 260),
        curve: Curves.easeOutCubic,
        width: active ? 34 : 8,
        height: active ? 10 : 8,
        decoration: BoxDecoration(
          color: active ? null : const Color(0x3266758A),
          gradient: active
              ? const LinearGradient(
                  begin: Alignment.centerLeft,
                  end: Alignment.centerRight,
                  colors: [AppColors.brand, AppColors.brandSoft],
                )
              : null,
          borderRadius: BorderRadius.circular(AppRadii.full),
          boxShadow: active
              ? [
                  BoxShadow(
                    color: AppColors.brand.withValues(alpha: 0.24),
                    blurRadius: 12,
                    offset: const Offset(0, 5),
                  ),
                ]
              : null,
        ),
      ),
    );
  }
}

class _Reveal extends StatefulWidget {
  const _Reveal({required this.child, this.animateUpdates = true});

  final Widget child;
  final bool animateUpdates;

  @override
  State<_Reveal> createState() => _RevealState();
}

class _RevealState extends State<_Reveal> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _opacity;
  late final Animation<double> _offset;
  late final Animation<double> _scale;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 420),
    );
    final curve = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOutCubic,
    );
    _opacity = Tween<double>(begin: 0.58, end: 1).animate(curve);
    _offset = Tween<double>(begin: 10, end: 0).animate(curve);
    _scale = Tween<double>(begin: 0.985, end: 1).animate(curve);
    unawaited(_controller.forward());
  }

  @override
  void didUpdateWidget(covariant _Reveal oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!widget.animateUpdates) return;
    _controller
      ..reset()
      ..forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (MediaQuery.of(context).disableAnimations) {
      return widget.child;
    }

    return AnimatedBuilder(
      animation: _controller,
      child: widget.child,
      builder: (context, child) {
        return Opacity(
          opacity: _opacity.value,
          child: Transform.translate(
            offset: Offset(0, _offset.value),
            child: Transform.scale(scale: _scale.value, child: child),
          ),
        );
      },
    );
  }
}

class _ArtOverlay extends StatelessWidget {
  const _ArtOverlay();

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: const [
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Color(0x05FFFFFF),
                  Color(0x00FFFFFF),
                  Color(0x57F5F8FC),
                ],
                stops: [0, 0.58, 1],
              ),
            ),
          ),
        ),
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.centerLeft,
                end: Alignment.centerRight,
                colors: [
                  Color(0x292F6CF6),
                  Color(0x00FFFFFF),
                  Color(0x1F6D65E7),
                ],
                stops: [0, 0.44, 1],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _SmallIcon extends StatelessWidget {
  const _SmallIcon({required this.icon});

  final _WelcomeIcon icon;

  @override
  Widget build(BuildContext context) {
    final data = switch (icon) {
      _WelcomeIcon.sparkles => Icons.auto_awesome,
      _WelcomeIcon.book => Icons.menu_book_outlined,
      _WelcomeIcon.shield => Icons.verified_user_outlined,
      _WelcomeIcon.home => Icons.home_outlined,
    };
    return Icon(data, color: AppColors.ink, size: 14);
  }
}

class _WelcomeSlide {
  const _WelcomeSlide({
    required this.image,
    required this.alt,
    required this.badge,
    required this.icon,
    required this.title,
    required this.desc,
  });

  final String image;
  final String alt;
  final String badge;
  final _WelcomeIcon icon;
  final String title;
  final String desc;
}

enum _WelcomeIcon { sparkles, book, shield, home }
