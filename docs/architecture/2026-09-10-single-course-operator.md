# 单门六年级数学测试课执行边界

本轮仅 `primary_6 / math / fraction_ratio_percentage / slot 1`。槽位的难度由冻结课程配置明确声明；不能凭 ordinal 推断难度。保留原来的三门已发布课程，不启动普通课程 worker，不自动扩大到三科。`generate_one_library_course.py` 只手动推进当前共享 owner 的一个启用槽位，最多 14 次题目 Provider phase 派发、1 个 OpenMAIC 课程实例；正常教学审核最多三轮由 Native 现有版本化质量政策限制。任何失败或不明结果保留原记录，不自动另建实例或增加审核轮次。

默认 `backend/content/learning_budget_policy.json` 仍为 disabled。临时政策文件位于忽略目录 `output/`，只有一个精确生产 scope 和固定开始/结束时间。用户现已明确要求移除本样课的人为累计额度拦截：使用 `aggregateLimitsEnabled=false` 后，金额、token、字符、媒体量和调用次数的全局/用途/用户/单课/授权累计配额均只保留记录，不再拒绝调用。原来 8 元生产、10 元全流程是内部自定限制，不是用户指定金额，当前样课不再采用该限制。issue/context/reserve/dispatch 仍核对身份、scope、有效期；已派发调用可在窗口关闭后结算或记录未知状态。

## 当前样课移除累计配额

使用原暂停文件执行下列命令；不要重新 make-policy。命令只把 `aggregateLimitsEnabled` 写为 `false`，保持 `enabled=false`、原 scope、价格、有效期及所有原限额字段不变，不访问数据库、不签发新授权、不派发调用。输出前后政策 SHA，后续实际预留记录新政策 SHA。原授权行保持不变，因此既有百度价格迁移审计仍有效。观察模式同样跳过价格表 `perCallMax` 的人为配额，不把计费表的 500k 输入预估误当模型技术能力；合法计量单位、安全整数、每次真实请求 `calls=1`、版本化价格及实际费用计算仍严格校验。Native 的任务输出边界和模型 SDK 技术限制继续执行。

```sh
/usr/bin/python3 backend/scripts/generate_one_library_course.py observe-budget \
  --grade primary_6 --subject math --skill fraction_ratio_percentage --slot 1 \
  --budget-policy output/primary6-math-single-course-budget.json
```

后端 `/internal/learning/budget/context` 返回 `aggregateLimitsEnabled: false`、`unsettledReservationCount` 和原授权价格。负责执行的操作者确认代码就绪后才启用同一政策并恢复同一实例；恢复要求无 `reserved/dispatched/unknown`，不会重放已付费调用。默认政策缺省该字段时仍保留原配额行为，普通 worker 保持停止。

## 价格版本

核查日期 2026-09-10。DeepSeek 输入按高峰、全部缓存未命中计上限，输出也按高峰计，实际账单可能更低。免费额度不提前抵扣预算。高峰 Pro 输入/输出为每百万 tokens 9/27 元，Flash 与视觉实验模型为 3/9 元。[DeepSeek 官方中文价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

北京 Qwen3-TTS-Flash 为 0.8 元/万字符，Qwen3-ASR-Flash 为 0.00022 元/秒；本次只允许这两个确切模型，地域需保持现有北京端点。[百炼官方价格](https://help.aliyun.com/zh/model-studio/model-pricing)

搜索供应商在生成新政策时明确选择，只授权选中的搜索价格。Brave Search 标价 5 美元/千次，临时政策按预算汇率 8 元/美元预留 0.04 元/次；这是保守预算换算，不是实时汇率或供应商最终账单。[Brave 官方计划](https://brave.com/search/api/)

百度搜索标准版为 0.036 元/次调用，增强版为 0.072 元/次。百度接入固定 `search_source=baidu_search_v2`、`edition=standard`；价格身份为 `baidu / baidu-web-search`，每个实际请求计 `calls=1, search_requests=1`。政策中的价格键为 `baidu-search-standard-2026-09-10`，价格版本为 `official-2026-09-10-baidu-standard.v1`，不能用于增强版。免费额度按天发放、默认优先抵扣，但预算仍按标准版目录价预留，不提前按零元结算。价格于 2026-09-10 核对。[百度官方计费说明](https://cloud.baidu.com/doc/qianfan/s/1mh4sv6c4)、[百度搜索 API](https://cloud.baidu.com/doc/qianfan-api/s/Wmbq4z7e5)

仅计量模式下，账本不再执行原来 20 次搜索的累计配额，Native 也不以原来每课 4 次搜索额度阻断。默认执行模式仍保留原搜索限制；两种模式均累计真实搜索记录，恢复不会重置历史。后端研究回执仅要求搜索次数为正整数且与完整记录数量相符，不再把 4 写成结构上界。公共 HTML 检索不满足正式生产的 API 配置门槛。

所有实际调用及本轮前置连通性探测继续记账，使用原冻结版本价格估算费用。仅计量模式不通过增加上限数字实现：原授权及其中历史限额完全不改，服务端明确跳过累计配额比较。原 Pro driver 的 16,384 输出限制同样是补丁 0058 自定的额度，并非模型技术边界，曾使修复回复截断；0079 在可信观察模式中取消该限制，直接采用 driver 已登记的模型输出窗口（当前 DeepSeek V4 Pro 为 393,216），预留与真实请求一致，结算仍按实际 usage。默认模式保留原限制。Native 的模型 SDK 与上下文真实容量、其他任务输出边界、并发守卫、未知结果保留、派发幂等与质量审核纪律仍执行；费用不影响既定模型、内容、交互、语音和审核要求，截断仍拒绝作为完成结果。视觉模型使用 `deepseek / deepseek-v4-flash-vision-exp`，单次最多输入 65536、输出 8192 tokens；图像必须经过实际图像 token 计量，不能用零 token 或假的收据。

## 执行顺序

在 OpenMAIC 自有配置中选择百度或 Brave，并配置对应服务端 Key，由受管脚本传给服务端，不能填到 Flutter、Student Web 或 App API。百度必须由 Native 报告 `providerId=baidu, productionMode=baidu_api`；Brave 对应 `brave, brave_api`。后端只接受这两组严格匹配的正式 API 配置，同时仍检查版本、模型和生成合同。普通健康接口报告 `runtimePolicy.webSearch` 的模式、配置状态和 `verification: configuration_only`；没有 Key 时，新的正式生成前置检查明确停止，普通健康接口及已有发布课仍可读取。配置 Key 只证明提供了凭据，不代表联网调用已验证成功。

Key 可从 [Brave 官方入口](https://api-dashboard.search.brave.com/register)申请。实际使用按版本化价格持续记账，不因供应商赠送额度提前计为零费用。

以下命令由负责实际执行的操作者运行。`make-policy` 仅用于尚未签发授权的新执行计划，须在年级、难度和 Native 补丁确定后绑定准确 target fingerprint。它不启用 API、签发授权或创建课程，并以原子 exclusive 创建拒绝覆盖任何已存在文件或符号链接；已有暂停文件的 `enabled` 和原有效期不会被重写。`pause-budget`、`close-budget` 仍保留必要的原文件更新能力。已经签发、暂停或到期的原任务不能靠换文件名切换供应商、续期或获得第二份预算；必须保留原账本和实例，另行完成精确、有审计的授权变更。

```sh
/usr/bin/python3 backend/scripts/generate_one_library_course.py make-policy \
  --grade primary_6 --subject math --skill fraction_ratio_percentage --slot 1 \
  --vision-provider deepseek --ttl-minutes 180 \
  --search-provider brave \
  --policy-output output/primary6-math-single-course-budget.json
```

新执行计划选择百度时使用 `--search-provider baidu`；不传此参数保持 Brave 兼容行为。该选项仅允许用于 `make-policy`，用于其他命令会直接拒绝，避免看似切换供应商却继续使用旧授权。此代码变更不修改现有 `output/` 政策、授权有效期或预算上限；原 Brave 授权没有百度价格键时，真实百度调用会被预算门拒绝。

每次正式生产 tick 及实际 Native 恢复之前，operator 都先读取 Runtime 搜索配置和当前政策，核对其唯一搜索供应商/模型；若原授权已存在，还通过只读事务检查有效期、scope 和冻结搜索价格。百度 Runtime 与 Brave 政策、或新百度政策与原 Brave 授权不一致时，会在题目生成之前停止，不能先消耗内容预算再等搜索阶段报错。该前置检查不调用搜索、模型或授权签发接口，不能替代实际调用前的原子预算门。

然后将同一个绝对路径通过 `LEARNING_BUDGET_POLICY_PATH` 传给本地 API-only 进程并重启 API；Native 的预算请求仍访问这台 API。仅给 operator 设置路径不够，常驻 API 的默认 disabled 会正确阻止派发。不要启动普通 worker，不要修改全站默认 JSON。执行前检查当前 Host/provider readiness；本脚本不偷偷运行付费探测。

```sh
/usr/bin/python3 backend/scripts/generate_one_library_course.py prepare \
  --grade primary_6 --subject math --skill fraction_ratio_percentage --slot 1
/usr/bin/python3 backend/scripts/generate_one_library_course.py run-to-review \
  --grade primary_6 --subject math --skill fraction_ratio_percentage --slot 1 \
  --budget-policy output/primary6-math-single-course-budget.json \
  --review-output output/primary6-math-review-request.json \
  --confirm-workers-stopped
```

`prepare` 只登记精确共享范围。`run-to-review` 关闭自动发布，等待真实课件质量、TTS、ASR 回听验证完成，输出最终课件与真实自动视觉审核收据的绑定文件。该文件的 `status` 为 `awaiting_visual_observation`，不是通过证据。

操作者逐页检查实际截图后，另写确认文件，仅包含 review-request 的 `schemaVersion`、`buildItemId`、`upstreamClassroomId`、`featureManifestSha256`、`visualReviewReceiptSha256` 和 `status: approved`。不得直接把生产器输出视为已完成人工查看。确认文件只追加本次操作者确认，不替代 Native 模型视觉审核、质量门槛、Host 检查或媒体验证。

```sh
/usr/bin/python3 backend/scripts/generate_one_library_course.py publish \
  --grade primary_6 --subject math --skill fraction_ratio_percentage --slot 1 \
  --visual-confirmation output/primary6-math-visual-confirmation.json \
  --budget-policy output/primary6-math-single-course-budget.json \
  --confirm-workers-stopped
```

发布仍走原来正式验证与发布服务；任何 snapshot 或真实视觉 receipt 不一致都会停止。

## 样课学习与结束

样课的必要讨论不能因默认政策关闭而被当作已完成。正常从学生端创建该已发布课的学习会话和 classroom launch（服务端完成正式版本绑定），再对这一个真实会话授权。`authorize-teaching` 会重查课程、当前年级、正式发布和媒体门槛，绑定同一政策的必要指导授权；仅计量模式下不会因原来的 2 元或累计 token/调用数配额拒绝必要教学，真实调用仍记录预留和结算。它不创建学习会话、不替孩子学习、不开放其他用户或可选互动，也不延长原政策有效时间。API 继续使用同一政策文件即可按实际请求重新加载。

```sh
/usr/bin/python3 backend/scripts/generate_one_library_course.py authorize-teaching \
  --grade primary_6 --subject math --skill fraction_ratio_percentage --slot 1 \
  --budget-policy output/primary6-math-single-course-budget.json \
  --learning-session-id ACTUAL_LEARNING_SESSION_ID \
  --confirm-workers-stopped
```

完成测试后关闭本次授权；已派发但结果未知的扣费预留仍保留。随后移除 API 的临时政策环境变量、恢复默认 disabled 并重启 API-only。已保存的课件与对话仍可按原身份读取；后续新的实时指导需要另有运营授权。

```sh
/usr/bin/python3 backend/scripts/generate_one_library_course.py close-budget \
  --grade primary_6 --subject math --skill fraction_ratio_percentage --slot 1 \
  --budget-policy output/primary6-math-single-course-budget.json
```

普通 worker 全程保持停止。本次一个测试样课不代表二至六年级全年课程库已准备完成。

遇到外部配置缺失、需要保留原失败实例等待后续处理时，使用 `pause-budget` 及相同单课参数。它仅关闭政策的 enabled，保留原授权、原时限和所有已结算/未知记录；与永久撤销授权的 `close-budget` 不同。需要时恢复 API 原有默认禁用配置。原时限到期后，现有 issue 接口不会续期，不能直接重开开关后声称可继续；需要留审计地处理同一任务有效期并保留所有历史费用；仅计量模式不会重新引入原生产 8 元、全流程 10 元额度。

## 原样课一次性切换百度

`plan-search-transition` / `apply-search-transition` 仅用于本次已通过内容审核、13 条内容派发记录、唯一失败 Native 实例的原六年级数学任务。复用原年级、技能、槽位和 `--budget-policy` 参数；plan 只读核对暂停文件、未撤销且仍有效的原授权、全账本不存在 pending/unknown 调用、原 Native job、现有内容与全部账本 SHA，返回 `transitionSha256`。apply 必须传同一计划的 `--expected-transition-sha` 和 `--confirm-workers-stopped`。

用户明确继续本任务后，可以额外传固定的 `--continuation-expires-at`（epoch 毫秒）；plan/apply 必须使用同一数值，不能分别按各自运行时间重新计算。它只允许当前时间起最多三小时、Asia/Shanghai 同一日内的一次续作，保留原 startsAt，并将旧/新有效期同时写入审计。首次 apply 时原授权仍须未过期；这不是通用的过期授权恢复功能，也不支持跨日或跨月续期。

迁移向原授权追加百度标准版冻结价，完整保留 Brave 历史价与每条已有账本，但当前政策只选择百度；已审计的新调用及价格上下文不再开放 Brave。服务对模板复用的窄例外只接受该审计精确绑定的价格集合，其他 scope、期限和额度不相符仍拒绝。不会新建授权、课程、Native 实例，或重置调用数、审核轮次和历史费用。

本次两份实际百度诊断报告（`output/baidu-search-probe.json` 与 `output/baidu-runtime-search-probe.json`）各按一次标准版目录价估算，共 0.072 元，独立绑定原文件 SHA 和供应商 requestId。直连诊断的请求版本与次数来自当次操作者已确认的单次标准请求；原响应文件未包含这些字段，不改写原文件补成供应商证据。此前迁移审计将其从当时的内部上限扣除，历史值为全局/单课 9.928 元、生产 7.928 元；这些审计值继续原样保存，当前仅计量模式不再执行这些累计限制。原账本其他探测授权的费用仍参与全局计算，两份外部诊断不伪造为新的账本调用，也不能充当课件联网引用。

apply 先在预算锁下 CAS 原授权并追加不可变审计事件，再原子更新政策文件。若文件启用失败，旧文件仍暂停；仅凭同一 SHA、相同原始账本和实例可完成文件安装，不会再次签发授权。执行后应让常驻 API 加载更新后的预算服务代码和原政策路径，再执行原 Native 恢复。当前仅计量模式不会因这些历史金额限额停止，也不削减模型、课程内容、深度交互、语音或审核。

## 已返回审核失败的精确恢复

`plan-content-recovery` 只检查原先同一 item 的六条阶段记录与冻结输入，输出不可变历史 SHA。`recover-content` 要求操作者传回这个 SHA、原单槽政策仍有效且普通 worker 停止；它在同一事务内登记 `mira.single-course.content-recovery.v1` 审计事件，保留全部旧记录，仅建立原 item 的逻辑 attempt 2。它只复用已验明输入、profile 与输出 SHA 的 outline，不复用旧题目、依赖这些题目的 lesson/reconciliation 或失败审核结论。

```sh
/usr/bin/python3 backend/scripts/generate_one_library_course.py plan-content-recovery \
  --grade primary_6 --subject math --skill fraction_ratio_percentage --slot 1 \
  --budget-policy output/primary6-math-single-course-budget.json
/usr/bin/python3 backend/scripts/generate_one_library_course.py recover-content \
  --grade primary_6 --subject math --skill fraction_ratio_percentage --slot 1 \
  --budget-policy output/primary6-math-single-course-budget.json \
  --expected-history-sha EXACT_REVIEWED_HISTORY_SHA256 --confirm-workers-stopped
```

恢复命令本身没有模型调用。outline 的复用单独记录为无 Provider 请求、无重复 token 计费的本地 checkpoint；原失败的六条记录和该复用记录都计入原总计 14 条阶段记录上限，实际新 Provider 调用继续共用原授权和费用账本；仅计量模式不再执行原累计金额限制。通常随后需要 raw、Host repair/编译、lesson、reconciliation 和独立审核五个阶段；Host 编译成功时其中四个阶段实际调用模型，有必要修题时仍受原上限约束。恢复不会创建第二个课程实例、提高审核名额或直接发布。

可以给原 `run-to-review` 命令附加 `--once`，只执行一次现有 `run_once` 后输出 `step_completed` 并退出。该事件不表示课件审核已完成，也不表示本次阶段一定成功；下一次运行仍重新检查持久化状态、范围和全部门槛。去掉 `--once` 才继续正常推进至待查看状态。

若 attempt 2 的 phase 4 已付费返回、只是本地规则实现误拒，使用 `plan-billed-reply-recovery` 检查，确认返回的 `historySha256` 后用 `recover-billed-reply --expected-history-sha SHA --confirm-workers-stopped` 执行。两者沿用上面相同的年级、技能、槽位及预算参数。固定纯本地 replay 程序从原响应归档重新编译，逐字段对齐真实 Provider 请求哈希、token 用量和账单证据，经过 Python 输出契约及进入 lesson 前的五题确定性验算。

执行前会把原完整失败行、该 attempt 的全部原记录、原 Provider 回复和校验产物写入 `backend/data/learning-provider-replies/recovery-<sha>.json`，以只创建、不覆盖的方式保存，再在准备事件中绑定文件 SHA。随后才复用已有 billed-checkpoint 恢复器封存同一个 phase 4 并续到 lesson；真实 Provider 计费字段不变，不新增派发、不创建 attempt 3，也不延长原硬截止。这个本地实现修复不构成独立 AI 审核通过，后续 reconciliation、独立审核、课件、媒体与发布门槛仍全部执行。

2026-09-10 本次实际恢复记录：同一 `catalog_build_item_ddaa5bc7be54a293272cc3e3` 的 attempt 2 phase 4 已由操作者成功执行 plan/apply，阶段记录仍为 10 条，恢复新增 Provider 调用为 0，下一阶段为 `lesson_text`。原 attempt 2 四条记录的历史 SHA 为 `086fa4b0b6d409c82638609a02a3be609819935b43ab53aa2b96f7bf973b0a59`；完整审计文件 SHA 为 `068068918eaf6ca18dfdeb4aea5ba9f895f199772a826c2c2151e427dfd623fa`；真实源回复归档 SHA 为 `bd17aedc790275276bf65c563aac88108b3b649794e333c89df2fc6d9115a35c`；本地接受的 checkpoint SHA 为 `3351d2d2181c80e28e8a253a766cf92a4c8d5942b1a6e31d9b1e520fbfb06f86`。这些只证明本次本地恢复完成，不表示后续独立审核或正式发布已经完成。

## 课件派发前就绪检查的恢复

`plan-runtime-preflight-recovery` 和 `recover-runtime-preflight` 沿用相同单课参数，后者还需 `--expected-history-sha` 与 `--confirm-workers-stopped`。它只处理已通过完整内容/独立审核/Host 证明、尚无任何 Runtime 实例、共享 owner 在 `generating_content` 被标记为 `preparation_generation_failed` 的已诊断情况。读取当前实际 Native 就绪信息后，只有严格就绪才允许 apply；原 owner、失败事件、内容收据和 Provider 记录摘要会保存到内容寻址审计文件并绑定新事件。只恢复 owner 的推进资格，不改内容已通过状态、不再生成题目、不新增调用或续期预算。

后续精确的 `OpenMaicRuntimeServiceError(openmaic_formal_generation_not_ready, 503)` 会走 30 秒可重试等待，而非误判为永久生成失败；其他 Runtime 契约/语义错误仍保持原终止处理。就绪检查本身不豁免服务端正式派发门槛。

## 已保存完整课件的结果接回

Native 的 `recover-formal-saved-stage.ts` 经 prepare/inspect/complete 完成正常 QA、视觉与语音验证，并真实提升原 job 为 succeeded 后，使用 `reconcile-saved-stage` 接回同一个后端 Runtime。该命令核对原 completion/source-job/prepared-snapshot/promoted job 的 SHA、request/formalInput/session/stage、课程范围及 Native API 成功证据，保存原 Runtime/owner 的不可变审计，仅在需要时复用 `resume_formal_candidate_after_validator_fix`，再执行原 `generation_status` 验证。它不创建 Agent、不搜索、不派发课程、不 claim/推进 owner、不发布。

```sh
/usr/bin/python3 backend/scripts/generate_one_library_course.py reconcile-saved-stage \
  --grade primary_6 --subject math --skill fraction_ratio_percentage --slot 1 \
  --runtime-id ORIGINAL_RUNTIME_ID \
  --completion /ABSOLUTE/NATIVE/data/formal-saved-stage-recoveries/ORIGINAL_JOB_ID/completion.json \
  --confirm-workers-stopped
```

只有同一个 Runtime 正常验证为 ready 才返回成功。原 `run-to-review` 随后处理媒体回执并停在人工视觉检查；`publish` 仍须单独执行。若再验证失败，保留新错误和原审计，不能借相同 completion 重复清除失败。

若同一快照的 `complete` 仅在浏览器检查阶段失败，修复检查器后可使用 Native `complete-browser-recheck manifest.json`。在原 manifest 上增加 `browserRecheck`，包含 `schemaVersion: mira.formal.browser-only-recheck.v1`、原质量目录的 `qualityIdentitySha256`、原 `complete-<snapshot>.claim` 的字节 SHA `priorClaimSha256`、原 `<snapshot>.json` 的字节 SHA `priorResultSha256`，以及 `inspectorSourceBundle()` 返回的 `inspectorSourceSha256`。该 bundle 包含 `mira-formal-scene-inspector.ts`、`mira-formal-scene-dom.ts`、`mira-formal-exploration.ts` 的规范化路径及字节 SHA。

入口必须证明原结果全部是 Browser check 问题、没有成功 completion 或 Provider/视觉派发产物，并通过内部预算接口确认同一授权没有未决调用、最后真实派发时间早于原 claim。检查器修复不允许清除原 claim；新 claim 独立绑定上述完整证据，随后执行原有完整浏览器、教学、视觉及语音验证。这里的检查器复查本身不产生模型调用；进入正常质量尾段后仍可能产生真实收费调用，不能把本地复查通过当作课程已验收或已发布。

## 同一门样课的操作有效期续作

用户已明确要求完成这一门样课并移除内部累计额度。观察模式下使用 `plan-budget-continuation` / `apply-budget-continuation` 延长同一授权的操作窗口；不另发生产授权，不重新计数，也不改变价格、scope、limits、原 policy SHA 或任何费用记录。该入口只接受原六年级数学标准样课，以及原 policy 已有的同课、同学生、同会话必要教学授权。新增教学会话仍通过 `authorize-teaching` 的正常发布与身份验证入口。

先暂停原 policy、停止手动派发并保持普通 worker 停止，确认没有未决调用，再执行只读 plan。例如本次续至 2026-09-10 20:30（上海时区）：

```sh
/usr/bin/python3 backend/scripts/generate_one_library_course.py plan-budget-continuation \
  --grade primary_6 --subject math --skill fraction_ratio_percentage --slot 1 \
  --budget-policy output/primary6-math-single-course-budget.json \
  --continuation-expires-at 1789043400000
```

使用同样参数执行 `apply-budget-continuation`，增加 `--expected-continuation-sha <plan 的 SHA>` 和 `--confirm-workers-stopped`。plan/apply 的时间戳必须完全相同，且处于同一天；已到期但未撤销的原授权也可在上述用户继续授权下续作。apply 先 CAS 更新原授权到期时间并保存不可变审计，再启用原 policy 文件，随后受管重载 API。文件写入失败只能重放原 SHA 完成安装；账本或业务状态改变时需要重新核查，不能把已派发结果清零。原 Brave→百度价格审计通过这条只改有效期的链继续验证。

课程已具备完整审核和媒体回执时，`run-to-review` 输出待观察结果、`publish` 处理发布均不再要求仍有效的生产付费窗口；质量门槛保持。实际新增模型、TTS、ASR 调用和必要实时教学仍须在对应授权窗口内执行。

发布后，可对原新建的隔离六年级 fixture 执行以下本地预检，避免浏览器首次消费票据时尚未具备该会话的必要教学授权：

```sh
/usr/bin/python3 backend/scripts/setup_grade6_student_smoke.py prepare-teaching \
  --credentials /ABSOLUTE/PRIVATE/FIXTURE.json \
  --confirm-sample-published --confirm-workers-stopped
```

该命令只使用正常 parent 配对码、student 配对、today、start session 和 openmaic-launch API。学生 token、task/session ID 保存在原 0600 文件，终端只显示安全 ID；不读取浏览器、不注入 cookie、不打开或保存 launchUrl、不消费课堂票据。随后对输出的 sessionId 执行原 `authorize-teaching`、受管重载 API，再用 `pair-code` 给独立浏览器生成新短码并从 `/pair` 正常进入。正式绑定关联 family/child/learning-session，不依赖预检登录 token 的有效期；浏览器会恢复同任务已有学习会话并取得自己的新票据。这验证的是经过精确预授权后的真实课堂进入和互动。

## 已保存 ASR 的比较器复核

若 WAV 和 ASR 转写都已成功保存，只因旧数学读法比较器低于 8500 被拦，可复制同一修复 manifest，加入原 `asrSourceRequestId`，执行 Native `revalidate-audio-comparison manifest.json`。此命令不调用 Provider，不替换音频或转写，只核对同一 job/session/stage/snapshot、原 TTS/ASR 记录、WAV、原转写及当前旁白的 SHA，按当前数学比较策略重算；仍低于 8500 时拒绝。通过后在 `data/formal-audio/comparison-revalidations/` 保存新的独立证据，原 ASR 的分数和记录字节保持不变。

将返回的 `asrComparisonRevalidation` 对象原样加入该 manifest，再执行 `complete-audio-comparison-tail manifest.json`。它重新核对原始文件与比较器源码 SHA，要求同一快照已有真正通过的质量回执，并强制 `cachedQualityOnly: true`，缓存缺失即拒绝。通过的原音频记录直接复用，仅缺失段会调用 TTS/ASR；这是可能收费的音频续作入口。最终 ASR 回执附带完整侧证，后端验证它与同课的教学质量、会话、音频及文本身份一致。该入口不伪造 `operatorRepair`、不重跑 Agent，也不替代后续正式发布门槛。

同一课堂有多条被旧比较器拒绝的记录时，分别以各自原 `asrSourceRequestId` 执行纯复核，然后将返回的引用放入同一 `asrComparisonRevalidation: [reference1, reference2]` 数组。引用必须全部来自同一 job/session/stage/snapshot，且绑定当前比较器源码；旧源码下的侧证需重新纯复核。所有引用在音频续作前逐条验证，重复 ASR ID 被拒绝，排序后的组合 SHA 绑定新完成 claim，不能仅更换数组顺序绕过已有 claim。原先只含一个对象的 manifest 继续兼容。

若后续某一段 TTS 确认为 failed/ambiguous，使用同一原 job manifest 的 `ttsSourceRequestId` 和逻辑 `asrSourceRequestId` 执行 `repair-audio`。单次物理请求固定为 `.repair1`，以原 job 的 paid binding 和稳定命名空间计费；原结果未知的记录和费用未知项保持，不能自行释放或记为零。该操作可能产生真实 TTS/ASR 费用，且不自动重试失败或结果未知的 repair 子请求。

单段修复成功后，在保留原比较引用数组的尾续 manifest 加入 `audioRepair: {asrRequestId, receiptSha256}`（逻辑 ASR ID 及 repair 返回的收据 SHA）。CLI 核对实际 `repairs/<ASR-ID-SHA>/source.json`、`promotion.json`、物理 `.repair1` 与逻辑记录、WAV、转写和当前课堂旁白，要求原比较引用对应的 consumed claim 已存在；只有这些实际证据验证通过，才以组合 SHA 创建新的音频续作 claim。manifest 时间戳或任意 nonce 不能打开新续作；原 claim 和所有失败审计保留，QA 仍只读同一已通过快照缓存。

同一课堂已有多段真实修复时，可使用 `audioRepair: [repair1, repair2]`，保留此前各段引用并追加新成功的 repair 收据。每条都需实际验证，重复 ID、空数组及跨课堂原始记录被拒绝；排序后的全部修复证据与原比较引用共同绑定 claim。单对象和只装入该对象的数组沿用相同摘要，不能通过包装方式重开已消费的续作。

数学原段和固定 `.repair1` 都因实际分数读法错误未通过时，可在同一段的 `repair-audio` manifest 加入 `pronunciationRepair: {failedRepairTtsSha256, failedRepairAsrSha256}`，绑定已保存的 `.repair1` 两条记录。入口重新核对原段、父 source、两次低分转写及失败 repair 的 WAV，且新规范化读法必须确实不同，原 repair 也尚未使用该规范化输入。只允许固定 `.pronunciation1` 物理请求，仍使用原 paid binding；失败或结果未知的该子请求不能重新派发。

成功前必须证明 TTS 的 `providerPronunciation` 与当前读法策略、原文/转换文本 SHA、实际字符数一致，ASR 仍须达到 8500。新审计保存在原 repairs 目录下的 `pronunciation1/` 子目录，父 source 和失败 records 保持。成功后尾续引用形状为 `{asrRequestId, receiptSha256, repairKind: 'pronunciation1'}`；可与此前 repair1 引用一起放入 `audioRepair` 数组。课堂显示内容、logical request、已通过的 QA 和比较器复核引用不因此改变。
