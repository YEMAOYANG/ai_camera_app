# 家长端 iOS 26 液态玻璃

日期：2026-09-29

## 结论与依据

用户要求真实的 iOS 26 液态玻璃，原先 frosted 材质的白色覆盖过重。
降低覆盖色只能改善透光，不能让 BackdropFilter 获得系统玻璃的折射和边缘光效。
本次将材质依赖替换为固定版本 `fresnel: 0.1.0`，在 iOS 26+ 调用 SwiftUI
`glassEffect`，保留 Flutter 的内容、点击、语义、路由和业务状态。

核对了发布包源码、元数据，并进行了本地原生构建和模拟器验证：

| 方案 | 实现 | 本项目结论 |
| --- | --- | --- |
| frosted_ui_kit 1.1.5 | BackdropFilter 与半透明填充 | 无原生折射，已移除 |
| glassmorphic_ui_kit 1.1.6 | 同类背景模糊与更多现成控件 | 换库本身不能解决效果差异 |
| liquid_glass_renderer 0.2.0-dev.4 | Impeller 折射 shader | 跨平台候选，本次未接入 |
| native_liquid_glass 0.3.1 | 原生 SwiftUI 玻璃 | 实测底部玻璃高度被安全区压缩，未保留 |
| fresnel 0.1.0 | 原生 SwiftUI 玻璃，平台能力检测 | 已接入；底部安全区验证通过 |

`fresnel_ios` 的 UIHostingController 禁用内部安全区，SwiftUI 玻璃视图使用
`ignoresSafeArea`。Flutter 负责唯一一份安全区布局，避免底部材质比按钮区域矮。
它属于早期版本，因此锁定版本，并集中封装在可替换的适配层内。

参考发布页：

- [frosted_ui_kit](https://pub.dev/packages/frosted_ui_kit)
- [glassmorphic_ui_kit](https://pub.dev/packages/glassmorphic_ui_kit)
- [liquid_glass_renderer](https://pub.dev/packages/liquid_glass_renderer)
- [native_liquid_glass](https://pub.dev/packages/native_liquid_glass)
- [fresnel](https://pub.dev/packages/fresnel)
- [fresnel 源码及已知限制](https://github.com/waqaralisiyal23/fresnel)

## 接入范围

- `main.dart`：首帧前完成 iOS / Android 材质能力初始化。
- `app.dart`：统一场景的材质渲染范围。
- `shared/widgets/app_glass_surface.dart`：唯一第三方材质入口。
- `app_tokens.dart`：统一降级材质、导航选中层及轻量阴影参数。
- `app_shell.dart`：iOS 底部导航用原生 `Glass.clear`，移除厚白底；
  加号按用户反馈恢复为黑底白色图标，两端一致。
- `home_habit_hero.dart`：场景图上的二维码入口使用 `Glass.clear`。
- `app_screen.dart`、`app_bottom_sheet.dart`：标题与较大弹层用系统自适应
  `Glass.regular`，保持文字和表单可读。

原生路径不再叠加一块接近不透明的白色面板。已有内容的颜色会透过玻璃，
纯白背景下效果自然更淡；没有为了展示玻璃另加装饰背景。

API 合约、后端、权限、持久化和业务路由保持原语义。不接入库提供的整页模板，
不替换已有表单与按钮的行为。

## 平台、无障碍与构建

- iOS 26+：实际原生 Liquid Glass。
- 旧版 iOS：Flutter 局部模糊及清晰的降级填充。
- Android：小型浮动导航和二维码控件在 Impeller 且 shader 成功加载时使用折射；
  不支持时使用局部轻模糊。标题和大面积弹层使用局部模糊与更强填充，保持可读。
- 高对比、减少动态效果、初始化检测到减少透明度：实底降级。
- 原生视图不接管点击；内容与可访问性仍由 Flutter 提供。
- 原生平台玻璃与 Flutter BackdropFilter 不能混在同一场景。
  适配层统一选择渲染路径，iOS 原生路径关闭所有自定义 BackdropFilter。
  Android 不创建原生玻璃平台视图。
- 继续使用已升级的 Flutter 3.44.9 / Dart 3.12.2。
- Xcode 27 的模拟器部署目标修复保留；Runner 和 Pods 对模拟器 SDK 的下限为 iOS 15。

`fresnel` 及五个配套包均锁定为 0.1.0。试用期间引入的 `native_liquid_glass`、
SVGKit 等依赖已从最终解析结果中移除，原有业务依赖未批量升级。

## 验证记录

本地输出目录：`output/frosted-ui-20260929/`。

- `flutter analyze`：无问题，日志 `fresnel-analyze.log`。
- `flutter test --reporter expanded`：383 项通过，1 项既有按需截图测试跳过，
  日志 `fresnel-full-test.log`。
- `flutter build apk --debug --no-pub --target-platform android-arm64`：通过，
  日志 `fresnel-android-build.log`。
- iPhone 17 Pro / iOS 26.5：原生构建、安装与运行通过。
- `ios-liquid-glass-final-home.png`：最终入口 `lib/main.dart` 的真实首页，
  沿用现有登录状态和开发接口；二维码玻璃按钮、完整底部导航已核对。
  模拟器最终停留在此业务页面，未保留诊断页作为启动入口。
- `fresnel-material-probe.png`：独立材质验证页，确认背景透色，顶部和底部
  62pt 玻璃高度完整。它不是业务页面。
- `fresnel-sheet-probe.png`：同一验证页打开真实公共弹层组件，确认原生玻璃、
  遮罩、圆角与底部安全区的叠层关系。
- 降级路径的点击、最小点击区域、语义关闭、320×568 / 1.3 倍文字 / 260px
  键盘下的保存操作，均包含在通过的测试中。

模拟器截图不能代替实体设备帧率、耗电与视频叠层验收；本轮没有完成这些检查。
Device Hub 窗口自动控制不可用，多页面真实手势操作也未作为本轮通过项。

## Android 真机调整

用户反馈 Android 效果较差，且加号需要恢复黑色。直接检查已连接的
OPPO PECM20 / Android 12 真机后，确认原先的强制实底路径让导航与二维码按钮
丢失通透感。

- 导航改为 60% 白色填充、局部 6px 模糊和轻量折射，非选中图标及文字使用深墨色。
  选中项保留清晰浅色底；最暗背景下未选中标签计算对比度仍达到 4.5:1。
- 加号恢复为近黑色实心圆和白色图标，点击区域仍为 44×44。
- 二维码按钮改为轻透材质，并随首页头部滚动，避免盖住“选教材”。
- 真机发现学习结果 ExpansionTile 的 Material 被正文底板隔开；补上透明
  Material，消除反复出现的绘制断言并恢复点击反馈。
- 通过已有 VM 调试连接热重启、热更新，没有重新安装、清除登录或提交表单。
- 读取实际图形能力：`hasNativeGlass=false`、`hasImpeller=true`，shader 已加载。
- 真机完成首页滚动、加号打开任务弹层、关闭弹层和返回顶部检查。
- 最终 `flutter analyze` 无问题，`flutter test` 383 项通过、1 项原有跳过。

证据保存在 `output/android-glass-20260929/`：`before-home.png`、
`after-home.png`、`after-home-scrolled.png`、`after-task-sheet.png`、
`render-capabilities.json`、`analyze.log`、`tests.log`。
这是实际真机界面与功能检查，未做量化帧率或耗电测试。
