# 教材同步原创教学与 OpenMAIC 接入评估

后续进展：2026-09-24 已将增量教材表应用到本机开发库，接入独立的第一课审核预览。见 [第一课与数据库落地记录](2026-09-24-textbook-first-course-preview.md)。以下保留第一阶段的实现与验证边界。

日期：2026-09-23。分支：`codex/fixed-textbook`。状态：已实现第一阶段的教材元数据导入、家长选书、学生固定目录、原创任务书冻结与发布绑定接口。**OpenMAIC 正式生产链路尚未适配教材合同，当前不能从这些目录生成并播放正式教材课。** 未迁移现有业务数据库，未导入教材正文或付费生成课程。

教学原则：目录、单元和教学范围与教材对应，讲解、例题、练习和视觉表达独立创作。目录就绪、教学目标核验、课件完成与可上课是不同状态。

## 1. 结论与本次核验

建议采用“教材同步、教学原创”。教材版本确定对应单元、课次、进度和知识范围；OpenMAIC 根据核验后的教学目标独立制作讲解、例题、练习和互动；Mira 后端负责版本、发布、共享复用、学生身份和学习记录。完整目录对应与内容使用分别评估，不能以“AI 改写”作为版权安全依据。

### GitHub 项目实际提供什么

检查对象：[pengboyjak/textbook-library](https://github.com/pengboyjak/textbook-library)，检查时 master 指向 `46bcffbdd527a3edb2762bcaa242cd7871b91383`。

直接读取并解析 `references/catalog.json`，未执行第三方脚本：

| 检查项 | 实际结果 |
| --- | --- |
| 数据生成时间 | 2026-06-15T15:29:26.676Z |
| 记录数 / 不同资源 ID 数 | 2637 / 2637 |
| 普通小学分类总数 | 282 |
| 普通小学语文 / 数学 / 英语 | 0 / 18 / 80 |
| 普通小学数学版本 | 人教版仅六个年级下册；西南大学版十二册 |
| 普通小学记录的章节 ID | 全部为空 |
| 教材正文、图片、页码映射、出版版次和 ISBN 专用字段 | 未提供 |
| 地区或学校采用教材的映射 | 未提供 |

记录包含 `id`、`title`、`tag_paths`、`resource_type`、`chapter_ids`、`chapter_paths`、`ti_items_count`。2637 是索引记录数量，其中有教师用书、课件等资源，不能解释为已经核验完整的 2637 本学生教材。另有 624 条归在“其他”。

查询脚本读取本地 JSON，并构造官方详情链接，没有直接提供教材内容服务。贡献说明提到的 `smartedu_scraper.js` 和 `build_catalog.js` 没有出现在本次读取的完整 Git 文件树中，不能假定仓库开箱即可持续同步。

结论：可作为待核验的初始索引；不能作为全国教材、当前学期版本、章节内容或福建学校选用版本的唯一依据。

来源：[实际目录数据](https://github.com/pengboyjak/textbook-library/blob/46bcffbdd527a3edb2762bcaa242cd7871b91383/references/catalog.json)、[查询脚本](https://github.com/pengboyjak/textbook-library/blob/46bcffbdd527a3edb2762bcaa242cd7871b91383/scripts/lookup.py)、[贡献说明](https://github.com/pengboyjak/textbook-library/blob/46bcffbdd527a3edb2762bcaa242cd7871b91383/CONTRIBUTING.md)。

### 官方网站实测

使用用户授权的账号，在用户完成滑块验证后成功登录；未将账号、密码或会话凭证写入项目。

检查了[小学语文一年级上册](https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId=1c73b348-e8b6-47d6-84b0-6dbacbe28268&catalogType=tchMaterial&subCatalog=tchMaterial)：页面注明根据 2022 年版课程标准修订、人民教育出版社；PDF 阅读器显示 118 页，具有章节大纲和正文文本层。

实际点击“天地人”后，阅读器跳到 PDF 第 13 页，书面印刷页码为 8。第一单元为识字，第二单元为汉语拼音。这个资源 ID 不在上述 GitHub 快照中。这同时证明：目录存在缺口、PDF 页码与书面页码必须分别保存、现有自编课程顺序不能直接充当教材目录。

书内有仅限个人学习、其他用途需授权的提示。[GitHub LICENSE](https://github.com/pengboyjak/textbook-library/blob/46bcffbdd527a3edb2762bcaa242cd7871b91383/LICENSE) 也明确说明项目不含教材正文，教材版权属于原出版社。此次登录阅读不能据此认定取得了产品展示、批量复制、向模型提交材料及课件分发所需的权限；按实际授权范围记录可用能力。

另按平台的“语文 → 统编版”逐年级核对六年制一至六年级上下册 12 册、五四学制一至五年级上下册 10 册，逐册打开官方详情页核验标题及资源编号。共 22 册，均为人民教育出版社；一至三年级上下册及四至六年级上册标注根据 2022 年版课程标准修订，其他已查下册未标注这一修订，不能猜定其出版年份或版次。对应资源链接逐册保存在 `backend/content/textbooks/*.json`。这里的“全国”指上述普通小学两种学制的语文官方书目范围，不含特殊教育、历史版次与地方教材，也不证明每所学校已经换用同一修订。

本次仅对其中一本验证目录、正文和章节跳转，尚未核验 22 册的完整目录与逐课目标，没有验证全部教材的下载能力、官方第三方接入 API 或跨站嵌入许可。官方页面可用于核验来源；不能把阅读器中的临时资源地址当成生产内容接口。

## 2. “目录同步、教学原创”的验收定义

| 内容 | 实现与验收方式 |
| --- | --- |
| 教材版本、单元、课名、顺序 | 建立准确对应关系，教师核对；目录标题和编排的具体使用依据单独核查，不默认全部不受保护 |
| 教学范围、知识点、难度、先修能力 | 与该课目标相符，知识正确、范围完整、不超纲；通用公式、术语和知识事实不为追求字面差异而改错 |
| 讲解、例题、练习、情境 | 根据知识目标独立创作，使用自己的问题、叙述和组织方式；不逐句改写课文、不将原题换数字后冒充原创 |
| 插图、动画、板书和音频 | 原创或按许可使用，独立设计；不描摹教材插图、不复刻版式、不默认将课文全文转为 TTS 发布 |
| 课文、教材原题等原始作品 | 默认不收录或分发；确有教学需要时按有效许可、公版依据或经核查的适当引用范围使用并记录来源 |
| 范围不清、材料权限未确认 | 不能猜写或伪装成教材同步课；状态可停留在待核验，不影响已核验课程 |

首批课程同时审核教学对齐和原创表达。相似度工具只作排查线索，不设“低于某个百分比就合法”的判定；AI 自称原创也不作为通过依据。

### 版权依据与适用边界

- 最高人民法院指导案例 81 号区分思想、公共素材与具有独创性的表达。由此制定本项目的创作策略：知识目标可以相同，具体教学表达独立完成；不能据此推断特定课文、题目或整套编排当然可以复制。[指导案例 81 号](https://www.court.gov.cn/shenpan/xiangqing/37642.html)
- 《著作权法》第十三条和第十五条分别涉及改编作品、具有独创性选择或编排的汇编作品。字面不同、标注来源或使用 AI 并不能自动解决原作品权利。第二十四条对引用和学校课堂教学有适用条件，商业 App 不能仅凭“用于教育”认定属于例外。[著作权法](https://www.ncac.gov.cn/xxfb/flfg/flfg_532/202103/t20210309_50530.html)
- 国家版权局 2003 年关于习题集类教辅的意见既指出独创性教材编排可能受保护，也专门说明义务教育配套教辅需具体分析，未再现教材内容的情形可不侵害教材著作权。不能只引用其中一部分，把所有教材目录都视为禁用或一概自由使用。该历史意见面向教辅图书，不能直接充当本 App 的法律结论。[完整意见](https://www.ncac.gov.cn/xxfb/tzgg/200312/t20031229_50191.html)

对于按整套教材目录商业上线的产品，应由版权专业人士结合具体教材、页面、生成材料输入和输出确认使用依据，必要时取得许可。系统保留对应结构和审核记录，不擅自改变用户要求的教学顺序来掩盖未解决的权利问题。

### 分学科实现

- 数学：围绕同一概念和能力目标另写情境、解题说明、例题和练习；独立验证答案与难度。
- 英语：保留应学词汇、语法和交际目标，另写对话、故事、角色和配图；不复刻教材情节或录音。
- 语文：围绕对应课文的字词、阅读方法和表达能力制作原创导读与训练。需要读原文时引导学生使用自己的教材或官方阅读入口，不用改写的故事冒充原课文。公版作品也需分别判断现代译注、配图和版式的权利。

## 3. 架构影响与数据模型

流程：核验教材版本与课次 → 确认目录及资料使用依据 → 建立知识目标与教学范围 → 固定原创教学任务书 → OpenMAIC 独立制作 → 教学对齐与版权审核 → 共享课程库 → 学生课堂。

新增教材领域，继续由 Python 后端作为权威数据源；Next.js 学生端负责展示，OpenMAIC 保留课件制作、语音、互动、讨论和课堂播放能力。学生端不持有官方平台账号或调用内容生产接口。

建议模型：

| 模型 | 关键字段 / 职责 |
| --- | --- |
| TextbookEdition | 学制、学科、年级、册次、出版社、教材系列、修订版次、ISBN（待核验时允许为空）、官方资源 ID |
| TextbookAlignmentRevision | editionId、目录/单元/知识目标映射摘要、核验依据、核验时间、目录使用评估、可发布状态；修订不可覆盖旧版，不要求先保存整本 PDF |
| TextbookSourceRevision | 可选的参考材料修订；内容摘要、来源、获取时间、校对状态及允许存储/模型处理/展示的范围；有权使用的材料才进入相应处理流程 |
| TextbookNode | 单元/课/园地等原书节点、原书顺序、标题、父节点、来源页；教材一课可拆多个教学课时，但保留同一原书节点 |
| LessonKnowledgeBrief | 对应课次、学习目标、词汇/公式/技能、先修、难度、禁止超纲内容、所需练习类型、核验依据；独立撰写，不夹带原文改写 |
| TextbookSourceBlock | 可选的、使用依据明确的引用或参考块；记录来源、页面位置、适用范围，不默认发往学生端或生成模型 |
| SchoolTextbookAdoption | 地区、学校（可选）、学年、学期、年级、学科、editionId、依据与确认状态 |
| StudentTextbookSelection | 学生本学期每科选择的 editionId、alignmentRevisionId、确认记录、学校当前课次 |
| TextbookCourseBinding | alignmentRevisionId、nodeId、知识目标版本、课时编号、原创讲解版本、courseId、courseVersion、发布状态 |

地区用于推荐教材组合，最终以学校或家长确认的教材版本为准。不同学校使用同一版教材时共享内容，不按省份重复制作；不同教材版本不得仅凭相同课名合并。

原有自编课程保留原身份和历史成绩，可用于补基础。新增教材学习路径；不得将历史自编课更换标题后标成“教材同步”。学校当前课次由明确选择记录驱动，不能根据省份推测。教材路径不继承与原书冲突的自编先修顺序，先修不足用诊断或补学提示处理，不伪造掌握记录。

## 4. OpenMAIC 必须增加教材模式

当前代码的几个具体差距：

- `backend/content/progressive_curriculum.v1.json` 标记为自编体系，一年级语文从“听音与单韵母”开始。
- `backend/services/progressive_course_generation.py` 的 `generation_brief` 绑定自编 lesson、先修关系和知识范围，没有教材原页、正文块或版本依据。
- `backend/services/learning_catalog_validator.py` 的现有来源合同明确为 `textbookDependency: none`；`backend/integrations/openmaic_question_adapter.py` 也有相应约束。
- `backend/integrations/openmaic_full_runtime_client.py` 的正式课程生成要求 `enable_web_search` 为 true，当前服务调用也明确打开搜索。
- 本地 OpenMAIC 存在文档材料上传、提取和 `pdfContent` 输入能力；这些通用能力尚不等于 Mira 正式课程已具备教材来源绑定。
- `backend/repositories/student_shared_course_repository.py` 已有读取、领取已发布共享课的流程，可以扩展复用。

新增独立版本的 `textbook-aligned-original` 生成合同，至少提供：

```json
{
  "schemaVersion": "mira.learning.textbook-original-generation.v1",
  "textbookBinding": {
    "editionId": "<verified-edition-id>",
    "alignmentRevisionId": "<verified-alignment-revision>",
    "nodeId": "<original-textbook-node>",
    "partIndex": 1,
    "alignmentManifestSha256": "<sha256>"
  },
  "knowledgeBriefId": "<reviewed-original-teaching-brief>",
  "knowledgeBriefSha256": "<sha256>",
  "allowedReferenceBlockIds": [],
  "sourcePolicy": {
    "allowWebSearch": false,
    "allowFullTextReproduction": false,
    "allowSourceParaphraseAsOriginal": false,
    "exerciseMode": "independently_authored",
    "visualMode": "original_or_licensed"
  }
}
```

上例表示目标结构；第一阶段实际合同见 `backend/content/textbook_catalog.py` 的 `generation_brief`：直接冻结 `knowledgeBrief`，加入 `teachingRevision`、`promptSha256` 和 `contentKey`，参考片段固定为空。生产端应提供已核验的知识目标和原创教学任务书，不默认上传整本教材或逐页改写。仅输入课名不足以保证教学对齐，先核对完整的本课目标。

OpenMAIC 生成的讲解、场景和练习需回传 `knowledgePointIds` 和 `alignmentNodeId`；实际使用引用时另附 `referenceBlockIds`。保存教学任务书摘要、合同摘要及课件版本。人工核对目标覆盖、错误/超纲、题目答案、表达独立性、图片构图和语音；不得通过照原图重画或逐句转述规避检查。

正式发布规则新增教学对齐、素材使用依据和原创表达审核，同时保留身份、媒体完整性、可播放性和学生会话隔离校验。教材模式的联网策略必须在 Python 客户端、运行时策略和验收回执中同时生效，不能只改 Prompt。关闭联网本身也不代表模型不会输出已有作品，输出审核仍然需要。

原创题量根据本课目标、学生年龄和学习时长确定，不复制原书题量与题组结构。题目使用 Mira 自有 ID，并标记为本课原创练习，不冒充教材原题。已经看过答案或在引导下完成的练习不当作独立掌握证据；朗读、开放回答等继续区分自动判断与需确认的结果。

## 5. 已实现接口与后续生产适配

以下接口已实现。保持现有学生会话和家长权限，教材读取没有 Provider 调用，也不在请求时创建缺失课程。

| 接口 | 用途 |
| --- | --- |
| `GET /api/v2/student/learning/textbooks` | 当前年级已收录教材，含家长确认、学制、仅索引/部分/完整目录标记；待核验样本可预览目录 |
| `GET /api/v2/student/learning/textbooks/{editionId}/contents?alignmentRevisionId=...` | 固定单元/课次、书面/PDF 页码、目标和课程状态；返回课程必须通过已有发布/媒体门禁与教材检查 |
| `GET /api/children/{childId}/textbooks` | 家长选书目录；要求管理孩子资料权限和家庭归属 |
| `PUT /api/children/{childId}/textbooks` | 每学年、学期、学科确认一个版本，支持可选当前节点；锁定孩子并检查选择修订号，保留历史事件 |
| `POST /internal/learning/textbooks/import` | 严格校验并导入元数据修订；拒绝正文/PDF 字段和同修订覆盖 |
| `POST /internal/learning/textbooks/prepare` | 幂等冻结已审核节点的原创任务书，返回 `providerDispatched:false`；没有实际生成调用 |
| `POST /internal/learning/textbooks/bind-published` | 将已正式发布且具有精确教材绑定、内容摘要及人工审核记录的产物挂到目录；该接口不负责生成或发布 |
| 现有 `POST /api/v2/student/learning/courses/{courseId}/versions/{courseVersion}/start` | 共用课程和会话的教材选择检查；现有正式课堂与先修检查仍生效 |

需要原文阅读时提供书面页码或官方阅读入口；只有使用依据覆盖展示时才提供相应原文。管理端的索引核验、资料处理、生成和审核使用单独授权的内部服务，不暴露给学生页面。

实际新增：

- `backend/content/textbook_catalog.py`、`backend/content/textbooks/`：严格元数据合同、不可变版本摘要、22 册语文版本索引和部分目录样本；`index_only` 必须为空目录，`partial/complete` 必须有真实节点。
- `backend/repositories/textbook_repository.py`：教材身份、修订、选书历史和课程制作身份。
- `backend/services/textbook_learning_service.py`、`backend/services/textbook_course_policy.py`：目录、家长确认、冻结任务书、发布绑定、开课检查。
- `backend/prompts/textbook-course.v1.json`：独立创作的版本化提示，不是生产运行时的强制控制本身。
- `backend/routes/api/v2/student_textbooks.py`：学生只读教材接口；注册到既有应用工厂。
- `student-web/src/lib/contracts/textbooks.ts`、`student-web/src/features/learning/learning-textbooks.tsx` 及同源 API 代理；入口 `/learning/textbooks`，学习首页有“学校教材”入口。
- `mobile/lib/src/features/learning/{domain,application,presentation}/` 下的教材模型、仓储和选书页；入口“孩子资料 → 学校教材”。
- `backend/migrations/082_fixed_textbook_learning.sql`：五张增量表。已在独立临时 MySQL 验证，没有应用到现有数据库。
- `backend/scripts/textbooks.py`：明确操作的校验、导入、任务书导出与准备工具。

**尚需完成生产适配**：现有生成器仍只接受自编循序课程注册表中的 `lessonId`，正式 OpenMAIC 仍要求其原有联网/研究策略。需要将教材合同加入内容生成、题目验证、课件编译、共享库存、运行时补丁及正式发布验收，实际落实教材模式的来源策略。当前 `prepare` 不会启动这些旧流程，也不会把教材节点强行改成旧 `lessonId`。`bind-published` 是预留的受校验接点，不表示现有生产器已经能产出教材课。

目标流程：查看本学期教材对应目录 → 单元及课次 → 听原创讲解 / 做原创练习；需要时提示翻开自己的课本或打开官方阅读页。首批仅收录语文，当前未产出可上课的教材课；数学、英语不以占位课程显示。学校未开设的学科不擅自显示成学校教材同步课程，不暗示出版社或官方平台为本课程背书。

## 6. 固定生成与复用

共用内容身份建议为：`editionId + alignmentRevisionId + nodeId + partIndex + teachingRevision`。知识任务书摘要进入不可变制作合同，模型、Prompt、运行时和音色作为制作与兼容性记录保存。具备完全相同目标且适合跨版本复用的原创内容可共用底层素材，但每个教材绑定需分别校验，不凭课名自动合并。

- 生成由管理端批次触发，一次制作，审核发布后所有符合教材版本的学生共享。
- 数据库唯一约束与原子任务领取防止多人并发重复付费；外部调用结果不确定时先查原任务，不能盲目重试。
- 学生访问目录、开始学习、重复听课，都读取已发布课件，不触发整课重新生成。
- 库存没有课件时显示准备状态，由后台受控补齐；不能用另一版本或相似标题课程顶替。
- 实时提问仍可能产生 AI 调用，但不会重建教材课程；固定讲解和音频直接复用。
- 教材修订只重新核验受影响的教学目标、对应关系和课时；旧课程与旧作答记录保持原版本。切换模型配置不应直接导致已发布课程全部重做。
- 学生学习记录独立存储，并附教材版本、对应课次、原创题目 ID、知识点和适用的引用记录，为后续错题复习和家长报告提供依据。

## 7. 首批范围与验收

按用户最新要求，首批采用全国普通小学语文官方版本，先验证语文学科，暂不扩展数学、英语。已收录的 22 册版本逐步补齐目录与逐课教学目标；六年制一年级上册第一单元作为目前可核对的目录样本。每批先明确目录及素材使用依据，再审核发布，不改变教材实际教学顺序。

必须验证：

1. 单元、课次和顺序与指定教材对应，所用目录的使用依据已核查，需定位原文时页码正确。
2. 教学目标和难度对齐，讲解、例题、练习和画面独立创作；合法使用的引用可追溯。
3. 错版、知识范围未经核对、使用依据未确认或未发布的课件不能启动为正式同步课。
4. 多个学生、刷新、重复开课及并发请求复用同一已发布课程版本；固定课程学习不触发生成。
5. 学生教材变更后新课与历史进度版本隔离，不把旧课成绩当作新教材已经掌握。
6. 受限原文、私有答案及家长/第三方账号凭证不进入学生接口；来源使用范围得到执行。
7. 在真实课堂中检查页面、语音、原创题作答和教材定位，而不只检查生成 JSON。

## 8. 第一阶段使用与验收记录

首批数据包含 22 册版本：21 册为 `index_only`，六年制一年级上册为 `partial`（`pep-chinese-g1-upper.preview.v1.json`，仅第一单元 6 个节点）。这不是全国完整课程库。出版版次、目录使用依据和逐课教学目标仍待核验，生成门禁保持关闭。样本中的教学目标是草稿，页码依据见 `coverage.note`。

纯本地校验，不需要数据库：

```sh
backend/.venv/bin/python backend/scripts/textbooks.py validate backend/content/textbooks/pep-chinese-g1-upper.preview.v1.json
backend/.venv/bin/python backend/scripts/textbooks.py validate-catalog backend/content/textbooks
```

上线顺序：先按项目流程备份并审核应用迁移 082，再显式运行 `textbooks.py import <manifest>`；整批导入使用 `textbooks.py import-catalog backend/content/textbooks`，在单个事务中校验并写入，任一版本冲突则整批回滚。这些命令使用配置的数据库，**不会替用户运行迁移**。然后家长在 App 确认教材，学生刷新“学校教材”目录。默认学期按上海时区 9—1 月/2—8 月划分；学校特殊校历与地区推荐表尚未接入，地区不会强制决定教材。

审核后的新资料必须使用新 `revisionId` 导入，不能把已导入的草稿原地改成审核通过。同一 `editionId` 的出版社、学制、年级、学科、册次、官方资源身份固定；其中任一改变需新教材 ID。目录修订摘要、节点、教学版本和 Prompt 摘要参与制作身份；重复 `prepare` 只返回同一行。后续 Prompt 升级不使已经审核的旧课自动失效。

`textbooks.py export-brief <reviewed-manifest> --node <nodeId>` 可在无数据库时导出制作输入；`textbooks.py prepare <reviewed-manifest> --node <nodeId>` 只为数据库中相同摘要的资料建立制作记录。两者都不调用 Provider。未经确认的样本执行时应返回 `textbook_review_required`。

本次检查：

- 后端教材隔离测试与既有课程注册表回归：21 项通过，覆盖全国版本索引、批量导入冲突回滚、身份、家庭归属、只读不生成、版本不可覆盖、年级切换、选择修订、发布与内容摘要检查。
- 独立临时 MySQL 9.6：新迁移执行、外键/发布 CHECK、4 路同版本导入只产生一版、4 路备课准备只产生一份、4 路同修订选书只有一次成功；发现并修复可重复读快照下的并发误冲突。
- Student Web：lint、typecheck、221 项测试、生产 build 通过。校正两处原有测试中已过时的课程粒度与预览文案断言。
- Flutter：analyze 无问题，457 项测试通过；人工查看两张差异图后更新截图基线，分别对应新增学校教材入口和已有首页课程库入口。
- 浏览器使用真实构建页面与后端隔离服务产生的响应样本，在 1440px/390px 核对目录、页码、空缺状态、刷新请求；无横向溢出、无脚本错误、刷新仅 GET。截图位于 `student-web/output/playwright/textbooks/`，该目录不纳入 Git。
- 22 册索引加入后，再用本机隔离响应核对当前年级的四种学制/册次组合。手机端使用紧凑选择框，实测切换六年制/五四制会更新精确来源链接和待核对状态；无横向溢出或浏览器错误。

验证边界：浏览器使用合成身份和拦截响应，不是生产账号端到端验收；未对已运行的业务库迁移或导入，未执行真实教材课生成、语音/画面验收或发布。本阶段也没有实现错题周测、家长学习报告或作业拍照分析。
