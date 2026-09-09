import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/learning/application/learning_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_models.dart';
import 'package:warm_sight/src/features/student_access/application/student_access_repository.dart';
import 'package:warm_sight/src/features/student_access/domain/student_access_models.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import 'package:warm_sight/src/shared/widgets/app_surface.dart';
import 'package:warm_sight/src/shared/widgets/app_text_field.dart';
import 'package:warm_sight/src/shared/widgets/app_toast.dart';

class StudentAccessManagementPanel extends ConsumerStatefulWidget {
  const StudentAccessManagementPanel({required this.childId, super.key});

  final String childId;

  @override
  ConsumerState<StudentAccessManagementPanel> createState() =>
      _StudentAccessManagementPanelState();
}

class _StudentAccessManagementPanelState
    extends ConsumerState<StudentAccessManagementPanel> {
  var _opened = false;
  var _loading = false;
  var _loadingMore = false;
  var _pinResetting = false;
  var _loadGeneration = 0;
  String? _error;
  String? _actionError;
  String? _revokingId;
  String? _nextCursor;
  List<StudentAuthorization> _authorizations = const [];
  List<LearningReport> _reports = const [];
  StudentPinResetResult? _pinResetResult;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _ManagementEntry(opened: _opened, onTap: _toggleOpen),
        if (_opened) ...[
          const SizedBox(height: 12),
          if (_loading)
            const _ManagementLoading()
          else if (_error != null)
            _ManagementError(message: _error!, onRetry: _load)
          else
            _ManagementContent(
              authorizations: _authorizations,
              reports: _reports,
              nextCursor: _nextCursor,
              actionError: _actionError,
              pinResetResult: _pinResetResult,
              revokingId: _revokingId,
              pinResetting: _pinResetting,
              loadingMore: _loadingMore,
              onRevoke: _confirmRevoke,
              onResetPin: _showPinReset,
              onReport: _showReportDetail,
              onLoadMore: _loadMore,
            ),
        ],
      ],
    );
  }

  void _toggleOpen() {
    setState(() => _opened = !_opened);
    if (_opened && !_loading && _authorizations.isEmpty && _reports.isEmpty) {
      unawaited(_load());
    }
  }

  Future<void> _load() async {
    final generation = ++_loadGeneration;
    setState(() {
      _loading = true;
      _error = null;
      _actionError = null;
    });
    try {
      final results = await Future.wait<Object>([
        ref
            .read(studentAccessRepositoryProvider)
            .listAuthorizations(widget.childId),
        ref
            .read(parentLearningReportsRepositoryProvider)
            .reports(childId: widget.childId),
      ]);
      if (!mounted || generation != _loadGeneration) return;
      final authorizationList = results[0] as StudentAuthorizationList;
      final reportPage = results[1] as LearningReportPage;
      setState(() {
        _authorizations = authorizationList.items;
        _reports = reportPage.items;
        _nextCursor = reportPage.nextCursor;
        _loading = false;
      });
    } catch (error) {
      if (!mounted || generation != _loadGeneration) return;
      setState(() {
        _loading = false;
        _error = _messageFor(error);
      });
    }
  }

  Future<void> _loadMore() async {
    final cursor = _nextCursor;
    if (cursor == null || _loadingMore) return;
    setState(() {
      _loadingMore = true;
      _actionError = null;
    });
    try {
      final page = await ref
          .read(parentLearningReportsRepositoryProvider)
          .reports(childId: widget.childId, cursor: cursor);
      if (!mounted) return;
      setState(() {
        final known = _reports.map((item) => item.id).toSet();
        _reports = [
          ..._reports,
          ...page.items.where((item) => known.add(item.id)),
        ];
        _nextCursor = page.nextCursor;
        _loadingMore = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loadingMore = false;
        _actionError = _messageFor(error);
      });
    }
  }

  Future<void> _confirmRevoke(StudentAuthorization authorization) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('撤销这台设备的学习授权？'),
        content: Text('“${authorization.displayName}”会立即退出学习空间，之后需要家长重新授权。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('取消'),
          ),
          FilledButton(
            key: const ValueKey('confirmRevokeStudentAuthorization'),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            style: FilledButton.styleFrom(backgroundColor: AppColors.danger),
            child: const Text('确认撤销'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() {
      _revokingId = authorization.id;
      _actionError = null;
    });
    try {
      await ref
          .read(studentAccessRepositoryProvider)
          .revokeAuthorization(
            childId: widget.childId,
            authorizationId: authorization.id,
          );
      if (!mounted) return;
      setState(() {
        _authorizations = _authorizations
            .where((item) => item.id != authorization.id)
            .toList(growable: false);
        _revokingId = null;
      });
      showAppToast(context, '设备授权已撤销', tone: AppToastTone.success);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _revokingId = null;
        _actionError = _messageFor(error);
      });
    }
  }

  Future<void> _showPinReset() async {
    var pinValue = '';
    var confirmationValue = '';
    final pin = await showDialog<String>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) {
          final ready = pinValue.length == 4 && confirmationValue == pinValue;
          return AlertDialog(
            title: const Text('重置 4 位学习 PIN'),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    '重置后，旧 PIN 立即失效，现有学习会话会退出；已授权设备仍保留，下次需用新 PIN 解锁。服务端不会回显 PIN。',
                    style: TextStyle(height: 1.45),
                  ),
                  const SizedBox(height: 14),
                  AppTextField(
                    key: const ValueKey('studentPinResetField'),
                    label: '新的学习 PIN',
                    icon: Icons.lock_reset_outlined,
                    value: '',
                    keyboardType: TextInputType.number,
                    inputFormatters: [
                      FilteringTextInputFormatter.digitsOnly,
                      LengthLimitingTextInputFormatter(4),
                    ],
                    obscureText: true,
                    onChanged: (value) =>
                        setDialogState(() => pinValue = value),
                  ),
                  const SizedBox(height: 12),
                  AppTextField(
                    key: const ValueKey('studentPinResetConfirmField'),
                    label: '再次输入',
                    icon: Icons.verified_user_outlined,
                    value: '',
                    keyboardType: TextInputType.number,
                    inputFormatters: [
                      FilteringTextInputFormatter.digitsOnly,
                      LengthLimitingTextInputFormatter(4),
                    ],
                    obscureText: true,
                    onChanged: (value) =>
                        setDialogState(() => confirmationValue = value),
                    errorText: confirmationValue.length == 4 && !ready
                        ? '两次输入的 PIN 不一致'
                        : null,
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(),
                child: const Text('取消'),
              ),
              FilledButton(
                key: const ValueKey('confirmStudentPinReset'),
                onPressed: ready
                    ? () => Navigator.of(dialogContext).pop(pinValue)
                    : null,
                child: const Text('确认重置'),
              ),
            ],
          );
        },
      ),
    );
    if (pin == null || !mounted) return;
    setState(() {
      _pinResetting = true;
      _actionError = null;
      _pinResetResult = null;
    });
    try {
      final result = await ref
          .read(studentAccessRepositoryProvider)
          .resetPin(childId: widget.childId, pin: pin);
      if (!mounted) return;
      setState(() {
        _pinResetResult = result;
        _pinResetting = false;
      });
      showAppToast(context, '学习 PIN 已更新', tone: AppToastTone.success);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _pinResetting = false;
        _actionError = _messageFor(error);
      });
    }
  }

  Future<void> _showReportDetail(LearningReport report) async {
    final future = ref
        .read(parentLearningReportsRepositoryProvider)
        .reportDetail(childId: widget.childId, reportId: report.id);
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => FutureBuilder<LearningReport>(
        future: future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const SizedBox(
              key: ValueKey('learningReportDetailLoading'),
              height: 280,
              child: Center(child: CircularProgressIndicator()),
            );
          }
          if (snapshot.hasError || snapshot.data == null) {
            return SizedBox(
              height: 280,
              child: Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    _messageFor(snapshot.error),
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
            );
          }
          return _LearningReportDetail(report: snapshot.data!);
        },
      ),
    );
  }

  static String _messageFor(Object? error) {
    if (error is StudentAccessException) return error.message;
    if (error is LearningException) return error.message;
    return '暂时无法完成操作，请检查网络后重试。';
  }
}

class _ManagementEntry extends StatelessWidget {
  const _ManagementEntry({required this.opened, required this.onTap});

  final bool opened;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      color: AppColors.surfaceTinted,
      borderColor: AppColors.borderSoft,
      radius: AppRadii.cardLarge,
      padding: const EdgeInsets.all(15),
      child: Row(
        children: [
          const Icon(Icons.devices_outlined, color: AppColors.brandDeep),
          const SizedBox(width: 12),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('设备授权与学习报告', style: _titleStyle),
                SizedBox(height: 4),
                Text('查看学生网页登录、重置 PIN 和学习结果。', style: _bodyStyle),
              ],
            ),
          ),
          IconButton(
            key: const ValueKey('openStudentAccessManagement'),
            tooltip: opened ? '收起' : '打开管理',
            onPressed: onTap,
            icon: Icon(opened ? Icons.expand_less : Icons.chevron_right),
          ),
        ],
      ),
    );
  }
}

class _ManagementLoading extends StatelessWidget {
  const _ManagementLoading();

  @override
  Widget build(BuildContext context) {
    return const AppSurface(
      key: ValueKey('studentAccessManagementLoading'),
      radius: AppRadii.cardLarge,
      padding: EdgeInsets.all(24),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(strokeWidth: 2),
            SizedBox(height: 12),
            Text('正在同步设备与学习报告', style: _bodyStyle),
          ],
        ),
      ),
    );
  }
}

class _ManagementError extends StatelessWidget {
  const _ManagementError({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      color: AppColors.dangerWash,
      borderColor: AppColors.danger.withValues(alpha: 0.12),
      radius: AppRadii.cardLarge,
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(message, style: _bodyStyle.copyWith(color: AppColors.danger)),
          const SizedBox(height: 12),
          AppSecondaryButton(
            key: const ValueKey('retryStudentAccessManagement'),
            label: '重新加载',
            onTap: onRetry,
          ),
        ],
      ),
    );
  }
}

class _ManagementContent extends StatelessWidget {
  const _ManagementContent({
    required this.authorizations,
    required this.reports,
    required this.nextCursor,
    required this.actionError,
    required this.pinResetResult,
    required this.revokingId,
    required this.pinResetting,
    required this.loadingMore,
    required this.onRevoke,
    required this.onResetPin,
    required this.onReport,
    required this.onLoadMore,
  });

  final List<StudentAuthorization> authorizations;
  final List<LearningReport> reports;
  final String? nextCursor;
  final String? actionError;
  final StudentPinResetResult? pinResetResult;
  final String? revokingId;
  final bool pinResetting;
  final bool loadingMore;
  final ValueChanged<StudentAuthorization> onRevoke;
  final VoidCallback onResetPin;
  final ValueChanged<LearningReport> onReport;
  final VoidCallback onLoadMore;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (actionError != null) ...[
          _InlineNotice(
            icon: Icons.error_outline,
            text: actionError!,
            foreground: AppColors.danger,
            background: AppColors.dangerWash,
          ),
          const SizedBox(height: 10),
        ],
        if (pinResetResult != null) ...[
          const _InlineNotice(
            key: ValueKey('studentPinResetSuccess'),
            icon: Icons.check_circle_outline,
            text: '学习 PIN 已更新。已授权设备仍受信任，现有会话已退出，下次请使用新 PIN 解锁。',
            foreground: AppColors.success,
            background: AppColors.successWash,
          ),
          const SizedBox(height: 10),
        ],
        AppSurface(
          radius: AppRadii.cardLarge,
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  const Expanded(child: Text('已授权设备', style: _titleStyle)),
                  TextButton.icon(
                    key: const ValueKey('resetStudentPin'),
                    onPressed: pinResetting ? null : onResetPin,
                    icon: const Icon(Icons.lock_reset_outlined, size: 18),
                    label: Text(pinResetting ? '正在更新' : '重置 PIN'),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              if (authorizations.isEmpty)
                const _EmptyLine(
                  icon: Icons.devices_other_outlined,
                  text: '还没有已授权设备',
                )
              else
                for (var index = 0; index < authorizations.length; index++) ...[
                  if (index > 0) const Divider(height: 22),
                  _AuthorizationRow(
                    authorization: authorizations[index],
                    revoking: revokingId == authorizations[index].id,
                    onRevoke: () => onRevoke(authorizations[index]),
                  ),
                ],
            ],
          ),
        ),
        const SizedBox(height: 12),
        AppSurface(
          radius: AppRadii.cardLarge,
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('学习报告', style: _titleStyle),
              const SizedBox(height: 10),
              if (reports.isEmpty)
                const _EmptyLine(
                  icon: Icons.assignment_outlined,
                  text: '还没有学习报告',
                )
              else
                for (var index = 0; index < reports.length; index++) ...[
                  if (index > 0) const Divider(height: 18),
                  _ReportRow(
                    report: reports[index],
                    onTap: () => onReport(reports[index]),
                  ),
                ],
              if (nextCursor != null) ...[
                const SizedBox(height: 12),
                AppSecondaryButton(
                  label: loadingMore ? '正在加载' : '加载更多报告',
                  onTap: loadingMore ? null : onLoadMore,
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _AuthorizationRow extends StatelessWidget {
  const _AuthorizationRow({
    required this.authorization,
    required this.revoking,
    required this.onRevoke,
  });

  final StudentAuthorization authorization;
  final bool revoking;
  final VoidCallback onRevoke;

  @override
  Widget build(BuildContext context) {
    final activeSessions = authorization.sessions
        .where((session) => session.status == 'active')
        .length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.computer_outlined, color: AppColors.brandDeep),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(authorization.displayName, style: _itemTitleStyle),
                  const SizedBox(height: 4),
                  Text('$activeSessions 个有效会话', style: _bodyStyle),
                  const SizedBox(height: 2),
                  Text(
                    '最近使用 ${_dateTime(authorization.lastUsedAt)}',
                    style: _bodyStyle,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '授权于 ${_date(authorization.createdAt)}',
                    style: _bodyStyle,
                  ),
                ],
              ),
            ),
            _StatusPill(
              label: authorization.isActive ? '使用中' : '已过期',
              active: authorization.isActive,
            ),
          ],
        ),
        const SizedBox(height: 10),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton.icon(
            key: ValueKey('revokeStudentAuthorization-${authorization.id}'),
            onPressed: revoking ? null : onRevoke,
            icon: const Icon(Icons.link_off_outlined, size: 18),
            label: Text(revoking ? '正在撤销' : '撤销授权'),
            style: TextButton.styleFrom(foregroundColor: AppColors.danger),
          ),
        ),
      ],
    );
  }
}

class _ReportRow extends StatelessWidget {
  const _ReportRow({required this.report, required this.onTap});

  final LearningReport report;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      key: ValueKey('learningReport-${report.id}'),
      onTap: onTap,
      borderRadius: BorderRadius.circular(AppRadii.control),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 7),
        child: Row(
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                color: AppColors.brandWash,
                borderRadius: BorderRadius.circular(AppRadii.control),
              ),
              child: const SizedBox(
                width: 42,
                height: 42,
                child: Icon(
                  Icons.analytics_outlined,
                  color: AppColors.brandDeep,
                ),
              ),
            ),
            const SizedBox(width: 11),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    report.courseTitle.isEmpty
                        ? report.subject
                        : report.courseTitle,
                    style: _itemTitleStyle,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${report.subject} · ${report.learningDate} · ${report.score} 分',
                    style: _bodyStyle,
                  ),
                ],
              ),
            ),
            _StatusPill(
              label: report.masteryDisplayLabel,
              active: report.score >= 80,
            ),
            const SizedBox(width: 4),
            const Icon(Icons.chevron_right, color: AppColors.subtle),
          ],
        ),
      ),
    );
  }
}

class _LearningReportDetail extends StatelessWidget {
  const _LearningReportDetail({required this.report});

  final LearningReport report;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.sizeOf(context).height * 0.78,
        ),
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('学习报告详情', style: _sheetTitleStyle),
              const SizedBox(height: 6),
              Text(
                '${report.courseTitle} · ${report.subject} · ${report.learningDate}',
                style: _bodyStyle,
              ),
              const SizedBox(height: 18),
              _MetricStrip(report: report),
              const SizedBox(height: 18),
              const Text('学习结论', style: _titleStyle),
              const SizedBox(height: 7),
              Text(report.summary, style: _detailStyle),
              if (report.strengths.isNotEmpty) ...[
                const SizedBox(height: 18),
                const Text('本次表现', style: _titleStyle),
                const SizedBox(height: 7),
                for (final strength in report.strengths)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 5),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('•', style: _detailStyle),
                        const SizedBox(width: 7),
                        Expanded(child: Text(strength, style: _detailStyle)),
                      ],
                    ),
                  ),
              ],
              const SizedBox(height: 18),
              const Text('下一步建议', style: _titleStyle),
              const SizedBox(height: 7),
              Text(report.nextSuggestion, style: _detailStyle),
            ],
          ),
        ),
      ),
    );
  }
}

class _MetricStrip extends StatelessWidget {
  const _MetricStrip({required this.report});

  final LearningReport report;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _Metric(label: '得分', value: '${report.score}'),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _Metric(
            label: '独立正确',
            value: '${report.independentCorrectCount}',
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _Metric(label: '提示', value: '${report.hintCount}'),
        ),
      ],
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surfaceTinted,
        borderRadius: BorderRadius.circular(AppRadii.control),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Column(
          children: [
            Text(value, style: _metricValueStyle),
            const SizedBox(height: 3),
            Text(label, style: _bodyStyle),
          ],
        ),
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.label, required this.active});

  final String label;
  final bool active;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: active ? AppColors.successWash : AppColors.surfaceTinted,
        borderRadius: BorderRadius.circular(AppRadii.full),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
        child: Text(
          label,
          style: TextStyle(
            color: active ? AppColors.success : AppColors.muted,
            fontFamily: AppTypography.systemFont,
            fontSize: 11,
            fontWeight: FontWeight.w800,
          ),
        ),
      ),
    );
  }
}

class _EmptyLine extends StatelessWidget {
  const _EmptyLine({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        children: [
          Icon(icon, color: AppColors.subtle, size: 21),
          const SizedBox(width: 9),
          Text(text, style: _bodyStyle),
        ],
      ),
    );
  }
}

class _InlineNotice extends StatelessWidget {
  const _InlineNotice({
    required this.icon,
    required this.text,
    required this.foreground,
    required this.background,
    super.key,
  });

  final IconData icon;
  final String text;
  final Color foreground;
  final Color background;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppRadii.control),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: foreground, size: 18),
            const SizedBox(width: 8),
            Expanded(
              child: Text(text, style: _bodyStyle.copyWith(color: foreground)),
            ),
          ],
        ),
      ),
    );
  }
}

String _date(DateTime value) => DateFormat('yyyy/M/d').format(value.toLocal());

String _dateTime(DateTime value) =>
    DateFormat('M/d HH:mm').format(value.toLocal());

const _titleStyle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 16,
  fontWeight: FontWeight.w900,
  height: 1.25,
);

const _itemTitleStyle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 14,
  fontWeight: FontWeight.w800,
  height: 1.25,
);

const _bodyStyle = TextStyle(
  color: AppColors.muted,
  fontFamily: AppTypography.systemFont,
  fontSize: 12.5,
  fontWeight: FontWeight.w600,
  height: 1.45,
);

const _detailStyle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 14,
  fontWeight: FontWeight.w600,
  height: 1.55,
);

const _sheetTitleStyle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 21,
  fontWeight: FontWeight.w900,
  height: 1.2,
);

const _metricValueStyle = TextStyle(
  color: AppColors.brandDeep,
  fontFamily: AppTypography.systemFont,
  fontSize: 20,
  fontWeight: FontWeight.w900,
);
