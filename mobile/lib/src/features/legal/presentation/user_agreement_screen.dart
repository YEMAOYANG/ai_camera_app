import 'package:flutter/material.dart';
import 'package:guardian_parent_app/src/features/legal/domain/legal_document.dart';
import 'package:guardian_parent_app/src/features/legal/presentation/legal_document_screen.dart';

class UserAgreementScreen extends StatelessWidget {
  const UserAgreementScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const LegalDocumentScreen(document: LegalDocuments.userAgreement);
  }
}
