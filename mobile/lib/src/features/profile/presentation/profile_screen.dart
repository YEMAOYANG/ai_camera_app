import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/profile/application/profile_repository.dart';
import 'package:guardian_parent_app/src/features/profile/domain/profile_avatar_persona.dart';
import 'package:guardian_parent_app/src/features/profile/domain/profile_models.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_list_row.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_screen.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_state_view.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(profileSummaryProvider);
    final subscription = ref.watch(subscriptionStatusProvider);
    final account = ref.watch(accountProfileProvider);

    return AppScreen(
      title: '我的',
      fixedHeader: false,
      showHeader: false,
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.pageHorizontal,
        8,
        AppSpacing.pageHorizontal,
        AppSpacing.pageBottom,
      ),
      children: [
        summary.when(
          data: (data) => _FamilySpaceHero(
            summary: data,
            subscription: subscription.asData?.value,
            account: account.asData?.value,
          ),
          loading: () => const _FamilySpaceLoading(),
          error: (error, _) => AppStateView(
            variant: AppStateVariant.serviceUnavailable,
            title: '家庭空间暂时无法同步',
            message: error is ProfileException ? error.message : '请稍后重试。',
            primaryActionLabel: '重新加载',
            onPrimaryAction: () => ref.invalidate(profileSummaryProvider),
            compact: true,
          ),
        ),
        const SizedBox(height: 18),
        const _ProfileCategorySections(
          sections: [
            _ProfileCategorySection(
              title: '看护空间',
              rows: [
                _ProfileCategory(
                  icon: Icons.groups_outlined,
                  title: '家庭与成员',
                  subtitle: '成员邀请、孩子资料和紧急联系人',
                  path: profileFamilyHubPath,
                  tone: AppListRowTone.green,
                ),
                _ProfileCategory(
                  icon: Icons.videocam_outlined,
                  title: '设备与看护',
                  subtitle: '设备、网络、摄像头和看护授权',
                  path: profileDeviceHubPath,
                  tone: AppListRowTone.blue,
                ),
                _ProfileCategory(
                  icon: Icons.auto_awesome_outlined,
                  title: 'AI 规则与提醒',
                  subtitle: '观察规则、语音播报和通知边界',
                  path: profileRulesHubPath,
                ),
              ],
            ),
            _ProfileCategorySection(
              title: '权益与安全',
              rows: [
                _ProfileCategory(
                  icon: Icons.workspace_premium_outlined,
                  title: '订阅与套餐',
                  subtitle: '基础看护可用，会员增强长期报告',
                  path: profileSubscriptionPath,
                  tone: AppListRowTone.blue,
                ),
                _ProfileCategory(
                  icon: Icons.stars_outlined,
                  title: '积分与奖励',
                  subtitle: '积分账户、奖励中心和兑换记录',
                  path: profileTaskRewardHubPath,
                  tone: AppListRowTone.amber,
                ),
                _ProfileCategory(
                  icon: Icons.lock_outline,
                  title: '隐私与授权',
                  subtitle: '采集授权、儿童隐私和协议政策',
                  path: profilePrivacyHubPath,
                ),
                _ProfileCategory(
                  icon: Icons.manage_accounts_outlined,
                  title: '账号设置',
                  subtitle: '个人资料、账号安全和关于',
                  path: profileAccountSettingsPath,
                  tone: AppListRowTone.green,
                ),
              ],
            ),
          ],
        ),
      ],
    );
  }
}

class _FamilySpaceHero extends StatelessWidget {
  const _FamilySpaceHero({
    required this.summary,
    required this.subscription,
    required this.account,
  });

  final ProfileSummary summary;
  final SubscriptionStatus? subscription;
  final AccountProfile? account;

  @override
  Widget build(BuildContext context) {
    final child = summary.child;
    final childText = child == null
        ? '孩子资料待完善'
        : '${child.name} · ${child.displayStage}';
    final displayName = account?.displayName.isNotEmpty == true
        ? account!.displayName
        : summary.displayName.isEmpty
        ? '家长'
        : summary.displayName;
    final relationship = _relationshipLabel(
      account: account,
      summary: summary,
      displayName: displayName,
    );
    final planLabel = subscription?.planLabel.isNotEmpty == true
        ? subscription!.planLabel
        : '基础版';
    final persona = resolveGuardianAvatarPersona(
      account: account,
      summary: summary,
      relationship: relationship,
    );

    return _HeroPressable(
      onTap: () => context.push(profileAccountPath),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final compact = constraints.maxWidth < 350;
          final artWidth = compact ? 116.0 : 138.0;
          final rightReserve = compact ? 88.0 : 118.0;

          return ClipRRect(
            borderRadius: BorderRadius.circular(AppRadii.hero),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: const Color(0xFFEAF3EF),
                border: Border.all(
                  color: AppColors.brandSage.withValues(alpha: 0.12),
                ),
                gradient: const LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [Color(0xFFE7F1ED), Color(0xFFF7FAFB)],
                ),
              ),
              child: Stack(
                children: [
                  Positioned.fill(
                    child: Opacity(
                      opacity: 0.18,
                      child: Image.asset(
                        'assets/images/guardian/guardian_family.png',
                        fit: BoxFit.cover,
                        alignment: Alignment.centerRight,
                      ),
                    ),
                  ),
                  Positioned.fill(
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.centerLeft,
                          end: Alignment.centerRight,
                          colors: [
                            const Color(0xFFF6FAF8).withValues(alpha: 0.96),
                            const Color(0xFFF6FAF8).withValues(alpha: 0.74),
                            const Color(0xFFF6FAF8).withValues(alpha: 0.36),
                          ],
                        ),
                      ),
                    ),
                  ),
                  Positioned(
                    right: compact ? -22 : -10,
                    bottom: compact ? -2 : -1,
                    child: _GuardianCharacterArt(
                      persona: persona,
                      width: artWidth,
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 15, 16, 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Padding(
                          padding: EdgeInsets.only(right: rightReserve),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Flexible(
                                    child: Text(
                                      summary.spaceTitle,
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(
                                        color: AppColors.ink,
                                        fontFamily: AppTypography.systemFont,
                                        fontSize: 24,
                                        fontWeight: FontWeight.w900,
                                        height: 1.05,
                                        letterSpacing: 0,
                                      ),
                                    ),
                                  ),
                                  const SizedBox(width: 6),
                                  const Icon(
                                    Icons.chevron_right,
                                    color: AppColors.muted,
                                    size: 18,
                                  ),
                                ],
                              ),
                              const SizedBox(height: 5),
                              Text(
                                '$relationship · ${_phoneMask(summary.phone)}',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  color: AppColors.muted,
                                  fontFamily: AppTypography.systemFont,
                                  fontSize: 13,
                                  fontWeight: FontWeight.w800,
                                  height: 1.2,
                                  letterSpacing: 0,
                                ),
                              ),
                              const SizedBox(height: 7),
                              Wrap(
                                spacing: 7,
                                runSpacing: 7,
                                children: [
                                  StatusChip(
                                    label: relationship,
                                    tone: StatusTone.success,
                                  ),
                                  StatusChip(
                                    label: planLabel,
                                    tone: StatusTone.neutral,
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                        SizedBox(height: compact ? 24 : 30),
                        Padding(
                          padding: EdgeInsets.only(right: rightReserve * 0.45),
                          child: _ChildProfileEntry(childText: childText),
                        ),
                        const SizedBox(height: 10),
                        _FamilySignalStrip(
                          signals: [
                            _FamilySignal(
                              icon: Icons.group_outlined,
                              label: '家庭成员',
                              value: '${summary.memberCount}',
                            ),
                            _FamilySignal(
                              icon: Icons.sensors_outlined,
                              label: '已绑定设备',
                              value: '${summary.deviceCount}',
                            ),
                            _FamilySignal(
                              icon: Icons.pending_actions_outlined,
                              label: '待处理',
                              value: '${summary.pendingItemCount}',
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

class _HeroPressable extends StatefulWidget {
  const _HeroPressable({required this.child, required this.onTap});

  final Widget child;
  final VoidCallback onTap;

  @override
  State<_HeroPressable> createState() => _HeroPressableState();
}

class _HeroPressableState extends State<_HeroPressable> {
  var _pressed = false;

  @override
  Widget build(BuildContext context) {
    final scale = MediaQuery.of(context).disableAnimations
        ? 1.0
        : (_pressed ? AppMotion.buttonPressScale : 1.0);

    return Semantics(
      button: true,
      label: '编辑个人信息',
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: widget.onTap,
        onTapDown: (_) => setState(() => _pressed = true),
        onTapCancel: () => setState(() => _pressed = false),
        onTapUp: (_) => setState(() => _pressed = false),
        child: AnimatedScale(
          scale: scale,
          duration: AppMotion.duration(context, 150),
          curve: Curves.easeOutCubic,
          child: widget.child,
        ),
      ),
    );
  }
}

class _ChildProfileEntry extends StatelessWidget {
  const _ChildProfileEntry({required this.childText});

  final String childText;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => context.push(profileChildPath),
      child: Semantics(
        button: true,
        label: '查看孩子资料',
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.78),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: AppColors.ink.withValues(alpha: 0.045)),
          ),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(9, 7, 8, 7),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(
                  Icons.child_care_outlined,
                  color: AppColors.brandSage,
                  size: 16,
                ),
                const SizedBox(width: 7),
                Flexible(
                  child: Text(
                    childText,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.ink,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12.2,
                      fontWeight: FontWeight.w900,
                      letterSpacing: 0,
                    ),
                  ),
                ),
                const SizedBox(width: 5),
                const Icon(
                  Icons.chevron_right,
                  color: AppColors.muted,
                  size: 16,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _GuardianCharacterArt extends StatelessWidget {
  const _GuardianCharacterArt({required this.persona, required this.width});

  final GuardianAvatarPersona persona;
  final double width;

  @override
  Widget build(BuildContext context) {
    final image = Image.asset(
      persona.assetPath,
      key: ValueKey('guardianPersona:${persona.id}'),
      width: width,
      fit: BoxFit.contain,
      filterQuality: FilterQuality.medium,
      excludeFromSemantics: true,
    );

    return Semantics(
      image: true,
      label: persona.semanticLabel,
      child: MediaQuery.of(context).disableAnimations
          ? image
          : TweenAnimationBuilder<double>(
              tween: Tween(begin: 0.965, end: 1),
              duration: AppMotion.duration(context, 360),
              curve: Curves.easeOutCubic,
              builder: (context, value, child) {
                return Transform.translate(
                  offset: Offset(0, (1 - value) * 18),
                  child: Transform.scale(scale: value, child: child),
                );
              },
              child: image,
            ),
    );
  }
}

class _FamilySpaceLoading extends StatelessWidget {
  const _FamilySpaceLoading();

  @override
  Widget build(BuildContext context) {
    return const AppLoadingState(title: '正在同步家庭空间', message: '请稍候。');
  }
}

class _ProfileCategorySections extends StatelessWidget {
  const _ProfileCategorySections({required this.sections});

  final List<_ProfileCategorySection> sections;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var index = 0; index < sections.length; index++) ...[
          _ProfileCategoryPanel(section: sections[index]),
          if (index != sections.length - 1) const SizedBox(height: 14),
        ],
      ],
    );
  }
}

class _ProfileCategorySection {
  const _ProfileCategorySection({required this.title, required this.rows});

  final String title;
  final List<_ProfileCategory> rows;
}

class _ProfileCategory {
  const _ProfileCategory({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.path,
    this.tone = AppListRowTone.neutral,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final String path;
  final AppListRowTone tone;
}

class _ProfileCategoryPanel extends StatelessWidget {
  const _ProfileCategoryPanel({required this.section});

  final _ProfileCategorySection section;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 2, bottom: 9),
          child: Text(
            section.title,
            style: const TextStyle(
              color: AppColors.ink,
              fontFamily: AppTypography.systemFont,
              fontSize: 16,
              fontWeight: FontWeight.w900,
              height: 1.2,
              letterSpacing: 0,
            ),
          ),
        ),
        DecoratedBox(
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.76),
            borderRadius: BorderRadius.circular(AppRadii.cardLarge),
            border: Border.all(color: AppColors.borderSoft),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Column(
              children: [
                for (var index = 0; index < section.rows.length; index++)
                  _ProfileCategoryRow(
                    category: section.rows[index],
                    emphasized: index == 0,
                    last: index == section.rows.length - 1,
                  ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _ProfileCategoryRow extends StatelessWidget {
  const _ProfileCategoryRow({
    required this.category,
    required this.emphasized,
    required this.last,
  });

  final _ProfileCategory category;
  final bool emphasized;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final tone = _toneData(category.tone);
    final vertical = emphasized ? 14.0 : 12.0;
    final iconSize = emphasized ? 46.0 : 40.0;

    return _CategoryPressable(
      onTap: () => context.push(category.path),
      label: category.title,
      child: Column(
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(14, vertical, 12, vertical),
            child: Row(
              children: [
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: tone.background,
                    borderRadius: BorderRadius.circular(emphasized ? 16 : 14),
                  ),
                  child: SizedBox(
                    width: iconSize,
                    height: iconSize,
                    child: Center(
                      child: Icon(
                        category.icon,
                        color: tone.foreground,
                        size: 21,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        category.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: AppColors.ink,
                          fontFamily: AppTypography.systemFont,
                          fontSize: emphasized ? 15.5 : 14.5,
                          fontWeight: FontWeight.w900,
                          height: 1.18,
                          letterSpacing: 0,
                        ),
                      ),
                      const SizedBox(height: 5),
                      Text(
                        category.subtitle,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: AppColors.muted,
                          fontFamily: AppTypography.systemFont,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          height: 1.36,
                          letterSpacing: 0,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 10),
                const Icon(
                  Icons.chevron_right,
                  color: AppColors.subtle,
                  size: 19,
                ),
              ],
            ),
          ),
          if (!last)
            Padding(
              padding: EdgeInsets.only(left: 14 + iconSize + 12, right: 12),
              child: Divider(
                height: 1,
                thickness: 1,
                color: AppColors.borderSoft.withValues(alpha: 0.72),
              ),
            ),
        ],
      ),
    );
  }
}

class _CategoryPressable extends StatefulWidget {
  const _CategoryPressable({
    required this.child,
    required this.onTap,
    required this.label,
  });

  final Widget child;
  final VoidCallback onTap;
  final String label;

  @override
  State<_CategoryPressable> createState() => _CategoryPressableState();
}

class _CategoryPressableState extends State<_CategoryPressable> {
  var _pressed = false;

  @override
  Widget build(BuildContext context) {
    final offset = MediaQuery.of(context).disableAnimations || !_pressed
        ? Offset.zero
        : const Offset(0, 1);

    return Semantics(
      button: true,
      label: widget.label,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: widget.onTap,
        onTapDown: (_) => setState(() => _pressed = true),
        onTapCancel: () => setState(() => _pressed = false),
        onTapUp: (_) => setState(() => _pressed = false),
        child: AnimatedSlide(
          offset: offset,
          duration: AppMotion.duration(context, 140),
          curve: Curves.easeOutCubic,
          child: widget.child,
        ),
      ),
    );
  }
}

class _FamilySignalStrip extends StatelessWidget {
  const _FamilySignalStrip({required this.signals});

  final List<_FamilySignal> signals;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth < 350;
        if (compact) {
          return Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final signal in signals) _FamilySignalItem(signal: signal),
            ],
          );
        }
        return Row(
          children: [
            for (var index = 0; index < signals.length; index++) ...[
              Expanded(child: _FamilySignalItem(signal: signals[index])),
              if (index != signals.length - 1) const SizedBox(width: 8),
            ],
          ],
        );
      },
    );
  }
}

class _FamilySignal {
  const _FamilySignal({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;
}

class _FamilySignalItem extends StatelessWidget {
  const _FamilySignalItem({required this.signal});

  final _FamilySignal signal;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(13),
        border: Border.all(color: AppColors.ink.withValues(alpha: 0.045)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 7),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(signal.icon, color: AppColors.brandSage, size: 15),
            const SizedBox(width: 5),
            Text(
              signal.value,
              style: const TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 13.5,
                fontWeight: FontWeight.w900,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(width: 4),
            Flexible(
              child: Text(
                signal.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ToneData {
  const _ToneData({required this.foreground, required this.background});

  final Color foreground;
  final Color background;
}

_ToneData _toneData(AppListRowTone tone) {
  return switch (tone) {
    AppListRowTone.blue => _ToneData(
      foreground: AppColors.brand,
      background: AppColors.brand.withValues(alpha: 0.10),
    ),
    AppListRowTone.green => _ToneData(
      foreground: AppColors.success,
      background: AppColors.success.withValues(alpha: 0.10),
    ),
    AppListRowTone.amber => _ToneData(
      foreground: AppColors.warning,
      background: AppColors.warning.withValues(alpha: 0.12),
    ),
    AppListRowTone.red => _ToneData(
      foreground: AppColors.danger,
      background: AppColors.danger.withValues(alpha: 0.10),
    ),
    AppListRowTone.neutral => _ToneData(
      foreground: AppColors.ink,
      background: AppColors.ink.withValues(alpha: 0.06),
    ),
  };
}

String _relationshipLabel({
  required AccountProfile? account,
  required ProfileSummary summary,
  required String displayName,
}) {
  final relationship = account?.relationship.trim() ?? '';
  if (relationship.isNotEmpty) return relationship;
  final roleLabel = summary.roleLabel.trim();
  if (roleLabel.isNotEmpty) return roleLabel;
  if (displayName.trim().isNotEmpty) return displayName.trim();
  return '监护人';
}

String _phoneMask(String phone) {
  if (phone.length < 7) return phone.isEmpty ? '手机号待同步' : phone;
  return '${phone.substring(0, 3)} **** ${phone.substring(phone.length - 4)}';
}
