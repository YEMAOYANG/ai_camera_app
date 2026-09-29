import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';

const captureParentTextbooks = bool.fromEnvironment('MIRA_TEXTBOOK_VISUAL_QA');
const parentTextbookPreviewKey = ValueKey('parentTextbookPreview');

Future<void> loadParentTextbookPreviewFont() async {
  if (!captureParentTextbooks) return;
  final bytes = await File(
    'test/assets/fonts/NotoSansCJKsc-Regular.otf',
  ).readAsBytes();
  await (FontLoader(
    AppTypography.systemFont,
  )..addFont(Future.value(ByteData.sublistView(bytes)))).load();
  await (FontLoader(
    'Roboto',
  )..addFont(Future.value(ByteData.sublistView(bytes)))).load();
  final sdk = Platform.environment['FLUTTER_ROOT'];
  if (sdk != null) {
    final icons = await File(
      '$sdk/bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf',
    ).readAsBytes();
    await (FontLoader(
      'MaterialIcons',
    )..addFont(Future.value(ByteData.sublistView(icons)))).load();
  }
}

Future<void> captureParentTextbookPreview(
  WidgetTester tester,
  String name,
) async {
  if (!captureParentTextbooks) return;
  await tester.pumpAndSettle();
  final boundary = tester.renderObject<RenderRepaintBoundary>(
    find.byKey(parentTextbookPreviewKey),
  );
  await tester.runAsync(() async {
    final image = await boundary.toImage(pixelRatio: 2);
    final data = await image.toByteData(format: ui.ImageByteFormat.png);
    final bytes = data!.buffer.asUint8List();
    final directory = Directory(
      const String.fromEnvironment(
        'MIRA_TEXTBOOK_VISUAL_OUTPUT',
        defaultValue: '../output/parent-profile-redesign-20260928',
      ),
    );
    await directory.create(recursive: true);
    await File('${directory.path}/$name.png').writeAsBytes(bytes);
    image.dispose();
  });
}
