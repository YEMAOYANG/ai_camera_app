import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';

enum CameraDiscoveryVisualState {
  ready,
  permission,
  searching,
  found,
  connecting,
  success,
  notFound,
  failed,
}

/// CustomPaint layers for the Mira dual-frequency sonar discovery effect.
class DiscoverySonarPainter extends CustomPainter {
  DiscoverySonarPainter({
    required this.state,
    required this.progress,
    this.collapseProgress = 0,
    this.confirmPulse = 0,
  });

  final CameraDiscoveryVisualState state;
  final double progress;
  final double collapseProgress;
  final double confirmPulse;

  bool get _muted =>
      state == CameraDiscoveryVisualState.notFound ||
      state == CameraDiscoveryVisualState.failed;

  bool get _activeSearch =>
      state == CameraDiscoveryVisualState.searching ||
      state == CameraDiscoveryVisualState.found;

  bool get _connecting => state == CameraDiscoveryVisualState.connecting;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final minSide = math.min(size.width, size.height);
    final radius = minSide * 0.4;
    final breath = 0.14 + math.sin(progress * math.pi * 2) * 0.06;

    _drawAmbientGlow(canvas, center, radius, breath);
    if (!_muted && state != CameraDiscoveryVisualState.success) {
      if (_connecting) {
        _drawConnectingPulse(canvas, center, radius);
      } else if (_activeSearch) {
        _drawImpulseFills(canvas, center, radius);
        _drawRadarWedge(canvas, center, radius);
        _drawSonarGrid(canvas, center, radius);
        _drawTripleRings(canvas, center, radius);
        if (collapseProgress < 0.92) {
          _drawDualScanArcs(canvas, center, radius);
          _drawScanLine(canvas, center, radius);
          _drawOrbitBeacons(canvas, center, radius);
        }
      }
      if (state == CameraDiscoveryVisualState.found && confirmPulse > 0) {
        _drawSuccessRing(canvas, center, radius, confirmPulse);
      }
    }
  }

  void _drawAmbientGlow(
    Canvas canvas,
    Offset center,
    double radius,
    double breath,
  ) {
    final alpha = _muted ? 0.05 : breath;
    for (var layer = 0; layer < 2; layer++) {
      final scale = 1.35 + layer * 0.28;
      final rect = Rect.fromCircle(center: center, radius: radius * scale);
      final glow = Paint()
        ..shader = RadialGradient(
          colors: [
            AppColors.brandSageWash.withValues(alpha: alpha * (2.0 - layer * 0.4)),
            AppColors.brandWarmWash.withValues(alpha: alpha * (1.2 - layer * 0.2)),
            Colors.transparent,
          ],
          stops: const [0, 0.48, 1],
        ).createShader(rect);
      canvas.drawCircle(center, radius * scale, glow);
    }
  }

  void _drawImpulseFills(Canvas canvas, Offset center, double radius) {
    final collapse = collapseProgress.clamp(0.0, 1.0);
    for (var i = 0; i < 2; i++) {
      final phase = ((progress + i * 0.5) % 1);
      final r = radius * (0.28 + phase * 0.82) * (1 - collapse * 0.5);
      final alpha = ((1 - phase) * 0.14).clamp(0.0, 0.14) * (1 - collapse);
      final color = i == 0 ? AppColors.brandSage : AppColors.brandWarm;
      canvas.drawCircle(
        center,
        r,
        Paint()..color = color.withValues(alpha: alpha),
      );
    }
  }

  void _drawRadarWedge(Canvas canvas, Offset center, double radius) {
    final collapse = collapseProgress.clamp(0.0, 1.0);
    final angle = progress * math.pi * 2;
    final sweep = math.pi / 4.8;
    final wedgeRadius = radius * (0.98 - collapse * 0.2);
    final path = Path()
      ..moveTo(center.dx, center.dy)
      ..arcTo(
        Rect.fromCircle(center: center, radius: wedgeRadius),
        angle,
        sweep,
        false,
      )
      ..close();
    canvas.drawPath(
      path,
      Paint()..color = AppColors.brandSage.withValues(alpha: 0.16 * (1 - collapse)),
    );
  }

  void _drawScanLine(Canvas canvas, Offset center, double radius) {
    final angle = progress * math.pi * 2;
    final end = Offset(
      center.dx + math.cos(angle) * radius * 0.94,
      center.dy + math.sin(angle) * radius * 0.94,
    );
    final linePaint = Paint()
      ..strokeWidth = 1.4
      ..strokeCap = StrokeCap.round
      ..shader = LinearGradient(
        colors: [
          AppColors.brandWarm.withValues(alpha: 0.05),
          AppColors.brandWarm.withValues(alpha: 0.55),
          AppColors.brandSage.withValues(alpha: 0.35),
        ],
        stops: const [0, 0.72, 1],
      ).createShader(Rect.fromPoints(center, end));
    canvas.drawLine(center, end, linePaint);
  }

  void _drawSonarGrid(Canvas canvas, Offset center, double radius) {
    final collapse = collapseProgress.clamp(0.0, 1.0);
    final gridAlpha = (0.12 * (1 - collapse * 0.7)).clamp(0.0, 0.12);
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.8
      ..color = AppColors.brandSage.withValues(alpha: gridAlpha);
    for (var i = 1; i <= 3; i++) {
      canvas.drawCircle(center, radius * (0.32 + i * 0.22), paint);
    }
    for (var i = 0; i < 8; i++) {
      final angle = i * math.pi / 4 + progress * 0.15;
      final end = Offset(
        center.dx + math.cos(angle) * radius * 0.92,
        center.dy + math.sin(angle) * radius * 0.92,
      );
      canvas.drawLine(center, end, paint);
    }
  }

  void _drawTripleRings(Canvas canvas, Offset center, double radius) {
    final collapse = collapseProgress.clamp(0.0, 1.0);
    final minScale = 0.34;
    for (var band = 0; band < 3; band++) {
      final phase = ((progress + band * 0.33) % 1);
      final expand = phase * (1 - collapse * 0.88);
      final ringRadius = radius * (minScale + expand * 0.98);
      final opacity = ((1 - phase) * 0.58).clamp(0.0, 0.58) * (1 - collapse);
      final stroke = 2.2 - phase * 1.2;
      final rect = Rect.fromCircle(center: center, radius: ringRadius);
      final ringPaint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = stroke
        ..shader = SweepGradient(
          colors: [
            AppColors.brandSage.withValues(alpha: 0),
            AppColors.brandSage.withValues(alpha: opacity),
            AppColors.brandWarm.withValues(alpha: opacity * 0.85),
            AppColors.brandSage.withValues(alpha: 0),
          ],
          transform: GradientRotation(progress * math.pi * 2 + band),
        ).createShader(rect);
      canvas.drawCircle(center, ringRadius, ringPaint);
    }
  }

  void _drawDualScanArcs(Canvas canvas, Offset center, double radius) {
    final primaryAngle = progress * math.pi * 2;
    final secondaryAngle = -progress * math.pi * 1.6 + math.pi * 0.35;
    _drawScanArc(
      canvas,
      center,
      radius * 0.88,
      primaryAngle,
      math.pi * 0.72,
      AppColors.brandWarm,
      3.2,
      0.52,
    );
    _drawScanArc(
      canvas,
      center,
      radius * 0.62,
      secondaryAngle,
      math.pi * 0.55,
      AppColors.brandSage,
      2.4,
      0.38,
    );
  }

  void _drawScanArc(
    Canvas canvas,
    Offset center,
    double orbit,
    double angle,
    double sweep,
    Color color,
    double strokeWidth,
    double alpha,
  ) {
    final rect = Rect.fromCircle(center: center, radius: orbit);
    final arcPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round
      ..color = color.withValues(alpha: alpha);
    canvas.drawArc(rect, angle, sweep, false, arcPaint);

    final tipAngle = angle + sweep;
    final tip = Offset(
      center.dx + math.cos(tipAngle) * orbit,
      center.dy + math.sin(tipAngle) * orbit,
    );
    for (var i = 0; i < 4; i++) {
      final sparkOffset = Offset(
        tip.dx - math.cos(tipAngle) * i * 5,
        tip.dy - math.sin(tipAngle) * i * 5,
      );
      canvas.drawCircle(
        sparkOffset,
        3.2 - i * 0.55,
        Paint()
          ..color = color.withValues(alpha: (0.65 - i * 0.14).clamp(0.15, 0.65)),
      );
    }
    final glowPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth + 4
      ..color = color.withValues(alpha: alpha * 0.22);
    canvas.drawArc(rect, angle, sweep, false, glowPaint);
  }

  void _drawOrbitBeacons(Canvas canvas, Offset center, double radius) {
    for (var i = 0; i < 6; i++) {
      final angle = i * math.pi * 2 / 6 + progress * math.pi * 2;
      final orbit = radius * (0.52 + (i.isEven ? 0.18 : 0.32));
      final dot = Offset(
        center.dx + math.cos(angle) * orbit,
        center.dy + math.sin(angle) * orbit * 0.88,
      );
      final pulse = (math.sin(progress * math.pi * 4 + i) + 1) / 2;
      canvas.drawCircle(
        dot,
        2.2 + pulse * 1.2,
        Paint()
          ..color = (i.isEven ? AppColors.brandSage : AppColors.brandWarm)
              .withValues(alpha: 0.18 + pulse * 0.38),
      );
    }
  }

  void _drawConnectingPulse(Canvas canvas, Offset center, double radius) {
    final pulse = (math.sin(progress * math.pi * 2) + 1) / 2;
    for (var i = 0; i < 2; i++) {
      final phase = ((progress + i * 0.5) % 1);
      final ringRadius = radius * (0.48 + phase * 0.42);
      final color = i == 0 ? AppColors.brandSage : AppColors.brand;
      final paint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.2
        ..color = color.withValues(alpha: (1 - phase) * 0.5 * pulse + 0.1);
      canvas.drawCircle(center, ringRadius, paint);
    }
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius * 0.16),
      progress * math.pi * 2,
      math.pi * 1.25,
      false,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.2
        ..color = AppColors.brandSoft.withValues(alpha: 0.55),
    );
  }

  void _drawSuccessRing(
    Canvas canvas,
    Offset center,
    double radius,
    double pulse,
  ) {
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.8
      ..color = AppColors.success.withValues(alpha: (1 - pulse) * 0.62);
    canvas.drawCircle(center, radius * (0.46 + pulse * 0.38), paint);
  }

  @override
  bool shouldRepaint(DiscoverySonarPainter oldDelegate) {
    return oldDelegate.state != state ||
        oldDelegate.progress != progress ||
        oldDelegate.collapseProgress != collapseProgress ||
        oldDelegate.confirmPulse != confirmPulse;
  }
}

/// Compact pulsing ring for discovered-device tile icon.
class DiscoveryIconRingPainter extends CustomPainter {
  DiscoveryIconRingPainter({required this.progress, required this.active});

  final double progress;
  final bool active;

  @override
  void paint(Canvas canvas, Size size) {
    if (!active) return;
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width * 0.46;
    for (var i = 0; i < 2; i++) {
      final phase = ((progress + i * 0.5) % 1);
      final ringR = radius * (0.72 + phase * 0.28);
      final alpha = ((1 - phase) * 0.35).clamp(0.0, 0.35);
      canvas.drawCircle(
        center,
        ringR,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.8
          ..color = AppColors.brandSage.withValues(alpha: alpha),
      );
    }
  }

  @override
  bool shouldRepaint(DiscoveryIconRingPainter oldDelegate) {
    return oldDelegate.progress != progress || oldDelegate.active != active;
  }
}

/// Shared camera body drawing for sonar scene and device glyph.
class CameraDevicePainter extends CustomPainter {
  CameraDevicePainter({
    required this.scale,
    this.statusLightColor = AppColors.brandWarm,
    this.showLensRing = false,
    this.lensRingProgress = 0,
    this.elevated = false,
  });

  final double scale;
  final Color statusLightColor;
  final bool showLensRing;
  final double lensRingProgress;
  final bool elevated;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final minSide = math.min(size.width, size.height) * scale;
    if (elevated) {
      final podRect = Rect.fromCenter(
        center: center,
        width: minSide * 0.92,
        height: minSide * 0.88,
      );
      final podRRect = RRect.fromRectAndRadius(
        podRect,
        Radius.circular(minSide * 0.2),
      );
      canvas.drawRRect(
        podRRect.shift(const Offset(0, 4)),
        Paint()
          ..color = AppColors.brandSage.withValues(alpha: 0.12)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 12),
      );
      canvas.drawRRect(
        podRRect,
        Paint()
          ..shader = LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              AppColors.brandSageWash.withValues(alpha: 0.95),
              AppColors.surfaceElevated,
            ],
          ).createShader(podRect),
      );
      canvas.drawRRect(
        podRRect,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1
          ..color = AppColors.brandSage.withValues(alpha: 0.18),
      );
    }
    _drawCameraBody(
      canvas,
      center,
      minSide * (elevated ? 0.78 : 1),
      statusLightColor: statusLightColor,
      showLensRing: showLensRing,
      lensRingProgress: lensRingProgress,
    );
  }

  static void _drawCameraBody(
    Canvas canvas,
    Offset center,
    double minSide, {
    required Color statusLightColor,
    required bool showLensRing,
    required double lensRingProgress,
  }) {
    final bodyWidth = minSide * 0.72;
    final bodyHeight = minSide * 0.62;
    final bodyRect = Rect.fromCenter(
      center: center.translate(0, minSide * 0.02),
      width: bodyWidth,
      height: bodyHeight,
    );
    final bodyRRect = RRect.fromRectAndRadius(
      bodyRect,
      Radius.circular(minSide * 0.14),
    );
    final shadow = Paint()
      ..color = const Color(0x22000000)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 12);
    canvas.drawRRect(bodyRRect.shift(const Offset(0, 5)), shadow);

    final bodyPaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          AppColors.surfaceElevated,
          const Color(0xFFF4F7F5),
        ],
      ).createShader(bodyRect);
    canvas.drawRRect(bodyRRect, bodyPaint);

    final border = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2
      ..color = AppColors.border;
    canvas.drawRRect(bodyRRect, border);

    final lensCenter = bodyRect.center.translate(0, -minSide * 0.03);
    final lensRadius = minSide * 0.16;
    canvas.drawCircle(lensCenter, lensRadius, Paint()..color = AppColors.ink);
    canvas.drawCircle(
      lensCenter.translate(-minSide * 0.04, -minSide * 0.04),
      minSide * 0.04,
      Paint()..color = Colors.white.withValues(alpha: 0.82),
    );
    canvas.drawCircle(
      lensCenter,
      lensRadius * 1.08,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2
        ..color = AppColors.brandSage.withValues(alpha: 0.22),
    );
    if (showLensRing) {
      canvas.drawArc(
        Rect.fromCircle(center: lensCenter, radius: lensRadius * 1.35),
        lensRingProgress * math.pi * 2,
        math.pi * 1.1,
        false,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.8
          ..color = AppColors.brandSoft.withValues(alpha: 0.55),
      );
    }

    final statusCenter = bodyRect.topRight.translate(-minSide * 0.12, minSide * 0.12);
    canvas.drawCircle(
      statusCenter,
      minSide * 0.05,
      Paint()..color = statusLightColor.withValues(alpha: 0.35),
    );
    canvas.drawCircle(
      statusCenter,
      minSide * 0.035,
      Paint()..color = statusLightColor,
    );

    final baseRect = RRect.fromRectAndRadius(
      Rect.fromCenter(
        center: bodyRect.bottomCenter.translate(0, minSide * 0.1),
        width: bodyWidth * 0.52,
        height: minSide * 0.08,
      ),
      Radius.circular(minSide * 0.04),
    );
    canvas.drawRRect(baseRect, Paint()..color = AppColors.borderSoft);
  }

  @override
  bool shouldRepaint(CameraDevicePainter oldDelegate) {
    return oldDelegate.scale != scale ||
        oldDelegate.statusLightColor != statusLightColor ||
        oldDelegate.showLensRing != showLensRing ||
        oldDelegate.lensRingProgress != lensRingProgress ||
        oldDelegate.elevated != elevated;
  }
}
