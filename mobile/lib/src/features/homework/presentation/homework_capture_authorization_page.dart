import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import 'package:warm_sight/src/shared/widgets/app_screen.dart';
import 'package:warm_sight/src/shared/widgets/app_toast.dart';
import '../../learning_review/application/learning_review_repository.dart';
import '../../learning_review/domain/learning_review_models.dart';
import '../../learning_review/presentation/learning_support_widgets.dart';
import '../application/homework_repository.dart';

class HomeworkCaptureAuthorizationPage extends ConsumerStatefulWidget {
  const HomeworkCaptureAuthorizationPage({required this.childId, super.key});
  final String childId;
  @override
  ConsumerState<HomeworkCaptureAuthorizationPage> createState() =>
      _CaptureState();
}

class _CaptureState extends ConsumerState<HomeworkCaptureAuthorizationPage> {
  String? taskId, deviceId, error;
  bool busy = false;
  int days = 1;
  Future<void> save(Json value) async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await ref
          .read(homeworkCaptureRepositoryProvider)
          .save(widget.childId, value);
      ref.invalidate(homeworkCaptureAuthorizationProvider(widget.childId));
      if (mounted) showAppToast(context, '拍摄授权已更新', tone: AppToastTone.success);
    } catch (e) {
      if (mounted) setState(() => error = learningError(e));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => AppScreen(
    title: '设备拍作业授权',
    subtitle: '由家长选择任务和设备，默认关闭',
    reserveBottomNavigation: false,
    onBack: () => learningBack(context),
    children: [
      const Text(
        '仅允许经过验收、无需转向或打断看护的设备拍摄指定学习任务。授权最长 7 天，可随时关闭。',
        style: TextStyle(color: AppColors.mutedStrong, height: 1.6),
      ),
      if (error != null)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Text(error!, style: const TextStyle(color: AppColors.danger)),
        ),
      ref
          .watch(homeworkCaptureAuthorizationProvider(widget.childId))
          .when(
            loading: () => const LearningLoading(),
            error: (e, _) => LearningError(
              e,
              () => ref.invalidate(
                homeworkCaptureAuthorizationProvider(widget.childId),
              ),
            ),
            data: (data) {
              final tasks = jsonList(data['learningTasks']),
                  devices = jsonList(data['devices']),
                  authorizations = jsonList(data['authorizations']);
              final available = devices
                  .where((d) => d['available'] == true)
                  .toList();
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (final a in authorizations)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                        tasks
                                .where((t) => t['id'] == a['taskId'])
                                .map((t) => textValue(t['title']))
                                .firstOrNull ??
                            '学习任务',
                      ),
                      subtitle: Text(
                        '${a['enabled'] == true ? '已授权' : '已关闭'} · ${learningDate(a['expiresAt'] is num ? DateTime.fromMillisecondsSinceEpoch(number(a['expiresAt'])) : null)} 到期',
                      ),
                      trailing: a['enabled'] == true
                          ? TextButton(
                              onPressed: busy
                                  ? null
                                  : () => save({...a, 'enabled': false}),
                              child: const Text('关闭'),
                            )
                          : null,
                    ),
                  if (tasks.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 20),
                      child: Text('请先创建学习任务，再为该任务授权拍摄。'),
                    ),
                  if (available.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 20),
                      child: Text('当前没有通过无干扰拍摄验收的设备。请在“学习与作业”中使用手机拍照或相册上传。'),
                    ),
                  for (final d in devices.where((d) => d['available'] != true))
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.videocam_off_outlined),
                      title: Text(textValue(d['name'])),
                      subtitle: Text(
                        textValue(d['unavailableReason']).isEmpty
                            ? '暂不支持作业拍摄'
                            : textValue(d['unavailableReason']),
                      ),
                    ),
                  if (tasks.isNotEmpty && available.isNotEmpty) ...[
                    const LearningHeading('新增授权'),
                    DropdownButtonFormField<String>(
                      initialValue: taskId,
                      decoration: const InputDecoration(labelText: '学习任务'),
                      items: [
                        for (final t in tasks)
                          DropdownMenuItem(
                            value: textValue(t['id']),
                            child: Text(
                              textValue(t['title']),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                      ],
                      isExpanded: true,
                      onChanged: busy
                          ? null
                          : (v) => setState(() => taskId = v),
                    ),
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      initialValue: deviceId,
                      decoration: const InputDecoration(labelText: '用于拍摄的设备'),
                      items: [
                        for (final d in available)
                          DropdownMenuItem(
                            value: textValue(d['id']),
                            child: Text(
                              textValue(d['name']),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                      ],
                      isExpanded: true,
                      onChanged: busy
                          ? null
                          : (v) => setState(() => deviceId = v),
                    ),
                    const SizedBox(height: 12),
                    DropdownButtonFormField<int>(
                      initialValue: days,
                      decoration: const InputDecoration(labelText: '有效期'),
                      items: [
                        for (final n in [1, 3, 7])
                          DropdownMenuItem(value: n, child: Text('$n 天')),
                      ],
                      onChanged: busy ? null : (v) => setState(() => days = v!),
                    ),
                    const SizedBox(height: 20),
                    AppPrimaryButton(
                      label: '授权指定任务拍摄',
                      loading: busy,
                      onTap: busy || taskId == null || deviceId == null
                          ? null
                          : () {
                              final previous = authorizations
                                  .where((a) => a['taskId'] == taskId)
                                  .firstOrNull;
                              save({
                                'taskId': taskId,
                                'deviceId': deviceId,
                                'revision': number(previous?['revision']),
                                'enabled': true,
                                'expiresAt': DateTime.now()
                                    .add(Duration(days: days))
                                    .millisecondsSinceEpoch,
                              });
                            },
                    ),
                  ],
                ],
              );
            },
          ),
    ],
  );
}
