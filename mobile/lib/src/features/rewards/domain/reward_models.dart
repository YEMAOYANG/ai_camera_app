import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

class RewardItem {
  const RewardItem({
    required this.id,
    required this.familyId,
    required this.childId,
    required this.title,
    required this.description,
    required this.pointsCost,
    required this.category,
    required this.status,
    required this.icon,
  });

  final String id;
  final String familyId;
  final String childId;
  final String title;
  final String description;
  final int pointsCost;
  final String category;
  final String status;
  final String icon;

  String get statusLabel {
    return switch (status) {
      'active' || 'available' => '可兑换',
      'paused' => '已暂停',
      'archived' => '已归档',
      _ => '可兑换',
    };
  }

  bool get available => status == 'active' || status == 'available';

  static RewardItem fromJson(Map<String, dynamic> json) {
    return RewardItem(
      id: _asString(json['id']),
      familyId: _asString(json['familyId']),
      childId: _asString(json['childId']),
      title: _asString(json['title'], fallback: '未命名奖励'),
      description: _asString(json['description']),
      pointsCost: _asInt(json['pointsCost']),
      category: _asString(json['category'], fallback: 'family'),
      status: _asString(json['status'], fallback: 'active'),
      icon: _asString(json['icon']),
    );
  }
}

enum RedemptionStatus {
  redeemed('redeemed', '待兑现', StatusTone.warning),
  fulfilled('fulfilled', '已兑现', StatusTone.success),
  cancelled('cancelled', '已取消', StatusTone.neutral),
  requested('requested', '待审批', StatusTone.warning),
  pendingParentApproval('pending_parent_approval', '待审批', StatusTone.warning),
  approved('approved', '已通过', StatusTone.success),
  rejected('rejected', '已拒绝', StatusTone.danger);

  const RedemptionStatus(this.value, this.label, this.tone);

  final String value;
  final String label;
  final StatusTone tone;

  static RedemptionStatus fromValue(String value) {
    return RedemptionStatus.values.firstWhere(
      (status) => status.value == value,
      orElse: () => RedemptionStatus.redeemed,
    );
  }
}

class RewardRedemption {
  const RewardRedemption({
    required this.id,
    required this.childId,
    required this.rewardItemId,
    required this.rewardTitle,
    required this.pointsCost,
    required this.status,
    required this.requestedAt,
    required this.fulfilledAt,
    required this.cancelledAt,
  });

  final String id;
  final String childId;
  final String rewardItemId;
  final String rewardTitle;
  final int pointsCost;
  final RedemptionStatus status;
  final int? requestedAt;
  final int? fulfilledAt;
  final int? cancelledAt;

  bool get canFulfill => status == RedemptionStatus.redeemed;
  bool get canCancel => status == RedemptionStatus.redeemed;

  static RewardRedemption fromJson(Map<String, dynamic> json) {
    return RewardRedemption(
      id: _asString(json['id']),
      childId: _asString(json['childId']),
      rewardItemId: _asString(json['rewardItemId']),
      rewardTitle: _asString(json['rewardTitle']),
      pointsCost: _asInt(json['pointsCost']),
      status: RedemptionStatus.fromValue(_asString(json['status'])),
      requestedAt: _asNullableInt(json['requestedAt']),
      fulfilledAt: _asNullableInt(json['fulfilledAt']),
      cancelledAt: _asNullableInt(json['cancelledAt']),
    );
  }
}

class RewardsSummary {
  const RewardsSummary({required this.items, required this.redemptions});

  final List<RewardItem> items;
  final List<RewardRedemption> redemptions;
}

String _asString(dynamic value, {String fallback = ''}) {
  return value is String && value.isNotEmpty ? value : fallback;
}

int _asInt(dynamic value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value) ?? 0;
  return 0;
}

int? _asNullableInt(dynamic value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}
