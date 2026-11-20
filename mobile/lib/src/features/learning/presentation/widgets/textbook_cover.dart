import 'package:flutter/material.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';

/// Small illustrated jackets for subjects. Edition details are shown in the
/// surrounding row so this artwork can be shared across textbook versions.
class TextbookCover extends StatelessWidget {
  const TextbookCover({
    required this.subject,
    this.volumeLabel,
    this.placeholder = false,
    this.width = 48,
    super.key,
  });

  final String subject;
  final String? volumeLabel;
  final bool placeholder;
  final double width;

  @override
  Widget build(BuildContext context) {
    final style = TextbookSubjectStyle.forSubject(subject);
    final art = style.art;
    final captionHeight = width * .34;
    final fallback = Center(
      child: Icon(
        Icons.auto_stories_outlined,
        size: width * .38,
        color: style.ink,
      ),
    );

    return ExcludeSemantics(
      child: SizedBox(
        width: width,
        height: width * 1.39,
        child: ClipRRect(
          borderRadius: const BorderRadius.horizontal(
            left: Radius.circular(2),
            right: Radius.circular(5),
          ),
          child: ColoredBox(
            color: style.paper,
            child: Stack(
              children: [
                Positioned(
                  left: width * .07,
                  right: 0,
                  top: 0,
                  bottom: captionHeight,
                  child: Opacity(
                    opacity: placeholder ? .48 : 1,
                    child: art == null
                        ? fallback
                        : Image.asset(
                            art,
                            fit: BoxFit.cover,
                            excludeFromSemantics: true,
                            errorBuilder: (_, _, _) => fallback,
                          ),
                  ),
                ),
                Positioned(
                  left: width * .07,
                  right: 0,
                  bottom: 0,
                  height: captionHeight,
                  child: Center(
                    child: placeholder
                        ? Icon(Icons.add, size: width * .28, color: style.ink)
                        : FittedBox(
                            fit: BoxFit.scaleDown,
                            child: Text(
                              volumeLabel ?? '课本',
                              textScaler: TextScaler.noScaling,
                              style: TextStyle(
                                fontSize: width * .205,
                                fontWeight: FontWeight.w700,
                                height: 1,
                                color: style.ink,
                              ),
                            ),
                          ),
                  ),
                ),
                Positioned(
                  left: 0,
                  top: 0,
                  bottom: 0,
                  width: width * .07,
                  child: ColoredBox(color: style.ink.withValues(alpha: .28)),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class TextbookSubjectStyle {
  const TextbookSubjectStyle(this.paper, this.ink, {this.art});

  final Color paper;
  final Color ink;
  final String? art;

  static const _assetDirectory = 'assets/images/bookplates';

  static TextbookSubjectStyle forSubject(String subject) => switch (subject) {
    'chinese' => const TextbookSubjectStyle(
      Color(0xFFF3E4D7),
      Color(0xFF843F32),
      art: '$_assetDirectory/chinese.webp',
    ),
    'math' => const TextbookSubjectStyle(
      Color(0xFFE6EBDD),
      Color(0xFF3E6054),
      art: '$_assetDirectory/math.webp',
    ),
    'english' => const TextbookSubjectStyle(
      Color(0xFFF4E8C8),
      Color(0xFF745217),
      art: '$_assetDirectory/english.webp',
    ),
    'science' => const TextbookSubjectStyle(
      Color(0xFFE2EDDE),
      Color(0xFF376251),
      art: '$_assetDirectory/science.webp',
    ),
    _ => const TextbookSubjectStyle(
      AppColors.surfaceStrong,
      AppColors.mutedStrong,
    ),
  };
}
