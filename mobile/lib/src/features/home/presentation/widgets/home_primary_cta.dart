import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/home/domain/home_models.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_shared.dart';
import 'package:warm_sight/src/features/setup/presentation/add_camera_sheet.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';

class HomePrimaryCtaBar extends StatelessWidget {
  const HomePrimaryCtaBar({
    super.key,
    required this.cta,
    required this.showLiveCareLink,
  });

  final HomePrimaryCta cta;
  final bool showLiveCareLink;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (cta.kind != HomePrimaryCtaKind.none) ...[
          AppPrimaryButton(
            label: cta.label,
            trailing: const AppButtonGlyph(icon: Icons.arrow_forward),
            onTap: () => _handlePrimaryTap(context),
          ),
          const SizedBox(height: 10),
        ],
        if (showLiveCareLink)
          HomePressable(
            onTap: () => context.go(AppRoute.live.path),
            child: Semantics(
              button: true,
              label: '进入实时看护',
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Text(
                  '进入实时看护',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.brandDeep,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 13,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }

  void _handlePrimaryTap(BuildContext context) {
    switch (cta.kind) {
      case HomePrimaryCtaKind.connectCamera:
        showAddCameraSheet(context);
      case HomePrimaryCtaKind.pendingActions:
      case HomePrimaryCtaKind.checkDevice:
        if (cta.routePath != null) context.go(cta.routePath!);
      case HomePrimaryCtaKind.none:
        break;
    }
  }
}
