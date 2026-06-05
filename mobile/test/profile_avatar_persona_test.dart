import 'package:flutter_test/flutter_test.dart';
import 'package:guardian_parent_app/src/features/profile/domain/profile_avatar_persona.dart';
import 'package:guardian_parent_app/src/features/profile/domain/profile_models.dart';

void main() {
  group('resolveGuardianAvatarPersona', () {
    test('maps direct family roles to specific guardian assets', () {
      expect(_resolve('妈妈').id, 'guardian_mom');
      expect(_resolve('爸爸').id, 'guardian_dad');
      expect(_resolve('爷爷').id, 'guardian_grandpa');
      expect(_resolve('外公').id, 'guardian_grandpa');
      expect(_resolve('奶奶').id, 'guardian_grandma');
      expect(_resolve('外婆').id, 'guardian_grandma');
    });

    test('maps custom recognizable relatives to adult guardian assets', () {
      expect(_resolve('小姨').id, 'guardian_female_adult');
      expect(_resolve('舅妈').id, 'guardian_female_adult');
      expect(_resolve('叔叔').id, 'guardian_male_adult');
      expect(_resolve('舅舅').id, 'guardian_male_adult');
    });

    test('keeps ambiguous custom labels on the default guardian asset', () {
      expect(_resolve('监护人A').id, 'guardian_default');
      expect(_resolve('老师').id, 'guardian_default');
      expect(_resolve('家人').id, 'guardian_default');
    });

    test('uses explicit avatar persona before relationship text', () {
      final persona = resolveGuardianAvatarPersona(
        account: _account(relationship: '妈妈', avatarPersona: 'guardian_dad'),
        summary: _summary(),
        relationship: '妈妈',
      );

      expect(persona.id, 'guardian_dad');
    });

    test(
      'does not confuse grandmother with mother in explicit persona text',
      () {
        final persona = resolveGuardianAvatarPersona(
          account: _account(relationship: '监护人', avatarPersona: 'grandmother'),
          summary: _summary(),
          relationship: '监护人',
        );

        expect(persona.id, 'guardian_grandma');
      },
    );
  });
}

GuardianAvatarPersona _resolve(String relationship) {
  return resolveGuardianAvatarPersona(
    account: _account(relationship: relationship),
    summary: _summary(),
    relationship: relationship,
  );
}

ProfileSummary _summary({String avatarPersona = ''}) {
  return ProfileSummary(
    spaceTitle: '家庭看护空间',
    familyId: 'family_test',
    familyName: '我的家庭空间',
    displayName: '家长',
    phone: '13800002026',
    roleLabel: '管理员',
    avatarPersona: avatarPersona,
    memberCount: 1,
    deviceCount: 1,
    pendingItemCount: 0,
    child: null,
  );
}

AccountProfile _account({
  required String relationship,
  String avatarPersona = '',
  String gender = '',
  String ageGroup = '',
}) {
  return AccountProfile(
    userId: 'user_test',
    phone: '13800002026',
    displayName: '家长',
    familyName: '我的家庭空间',
    relationship: relationship,
    role: 'admin',
    avatarPersona: avatarPersona,
    gender: gender,
    ageGroup: ageGroup,
  );
}
