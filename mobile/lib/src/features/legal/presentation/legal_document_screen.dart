import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/legal/domain/legal_document.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_background.dart';

class LegalDocumentScreen extends StatelessWidget {
  const LegalDocumentScreen({required this.document, super.key});

  final LegalDocument document;

  @override
  Widget build(BuildContext context) {
    final safeArea = MediaQuery.paddingOf(context);

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.dark.copyWith(
        statusBarColor: Colors.transparent,
        systemNavigationBarColor: AppColors.appBackgroundWarm,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
      child: Scaffold(
        backgroundColor: AppColors.appBackgroundWarm,
        body: Stack(
          children: [
            const Positioned.fill(child: AppScreenBackground()),
            Column(
              children: [
                _LegalTopBar(title: document.title, safeTop: safeArea.top),
                Expanded(
                  child: SingleChildScrollView(
                    padding: EdgeInsets.fromLTRB(
                      20,
                      12,
                      20,
                      safeArea.bottom + 28,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _SummaryPanel(document: document),
                        const SizedBox(height: 14),
                        _HighlightsPanel(highlights: document.highlights),
                        const SizedBox(height: 14),
                        _SectionGroup(sections: document.sections),
                        const SizedBox(height: 18),
                        _VersionFooter(document: document),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _LegalTopBar extends StatelessWidget {
  const _LegalTopBar({required this.title, required this.safeTop});

  final String title;
  final double safeTop;

  @override
  Widget build(BuildContext context) {
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.appBackground.withValues(alpha: 0.78),
            border: Border(
              bottom: BorderSide(
                color: AppColors.ink.withValues(alpha: 0.07),
                width: 0.6,
              ),
            ),
          ),
          child: Padding(
            padding: EdgeInsets.fromLTRB(20, safeTop, 20, 0),
            child: SizedBox(
              height: AppChrome.pinnedHeaderHeight,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  _BackButton(onTap: () => _goBack(context)),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: AppColors.ink,
                            fontFamily: AppTypography.systemFont,
                            fontSize: 24,
                            fontWeight: FontWeight.w800,
                            height: 1.14,
                            letterSpacing: 0,
                          ),
                        ),
                        const SizedBox(height: 7),
                        const Text(
                          '请在使用前阅读并确认',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: AppColors.muted,
                            fontFamily: AppTypography.systemFont,
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                            height: 1.35,
                            letterSpacing: 0,
                          ),
                        ),
                      ],
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

  void _goBack(BuildContext context) {
    if (context.canPop()) {
      context.pop();
      return;
    }
    context.go(loginPath);
  }
}

class _BackButton extends StatefulWidget {
  const _BackButton({required this.onTap});

  final VoidCallback onTap;

  @override
  State<_BackButton> createState() => _BackButtonState();
}

class _BackButtonState extends State<_BackButton> {
  var _pressed = false;

  @override
  Widget build(BuildContext context) {
    final scale = MediaQuery.of(context).disableAnimations
        ? 1.0
        : (_pressed ? AppMotion.buttonPressScale : 1.0);

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: widget.onTap,
      onTapDown: (_) => setState(() => _pressed = true),
      onTapCancel: () => setState(() => _pressed = false),
      onTapUp: (_) => setState(() => _pressed = false),
      child: Semantics(
        button: true,
        label: '返回登录页',
        child: AnimatedScale(
          scale: scale,
          duration: AppMotion.duration(context, 160),
          curve: Curves.easeOutCubic,
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.72),
              borderRadius: BorderRadius.circular(15),
              border: Border.all(color: Colors.white.withValues(alpha: 0.82)),
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFF4C6685).withValues(alpha: 0.08),
                  blurRadius: 14,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            child: const SizedBox(
              width: 44,
              height: 44,
              child: Center(
                child: Icon(
                  Icons.arrow_back_ios_new,
                  color: AppColors.ink,
                  size: 18,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _SummaryPanel extends StatelessWidget {
  const _SummaryPanel({required this.document});

  final LegalDocument document;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.64),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: Colors.white.withValues(alpha: 0.86)),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF4C6685).withValues(alpha: 0.07),
            blurRadius: 22,
            offset: const Offset(0, 14),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 17),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: AppColors.ink,
                    borderRadius: BorderRadius.circular(13),
                  ),
                  child: const SizedBox(
                    width: 34,
                    height: 34,
                    child: Center(
                      child: Icon(
                        Icons.description_outlined,
                        color: Colors.white,
                        size: 18,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 11),
                const Text(
                  '法律文档',
                  style: TextStyle(
                    color: Color(0x99526579),
                    fontFamily: AppTypography.systemFont,
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                    height: 1,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Text(
              document.summaryTitle,
              style: const TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 22,
                fontWeight: FontWeight.w800,
                height: 1.24,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              document.summary,
              style: const TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 14,
                fontWeight: FontWeight.w600,
                height: 1.68,
                letterSpacing: 0,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HighlightsPanel extends StatelessWidget {
  const _HighlightsPanel({required this.highlights});

  final List<String> highlights;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.brand.withValues(alpha: 0.075),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.brand.withValues(alpha: 0.12)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 15, 16, 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(
                  Icons.privacy_tip_outlined,
                  color: AppColors.brand,
                  size: 18,
                ),
                SizedBox(width: 8),
                Text(
                  '重点提示',
                  style: TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                    height: 1.2,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            for (final highlight in highlights) _BulletText(text: highlight),
          ],
        ),
      ),
    );
  }
}

class _SectionGroup extends StatelessWidget {
  const _SectionGroup({required this.sections});

  final List<LegalSection> sections;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.54),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: Colors.white.withValues(alpha: 0.78)),
      ),
      child: Column(
        children: [
          for (var index = 0; index < sections.length; index++) ...[
            _SectionBlock(section: sections[index]),
            if (index != sections.length - 1)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 18),
                child: Divider(
                  height: 1,
                  color: AppColors.ink.withValues(alpha: 0.08),
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class _SectionBlock extends StatelessWidget {
  const _SectionBlock({required this.section});

  final LegalSection section;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 17),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            section.title,
            style: const TextStyle(
              color: AppColors.ink,
              fontFamily: AppTypography.systemFont,
              fontSize: 16,
              fontWeight: FontWeight.w800,
              height: 1.32,
              letterSpacing: 0,
            ),
          ),
          if (section.paragraphs.isNotEmpty) const SizedBox(height: 10),
          for (final paragraph in section.paragraphs)
            _ParagraphText(text: paragraph),
          if (section.bullets.isNotEmpty) ...[
            if (section.paragraphs.isNotEmpty) const SizedBox(height: 2),
            for (final bullet in section.bullets) _BulletText(text: bullet),
          ],
        ],
      ),
    );
  }
}

class _ParagraphText extends StatelessWidget {
  const _ParagraphText({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 9),
      child: Text(
        text,
        style: const TextStyle(
          color: Color(0xD9142033),
          fontFamily: AppTypography.systemFont,
          fontSize: 13.5,
          fontWeight: FontWeight.w500,
          height: 1.72,
          letterSpacing: 0,
        ),
      ),
    );
  }
}

class _BulletText extends StatelessWidget {
  const _BulletText({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 9),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: AppColors.brand.withValues(alpha: 0.9),
                borderRadius: BorderRadius.circular(AppRadii.full),
              ),
              child: const SizedBox(width: 5, height: 5),
            ),
          ),
          const SizedBox(width: 9),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(
                color: Color(0xD9142033),
                fontFamily: AppTypography.systemFont,
                fontSize: 13.5,
                fontWeight: FontWeight.w500,
                height: 1.68,
                letterSpacing: 0,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _VersionFooter extends StatelessWidget {
  const _VersionFooter({required this.document});

  final LegalDocument document;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.ink.withValues(alpha: 0.045),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '版本：${document.version}',
              style: const TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 12,
                fontWeight: FontWeight.w800,
                height: 1.45,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 3),
            Text(
              '生效日期：${document.effectiveDate}',
              style: const TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 12,
                fontWeight: FontWeight.w700,
                height: 1.45,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              '本文为产品合规草案，正式上线前需要运营主体、第三方服务清单和法务意见确认。',
              style: TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 12,
                fontWeight: FontWeight.w600,
                height: 1.55,
                letterSpacing: 0,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
