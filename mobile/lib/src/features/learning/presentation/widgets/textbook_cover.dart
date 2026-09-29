import 'package:flutter/material.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';

/// App-owned subject identifiers, not reproductions of a publisher's cover.
/// Edition, publisher and school system remain readable alongside them.
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
    return ExcludeSemantics(
      child: SizedBox(
        width: width,
        height: width * 1.36,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: style.paper,
            borderRadius: const BorderRadius.horizontal(
              left: Radius.circular(3),
              right: Radius.circular(7),
            ),
            boxShadow: [
              BoxShadow(
                color: style.ink.withValues(alpha: 0.10),
                blurRadius: 5,
                offset: const Offset(1, 3),
              ),
            ],
          ),
          child: Stack(
            children: [
              Positioned(
                left: 5,
                top: 0,
                bottom: 0,
                child: ColoredBox(
                  color: style.ink.withValues(alpha: 0.14),
                  child: const SizedBox(width: 1),
                ),
              ),
              Positioned.fill(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(12, 8, 6, 8),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      FittedBox(
                        fit: BoxFit.scaleDown,
                        alignment: Alignment.centerLeft,
                        child: Text(
                          style.mark,
                          maxLines: 1,
                          textScaler: TextScaler.noScaling,
                          style: TextStyle(
                            fontSize: width * 0.35,
                            height: 1.15,
                            fontWeight: FontWeight.w700,
                            color: style.ink,
                          ),
                        ),
                      ),
                      const Spacer(),
                      if (placeholder)
                        Icon(Icons.add, size: 14, color: style.ink)
                      else
                        Text(
                          volumeLabel ?? '课本',
                          textScaler: TextScaler.noScaling,
                          style: TextStyle(
                            fontSize: 10,
                            height: 1.2,
                            color: style.ink,
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class TextbookSubjectStyle {
  const TextbookSubjectStyle(this.mark, this.paper, this.ink);

  final String mark;
  final Color paper, ink;

  static TextbookSubjectStyle forSubject(String subject) => switch (subject) {
    'chinese' => const TextbookSubjectStyle(
      '文',
      Color(0xFFF8E6DF),
      Color(0xFF924933),
    ),
    'math' => const TextbookSubjectStyle(
      '数',
      AppColors.brandWash,
      Color(0xFF345AA0),
    ),
    'english' => const TextbookSubjectStyle(
      'Aa',
      AppColors.brandWarmWash,
      Color(0xFF885719),
    ),
    'science' => const TextbookSubjectStyle(
      '科',
      AppColors.brandSageWash,
      Color(0xFF376E5D),
    ),
    _ => const TextbookSubjectStyle(
      '书',
      AppColors.surfaceStrong,
      AppColors.mutedStrong,
    ),
  };
}
