# 单节英语课明确要求 3D 与小游戏

用户授权重新生成一节语文或英语课，要求同时包含 3D 和小游戏，并明确授权本任务所需 DeepSeek 调用无需再次确认。本次选六年级英语 `past_future / slot 1`，主题方向为昨天的活动与明天的计划。

## 架构与合同

沿用 Backend 冻结教学目标、OpenMAIC Pro 生成与独立审核、TTS/ASR 和正式发布链路，不新增 App API。原 playful v1 的语言课不强制 3D；因此新增精确的 v2 opt-in，而不是改写已保存的 v1 含义。

v2 为 `mira.openmaic.playful-learning.v2` / `mira-primary-playful-3d.v2`，保留 v1 字段，但 `threeDUsage=required`，并增加 `minimumThreeDScenes=1`。它要求独立 `visualization3d` 互动页与独立 `game` 页。Native 主提示、逐页内容与动作提示、独立审核接收同一冻结 v2 context；结构检查只证明页面存在，真实几何、教学状态联动、操作、错误反馈、重玩和 pointer/touch 验收仍走原质量门槛。

单课 operator 的 `--require-3d` 在进程内选择 v2，并生成独立 target fingerprint。默认仍为 v1；Backend 和 Student Web 严格接受两个完整版本。Native 健康响应新增 `runtimePolicy.formalGenerationSupportedProfessionalPolicies`，opt-in 在花费前检查确切 v2 能力。

相关实现：Backend 的 playful/media/client、preparation contract、runtime service 与 single-course operator；Student Web 的 playful/runtime Zod 合同；Native 补丁 `0109-mira-explicit-3d-game-policy.patch`。无 Provider key 或权威答案进入学生端。

## 本次运行

普通课程 worker 已停止。本课操作目录为 `output/english-3d-20260915/`，所有命令必须重复 `--require-3d`。临时精确单课 policy 设置 `aggregateLimitsEnabled=false`，记录实际费用，保留有效期、scope、幂等、并发和未知结果保护。

当前常驻 API 使用已启用、仅计量的 `learning_classroom_policy.json`；它可按数据库冻结的新单课授权核验 scope、有效期和价格，无需替换该政策或影响既有课堂续期。历史五条 unknown 记录保留，其中四条有原传输终止审计；本次没有清除或伪造结算。

新 build item：`catalog_build_item_0da6d2c962178ac8fa1b9842`。本文件记录实现与操作范围，不代表课程已经生成、审核或发布；最终结果以本课实际收据与学生入口证据为准。

## 此前独立预览（历史记录）

完整 `run-to-review` 命令被自动审批拒绝，未执行也未派发正式制课；拒绝理由是百度搜索和阿里云 TTS/ASR 不在本次明确的 DeepSeek 授权中。原正式单课政策已暂停，普通 worker 保持停止。

采用只向 DeepSeek 发送原创普通英语教学要求的安全替代方案：两次 DeepSeek 调用（初稿与修复），生成独立 `output/english-3d-20260915/lesson.html`。随后修复局部几何投影/遮挡、拼词判题、键盘事件和重玩问题，未导入现成游戏。原回复与修改前稿保留，专用 DeepSeek 授权已关闭。

预览地址 `http://127.0.0.1:8788`，仅本机服务，CSP 禁止外部连接。真实 Chromium 1280×800 与 390×844 检查通过：三种教学状态、八个旋转角度、图像精确重置、两关拼词成功、错误动词反馈、键盘、触摸旋转、触摸拼词、重玩、四题检查与再练，无横向溢出或脚本错误。验收记录为 `completion-preview.json`。它是无配音的独立预览课件，尚未通过完整 TTS/ASR、正式发布或学生课程库入口，不应把预览验收当成正式发布。

## 用户补充授权后继续

用户在已明确列出百度搜索、阿里云配音/回听和必要插图的确认问题后回复“允许”。保留原拒绝记录，并仅将同一正式单课 `budget.json` 的 `enabled` 从 false 改为 true，scope 与原有效期不变；审计见 `full-pipeline-resume-approval.json`。同一 `--require-3d` 单课 operator 已开始 `run-to-review`，普通课程 worker 仍停止。此阶段尚不代表正式发布完成。

### 英语规则桥接修复

正式内容前两阶段已产生并保存真实模型结果；第三阶段在付费派发前被本地目标规则桥接误拒。英语动词表的 Python tuple 经 JSON 传递变为 list，普通对象相等判断将无损序列化误认为规则漂移。`formal_question_preflight_cli.py` 改为严格 canonical JSON 比较，既接受同一规则的序列化往返，又拒绝布尔/数字或字段值的变化，不修改课程目标和答案标准。原失败完整审计为 `preflight-failure-state.json`；phase3 没有 intent/response 或预算 reservation，前两阶段费用已结算。修复后本地评估返回 q2/q4 时间词问题，继续正常模型修复后同样被拒；进一步核对发现边界明确登记 `last week`，公开 objectivePolicy 没有排除它的时间词枚举。这是 solver 对已登记一般过去时表达的遗漏，需要仅为 `past_future` 补齐该已登记时间词的判断，其他时态与未登记时间表达仍拒绝。已保存的模型题面、答案和响应原样保留，修复后走纯 Host 重放及原独立审查。

## 正式课件与播放器验收

同一 Native 会话生成《时间词侦探:过去与未来时态练习》9 页：4 页讲解、2 页测验、时间词图解、12 张词卡配对游戏，以及 Three.js 几何体/相机/OrbitControls 构成的 3D 昨天小店。规则与不规则过去式、过去/将来时间词均服务于冻结的 `past_future` 目标。正式课堂 ID 为 `stage-9uUmwRu0qn`，唯一 Runtime 为 `omfc_vMaH7OymxhbaBU_vfjt0Oukxxoga73l31eNXUOoRWM8`。

原始保存快照 SHA 为 `7cbbdd51894467eb14a3f41bd1bfceb12df0d0d68d3824b7557f2b789c647e92`；正式评审投影 SHA 为 `c5b53c98125cdd51f95afb4513ee07e089ac271ec19dea2a27f5d3864baa0d9c`。两者采用不同的既有投影，不能混用。正式质量收据 `3df88b86b88dc4dedf7a59e4fc0575073b88f0127cd03f5da4bcbef01098b6ba` 已通过。真实 SlideCanvas、QuizView 和交互 iframe 的 1280×720、1024×768 共 18 项检查通过；游戏和 3D 另做 390×844 触屏操作、重置与重玩验证。

补丁 `0110-mira-trusted-touch-interaction-bridge.patch` 修复播放器对按钮 `touchstart` 操作的记录：保留可信手势、私有端口、可见反馈变化与关闭/隐藏屏蔽，并避免兼容 click 重复记录。课件 HTML 保持原样，因此已有音频身份不发生变化。12 项聚焦测试、原课件真实触屏/鼠标/Enter 验证及重建后的 18 项正式检查通过。受管服务通过独立进程会话启动，避免被命令会话清理；普通制课 worker 保持停止。

## 音频恢复与英语拼读

本课有 43 段旁白。第 15 段首次 TTS 在约 120 秒后结果未知，原请求和 unknown 费用占用保留。现有 `repair1` 的首次本地执行因 operator 包装器缺少 `MIRA_BACKEND_INTERNAL_URL`，在 6ms 内、任何预算预约/Provider 派发前退出。修复包装器默认地址与正常生产入口一致后，通过精确源文件 SHA、全账本零派发证明和不可覆盖失败归档恢复同一未派发的 repair1 身份，未改原 unknown 账本。该段真实配音及 ASR 已完成，回听相似度 10000，修复收据为 `757ed057116c9e392752c4b36250f78bc16929f8b6a6019c10927d453eb68d19`。

后续第 27 段把字母间连字符读成“减”，正式 ASR 8333 未通过；逐段复核还发现第 17 段虽然整体 ASR 9215，仍将 `-ed` 读成“减 ed”并误识别 `sing`。这两段原音频、原分数和转写完整保留。新增英语物理 TTS 输入规则仅处理明确拼写串和教学后缀，不修改逻辑旁白、课程快照或常规 8500 门槛。高分片段的修复还必须通过原 WAV/转写哈希与明确误读证据；新录音须保持严格英文词序并排除“减”误读。

当前正式发布尚待音频尾段和最终发布收据。原失败与恢复记录位于 `output/english-3d-20260915/` 及 Native 的 `data/formal-saved-stage-recoveries/omformal_6aed1debc561e63eaa4c0709/`，不得用独立预览替代正式发布。

### 混合语言 ASR 独立诊断合同

第 27 段已用明确字母拼读完成一次真实 repair1，ASR 10000。第 17 段新 WAV 的后缀误读已消失，但正式 ASR 强制 `zh` 后把 `eat 和 sing` 识别为 `it a thing`；严格词序验证拒绝晋升，原 9215 分不视为本段足够证据。

计划补丁 0112 仅增加服务器恢复工具的单次自动语言 ASR 诊断：重核原高分减号误读、同源 repair1 音频与物理输入证明、原 repair1 ASR 高分但英文词序失败，固定 `.repair1.diagnostic1`，复用原 WAV、0 次 TTS，仅省略 language，绝不发送期望文本或词表。独立预算、原始转写、body hash 与采纳收据均保留。采纳仍要求 8500 与严格英文词序，通过明确收据绑定；普通与数学 ASR、学生 API、课程逻辑旁白均不变。计划文件为 Native audio、audio-repair、窄诊断 helper、恢复 CLI、completion verifier 与聚焦测试。

2026-09-15 在线核实：[阿里云 Qwen-ASR API 官方文档](https://help.aliyun.com/en/model-studio/qwen-asr-api-reference) 的 DashScope `asr_options.language` 说明，中英等多语言混合音频应省略 language。现有 `zh` 为合法单语言参数；诊断不需要迁移域名或更换模型。

### 最后音频检查

第 17 段同 WAV 自动语言 ASR 9803，完整保留 `eat / sing / yesterday / tomorrow / ed`，独立收据 `38bbaaf6716a8cc85262456fe594a7557bbab3ba238df557f5a56f386cfa7dd3` 已零调用采纳，promotion `e81d91a9e7cc8ed3ee09b88aec2418d903a6cd2c2becbc81053a1eb41a3b90b1`。随后原 43 段 TTS/ASR全部完成，原 Native completion `373b66b2f2335b225b54addd64f42f6d9134bdb8fc2c55e89776809807e5a1d1` 保留。

最后逐词检查发现第 30 段 ASR 8888 对 `ate / e-a-t / a-t-e` 存在字母歧义，尚未正式发布。计划仅增加 operator 逻辑音频的同 WAV 自动语言 ASR 核验和显式采纳，再用禁止任何 TTS/ASR 派发的只读依赖重算 formalAudio 与完成收据；保留旧成功报告和源失败审计。文件范围为窄英语音频诊断 helper、独立成功后音频 reconciliation 脚本，以及必要的服务器诊断 profile 导出。课程旁白、TTS WAV、九页快照、答案、Student API 和普通生成路径均不变。

## 最终结果：已发布

《时间词侦探:过去与未来时态练习》已正式发布：六年级英语，9 页，第 4 页为词卡小游戏、第 7 页为可旋转/缩放/切换动作的真实 3D 场景，43 段配音和逐词回听检查全部通过。第 30 段同 WAV 自动语言 ASR 10000；原诊断与旧成功完成报告保留，零调用刷新完成收据为 `252ba5b38a47425813999ff0a06c2d0f35c7a032ee2a16bf2be0bfe98ae82b70`，最新音频收据为 `2c6032d2eff503f80953a9591bb49860195d7199d34bd6051d85fdee9d088e06`。

原 Backend ready 收据仅包含不变的课件；当时尚无 Backend 音频导入任务，因此没有重置 Runtime 状态。正常 run-to-review 重新读取最新 Native 音频并通过发布门槛，旧恢复事件保留历史。发布收据为 `c72e22e4b0a77d6c9be5105e8648573780519e1b5407110cd874fc453ebd647f`。Student Web 已实开课程详情、开始上课、加载完整互动课堂；老师讲解已启动并推进，现暂停供用户继续。制作 budget 已关闭，未结费用证据保留，学生课堂授权不受影响。实际课堂入口：http://localhost:3000/lesson/task_9d3e0cce7ba54ed581144a525b15a00e/classroom。

受管 Native 已构建并运行 0112，BUILD_ID `RZenpCRQJpywuwmjhYwVa`；0113 只增加被独立 operator bundle 使用的诊断导出和测试，本次诊断通过该 bundle 执行，普通运行路由不变。最终证据汇总在 `output/english-3d-20260915/completion-final.json`。
