import 'dart:convert';
import 'dart:math' as math;
import 'dart:ui' as ui;
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import 'package:image_picker_android/image_picker_android.dart';
import 'package:image_picker_platform_interface/image_picker_platform_interface.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:warm_sight/src/core/storage/auth_session_store.dart';
import 'package:warm_sight/src/core/storage/onboarding_store.dart';
import '../../learning_review/application/learning_review_repository.dart';
import '../../learning_review/domain/learning_review_models.dart';
import '../domain/homework_upload_photo.dart';

final homeworkPhotoPickerProvider = Provider(
  (ref) => HomeworkPhotoPicker(
    ImagePicker(),
    ref.watch(sharedPreferencesProvider),
    () => ref.read(authSessionStoreProvider).currentSession?.userId ?? '',
  ),
);
final homeworkPhotoRecoveryProvider = FutureProvider.autoDispose
    .family<String?, String>(
      (ref, childId) => ref.watch(homeworkPhotoPickerProvider).recover(childId),
    );

class HomeworkPhotoException implements Exception {
  const HomeworkPhotoException(this.message, {this.permission = false});
  final String message;
  final bool permission;
}

class PendingHomeworkPhoto {
  const PendingHomeworkPhoto({required this.path, required this.key});
  final String path, key;
  Json get json => {'path': path, 'key': key};
}

class HomeworkPhotoPicker {
  HomeworkPhotoPicker(this.picker, this.preferences, this.userId);
  final ImagePicker picker;
  final SharedPreferences preferences;
  final String Function() userId;
  final Map<String, int> _discardVersions = {};
  String get _store => 'homework.pending.${userId()}';
  String get _capture => 'homework.capture.${userId()}';
  List<PendingHomeworkPhoto> pending(String id) {
    final all = jsonMap(jsonDecode(preferences.getString(_store) ?? '{}'));
    return jsonList(all[id])
        .map(
          (e) => PendingHomeworkPhoto(
            path: textValue(e['path']),
            key: textValue(e['key']),
          ),
        )
        .toList();
  }

  Future<void> _save(String id, List<PendingHomeworkPhoto> values) async {
    final all = jsonMap(jsonDecode(preferences.getString(_store) ?? '{}'));
    if (values.isEmpty) {
      all.remove(id);
    } else {
      all[id] = values.map((e) => e.json).toList();
    }
    await preferences.setString(_store, jsonEncode(all));
  }

  Future<void> remove(String id, String key) async =>
      _save(id, pending(id).where((e) => e.key != key).toList());
  Future<void> discard(String id) async {
    final owner = userId();
    final key = '$owner:$id';
    _discardVersions[key] = (_discardVersions[key] ?? 0) + 1;
    final captureKey = 'homework.capture.$owner';
    final capture = jsonMap(
      jsonDecode(preferences.getString(captureKey) ?? '{}'),
    );
    if (capture['submissionId'] == id) await preferences.remove(captureKey);
    if (userId() == owner) await _save(id, []);
  }

  Future<void> pick(
    String id,
    String childId, {
    required bool camera,
    required int remaining,
  }) async {
    final owner = userId();
    final captureKey = 'homework.capture.$owner';
    final discardKey = '$owner:$id';
    final discardVersion = _discardVersions[discardKey] ?? 0;
    void requireSameParent() {
      if (owner.isEmpty || userId() != owner) {
        throw const HomeworkPhotoException('登录状态已变化，请重新打开作业。');
      }
      if ((_discardVersions[discardKey] ?? 0) != discardVersion) {
        throw const HomeworkPhotoException('待上传照片已移除，需要时请重新选择。');
      }
    }

    requireSameParent();
    if (remaining <= 0) {
      throw const HomeworkPhotoException('每份最多 10 页，请先删除多余页面。');
    }
    if (pending(id).isNotEmpty) {
      throw const HomeworkPhotoException('请先继续上传或移除之前未上传的照片。');
    }
    if (camera &&
        !kIsWeb &&
        {
          TargetPlatform.android,
          TargetPlatform.iOS,
        }.contains(defaultTargetPlatform)) {
      final permission = await Permission.camera.request();
      if (!permission.isGranted) {
        throw const HomeworkPhotoException(
          '相机权限尚未开启。可以在设置中开启，或改用相册。',
          permission: true,
        );
      }
    }
    requireSameParent();
    final capture = jsonEncode({
      'submissionId': id,
      'childId': childId,
      'requestId': learningRequestId(),
    });
    await preferences.setString(captureKey, capture);
    try {
      final files = camera
          ? [
              ?await picker.pickImage(
                source: ImageSource.camera,
                maxWidth: 3000,
                maxHeight: 4000,
                imageQuality: 92,
                requestFullMetadata: false,
              ),
            ]
          : await _pickAlbum(remaining);
      requireSameParent();
      if (files.length > remaining) {
        throw const HomeworkPhotoException('所选照片超过剩余页数，请减少后重选。');
      }
      await _save(
        id,
        files
            .map(
              (e) =>
                  PendingHomeworkPhoto(path: e.path, key: learningRequestId()),
            )
            .toList(),
      );
    } on PlatformException catch (e) {
      throw HomeworkPhotoException(
        e.code.contains('access') ? '无法访问相机或照片，请检查系统权限。' : '暂时无法选择照片，请重试。',
        permission: e.code.contains('access'),
      );
    } finally {
      if (preferences.getString(captureKey) == capture) {
        await preferences.remove(captureKey);
      }
    }
  }

  Future<List<XFile>> _pickAlbum(int remaining) {
    final platform = ImagePickerPlatform.instance;
    final androidPicker =
        !kIsWeb &&
            defaultTargetPlatform == TargetPlatform.android &&
            platform is ImagePickerAndroid
        ? platform
        : null;
    final previousPhotoPicker = androidPicker?.useAndroidPhotoPicker;
    try {
      // The pinned plugin copies this flag into the native request before
      // returning its Future. Restore it immediately so other pickers keep
      // their settings while the parent is choosing homework pages.
      if (androidPicker != null) androidPicker.useAndroidPhotoPicker = true;
      return picker.pickMultiImage(
        maxWidth: 3000,
        maxHeight: 4000,
        imageQuality: 92,
        requestFullMetadata: false,
        limit: remaining,
      );
    } finally {
      if (androidPicker != null) {
        androidPicker.useAndroidPhotoPicker = previousPhotoPicker!;
      }
    }
  }

  // Android can reclaim the activity while the camera/gallery is foreground.
  // Only recover into the same signed-in parent and server-owned draft.
  Future<String?> recover(String childId) async {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) return null;
    final owner = userId();
    final captureKey = _capture;
    final capture = preferences.getString(captureKey);
    final context = jsonMap(jsonDecode(capture ?? '{}'));
    if (context['childId'] != childId) return null;
    final lost = await picker.retrieveLostData();
    if (owner.isEmpty ||
        userId() != owner ||
        preferences.getString(captureKey) != capture) {
      return null;
    }
    if (lost.isEmpty) {
      await preferences.remove(captureKey);
      return null;
    }
    if (lost.exception != null) {
      throw const HomeworkPhotoException('上次选图被系统中断，请重新选择。');
    }
    final id = textValue(context['submissionId']);
    if (id.isEmpty) return null;
    final existing = pending(id);
    await _save(id, [
      ...existing,
      ...(lost.files ?? [])
          .where((f) => !existing.any((e) => e.path == f.path))
          .map(
            (e) => PendingHomeworkPhoto(path: e.path, key: learningRequestId()),
          ),
    ]);
    if (preferences.getString(captureKey) == capture) {
      await preferences.remove(captureKey);
    }
    return id;
  }

  static const maxUploadBytes = 12 * 1024 * 1024;
  static const maxImagePixels = 24000000;
  static const maxPreparedLongSide = 4000;

  Future<HomeworkUploadPhoto> prepare(PendingHomeworkPhoto photo) async =>
      prepareBytes(await XFile(photo.path).readAsBytes());

  // Keep camera JPEGs compressed. The backend applies EXIF orientation and
  // removes metadata; converting a normal JPEG to PNG here can exceed 12 MiB.
  Future<HomeworkUploadPhoto> prepareBytes(
    Uint8List bytes, {
    bool forcePng = false,
  }) async {
    ui.ImmutableBuffer? buffer;
    ui.ImageDescriptor? descriptor;
    try {
      buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
      descriptor = await ui.ImageDescriptor.encoded(buffer);
      final width = descriptor.width, height = descriptor.height;
      final jpeg =
          bytes.length >= 3 &&
          bytes[0] == 0xff &&
          bytes[1] == 0xd8 &&
          bytes[2] == 0xff;
      if (!forcePng &&
          jpeg &&
          bytes.length <= maxUploadBytes &&
          width * height <= maxImagePixels) {
        return HomeworkUploadPhoto(
          bytes: bytes,
          format: HomeworkPhotoFormat.jpeg,
          width: width,
          height: height,
        );
      }

      final longSide = math.max(width, height);
      final shortSide = math.min(width, height);
      var targetLongSide = math.min(longSide, maxPreparedLongSide);
      // Preserve enough detail for normal full-page work. Already-small images
      // are not enlarged; their quality is checked by the existing backend gate.
      final minimumLongSide = shortSide < 640
          ? targetLongSide
          : math.min(
              longSide,
              math.max(1600, (640 * longSide / shortSide).ceil()),
            );
      if (targetLongSide < minimumLongSide) {
        throw const HomeworkPhotoException('图片过长，请分成多张拍摄，保留清晰完整的题目。');
      }
      while (true) {
        final ratio = targetLongSide / longSide;
        final targetWidth = math.max(1, (width * ratio).floor());
        final targetHeight = math.max(1, (height * ratio).floor());
        final codec = await descriptor.instantiateCodec(
          targetWidth: targetWidth,
          targetHeight: targetHeight,
        );
        ui.Image? image;
        try {
          image = (await codec.getNextFrame()).image;
          final result = await image.toByteData(format: ui.ImageByteFormat.png);
          if (result == null) {
            throw const HomeworkPhotoException('无法读取照片，请重新拍摄。');
          }
          final prepared = result.buffer.asUint8List(
            result.offsetInBytes,
            result.lengthInBytes,
          );
          if (prepared.length <= maxUploadBytes) {
            return HomeworkUploadPhoto(
              bytes: prepared,
              format: HomeworkPhotoFormat.png,
              width: image.width,
              height: image.height,
            );
          }
        } finally {
          image?.dispose();
          codec.dispose();
        }
        if (targetLongSide <= minimumLongSide) {
          throw const HomeworkPhotoException('照片细节过多，请分成多张拍摄，避免题目变得不清楚。');
        }
        targetLongSide = math.max(
          minimumLongSide,
          (targetLongSide * 0.85).floor(),
        );
      }
    } on HomeworkPhotoException {
      rethrow;
    } catch (_) {
      throw const HomeworkPhotoException('无法读取照片，请重新选择或拍摄。');
    } finally {
      descriptor?.dispose();
      buffer?.dispose();
    }
  }

  // Compatibility for callers that explicitly need a PNG, not the upload path.
  Future<Uint8List> png(PendingHomeworkPhoto photo) async =>
      (await prepareBytes(
        await XFile(photo.path).readAsBytes(),
        forcePng: true,
      )).bytes;
}
