# 年级触发的自动备课与发布设计

## 1. 目标

家长在首次设置或孩子资料中选择小学年级后，Mira 立即为该年级创建一条可审计的后台备课计划。请求只写入计划，不在 App 请求中调用模型。后台按语文、数学、英语生成完整课程课件；每门课通过自动质量门后，系统原子发布到学生课程库，不依赖人工审核。

首批为当前课程边界注册表中的每个能力点准备 3 个教学变体：一年级 10 个能力点、约 30 门课，二至六年级各 9 个能力点、约 27 门课。统一按“约 30 门”展示，保证约 14 天的两节课日程缓冲。后续增加课程边界时沿用同一流程，不修改家长端或学生端 API。

本设计中的“直接生成”含义固定为：

1. 年级保存事务内一定创建或复用备课计划；
2. 保存接口立即返回计划状态，不等待模型；
3. 后台 worker 自动推进生成、语音、校验与发布；
4. 家长端持续显示真实阶段和计数；
5. 学生请求只读取已发布课件，绝不触发生成。

## 2. 已确认的产品规则

- 年级范围为 `primary_1` 至 `primary_6`。
- 每个年级准备语文、数学、英语课程。
- 同一年级的正式课程按课程合同共享，不为每个孩子重复调用模型。
- 不设置人工审核、待审核或运营审批状态。
- 自动校验失败的课程不发布，也不以简化版课件降级。
- 正式完整课堂保留幻灯片、测验、模拟、HTML 小游戏、3D 可视化、多 Agent 讨论、教师动作、逐场讲稿和 Qwen3-TTS；白板不在当前必需范围。
- 自动连播在学生课堂默认关闭，学生可在单次课堂内临时开启。
- 历史任务、学习会话、报告和旧课程版本只读保留；年级变化只影响新的备课计划和后续任务。

## 3. 采用方案

采用“孩子计划 + 年级共享构建 + 年级级原子发布”。

### 3.1 不采用的方案

**在保存年级接口中同步生成**：耗时不可控，断网或 Provider 超时会让家长误以为资料没有保存，也会再次出现十多个小时没有明确结果的问题。

**每个孩子单独生成一套相同年级课程**：浪费模型与 TTS 成本，并会产生内容版本不一致。

**一次生成一至六年级全部课程**：首次交付周期过长，任何一个年级失败都会阻塞其他家庭，无法按阶段验收。

### 3.2 推荐结构

```text
家长保存年级
  -> 同一数据库事务：保存 child grade + reserve child preparation plan
  -> 后台 coordinator 领取 queued plan
  -> 复用同年级已 ready 发布，或绑定同年级共享 catalog build
  -> 课程内容生成
  -> 完整 OpenMAIC Runtime 课件生成
  -> Qwen3-TTS 音频生成
  -> 自动质量与安全校验
  -> 年级级 release 原子切换
  -> plan ready
  -> 学生课程库读取新 release
```

多个孩子选择同一年级时，各自拥有可见的孩子计划，但只绑定一个共享构建。已有同合同的 ready 年级发布时，计划直接进入 `ready`，不再次调用模型。

### 3.3 课程库存策略

- 初次选定年级：准备约 27～30 门完整课程；
- 每天：从 ready 库中安排两节课，不调用生成模型；
- 可用未学课程少于 14 门时：后台创建下一批增量准备任务，恢复到约 28～30 门缓冲；
- 每学期目标：逐步形成约 90 门不同正式课程，原则上每科约 30 门；
- 复习、错题巩固和间隔复习可以复用已发布课程或其练习变体，不把每个学习课次都算作一门新课；
- 增量补充由库存水位触发，不按自然日无条件生成。

## 4. 数据模型

新增迁移，使用下一个可用迁移号，不修改已登记的历史迁移。

### 4.1 `learning_curriculum_preparation_plans`

每条记录是一个孩子在一个年级与课程合同下的准备计划。

关键字段：

- `id`
- `family_id`
- `child_id`
- `grade_code`
- `school_year_start_year`
- `grade_selection_revision`
- `curriculum_version`
- `preparation_contract_version`
- `target_spec_json`
- `target_fingerprint`
- `request_id`
- `shared_build_request_id`
- `status`
- `stage`
- `catalog_build_id`
- `catalog_release_id`
- `total_course_count`
- `ready_course_count`
- `failed_course_count`
- `progress_percent`
- `resume_stage`
- `retry_of_plan_id`
- `retry_ordinal`
- `lease_token`
- `lease_expires_at`
- `heartbeat_at`
- `next_run_at`
- `hard_deadline_at`
- `error_code`
- `error_message_safe`
- `last_progress_at`
- `started_at`
- `completed_at`
- `superseded_at`
- `created_at`
- `updated_at`

孩子表增加 `grade_selection_revision`。只有规范化后的年级或学年发生变化时才递增；普通资料保存和重复提交同一年级不递增。计划唯一键固定为 `child_id + grade_selection_revision + target_fingerprint + retry_ordinal`。

`target_spec_json` 保存规范化目标；`target_fingerprint` 是该 JSON 的 SHA-256。目标至少包含年级、语数英、每科 boundary 数和课程数、每个 skillId 与 boundaryVersion、curriculumVersion、LessonPackage compiler 版本、教师与 voice 合同、完整 Runtime 合同和变体数。它不使用每次保存都会变化的 `grade_confirmed_at`。`request_id` 唯一绑定一次孩子计划或重试；`shared_build_request_id` 只由 target fingerprint 派生，因此不同孩子可以安全共享同一 catalog build。结果是：

- 同一年级重复保存返回原计划；
- `一年级 -> 二年级 -> 一年级` 会创建新的选择版本，不会把旧 superseded 计划重新变成当前计划；
- 教师、声音、课件或课程边界合同升级时会创建新目标，不会误复用旧课件。

### 4.2 `learning_curriculum_preparation_events`

追加式事件记录计划的阶段变化、计数和安全错误码。它不保存 Provider 原始错误、密钥、Prompt 或儿童隐私文本。

### 4.3 `learning_catalog_active_grade_scopes`

现有 catalog release 激活会退役同课程版本的其他 active release，不能同时服务多个年级。新增年级级发布指针：

- 主键：`curriculum_version + grade_code`
- 当前 `release_id`
- `target_fingerprint`
- `preparation_contract_version`
- `activated_at`
- `updated_at`

新 release 必须只包含一个年级、覆盖该年级三科的全部当前边界，并全部 ready。激活事务只切换这个年级的指针，不影响其他年级。学生课程查询必须同时匹配孩子年级和该指针。

已有一年级数学 release 在完整一年级三科发布成功前继续可读；新指针切换后再停止给新任务分配旧 release。历史会话继续固定旧版本。

## 5. 状态机

对家长公开的状态固定为：

```text
queued
  -> planning
  -> generating_content
  -> building_classrooms
  -> generating_speech
  -> validating
  -> publishing
  -> ready

任一处理中阶段 -> retry_wait -> 原阶段
任一非终态 -> failed
年级选择发生变化 -> superseded
```

计划 `status` 固定为 `queued | running | ready | failed | superseded`；`stage` 固定为 `queued | planning | generating_content | building_classrooms | generating_speech | validating | publishing | retry_wait | completed`。任一非终态可以进入 `retry_wait` 或 `failed`；孩子改为其他年级时，旧计划进入 `superseded`。`ready`、`failed`、`superseded` 是终态。

家长端文案分别为：排队中、规划课程、生成课程内容、制作互动课件、生成讲解语音、系统校验、发布课程、等待服务恢复后继续、课程已就绪、准备失败、年级已变更。

进度只能由已完成项目计数和阶段权重计算，禁止用前端计时器伪造。worker 使用短租约和心跳；租约过期后只能由另一个 worker 复用相同 requestId 接管，不能因此新增一次付费调用。

超时按阶段分别判断，不使用一个笼统的 15 分钟误杀长任务：planning 与 publishing 最长 2 分钟，单个内容或课件项目最长 10 分钟，完整 Runtime 最长 45 分钟，单条语音最长 3 分钟且单门课语音最长 30 分钟，validating 最长 10 分钟。下游状态有新进展时刷新阶段进度时间；超过硬截止才进入明确失败，不会无限保持 `running`。

每个课程项目最多一次初始生成和一次自动修复尝试。两次都失败后计划明确失败。家长点击重试时创建一条 successor plan，通过 `retry_of_plan_id` 关联原计划；旧 failed 计划保持不变。相同幂等键并发重试只创建一个 successor，不覆盖旧错误或事件。

家长手动重试预算固定为 1 次。客户端 `requestId` 只作为该家庭、该失败计划下的幂等输入；服务端保存的全局唯一 request key 必须由 `family_id + failed_plan_id + client requestId` 派生，不能直接把不同家庭都可能提交的字符串设为全局唯一键。已被新年级 revision 或新 target fingerprint 取代的失败计划不可重试。

## 6. 自动发布合同

取消人工审核不等于取消发布门。系统只有在下列门禁全部通过后才自动发布：

### 6.1 课程内容

- 年级、学科、能力边界和先修关系精确匹配；
- 题型、答案、数学表达式或语言规则通过确定性校验；
- 生成模型与独立验证模型结果一致；
- 不泄漏独立练习答案；
- 内容去重、长度、适龄性和安全规则通过；
- 三科全部当前边界均有可执行课程。

### 6.2 完整课堂

- 每门课严格 10 个连续场景；
- 必含 `slides`、`quiz`、`simulation`、`html_game`、`3d_visualization`、`multi_agent_roundtable`、`teacher_actions`；
- 互动 HTML 有真实状态变化，禁止空脚本和摆设按钮；
- 3D 有真实 WebGL/Three.js 渲染与交互；
- 至少 1 名教师、3 名同伴和 2 条不同同伴讨论；
- 每场有非空讲稿和独立语音动作；
- 教师身份、头像、声音和学科一致；
- 学生模式不出现 OpenMAIC 品牌、编辑、下载、Provider 设置或系统主题控件。

### 6.3 音频与对话能力

- 每场一条唯一、可读取、容器有效的音频，共 10 条；
- 数学样板沿用 `qwen-tts / qwen3-tts-flash / Serena`，其他学科由版本化教师注册表给出固定 voice；
- 不允许浏览器 TTS 或其他 Provider 降级；
- Runtime health 必须证明固定的 Kimi 对话策略与 Qwen ASR 策略；
- 正式开放前还需完成真实文字对话与真实麦克风转写的 Provider E2E，不以 `providerCall=false` 的路由探针代替。

英语和拼音不再等待人工发音审核。系统自动写入版本化音频校验回执，至少绑定 provider、model、voice、文本哈希、音频哈希、格式、时长、非静音检测和 Qwen ASR 回转文本比对结果。只有自动回执通过才产生 `auto_validated` 媒体证据；不能把机器结果伪装成人工 `approved`，也不能直接把旧 pending review 改成通过。学生发布查询显式接受当前合同下的 `auto_validated` 和历史人工 `approved`，两种证据保持可区分。

### 6.4 原子发布

同年级所有目标课程、课堂和音频全部通过后，一次事务切换年级发布指针。任何一门失败时，旧年级发布继续服务，候选 release 不对学生可见。

完整 Runtime 生成必须支持“候选 release 权限”：worker 可以为尚未 active、但已绑定当前计划与 target fingerprint 的候选 package 生成课堂；学生启动仍只允许当前年级指针下的 ready release。不能继续复用当前仅允许 active 样板课程的硬编码入口。

## 7. API 合同

### 7.1 年级保存响应

现有接口保持兼容：

- `POST /api/setup/child`
- `PATCH /api/children/{childId}`

当提交的小学年级发生变化或首次确定时，响应增加：

```json
{
  "learningPreparation": {
    "id": "lcp_...",
    "gradeCode": "primary_1",
    "gradeLabel": "一年级",
    "schemaVersion": "mira.learning.preparation.v1",
    "status": "queued",
    "stage": "queued",
    "subjects": [
      {
        "code": "chinese",
        "label": "语文",
        "readyCourseCount": 0,
        "failedCourseCount": 0,
        "totalCourseCount": 12
      },
      {
        "code": "math",
        "label": "数学",
        "readyCourseCount": 0,
        "failedCourseCount": 0,
        "totalCourseCount": 9
      },
      {
        "code": "english",
        "label": "英语",
        "readyCourseCount": 0,
        "failedCourseCount": 0,
        "totalCourseCount": 9
      }
    ],
    "progressPercent": 0,
    "totalCourseCount": 30,
    "readyCourseCount": 0,
    "failedCourseCount": 0,
    "canRetry": false,
    "retryAfterMs": 2500,
    "message": "已开始准备约 30 门一年级语文、数学和英语课程"
  }
}
```

保存事务只创建计划，不调用 OpenMAIC、Kimi、Qwen TTS 或 Qwen ASR。

### 7.2 家长查询

`GET /api/learning/preparations/current?childId={childId}`

返回当前年级计划、三科各自的完成数/总数、总阶段、最后进展时间和安全错误。学科名称和范围来自接口，App 不硬编码“语数英已完成”。家庭权限必须与现有孩子资料权限一致。

### 7.3 家长重试

`POST /api/learning/preparations/{planId}/retry`

请求体固定为 `{ "requestId": "..." }`。仅允许当前家庭、`failed` 计划且重试预算未超限。相同 requestId 重复请求返回同一 successor plan；不会二次派发。

### 7.4 内部 worker

内部接口只负责状态与运维，不对 App 暴露 Provider 细节。正式 worker 从数据库租约领取任务，不由 HTTP GET 或学生页面触发模型。

## 8. 家长端体验

首次设置保存成功后立即进入首页，不显示阻塞式生成页。首页学习区域展示一条紧凑的准备状态：

- 标题：`正在准备约 30 门一年级课程`
- 副文案：当前阶段与 `已完成 / 总课程`；
- 三科进度：语文、数学、英语；
- 失败时显示安全、可执行原因和“重新准备”；
- ready 后切换为“课程已就绪”，进入现有学习入口。

资料页修改年级后使用 learning feature 中的同一状态组件。旧年级已完成的历史报告仍可查看，但首页和新任务只使用新年级计划。

App 轮询采用退避策略，进入后台时停止；恢复前台立即刷新。后端实时事件可作为后续优化，不是第一检查点依赖。

在计划到达 `ready` 前，首页不调用 `/learning/today` 自动分配课程。网络状态刷新失败只显示“重新获取状态”，不会误触发生成重试。

小学孩子的当前计划为 `null` 时必须 fail closed，显示“课程还没有开始准备”，不能当作历史兼容的 ready。首页前台恢复、下拉刷新及任何实时刷新 helper 都先成功获取当前计划，只有明确 `ready` 才能请求 `/learning/today`。today provider 的缓存键必须同时包含 `childId + preparationId`；无论经过 queued 中间态还是直接从 ready 计划 A 切到 ready 计划 B，都不得按相同 childId 复用旧年级结果。

## 9. 第一检查点

本轮只实现并交付以下可见闭环，完成后停下让用户验收：

1. 年级首次保存和资料页修改都能事务内幂等创建计划；
2. 后端提供当前计划查询和失败计划重试合同；
3. 家长首页显示真实阶段、课程计数、失败和重试；
4. runner 只实现安全领取、心跳、分阶段 deadline、崩溃恢复和共享构建绑定，不启动真实批量模型生成；
5. 使用 fake generation adapter 的后端与 Flutter 测试证明完整状态流；
6. 生成首页 queued 与资料页 failed 两张固定尺寸 widget 截图，供用户在不写开发库的情况下验收；
7. 不写开发库测试学生、不修改历史任务/会话/报告。

第一检查点只把已验证的 `Serena` 记为“一年级数学样板健康基线”，不把它伪装成语数英共同的正式 voice。语文、数学、英语的 teacher profile/version 都进入 target fingerprint；语文和英语的正式 Qwen3 voice ID 在版本化 subject-voice registry 建立前保持 fail closed，后续 registry/voice 合同升级必须生成新 target fingerprint。

第二检查点才把现有 catalog 生成器接入计划 runner，并先用一年级三科小批量运行；第三检查点接完整 Runtime、Qwen3-TTS、自动发布和真实学生 E2E。

第二、第三检查点还必须补上现有链路的恢复缺口：`external_failed` 和 `course_ready` 需要 runner 继续推进，媒体 `generating` 需要 lease/stale 回收；任何恢复都复用原 logical requestId，不能因进程重启重复付费调用。

## 10. 计划修改范围

第一检查点预计修改：

- `backend/migrations/`：新增计划与事件表；
- `backend/repositories/`：新增 preparation repository；
- `backend/services/`：新增 coordinator/runner，并接入 setup/profile service；
- `backend/routes/api/v1/learning.py`：新增家长查询与重试 API；
- `backend/services/service_factory.py`、`backend/app.py`、`backend/core/config.py`：依赖和显式开关；
- `mobile/lib/src/features/learning/`：计划模型、repository 和状态组件；
- `mobile/lib/src/features/home/presentation/widgets/home_primary_learning_preview.dart`：嵌入准备状态；
- `backend/services/setup_service.py`、`backend/services/profile_service.py` 及其 repository：只在现有年级保存事务内 reserve plan，不嵌套调用 catalog create/run；
- setup/profile 定向测试、学习 API 测试、runner 状态机测试和 Flutter widget/repository 测试。

不会在第一检查点修改 OpenMAIC Runtime、Gateway、学生 Web、模型路由或真实 Provider 配置。

## 11. 验收标准

- 同一孩子重复保存同一年级只得到同一计划；
- 并发保存不会创建重复计划或重复 worker claim；
- 两个孩子选择同一年级得到两条孩子计划，但共享同一个 target fingerprint 和 catalog build；
- 改年级创建新计划并 supersede 旧非终态计划，不改历史学习数据；
- `一年级 -> 二年级 -> 一年级` 创建新的选择 revision，不复活旧计划；
- 保存年级接口在没有模型服务时仍可快速返回；
- 家长端能区分 queued、各处理中阶段、ready、failed、superseded；
- stale 状态在有限时间内终结，不能无限“制作中”；
- 失败重试幂等且有次数上限；
- 学生和 `GET /learning/today` 不调用生成器；
- 自动发布前必须满足完整机器合同，不存在“生成成功即上线”的旁路；
- 日常排课不创建生成任务；只有首次年级准备、合同升级或 ready 未学库存低于 14 门时才增量生成；
- 后端定向测试、迁移测试、并发测试、`flutter analyze` 和相关 `flutter test` 全部通过。

## 12. 非目标

- 第一检查点不调用真实 Kimi、Qwen TTS、Qwen ASR 或 OpenMAIC 生成；
- 第一检查点不批量生成 1–6 年级课程；
- 不引入日计划或 `daily_plan` 新域；
- 不删除、覆盖或重写历史课程、任务、会话和报告；
- 不把教材同步、地区教材版本或全学期覆盖作为当前承诺。
