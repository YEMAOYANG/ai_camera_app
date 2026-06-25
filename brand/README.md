# 暖瞳 / WarmSight Brand Assets

本目录保存暖瞳正式 Logo 文件包、视觉系统规范和 Flutter App 接入准备资产。当前资产来自已确认的正式包：
`/Users/sqcopenclaw/Downloads/WarmSight_Exact_Artwork_Package_v2/`。

本目录不再存放旧 Logo 候选、探索图或 moodboard。

## Brand

- 中文名：暖瞳
- English name：WarmSight
- 产品全称：暖瞳 AI 成长陪伴摄像头
- Slogan：陪在成长的每一天
- 定位：为幼儿园孩子家庭设计的 AI 成长陪伴摄像头，帮助家长温柔看见孩子的作息、习惯和需要。

## Directory

- `brand-guidelines.md`：品牌基础、Logo 使用、色彩、字体、图标、插画、动效和 Flutter 接入建议。
- `logo/source/`：Downloads 包中的原始 1254px 附件。
- `logo/png/`：透明底、米白底 1024px PNG。
- `logo/app-icon/`：米白底 App icon 尺寸。
- `logo/proof/`：SHA256、精确性说明、来源证明和 PDF 规范。
- `visual-system/`：App 视觉系统延展文档和预览图。

`logo/app-icon/` 的尺寸图从正式包内 `01_PNG_CreamBG_1024/WarmSight_01_Icon_1024.png` 衍生。原因是正式包中 `04_Icon_Sizes/WarmSight_Icon_CreamBG_1024.png` 在 Pillow 中读取为截断文件；本处理不重画 Logo，只保证 repo 内 PNG 可被工具链稳定读取。

## App Assets

Flutter 可引用的核心资产已同步到：

- `mobile/assets/brand/nuantong-logo-mark.png`
- `mobile/assets/brand/nuantong-logo-horizontal.png`
- `mobile/assets/brand/nuantong-logo-vertical.png`
- `mobile/assets/brand/nuantong-app-icon-1024.png`

本轮没有替换 Android / iOS 平台图标。后续确认后再使用 `flutter_launcher_icons` 生成平台图标。

## Notes

- 不要把新 Logo 候选放回 `brand/logo/`。
- 不要覆盖 Downloads 中的源包。
- 不要直接编辑正式 PNG 源文件；如需衍生尺寸，放入清晰的新目录并记录来源。
- App icon 源图使用不透明米白底 PNG，适合后续 iOS / Android 平台图标生成。
