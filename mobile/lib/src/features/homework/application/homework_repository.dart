import 'dart:typed_data';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import '../../learning_review/domain/learning_review_models.dart';
import '../domain/homework_models.dart';
import '../domain/homework_upload_photo.dart';

final homeworkRepositoryProvider = Provider(
  (ref) => HomeworkRepository(ref.watch(apiClientProvider)),
);
final homeworkListProvider = AsyncNotifierProvider.autoDispose
    .family<HomeworkListController, List<HomeworkSubmission>, String>(
      HomeworkListController.new,
    );
final homeworkDetailProvider = AsyncNotifierProvider.autoDispose
    .family<HomeworkDetailController, HomeworkSubmission, String>(
      HomeworkDetailController.new,
    );

class HomeworkListController extends AsyncNotifier<List<HomeworkSubmission>> {
  HomeworkListController(this.childId);
  final String childId;
  int _readVersion = 0;
  Future<List<HomeworkSubmission>>? _initialRead, _refreshing;

  @override
  Future<List<HomeworkSubmission>> build() async {
    _readVersion++;
    final read = ref.watch(homeworkRepositoryProvider).list(childId);
    _initialRead = read;
    try {
      return await read;
    } finally {
      if (identical(_initialRead, read)) _initialRead = null;
    }
  }

  // A detail write also wins over a list read that started before it.
  void acceptFromDetail(HomeworkSubmission result) {
    if (!ref.mounted || result.childId != childId) return;
    _readVersion++;
    final current = state.asData?.value;
    if (current == null) return;
    state = AsyncData([
      for (final item in current)
        if (item.id == result.id && item.revision <= result.revision)
          result
        else
          item,
    ]);
  }

  Future<List<HomeworkSubmission>> refresh() =>
      _initialRead ?? (_refreshing ??= _refreshOnce());

  Future<List<HomeworkSubmission>> _refreshOnce() async {
    final request = ++_readVersion;
    try {
      final result = await ref.read(homeworkRepositoryProvider).list(childId);
      if (!ref.mounted) return result;
      final current = state.asData?.value;
      if (request != _readVersion && current != null) return current;
      state = AsyncData(result);
      return result;
    } catch (error, stack) {
      if (ref.mounted) {
        final current = state.asData?.value;
        if (request != _readVersion && current != null) return current;
        if (current == null) state = AsyncError(error, stack);
      }
      rethrow;
    } finally {
      _refreshing = null;
    }
  }
}

class HomeworkDetailController extends AsyncNotifier<HomeworkSubmission> {
  HomeworkDetailController(this.id);
  final String id;
  int _readVersion = 0;
  Future<HomeworkSubmission>? _initialRead, _refreshing;

  @override
  Future<HomeworkSubmission> build() async {
    _readVersion++;
    final read = ref.watch(homeworkRepositoryProvider).get(id);
    _initialRead = read;
    try {
      return await read;
    } finally {
      if (identical(_initialRead, read)) _initialRead = null;
    }
  }

  // A refresh started before a write must never restore a removed photo.
  void beginMutation() => _readVersion++;

  void accept(HomeworkSubmission result) {
    if (!ref.mounted || result.id != id) return;
    _readVersion++;
    final current = state.asData?.value;
    if (current != null && current.revision > result.revision) return;
    state = AsyncData(result);
  }

  Future<HomeworkSubmission> refresh() =>
      _initialRead ?? (_refreshing ??= _refreshOnce());

  Future<HomeworkSubmission> _refreshOnce() async {
    final request = ++_readVersion;
    try {
      final result = await ref.read(homeworkRepositoryProvider).get(id);
      if (!ref.mounted) return result;
      final current = state.asData?.value;
      if (request != _readVersion ||
          (current != null && current.revision > result.revision)) {
        return current ?? result;
      }
      state = AsyncData(result);
      return result;
    } catch (error, stack) {
      if (ref.mounted) {
        final current = state.asData?.value;
        if (request != _readVersion && current != null) return current;
        // Keep successfully saved pages visible when a later read fails.
        if (current == null) state = AsyncError(error, stack);
      }
      rethrow;
    } finally {
      _refreshing = null;
    }
  }
}

final homeworkImageProvider = FutureProvider.autoDispose
    .family<
      Uint8List,
      ({String submissionId, String pageId, int revision, bool original})
    >(
      (ref, key) => ref
          .watch(homeworkRepositoryProvider)
          .image(key.submissionId, key.pageId, original: key.original),
    );

class HomeworkRepository {
  const HomeworkRepository(this.api);
  final ApiClient api;
  String _path(String id) => '/homework-submissions/${Uri.encodeComponent(id)}';
  HomeworkSubmission _submission(Response<dynamic> r) =>
      HomeworkSubmission(jsonMap(jsonMap(r.data)['submission']));
  Future<List<HomeworkSubmission>> list(String childId) async => jsonList(
    jsonMap(
      (await api.get(
        '/children/${Uri.encodeComponent(childId)}/homework-submissions',
      )).data,
    )['submissions'],
  ).map(HomeworkSubmission.new).toList();
  Future<HomeworkSubmission> get(String id) async =>
      _submission(await api.get(_path(id)));
  Future<HomeworkSubmission> create(
    String childId, {
    required String title,
    required String subject,
    required String idempotencyKey,
    String analysisKind = 'questions',
  }) async => _submission(
    await api.post(
      '/children/${Uri.encodeComponent(childId)}/homework-submissions',
      data: {
        'title': title,
        'subject': subject,
        'analysisKind': analysisKind,
        'analysisConsent': true,
        'idempotencyKey': idempotencyKey,
      },
    ),
  );
  Future<HomeworkSubmission> upload(
    HomeworkSubmission submission, {
    required Uint8List bytes,
    required String idempotencyKey,
    HomeworkPhotoFormat format = HomeworkPhotoFormat.png,
  }) async => _submission(
    await api.post(
      '${_path(submission.id)}/pages',
      data: FormData.fromMap({
        'revision': submission.revision.toString(),
        'idempotencyKey': idempotencyKey,
        'file': MultipartFile.fromBytes(
          bytes,
          filename: format == HomeworkPhotoFormat.jpeg
              ? 'homework.jpg'
              : 'homework.png',
          contentType: DioMediaType(
            'image',
            format == HomeworkPhotoFormat.jpeg ? 'jpeg' : 'png',
          ),
        ),
      }),
      options: Options(
        sendTimeout: const Duration(seconds: 90),
        receiveTimeout: const Duration(seconds: 30),
      ),
    ),
  );
  Future<HomeworkSubmission> editPages(
    HomeworkSubmission submission,
    List<Json> pages,
  ) async => _submission(
    await api.patch(
      '${_path(submission.id)}/pages',
      data: {'revision': submission.revision, 'pages': pages},
    ),
  );
  Future<HomeworkSubmission> analyze(HomeworkSubmission submission) async =>
      _submission(
        await api.post(
          '${_path(submission.id)}/analyze',
          data: {'revision': submission.revision},
        ),
      );
  Future<void> delete(HomeworkSubmission submission) async {
    await api.delete(
      _path(submission.id),
      data: {'revision': submission.revision},
    );
  }

  // Construct the authenticated path ourselves. Never forward tokens to a URL
  // supplied by recognition content, and never persist private image bytes.
  Future<Uint8List> image(
    String submissionId,
    String pageId, {
    bool original = false,
  }) async {
    final response = await api.get(
      '${_path(submissionId)}/pages/${Uri.encodeComponent(pageId)}/image',
      queryParameters: original ? {'original': '1'} : null,
      options: Options(
        responseType: ResponseType.bytes,
        followRedirects: false,
      ),
    );
    return Uint8List.fromList((response.data as List).cast<int>());
  }
}

final homeworkCaptureAuthorizationProvider = FutureProvider.autoDispose
    .family<Json, String>(
      (ref, childId) =>
          ref.watch(homeworkCaptureRepositoryProvider).get(childId),
    );
final homeworkCaptureRepositoryProvider = Provider(
  (ref) => HomeworkCaptureRepository(ref.watch(apiClientProvider)),
);

class HomeworkCaptureRepository {
  const HomeworkCaptureRepository(this.api);
  final ApiClient api;
  Future<Json> get(String childId) async => jsonMap(
    (await api.get(
      '/children/${Uri.encodeComponent(childId)}/homework-capture-authorization',
    )).data,
  );
  Future<void> save(String childId, Json value) async {
    await api.put(
      '/children/${Uri.encodeComponent(childId)}/homework-capture-authorization',
      data: value,
    );
  }
}
