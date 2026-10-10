import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/homework/application/homework_photo_picker.dart';
import 'package:warm_sight/src/features/homework/application/homework_repository.dart';
import 'package:warm_sight/src/features/homework/domain/homework_models.dart';
import 'package:warm_sight/src/features/homework/domain/homework_upload_photo.dart';

Future<Uint8List> png(int width, int height, {bool noise = false}) async {
  final pixels = Uint8List(width * height * 4);
  var random = 0x123456;
  for (var offset = 0; offset < pixels.length; offset += 4) {
    random = (random * 1664525 + 1013904223) & 0xffffffff;
    pixels[offset] = noise ? (random >> 24) & 0xff : 240;
    pixels[offset + 1] = noise ? (random >> 16) & 0xff : 237;
    pixels[offset + 2] = noise ? (random >> 8) & 0xff : 211;
    pixels[offset + 3] = 255;
  }
  final decoded = Completer<ui.Image>();
  ui.decodeImageFromPixels(
    pixels,
    width,
    height,
    ui.PixelFormat.rgba8888,
    decoded.complete,
  );
  final image = await decoded.future;
  try {
    final data = (await image.toByteData(format: ui.ImageByteFormat.png))!;
    return data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
  } finally {
    image.dispose();
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late HomeworkPhotoPicker picker;
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    picker = HomeworkPhotoPicker(
      ImagePicker(),
      await SharedPreferences.getInstance(),
      () => 'parent',
    );
  });

  test('camera JPEG remains JPEG with identical compressed bytes', () async {
    final original = await File(
      'test/fixtures/homework_camera.jpg',
    ).readAsBytes();
    final photo = await picker.prepareBytes(original);
    expect(photo.bytes, same(original));
    expect(photo.format, HomeworkPhotoFormat.jpeg);
    expect((photo.width, photo.height), (960, 1280));
  });

  test(
    'oversized noisy PNG is reduced into budget with readable dimensions',
    () async {
      final original = await png(2200, 2200, noise: true);
      expect(original.length, greaterThan(HomeworkPhotoPicker.maxUploadBytes));
      final photo = await picker.prepareBytes(original);
      expect(photo.format, HomeworkPhotoFormat.png);
      expect(
        photo.bytes.length,
        lessThanOrEqualTo(HomeworkPhotoPicker.maxUploadBytes),
      );
      expect(photo.width, inInclusiveRange(1600, 2199));
      expect(photo.height, photo.width);
      expect(photo.bytes.take(8), [137, 80, 78, 71, 13, 10, 26, 10]);
    },
  );

  for (final dimensions in [(1600, 6000), (6000, 1600)]) {
    test('both orientations bound longest side: $dimensions', () async {
      final photo = await picker.prepareBytes(
        await png(dimensions.$1, dimensions.$2),
      );
      expect(photo.width, lessThanOrEqualTo(4000));
      expect(photo.height, lessThanOrEqualTo(4000));
      expect(photo.width, greaterThanOrEqualTo(640));
      expect(photo.height, greaterThanOrEqualTo(640));
      expect(
        photo.width / photo.height,
        closeTo(dimensions.$1 / dimensions.$2, 0.004),
      );
    });
  }

  test(
    'small image is not enlarged and remains for backend quality check',
    () async {
      final photo = await picker.prepareBytes(await png(32, 48));
      expect((photo.width, photo.height), (32, 48));
    },
  );

  test(
    'unreadable panoramic downsize fails instead of silently discarding it',
    () async {
      await expectLater(
        picker.prepareBytes(await png(640, 6000)),
        throwsA(isA<HomeworkPhotoException>()),
      );
    },
  );

  test(
    'invalid JPEG signature is not uploaded with a false JPEG type',
    () async {
      await expectLater(
        picker.prepareBytes(Uint8List.fromList([255, 216, 255, 0])),
        throwsA(isA<HomeworkPhotoException>()),
      );
    },
  );

  test('explicit PNG compatibility method still returns encoded PNG', () async {
    final bytes = await picker.png(
      const PendingHomeworkPhoto(
        path: 'test/fixtures/homework_camera.jpg',
        key: 'compat',
      ),
    );
    expect(bytes.take(8), [137, 80, 78, 71, 13, 10, 26, 10]);
  });

  test('prepared JPEG multipart uses correct MIME and extension', () async {
    final dio = Dio();
    FormData? posted;
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (request, handler) {
          posted = request.data as FormData;
          handler.resolve(
            Response(
              requestOptions: request,
              data: {
                'submission': {'id': 'hw', 'revision': 2},
              },
            ),
          );
        },
      ),
    );
    final photo = await picker.prepareBytes(
      await File('test/fixtures/homework_camera.jpg').readAsBytes(),
    );
    await HomeworkRepository(ApiClient(dio)).upload(
      HomeworkSubmission({'id': 'hw', 'revision': 1}),
      bytes: photo.bytes,
      format: photo.format,
      idempotencyKey: 'stable',
    );
    expect(posted!.files.single.value.filename, 'homework.jpg');
    expect(posted!.files.single.value.contentType.toString(), 'image/jpeg');
    expect(posted!.files.single.value.length, photo.bytes.length);
    expect(Map.fromEntries(posted!.fields)['idempotencyKey'], 'stable');
  });
}
