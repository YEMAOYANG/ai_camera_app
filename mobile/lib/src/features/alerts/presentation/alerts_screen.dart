import 'package:flutter/material.dart';
import 'package:warm_sight/src/shared/widgets/app_screen.dart';
import 'package:warm_sight/src/shared/widgets/app_state_view.dart';

class AlertsScreen extends StatelessWidget {
  const AlertsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const AppScreen(
      title: '告警',
      subtitle: '安全提醒能力会在后续版本开启',
      children: [
        AppStateView(
          variant: AppStateVariant.noData,
          title: '暂时没有告警能力',
          message: '当前版本不展示告警记录。后续开启安全提醒后，这里会显示需要家长关注的事项。',
          compact: true,
        ),
      ],
    );
  }
}
