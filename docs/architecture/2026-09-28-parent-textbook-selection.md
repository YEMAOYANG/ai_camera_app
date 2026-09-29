# 家长三科教材选择

注册仍先完成家长身份、孩子昵称与年级。小学孩子保存资料后进入可跳过的教材选择；幼儿园直接进入首页。注册后的选书与“我的 → 孩子资料 → 学校教材”共用同一页面和同一保存规则。昵称、学段和年级编辑也共用组件。

## 架构与文件

- Flutter `shared/widgets/child_learning_identity_fields.dart`：注册和资料编辑共用的学习身份字段。
- Flutter `features/learning/presentation/school_textbooks_page.dart`：学年学期、三科总览、版本选择、草稿和一次保存；注册模式提供稍后设置。
- Flutter 教材 model/repository、setup/profile/router：真实接口及两处入口。
- Python `textbook_learning_service.py`、`student_textbooks.py`：多科原子确认，保留旧单科接口。
- `content/textbooks/`：仅加入有真实官方来源的版本索引，目录与课程未就绪时如实标记。

复用现有教材、选择和选择历史表，不执行结构迁移；不改变学生开课的精确版本、年级、发布及媒体门禁。选书只保存选择，不生成或发布课程。

## API

既有 `GET /api/children/{childId}/textbooks` 返回当前年级教材，前端按本学期、学科和学制组织。

新增 `PUT /api/children/{childId}/textbooks/selections`：

```json
{
  "schoolYearStartYear": 2026,
  "semester": "upper",
  "selections": [
    {"editionId": "...", "alignmentRevisionId": "...", "expectedSelectionRevision": 0}
  ]
}
```

`selections` 为 1—3 科，每科只能出现一次；每项可选 `currentNodeId`。同一事务中校验家庭权限、孩子已确认年级、当前学期、教材年级/册次和各科选择修订号，写入选择及历史。任一项冲突则全部回滚。返回 `ok` 及每科的 `subject`、`editionId`、`alignmentRevisionId`、`selectionRevision`。

失败保留家长草稿，读取服务端现状供核对，不自动重放写请求。已确认的版本不因目录出现新修订而自动切换。未收录的版本不可伪装为可选教材；未开课不影响已有真实教材索引的选择。

## 目录与验收结果

- 新增 `content/textbooks/math-english-v1/` 的 65 册官方版本索引：数学 36 册，英语 29 册；具体年级、系列、缺口与导入命令见该目录 README。数学覆盖六年制一至六年级；本批英语覆盖三至六年级的部分常见系列，不能代表全国全版本。
- 已导入本机 `127.0.0.1:3306/ai_camera_app_dev`，原语文 24 个修订保持不变。导入结果逐条回读一致，未修改任何孩子选择、表结构，也未生成或发布课程。书目导入前快照及结果保存在 `output/parent-textbook-20260928/`。
- 通过现有托管脚本的进程身份、目录和端口校验，仅重启本机后端。健康检查成功；新增保存路由对格式正确但未登录的请求返回 401。
- `flutter analyze`：无问题。
- `flutter test`：465 项通过，1 项按需视觉导出测试默认跳过；视觉导出另行开启验证通过。
- 后端教材及批量选择测试：28 项通过，包括最后一科冲突时整批与审计记录回滚、跨家庭与查看者拦截、单科更新保留其他科，以及 HTTP 合约。
- Flutter 390×844 实际组件渲染已检查：首次资料填写、资料编辑、教材总览、数学和英语版本面板、三科待保存。320 宽与 1.5 倍文字交互验证无溢出。测试资料仅用于渲染和隔离测试，不是真实家庭记录；未做真机安装验收。
- 已有注册/资料页面冒烟测试随新流程更新；仅更新受资料布局影响的 `learning_preparation_profile_failed.png` 基准，首页基准未改动。

视觉复核命令：

```sh
cd mobile
flutter test --dart-define=MIRA_TEXTBOOK_VISUAL_QA=true test/school_textbooks_page_test.dart test/profile_child_preparation_test.dart
```

输出位于 `output/parent-textbook-20260928/`。失败会保留选择并等待家长明确再次保存；若读回证实保存已成功，则显示已确认状态，注册场景正常进入首页。


## 2026-09-28 第二轮：紧凑资料表单与官方目录复核

用户选择 Product Design 第二张设计图：紧凑的分组资料表，行内称呼、学段切换与可展开的三列年级选项。首次填写和“我的→孩子资料”继续共用 `ChildLearningIdentityFields`；删除装饰步骤线与重复年级大卡片。注册仍为资料→可跳过教材，幼儿园直接完成；编辑保留所有现有后台准备状态和学生入口。昵称/年级缺失、保存中、无管理权限、保存失败保留输入等状态不变。

教材页使用同样紧凑的列表层级；版本多时支持按版本、出版社、主编搜索；六年制与五四学制分别筛选，并优先打开已选书对应的学制。三科独立暂存，统一原子保存；失败回读、不自动重放写入的契约不变。没有新增 API、定位权限、表结构或课程生成动作。

### 官方复核结论

原有数学、英语 65 册的资源编号及身份字段与官方可见目录相符，问题是漏收。新增 216 册后共 281 册：六年制数学 83、英语 172；五四数学 17、英语 9。数学版本分别 7/2 个，英语分别 23/2 个。保留主编系列与官方实际展示册次，不猜测新旧版、起点及 PEP/精通等别名。书目索引不等同于课程可学。

逐册出处见 `backend/content/textbooks/sources/smartedu-math-english-20260928.json`；范围和导入见 `math-english-v2/README.md`。可见目录是本轮证据；详情页仅抽样打开，未逐册阅读正文。当前开发库新增导入 216 册并回读一致，既有修订和孩子选择保留。


第二轮验证：`flutter analyze` 无问题；`flutter test` 467 通过、1 个可选截图测试默认跳过（已单独运行通过）；教材/表单定向 32 项通过；后端 29 项通过。视觉 QA 见 `mobile/design-qa.md`，截图为 Flutter 引擎渲染，不是手机实拍。未安装真机 App、未生成或发布课程。

## 2026-09-28 第三轮：紧凑资料、统一学期和固定课程状态

孩子资料采用行式布局：已有学段、年级默认收起，编辑时展开；字段 15px、导航标题 17px，三科状态统一为“教材与课程”，移除旧的备课百分比。注册和编辑继续共用组件；学生空间登录权限与课程是否上架分别判断。

### 架构及 API

后端负责有效学年和学期，默认按 Asia/Shanghai：9—1 月上学期，2—8 月下学期。日期是建议，家长可以按学校实际进度调整。覆盖值复用 `app_settings` 的家庭/孩子范围键保存，在家庭及孩子锁内检查修订号；跨学年或年级修订变化后失效。切换保留原学期教材选择及学习记录，不自动升年级，不执行表结构迁移。

`GET /api/children/{childId}/textbooks` 与学生目录增加 `termSource`、`suggestedSemester`、`contextRevision`、`gradeRevision`、三科 `subjects[].status`；已选择教材增加 `learningStatus`，包含实际可用课程数与已完成课程数。来源使用学生目录同一发布校验，完成记录按家庭、孩子和精确课程版本统计；书目索引数量不计作已发布课程。

`PUT /api/children/{childId}/textbooks/context`：

```json
{
  "schoolYearStartYear": 2026,
  "semester": "lower",
  "expectedContextRevision": 0,
  "expectedGradeRevision": 1
}
```

`semester` 支持 `upper`、`lower` 或 `null`（恢复日期默认）；需要管理孩子资料权限，拒绝跨家庭、过期学年、年级和修订号。多科批量保存另携带 `expectedContextRevision`，阻止旧选书页面覆盖新学期设置。丢失响应时只回读确认，不自动重放写入。

两个客户端和两条课堂入口均读取这一学期设置。学生端窗口重新获得焦点时刷新目录；家长端首页手动/生命周期刷新读取当前教材状态。

### 一、二年级英语的证据约束

用户确认一年级起保留英语入口，并要求先查官方依据。尚未确定学校版本的家长可以稍后设置；没有默认北京版，也没有自动建立自主启蒙路径。只加入有具体年级和册次依据的书目：北京出版社目录对应一、二年级上下册 4 条，上海市教委 2026 秋季目录对应一、二年级上册 2 条。人教社资料目前作为系列证据，未擅自合并旧一年级起点和新版 PEP 预备级。

详细来源、时间和限制见 [低年级英语官方核对](2026-09-28-low-grade-english-authority.md)。新增 6 条仅为 `index_only`、审核待完成，无课文和课程；已导入本机开发库并逐条回读，导入前后孩子选择指纹一致，未生成或发布课程。

### 本轮验收

Flutter 静态检查无问题；完整测试 371 通过、1 个可选截图测试默认跳过，截图流程另行运行 35 通过。后端隔离测试 51 通过。学生端 lint、typecheck、250 项测试及隔离源码副本生产构建通过。

本机后端按托管身份校验重载后健康接口 200，新学期路由未登录请求返回 401。Student Web 既有运行进程身份记录异常，未替换该进程；未做真机安装或真实家庭写入验收。当前视觉与交互证据见 `mobile/design-qa.md`。
