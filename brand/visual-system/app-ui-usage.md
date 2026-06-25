# 暖瞳 App UI 使用建议

## 页面气质

App 是家长端日常工具，不是营销页，也不是后台控制台。界面应安静、可信、温暖，优先服务“今天发生了什么、孩子需要什么、家长下一步做什么”。

## 推荐使用

- 背景使用暖米白或轻米白。
- 重要操作使用暖瞳墨蓝。
- 成功、开启、成长相关状态使用嫩芽绿。
- 重点提醒或需要关注的小点使用暖金。
- 卡片边界使用柔雾灰，避免堆叠太多白卡。

## Logo 使用

- 启动页可以使用竖版或标准图标。
- App 内导航和工具栏优先使用标准图标或文字标，不使用完整传播组合。
- 关于页、品牌页、帮助页可以使用横版或竖版组合。
- 空状态不重复堆叠 Logo，使用插画风格延展品牌。

## 后续平台图标

后续确认后可使用 `flutter_launcher_icons`：

```yaml
flutter_launcher_icons:
  android: true
  ios: true
  image_path: assets/brand/nuantong-app-icon-1024.png
  adaptive_icon_background: "#FFF7EA"
  adaptive_icon_foreground: assets/brand/nuantong-app-icon-1024.png
```

执行命令：

```sh
cd /Users/sqcopenclaw/Desktop/ai_camera_app/mobile
dart run flutter_launcher_icons
```

本轮不执行该命令，不覆盖现有平台图标。
