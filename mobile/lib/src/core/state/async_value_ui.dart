import 'package:flutter_riverpod/flutter_riverpod.dart';

/// 仅首次加载（尚无缓存）时为 true；后台 refresh/reload 时为 false。
bool isInitialAsyncLoad<T>(AsyncValue<T> value) =>
    !value.hasValue && value.isLoading;

bool isBackgroundAsyncRefresh<T>(AsyncValue<T> value) =>
    value.isRefreshing || value.isReloading;

/// 有缓存时静默 refresh，失败保留旧数据。
Future<void> silentRefreshProvider(dynamic ref, Object provider) async {
  try {
    final value = ref.refresh(provider);
    if (value is Future) {
      await value;
    }
  } catch (_) {}
}
