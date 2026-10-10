import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import '../../learning_review/domain/learning_review_models.dart';
import '../../learning_review/presentation/learning_support_widgets.dart';
import '../application/homework_repository.dart';
import '../domain/homework_models.dart';

class HomeworkPageEditor extends ConsumerStatefulWidget {
  const HomeworkPageEditor({
    required this.submission,
    required this.page,
    super.key,
  });
  final HomeworkSubmission submission;
  final HomeworkPage page;
  @override
  ConsumerState<HomeworkPageEditor> createState() => _HomeworkPageEditorState();
}

class _HomeworkPageEditorState extends ConsumerState<HomeworkPageEditor> {
  late int rotation = widget.page.rotation;
  late Rect crop = _readCrop(widget.page.data['crop']);
  Offset? start;
  static Rect _readCrop(Object? value) {
    final r = jsonMap(value);
    return r.isEmpty
        ? const Rect.fromLTWH(0, 0, 1, 1)
        : Rect.fromLTWH(
            (r['x'] as num).toDouble(),
            (r['y'] as num).toDouble(),
            (r['width'] as num).toDouble(),
            (r['height'] as num).toDouble(),
          );
  }

  @override
  Widget build(BuildContext context) {
    final key = (
      submissionId: widget.submission.id,
      pageId: widget.page.id,
      revision: widget.submission.revision,
      original: true,
    );
    final image = ref.watch(homeworkImageProvider(key));
    return Scaffold(
      appBar: AppBar(title: const Text('旋转与裁剪')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              const Text('拖动画出需要保留的区域。尽量保留题号和完整作答。'),
              const SizedBox(height: 12),
              Expanded(
                child: image.when(
                  loading: () => const LearningLoading(),
                  error: (e, _) => LearningError(
                    e,
                    () => ref.invalidate(homeworkImageProvider(key)),
                  ),
                  data: (bytes) => Center(
                    child: AspectRatio(
                      aspectRatio: rotation % 180 == 0
                          ? widget.page.aspectRatio
                          : 1 / widget.page.aspectRatio,
                      child: _canvas(bytes),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  TextButton.icon(
                    onPressed: () => setState(() {
                      rotation = (rotation + 90) % 360;
                      crop = const Rect.fromLTWH(0, 0, 1, 1);
                    }),
                    icon: const Icon(Icons.rotate_right),
                    label: const Text('向右旋转'),
                  ),
                  TextButton(
                    onPressed: () =>
                        setState(() => crop = const Rect.fromLTWH(0, 0, 1, 1)),
                    child: const Text('保留整页'),
                  ),
                ],
              ),
              AppPrimaryButton(
                label: '使用此页面',
                onTap: image.hasValue
                    ? () => Navigator.pop(context, {
                        'id': widget.page.id,
                        'rotation': rotation,
                        'crop': crop == const Rect.fromLTWH(0, 0, 1, 1)
                            ? null
                            : {
                                'x': crop.left,
                                'y': crop.top,
                                'width': crop.width,
                                'height': crop.height,
                              },
                      })
                    : null,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _canvas(Uint8List bytes) => LayoutBuilder(
    builder: (context, size) {
      Offset normalized(Offset p) => Offset(
        (p.dx / size.maxWidth).clamp(0, 1),
        (p.dy / size.maxHeight).clamp(0, 1),
      );
      return GestureDetector(
        onPanStart: (e) {
          start = normalized(e.localPosition);
        },
        onPanUpdate: (e) {
          final end = normalized(e.localPosition);
          final rect = Rect.fromPoints(start!, end);
          if (rect.width >= 0.03 && rect.height >= 0.03) {
            setState(() => crop = rect);
          }
        },
        child: Stack(
          fit: StackFit.expand,
          children: [
            RotatedBox(
              quarterTurns: rotation ~/ 90,
              child: Image.memory(bytes, fit: BoxFit.fill),
            ),
            CustomPaint(painter: _CropPainter(crop)),
            Positioned(
              left: 8,
              top: 8,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: AppColors.ink.withValues(alpha: 0.8),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Padding(
                  padding: EdgeInsets.all(6),
                  child: Text(
                    '框内区域将被保留',
                    style: TextStyle(color: Colors.white, fontSize: 12),
                  ),
                ),
              ),
            ),
          ],
        ),
      );
    },
  );
}

class _CropPainter extends CustomPainter {
  const _CropPainter(this.rect);
  final Rect rect;
  @override
  void paint(Canvas canvas, Size size) {
    final r = Rect.fromLTWH(
      rect.left * size.width,
      rect.top * size.height,
      rect.width * size.width,
      rect.height * size.height,
    );
    final path = Path()
      ..addRect(Offset.zero & size)
      ..addRect(r)
      ..fillType = PathFillType.evenOdd;
    canvas.drawPath(path, Paint()..color = Colors.black.withValues(alpha: 0.4));
    canvas.drawRect(
      r,
      Paint()
        ..color = AppColors.brandDeep
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3,
    );
  }

  @override
  bool shouldRepaint(_CropPainter oldDelegate) => oldDelegate.rect != rect;
}
