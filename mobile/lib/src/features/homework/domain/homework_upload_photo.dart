import 'dart:typed_data';

enum HomeworkPhotoFormat { jpeg, png }

class HomeworkUploadPhoto {
  const HomeworkUploadPhoto({
    required this.bytes,
    required this.format,
    required this.width,
    required this.height,
  });

  final Uint8List bytes;
  final HomeworkPhotoFormat format;
  final int width, height;
}
