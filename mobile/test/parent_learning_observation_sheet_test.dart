import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/learning/application/learning_observation_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_observation_models.dart';
import 'package:warm_sight/src/features/learning/presentation/widgets/parent_learning_observation_sheet.dart';

void main() {
  setUpAll(() async {
    final bytes = await File(
      'test/assets/fonts/NotoSansCJKsc-Regular.otf',
    ).readAsBytes();
    await (FontLoader(
      AppTypography.systemFont,
    )..addFont(Future.value(ByteData.view(bytes.buffer)))).load();
    final sdk = Platform.environment['FLUTTER_ROOT'];
    if (sdk != null) {
      final icons = await File(
        '$sdk/bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf',
      ).readAsBytes();
      await (FontLoader(
        'MaterialIcons',
      )..addFont(Future.value(ByteData.view(icons.buffer)))).load();
    }
  });
  testWidgets(
    'parent observes the stated lesson and can confirm after further practice',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final gateway = _ObservationGateway();
      final capture = GlobalKey();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            parentObservationRepositoryProvider.overrideWithValue(gateway),
          ],
          child: RepaintBoundary(
            key: capture,
            child: MaterialApp(
              debugShowCheckedModeBanner: false,
              theme: AppTheme.light,
              home: const Scaffold(
                body: SafeArea(
                  child: ParentLearningObservationEntry(
                    childId: 'test-child',
                    childName: '测试孩子',
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('确认孩子的学习表现'));
      await tester.pumpAndSettle();
      expect(find.text('请孩子独立写出本课学过的独体字，观察笔顺是否正确。'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.runAsync(() async {
        final boundary =
            capture.currentContext!.findRenderObject()!
                as RenderRepaintBoundary;
        final image = await boundary.toImage(pixelRatio: 1);
        final data = await image.toByteData(format: ui.ImageByteFormat.png);
        final file = File(
          '../output/flutter/parent-learning-observation-sheet.png',
        );
        await file.parent.create(recursive: true);
        await file.writeAsBytes(data!.buffer.asUint8List());
        image.dispose();
      });
      await tester.tap(find.text('还需练习'));
      await tester.pumpAndSettle();
      expect(gateway.confirmations.single, (
        'test-child',
        'ZH1B02.02',
        'obs_${'a' * 64}',
        false,
      ));
      expect(find.textContaining('练习后可以重新观察'), findsOneWidget);
      await tester.tap(find.text('完成'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('确认孩子的学习表现'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('能独立完成'));
      await tester.pumpAndSettle();
      expect(gateway.confirmations.last, (
        'test-child',
        'ZH1B02.02',
        'obs_${'b' * 64}',
        true,
      ));
      expect(find.textContaining('已记录为能独立完成'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}

class _ObservationGateway implements ParentObservationGateway {
  final confirmations = <(String, String, String, bool)>[];
  @override
  Future<List<ParentObservationLesson>> pending(String childId) async {
    if (confirmations.isNotEmpty && confirmations.last.$4) return [];
    return [
      ParentObservationLesson(
        lessonId: 'ZH1B02.02',
        title: '简单独体字笔顺',
        unitTitle: '基础汉字与书写',
        gradeCode: 'primary_1',
        subject: 'chinese',
        criteria: const [
          '请孩子独立写出本课学过的独体字，观察笔顺是否正确。',
          '请在不示范、不提示的情况下，观察孩子能否独立完成。',
        ],
        confirmationId: 'obs_${(confirmations.isEmpty ? 'a' : 'b') * 64}',
      ),
    ];
  }

  @override
  Future<void> confirm({
    required String childId,
    required ParentObservationLesson lesson,
    required bool confirmed,
  }) async {
    confirmations.add((
      childId,
      lesson.lessonId,
      lesson.confirmationId,
      confirmed,
    ));
  }
}
