import 'dart:ui' show SemanticsAction;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/shared/widgets/app_bottom_sheet.dart';
import 'package:warm_sight/src/shared/widgets/app_glass_surface.dart';

void main() {
  testWidgets(
    'glass adapts to platform and accessibility without losing taps',
    (tester) async {
      var taps = 0;
      for (final mode in [
        (TargetPlatform.iOS, false, false, true),
        (TargetPlatform.android, false, false, true),
        (TargetPlatform.iOS, true, false, false),
        (TargetPlatform.iOS, false, true, false),
      ]) {
        await tester.pumpWidget(
          MaterialApp(
            theme: AppTheme.light.copyWith(platform: mode.$1),
            builder: (context, child) => MediaQuery(
              data: MediaQuery.of(
                context,
              ).copyWith(highContrast: mode.$2, disableAnimations: mode.$3),
              child: child!,
            ),
            home: Scaffold(
              backgroundColor: Colors.black,
              body: Center(
                child: AppGlassSurface(
                  style: AppGlassStyle.navigation,
                  borderRadius: BorderRadius.circular(24),
                  child: TextButton(
                    onPressed: () => taps++,
                    child: const Text('打开任务'),
                  ),
                ),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(
          find.byType(BackdropFilter),
          mode.$4 ? findsOneWidget : findsNothing,
        );
        expect(find.byType(ClipRRect), findsWidgets);
        await tester.tap(find.text('打开任务'));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
      }
      expect(taps, 4);
    },
  );

  test('fallback labels retain contrast over a dark backdrop', () {
    double contrast(Color foreground, Color background) =>
        (background.computeLuminance() + 0.05) /
        (foreground.computeLuminance() + 0.05);

    expect(
      contrast(
        AppColors.navInactiveFg,
        Color.alphaBlend(AppGlass.readableFallback, Colors.black),
      ),
      greaterThanOrEqualTo(4.5),
    );
    expect(
      contrast(
        AppColors.mutedStrong,
        Color.alphaBlend(AppGlass.readableFallback, Colors.black),
      ),
      greaterThanOrEqualTo(4.5),
    );
    expect(
      contrast(
        AppColors.ink,
        Color.alphaBlend(AppGlass.androidNavigationFill, Colors.black),
      ),
      greaterThanOrEqualTo(4.5),
    );
  });

  testWidgets('sheet keeps its actions reachable above a compact keyboard', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    try {
      tester.view
        ..physicalSize = const Size(320, 568)
        ..devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetViewInsets);
      bool? result;

      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light,
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context).copyWith(
              textScaler: const TextScaler.linear(1.3),
              disableAnimations: true,
            ),
            child: child!,
          ),
          home: Scaffold(
            body: Builder(
              builder: (context) => TextButton(
                onPressed: () async {
                  result = await showAppBottomSheet<bool>(
                    context: context,
                    maxHeightFactor: 0.88,
                    child: AppBottomSheetBody(
                      title: '编辑提醒',
                      footer: Builder(
                        builder: (context) => AppSheetPrimaryButton(
                          label: '保存',
                          onTap: () => Navigator.of(context).pop(true),
                        ),
                      ),
                      child: const Column(
                        children: [
                          TextField(
                            decoration: InputDecoration(labelText: '名称'),
                          ),
                          SizedBox(height: 400),
                          Text('提醒内容'),
                        ],
                      ),
                    ),
                  );
                },
                child: const Text('编辑'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('编辑'));
      await tester.pumpAndSettle();
      tester.view.viewInsets = const FakeViewPadding(bottom: 260);
      await tester.pumpAndSettle();

      final closeTarget = tester.getSize(find.byTooltip('关闭'));
      expect(
        closeTarget.width,
        greaterThanOrEqualTo(AppControls.minTouchTarget),
      );
      expect(
        closeTarget.height,
        greaterThanOrEqualTo(AppControls.minTouchTarget),
      );
      expect(
        tester
            .getSemantics(find.bySemanticsLabel('关闭'))
            .getSemanticsData()
            .hasAction(SemanticsAction.tap),
        isTrue,
      );
      expect(tester.getBottomLeft(find.text('保存')).dy, lessThanOrEqualTo(308));
      expect(find.byType(BackdropFilter), findsNothing);
      expect(tester.takeException(), isNull);

      await tester.tap(find.text('保存'));
      await tester.pumpAndSettle();
      expect(result, isTrue);
      expect(find.text('编辑提醒'), findsNothing);
    } finally {
      semantics.dispose();
    }
  });
}
