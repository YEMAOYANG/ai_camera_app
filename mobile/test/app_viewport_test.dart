import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/shared/widgets/app_bottom_sheet.dart';
import 'package:warm_sight/src/shared/widgets/app_viewport.dart';

void main() {
  testWidgets('a sheet and its draft stay open clear of the fold', (
    tester,
  ) async {
    final geometry = StreamController<Object?>();
    addTearDown(geometry.close);
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(951, 669);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);

    const form = ValueKey('form');
    const save = ValueKey('save');
    await tester.pumpWidget(
      MaterialApp(
        builder: (context, child) =>
            AppViewport(geometryEvents: geometry.stream, child: child!),
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () => showAppBottomSheet<void>(
                context: context,
                child: AppBottomSheetBody(
                  title: '编辑任务',
                  footer: TextButton(
                    key: save,
                    onPressed: () {},
                    child: const Text('保存'),
                  ),
                  child: const TextField(key: form),
                ),
              ),
              child: const Text('打开任务'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('打开任务'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(form), '睡前阅读');

    geometry.add({
      'width': 951,
      'height': 669,
      'barEdge': 'right',
      'foldable': true,
      'divisions': [
        [455, 0, 40, 669],
      ],
    });
    await tester.pumpAndSettle();
    expect(tester.getRect(find.byKey(form)).left, greaterThanOrEqualTo(495));
    expect(find.text('睡前阅读'), findsOneWidget);

    // Tabletop pose: let the sheet scroll within the top pane.
    geometry.add({
      'width': 951,
      'height': 669,
      'barEdge': 'right',
      'foldable': true,
      'divisions': [
        [0, 315, 951, 40],
      ],
    });
    await tester.pumpAndSettle();
    expect(tester.getRect(find.byKey(save)).bottom, lessThanOrEqualTo(315));
    expect(find.text('睡前阅读'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
