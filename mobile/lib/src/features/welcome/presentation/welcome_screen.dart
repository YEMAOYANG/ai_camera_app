import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class _WelcomeTokens {
  const _WelcomeTokens._();

  static const ink = Color(0xFF142033);
  static const muted = Color(0xFF66758A);
  static const blue = Color(0xFF2F6CF6);
  static const blueSoft = Color(0xFF7FA6FF);
}

Duration _motionDuration(BuildContext context, int milliseconds) {
  return MediaQuery.of(context).disableAnimations
      ? Duration.zero
      : Duration(milliseconds: milliseconds);
}

class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({super.key});

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
      desc: '米拉把观察、任务、提醒和证据整理好，让家长先看到孩子状态，再处理真正需要判断的事。',
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

    setState(() => _loading = true);
    await Future<void>.delayed(const Duration(milliseconds: 420));
    if (mounted) {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    final artHeight = math.min(size.height * 0.45, 382.0);
    final slide = _slides[_step];
    final isLast = _step == _slides.length - 1;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.dark.copyWith(
        statusBarColor: Colors.transparent,
        systemNavigationBarColor: const Color(0xFFF7F7F3),
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
      child: Scaffold(
        backgroundColor: const Color(0xFFF8FAFD),
        body: DecoratedBox(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [Color(0xFFF8FAFD), Color(0xFFEEF4FA), Color(0xFFF7F7F3)],
              stops: [0, 0.52, 1],
            ),
          ),
          child: Stack(
            children: [
              const Positioned.fill(child: _SurfaceWash()),
              SingleChildScrollView(
                padding: EdgeInsets.fromLTRB(18, 60, 18, bottomInset + 32),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _WelcomeArt(
                      slide: slide,
                      height: artHeight,
                      floatController: _floatController,
                    ),
                    const SizedBox(height: 16),
                    _WelcomeCopy(
                      slide: slide,
                      currentStep: _step,
                      slideCount: _slides.length,
                      isLast: isLast,
                      loading: _loading,
                      onDotTap: _jumpTo,
                      onNext: _next,
                    ),
                  ],
                ),
              ),
            ],
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
  });

  final _WelcomeSlide slide;
  final int currentStep;
  final int slideCount;
  final bool isLast;
  final bool loading;
  final ValueChanged<int> onDotTap;
  final VoidCallback onNext;

  @override
  Widget build(BuildContext context) {
    final motion = _motionDuration(context, 300);

    return _Reveal(
      animateUpdates: false,
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
              ),
            ),
            const SizedBox(height: 22),
            _WelcomeProgress(
              currentStep: currentStep,
              slideCount: slideCount,
              onDotTap: onDotTap,
            ),
            const SizedBox(height: 22),
            _PrimaryWelcomeButton(
              label: isLast ? '开始设置' : '继续',
              loading: loading,
              isLast: isLast,
              onTap: loading ? null : onNext,
            ),
            const SizedBox(height: 12),
            _SecondaryWelcomeButton(onTap: () {}),
          ],
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
                  const Color(0xFFEAF2FB).withValues(alpha: 0.46),
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
  const _WelcomeTextBlock({required this.slide, super.key});

  final _WelcomeSlide slide;

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
                    fontFamily: '.AppleSystemUIFont',
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
        const SizedBox(height: 18),
        Text(
          slide.title,
          style: const TextStyle(
            color: _WelcomeTokens.ink,
            fontFamily: '.AppleSystemUIFont',
            fontSize: 32,
            fontWeight: FontWeight.w700,
            height: 1.11,
            letterSpacing: 0,
          ),
        ),
        const SizedBox(height: 15),
        _DescriptionBlock(text: slide.desc),
      ],
    );
  }
}

class _DescriptionBlock extends StatelessWidget {
  const _DescriptionBlock({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 2,
          height: 44,
          margin: const EdgeInsets.only(top: 5, right: 12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(999),
            gradient: const LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [Color(0x002F6CF6), Color(0x6C2F6CF6), Color(0x002F6CF6)],
            ),
          ),
        ),
        Expanded(
          child: Text(
            text,
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: _WelcomeTokens.muted,
              fontFamily: '.AppleSystemUIFont',
              fontSize: 15,
              fontWeight: FontWeight.w500,
              height: 1.72,
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
        height: height,
        child: LayoutBuilder(
          builder: (context, constraints) {
            return Transform.translate(
              offset: const Offset(-4, 0),
              child: SizedBox(
                width: constraints.maxWidth + 8,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(26),
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
                    borderRadius: BorderRadius.circular(26),
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
                              final y =
                                  -7 *
                                  math.sin(floatController.value * math.pi);
                              return Transform.translate(
                                offset: Offset(0, y),
                                child: child,
                              );
                            },
                            child: SizedBox.expand(
                              child: AnimatedSwitcher(
                                duration: const Duration(milliseconds: 260),
                                switchInCurve: Curves.easeOutCubic,
                                switchOutCurve: Curves.easeInCubic,
                                layoutBuilder:
                                    (currentChild, previousChildren) {
                                      return Stack(
                                        fit: StackFit.expand,
                                        children: [
                                          ...previousChildren,
                                          ?currentChild,
                                        ],
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
                                border: Border.all(
                                  color: const Color(0x52FFFFFF),
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
            );
          },
        ),
      ),
    );
  }
}

class _PrimaryWelcomeButton extends StatelessWidget {
  const _PrimaryWelcomeButton({
    required this.label,
    required this.loading,
    required this.isLast,
    required this.onTap,
  });

  final String label;
  final bool loading;
  final bool isLast;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return _TapScale(
      onTap: onTap,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(19),
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(19),
            border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [Color(0xFF1C2940), Color(0xFF111827)],
            ),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFF172033).withValues(alpha: 0.24),
                blurRadius: 24,
                offset: const Offset(0, 15),
              ),
            ],
          ),
          child: Stack(
            children: [
              Positioned(
                left: 18,
                right: 18,
                top: 1,
                height: 1,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [
                        Colors.white.withValues(alpha: 0),
                        Colors.white.withValues(alpha: 0.42),
                        Colors.white.withValues(alpha: 0),
                      ],
                    ),
                  ),
                ),
              ),
              const Positioned(
                left: -80,
                top: -70,
                width: 210,
                height: 160,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: RadialGradient(
                      colors: [Color(0x183B82F6), Color(0x003B82F6)],
                    ),
                  ),
                ),
              ),
              SizedBox(
                height: 56,
                width: double.infinity,
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      label,
                      style: const TextStyle(
                        color: Colors.white,
                        fontFamily: '.AppleSystemUIFont',
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0,
                      ),
                    ),
                    const SizedBox(width: 9),
                    _PrimaryButtonGlyph(loading: loading, isLast: isLast),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PrimaryButtonGlyph extends StatelessWidget {
  const _PrimaryButtonGlyph({required this.loading, required this.isLast});

  final bool loading;
  final bool isLast;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
      ),
      child: SizedBox(
        width: 22,
        height: 22,
        child: Center(
          child: loading
              ? const SizedBox(
                  width: 13,
                  height: 13,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                    backgroundColor: Color(0x55FFFFFF),
                  ),
                )
              : Icon(
                  isLast ? Icons.arrow_forward : Icons.chevron_right,
                  color: Colors.white,
                  size: 15,
                ),
        ),
      ),
    );
  }
}

class _SecondaryWelcomeButton extends StatelessWidget {
  const _SecondaryWelcomeButton({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return _TapScale(
      onTap: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: Colors.white.withValues(alpha: 0.7)),
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Colors.white.withValues(alpha: 0.78),
              Colors.white.withValues(alpha: 0.54),
            ],
          ),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF4C6685).withValues(alpha: 0.07),
              blurRadius: 18,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: const SizedBox(
          height: 50,
          width: double.infinity,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                '登录或创建家庭',
                style: TextStyle(
                  color: _WelcomeTokens.ink,
                  fontFamily: '.AppleSystemUIFont',
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0,
                ),
              ),
              SizedBox(width: 8),
              Icon(
                Icons.person_add_alt_1_outlined,
                color: _WelcomeTokens.ink,
                size: 16,
              ),
            ],
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
        borderRadius: BorderRadius.circular(999),
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
                  color: Color(0xFF142033),
                  fontFamily: '.AppleSystemUIFont',
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
        borderRadius: BorderRadius.circular(999),
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
        duration: _motionDuration(context, 260),
        curve: Curves.easeOutCubic,
        width: active ? 34 : 8,
        height: active ? 10 : 8,
        decoration: BoxDecoration(
          color: active ? null : const Color(0x3266758A),
          gradient: active
              ? const LinearGradient(
                  begin: Alignment.centerLeft,
                  end: Alignment.centerRight,
                  colors: [_WelcomeTokens.blue, _WelcomeTokens.blueSoft],
                )
              : null,
          borderRadius: BorderRadius.circular(999),
          boxShadow: active
              ? [
                  BoxShadow(
                    color: _WelcomeTokens.blue.withValues(alpha: 0.24),
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

class _TapScale extends StatefulWidget {
  const _TapScale({required this.child, required this.onTap});

  final Widget child;
  final VoidCallback? onTap;

  @override
  State<_TapScale> createState() => _TapScaleState();
}

class _TapScaleState extends State<_TapScale> {
  var _pressed = false;

  @override
  Widget build(BuildContext context) {
    final scale = MediaQuery.of(context).disableAnimations
        ? 1.0
        : (_pressed ? 0.975 : 1.0);

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: widget.onTap,
      onTapDown: widget.onTap == null
          ? null
          : (_) => setState(() => _pressed = true),
      onTapCancel: widget.onTap == null
          ? null
          : () => setState(() => _pressed = false),
      onTapUp: widget.onTap == null
          ? null
          : (_) => setState(() => _pressed = false),
      child: AnimatedScale(
        scale: scale,
        duration: _motionDuration(context, 180),
        curve: Curves.easeOutCubic,
        child: widget.child,
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

class _SurfaceWash extends StatelessWidget {
  const _SurfaceWash();

  @override
  Widget build(BuildContext context) {
    return const DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0x6BFFFFFF), Color(0x0DFFFFFF), Color(0x102F6CF6)],
          stops: [0, 0.48, 1],
        ),
      ),
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
    return Icon(data, color: const Color(0xFF142033), size: 14);
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
