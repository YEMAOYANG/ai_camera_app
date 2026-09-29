# 暖瞳 Flutter App

暖瞳家长端 Flutter 工程，负责设备绑定、孩子档案、任务、实时看护、任务证据、奖励、告警、报告、隐私与家庭成员管理。

## 技术底座

- Flutter 3.44.9 / Dart 3.12.2（当前验证版本）
- `flutter_riverpod`：状态管理与依赖注入
- `go_router`：声明式路由与底部主导航
- `dio`：后端 API 客户端
- Material 3：家长端基础主题
- `fresnel` 0.1.0：iOS 26+ 使用系统原生 Liquid Glass，统一通过
  `AppGlassSurface` 适配；Android 的小型浮动控件按图形能力使用折射或轻模糊，
  减少透明度、高对比和减少动态效果使用实底降级。

Flutter SDK 至少需要 3.44.9，Dart 至少需要 3.12.2。升级 SDK 后运行
`flutter pub get`，提交更新后的 `pubspec.lock`。玻璃组件的选型和验收范围见
[液态玻璃接入记录](../docs/design/2026-09-29-parent-liquid-glass.md)。

## 目录

```text
lib/
  main.dart
  src/
    app/              # App、路由、Shell
    core/             # 环境、网络、主题
    features/         # home/tasks/live_care/alerts/profile
    shared/           # 通用 UI 组件
```

## 运行

```sh
cd mobile
flutter pub get
flutter run
```

iOS 模拟器：先在 Xcode 的 Device Hub（Xcode 27）中启动设备，再运行
`flutter devices` 查找设备 ID，并执行 `flutter run -d <device-id> --no-pub`。
Runner 和 Pods 对 `iphonesimulator` SDK 使用至少 iOS 15 的部署目标，以满足
Xcode 27 的构建要求；此设置仅针对模拟器。

环境配置在 `mobile/.env.development` 和 `mobile/.env.product`。开发环境默认使用当前
局域网后端地址。`.env.product` 里是不可发布的占位域名：生产构建前必须替换
为真实的 API、实时服务和学生 Web 域名。production 会在启动时强制 API/学生 Web
使用 HTTPS、WebSocket 使用 WSS；明文 `http://` 或 `ws://` 配置会被拒绝。
移动端不会在 Dart 代码里写死 API 地址；debug 构建默认读取 `.env.development`，
release 构建默认读取 `.env.product`。如果需要显式覆盖，也可以继续通过 dart define
指定配置文件：

```sh
flutter run --dart-define-from-file=.env.development
```

```sh
flutter build apk --dart-define-from-file=.env.product
```

安卓 USB 真机调试时，脚本只负责建立 `adb reverse` 并读取 `.env.development`。
如果要走 USB 转发，请把 `.env.development` 里的地址配置为 `127.0.0.1`：

```sh
cd mobile
scripts/run_android_usb.sh -d <device-id>
```

安卓真机连同一 Wi-Fi、但不走 USB 转发时，把电脑局域网地址写在 `.env.development`
里，然后用脚本启动：

```sh
cd mobile
scripts/run_android_lan.sh -d <device-id>
```

后端需要先用 `backend/.env` 里的 `APP_HOST=0.0.0.0` 启动，手机才能访问电脑后端。

Web 调试：

```sh
flutter run -d web-server --web-hostname 127.0.0.1 --web-port 5188
```

## 验证

```sh
flutter analyze
flutter test
```
