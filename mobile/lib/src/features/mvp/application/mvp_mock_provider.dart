import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/core/config/app_environment.dart';
import 'package:guardian_parent_app/src/features/mvp/domain/mvp_models.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

final guardianMvpSnapshotProvider = Provider<GuardianMvpSnapshot>((ref) {
  final environment = ref.watch(appEnvironmentProvider);
  if (!environment.useMockData) return _productionPlaceholderSnapshot;
  return _mockSnapshot;
});

const _productionPlaceholderSnapshot = GuardianMvpSnapshot(
  child: ChildProfileSummary(
    name: '孩子',
    stage: '资料待同步',
    grade: '',
    location: '家庭空间',
    currentState: '看护数据同步中',
    todayFocus: '完成首次设置后，首页会生成任务和设备摘要',
  ),
  device: GuardianDeviceSummary(
    name: '看护设备',
    room: '家庭空间',
    online: false,
    connectionLabel: '待同步',
    networkLabel: '正在同步设备状态',
    privacyLightOn: false,
    cameraEnabled: false,
    microphoneEnabled: false,
    lastOnlineLabel: '等待设备接入',
  ),
  aiSummary: '完成设备绑定后，AI 观察摘要会在这里显示。',
  nextAction: '请先完成孩子资料、设备绑定和任务配置。',
  pendingItems: [],
  tasks: [],
  alerts: [],
  familyMembers: [],
  settings: _settings,
);

const _mockSnapshot = GuardianMvpSnapshot(
  child: ChildProfileSummary(
    name: '小宇',
    stage: '小学',
    grade: '一年级',
    location: '书桌区',
    currentState: '数学作业进行中，状态正常',
    todayFocus: '练习作业自启动，减少家长重复催促',
  ),
  device: GuardianDeviceSummary(
    name: '客厅设备',
    room: '客厅书桌区',
    online: true,
    connectionLabel: '在线',
    networkLabel: 'Home Wi-Fi 5G · 信号良好',
    privacyLightOn: true,
    cameraEnabled: true,
    microphoneEnabled: true,
    lastOnlineLabel: '刚刚在线',
  ),
  aiSummary: '看护助手已提醒 2 次，孩子在 3 分钟内回到书桌。当前不需要家长介入，12 分钟后需要确认证据。',
  nextAction: '19:35 进入休息，之后确认数学作业证据。',
  pendingItems: [
    PendingCareItem(
      title: '作业证据待确认',
      detail: '2 张书桌截图，AI 置信度 86%',
      actionLabel: '处理',
      tone: StatusTone.warning,
      taskId: 'math-homework',
    ),
    PendingCareItem(
      title: '奖励申请待确认',
      detail: '孩子申请周末亲子游戏 20 分钟',
      actionLabel: '确认',
      tone: StatusTone.neutral,
      taskId: null,
    ),
  ],
  tasks: [
    MvpTask(
      id: 'drink-break',
      title: '喝水休息',
      type: '生活',
      timeLabel: '17:30',
      durationLabel: '5 分钟',
      status: MvpTaskStatus.completed,
      points: 1,
      evidence: TaskEvidence(
        summary: '摄像头完成一次温和提醒，孩子已喝水。',
        confidenceLabel: '92%',
        leaveSeatCount: 0,
        parentDecision: '自动完成',
      ),
      aiAdvice: '无需重复提醒，继续保持低打扰。',
      nextStep: '已进入今日记录。',
    ),
    MvpTask(
      id: 'math-homework',
      title: '数学作业',
      type: '学习',
      timeLabel: '19:00 - 19:40',
      durationLabel: '25 分钟专注 + 5 分钟休息',
      status: MvpTaskStatus.running,
      points: 5,
      evidence: TaskEvidence(
        summary: '桌面截图显示书写动作稳定，离座后 3 分钟内回座。',
        confidenceLabel: '86%',
        leaveSeatCount: 1,
        parentDecision: '待确认',
      ),
      aiAdvice: '建议完成本轮后再由家长确认证据，避免中途打断。',
      nextStep: '12 分钟后进入证据确认。',
    ),
    MvpTask(
      id: 'schoolbag',
      title: '检查小书包',
      type: '生活',
      timeLabel: '20:10',
      durationLabel: '睡前 + 明早复查',
      status: MvpTaskStatus.pendingStart,
      points: 3,
      evidence: TaskEvidence(
        summary: '明天按一年级课表准备语文、数学和美术材料。',
        confidenceLabel: '待执行',
        leaveSeatCount: 0,
        parentDecision: '未开始',
      ),
      aiAdvice: '先让孩子自查，再在明早补一次轻提醒。',
      nextStep: '20:10 由摄像头温和提醒。',
    ),
    MvpTask(
      id: 'bedtime',
      title: '睡前洗漱',
      type: '作息',
      timeLabel: '21:00',
      durationLabel: '目标 21:30 上床',
      status: MvpTaskStatus.pendingStart,
      points: 2,
      evidence: TaskEvidence(
        summary: '洗漱、检查小书包、上床三个节点。',
        confidenceLabel: '待执行',
        leaveSeatCount: 0,
        parentDecision: '未开始',
      ),
      aiAdvice: '今晚任务较多，建议提前 10 分钟进入睡前节奏。',
      nextStep: '21:00 开始睡前提醒。',
    ),
    MvpTask(
      id: 'english-read',
      title: '英语听读',
      type: '学习',
      timeLabel: '19:50',
      durationLabel: '15 分钟',
      status: MvpTaskStatus.needsConfirmation,
      points: 3,
      evidence: TaskEvidence(
        summary: '音频片段显示朗读完成，需要家长确认发音任务结果。',
        confidenceLabel: '78%',
        leaveSeatCount: 0,
        parentDecision: '待确认',
      ),
      aiAdvice: '建议确认完成，但不要追加过高奖励。',
      nextStep: '等待家长确认。',
    ),
  ],
  alerts: [
    MvpAlert(
      id: 'door-sound',
      title: '门口声音',
      timeLabel: '18:42',
      summary: '门口出现短暂声音，未识别到开门动作。',
      level: '普通',
      state: AlertState.read,
      suggestedAction: '保留记录，无需升级。',
    ),
    MvpAlert(
      id: 'leave-seat',
      title: '离座过久',
      timeLabel: '19:18',
      summary: '作业中离座 6 分钟，摄像头已温和提醒回座。',
      level: '关注',
      state: AlertState.processing,
      suggestedAction: '完成作业后一起看是否需要调整休息规则。',
    ),
    MvpAlert(
      id: 'device-network',
      title: '网络波动',
      timeLabel: '19:25',
      summary: '实时看护画面短暂停顿，设备随后自动恢复。',
      level: '设备',
      state: AlertState.handled,
      suggestedAction: '无需处理，可在设备管理查看网络状态。',
    ),
    MvpAlert(
      id: 'homework-noise',
      title: '异常声音',
      timeLabel: '昨天 21:08',
      summary: '睡前阶段有较高音量，家长已标记为误报。',
      level: '普通',
      state: AlertState.falseAlarm,
      suggestedAction: '已记录为误报样例。',
    ),
  ],
  familyMembers: [
    MvpFamilyMember(
      name: '妈妈',
      role: '管理员',
      permission: '全部看护、任务和隐私设置',
      notifyLabel: '全部通知',
    ),
    MvpFamilyMember(
      name: '爸爸',
      role: '监护人',
      permission: '看护、告警和任务确认',
      notifyLabel: '重要通知',
    ),
    MvpFamilyMember(
      name: '奶奶',
      role: '临时查看者',
      permission: '只能查看今日任务和部分提醒',
      notifyLabel: '暂停通知',
    ),
  ],
  settings: _settings,
);

const _settings = [
  MvpSettingEntry(
    title: '家庭成员',
    subtitle: '成员权限和协作通知',
    kind: MvpSettingKind.family,
  ),
  MvpSettingEntry(
    title: '孩子资料',
    subtitle: '生日、就读阶段和任务模板',
    kind: MvpSettingKind.child,
  ),
  MvpSettingEntry(
    title: '设备管理',
    subtitle: '在线状态、网络和隐私灯',
    kind: MvpSettingKind.device,
  ),
  MvpSettingEntry(
    title: '积分',
    subtitle: '余额、任务奖励和兑换流水',
    kind: MvpSettingKind.points,
  ),
  MvpSettingEntry(
    title: '奖励',
    subtitle: '奖励项、兑换记录和手动兑现',
    kind: MvpSettingKind.rewards,
  ),
  MvpSettingEntry(
    title: 'AI 规则设置',
    subtitle: '提醒语气、作业模式和误判纠正',
    kind: MvpSettingKind.aiRules,
  ),
  MvpSettingEntry(
    title: '隐私权限',
    subtitle: '音视频、记录保存和儿童数据删除',
    kind: MvpSettingKind.privacy,
  ),
  MvpSettingEntry(
    title: '用户协议',
    subtitle: '查看家庭使用边界',
    kind: MvpSettingKind.userAgreement,
  ),
  MvpSettingEntry(
    title: '隐私政策',
    subtitle: '查看儿童数据和权限说明',
    kind: MvpSettingKind.privacyPolicy,
  ),
];
