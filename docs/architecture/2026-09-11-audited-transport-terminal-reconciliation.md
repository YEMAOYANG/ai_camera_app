# 已停止本地传输的独立并发审计

状态：设计待审；未实现服务、未写入真实审计、未停服。本文件不启用策略、不新增授权或 Provider 调用。

## 问题与边界

`learning_budget_reservations.state=unknown` 表示结果或费用未知。现有 `_PENDING` 同时把 `reserved/dispatched/unknown` 用于费用持有和并发准入，因此四条历史 unknown 会一直占满默认四个并发名额。

不能把全部 unknown 当作请求已结束。Native `lib/server/mira-paid-budget.ts` 的流取消路径先写 unknown、后取消 reader；错误分片会写 unknown 后继续 enqueue；音频 HTTP 响应头校验失败也可能在响应体没有读完或取消时进入 unknown。这些路径不提供传输结束证明。

本方案只确认 **当前部署的本地请求传输已结束**。受管理进程退出并不能证明远端 Provider 已停止计算、没有费用或实际使用量为零；这些不确定性继续通过原 unknown、原 maxUnits 和后续真实结算保留。若并发限制被定义为“Provider 远端仍在计算的全部请求”，本方案不足以证明释放条件，仍必须取得 Provider 端终止回执。

## 最小实现范围

后续实现拟仅涉及：

- 新增 `backend/services/learning_transport_terminal_reconciliation.py`：只读 plan、受审计 apply、纯证据校验。
- 新增 `backend/scripts/reconcile_learning_transport_terminal.py`：独立人工 CLI，不能调用生成、重试、授权或 Provider。
- 修改 `backend/repositories/learning_budget_repository.py`：批量读取指定 pending reservation 的专用终止审计事件。
- 修改 `backend/services/learning_budget_service.py`：仅 observation 模式的并发计算扣除已验证终止的 unknown；保留现有 `_PENDING` 定义及费用、状态、授权上下文和重试判断。
- 对应离线 SQL/并发/篡改回归测试。本设计文件与现有精确 production +1 配置分开。

无需 schema migration：使用既有 `learning_budget_events`。无需 HTTP API；客户端、Native 的通用 unknown 接口不能写该专用审计。第一版不改 Native adapter，不自动确认未来 unknown。

## 两份不可混用的证据

**费用回执**仍用于现有 settle：必须来自同一物理请求的真实 usage/Provider 回执，不能借用 `.repair1` 或其他调用结果。

**本地传输终止证明**仅用于并发：由维护操作产生，绑定明确的 reservation、实际请求身份、来源部署，以及关闭该部署所有相关调用进程的证据。它不是 settle/release，不能修改账本任何原字段。

原始证据存放在私有的 `backend/data/learning-provider-replies/transport-terminal-<planSha256>.json`，只创建、不覆盖。终端只输出数量、摘要 SHA 和准入变化，不输出模型消息、个人字段、环境变量或密钥。

## 本次运行的前置条件

1. 等原 Pro 这次续写产生真实终态，保存最终文档、事件和失败历史。不能为本审计提前取消活跃制课。
2. 冻结本次明确的四个旧 unknown reservation ID。三条本课程 DeepSeek 和一条旧 Qwen 属于不同授权，必须分别绑定；不把两类费用并入同课，也不自动纳入之后的新 unknown。
3. 在停服前采集受管理服务的实际 PID、进程启动身份、cwd、命令和 build 身份、进程树、端口归属及采集时间。每条 reservation 要有可复核的来源映射：authorization、dispatch/request 身份和 Native 记录，证明它属于此部署而非其他主机或 sidecar。
4. 通过 `openmaic-runtime/scripts/local-test-stack.sh stop` 关闭受管理栈。该脚本先停止 curriculum worker，再停止 Student Web、Native/Gateway，最后 Backend；MySQL/PostgreSQL 可以继续运行以供离线审计。不得使用“端口无人监听”作为唯一证明。
5. 再次核对原 PID 的启动身份已消失、已捕获的后代均退出、已知 Native/Gateway/worker/Backend 端口与进程没有替代者；检查同一部署目录下是否有额外手动启动的 Provider 调用进程。未知归属、重启、遗留子进程或不能排除其他主机仍拥有这些请求时，拒绝确认。
6. apply 期间栈保持停止。已有 stop 脚本只验证/终止已知服务，不会自动证明所有独立调用进程消失；审计 helper 必须额外核验第 5 项，不能仅相信脚本退出码。

旧请求可能来自已退出的前一代 Native 进程。此时不能虚构它属于本次刚停止的 PID：归因应写成“此部署的历史请求；现存该部署全部调用进程已停止”，保留原请求与历史进程证据。无法确认单部署排他归属的记录继续占位。

## CLI 与 plan 数据契约

拟定入口，以下是接口设计，不是已存在的可执行命令：

```text
reconcile_learning_transport_terminal.py plan
  --reservation-ids <明确的四个ID>
  --stop-evidence <维护操作证据manifest.json>
  --output <私有plan路径>

reconcile_learning_transport_terminal.py apply
  --plan <私有plan路径>
  --expected-plan-sha <已审阅SHA256>
  --confirm-managed-stack-stopped
```

plan 的稳定内容：

```json
{
  "schemaVersion": "mira.learning.transport-terminal-reconciliation.v1",
  "confirmationKind": "managed_deployment_processes_exited",
  "scope": "local_transport_concurrency_only",
  "reservationIds": ["four explicitly selected IDs"],
  "reservations": ["full original rows, privately archived"],
  "authorizations": ["full original rows, privately archived"],
  "priorEventDigestByReservation": {"id": "sha256"},
  "sourceAttributionByReservation": {"id": "request/deployment evidence"},
  "deploymentIdentity": "stable identity of this local deployment",
  "stopEvidenceSha256": "sha256",
  "lastRequestDispatchedAt": 0,
  "localTransportEndedAt": 0,
  "approvalReference": "operator review reference"
}
```

`planSha256` 为上述 canonical JSON 的 digest；复查时间放在结果摘要之外，不能每次重查都改变已审阅 SHA。`localTransportEndedAt` 必须晚于四条原 dispatched_at，且来自成功停止和复核证据。不得用“超时了”或单个 session_end 代替停止证明。

第一版固定接受四个明确选择、状态均为 unknown 的历史行，不扫描并自动释放全局所有 unknown。发现新增 unknown 只报告；不得把它纳入旧 proof，也不得增加临时名额。

## apply 事务与持久事件

apply 先重读私有 proof、全部文件 hash、进程停止状态，再进入既有 `LearningBudgetRepository.locked()` 的 InnoDB 全局互斥事务，重新核对四条原行、授权行、每条事件历史与来源映射。锁内再次确认维护状态未变化。

每条 unknown 只 append 一条 event，`event_type=transport_terminal_confirmed`（符合既有 VARCHAR(32)）。不 UPDATE reservation、authorization、budget halt、金额、maxUnits、actualUnits、settlement、scope、expiry 或 policy；不补零费用，不创建新 grant。

事件 evidence 的最小结构：

```json
{
  "schemaVersion": "mira.learning.transport-terminal-receipt.v1",
  "planSha256": "sha256",
  "reservationId": "exact FK identity",
  "reservationSnapshotSha256": "digest of original complete unknown row",
  "authorizationId": "original authority",
  "requestIdentitySha256": "original request_identity_sha256",
  "stopEvidenceSha256": "sha256",
  "localTransportEndedAt": 0,
  "confirmationKind": "managed_deployment_processes_exited",
  "scope": "local_transport_concurrency_only"
}
```

审计事件本身是可信离线 operator 的持久承诺；相同事务内四条要么全写、要么全回滚。重复 apply 只有完整四条相同 proof 已存在时幂等成功；部分事件、不同 proof、重复冲突事件或原行改变均拒绝。已结算不需要并发确认，不能把变成 settled 的行重新写回 unknown。

## 准入规则

严格模式 `aggregateLimitsEnabled=true`：沿用全部三态 `_PENDING` 并发持有，行为完全不变。

可信 observation 模式：

```text
active = reserved + dispatched + unknown_without_valid_terminal_receipt
```

有效 receipt 必须同时匹配 reservation FK、原授权、原 request identity、当前完整 unknown 行 digest、合法专用 schema/kind/scope，并且来自完整、无冲突的同批 plan 事件。读取缺失、结构错误或无法验证时继续计入并发，不能 fail open。实现可把完整批次摘要放入每个 event 以便 SQL 批量校验；热路径不得信任调用方 reasonCode，也不应读取任意用户提供的文件路径。

费用计算和未知结果判断仍按原 `_PENDING` 三态；`unsettledReservationCount` 仍包含这些 unknown。原请求幂等 dispatch 继续返回不允许，旧 Native/Backend attempt 仍不能因此自动重试。未来真实 Provider 回执可以正常 settle，原终止审计保留。

临时 production +1 配置需要人工在恢复正常课堂策略时移除。该策略回到 `maxInflightCalls=4` 后，四条已有终止审计的旧 unknown 不占本地活跃名额；四个新的 reserved/dispatched 仍占满，第五个拒绝。未来新 unknown 没有本次 proof，继续占位，不能自动继承终止结论。

## 验收与实际可证明范围

- 离线 plan/apply：四条费用行和所有原授权逐字段不变，仅新增四条专用 event；无 Provider/课程/派发新增。
- 相同 proof apply 幂等；错误请求、错误授权、跨部署、停止后进程重启、审计篡改、部分事件、重复事件、行状态改变、额外 unknown 自动纳入均拒绝。
- observation：四条经审计旧 unknown + 四条新活跃请求可以共存，第五条新活跃请求拒绝；新 unknown 没有证明仍阻塞。并行 reserve 在现有 SQL 锁下不能突破四个活跃名额。
- 严格默认模式：相同旧 unknown 仍按原规则计入并发。关闭 observation 不隐式废除风险持有。
- 之后启动正常 Backend/Native/Student 并通过学生原会话发起正常讨论，证明接口恢复；不能仅凭 budget 单元测试声称课堂已恢复。
- 本地进程终止没有揭示真实远端费用；UI/日志应使用“本地传输已结束，费用待核对”，不能显示“已退款”“免费”“Provider 已取消”。

## 本地实际执行

2026-09-11 21:57，原 AI 已终止并导出原始未审核稿后，采集四个托管服务完整身份，使用现有 local-test-stack.sh stop 停止服务并复查所有原 PID 已退出、3000/3100/3101/8000 端口关闭。基础设施身份另列，不停止 Codex、IDE 或用户终端。真实 plan/apply SHA `ea65c1f5acacc86c22f65997d751ea4e80c005383a426140e8589abf2646cfbf`，新增四条传输终止事件，费用行与授权行修改均为零，Provider 调用零。

已移除临时 production +1 并启动新 Backend；只读复查 reserved=0、dispatched=0、unknown=4，四条 receipt 全部有效，无额外未知请求。费用仍待核对，不是 settled/refund，正常学生对话尚待服务恢复后的实际检查。
