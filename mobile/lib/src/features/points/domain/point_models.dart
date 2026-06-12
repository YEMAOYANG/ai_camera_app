class PointAccount {
  const PointAccount({
    required this.familyId,
    required this.childId,
    required this.balance,
    required this.stageNoticeHandledBalance,
    required this.updatedAt,
  });

  final String familyId;
  final String childId;
  final int balance;
  final int stageNoticeHandledBalance;
  final int updatedAt;

  static const empty = PointAccount(
    familyId: '',
    childId: '',
    balance: 0,
    stageNoticeHandledBalance: 0,
    updatedAt: 0,
  );

  static PointAccount fromJson(Map<String, dynamic> json) {
    return PointAccount(
      familyId: _asString(json['familyId']),
      childId: _asString(json['childId']),
      balance: _asInt(json['balance']),
      stageNoticeHandledBalance: _asInt(json['stageNoticeHandledBalance']),
      updatedAt: _asInt(json['updatedAt']),
    );
  }
}

class PointLedgerEntry {
  const PointLedgerEntry({
    required this.id,
    required this.childId,
    required this.delta,
    required this.balanceAfter,
    required this.type,
    required this.sourceType,
    required this.sourceId,
    required this.note,
    required this.createdAt,
  });

  final String id;
  final String childId;
  final int delta;
  final int balanceAfter;
  final String type;
  final String sourceType;
  final String sourceId;
  final String note;
  final int createdAt;

  String get typeLabel {
    return switch (type) {
      'task_completed' => '任务奖励',
      'parent_adjustment' => '家长调整',
      'redemption_spent' => '奖励兑换',
      'redemption_cancelled' => '兑换取消',
      'system_adjustment' => '系统调整',
      _ => '积分变更',
    };
  }

  static PointLedgerEntry fromJson(Map<String, dynamic> json) {
    return PointLedgerEntry(
      id: _asString(json['id']),
      childId: _asString(json['childId']),
      delta: _asInt(json['delta']),
      balanceAfter: _asInt(json['balanceAfter']),
      type: _asString(json['type']),
      sourceType: _asString(json['sourceType']),
      sourceId: _asString(json['sourceId']),
      note: _asString(json['note']),
      createdAt: _asInt(json['createdAt']),
    );
  }
}

class PointsSummary {
  const PointsSummary({required this.account, required this.ledger});

  final PointAccount account;
  final List<PointLedgerEntry> ledger;
}

String _asString(dynamic value) {
  return value is String ? value : '';
}

int _asInt(dynamic value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value) ?? 0;
  return 0;
}
