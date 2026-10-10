import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:image_picker_android/image_picker_android.dart';
import 'package:image_picker_platform_interface/image_picker_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:warm_sight/src/features/homework/application/homework_photo_picker.dart';

class _AlbumPlatform extends ImagePickerAndroid {
  Future<List<XFile>> Function() selection = () async => [];
  int multiOpens = 0, singleOpens = 0;
  int? selectionLimit;
  bool systemPickerAtOpen = false;

  @override
  Future<List<XFile>> getMultiImageWithOptions({
    MultiImagePickerOptions options = const MultiImagePickerOptions(),
  }) async {
    multiOpens++;
    selectionLimit = options.limit;
    systemPickerAtOpen = useAndroidPhotoPicker;
    return selection();
  }

  @override
  Future<XFile?> getImageFromSource({
    required ImageSource source,
    ImagePickerOptions options = const ImagePickerOptions(),
  }) async {
    expect(source, ImageSource.gallery);
    singleOpens++;
    systemPickerAtOpen = useAndroidPhotoPicker;
    final files = await selection();
    return files.isEmpty ? null : files.single;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late _AlbumPlatform album;
  late HomeworkPhotoPicker picker;
  late SharedPreferences preferences;

  setUp(() async {
    final originalPlatform = ImagePickerPlatform.instance;
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    album = _AlbumPlatform();
    ImagePickerPlatform.instance = album;
    addTearDown(() {
      ImagePickerPlatform.instance = originalPlatform;
      debugDefaultTargetPlatformOverride = null;
    });
    SharedPreferences.setMockInitialValues({});
    preferences = await SharedPreferences.getInstance();
    picker = HomeworkPhotoPicker(ImagePicker(), preferences, () => 'parent');
  });

  test(
    'one album selection saves the whole ordered batch for upload',
    () async {
      album.selection = () async => [XFile('page-a.jpg'), XFile('page-b.jpg')];

      await picker.pick('hw', 'child', camera: false, remaining: 4);

      expect(album.multiOpens, 1);
      expect(album.selectionLimit, 4);
      expect(album.systemPickerAtOpen, isTrue);
      expect(album.useAndroidPhotoPicker, isFalse);
      expect(picker.pending('hw').map((photo) => photo.path), [
        'page-a.jpg',
        'page-b.jpg',
      ]);
      expect(picker.pending('hw').map((photo) => photo.key).toSet().length, 2);
      expect(preferences.getString('homework.capture.parent'), isNull);

      // Reopening the app retains both selected pages and their retry keys.
      final reopened = HomeworkPhotoPicker(
        ImagePicker(),
        preferences,
        () => 'parent',
      );
      expect(
        reopened.pending('hw').map((photo) => photo.json),
        picker.pending('hw').map((photo) => photo.json),
      );
    },
  );

  test(
    'the final remaining page uses the single-image gallery contract',
    () async {
      album.selection = () async => [XFile('last-page.jpg')];

      await picker.pick('hw', 'child', camera: false, remaining: 1);

      expect(album.singleOpens, 1);
      expect(album.multiOpens, 0);
      expect(album.systemPickerAtOpen, isTrue);
      expect(picker.pending('hw').single.path, 'last-page.jpg');
    },
  );

  test(
    'an open homework album does not change other picker settings',
    () async {
      final opened = Completer<void>();
      final selected = Completer<List<XFile>>();
      album.selection = () {
        opened.complete();
        return selected.future;
      };

      final operation = picker.pick(
        'hw',
        'child',
        camera: false,
        remaining: 10,
      );
      await opened.future;

      expect(album.systemPickerAtOpen, isTrue);
      expect(album.useAndroidPhotoPicker, isFalse);
      selected.complete([XFile('page-a.jpg'), XFile('page-b.jpg')]);
      await operation;
      expect(picker.pending('hw'), hasLength(2));
    },
  );

  test(
    'cancelling the album leaves no pending photos or capture marker',
    () async {
      await picker.pick('hw', 'child', camera: false, remaining: 10);

      expect(picker.pending('hw'), isEmpty);
      expect(preferences.getString('homework.capture.parent'), isNull);
      expect(album.useAndroidPhotoPicker, isFalse);
    },
  );

  test(
    'a fallback returning too many pages never silently drops photos',
    () async {
      album.selection = () async => [
        XFile('a.jpg'),
        XFile('b.jpg'),
        XFile('c.jpg'),
      ];

      await expectLater(
        picker.pick('hw', 'child', camera: false, remaining: 2),
        throwsA(isA<HomeworkPhotoException>()),
      );

      expect(picker.pending('hw'), isEmpty);
      expect(preferences.getString('homework.capture.parent'), isNull);
      expect(album.useAndroidPhotoPicker, isFalse);
    },
  );

  test('a picker error restores the previous platform setting', () async {
    album.useAndroidPhotoPicker = true;
    album.selection = () async =>
        throw PlatformException(code: 'picker_failed');

    await expectLater(
      picker.pick('hw', 'child', camera: false, remaining: 10),
      throwsA(isA<HomeworkPhotoException>()),
    );

    expect(picker.pending('hw'), isEmpty);
    expect(preferences.getString('homework.capture.parent'), isNull);
    expect(album.useAndroidPhotoPicker, isTrue);
  });
}
