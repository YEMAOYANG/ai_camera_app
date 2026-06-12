# Mira Guardian Flutter App

米拉家长端 Flutter 工程，负责设备绑定、孩子档案、任务、实时看护、任务证据、奖励、告警、报告、隐私与家庭成员管理。

## 技术底座

- Flutter 3.41 / Dart 3.11
- `flutter_riverpod`：状态管理与依赖注入
- `go_router`：声明式路由与底部主导航
- `dio`：后端 API 客户端
- Material 3：家长端基础主题

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

安卓真机连同一 Wi-Fi 调试时，用脚本自动把电脑局域网 IP 写入 App：

```sh
cd mobile
scripts/run_android_lan.sh -d <device-id>
```

脚本会生成类似 `http://192.168.x.x:8000/api` 的 `API_BASE_URL`。后端需要先用
`backend/.env` 里的 `APP_HOST=0.0.0.0` 启动，手机才能访问电脑后端。

Web 调试：

```sh
flutter run -d web-server --web-hostname 127.0.0.1 --web-port 5188
```

## 验证

```sh
flutter analyze
flutter test
```
