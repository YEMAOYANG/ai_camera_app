import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/features/home/domain/home_models.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_habit_hero.dart';
import 'package:warm_sight/src/shared/widgets/status_chip.dart';

void main() {
  testWidgets('home hero fits compact Android height with long observation', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: MediaQuery(
          data: MediaQueryData(
            size: Size(360, 640),
            padding: EdgeInsets.only(top: 44),
          ),
          child: Scaffold(
            body: SizedBox(
              width: 360,
              height: 190,
              child: HomeHabitHero(
                safeTop: 44,
                scrollOffset: 0,
                isLoading: false,
                panelOverlap: 58,
                focus: HabitFocusCopy(
                  headerTime: '今天中午',
                  headerTitle: '小爱现在',
                  title: '孩子正在玩手机',
                  detail: '孩子在看屏幕，注意用眼距离。',
                  chips: [
                    HomeChipSpec(
                      kind: HomeChipKind.device,
                      label: '设备在线',
                      tone: StatusTone.success,
                    ),
                    HomeChipSpec(
                      kind: HomeChipKind.stage,
                      label: '幼儿园 · 中班',
                      tone: StatusTone.neutral,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );

    expect(tester.takeException(), isNull);
    expect(find.text('孩子正在玩手机'), findsOneWidget);
  });

  testWidgets('home hero keeps a 48px student QR entry discoverable', (
    tester,
  ) async {
    var tapped = false;
    await tester.pumpWidget(
      MaterialApp(
        home: MediaQuery(
          data: const MediaQueryData(size: Size(390, 844)),
          child: Scaffold(
            body: SizedBox(
              width: 390,
              height: 360,
              child: Align(
                alignment: Alignment.topRight,
                child: HomeStudentQrButton(onTap: () => tapped = true),
              ),
            ),
          ),
        ),
      ),
    );

    final entry = find.byKey(const ValueKey('homeStudentQrScanButton'));
    expect(entry, findsOneWidget);
    expect(tester.getSize(entry), const Size(48, 48));
    await tester.tap(entry);
    expect(tapped, isTrue);
  });
}
