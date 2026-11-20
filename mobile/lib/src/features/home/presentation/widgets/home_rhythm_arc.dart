import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/home/domain/home_models.dart';

typedef _TimedNode = ({int minute, RhythmNodeState state});

class HomeRhythmArc extends StatelessWidget {
  const HomeRhythmArc({
    required this.nodes,
    required this.now,
    this.padding = const EdgeInsets.fromLTRB(
      AppSpacing.pageHorizontalExpanded,
      0,
      AppSpacing.pageHorizontalExpanded,
      13,
    ),
    super.key,
  });

  final List<RhythmNode> nodes;
  final DateTime now;
  final EdgeInsetsGeometry padding;

  static final _timePattern = RegExp(r'^(\d{1,2}):(\d{2})(?::\d{2})?$');

  @override
  Widget build(BuildContext context) {
    final timed = <_TimedNode>[];
    for (final node in nodes) {
      final match = _timePattern.firstMatch(node.timeLabel.trim());
      if (match == null) continue;
      final hour = int.parse(match[1]!);
      final minute = int.parse(match[2]!);
      if (hour < 24 && minute < 60) {
        timed.add((minute: hour * 60 + minute, state: node.state));
      }
    }
    if (timed.isEmpty) return const SizedBox.shrink();

    final current = now.hour * 60 + now.minute;
    var start = math.min(360, current);
    var end = math.max(1320, current);
    for (final node in timed) {
      start = math.min(start, node.minute);
      end = math.max(end, node.minute);
    }
    start = start ~/ 60 * 60;
    end = (end / 60).ceil() * 60;

    return Padding(
      padding: padding,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(
            alignment: WrapAlignment.spaceBetween,
            spacing: 14,
            runSpacing: 4,
            children: [
              const Text(
                '今日节奏',
                style: TextStyle(
                  color: AppColors.navActiveFg,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
              Text('现在 ${_clock(current)}', style: _timeStyle),
            ],
          ),
          const SizedBox(height: 4),
          ExcludeSemantics(
            child: SizedBox(
              height: 48,
              child: CustomPaint(
                painter: _RhythmArcPainter(
                  nodes: timed,
                  currentMinute: current,
                  startMinute: start,
                  endMinute: end,
                ),
              ),
            ),
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(_clock(start), style: _timeStyle),
              Text(_clock(end), style: _timeStyle),
            ],
          ),
        ],
      ),
    );
  }

  static String _clock(int minute) =>
      '${(minute ~/ 60).toString().padLeft(2, '0')}:${(minute % 60).toString().padLeft(2, '0')}';

  static const _timeStyle = TextStyle(
    color: AppColors.navInactiveFg,
    fontSize: 11,
    fontWeight: FontWeight.w500,
    fontFeatures: [FontFeature.tabularFigures()],
  );
}

class _RhythmArcPainter extends CustomPainter {
  const _RhythmArcPainter({
    required this.nodes,
    required this.currentMinute,
    required this.startMinute,
    required this.endMinute,
  });

  final List<_TimedNode> nodes;
  final int currentMinute;
  final int startMinute;
  final int endMinute;

  @override
  void paint(Canvas canvas, Size size) {
    final bottom = size.height - 6;
    final span = endMinute - startMinute;
    double fraction(int minute) => (minute - startMinute) / span;
    Offset point(double time) => Offset(
      3 + (size.width - 6) * time,
      bottom - (size.height - 12) * 4 * time * (1 - time),
    );

    Path curve(double from, double to) {
      final first = point(from);
      final last = point(to);
      final mid = point((from + to) / 2);
      final control = mid * 2 - (first + last) * .5;
      return Path()
        ..moveTo(first.dx, first.dy)
        ..quadraticBezierTo(control.dx, control.dy, last.dx, last.dy);
    }

    final now = fraction(currentMinute);
    final marker = point(now);
    final start = point(0);
    final elapsed = curve(0, now);
    final tintArea = Path.from(elapsed)
      ..lineTo(marker.dx, bottom)
      ..lineTo(start.dx, bottom)
      ..close();
    canvas.drawPath(
      tintArea,
      Paint()..color = AppColors.brandSageWash.withValues(alpha: .56),
    );
    canvas.drawPath(
      curve(now, 1),
      Paint()
        ..color = AppColors.brandSoft
        ..strokeWidth = 1
        ..style = PaintingStyle.stroke,
    );
    canvas.drawPath(
      elapsed,
      Paint()
        ..color = AppColors.brandSage
        ..strokeWidth = 1.45
        ..strokeCap = StrokeCap.round
        ..style = PaintingStyle.stroke,
    );

    for (final node in nodes) {
      final center = point(fraction(node.minute));
      final complete = node.state == RhythmNodeState.completed;
      final color = complete ? AppColors.brandSage : AppColors.brandSoft;
      canvas.drawCircle(center, 3.4, Paint()..color = color);
      if (!complete) {
        canvas.drawCircle(center, 2.15, Paint()..color = AppColors.shellPaper);
      }
    }
    canvas.drawCircle(marker, 6.5, Paint()..color = AppColors.shellPaper);
    canvas.drawCircle(marker, 4.65, Paint()..color = AppColors.brandWarm);
  }

  @override
  bool shouldRepaint(_RhythmArcPainter oldDelegate) =>
      currentMinute != oldDelegate.currentMinute ||
      startMinute != oldDelegate.startMinute ||
      endMinute != oldDelegate.endMinute ||
      !listEquals(nodes, oldDelegate.nodes);
}
