import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/learning/domain/textbook_models.dart';

abstract interface class TextbookGateway {
  Future<SchoolTextbookCatalog> catalog(String childId);
  Future<void> select(
    String childId,
    SchoolTextbookCatalog catalog,
    SchoolTextbook book,
  );
}

final textbookRepositoryProvider = Provider<TextbookGateway>(
  (ref) => TextbookRepository(ref.watch(apiClientProvider)),
);
final schoolTextbooksProvider = FutureProvider.autoDispose
    .family<SchoolTextbookCatalog, String>(
      (ref, childId) => ref.watch(textbookRepositoryProvider).catalog(childId),
    );

class TextbookRepository implements TextbookGateway {
  const TextbookRepository(this.api);
  final ApiClient api;
  String _path(String childId) =>
      '/children/${Uri.encodeComponent(childId)}/textbooks';
  @override
  Future<SchoolTextbookCatalog> catalog(String childId) async {
    try {
      return SchoolTextbookCatalog.fromJson(
        (await api.get(_path(childId))).data,
      );
    } on DioException catch (error) {
      throw TextbookException.fromDio(error);
    }
  }

  @override
  Future<void> select(
    String childId,
    SchoolTextbookCatalog catalog,
    SchoolTextbook book,
  ) async {
    try {
      await api.put(
        _path(childId),
        data: {
          'editionId': book.editionId,
          'alignmentRevisionId': book.revisionId,
          'expectedSelectionRevision': book.selectionRevision,
          'schoolYearStartYear': catalog.year,
          'semester': catalog.semester,
        },
      );
    } on DioException catch (error) {
      throw TextbookException.fromDio(error);
    }
  }
}

class TextbookException implements Exception {
  const TextbookException(this.message);
  final String message;
  factory TextbookException.fromDio(DioException error) {
    final data = error.response?.data;
    return TextbookException(
      data is Map && data['message'] is String
          ? data['message'] as String
          : '网络暂时没有连接上，请刷新后重试',
    );
  }
  @override
  String toString() => message;
}
