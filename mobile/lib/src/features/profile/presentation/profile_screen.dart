import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/profile/application/profile_repository.dart';
import 'package:guardian_parent_app/src/features/profile/domain/profile_models.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_list_row.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_screen.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_state_view.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_surface.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(profileSummaryProvider);
    final subscription = ref.watch(subscriptionStatusProvider);

    return AppScreen(
      title: '我的',
      fixedHeader: false,
      showHeader: false,
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 28),
      children: [
        summary.when(
          data: (data) => _FamilySpaceCard(
            summary: data,
            subscription: subscription.asData?.value,
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
        const SizedBox(height: 12),
        _SubscriptionEntry(subscription: subscription),
        const SizedBox(height: 14),
        const _ProfileCategorySections(
          sections: [
            _ProfileCategorySection(
              title: '家庭管理',
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
                  subtitle: '设备、网络、摄像头和声音能力',
                  path: profileDeviceHubPath,
                  tone: AppListRowTone.blue,
                ),
                _ProfileCategory(
                  icon: Icons.auto_awesome_outlined,
                  title: 'AI 规则与提醒',
                  subtitle: '观察规则、语音播报和通知设置',
                  path: profileRulesHubPath,
                ),
              ],
            ),
            _ProfileCategorySection(
              title: '账户与权益',
              rows: [
                _ProfileCategory(
                  icon: Icons.stars_outlined,
                  title: '任务与奖励',
                  subtitle: '积分账户、奖励中心和兑换记录',
                  path: profileTaskRewardHubPath,
                  tone: AppListRowTone.amber,
                ),
                _ProfileCategory(
                  icon: Icons.verified_user_outlined,
                  title: '账号安全',
                  subtitle: '手机号、登录方式和登录设备',
                  path: profileSecurityPath,
                  tone: AppListRowTone.green,
                ),
                _ProfileCategory(
                  icon: Icons.lock_outline,
                  title: '隐私与授权',
                  subtitle: '采集授权、儿童隐私和协议政策',
                  path: profilePrivacyHubPath,
                ),
                _ProfileCategory(
                  icon: Icons.info_outline,
                  title: '关于',
                  subtitle: '帮助反馈、当前版本和协议政策',
                  path: profileAboutPath,
                ),
              ],
            ),
          ],
        ),
      ],
    );
  }
}

class _FamilySpaceCard extends StatelessWidget {
  const _FamilySpaceCard({required this.summary, required this.subscription});

  final ProfileSummary summary;
  final SubscriptionStatus? subscription;

  @override
  Widget build(BuildContext context) {
    final child = summary.child;
    final childText = child == null
        ? '孩子资料待完善'
        : '${child.name} · ${child.displayStage}';
    final displayName = summary.displayName.isEmpty
        ? '家长'
        : summary.displayName;

    final planLabel = subscription?.planLabel.isNotEmpty == true
        ? subscription!.planLabel
        : '基础版';

    return AppSurface(
      color: AppColors.ink,
      borderColor: AppColors.ink,
      radius: 24,
      onTap: () => context.push(profileAccountPath),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              DecoratedBox(
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.10),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const SizedBox(
                  width: 48,
                  height: 48,
                  child: Center(
                    child: Icon(
                      Icons.home_outlined,
                      color: Colors.white,
                      size: 24,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(summary.spaceTitle, style: _darkTitle),
                    const SizedBox(height: 5),
                    Text(
                      '$displayName · ${_phoneMask(summary.phone)}',
                      style: _darkSub,
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  StatusChip(label: planLabel, tone: StatusTone.neutral),
                  const SizedBox(height: 7),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        '编辑资料',
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.64),
                          fontFamily: AppTypography.systemFont,
                          fontSize: 11,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 0,
                        ),
                      ),
                      const SizedBox(width: 3),
                      Icon(
                        Icons.chevron_right,
                        color: Colors.white.withValues(alpha: 0.56),
                        size: 14,
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(childText, style: _darkSub),
          const SizedBox(height: 16),
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
    );
  }
}

class _SubscriptionEntry extends StatelessWidget {
  const _SubscriptionEntry({required this.subscription});

  final AsyncValue<SubscriptionStatus> subscription;

  @override
  Widget build(BuildContext context) {
    final data = subscription.asData?.value;
    final title = data?.planLabel.isNotEmpty == true ? data!.planLabel : '基础版';
    final subtitle = data?.renewalText.isNotEmpty == true
        ? data!.renewalText
        : '基础看护、任务提醒和隐私控制保持可用';
    final status = data?.statusLabel.isNotEmpty == true
        ? data!.statusLabel
        : '已启用';

    return AppSurface(
      radius: 18,
      padding: const EdgeInsets.fromLTRB(15, 14, 13, 14),
      onTap: () => context.push(profileSubscriptionPath),
      child: Row(
        children: [
          DecoratedBox(
            decoration: BoxDecoration(
              color: AppColors.brand.withValues(alpha: 0.10),
              borderRadius: BorderRadius.circular(14),
            ),
            child: const SizedBox(
              width: 42,
              height: 42,
              child: Center(
                child: Icon(
                  Icons.workspace_premium_outlined,
                  color: AppColors.brand,
                  size: 20,
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('订阅与套餐', style: _subscriptionTitleStyle),
                const SizedBox(height: 4),
                Text('$title · $subtitle', style: _subscriptionSubtitleStyle),
              ],
            ),
          ),
          const SizedBox(width: 10),
          StatusChip(label: status, tone: StatusTone.neutral),
        ],
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
      children: [
        for (
          var sectionIndex = 0;
          sectionIndex < sections.length;
          sectionIndex++
        )
          Padding(
            padding: EdgeInsets.only(
              bottom: sectionIndex == sections.length - 1 ? 0 : 12,
            ),
            child: _ProfileCategorySectionCard(section: sections[sectionIndex]),
          ),
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

class _ProfileCategorySectionCard extends StatelessWidget {
  const _ProfileCategorySectionCard({required this.section});

  final _ProfileCategorySection section;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      radius: 22,
      padding: const EdgeInsets.fromLTRB(16, 14, 12, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            section.title,
            style: const TextStyle(
              color: AppColors.ink,
              fontFamily: AppTypography.systemFont,
              fontSize: 15.5,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 7),
          for (var index = 0; index < section.rows.length; index++) ...[
            _ProfileCategoryRow(category: section.rows[index]),
            if (index != section.rows.length - 1)
              const Divider(
                height: 1,
                thickness: 1,
                indent: 50,
                color: AppColors.borderSoft,
              ),
          ],
        ],
      ),
    );
  }
}

class _ProfileCategoryRow extends StatelessWidget {
  const _ProfileCategoryRow({required this.category});

  final _ProfileCategory category;

  @override
  Widget build(BuildContext context) {
    final color = switch (category.tone) {
      AppListRowTone.blue => AppColors.brand,
      AppListRowTone.green => AppColors.success,
      AppListRowTone.amber => AppColors.warning,
      AppListRowTone.red => AppColors.danger,
      AppListRowTone.neutral => AppColors.ink,
    };
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => context.push(category.path),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 11),
        child: Row(
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(13),
              ),
              child: SizedBox(
                width: 38,
                height: 38,
                child: Center(
                  child: Icon(category.icon, color: color, size: 19),
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
                    style: const TextStyle(
                      color: AppColors.ink,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 14.5,
                      fontWeight: FontWeight.w800,
                      height: 1.25,
                      letterSpacing: 0,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    category.subtitle,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      height: 1.4,
                      letterSpacing: 0,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            const Icon(Icons.chevron_right, color: AppColors.subtle, size: 18),
          ],
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
    return Wrap(
      spacing: 13,
      runSpacing: 10,
      children: [
        for (final signal in signals) _FamilySignalItem(signal: signal),
      ],
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
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          signal.icon,
          color: Colors.white.withValues(alpha: 0.72),
          size: 17,
        ),
        const SizedBox(width: 6),
        Text(
          signal.value,
          style: const TextStyle(
            color: Colors.white,
            fontFamily: AppTypography.systemFont,
            fontSize: 15,
            fontWeight: FontWeight.w900,
            letterSpacing: 0,
          ),
        ),
        const SizedBox(width: 4),
        Text(
          signal.label,
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.62),
            fontFamily: AppTypography.systemFont,
            fontSize: 11,
            fontWeight: FontWeight.w700,
            letterSpacing: 0,
          ),
        ),
      ],
    );
  }
}

String _phoneMask(String phone) {
  if (phone.length < 7) return phone.isEmpty ? '手机号待同步' : phone;
  return '${phone.substring(0, 3)} **** ${phone.substring(phone.length - 4)}';
}

const _darkTitle = TextStyle(
  color: Colors.white,
  fontFamily: AppTypography.systemFont,
  fontSize: 18,
  fontWeight: FontWeight.w800,
  letterSpacing: 0,
);

final _darkSub = TextStyle(
  color: Colors.white.withValues(alpha: 0.66),
  fontFamily: AppTypography.systemFont,
  fontSize: 12,
  fontWeight: FontWeight.w700,
  height: 1.45,
  letterSpacing: 0,
);

const _subscriptionTitleStyle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 14.5,
  fontWeight: FontWeight.w900,
  height: 1.2,
  letterSpacing: 0,
);

const _subscriptionSubtitleStyle = TextStyle(
  color: AppColors.muted,
  fontFamily: AppTypography.systemFont,
  fontSize: 12,
  fontWeight: FontWeight.w600,
  height: 1.36,
  letterSpacing: 0,
);
