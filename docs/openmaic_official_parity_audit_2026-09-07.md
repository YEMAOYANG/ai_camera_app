# OpenMAIC 官方功能与本地差距核查

核查日期：2026-09-07。范围：官方 v1.0.0 tag、当日 open.maic.chat 实际页面、本地源码、3100 运行接口、已生成课堂文件和数据库发布状态。本次是只读审计：未修改应用代码、配置或数据库，未重启服务，未重新生成课程。

**结论：版本已经对齐，完整体验尚未对齐。** 本地锁定官方 v1.0.0 的同一个 commit `aa2bfb3c1d406c47100c6744d90e788abdf1f6d5`，叠加 45 个 Mira 补丁。后台专业 Agent 和联网研究已有真实成功样本；前台 Pro 工作台、图片/视频、导入导出、完整素材工作流、官网运营层及逐页效果验收仍有差距。

不能沿用此前“本地 0.3.2、Kimi、固定 10 页”的结论：当前正式创建使用 DeepSeek V4 Pro，独立验证使用 V4 Flash，专业 Agent 自适应规划页面。历史固定模板仍有兼容代码，不能用它描述当前正式新生成路径。

**功能对照**

| 功能 | 官方 v1.0.0 / 在线 Demo | 本地当前证据 | 差距与验收目标 |
|---|---|---|---|
| 版本 | v1.0.0 tag | lock、运行目录 HEAD 和健康接口均为 v1.0.0 | 已对齐 tag；官网运行版本及私有配置未公开核实，不能断言与 tag 完全相同 |
| 专业模式入口 | 官网首页可切换到 `/workspace`，有对话、课程、材料、课堂引用、Skill 入口 | 后台 Agent 启用；本地首页没有 Pro 开关 | 构建没传 `NEXT_PUBLIC_PRO_WORKBENCH_ENABLED`，编辑开关也为 false；需恢复完整工作台并实测保存、取消、恢复和修改课程 |
| 联网搜索 | 经典生成有搜索选项；Pro 有搜索和网页抓取工具 | 正式生成强制搜索、同会话抓取和引用；已有成功回执 | 不是缺搜索。当前仅接 Brave；手动生成页实测显示“点击开启”，与正式流程的强制搜索不同；学生播放不开放搜索工具 |
| 多轮制作与 Skills | Agent 可规划、生成、修改课程，引用材料和元素，管理个人 Skills | 代码和后台工具保留，前台工作台不可达 | 后台自动制作不能代替运营者可见的多轮专业工作台。官方公告写 20 个内置 Skills，tag 实际目录为 22 个，验收按源码清单 |
| 文档、图片、音视频材料 | 材料上传、提取、搜索、重用；部分格式依赖解析服务或本地 ffmpeg/ASR | 增强 PDF provider 为空；正式请求拒绝 `pdfContent`；完整 Pro 材料入口未开放 | 基础文本/PDF 提取代码存在，不能概括为“完全不支持 PDF”。需要按格式逐一验证从上传到最终课件的素材引用 |
| 图片生成 | 官方引擎支持图像生成；已查看的分数 Demo 含插画 | 运行 `imageGeneration=false`，image provider 为空；正式请求强制 false | 单独配置 provider 不够，还要调整正式生成契约及媒体验证；两个成功样本均没有 image 元素 |
| 视频生成 | 官方有视频生成工具，依赖相应 provider | 运行 `videoGeneration=false`，video provider 为空；正式请求强制 false | 需要服务配置、工具调用、资产保存和播放证据 |
| PPTX 导入与编辑 | 官方有布局导入、页面/元素编辑；导入有独立开关 | native 构建与启动强制 PPTX import=false、editor=false | 必须打开并验收导入布局、字体、元素编辑和保存，不是补一个按钮 |
| 导出 | 官方代码有 PPTX、完整课堂包、互动 HTML、旁白 MD/DOCX、视频等导出；官网示例可见 PPTX 导出 | 视频导出被关闭；学生模式隐藏整组 HeaderControls；运营者导出未做完整功能验收 | 区分 PPTX 导入开关与 PPTX 导出，不能误报所有导出都不存在。MP4/预览需 Render Service |
| 语音及声音克隆 | 讲解、语音输入、Qwen 声音克隆 | Qwen TTS/ASR 已启用，成功课程有逐段回执；声音克隆未核实可用 | 两个样本分别 26/32 段 speech；须实测音频、讨论语音、静音/续播、克隆声音链路 |
| HTML、3D、游戏、编程、PBL | 官方支持仿真、图解、游戏、编程、3D 和项目式学习 | 类型/工具保留；两节成功样本包含 diagram、simulation、game | 样本中没有 3D 或 PBL；这是覆盖和验收缺口，不能据此说引擎不支持 |
| 多 Agent、聚焦、白板 | 官方课堂具有角色讨论、聚焦指示、白板与播放控制 | 样本包含 discussion、spotlight；Mira 正式约束为 1 老师 + 4 同学，白板不是必选产出 | 与官方自由配置不同；样本没有白板 action，需要真实课型覆盖 |
| 学生体验 | 官网示例可直接浏览课程、切页、互动、打开白板 | Mira 通过学生身份、授权票据、发布课程和进度契约进入；编辑/搜索/导出受限 | 应分别验收制作端全功能与学生课堂体验；不能靠开放无限制编辑器来替代对齐 |
| 发现/公共课程库 | 官网首页有发现与精选课程 | 开源源码明确说明自部署不含 Discover feed，本地只有最近课程/文件夹 | 官网运营能力需要另行接入或实现；不是本地开关错误 |
| 竞技场、账号、积分/活动 | 官网导航可见竞技场、账号和积分活动 | v1.0.0 未发现相应完整业务模块；Agent 默认匿名 owner，用量日志不等于计费积分 | 若“所有功能”包括这些，必须单列；复用 Mira 账号/积分时需区分学习奖励积分和模型使用额度 |

**专业模式为何后台有、页面却没有**

`openmaic-runtime/scripts/native-runtime.sh:1724–1740` 使用 `env -i` 构建，未注入 `NEXT_PUBLIC_PRO_WORKBENCH_ENABLED`，同时设定 `NEXT_PUBLIC_MAIC_EDITOR_ENABLED=false`、`NEXT_PUBLIC_ENABLE_VIDEO_EXPORT=false`、`NEXT_PUBLIC_ENABLE_PPTX_IMPORT=false`。因此只改 `.env` 不足以保证开关进入构建。

上游 `lib/config/feature-flags.ts:32–48`、`lib/workbench/entry-gate.ts` 和 `app/workspace/page.tsx` 要求前台 Pro flag 与后台 Agent 配置同时有效。不满足时 `/workspace` 返回首页。浏览器实查与这条代码路径一致。

当前健康信息中的 `proModeAvailableToOperators:true` 来自 `lib/server/mira-professional-research-policy.ts:6` 静态策略声明，不能证明前台工作台可用。这项状态应改为实际检测，明确区分“策略允许”“构建启用”“运行可用”。

**实际生成和发布证据**

在当前 v4 DeepSeek 专业任务文件中观察到 2 succeeded、4 failed、1 running。这是历史任务快照，包含恢复/重试上下文，不能计算成正式成功率。失败示例含 `FORMAL_PROFESSIONAL_STAGE_LINK_INVALID` 和 `FORMAL_AUDIO_ASR_INCOMPLETE:0:succeeded`。

| 成功课堂 | 结构 | 讲解/动作 | 联网回执 |
|---|---|---|---|
| 《小浣熊的校园创意节：单韵母 a、o、e 大冒险》 `stage-D8VpGp9gAT` | 8 页：3 slide、3 interactive、2 quiz | 26 speech、9 spotlight、2 discussion | 1 search、5 results、1 fetch、1 citation |
| 《冬阳广场里的数位探险》 `stage-nfrSLomAhh` | 9 页：3 slide、3 interactive、3 quiz | 32 speech、10 spotlight、4 discussion、5 widget_highlight、2 widget_annotation | 1 search、5 results、1 fetch、1 citation |

两节均有 professional/research succeeded 记录。两节的 slide 元素统计均为 0 image，且没有 PBL、3D、白板 action。因此可确认后台专业生成和联网工作过，尚不能用这两节证明官网所有课型与素材质量已达标。

数据库发布快照：新的 30 课专业准备计划仍在 running/generating_content，2 课已有课堂、语音、验证和逐课发布回执，整体未 ready。primary_1 整批年级指针仍指向 2026-08-29 的旧 release。另一方面，两节新课各已有 progressive_plan 学生绑定；对当前已打开任务所属孩子按实际可见性 SQL 查询，两课均可见，目录汇总为 `catalogStatus=failed, availableCourseCount=2, targetCourseCount=30`。准备计划、整批 release、孩子目录是不同状态层，不能互相替代。不能说学生一律只能看旧课，也不能说 30 节专业课程全部就绪。

权威 Runtime 事件进一步证明：语文课已有 `classroom_completed=1`、8 个 action_completed、4 个 answer_submitted；数学课已有 9 个 scene_entered、6 个 action_completed、4 个 answer_submitted，尚无 classroom_completed。语文已有历史学习完成闭环，但本次没有重新播放；不能由会话摘要的空字段或游标 0 反推未完成，也不能据此宣称本次已通过两课完整长测。

浏览器现有的一条学生课堂链接显示“完整互动课堂暂时打不开 / 正式课程刚刚更新，请重新打开这节课”。本次仅观察，未点击重新检查或改变其会话。当前 SQL 判断该任务对应课程可见，所以页面可能保留先前请求的错误；尚未验证重试是否恢复。该事实应纳入后续入口/恢复验收，不能据此认定当前仍拒绝，更不能推断所有课堂不可用。

**“课件和官方 Demo 一模一样”的可验证定义**

已实际打开官网 [Understanding Fractions](https://open.maic.chat/classroom/bSxqO1_D1d)：可见 10 页课件、插画、披萨分割互动、测验、旁白、角色区、白板入口和 PPTX 导出。该例是展示质量和交互机制的参考，不应将三年级分数内容直接用于本地一年级课程。

1. 同一课件的呈现一致：取得允许导出的完整课件包及其素材，使用相同 DSL、renderer、字体、主题、媒体与动作，逐页对比截图和交互。内容层和外层 Mira 导航分别验收。
2. 新生成课件的质量一致：同主题、年级、时长、材料和生成选项，对照插图、信息层级、仿真逻辑、动作讲解、旁白、引用、测验和导出质量。不能以 scene 数量相同作为合格标准。
3. 相同提示词重新生成不保证逐字逐像素相同：结果还受模型/版本、搜索结果、素材、教师上下文和生成随机性影响。官方公开推荐模型不等于其线上实际模型配置；本次未获得官网私有部署配置。

保留上游官方的生成、DSL、渲染和编辑链路。Mira 已有年级、题目、身份与发布约束应放在边界验证中；对限制素材或改变页面内容的约束逐项评估，避免在上游已经生成完整内容后再压回简化模板。

**建议的实施顺序与验收点**

1. 恢复制作端完整 Pro 工作台，修正能力状态。先验收入口、会话/课程/Skill/材料列表、编辑保存、取消/恢复；确认前台构建 flag 与健康接口一致。复用原有 Agent API，首阶段无需改变学生身份/评分接口。
2. 补齐素材、PPTX 和导出。由服务端配置搜索、图片、视频、解析、渲染能力，调整正式请求中强制 false 和拒绝材料的规则；每种能力用一个真实结果验收。同步 native 与 Docker 启动，避免只在一个启动方式有效。
3. 做官方示例呈现基准及本地适龄生成样课。覆盖图文、仿真、3D、游戏、编程、测验、PBL、讨论、白板、聚焦、语音、引用与导出；按页和交互检查。先交付一组可审阅样课，再扩大生成批次。
4. 验证学生发布、重入、长课播放与完整完成。同时检查 progressive_plan 和整批发布入口，证明音频可听、互动有状态变化、无 HMR/iframe 意外重载、进度/评分/报告与课堂一致。
5. 单列官网运营功能：发现课程、公共发布/分享、竞技场、账号及使用额度。定义与 Mira 现有业务的映射后再实现，不能把开源版本升级当作这一层已交付。

预期修改范围：`openmaic-runtime/scripts/native-runtime.sh`、`openmaic-runtime/docker-compose.yml`、配置样例与状态检测；新的有序上游补丁（工作台/素材/能力状态）；`backend/integrations/openmaic_full_runtime_client.py` 及相应正式生成/发布契约；只有学生课堂呈现或入口确需改变时才修改 `student-web` 和 gateway。不要只手改被 bootstrap 重建的 `.runtime/OpenMAIC`。

架构保持：Mira 负责身份、年级、课程发布、评分和报告；OpenMAIC 负责专业创作、检索、素材、完整课件和课堂播放。制作端能力扩展不应向浏览器或学生暴露模型密钥。正式生成请求、媒体回执和 capability 字段的变更，须让调用方与校验方同步；不能单边把 `enableImageGeneration` 改 true 绕过现有校验。

**主要证据位置**

- 本地版本：`openmaic-runtime/upstream.lock.json:3–10`。
- 本地构建/启动：`openmaic-runtime/scripts/native-runtime.sh:1724–1740`、`:1777`。
- 正式生成条件：`.runtime/OpenMAIC/lib/server/mira-formal-generation-policy.ts:19–71`、`:146–159`；`backend/integrations/openmaic_full_runtime_client.py:187`。
- 学生边界：`openmaic-runtime/gateway/src/server.mjs`、`.runtime/OpenMAIC/components/header.tsx:94`。
- 实际样课：`.runtime/OpenMAIC/data/classrooms/stage-D8VpGp9gAT.json`、`stage-nfrSLomAhh.json` 及 `data/classroom-jobs/` 对应记录。
- [官方 v1.0.0 Release](https://github.com/THU-MAIC/OpenMAIC/releases/tag/v1.0.0)、[官方配置模板](https://github.com/THU-MAIC/OpenMAIC/blob/v1.0.0/.env.example#L301-L362)、[官方 Skills](https://github.com/THU-MAIC/OpenMAIC/tree/v1.0.0/skills/agent-runtime)。
- [官方生成模板](https://github.com/THU-MAIC/OpenMAIC/tree/v1.0.0/packages/%40openmaic/generation/templates)、[官方搜索适配器](https://github.com/THU-MAIC/OpenMAIC/blob/v1.0.0/lib/web-search/constants.ts)、[导出入口](https://github.com/THU-MAIC/OpenMAIC/blob/v1.0.0/components/stage/header-controls.tsx)。
- [自部署不含 Discover 的源码说明](https://github.com/THU-MAIC/OpenMAIC/blob/v1.0.0/lib/hooks/use-home-discovery.tsx#L19-L24)、[匿名身份边界](https://github.com/THU-MAIC/OpenMAIC/blob/v1.0.0/lib/server/agent-runtime/with-owner.ts#L12-L19)、[纯用量日志](https://github.com/THU-MAIC/OpenMAIC/blob/v1.0.0/lib/server/usage-storage.ts#L25-L59)。

本次未执行全套测试、付费模型调用、完整学生长课或同一课件导入对照；以上明确区分运行配置、现有回执、可见页面与尚未验证项。上线等效结论必须等待对应验收完成。

**追问补充：关闭原因与 MAIC-UI 集成判断**

2026-09-07 再次只读核查，未安装依赖、启动 MAIC-UI、改变现有配置或调用模型。

- 图片：现有服务端配置存在可复用的 DashScope 凭证（只核查存在性，未输出值），native loader 支持复用；图片开关未设置，默认关闭。`native-runtime.sh:636–655` 将其设计为独立计费能力，不随 TTS/ASR 自动开启。账户是否获准使用图片模型尚未验证。除此之外，backend 和 runtime 正式契约均强制图片 false，所以仅启用 provider 也不能完成正式课程接入。
- 视频：未配置视频 provider 凭证；native loader 没有视频加载/注入链路；正式契约同样强制 false。AI 视频生成与 MP4 课程导出是两项独立能力，后者还需要 Chromium/FFmpeg 渲染服务。
- 历史补丁证据：`0012-mira-candidate-runtime-idempotency.patch:681` 同时限制搜索、图片、视频；`0038-mira-formal-professional-agent.patch:747` 升级专业流程时只把搜索改为 true，媒体限制保留。没有找到用户要求永久关闭制作端图片/视频的依据。当前差距应归为接入与验收未完成。
- Pro、编辑、PPTX 和视频导出的关闭作用于整个制作端构建，不能归因于学生隔离；学生授权与工具限制已有 gateway 和学生模式机制。

Pro 工作台是给内容制作人员使用的对话式课件编辑界面：输入教学要求/上传材料，Agent 规划课程和生成页面；随后可以继续要求修改某页、添加互动、调整讲解或引用素材，并保存课程和对话。后台专业 Agent 是执行引擎，前台工作台是人使用该引擎的界面。儿童自动进入已发布课堂不依赖家长手动操作该工作台；改善学生课件质量应优先补齐媒体和互动生成，而不必等待家长制作流程。

MAIC-UI 核查主干 commit：`aad58ddcc2103058b4c2deffc48a3c13e2c64dd6`。这是独立的 Next.js/FastAPI 制作应用，有登录、PDF/PPT/概念输入、模板、互动 HTML 生成和版本编辑，含真实 Docker/Compose 源码。它不是 `@openmaic/renderer` 等 SDK 的别名，也不是当前 OpenMAIC 缺失的必装 UI 包。

实际用法是登录后输入概念或上传材料，选择模型/年级/生成方式或模板，生成互动网页，再预览和编辑。独立部署需模型配置、JWT secret 和数据库；Compose 入口为 8927。README clone 地址仍是占位符，默认 `AI_PROVIDER=zhipu` 与 PDF 路由部分解析分支也有不一致，因此本次只验证源码，没有宣称照文档已一键部署成功。

其 API 链为 `POST /api/pdf/concept/upload` → `document_id` → 查询处理状态 → `GET /api/pdf/documents/{id}/website` 返回 `{html, metadata}`；PPT 产物为 slide 图片或 demo HTML 列表，并非 OpenMAIC Stage/Scene/Actions。当前 OpenMAIC 已使用自身 generation/renderer/dsl/editor/importer/storage 六个包，两仓没有现成的对接链路。

集成建议：**现阶段不把 MAIC-UI 并入正式主链路。** 先完成原生 OpenMAIC 的媒体/制作/播放能力。需要进一步提升复杂互动页面时，用同题样课独立比较 MAIC-UI；若效果有明确增益，将其作为可选 HTML 生成服务，通过适配器生成 OpenMAIC Interactive Scene，并补充教师操作协议、讲解动作、资产保存与学习完成证据。文档推荐不能证明官方 Demo 由 MAIC-UI 生成，也不能证明更换生成器必然改善当前样课。

补充官方来源：[MAIC-UI 仓库](https://github.com/THU-MAIC/MAIC-UI)、[部署定义](https://github.com/THU-MAIC/MAIC-UI/blob/main/docker-compose.yml)、[实际 HTML API](https://github.com/THU-MAIC/MAIC-UI/blob/main/backend/src/api/pdf_processing.py)、[互动生成器](https://github.com/THU-MAIC/MAIC-UI/blob/main/backend/src/services/html_generation/heavy_generator.py)、[OpenMAIC 推荐段落](https://github.com/THU-MAIC/OpenMAIC/blob/main/README-zh.md)。
