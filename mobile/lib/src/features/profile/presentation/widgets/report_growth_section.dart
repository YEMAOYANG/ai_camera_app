import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/shared/widgets/app_surface.dart';

class ReportGrowthSection extends StatefulWidget {
  const ReportGrowthSection({required this.maps, super.key});
  final List<ReportSkillMap> maps;

  @override
  State<ReportGrowthSection> createState() => _ReportGrowthSectionState();
}

class _ReportGrowthSectionState extends State<ReportGrowthSection> {
  String? selectedChild;

  @override
  Widget build(BuildContext context) {
    if (widget.maps.isEmpty) return const SizedBox.shrink();
    final map = widget.maps.firstWhere(
      (m) => m.childId == selectedChild,
      orElse: () => widget.maps.first,
    );
    final observed = map.skills.where((s) => s.observed).toList();
    return AppSurface(
      radius: 22,
      padding: const EdgeInsets.all(16),
      child: Material(
        color: Colors.transparent,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('成长能力图谱', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 4),
            Text(
              '${map.childName} · 摄像头、家长确认与课件学习',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            if (widget.maps.length > 1) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 4,
                children: [
                  for (final child in widget.maps)
                    ChoiceChip(
                      label: Text(child.childName),
                      labelStyle: const TextStyle(
                        fontFamily: AppTypography.systemFont,
                      ),
                      selected: child.childId == map.childId,
                      onSelected: (_) =>
                          setState(() => selectedChild = child.childId),
                    ),
                ],
              ),
            ],
            const SizedBox(height: 12),
            Text(
              observed.isEmpty ? '等待第一份直接证据' : '本期有 ${observed.length} 项表现记录',
              style: Theme.of(context).textTheme.titleSmall,
            ),
            const SizedBox(height: 8),
            // Missing axes stay blank. They are never plotted as zero ability.
            if (MediaQuery.textScalerOf(context).scale(1) <= 1.2)
              SizedBox(
                height: 220,
                child: CustomPaint(painter: _GrowthRadar(map.skills)),
              ),
            for (final skill in map.skills) ...[
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                    flex: 2,
                    child: Text(
                      skill.label,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    flex: 3,
                    child: LinearProgressIndicator(
                      value: skill.ratio,
                      minHeight: 6,
                      backgroundColor: AppColors.surfaceStrong,
                      color: skill.observed
                          ? AppColors.brand
                          : AppColors.border,
                    ),
                  ),
                  const SizedBox(width: 10),
                  SizedBox(
                    width: 66,
                    child: Text(
                      skill.scoreLabel,
                      textAlign: TextAlign.end,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 14),
            Text(map.scope, style: Theme.of(context).textTheme.bodySmall),
            ExpansionTile(
              key: ValueKey('growth-evidence-${map.childId}'),
              tilePadding: EdgeInsets.zero,
              title: const Text('查看评分依据'),
              children: [
                for (final skill in map.skills)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 14),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          '${skill.label} · ${skill.scoreLabel}',
                          style: Theme.of(context).textTheme.titleSmall,
                        ),
                        Text(
                          skill.detail,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                        for (final item in skill.evidence) ...[
                          const SizedBox(height: 5),
                          Text(
                            '${item.recordDate} · ${item.label} · ${item.correct}/${item.total}',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                          Text(
                            item.detail,
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ],
                      ],
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

class _GrowthRadar extends CustomPainter {
  _GrowthRadar(this.skills);
  final List<ReportSkill> skills;

  @override
  void paint(Canvas canvas, Size size) {
    if (skills.length < 3) return;
    final center = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width, size.height) * 0.32;
    final grid = Paint()
      ..color = AppColors.border
      ..style = PaintingStyle.stroke;
    final point = Paint()..color = AppColors.brand;
    Offset position(int i, double scale) {
      final angle = -math.pi / 2 + 2 * math.pi * i / skills.length;
      return center + Offset(math.cos(angle), math.sin(angle)) * radius * scale;
    }

    for (var level = 1; level <= 4; level++) {
      final path = Path();
      for (var i = 0; i < skills.length; i++) {
        final p = position(i, level / 4);
        if (i == 0) {
          path.moveTo(p.dx, p.dy);
        } else {
          path.lineTo(p.dx, p.dy);
        }
      }
      canvas.drawPath(path..close(), grid);
    }
    for (var i = 0; i < skills.length; i++) {
      canvas.drawLine(center, position(i, 1), grid);
      if (skills[i].observed) {
        canvas.drawLine(
          center,
          position(i, skills[i].ratio),
          Paint()
            ..color = AppColors.brand.withValues(alpha: .35)
            ..strokeWidth = 2,
        );
        canvas.drawCircle(position(i, skills[i].ratio), 4, point);
      }
      final label = TextPainter(
        text: TextSpan(
          text: skills[i].label,
          style: TextStyle(
            color: skills[i].observed ? AppColors.ink : AppColors.subtle,
            fontFamily: AppTypography.systemFont,
            fontSize: 11,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: 62);
      label.paint(
        canvas,
        position(i, 1.35) - Offset(label.width / 2, label.height / 2),
      );
    }
  }

  @override
  bool shouldRepaint(covariant _GrowthRadar oldDelegate) =>
      oldDelegate.skills != skills;
}
