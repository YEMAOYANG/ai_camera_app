# 家长端教材界面改版

本轮范围：首页“教材与课程”、孩子资料中同一模块、教材设置和版本选择面板。保留注册与资料编辑共用的选书流程。

## 设计参考

- [Apple Books 官方展示](https://www.apple.com/apple-books/)：查看实际 App 画面，参考书本作为视觉主体、书籍元信息的层级和轻量内容陈列。
- [Khan Academy Kids Library 官方说明与截图](https://khankids.zendesk.com/hc/en-us/articles/4403657703821-Find-books-and-lessons-in-the-Khan-Kids-Library)：参考学科分类和年级筛选的独立位置。

采用既有暖瞳背景、文字和操作颜色。四科的低饱和书本标识仅用于辨认学科，不是出版社原封面。没有引入第三方图片、远程字体或新依赖。

## 架构与 API

仅修改 Flutter 展示层：

- `textbook_cover.dart`：共享的学科视觉组件。
- `textbook_learning_summary.dart`：首页 / 孩子资料共用书架；正常宽度两列，窄屏或大字号转单列；可由书本或选教材入口进入设置。
- `school_textbooks_page.dart`：学期条、选书列表、折叠帮助、带书本标识的版本面板、学制分段选择和可清除的搜索。
- `parent_learning_observation_sheet.dart`：仅调整首页已有学习表现入口的字体和间距。

沿用 `GET /api/children/{childId}/textbooks`、`PUT .../textbooks/selections` 和 `PUT .../textbooks/context`。没有修改数据结构、服务端权限、路由、课程发布门槛或写入协议。草稿、整批原子保存、修订冲突、丢失响应回读以及不自动重放写请求的行为保留。

首页依据后端 learningStatus 显示已开放 / 已学课程数量；只有实际开放数量大于零时展示进度条。目录未同步或尚未生成课件在家长摘要中统一表述为“课程待上架”，不将目录条目计作可用课程；“完成前序课程后开放”状态仍单独呈现。

## 验证

- `flutter analyze`：无问题。
- `flutter test`：371 通过，1 个可选截图测试默认跳过。
- 390×844 的截图单独开启导出；同时保留既有 320 宽、1.5–2 倍文字、键盘占位、未收录学科、保存冲突与回读检查。
- 全量检查发现英文书本标识在宽字体下会换行溢出，已改为单行按标识宽度适配；修复后的完整检查通过。
- 只更新受本次 UI 改版影响的首页 / 资料页两个现有截图基准，并显式加载图标字体。

预览和日志：`output/parent-textbook-ui-20260928/`，入口为 `preview.html`。使用合成家庭资料与隔离课程状态，版本选择面板使用仓库教材元数据；不是实体手机实拍或生产账号验收。本轮未安装真机、未更改真实家庭的教材选择。
