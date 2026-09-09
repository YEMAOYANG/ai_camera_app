# DeepSeek 百炼免费额度与官方回切

2026-09-09 本地现状：用户要求后已切回 DeepSeek 官方，Pro/Flash 请求使用官方模型 ID。百炼曾返回 `AllocationQuota.FreeTierOnly`；保留该失败审计与百炼配置。用户随后明确批准官方三科首课各一门的生成与本地测试发布；官方探测已通过。当前由受限操作器推进，独立课程 worker 保持停止，避免超出已授权范围。

本机 OpenMAIC 使用 `openmaic-runtime/.env` 的 `DEEPSEEK_SERVICE` 选择推理服务。
此开关由 native-runtime.sh 读取；Docker Compose 不读取这个原生启动选择器。

| 配置 | 官方 | 百炼 |
|---|---|---|
| DEEPSEEK_SERVICE | official | bailian |
| 凭据 | DEEPSEEK_API_KEY | BAILIAN_DEEPSEEK_API_KEY |
| 地址 | DEEPSEEK_BASE_URL | BAILIAN_DEEPSEEK_BASE_URL |
| 专业创作模型（请求实际发送值） | deepseek-v4-pro | deepseek-v4-pro-0813 |
| 独立校验模型（请求实际发送值） | deepseek-v4-flash | deepseek-v4-flash-0731 |

内部阶段仍使用 `deepseek-v4-pro` / `deepseek-v4-flash` 逻辑标识。
`lib/ai/deepseek-service.ts` 在 HTTP 边界映射百炼日期版本，并把
`thinking.type` 转为 `enable_thinking`。官方模型标识保持原值。
DeepSeek 的结构化输出使用兼容 JSON 模式时，必须把原 JSON Schema
同时保留在系统提示中；不能仅删除 `json_schema` 后期待模型猜中字段。
第 57 号补丁已补上这一点，并在真实请求适配函数的出口验证。
`GET /api/health` 的 `runtimePolicy.modelService` 报告服务和实际模型映射，
不返回凭据。正式 readiness 探测也使用同一转换函数。

## 免费额度保护

2026-09-09 已在控制台为 **Pro 0813** 和 **Flash 0731** 分别开启
“免费额度用尽即停”，刷新后确认保存。每模型初始额度 1,000,000 tokens，
有效期至 2026-11-17。实际剩余额度以控制台为准。

`BAILIAN_DEEPSEEK_FREE_TIER_ONLY_CONFIRMED=1` 只是操作者对控制台设置的
确认记录，并不会代替或实时验证云端开关。不要关闭这两个模型的云端开关。
没有实现自动官方回退：用户明确选择额度用完后停止百炼，再协助切回官方。
一般网络异常、超时、限流也不会触发跨服务切换。

## 回切步骤（协助操作时执行）

1. 同时检查课程 worker、MySQL Runtime 的 `generating` 状态和 PostgreSQL
   Agent session 的 `running` / `queued` 状态。Runtime 已失败不代表 Agent
   已停止；两层都要核实。部署前等待结束，或通过原 session 的取消接口明确停止，
   保留原任务、课件与审计，再确认无活动 Agent。
2. 使用 `openmaic-runtime/scripts/local-test-stack.sh stop-curriculum-worker`
   暂停新任务；核对服务 PID 身份后停止 OpenMAIC。
3. 将 `openmaic-runtime/.env` 中 `DEEPSEEK_SERVICE=bailian` 改为
   `DEEPSEEK_SERVICE=official`。官方 Key、地址原样保留，无需重新申请或复制。
4. 按现有 local-test-stack 的生产启动方式恢复 API、学生网页和课堂服务；仅在当前生成范围与付费已授权后恢复课程 worker。
   仅切换服务配置不需要重新构建。
5. 检查 `/api/health` 的服务标识与课堂网关健康，并验证一笔小请求。

切换服务不意味着重新生成已发布课程，也不允许重放结果不确定的历史请求。
若需要重试已失败课程，必须沿用项目既有的请求身份、审计和重试约束。

官方资料：
- https://help.aliyun.com/zh/model-studio/deepseek-api
- https://platform.qianwenai.com/home/benefits



## 独立课程库操作

从 `backend/` 运行；`status` 只读，`prepare` 仅写入期望覆盖，不调用模型。

`python3 scripts/course_library.py check-dependencies` 检查当前配置的资料检索服务。
它使用短查询，不传 PDF，不触发检索查询改写或课程创作；客户端最多等待 20 秒。
当前 Brave 网页检索仍会返回 HTTP 429，应先恢复检索或配置稳定的正式检索服务。
`run-canaries` 会先执行同一检查；失败时不探测付费模型、不解除失败记录，
也不开始新的课堂尝试。入口检查成功不代表后续所有检索一定成功。

```sh
python3 scripts/course_library.py status
python3 scripts/course_library.py prepare --scope canary
```

正式生成使用受限命令，硬性限定三科首课；保持独立 worker 停止，避免两个操作者竞争。`--confirm-paid-canaries` 必须对应真实用户付费授权，不能仅因切换配置就使用。`--probe-provider` 用于已授权的换服务探测，未知费用故障不会自行解除。

```sh
python3 scripts/course_library.py run-canaries --confirm-paid-canaries --probe-provider
```

若需要重试一门明确失败的课堂，加 `--retry-item <build-item-id>`。仅解除该条最新已知失败，不清除原始 Runtime/派发记录；若新尝试又失败，必须重新处理，不能继承上次授权反复重试。结果不明的调用始终不走这条重试入口。

`LEARNING_COURSE_SUPPLY_SCOPE` 是持续 worker 的生产范围上限，默认 `canary`。扩大到 `first_unit` 或 `catalog` 前确认课程范围、成本与教研验收；`prepare` 写入的范围会在下一次 worker 按配置刷新时收敛。此次未提高调用限额，也未生成首课之外的课程。

受保护的只读接口：`GET /internal/learning/curriculum-preparations/library/status`，使用原有内部 Token。返回期望覆盖、真实 ready 数量、缺失知识点、阻塞原因、进度/活动时间和样本统计，支持 ETag；不返回密钥或个人学习数据。

家长准备接口、学生今日课程和课程库列表增加可选 `courseSupply` 摘要，旧字段保持兼容；摘要含 `paused`、`delayed`、`message`、`retryAfterMs` 与版本标识。部署这次更新时同时更新家长 App，以支持旧协议的严格解析器中的可选字段。

## 2026-09-09 课堂检查修复

第 55 号补丁修复小屏幕下跨进程 iframe 的点击坐标：以真实 DOM 中心和外层缩放比例计算鼠标位置，在两个文档中检查遮挡，再观察页面响应。没有以脚本触发 click 替代真实点击，也没有放宽课程发布门。两个已失败互动页面均已用正确坐标复现响应。

质量工具现在返回剩余修正次数，最后一次仍未通过时结束 Agent 当前工具批次，避免持续改写却已无可用检查次数。已有三次检查记录与失败 Runtime 保留；新的受限尝试仍遵守每门最多三次 Runtime、三科各一门发布的原有上限。
