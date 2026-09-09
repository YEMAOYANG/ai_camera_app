# 年级触发备课 Checkpoint 2：三科内容候选生成设计

## 1. 状态与目标

本设计是《年级触发的自动备课与发布设计》的第二检查点。采用用户确认的方案 A：先为一年级语文、数学、英语各生成 1 门真实内容候选，共 3 门；三门全部通过自动门禁后，同一个共享构建自动扩展到一年级完整 30 门内容候选。

Checkpoint 2 只建立“正式内容候选门”，不生成旧版 5 场景 LessonPackage，不生成完整 OpenMAIC Runtime，不调用 TTS/ASR，不激活 release，也不把家长计划标记为 `ready`。

本检查点完成时应得到：

- 一年级语文 12、数学 9、英语 9，共 30 门经过内容门的候选课程；
- 每个能力边界恰好 3 个语义不同的变体；
- 可恢复、可审计、不会因崩溃自动重发同一 Provider 子调用的后台生成链；
- 家长端可看到真实的内容候选进度，但学生端仍不能消费候选 release；
- 后续 Checkpoint 3 可从同一 build 的 `course_ready` 项继续制作 10 场景完整课堂、Qwen3-TTS、自动验证与年级级原子发布。

## 2. 已冻结边界

### 2.1 本检查点包含

1. 将 preparation runner 从 create-only 扩展到真实的 content-only 生成。
2. 修正逐门工作单元的租约、deadline、正常续跑和崩溃恢复。
3. 建立一年级三科内容门，先做 3 门 canary，再自动扩展到 30 门。
4. 增加内容候选计数、分科计数、canary 证据和安全可观测性。
5. 保持保存年级、查询计划、Today、assign 和学生请求零生成调用。
6. 完成测试环境全链验证后，才允许在开发环境显式打开一次 canary。

### 2.2 本检查点不包含

- 5 场景受控 LessonPackage 的生成或发布；
- 10 场景完整 Runtime、HTML 小游戏、3D、多 Agent 或逐场讲稿；
- Qwen3-TTS、Qwen ASR、Kimi 课堂对话或任何媒体人工/自动批准；
- 年级级 release pointer、自动发布、学生 launch 或正式学习完成回写；
- 一至六年级全量生成；
- 日常排课触发生成；
- 将候选内容描述为“正式课程已完成”或“学生可以学习”。

## 3. 两阶段执行

### 3.1 Phase 2A：三科 canary

canary 固定使用一年级每科第一个注册能力边界、第一变体：

| 学科 | skillId | variant |
|---|---|---:|
| 语文 | `pinyin_syllables` | 1 |
| 数学 | `number_sense_20` | 1 |
| 英语 | `letters_sounds` | 1 |

三个 target 都属于后续 30 门正式候选，不建立一次性临时课程或第二套 build。

只有三门全部满足以下条件，runner 才自动解除 canary 限制：

- 生成身份、grade、subject、skill、boundaryVersion、variant 与 build item 精确一致；
- 5 题角色合同、答案、题型和内容哈希全部通过；
- 学科技能级确定性门禁通过；
- 隔离复核回执通过；
- 三门没有终态失败，且没有 package、media、Runtime 或 release 写入；
- 每个 item 的 logical content attempt 不超过一次初始尝试和一次自动修复尝试；每次 attempt 内的 Provider 子调用还必须受第 5.3 节的 named-phase 派发账本约束。

若任一 canary 在两次内容尝试后仍失败，扩展立即停止，计划进入明确 `failed`。已经生成的不可变候选和审计记录保留，不激活、不删除、不伪装为成功。

### 3.2 Phase 2B：扩展到 30 门

canary 通过后的下一次 runner tick 自动继续同一 build：

- 语文：4 boundaries × 3 variants = 12；
- 数学：3 boundaries × 3 variants = 9；
- 英语：3 boundaries × 3 variants = 9；
- 总计：30。

选择顺序固定为“分科公平、边界顺序、变体顺序”：优先让三科的完成数保持均衡，同科内按课程边界注册顺序、再按 `variant_ordinal` 递增。不能依赖字母排序恰好得到 canary，也不能连续消费完一科后才开始另一科。

30 门全部通过内容门后：

- build items 保持 `course_ready`，`package_attempt_count=0`；
- preparation plan 保持 `status=running`；
- plan 进入 `stage=building_classrooms`；
- 写入 `content_generation_completed_at`；
- `ready_course_count` 仍为 0；
- `progress_percent` 固定为 35，而不是 100；
- release 仍为 candidate/draft，不调用 `activate()`；
- Checkpoint 2 runner 不支持 `building_classrooms`，因此在该阶段安全停住，等待 Checkpoint 3。

## 4. 架构流程

```text
保存年级请求
  -> 只 reserve/reuse preparation plan（零 Provider）
  -> preparation runner claim plan
  -> planning: create/reconcile shared catalog build
  -> generating_content: claim exactly one content item
  -> durable logical requestId + attempt count
  -> one named Provider/Host phase per tick + durable dispatch/checkpoint
  -> host deterministic validation + isolated verifier receipt
  -> persist immutable course + mark build item course_ready
  -> reconcile all matching child plans from shared build counts
  -> release plan lease and schedule next item
  -> first 3 exact targets pass
  -> automatically widen eligibility to all 30 targets
  -> 30/30 content candidates
  -> hand off to building_classrooms, stop
```

唯一内容权威是 catalog build item。preparation plan 只保存可重建的汇总进度，不复制 Provider 尝试身份，也不自行产生 `.retryN` requestId。

`planning` 创建 build 时必须使用一个年级、三科、每 boundary 三变体以及 `allowPartial=false`。Checkpoint 2 虽然不会激活 release，但不能把允许缺科、缺 boundary 或缺变体的 partial build 留给 Checkpoint 3。

## 5. Catalog content-only 合同

catalog build 必须持久化 `execution_mode`：

- 历史与 operator build 默认为 `full_pipeline`；
- preparation Checkpoint 2 build 精确为 `content_only`。

`content_only` 不是请求参数层的提示，而是数据库权威。现有 catalog `run()`、内部 run route 和 `activate()` 必须在读取 build 后拒绝 `content_only`，即使调用者拥有内部 token 也不能进入 package/media 或发布。只有 Checkpoint 3 的新迁移与合同校验才能把一个 30/30 的 content-only build 交接给课堂阶段；Checkpoint 2 不提供修改 execution mode 的 API。

### 5.1 新服务边界

在 `LearningCatalogReleaseService` 增加内部 Python 服务方法，不新增公开生成 HTTP API：

```python
advance_content(
    build_id: str,
    *,
    heartbeat: Callable[[], bool],
) -> ContentAdvanceResult
```

eligible targets、canary phase、subject/boundary ordinal 和 stage ceiling 全部从 build 的 immutable target manifest 推导；调用者不能传任意列表扩大范围。

一次调用最多推进 1 个 item 的 1 个持久化 phase；一次 runner tick 最多发生 1 个 Provider HTTP 子调用。该方法只允许：

1. 领取新内容 item 或恢复未完成的 content gate；
2. 根据持久化 phase graph 最多推进一个 Provider/Host phase；
3. 在所有生成 phase 完成后持久化 immutable course identity；
4. 执行或恢复内容 gate；
5. 将 item 置为 `course_ready`。

明确禁止：

- `claim_package_for_item()`；
- `lesson_package_service.generate()`；
- media worker；
- OpenMAIC Runtime；
- `activate()`；
- 修改 active release；
- 把 `course_ready` 改写成完整 `ready`。

现有 `run()` 保留 operator/catalog 原行为，但 service 与 repository 的 package claim 都必须先读取 build，并只接受 `execution_mode=full_pipeline` 且 stage ceiling 允许 package 的 build；对 `content_only` 返回稳定 409/不可领取。`activate()` 同样在事务内读取 build 权威后硬拒绝 `content_only`。preparation runner 只能调用 `advance_content()`。

`advance_content()` 依赖 capability-restricted `ContentCandidateGenerator`。该接口没有 `enqueue_classroom` 参数，并在内部永久固定 `enqueue_classroom=False`；不能把“不要创建课包”的安全性寄托在调用者记得传一个默认值相反的布尔参数上。

### 5.2 内容 item 领取

新增 repository 的 `claim_next_content_item()`，可选择两类工作：

**新生成或生成恢复**：

- `pending + attempt_count=0`；
- `failed + attempt_count=1 + content_gate_status=failed_deterministic`，且前次要求的 dispatch 全部 `succeeded`、immutable course/checkpoint 与安全 generation feedback 回执完整时，开始唯一一次自动修复；
- 尚未发生 Provider dispatch 的安全前置失败；
- `content_phase` 仍处于 named Provider/Host 生成阶段的 stale `processing`，但只有当前 logical attempt 的 dispatch ledger/checkpoint 明确证明可以无重发恢复；是否存在上一 attempt 被拒绝的 course pointer 不参与工作分类。

**已持久化课程的 content-gate 恢复**：

- `course_id/course_version` 已存在；
- `status=processing`；
- `content_phase=host_gate_pending|host_gate_running` 且 `content_gate_status=pending|retry_wait`；
- `active_package_request_id IS NULL`；
- 不再次调用 Provider，只重新读取 immutable course 并执行内容 gate。

它必须：

- 过滤由 build manifest 推导的 exact `eligible_targets`；
- 先锁 owning release sentinel row，再锁 build row，然后检查 execution mode、stage ceiling、canary manifest、inflight item 和当前内容回执；release 是稳定 mutex，因为 build 对它有强制 FK 且不能先存在；
- 按持久化的 `subject_ordinal + boundary_ordinal + variant_ordinal` 公平选择，不能按 skillId 字母顺序推断教学顺序；
- 排除 `course_ready`、package/media/ready item；
- 遇到任意 `package_attempt_count>0`、`active_package_request_id`、package identity 或 release item 时 fail closed，不能继续 content-only build；
- 同一个 build 存在未 stale 的 content `processing` item 时不并行领取第二个；
- 新付费尝试仅在 `pending` 或 `failed` claim 时增加 `attempt_count`；
- logical requestId 只用于身份绑定，不得被描述为 Provider 幂等证明；
- 使用 item 级 lease token、行锁与 CAS，两个计划或两个 runner 不能领取同一 item；
- course 持久化、gate 通过、拒绝和失败写入都必须同时匹配 item lease token 与 active requestId。

工作分类由 `content_phase + content_gate_status + logical attempt` 决定，绝不能重新退化为 `course_id IS NULL/NOT NULL` 二分。第一 attempt 的 immutable course 若被 gate 确定性拒绝，其 course/dispatch/checkpoint 记录永久保留；第二 attempt 生成新的 immutable course identity，并只在规范化 course checkpoint 完整后以 CAS 更新 item 当前指针，不能原地修改第一版课程。

course 生成完成后先以 CAS 写入 `course_id/version + content_phase=host_gate_pending + content_gate_status=pending`，把该 Provider attempt 的 started/deadline/completed 证据归档到不可变 dispatch/course checkpoint，随后清空 item 当前 Provider outer deadline、work-unit deadline 与 lease，仍保持 `status=processing`。host gate 是独立的无 Provider work unit：最多 3 个 gate ordinal，但不增加 content `attempt_count`，也永远不能回到 Provider phase。这样即使进程在 course 持久化后长时间停机，恢复也只重跑确定性 Host gate，不重新付费生成。

最终 `course_ready` 只能由 finalize CAS 写入，并同时核对 item/course identity、logical attempt、active generation request、host-gate lease、current validation contract 和 receipt hash。暂时性 gate 依赖失败保持 pending/scheduled，不调用 Provider；三次 host-gate claim 耗尽则以稳定基础设施错误终结。确定性 gate 拒绝按本 logical attempt 结束并安全进入唯一一次修复或终态失败。

### 5.3 Provider dispatch 账本与阶段化 sidecar

现有 sidecar 的一次 question-generation 命令内部会连续执行 outline、候选、修复、讲解文案、reconciliation、泄漏修复等多个 Provider HTTP 请求；Python 随后还会执行 verify、可选 consistency repair 和 re-verify。当前 Provider 请求不发送或验证任何上游幂等键，因此 local `requestId` 不能防止“响应已产生、进程在本地持久化前崩溃”后的重复计费。

Checkpoint 2 必须先把生成链拆成可持久化的 named phase graph。当前允许的 Provider phase 上限固定为：

```text
outline
raw_candidate
candidate_repair
candidate_repair_retry (conditional)
lesson_text
reconciliation
reconciliation_retry (conditional)
practice_leak_repair_1 (conditional)
practice_leak_repair_2 (conditional)
choice_prompt_repair (conditional)
independent_verification
consistency_repair (conditional)
consistency_repair_retry (conditional)
verification_after_repair (conditional)
```

一个 logical content attempt 最多 14 个 Provider dispatch；每个 runner tick 最多一个。实现阶段若发现需要第 15 个 phase，必须先修改合同与测试，不能在循环里隐式增加调用。

新增只追加 identity、只允许单调 CAS 状态推进且永不删除/复用的 `learning_course_provider_dispatches`：

- deterministic dispatch ID；
- build item、logical attempt、phase、phase ordinal；
- generation request identity；
- provider/model/profile 身份；
- input SHA-256；
- `dispatched | succeeded | failed_safe | ambiguous`；
- normalized checkpoint JSON 与 output SHA-256；
- immutable Provider attempt started/deadline identity；
- Provider 若返回则保存其 request ID 哈希、规范化 input/output token usage 与 `billingEvidence=reported|unknown`；
- safe error code；
- dispatched/completed timestamps。

named phase 与 phase ordinal 由版本化静态图一一映射，不能由调用者任选。数据库同时建立 `UNIQUE(build_item_id, logical_attempt, phase)` 与 `UNIQUE(build_item_id, logical_attempt, phase_ordinal)`，并 CHECK `logical_attempt BETWEEN 1 AND 2`，从两个方向锁死同一 attempt 的重名/换 ordinal 重发。不保存 API key、raw prompt、Provider raw body 或 raw error。

执行规则：

1. availability 与合同检查发生在 dispatch 前，失败可安全重试且不创建 dispatch；
2. 调用 Provider 前先提交 `dispatched` 行；
3. sidecar 每次进程最多执行一个 HTTP 请求，且 SDK/fetch retry 固定为 0；
4. Kimi phase 使用 `stream=true` 与 `stream_options.include_usage=true`；sidecar 只在 SSE 内容完整、终态明确且收到 `[DONE]` 后组装规范化结果，截断流按 lost response 处理；
5. 成功返回后先把规范化结果写入 checkpoint，再推进下一 phase；
6. 崩溃、timeout、连接中断或无法证明 Provider 未收到请求时，将该 dispatch 视为 `ambiguous`；
7. `dispatched/ambiguous` 永不自动重发；plan 以 `preparation_provider_dispatch_outcome_unknown` fail closed；
8. `failed_safe` 只表示 Provider 明确返回了无候选结果的稳定失败证据，也不在同一 phase 自动重发；CP2 将其安全终结为 provider/dependency failure，而不是偷用第二 logical attempt；
9. 只有已有 normalized checkpoint 的 `succeeded` phase 可无调用恢复；
10. 第二 logical attempt 只允许在第一 attempt 已得到完整结果但 Host 确定性拒绝后开始，不能用于绕过 `failed_safe` 或 ambiguous dispatch。

这提供的是应用侧“每个 phase 至多 dispatch 一次”，而不是声称 Provider 支持幂等或能够证明其最终计费结果。

一旦某 phase 进入 `failed_safe` 或 `ambiguous`，item 及共享 build 停止领取后续目标，所有当前匹配 follower plan 由同一 build 事实 fan-out 为稳定失败；不能让另一个孩子、successor plan 或旧 operator run 继续消费该 phase/attempt。尚未创建 dispatch 的 availability/preflight 失败才允许按原 deadline 做 dependency retry。

### 5.4 进度查询

build payload 增加只读内容汇总：

```json
{
  "contentCandidateItemCount": 3,
  "contentFailedItemCount": 0,
  "subjectContentProgress": {
    "chinese": {"candidateCount": 1, "failedCount": 0, "targetCount": 12},
    "math": {"candidateCount": 1, "failedCount": 0, "targetCount": 9},
    "english": {"candidateCount": 1, "failedCount": 0, "targetCount": 9}
  },
  "canary": {
    "targetCount": 3,
    "candidateCount": 3,
    "failedCount": 0,
    "passed": true
  },
  "canActivate": false
}
```

现有 catalog payload 的 `canActivate` 在 Checkpoint 2 永远为 `false`，且只由数据库中的 execution mode、stage ceiling 和 receipts 推导；不能信任请求参数或另造第二个同义布尔值。

## 6. 内容生成与自动门禁

### 6.1 版本化内容合同

preparation target 增加：

- `contentGenerationContractVersion`；
- `contentValidationContractVersion`；
- `subjectLanguagePolicyVersion`；
- 每科 `instructionLanguageCode`；
- 每科 `targetLanguageCode`；
- canary manifest version。

英语固定为中文低龄引导、英语目标内容：

```text
instructionLanguageCode = zh-CN
targetLanguageCode = en-US
```

语文和数学均为 `zh-CN / zh-CN`。不能继续用一个含义模糊的 `language=zh-CN` 让英语落入非英语生成分支。

这些字段参与 `target_fingerprint`。合同升级不能复用旧 build。当前年级但旧 fingerprint 的非终态计划由后台 reconciliation 创建/绑定新计划；保存年级请求本身仍只做事务内 reserve，不调用模型。reconciliation 首轮只允许 `primary_1`，默认关闭，并保留旧计划、任务、会话和报告。

三类版本必须分开命名、分别校验，不能用一个含糊的“v2”互相替代：

- preparation target/fingerprint 合同：`mira.learning.preparation-target.v2`，决定 30 个目标、顺序、语言策略、canary 与共享 build 身份；
- question generation/verification 合同：`mira.learning.question-contract.v2`，决定 Python adapter 与 Sidecar 每个 named phase 的输入、输出和 checkpoint；
- 家长端公开 wire 合同：`mira.learning.preparation.v2`，只决定 API/Flutter 的严格字段形状。

任一层版本漂移都必须 fail closed；公开 wire 升级不能隐式扩大生成目标，question 合同升级也不能复用旧 fingerprint/build。

### 6.2 通用内容门

每门候选必须满足：

- grade/subject/skill/boundary/prerequisite 精确绑定；
- 固定 5 题及 q1 示范、q2–q3 引导、q4–q5 独立角色；
- 题型、答案、选项、可接受文本、数值 AST 等 Host 校验；
- q4–q5 不泄漏答案；
- 安全、适龄、长度、原创性和跨变体语义去重；
- generation 与 verification 为两个隔离请求；
- 回执记录 generator profile 与 verifier profile 身份。

若 generator 与 verifier 仍使用相同 provider/model，公开证据只能称“隔离复核”，不能称“独立模型验证”。Checkpoint 3 正式发布门仍要求独立验证身份或等价的更强自动证据。

### 6.3 一年级学科门

Checkpoint 2 必须覆盖一年级全部 10 个 boundary，而不是只为 canary 写特例。

规则依赖版本化、仓库内可审计的数据权威，而不是临时正则或 verifier 自报：

- 语文：拼音 inventory、已学先修集合、受控常用字/偏旁/词语关系表、句子与标点有限规则；
- 英语：字母大小写与首音映射、问候固定句型、1–20 数词和基础颜色词表；
- 数学：每个 boundary 的数值范围、运算 AST、图形与位置有限关系。

这些数据集各有版本并进入 `contentValidationContractVersion` 和 receipt hash。规则只限制教学/考核目标；例如 `pinyin_syllables` 可以使用中文低龄说明，但不能把汉字识读或声母作为本课教学目标，不能把“出现任意汉字”误写成拒绝条件。

语文：

- `pinyin_syllables` 的教学/考核目标只允许 a/o/e 的口形、听辨和跟读，不得把声母、汉字识读或偏旁作为目标；中文低龄引导可以出现已冻结的说明用字；
- `pinyin_initials_syllables` 校验声母、已学韵母、简单两拼和先修边界；
- `characters_words` 只接受可唯一判定的常用字、基础偏旁和词语搭配；
- `simple_sentences` 要求短句完整性、基础语序和显式标点证据。

数学：

- 沿用并加强 `number_sense_20`、`addition_subtraction_20`、`shapes_position` 的确定性规则；
- 所有 numeric 答案继续由 Host AST/Decimal 独立复算；
- 任何超范围、含糊图形关系或无法唯一判分的题目直接拒绝。

英语：

- `letters_sounds` 只覆盖字母识别、大小写匹配和明确首音；
- `greetings` 只覆盖固定问候与简单姓名表达；
- `numbers_colors` 只覆盖 1–20 和基础颜色；
- 大小写与句末标点归一化只能用于评分，不能掩盖错误词义；
- 题目目标文本必须走英语分支，低龄讲解可以是中文。

任一规则无法确定性给出唯一结果时，候选必须失败，不能以模型自报 `passed=true` 代替。

### 6.4 变体门

同一 boundary 的 3 个变体必须：

- 使用同一 boundaryVersion；
- 各有独立 course ID/version；
- 规范化题干、答案、选项后语义指纹不同；
- 不能仅通过变更题目 ID、选项顺序、空格或标点绕过去重；
- 每个变体都独立通过 Host gate。

## 7. Preparation runner 状态机修正

### 7.1 正常续跑不使用 `retry_wait`

状态证据固定如下，056 的 CHECK 与 repository CAS 必须逐格实现：

| 形态 | status/stage | plan lease | next_run_at | hard_deadline_at | resume_stage |
|---|---|---|---|---|---|
| initial | `queued/queued` | NULL | NOT NULL | NULL | NULL |
| scheduled-unleased | `running/planning|generating_content` | NULL | NOT NULL | NULL | NULL |
| coordinator-claimed | `running/planning|generating_content` | 全非 NULL | NOT NULL | NOT NULL，2 分钟协调 work-unit deadline | NULL |
| item-bound-claimed | `running/generating_content` | 全非 NULL | NOT NULL | NOT NULL，精确镜像 item 当前 work-unit deadline | NULL |
| dependency retry | `queued/retry_wait` | NULL | NOT NULL 且不晚于 deadline | NOT NULL | NOT NULL |
| handoff-paused | `running/building_classrooms` | NULL | NULL | NULL | NULL |

`coordinator-claimed` 只允许在领取 plan 后、尚未领取/绑定 catalog item 的短协调窗口存在，使用独立的 2 分钟 plan 协调 deadline，绝不能调用 Provider。plan 行必须以 `work_unit_kind=coordinator` 持久化区分它。item claim 成功后必须先 CAS 为 `item-bound-claimed`，写入 bound item/attempt/phase，并把 plan deadline 原子替换为 item 当前 work-unit deadline，之后才可 dispatch。

`handoff-paused` 必须同时绑定 exact build/release、content 30/30、完成时间和当前合同回执；正式 ready/failed counts 仍为 0。它不是 claimable 状态，也不是 ready。Checkpoint 3 必须用新合同显式重新调度，旧 runner 不会自动领取。

`retry_wait` 只表示真实可恢复依赖错误，必须带 `resume_stage` 和仍有效的原 work-unit deadline。若失败发生在 item 绑定前，保留 `work_unit_kind=coordinator` 且 bound 字段全 NULL；发生在 item 绑定后，保留 `provider_phase|host_gate` 与 exact bound item/attempt/phase，便于只恢复同一工作。正常阶段交接或同阶段下一 item 不能写 `retry_wait`。

`initial`、scheduled-unleased、handoff 与 terminal plan 的 `work_unit_kind/bound_*` 全部为 NULL。dependency retry 精确保留上一段所述 kind/binding；不得写任意组合或依赖 NULL/UNKNOWN 侥幸通过 CHECK。

### 7.2 Provider attempt 与 work-unit 双层 deadline

- planning/coordinator work unit：2 分钟；
- 每个 Provider phase：最多 2 分钟，fetch/SDK retry 为 0；
- 单门 logical Provider generation attempt：从 item attempt claim 提交起最多 30 分钟，权威字段为不可移动的 `content_provider_attempt_hard_deadline_at`；
- 当前 phase 的 `content_work_unit_deadline_at = MIN(now + 2min, content_provider_attempt_hard_deadline_at)`，phase 切换只更新 work-unit deadline，绝不移动外层 Provider deadline；
- immutable course checkpoint 完成后把 Provider outer deadline 归档到 dispatch/course checkpoint 并清空 item 当前 outer/work-unit 字段，Provider generation attempt 正式关闭；随后 host gate 是独立 Host-only work unit；
- 同一 host-gate ordinal 的 dependency retry 保留原 2 分钟 deadline且不增加 `content_gate_attempt_count`；只有明确结束上一 ordinal 后开始下一 ordinal，才把 count 加一并创建新的 2 分钟 deadline，最多 3 次；
- retry_wait 不延长原 work-unit deadline；
- catalog item 的两层 deadline 是共享 build 下的唯一工作时间权威；plan `hard_deadline_at` 只镜像当前 `content_work_unit_deadline_at`，不能延长；
- item 成功通过内容 gate并调度下一 item 后，清空旧 plan deadline；
- 第一 logical attempt 被 Host 确定性拒绝后结束；领取唯一一次自动修复时建立新的 30 分钟 deadline；
- safe checkpoint 恢复同一 attempt 时保留 item 原 deadline，不能通过换 plan、换孩子或重启无限续命；
- Provider outer 或当前 Provider-phase work-unit deadline 任一到期后不再发起 Provider 请求；当前 Host-gate work-unit deadline 到期后只允许安全重领 Host gate。所有迟到结果都因 dispatch/item lease/status CAS 不能覆盖新 owner 或终态。

staged generation job、dispatch phase 与 item 使用同一时钟：单 phase lease/timeout 必须早于 Provider attempt outer deadline 并留出持久化余量。现有 15 分钟 job stale 与 420 秒多调用 subprocess 不可沿用到 content-only staged path；新 path 的单调用 subprocess timeout 不得超过 phase 的 2 分钟 work-unit deadline。

主设计中“单个内容 work unit 10 分钟”的假设不适用于当前多阶段 question pipeline。Checkpoint 2 以可审计的单 phase 2 分钟、整次 attempt 30 分钟取代该假设；任何阶段都不能一次包住多个不透明 Provider 调用。

### 7.3 heartbeat

协调阶段 heartbeat 只更新 plan lease并受 plan 的 2 分钟 hard deadline 约束；item 绑定后使用独立 `LeaseHeartbeatGuard`，周期不超过 `min(lease/3, 15s)`，同一节拍更新 plan lease 与当前 catalog item content lease。Provider phase 同时受 outer Provider deadline 与当前 work-unit deadline 约束；Host gate 只受其 Host-only work-unit deadline 约束。heartbeat 丢失后：

- Provider phase heartbeat 只能写 `lease_expires_at = LEAST(now + lease_ms, content_work_unit_deadline_at, content_provider_attempt_hard_deadline_at)`；Host gate 使用 item `LEAST(now + lease_ms, content_work_unit_deadline_at)`；coordinator 使用 plan `LEAST(now + lease_ms, hard_deadline_at)`；任一适用 deadline 到达后停止；
- 所有 owner lifecycle 写入都要求 exact plan/item lease token、fingerprint、attempt、phase 且 `lease_expires_at >= now`；
- 已过 deadline 的 row 在锁内直接终结，不能再交给 adapter；

- 允许正在进行的外部调用自然结束；
- 其结果只能按 catalog item 的 active requestId/CAS 持久化；
- 旧 plan lease 不能更新计划；
- 下一 worker 从 catalog 权威状态重新汇总。

### 7.4 shared build 协调

多个孩子共享同一 `shared_build_request_id`：

- catalog item claim 是付费工作唯一权威；
- item 级 content lease/deadline 跨所有共享 plan 生效；
- 一个 build 同时最多一个非 stale content item；
- content claim 事务先 `SELECT release ... FOR UPDATE` 作为 catalog mutex，再 `SELECT build ... FOR UPDATE`，然后检查 live item lease 和选择 target；不能靠 `SKIP LOCKED` 跳过已锁 item 后领取第二门；
- 任一 plan 推进 build 后，repository 根据 build 汇总，更新所有仍匹配相同 fingerprint、grade revision 且非终态的 plan；
- follower plan 不重复调用 Provider；
- 孩子已换年级或 plan 已 superseded 时不再 fan-out 更新。

“匹配 grade revision”是逐条重新锁定每个 plan 对应 child 并确认该 child 的当前 revision，不能要求不同孩子的 revision 数值彼此相同。Phase 2A 或 2B 任一目标耗尽两次 logical attempt 后，立即停止该 build 的新 claim，并把所有仍匹配该 build/fingerprint 的当前 follower plan 原子写为同一安全失败；不能留下 29/30 永久 running，也不能让另一个孩子重新消费预算。

普通进度 fan-out 在 release→build mutex 后只更新派生计数以及 unleased/expired follower。它不能清除另一个 live plan owner 的 lease；当前 owner 的 lifecycle 仍由 token CAS 完成。唯一例外是 build 级不可恢复终态：事务先写不可逆 build terminal fence，再对所有当前匹配 plan 执行 terminal CAS、清除其 lease/binding 并写同一安全错误；任何迟到 owner 都因 build terminal fence 与 plan status/token CAS 失败，不能再写回。若 follower plan claim 后发现 build 正忙，adapter 返回 `ContentAdvanceResult(kind="busy")`，正常释放为 scheduled-unleased 并设置短 next_run；不能写 retry_wait、失败或 deadline。

## 8. 数据迁移

新增 `056_learning_curriculum_preparation_content_stage.sql`，不修改已登记的 054/055。

计划表增加：

- `content_target_count`；
- `content_candidate_count`；
- `content_failed_count`；
- `content_canary_target_count`；
- `content_canary_candidate_count`；
- `content_canary_failed_count`；
- `content_canary_passed_at`；
- `content_generation_completed_at`；
- `retry_reason_code`；
- `retry_message_safe`；
- `work_unit_kind`；
- `bound_catalog_item_id`；
- `bound_content_attempt_ordinal`；
- `bound_content_phase`；
- `stage_progress_json`。

catalog build 增加：

- `execution_mode`，历史/现有行为 backfill 为 `full_pipeline`，Checkpoint 2 精确为 `content_only`；
- immutable `content_manifest_version`、`canary_manifest_json` 与 `stage_ceiling`；历史 `full_pipeline` backfill `stage_ceiling=active_release` 且 manifest 可为 NULL，Checkpoint 2 精确为非空 manifest + `content_ready`。

catalog build item 增加：

- `execution_mode_snapshot`；
- `content_manifest_version_snapshot`；
- `subject_ordinal`；
- `boundary_ordinal`；
- `content_phase`；
- `content_gate_status`；
- `content_gate_attempt_count`；
- `content_gate_passed_at`；
- `content_validation_contract_version`；
- `content_receipt_hash`；
- `content_lease_token`；
- `content_lease_expires_at`；
- `content_heartbeat_at`；
- `content_attempt_started_at`；
- `content_provider_attempt_hard_deadline_at`；
- `content_work_unit_deadline_at`；
- `content_claim_attempt_ordinal`。

新增 `learning_course_provider_dispatches`，保存上一节定义的不可删除、不可复用、状态单调推进的 dispatch/checkpoint 证据。

约束要求：

- 所有计数非负且不超过 target；
- canary target 对当前合同精确为 3；
- `content_canary_passed_at` 非空时 canary 自身必须 3/3、`content_canary_failed_count=0`；后续 27 门失败不能抹掉已通过的 canary 证据；
- `content_generation_completed_at` 非空时内容必须 30/30、失败为 0；
- `candidate + terminal_failed <= target`，`canary_candidate + canary_failed <= canary_target`，canary 计数不得超过对应全局计数；
- `ready_course_count` 不能由内容候选计数推进；
- `building_classrooms` 的 Checkpoint 2 handoff 必须有完整 content evidence；
- content 候选计数只认当前验证合同下非空 `content_gate_passed_at + content_receipt_hash`，不能用 `course_id IS NOT NULL` 或临时 status 推断；
- `course_ready` 在 content-only build 中只能由 `content_gate_status=passed` 的 finalize CAS 写入；gate 暂缓保持 processing/pending，不得提前写 course_ready；
- content lease 三字段满足完整 group 约束；`course_ready`、package/ready 和终态失败均不得残留 content lease；
- `content_provider_attempt_hard_deadline_at` 在当前 Provider attempt claim 后写入且绝不后移；immutable course checkpoint 把它归档进不可变 dispatch/course 证据后，item 当前字段必须清空。`content_work_unit_deadline_at` 仅用于 item 的 provider-phase/host-gate，coordinator deadline 只存在 plan；Provider phase work-unit 必须不晚于 outer deadline；
- 当前合同下 `content_gate_status` 精确为 `not_started|pending|retry_wait|passed|failed_deterministic`；host-gate attempt 为 0–3，只有 pending/retry_wait 可领取，且 host-gate work unit 不增加 Provider content attempt；
- `execution_mode=content_only` 的 item 不得具有 package attempt/identity；
- subject/boundary ordinal、canary manifest 与 stage ceiling 必须参与 target fingerprint/receipt，不能在运行时静默改变顺序或范围；
- dispatch 的 `dispatched/ambiguous` 不可再次领取，`succeeded` 必须有 normalized checkpoint 与 output hash；
- dispatch 唯一键精确覆盖 item/attempt/phase/ordinal；`dispatched` 不得伪造 terminal 字段，`succeeded` 必须有 completed/checkpoint/output，`failed_safe|ambiguous` 必须有稳定 safe code 且不得带候选 checkpoint；所有 usage 计数若存在必须非负；
- retry_wait 必须有非空 `retry_reason_code/retry_message_safe`，重新 claim 时清空；正常 busy/handoff 不得写 retry reason；
- scheduled-unleased、claimed、retry_wait、failed 和 handoff 均使用显式 `IS NULL/IS NOT NULL`，防止 MySQL CHECK 的 UNKNOWN 绕过；
- plan `work_unit_kind` 精确为 `coordinator|provider_phase|host_gate`：coordinator 的 bound 字段全 NULL；后两者必须有 bound item/attempt/phase。claimed 与 dependency-retry 保留适用 kind/binding；initial、scheduled-unleased、handoff 与 terminal 全部 NULL。MySQL CHECK 锁本行形状，repository 在 release→build mutex 下锁 item并验证 bound identity/deadline 镜像；
- 历史 `full_pipeline` item backfill `execution_mode_snapshot=full_pipeline, content_phase=legacy_full_pipeline, content_gate_status=not_applicable, content_gate_attempt_count=0`；ordinal、manifest、content lease/deadline/receipt 可为 NULL，且永远不被 content claim。新 `content_only` item 必须 snapshot mode/manifest、ordinal 和本节所有 content evidence，不能使用 legacy sentinel；
- item CHECK 按本行不可变 `execution_mode_snapshot` 分支；repository 在锁住 release→build 后另行核对 snapshot 等于 build 权威。不能声称 MySQL CHECK 能跨表证明两者一致；
- migration 两次 replay、旧 054/055 合法行升级和 partial-DDL restart 均可验证。

`stage_progress_json` 只保存规范化计数和安全状态，不保存 prompt、Provider 原始响应、儿童文本或密钥。

056 必须采用可重放顺序：

1. 每列/表/索引通过 `INFORMATION_SCHEMA` 独立检测后增加；
2. 完成不改变 plan state shape 的安全 backfill，并以新增临时/持久分类字段记录 legacy retry 的可证明来源；
3. 条件 drop 055 的 `chk_learning_prep_state_evidence`；
4. 幂等执行 `running/queued`、legacy retry、build mode 与 historical item sentinel 等状态归一化；
5. 立即添加唯一的新 state CHECK；
6. 再添加依赖新状态的 NOT NULL、dispatch/item/计数等其余 CHECK 与索引；
7. 验证旧 CHECK 不存在、唯一新 CHECK/所有列/索引/回填均精确后，才登记 migration。

新 CHECK 按 `target_spec_json.schemaVersion` 的 target contract version 分支：`mira.learning.preparation-target.v1` 为历史分支，`mira.learning.preparation-target.v2` 为当前严格 3/30 分支；不能把 v1 历史行强制为 3/30。`preparation_contract_version` 继续表示既有 `mira.learning.grade-preparation.v1` envelope contract，不能虚构尚无生产者的 v2 值来区分新旧 target。每个 nullable 字段先显式 `IS NULL/IS NOT NULL`，再执行 `IN`、比较或 JSON 读取，确保 OR 分支只产生 TRUE/FALSE；`stage_progress_json` 先合法 backfill，再要求 `IS NOT NULL AND JSON_VALID(...)=1`。partial restart 必须特别覆盖“旧 CHECK 已 drop、状态只转换一半、新 CHECK 尚未添加”，重跑需继续归一化并恢复唯一新 CHECK，不能因 migration marker 缺失而盲目重复非幂等 DDL。

旧 Checkpoint 1 状态迁移：

- `running/queued` 映射为 `running/planning`，保留已有 lease/deadline；
- v1 `planning` 维持旧合同分支，不自动获得 content 资格；
- 旧 `retry_wait` 若可证明来自 create-only planning，则转换为 planning scheduled-unleased；无法证明来源的行以安全 upgrade error 终结，不能猜测为 Provider 可重试；
- 新 v2 plan 由 reconciliation 另行 reserve，旧 plan、任务、会话和报告不删除。

## 9. API 与家长端合同

### 9.1 公开 API

不增加任何生成 POST。以下请求继续只读或只 reserve：

- 保存年级；
- `GET /api/learning/preparations/current`；
- preparation retry；
- Today/assign；
- student library/classroom。

现有客户端对 v1 执行 exact-key 校验，因此不能直接在默认响应增加字段。版本协商固定为：

- 无 header：继续返回 exact `mira.learning.preparation.v1`；
- `X-Mira-Preparation-Schema: mira.learning.preparation.v2`：返回 exact v2；
- 未知版本：406 `learning_preparation_schema_not_acceptable`；
- 响应增加 `Vary: X-Mira-Preparation-Schema`；
- setup/profile 保存响应继续返回 v1，移动端保存成功后刷新 current GET 获取权威 v2；
- current GET 与 retry POST 支持相同协商规则。

所有公开路由继续先完成现有家庭/孩子鉴权，再解析协商 header 或 retry body；未认证请求即使携带未知 schema 或畸形 JSON 也只返回现有 401，不泄漏合同差异。

v2 新增：

```json
{
  "contentProgress": {
    "candidateCount": 3,
    "failedCount": 0,
    "targetCount": 30,
    "canary": {
      "candidateCount": 3,
      "failedCount": 0,
      "targetCount": 3,
      "passed": true
    }
  }
}
```

exact v2 根字段集合定义为 exact v1 根字段集合再增加且只增加 `contentProgress`；每个 subject 对象定义为 exact v1 subject 字段集合再增加且只增加 `contentCandidateCount` 与 `contentFailedCount`。嵌套集合精确为：

- `contentProgress`：`candidateCount, failedCount, targetCount, canary`，无其他键；
- `contentProgress.canary`：`candidateCount, failedCount, targetCount, passed`，无其他键。

所有 count 必须是严格 integer（拒绝 bool、float、string、null），`passed` 必须是严格 boolean。所有 count 非负；全局与每科均满足 `candidate + failed <= target`；顶层 candidate/failed/target 分别等于三科同类字段之和；`contentProgress.targetCount == totalCourseCount`。当前 `mira.learning.preparation-target.v2` 还要求顶层 target=30、canary target=3、canary candidate/failed 不超过对应全局计数，且 canary `passed=true` 当且仅当 `candidateCount=targetCount=3 && failedCount=0`。任一未知键、缺键、类型或计数不变量错误都 fail closed。原 `readyCourseCount` 与 `failedCourseCount` 的正式课件含义不变。

30/30 后家长端显示：

```text
30 门课程内容已通过，等待制作完整互动课件
```

它不能显示“课程已就绪”，也不能挂载 Today。

Flutter 先按 schemaVersion 分派，再分别执行 exact v1/exact v2 校验。v1 没有内容进度时映射为 `unknown` 而不是 0；不凭本地计时器推断。

v1/v2 的 `isReady` 必须完整继承 Checkpoint 1 已冻结的全部形式就绪不变量，不能缩短成少数顶层字段：supported schema、`status=ready`、supported `stage=completed`、`progressPercent=100`、`totalCourseCount>0`、顶层 ready=total/failed=0、学科集合恰好且不重复为 chinese/math/english、每科 total>0/ready=total/failed=0、三科 total/ready/failed 分别严格求和等于顶层。v2 在此基础上还要求前述 exact `contentProgress` 完整有效、candidate=target、failed=0、canary passed。缓存 authority 继续使用 `childId + preparationId`，任何一条证据不满足都不请求 Today/assign。

在 `generating_content/building_classrooms` 阶段，卡片主计数和无障碍文案使用“内容已通过 X/30”，不能继续显示“已就绪 0/30”。

总进度使用可审计的固定权重：planning 完成为 5%，内容阶段为 30%。因此内容阶段进度为 `5 + floor(30 × candidateCount / targetCount)`，30/30 handoff 精确为 35%。Checkpoint 2 不会产生 36–100% 的值。

### 9.2 内部状态 API

新增只读、内部 token 保护的：

```text
GET /internal/learning/curriculum-preparations/runner/status
```

白名单响应：

```json
{
  "ok": true,
  "schemaVersion": "mira.learning.preparation-runner-status.v1",
  "internal": {
    "auditId": "audit_opaque"
  },
  "runner": {
    "enabled": false,
    "contentGenerationEnabled": false,
    "gradeAllowlist": ["primary_1"],
    "maxProviderSubcallsPerTick": 1,
    "observationScope": "process",
    "lastRunAt": null,
    "lastResultCode": null,
    "lastStage": null,
    "lastErrorCode": null,
    "claimablePlanCount": 0,
    "runningPlanCount": 0,
    "expiredLeaseCount": 0
  }
}
```

鉴权必须先于 schema/query 校验、任何状态或计数读取。GET 不 claim、不修改 preparation/catalog/event 业务数据、不调用 Provider；只允许现有 `InternalRequestGuard` 写安全访问审计并返回不含凭据的 opaque `auditId`。`lastRunAt/lastResultCode/lastStage/lastErrorCode` 是当前进程观察，数据库计数是全局观察。响应不返回开放结构、原始异常正文、plan/build ID、Provider、model 或 base URL。

不提供 HTTP `run` 或 `generate` 入口；真实工作只能由受配置门控制的后台 runner 领取。

## 10. 配置与启用顺序

新增并默认关闭：

```text
LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED=0
LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST=primary_1
LEARNING_CURRICULUM_PREPARATION_MAX_PROVIDER_SUBCALLS_PER_TICK=1
LEARNING_CURRICULUM_PREPARATION_MAX_INFLIGHT_PER_BUILD=1
LEARNING_CURRICULUM_PREPARATION_CANARY_ENABLED=1
LEARNING_CURRICULUM_PREPARATION_CANARY_AUTO_EXPAND=1
LEARNING_CURRICULUM_PREPARATION_RECONCILIATION_ENABLED=0
```

生产示例和默认值保持 `RUNNER_ENABLED=0`、`CONTENT_GENERATION_ENABLED=0`。只有同时满足以下条件才可调用真实生成：

1. runner enabled；
2. content generation enabled；
3. grade 在 exact allowlist；
4. active preparation/content contract 与 plan fingerprint 一致；
5. build 仅含 primary_1 三科 30 个目标；
6. Provider readiness 通过；
7. package、Runtime、TTS、ASR、activate 路径均保持关闭。

首次开发环境 canary 必须在所有定向测试、全相关回归、迁移 readback 和零调用证明通过后显式启用。任何门不符立即停止，不降级、不扩大到 30。

## 11. 错误与重试

### 11.1 自动内容尝试

每个 catalog item 最多：

- 1 次初始生成；
- 1 次带安全 generation feedback 的自动修复。

safe checkpoint 恢复可以复用同一 active request identity，但不得重发已 `dispatched/ambiguous` 的 Provider phase。`external_failed` 只有在 dispatch ledger 证明调用尚未发生时才可重试；否则进入 `preparation_provider_dispatch_outcome_unknown`。coordinator 不生成 retry suffix，logical attempt 由 catalog repository 单独决定。

### 11.2 家长 retry

家长 retry 只允许恢复可重放的 orchestration/dependency 失败。若某课程已经两次确定性内容失败，公开 `canRetry=false`；不能通过 successor plan 绕过每 item 两次预算。合同升级后使用新 fingerprint/new build，不修改旧失败记录。

payload 与 retry POST 必须共用唯一 `parent_retry_decision(plan, build_snapshot)`。POST 在事务内重新锁 plan、build 和相关 item 真值，只允许稳定 allowlist 中的安全前置依赖/协调失败，或 ledger 已证明所有 Provider phase 成功且下一动作严格为 Host-only gate 的依赖失败；两类 retry 都必须证明 Provider delta 为 0。canary failure、validation exhausted、`failed_safe`、dispatch ambiguous 和 contract drift 均拒绝。客户端 `canRetry` 不具有授权力。

### 11.3 安全错误

公开和事件只保存稳定错误码与安全中文文案，例如：

- `preparation_content_canary_failed`；
- `preparation_content_validation_failed`；
- `preparation_content_attempts_exhausted`；
- `preparation_content_provider_unavailable`；
- `preparation_provider_dispatch_outcome_unknown`；
- `preparation_content_gate_attempts_exhausted`；
- `preparation_content_stage_deadline_exceeded`；
- `preparation_content_contract_drift`。

不保存或返回 Provider raw error、模型正文、prompt、API key 或儿童隐私信息。

后台 loop 不再 `except Exception: pass`。所有未分类错误必须：

- 记录结构化安全日志；
- 更新 in-memory runner observation；
- 不泄漏原始 Provider 内容；
- 不把未知错误自动判为 retryable。

## 12. 原子性与崩溃恢复

必须验证以下 crash points：

1. plan claim 后、catalog item claim 前；
2. item claim 后、plan item-bind 前；
3. dispatch ledger 提交前；
4. `dispatched` 提交后、HTTP 发送前；
5. Provider 返回后、normalized checkpoint 提交前；
6. phase checkpoint 后、下一 phase 调度前；
7. course 持久化后、内容 gate 完成前；
8. item `course_ready` 后、plan 汇总前；
9. canary 3/3 后、解除 eligible target 限制前；
10. 30/30 后、plan handoff 前。

恢复原则：

- catalog item 是事实权威；
- plan 汇总可重复计算；
- 迟到 plan lease 不能覆盖新 owner；
- active generation request identity 不变，但它不被当作 Provider 幂等凭据；
- `dispatched` 后没有 checkpoint 的 phase 一律 ambiguous、零自动重发；
- succeeded checkpoint 恢复不调用 Provider；
- 已持久化 immutable course 不重新生成；
- canary pass 和 30/30 handoff 都由 exact item 集合重新计算，不依赖单一布尔值；
- 任一异常不触发 package/TTS/Runtime/activation。

## 13. 测试与验收

### 13.1 TDD 顺序

1. migration 和 repository 状态证据；
2. normal scheduled continuation 与 per-item deadline；
3. content-only catalog claim/process；
4. 三门 exact canary 与自动 expansion；
5. 一年级 10 boundary 学科 validators；
6. shared build/fan-out、崩溃恢复和尝试预算；
7. API v2、内部 status、Flutter 内容进度；
8. request-path 零调用与 package/Runtime/TTS/activate 零调用；
9. 开发环境 3 门真实 canary；
10. canary 通过后同 build 扩展到 30 门。

### 13.2 必测矩阵

| 类别 | 必须证明 |
|---|---|
| 目标 | primary_1 精确 30；语文 12、数学 9、英语 9；每 boundary 3 variants |
| Canary | exact 三个 skill/variant；任一失败不扩展；3/3 后自动扩展 |
| 内容边界 | 10 个一年级 boundary 各有合法 golden 和 mutation rejection |
| 变体 | 改 ID/顺序/空格不能绕过去重 |
| 状态机 | 正常续跑不进入 retry_wait；同 stage 可逐 item 释放和重领 |
| Deadline | 新 item 新 deadline；stale 同 item 不续期；heartbeat 不移动 hard deadline |
| Dispatch | 每个 named phase 最多一次；failed_safe/ambiguous 均不自动重发；dispatch 总数不超过静态 phase graph；usage/billing 只按 Provider 回执报告、不臆测 |
| 幂等 | safe checkpoint 恢复零 Provider；stale/external/lost response 不绕过 dispatch ledger |
| 共享 | 多孩子同 fingerprint 只有一次 build/item/phase dispatch，进度 fan-out |
| 计数 | content count 与 ready count 分离；30 content 不产生 ready |
| 旁路 | content-only build 的旧 run/activate 均 409；package、media、Runtime、TTS、ASR、activate 调用精确为 0 |
| 请求隔离 | setup/profile/current/retry/today/assign/student/daily runner Provider 调用精确为 0 |
| 可观测 | status GET 除内部鉴权审计外业务零写、Provider 零调用；后台异常有安全 observation/log |
| Flutter | exact v1/v2、v1 ready、v2 canary/30 content、future/畸形 v2、failed；逐项 mutation status/stage/progress/零 total/缺科/重复科/分科求和/content nested keys/type/负数/越界/canary，所有非正式 ready 均不请求 Today/assign |
| 迁移 | 056 replay、partial restart、CHECK NULL 反例、旧行升级、真实测试 MySQL |

### 13.3 首次真实 canary 证据

在开发环境只允许三门各产生至多两个 logical content attempt。每个 attempt 的 Provider dispatch 上限由 14-phase 静态图决定，因此单 item 最坏上限 28、三门 canary 最坏上限 84；正常调用数应明显更低，但执行前后都必须按 dispatch ledger 精确报告。报告至少包含：

- build/request/fingerprint 的非敏感身份；
- 三个 item 的 logical attempt 数、每 phase dispatch 状态、active requestId 哈希、course identity；
- generator/verifier profile 身份；
- Host validator 结果与三科门禁版本；
- package/TTS/Runtime/activation 调用为 0；
- 旧任务、会话、报告和 active release 未变化的只读证据。

canary 未全部通过时不得扩大调用。canary 全部通过后，自动扩到 30 的行为由本设计授权，不再逐门请求用户确认；但必须持续受每 item 两次 logical attempt、每 phase 一次 dispatch、单 build 并发 1 和一年级 allowlist 约束。

## 14. 计划文件范围

预计生产代码：

- 新增 `backend/migrations/056_learning_curriculum_preparation_content_stage.sql`；
- 修改 `backend/services/learning_curriculum_preparation_runner.py`；
- 修改 `backend/repositories/learning_curriculum_preparation_repository.py`；
- 修改 `backend/services/learning_curriculum_preparation_service.py`；
- 修改 `backend/services/learning_catalog_release_service.py`；
- 修改 `backend/repositories/learning_catalog_repository.py`；
- 修改 `backend/services/dynamic_learning_course_generation_service.py`；
- 修改 `backend/integrations/openmaic_question_adapter.py`；
- 修改 `backend/repositories/dynamic_learning_course_repository.py`；
- 修改 `backend/services/learning_generated_course_validator.py`；
- 修改 `backend/services/learning_catalog_validator.py`；
- 修改 `backend/content/primary_skill_boundaries.py`；
- 修改 `backend/openmaic-sidecar/src/cli.mjs`、`provider.mjs`；
- 修改 `backend/openmaic-sidecar/src/question-contract.mjs`；
- 修改 `backend/services/learning_curriculum_preparation_contract.py`；
- 修改 `backend/services/service_factory.py`；
- 修改 `backend/core/config.py`、`backend/app.py`、`backend/.env.example`、`backend/README.md`；
- 修改 `backend/routes/api/v1/learning.py`，实现显式 v1/v2 协商；
- 修改 `backend/routes/internal/learning_content.py`，让旧 run/activate 对 content-only build 硬拒绝；
- 新增明确命名的内部只读 status route 并在 `backend/app.py` 注册；
- 修改 Flutter preparation model/repository/card、Home preview 与 realtime helper 的 v2 内容进度和 fail-closed 验证。

对应新增或扩展 migration、repository、runner、catalog、validator、request-zero-call、API、config、internal route、Flutter model/widget/golden 测试。

不会修改：

- OpenMAIC Runtime 与 patch 链；
- Gateway 或 student-web；
- LessonPackage/media/TTS/ASR 实现；
- 年级级 active release 发布或全局激活语义；只在现有 `run/activate` 增加 `content_only` build 的硬拒绝；
- 历史任务、会话和报告。

## 15. Checkpoint 2 完成定义

只有同时满足以下条件，Checkpoint 2 才完成：

1. 代码和迁移通过 TDD、定向与相关全量回归；
2. runner 默认关闭并具有一年级硬 allowlist；
3. 三门真实 canary 全部通过；
4. 同一 build 自动扩展并得到 30/30 内容候选；
5. 所有 logical attempt、named Provider dispatch、request identity、checkpoint 和恢复证据可审计；
6. package、media、Runtime、TTS、ASR、activate 调用均为 0；
7. 家长端显示内容进度但计划仍非 ready；
8. 学生与 Today 仍不能读取候选 release；
9. 旧 active release、历史任务、会话和报告未被修改；
10. 输出 Checkpoint 2 证据报告并停下，等待进入 Checkpoint 3。

Checkpoint 2 完成后可以说“30 门一年级课程内容候选已经生成并通过内容门”，不能说“30 门正式完整课件已经上线”。
