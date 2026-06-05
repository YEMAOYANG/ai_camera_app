import 'package:guardian_parent_app/src/features/profile/domain/profile_models.dart';

class GuardianAvatarPersona {
  const GuardianAvatarPersona({
    required this.id,
    required this.assetPath,
    required this.loopAssetPath,
    required this.semanticLabel,
  });

  final String id;
  final String assetPath;
  final String loopAssetPath;
  final String semanticLabel;
}

const guardianMomPersona = GuardianAvatarPersona(
  id: 'guardian_mom',
  assetPath: 'assets/images/guardian/guardian_mom.png',
  loopAssetPath: 'assets/images/guardian/guardian_mom_loop.mp4',
  semanticLabel: '妈妈监护人形象',
);

const guardianDadPersona = GuardianAvatarPersona(
  id: 'guardian_dad',
  assetPath: 'assets/images/guardian/guardian_dad.png',
  loopAssetPath: 'assets/images/guardian/guardian_dad_loop.mp4',
  semanticLabel: '爸爸监护人形象',
);

const guardianGrandmaPersona = GuardianAvatarPersona(
  id: 'guardian_grandma',
  assetPath: 'assets/images/guardian/guardian_grandma.png',
  loopAssetPath: 'assets/images/guardian/guardian_grandma_loop.mp4',
  semanticLabel: '奶奶或外婆监护人形象',
);

const guardianGrandpaPersona = GuardianAvatarPersona(
  id: 'guardian_grandpa',
  assetPath: 'assets/images/guardian/guardian_grandpa.png',
  loopAssetPath: 'assets/images/guardian/guardian_grandpa_loop.mp4',
  semanticLabel: '爷爷或外公监护人形象',
);

const guardianFemaleAdultPersona = GuardianAvatarPersona(
  id: 'guardian_female_adult',
  assetPath: 'assets/images/guardian/guardian_female_adult.png',
  loopAssetPath: 'assets/images/guardian/guardian_female_adult_loop.mp4',
  semanticLabel: '女性家庭监护人形象',
);

const guardianMaleAdultPersona = GuardianAvatarPersona(
  id: 'guardian_male_adult',
  assetPath: 'assets/images/guardian/guardian_male_adult.png',
  loopAssetPath: 'assets/images/guardian/guardian_male_adult_loop.mp4',
  semanticLabel: '男性家庭监护人形象',
);

const guardianDefaultPersona = GuardianAvatarPersona(
  id: 'guardian_default',
  assetPath: 'assets/images/guardian/guardian_default.png',
  loopAssetPath: 'assets/images/guardian/guardian_default_loop.mp4',
  semanticLabel: '默认家庭监护人形象',
);

GuardianAvatarPersona resolveGuardianAvatarPersona({
  required AccountProfile? account,
  required ProfileSummary summary,
  required String relationship,
}) {
  final explicit =
      _fromPersona(account?.avatarPersona) ??
      _fromPersona(summary.avatarPersona);
  if (explicit != null) return explicit;

  final text = _normalizeRoleText(
    [
      relationship,
      account?.relationship ?? '',
      account?.displayName ?? '',
      summary.displayName,
      summary.roleLabel,
    ].join(' '),
  );

  if (_containsAny(text, const ['爷爷', '外公', '祖父', 'grandpa', 'grandfather'])) {
    return guardianGrandpaPersona;
  }
  if (_containsAny(text, const ['奶奶', '外婆', '祖母', 'grandma', 'grandmother'])) {
    return guardianGrandmaPersona;
  }
  if (_containsAny(text, const [
    '妈妈',
    '母亲',
    '妈咪',
    '干妈',
    'mother',
    'mom',
    'mama',
  ])) {
    return guardianMomPersona;
  }
  if (_containsAny(text, const ['爸爸', '父亲', '爹地', 'father', 'dad', 'papa'])) {
    return guardianDadPersona;
  }
  if (_containsAny(text, const [
    '阿姨',
    '小姨',
    '大姨',
    '姑姑',
    '姑妈',
    '舅妈',
    '姨妈',
    '婶婶',
    '伯母',
    '女性亲属',
  ])) {
    return guardianFemaleAdultPersona;
  }
  if (_containsAny(text, const ['叔叔', '舅舅', '伯伯', '伯父', '姑父', '姨父', '男性亲属'])) {
    return guardianMaleAdultPersona;
  }

  final gender = _normalizeRoleText(account?.gender ?? '');
  final ageGroup = _normalizeRoleText(account?.ageGroup ?? '');
  final senior = _containsAny(ageGroup, const [
    'senior',
    'elder',
    'older',
    'grand',
    '祖辈',
    '长辈',
    '老年',
  ]);
  if (_containsAny(gender, const ['female', 'woman', '女'])) {
    return senior ? guardianGrandmaPersona : guardianFemaleAdultPersona;
  }
  if (_containsAny(gender, const ['male', 'man', '男'])) {
    return senior ? guardianGrandpaPersona : guardianMaleAdultPersona;
  }

  return guardianDefaultPersona;
}

GuardianAvatarPersona? _fromPersona(String? value) {
  final persona = _normalizeRoleText(value ?? '');
  if (persona.isEmpty) return null;
  if (_containsAny(persona, const [
    'guardiangrandma',
    'grandma',
    'grandmother',
    '奶奶',
    '外婆',
  ])) {
    return guardianGrandmaPersona;
  }
  if (_containsAny(persona, const [
    'guardiangrandpa',
    'grandpa',
    'grandfather',
    '爷爷',
    '外公',
  ])) {
    return guardianGrandpaPersona;
  }
  if (_containsAny(persona, const ['guardianmom', 'mom', 'mother', '妈妈'])) {
    return guardianMomPersona;
  }
  if (_containsAny(persona, const ['guardiandad', 'dad', 'father', '爸爸'])) {
    return guardianDadPersona;
  }
  if (_containsAny(persona, const ['guardianfemaleadult', 'femaleadult'])) {
    return guardianFemaleAdultPersona;
  }
  if (_containsAny(persona, const ['guardianmaleadult', 'maleadult'])) {
    return guardianMaleAdultPersona;
  }
  if (_containsAny(persona, const ['guardiandefault', 'default'])) {
    return guardianDefaultPersona;
  }
  return null;
}

String _normalizeRoleText(String value) {
  return value.toLowerCase().replaceAll(RegExp(r'[\s_\-/.·]'), '').trim();
}

bool _containsAny(String value, List<String> needles) {
  for (final needle in needles) {
    if (value.contains(_normalizeRoleText(needle))) return true;
  }
  return false;
}
