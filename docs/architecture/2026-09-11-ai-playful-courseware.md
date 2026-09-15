# AI 生成的适龄探索课件

用户要求小学课件像 OpenMAIC 官方示例一样包含有教学作用的小游戏和 3D，减少连续做题，并明确要求玩法由 AI 生成，不能写死关卡。本次使用既有 OpenMAIC Pro 制课链路，没有接入预制游戏 HTML、固定关卡数组或按课程标题选择模板。

## 新课约束

新创建政策增加精确的 `playfulLearningPolicy`，版本为 `mira.openmaic.playful-learning.v1` / `mira-primary-playful-exploration.v1`。这个对象参与课程目标身份；已经冻结的旧课程不追加标记，旧课程、旧会话及发布收据保持兼容。

- Pro AI 根据冻结年级、知识边界、目标与难度，自行设计场景、规则、操作对象、状态和反馈。
- 每课至少一个可重玩的真正小游戏。目标、规则、操作、根据教学模型计算的结果、解释和重玩入口必须实际存在，不能只贴 `game` 标签或用答题按钮代替玩法。
- 数量、分组、分数、比与百分数等适合实体表达的数学知识，要求可操作的真实 3D 教学模型；旋转、选择、拆分或组合须服务本课目标。其他内容按教学需要选择 2D 或 3D，不能强加课外知识或装饰性旋转物。
- 正式评估仍保留原有四题及原顺序：两道引导题合并为一页，两道独立题合并为一页。减少的是答题页面，不是正式题目数量。游戏不增加正式题目、积分、奖励或完成事件。
- 内容、安全、独立教学审核、真实浏览器交互与视觉审核、TTS/ASR 和发布门槛继续执行。结构校验通过不等于实际可玩。

## 接入位置

后端 `openmaic_formal_media.py` 和 Native 的生成政策共同声明新版本，`openmaic_full_runtime_client.py` 为新请求选择该政策。后端与 Student Web 的严格契约同时识别新标记并检查游戏和答题页面结构。

Native 补丁 `0094` 将要求写入冻结 Pro 主提示，并在只读检查和最终提升阶段检查页面结构。补丁 `0095` 让逐页内容、旁白生成和独立质量审核直接接收该冻结上下文，不再只依赖主 Agent 转述；生成收据、审核输入哈希和质量缓存身份也包含该上下文。小游戏提示要求 AI 自行选择非答题玩法，反馈不计正式积分。生成器保留 AI 返回的实际玩法配置，不在生成后替换为人工编写的游戏。旧任务的提示、缓存身份和审核账本保持不变。

共享库存展示继续支持已发布旧课；请求新探索政策的生产槽位必须匹配完整新政策，不能以旧版同技能课程提前满足新版本生产任务。学生的既有课堂不会被直接替换。

## 首门真实样课与校验

本次仅生成六年级数学 `fraction_ratio_percentage` 标准槽位 1，新 build item 为 `catalog_build_item_ea873d206248a13de584960e`。保留原数学课程，普通批量 worker 保持停止。

第一轮在内容阶段停止，尚未进入 Native 课件生成，也没有发布。AI 答案 `48人;60%` 与 Host 数学结果 `48;60%` 因人数单位字面量不一致被拒绝。已修复严格同值且量纲正确的表达识别，未修改题目、答案或原 Provider 回复。原两份付费回复共十个题目结果全部通过离线重放。

`learning_content_recovery.py` 和 `learning_catalog_repository.py` 增加受限的新政策首次尝试恢复路径：必须是同一单槽、四条已返回的阶段记录、原请求及 profile 哈希相同、无其他尝试或 Runtime，且原硬截止未到。先存内容寻址的完整原失败行和事件，再恢复有效 checkpoint；原计费字段、开始时间和硬截止不变。旧 attempt 2 路径保留。

本次 plan/apply 已成功，恢复增加 Provider 调用为 0；仍为原四条派发记录，下一阶段 `lesson_text`。恢复审计 SHA 为 `d9f553704ad281a1605e641ac5698cbb6fa18dd1bb85d19d2aceef260adbabb6`，原硬截止为北京时间 2026-09-11 19:45:49.080。

后续真实制课命令曾两次被自动审批拒绝，拒绝的命令均未执行。用户随后明确回复“允许”，授权项目配置的 DeepSeek、百度搜索和阿里云通义接收本课教学内容、生成的截图、旁白和音频，并产生制课费用。原单槽政策在身份与截止核验后恢复；同一内容尝试在原硬截止内完成，累计七条内容派发，随后进入唯一 Native 实例 `omformal_3b6ae9c7b6e8f13472a10d04`。

AI 第一版保存了八页：四页讲解、一个模拟器、一个游戏和两页正式评估。实际试玩发现游戏将 1/3 四舍五入后判为精确 33%，分子超过分母时显示互相矛盾，且所谓 3D 只有两个平面。2026-09-11 20:01:45，通过官方 `postUserMessage` 持久队列向同一仍在运行的 Pro 会话发送唯一观察反馈（seq 5762，delivery `steer`，未重新排队）。发送前原场景与观察审计保存在 `output/primary6-playful-ai-scenes/scene-p5-operator-feedback-before.json`；未手工修改生成的 HTML、冻结提示或质量结果。后续以 AI 修复后的原始输出和真实验收为准。

新旧政策和库存兼容、数学答案规则等 53 项后端测试通过；恢复及 operator guards 8 项通过。Native 上下文相关 67 项测试、实际生成工具 13 项测试、production TypeScript 检查与生产构建通过。Student Web 的 lint、类型检查、160 项测试和生产构建通过。最近一组后端新入口、库存、探索政策与恢复回归共 45 项通过。最终可玩性和正式发布仍以实际新课的交互、视觉、媒体收据为准；第一版已生成，但尚未通过验收或发布。

## 正式新课的学生入口

“我的学习”合并当前年级已正式发布、媒体齐备的共享课程。新接口 `POST /api/v2/student/learning/courses/{courseId}/versions/{courseVersion}/start` 接收空对象，返回 `{ok, taskId, created, courseId, courseVersion}`。服务端验证真实学生、当前年级修订和精确发布版本后，关联既有共享生产者的 child follower，继续使用原 progressive-plan 包与 Runtime 绑定权限。

选择课程创建独立 `catalog` 学习任务；同版本幂等，旧版本任务和课堂进度保留。此类任务不占今日排课、不进入自动补课，不推进全局年级指针或重启生产 worker。前端仅为完整课堂就绪且尚无任务的课程显示新入口，创建后通过完整文档导航进入既有课堂路径。已经取消、拒绝或过期的安排返回中文 409，不恢复家长停止的任务。所有生成、发布和学生入口可用性分别记录，不能将代码完成当成样课已经发布。

## 本轮超时与保存稿继续流程

2026-09-11 20:37:55，原 Native 任务按既有 60 分钟截止报 `FORMAL_PROFESSIONAL_SESSION_TIMEOUT`，Pro 会话转为 cancelled。五条人工实测反馈均由官方队列消费，原始 AI 草稿八页仍在。p5 真正六面体和数学交互已经通过独立回归，p3 有限小数显示、p5 矮视口布局、p2/p4 引用文字越界及最终质量/媒体审核仍未完成。原 failed job 完整字节与 SHA 保存在 `output/primary6-playful-ai-scenes/native-terminal-job.json`，终止观察在 `terminal-monitor.json`，没有发布。

继续工作须保留这次失败和计费历史。Agent 官方 terminal `postUserMessage` 可续写同一 session/stage，但不会自动恢复 Native failed job 或 Backend Runtime；之后仍要经既有 saved-stage prepare/inspect/complete、Backend reconcile 和正式 publish。原授权及窗口继续约束请求，不能把 requeue 当作重新签发预算，也不能直接把失败状态改成 ready。

补丁 `0096` 仅细化校验错误路径：缺失的分子/分母字段、状态/操作位置和示范晚于操作的场景位置。35 项限定测试通过，637 个输入变体与旧校验器的接受性无差异。补丁在原任务终止后才应用，未变更本轮原始提示或校验条件。

### 自动重复尝试的停止与审计

原任务超时后，单课 operator 在一次循环中先轮询失败状态、随后仍执行候选处理，于 20:37:58 创建了第二个 Runtime `omfc_QmZA9I_RsxllsxE0T8J_BQbp7Ma8jBvdTEm7HrdHPyo` / Native job `omformal_17093f873cc1aee85c1aac03`。下一循环虽停止，已经不能撤销这次自动派发。已在每次状态轮询和处理 tick 后立即刷新并检查范围，失败时禁止继续派发。

重复 Pro 在 20:47:24 经官方 `requestCancel` 取消；随后通过原 Native 状态读取与 Backend `generation_status` 同步为 failed/rejected。它没有生成 stage 或页面，但执行过研究工具，不能宣称没有 Provider 使用。两条 Runtime、失败字节、取消事件、原付费与未知账目完整保留，证据在 `output/primary6-playful-ai-duplicate-cancel/`。

后续恢复只允许明确选中第一个草稿用于 saved-stage 完成及发布。显式 plan/apply 审计入口保留完整两条历史，正常生成入口仍拒绝这两条历史 Runtime；不能过滤掉重复记录来满足原单实例上限。应用前必须核验相同课程身份、重复实例已取消且没有页面或学生绑定、原八页源快照与账本。原完整源快照为 `output/primary6-playful-ai-source-snapshot.json`，质量 SHA `9bfad485d87cf1f07d906eddaa93a51996390906108954eddd309ac4bd19b3f9`。

第一次 apply 因审计事件字段不符合现有公开事件契约而完整回滚；改用既有合法字段后，32 项定向测试通过，包含真实 `append_event` 校验与 SQL 写入。随后成功应用审计 `32a62d94c1b599cc2351ed0740b180277bbc00f4de400bc5ffd504fc50a2e070`：仅退役无产物的重复 Runtime，历史数仍为二，原账本不变。带此审计的 reconcile/publish 仅处理原课堂的正常媒体与发布尾段，不调用普通候选生成器。

2026-09-11 21:13:12.233，经官方 `postUserMessage` 对原 Pro 单次续写（seq 16562，delivery queued、requeued true），发送前审计 SHA `3c72a55238cfccda11c880fbe45d9dfc4655427612fdc5229e520bee93e05345`。提交事务确认原事件、提示、八页、Native failed job、派发标记及预算绑定完整保留。后续导出须使用续写终止时的真实新快照，不能把暂停时的旧 SHA 当作新结果；尚未正式发布。

21:13:21.829，该次续写消息已消费，但在 `reserve` 的全局并发检查阶段因 `MIRA_PAID_BUDGET_RESERVE_REJECTED_INFLIGHT_LIMIT` 终止。未进入 Provider 出站、未新增 reservation、工具调用或页面变化。原授权 92 条账本仍为 89 settled / 3 unknown，全局还有其他历史未确认占用。该终止快照单独存于 `output/primary6-playful-ai-continuation-failure-16562/`；它不是最终验收稿。后续不得虚构实际 usage、删除未知账目或通过反复重排绕过原并发守卫。

### 同一原稿继续与历史传输审计

21:31:19.282 原 Pro 官方续写 seq 16573 已提交，审计 `84921fbd987264fe4b2899aaecd8410fdb000cd71fde7a2407da770a61edb1d3`。原授权范围、身份、22:11:58.576 固定截止和所有未知费用保留；仅对精确生产授权临时增加一个准入名额，全局上限仍四，实际 reserved/dispatched 也始终最多四。续写已产生真实 Provider 回复及 AI 页面修改。

p3 有限小数精度与 p5 两栏布局已在真实 Chrome 观察，1/16=6.25%、1/32=3.125% 正确；3D 方块可拆分。21:48 正式质量检查仍要求 p3 在 1280×720 下重置后视觉及反馈完全一致，未人为放宽审核。最终导出、媒体审核与发布仍待实际结果。

四条历史 unknown 请求不能伪造结算，也不能无限占用正常学生课堂。新增独立本地传输审计入口：核对原请求身份、原始档案、托管部署进程和端口实际终止，再按完整四条批次追加 `transport_terminal_confirmed`。原费用与授权零修改，仅在 observation 模式的本地并发准入中使用；严格模式及无有效审计的新 unknown 继续保守计入。实现和边界见 `2026-09-11-audited-transport-terminal-reconciliation.md`。26 项 plan/apply、消费和临时准入定向测试通过；此时真实停服及四条事件尚未执行。

21:51:48 原 Pro 会话结束，但明确未得到最终质量通过：最后审核入口因流式事件总量超过 20,000 报错。真实完整 PG 原稿导出为 `output/primary6-playful-ai-unreviewed-terminal/`，source snapshot SHA `af28bf80539851ab7ae41982fc23834cde976ba758ca204620423ac4dbb4f8a2`。原八页、四道锁题和所有历史审计保持一致，不能把 Agent succeeded 等同于可发布。

两项执行层修复没有编辑 AI 课件：0097 在固定水位分页读取中仅排除已知 message_update 流式帧，保留全部原始 PG 事件、未知结构事件及 20k 结构事件上限；0098 解决可复现的 SVG 边缘一个色阶误差，只在数值、原 SVG、完整反馈、矩形、尺寸与 alpha 相同且极少量已有高对比边缘像素差不超过一个色阶时认可重置。不同状态的图形和反馈变更检查继续执行。原 p3 在真实 1280 pointer 与 1024 touch 都通过三状态及重置检查，16 项事件读取和 30 项探索定向测试通过。

两补丁已通过完整托管生产构建，Native BUILD_ID 为 `pNq9DZ4JvUWVdTSLr7NRD`。标准 saved-stage prepare 成功，正常提升及研究页脚规范化后的 snapshot 为 `efce9328097b203ec4669e43d03fd18402418f3ca63df1b834760458aac6ee13`。首轮独立 preflight 为 14/16：p3 的 saved-stage 通用检查错误选中默认状态下的 reset 并要求变化，而该入口没有传递普通正式审核使用的教学 probes。不能修改重置行为来迎合这项误报，也没有执行 complete 或发布。

22:11:58.576 原生产执行凭证到期，未延长原行。正常课堂 API 策略已恢复并重启，浏览器确认旧课程仍为 95% 进度，新课没有提前公开。剩余教学语义审核及 36 段旁白的 TTS/ASR 尚未派发。用户此前的明确许可覆盖同一课的完整审核、截图、旁白和音频；后续仅在这一既有许可范围内准备独立的 completion-only 执行凭证，保留原授权截止、失败和未知费用历史，不能用于新增 Agent、搜索、课程或 Runtime。

0099 已使 saved-stage CLI 复用正常正式审核的冻结教学探针。原样课件重新进行无 Provider 浏览器检查，16/16 全部通过，p3 两个视口各执行两项教学探针、三种状态和重置。第一次 auto-reset 失败的完整报告已单独保存，没有删除失败证据。浏览器通过仍不等于独立教学质量、语音及正式发布通过。

### 独立收尾凭证准备与执行阻断

0100 和后端的 saved-stage tail 接口内核已完成。凭证只绑定当前原稿、八页、四道锁题和 36 段旁白，并通过内部 budget/context 核验已提交的数据库审计。原 719d 授权、冻结 input、旧账本和 unknown 费用不更新。沿用 observation 模式，不新增累计调用、token 或费用额度限制。Native 87 项、后端 49 项定向测试通过；独立复审又核对了真实原稿和 8 项后端测试。

只读计划保存在 `output/primary6-playful-tail-authorization-plan.json`，SHA `83f8749ca5ad55868c8594b3d886c24d04a905d479113b714c8d2e4829584263`；预期授权 ID `a3a8ddfbc1267cc621a41406788dc32cd63076de6ae0f99d4c43dec93e694d01`，尚未签发。计划技术窗口为 2026-09-11 22:36:47.072 至次日 00:36:47.072，不代表新增用户批准时间。预期工作为 DeepSeek 教学语义和截图审核，以及阿里云通义 36 段 TTS 与对应 ASR；74 次是预估数量，不是新累计额度。

实际 `apply` 命令在执行前被自动审批拒绝，明确理由为“用户只授权了 AI 课件生成，未明确授权此具体预算、Provider 和付费收尾范围”。因此没有执行数据库签发，也没有发起任何收尾 Provider 调用。不能通过其他入口、重命名命令或替换原授权绕过此次拒绝；需要向用户说明具体收尾范围并取得明确批准，再继续已有原稿。代码构建和正常服务恢复不受影响，新课仍未发布。

0100 完整托管生产构建通过，实际 BUILD_ID 为 `8b3XT59hYcNl-nO6rh3iF`，Native、Gateway 与 Backend 均已正常重启，普通生成 worker 保持停止。只读实库确认新授权不存在、`saved_stage_tail_authorized` 事件为零，apply 与 sidecar 文件均不存在。后续若用户明确批准时原计划窗口已过期，需要重新生成未签发计划并保留本次被拒绝记录，不能修改已签发授权或伪造过去的批准时间。

### 2026-09-14 用户明确批准后的执行

用户针对 DeepSeek、阿里云通义、教学内容/截图/音频传输及预计约 74 次付费收尾调用明确回复“允许”。当前原始 job 字节与 AI 源稿未变；托管 Backend、Student、Native、Gateway 健康，普通 worker 停止。重新执行的浏览器检查为 16/16。旧拒绝计划保留，新只读计划 `df98a0ef837e8d53255eac9173a743b22ea677da48a290351de166044b5d9d00` 成功签发唯一 `a3a8ddfb…` 凭证，没有修改原授权。

第一次真实 complete 完成视觉和教学两个调用，两条均已 settled。视觉通过；教学审核拒绝，原因是规则前没有真实学生解释机会，现有 p3/p5 讨论只让 AI 同学乐乐/多多回答，p8 也只有旁白。36 段 TTS/ASR 尚未启动。完整 needs_revision、Provider 原回复、账本和原 complete claim 保留，不将它们标为通过或删除。

修复只针对上述具体缺口：新增版本化提示，由 DeepSeek Flash 在原 p1/p8 动作末尾生成两条真实学习者讨论，使用当前真实 teacher ID，并等待孩子通过既有聊天/语音输入解释。全部游戏 HTML、八页顺序、四题、36 条 speech 与既有动作不动。显式 `complete-learner-discussion-repair` 关联原失败 claim，追加自己的单次 claim，在同一已核验输入、Provider 和 completion 计费上下文完成；不启动 Agent、搜索或新生产。输入和派生输出分别记录哈希及原始 AI 回复，派生稿仍须经过完整正常质量和音频审核。此段描述实现范围，不表示 AI 修复或发布已经完成。

0101 已完整构建并恢复 Native/Gateway，BUILD_ID `k9ZOyt7V8mNCSIvwtJZRH`，补丁 SHA `b5c9b8abb30392462ae147a9e7132cc03de8eb03b6bccb9e0c52ae5e944999bb`。47 项 claim/凭证测试、30 项 AI 修复/Provider 测试、33 项后端收据测试通过，production TypeScript 与完整构建通过。后端验证两条讨论删除后必须恢复原准备快照，并核验原 AI 回复、请求及输入输出和最终质量上下文，不接受修改游戏、旁白或原题后重签的收据。

实际 AI 修复执行命令再次在执行前被自动审批拒绝。理由为原许可未明确覆盖审核失败后的额外修复调用及增加的费用范围。命令没有运行，新增修复 claim、AI 修复请求和 TTS/ASR 均未产生。具体待确认范围：1 次 DeepSeek Flash 生成两条讨论、2 次重新做视觉/教学审核，另完成此前尚未开始的 36 次 TTS 和 36 次 ASR。包含已经 settled 的两次初审，本课本次收尾预计总计 77 次，较原 74 次估算增加 3 次；不把估算改成累计额度限制。须获得用户对增加部分的明确批准后再执行，不通过其他入口绕过拒绝。

### 2026-09-14 追加调用获批及原回复校验修复

用户再次明确回复“允许”，覆盖新增三次 DeepSeek 修复/复审和原 36 TTS/36 ASR。10:00 的真实修复调用返回两条教师讨论：在 p1/p8 等待“这位同学通过课堂输入（文字或语音）回答”，禁止 AI 同学代答。本地硬匹配“真实|屏幕前”字面词误拒，原 Provider response、dispatch claim 和 failure 全部保留。当前三条收尾调用均 settled，没有新增 unknown。

代码影响仅为 Native 服务端校验与显式恢复 CLI，学生端 API 不变。0102 支持等价的真实学生措辞，并新增 complete-learner-discussion-response-recovery，要求独立 manifest 冻结 input/request/dispatch/rejection/response/failure 六项 SHA；只复用原回复，不重新请求修复 AI，也不改写原内容。恢复另存审计，派生课件仍走普通视觉、教学复审和 36 段 TTS/ASR。

0102 补丁 SHA f58dbdcd9beeb9ac9fe8a2d6e3bf22f72a22cb317995c6fb83c14994ff9565d3；50 项 CLI claim/预算测试、35 项回复校验和恢复测试通过，production TypeScript 通过。此时正在完整构建，课件尚未通过最终复审及发布。

### 派生稿真实视觉复审与练习布局

0102 完整构建通过，BUILD_ID 73XLflBZtF6S_PRVBVq6v；显式六哈希恢复成功，providerCalls=0，派生 snapshot 为 affcbac6ff6b71f3d484b9966ff1cba93f109ad490a107067ec9ae3b0b0a09fb，AI 原文未变。真实第二轮视觉审核指出 p7 在 1280x720 的题干顶部被遮挡，因此未继续教学文本审核和语音。

实测稳定渲染后的初始页面与普通点击没有题干遮挡。原检查截图可确认内部滚动至51px最大值，但入场动画触发滚动的因果未能稳定复现，不能据此断言。改动范围为 QuizView 宽屏双列选项与只读检查器的稳定初始画面；锁定题目不改、学生API不变。测试点击不表示标准答案，p6实际选项与算术经原内容核对正确。补充显式派生稿复审入口沿用已有 review-grant 机制，保留全部历史；在可信 observation 模式中不再误要求历史数量恰好三条，strict仍保持原规则。再次视觉审核会比上次77次估算多一次，总预估78次；这是估算而非新增累计配额。

0103 完整构建通过，BUILD_ID LJjh45ScyIFYkcN9paTbQ。首次本地练习检查在新稳定截图回调处遇到 tsx keepNames 注入的外部 __name 引用，未调用 Provider。0104 使用自包含对象方法保持浏览器序列化兼容，不向浏览器全局注入辅助函数；另把检查鼠标移到空白区，避免残留悬停。修复后的真实 p6/p7 × 1280x720/1024x768 四项检查全部通过，root实际查看 p7截图，第一题题干和全部选项完整、未提交且为0/2。原检查失败与前后的图片均保留，输出为 output/primary6-quiz-layout-inspection.json。

0103 SHA 89ef1bf159e08aa44cdae016ecf3d9574b6b9993bf3bb157a40f716777c7b130；0104 SHA db876d350bd5ad3b8d549919d9a4f560936d8e9cd4c4b479afca50156ee431c7。显式派生稿复审 manifest 为 native-visual-recheck-manifest.json，review grant SHA 2248056cc10f1496549dd7594c39e0adc85c8e70d9389819d58f9ff7d1c983c1，绑定完整五条历史账本 ef31baeeb5271821ccc326043e7e03c66c337209be87794e6efc63352fc74e7d。它不是新支付授权；实际付费执行仍须经过现有 completion authority 和执行审批。

0104 完整托管构建通过，BUILD_ID wWSwpM-H2K0nRA5OaVMjN，Native/Gateway 健康。最终 complete-learner-discussion-review 在进程创建前被自动审批拒绝：77次原估算变为78次，新增一次视觉审核付费调用需明确用户许可。因此没有新复审claim、没有消耗operator-review-grant、没有启动TTS/ASR或发布。下一步仅请求该新增1次DeepSeek视觉审核许可；余下1次教学文本审核与36组TTS/ASR沿用之前授权。当前已实现并真实验收的代码和原审计均保留。
