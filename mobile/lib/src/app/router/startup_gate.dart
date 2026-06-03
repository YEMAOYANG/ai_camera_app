import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mira_guardian_app/src/app/router/app_route.dart';
import 'package:mira_guardian_app/src/core/storage/auth_session_store.dart';
import 'package:mira_guardian_app/src/core/storage/onboarding_store.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';
import 'package:mira_guardian_app/src/features/setup/application/setup_repository.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_button.dart';

class StartupGate extends ConsumerStatefulWidget {
  const StartupGate({super.key});

  @override
  ConsumerState<StartupGate> createState() => _StartupGateState();
}

class _StartupGateState extends ConsumerState<StartupGate> {
  String? _errorText;
  var _checking = true;

  @override
  void initState() {
    super.initState();
    Future<void>.microtask(_resolve);
  }

  Future<void> _resolve() async {
    setState(() {
      _checking = true;
      _errorText = null;
    });

    final onboardingStore = ref.read(onboardingStoreProvider);
    if (!onboardingStore.hasSeenOnboarding) {
      if (mounted) context.go(welcomePath);
      return;
    }

    final sessionStore = ref.read(authSessionStoreProvider);
    if (!sessionStore.hasUsableSession) {
      if (mounted) context.go(loginPath);
      return;
    }

    try {
      final setupStatus = await ref.read(setupRepositoryProvider).status();
      if (!mounted) return;
      context.go(setupStatus.routePath);
    } on SetupException catch (error) {
      if (!mounted) return;
      setState(() {
        _checking = false;
        _errorText = error.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.appBackgroundWarm,
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(28),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: AppColors.ink,
                    borderRadius: BorderRadius.circular(18),
                  ),
                  child: const SizedBox(
                    width: 48,
                    height: 48,
                    child: Center(
                      child: Icon(
                        Icons.center_focus_strong_outlined,
                        color: Colors.white,
                        size: 22,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 18),
                Text(
                  _checking ? '正在确认登录状态' : '后端连接异常',
                  style: const TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 22,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  _errorText ?? '正在同步家庭账户和首次设置进度。',
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    height: 1.55,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 20),
                if (_checking)
                  const SizedBox(
                    width: 26,
                    height: 26,
                    child: CircularProgressIndicator(strokeWidth: 3),
                  )
                else
                  MiraPrimaryButton(
                    label: '重试',
                    trailing: const MiraButtonGlyph(icon: Icons.refresh),
                    onTap: _resolve,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
