# 家长端磨砂材质接入

日期：2026-09-29

> 历史记录：用户进一步明确需要 iOS 26 Liquid Glass 后，本方案已被
> [原生液态玻璃方案](2026-09-29-parent-liquid-glass.md) 替代。
> 下文的依赖、材质参数和验证结果仅对应前一版磨砂实现。

## 选型结论

选择 `frosted_ui_kit` 1.1.5 的 `BlurredCard` 作为公共材质基础，通过
`AppFrostedSurface` 接入现有 Flutter 组件。保留暖瞳的导航、权限判断、输入框、
按钮和弹层业务；库自带的邮箱登录和整页模板不接入。

这次核对的是 pub.dev 发布包的源码和元数据，不能把演示图或 README 中的性能
描述当成真机帧率证据。

| 项目 | frosted_ui_kit 1.1.5 | glassmorphic_ui_kit 1.1.6 |
| --- | --- | --- |
| 核心效果 | BackdropFilter 背景模糊与半透明容器 | 同样使用 BackdropFilter |
| Dart 要求 | ^3.12.2 | >=3.0.0 <4.0.0 |
| Android | BlurredCard 默认关闭模糊并加强遮色 | GlassContainer 没有平台自动降级分支 |
| 现成组件 | 导航、分段选择、按钮、弹层、输入等 | 覆盖更多 Material 控件类型 |
| 本项目适配点 | 材质参数、对比度、无障碍、关闭模糊时的裁切 | 同类适配，还需处理部分导航写死的白色前景 |
| 发布日期 | 2026-09-23 | 2025-10-13 |

`glassmorphic_ui_kit` 组件更多、SDK 门槛更低，但不会因此自动获得更好的质感或
性能。暖瞳已有完整组件系统，本次需要的是浮层材质，所以选择更适合这一边界的
`frosted_ui_kit`。两个包都不是调用系统原生 Liquid Glass 的桥接库。

参考：

- [frosted_ui_kit](https://pub.dev/packages/frosted_ui_kit)
- [frosted_ui_kit 源码](https://github.com/abdulrasol/frosted_ui_kit)
- [glassmorphic_ui_kit](https://pub.dev/packages/glassmorphic_ui_kit)
- [glassmorphic_ui_kit 源码](https://github.com/jamalihassan0307/glassmorphic_ui_kit)
- [Flutter SDK 官方归档](https://docs.flutter.dev/install/archive)

## 升级与架构

- Flutter 3.44.1 / Dart 3.12.1 → Flutter 3.44.9 / Dart 3.12.2，使用同一稳定系列的补丁版本。
- `pubspec.yaml` 声明最低工具链要求，`pubspec.lock` 锁定 frosted_ui_kit 1.1.5
  与新增的间接依赖 lottie 3.6.1；原有业务依赖版本保留。
- SDK 原有 `pubspec.lock` 本地改动保留，升级前的版本和差异存于本地验收输出。
- 库只在 `shared/widgets/app_frosted_surface.dart` 导入，页面不直接依赖库控件。
- 后端、API 合约、Riverpod 状态、go_router 路由及服务端权限均保持原语义。

## 视觉和交互范围

使用场景：家长经常在工作、通勤或睡前短暂打开 App，需要快速读清当前状态和
下一步操作。沿用冷白、深墨色和暖色场景图，用少量蓝色表达当前选择。

- 底部导航：一层局部磨砂底座、浅色选中透镜、较短的阴影；提高未选中文字对比度。
- 吸顶栏：统一模糊与遮色，降低标题和辅助说明的字重。
- 公共弹层：轻透的上缘逐渐过渡到高遮盖的正文区，保持表单和确认内容可读。
- 关闭操作：使用标准 IconButton，点击区域至少 44×44，提供提示和键盘焦点。
- 键盘：可用高度按实际屏幕和键盘计算，安全区计入弹层高度。
- 动态效果：弹层沿用 AppMotion；减少动态效果时取消转场并关闭模糊。
- Android、高对比和减少动态效果：使用不透明表面，保持相同组件布局和动作。

玻璃只用于导航和弹层。任务正文、教材、报告、隐私与危险操作继续使用各自清晰的
内容层级。没有把列表逐项包成 BackdropFilter，也没有为展示效果增加装饰背景。

## 验证记录

检查结果和截图保存在 `output/frosted-ui-20260929/`。截图通过现有 Flutter
页面及测试数据渲染，用于材质和布局比较，不代表实体设备、真实账号或真机帧率验收。

最终结果：

- `flutter analyze`：通过，无问题。
- `flutter test`：380 项通过，1 项原有的按需教材截图测试跳过。
- `flutter build apk --debug --no-pub --target-platform android-arm64`：通过，
  产物为 `mobile/build/app/outputs/flutter-apk/app-debug.apk`。
- 390×844 首页、任务、我的、任务弹层：已渲染并核对前后截图。
- 320×568、1.3 倍文字、260px 键盘遮挡：保存可点击且可关闭弹层，无布局异常。
- Android、高对比和减少动态效果：确认关闭 BackdropFilter，保留圆角和点击行为。
- 深色底图下导航标签、吸顶栏辅助文字：计算对比度均达到 4.5:1。
- 弹层关闭按钮：至少 44×44，语义标签包含可执行的点击动作。

回归中发现并修复了关闭图标约定及辅助功能点击语义的问题；核对视觉差异后，
更新了受顶部栏外观影响的一张现有截图基准。此次 SDK 补丁升级没有要求业务 API
迁移，原有依赖 API 的调用通过了分析和全量回归。

验收日志为 `flutter-analyze.log`、`flutter-test.log`、`android-build.log` 和
`visual-check.log`，位于上述本地输出目录。`before/` 和 `after/` 保存界面对照。

## iOS 模拟器补充验收

- 环境：Xcode 27.0、iPhone 17 Pro、iOS 26.5。
- 首次构建遇到 Xcode 27 不接受 iOS 13 模拟器部署目标的问题；在 Runner 和
  Podfile 中增加 `iphonesimulator` 专用的 iOS 15 下限后，原生构建通过。
- `flutter run -d 28DAC603-1144-4514-BDF0-7501750F80D4 --no-pub` 成功安装、
  启动 App 并连接 Dart VM，读取现有开发配置与登录状态，首页实际渲染正常。
- 实际模拟器截图保存为 `output/frosted-ui-20260929/ios-simulator-running.png`。
- 构建配置修复后再次执行 `flutter analyze`，无问题；`flutter test` 383 项通过、
  1 项跳过。对应日志为 `ios-flutter-analyze.log` 和 `ios-flutter-test.log`。
- Device Hub 的自动窗口控制持续超时，因此本轮只确认启动及首页画面，未通过
  模拟器手势完成多页走查。

真机签名构建、滑动帧率、耗电和实时视频上的叠层表现尚未验证。
