# 屏幕使用提醒 V2 计划

> **状态：** 规划中（V1 已交付、联调通过并已推送远端）  
> **V1 checkpoints：**  
> - `c9b5c61` — Add screen use care capability（初始能力 + gate + Flutter 第 4 项）  
> - `1ba2852` — Fix screen use resample labeling and tighten reminder loop（联调修复：motion 采样、resample、duplicate 绕过、播报文案、1 分钟间隔下限）  
> **关联文档：** [Edge-based Kimi Gate 完成度对照](./edge-based-kimi-gate-status.md)

---

## V1 已交付范围（不再重复开发）

V1 以独立 scenario `screen_use` 完成主链路，产品决策如下：

| 决策 | V1 行为 |
|------|---------|
| 用餐中看手机 | **B1：** 餐窗内归 `meal_habit` 播报，`screen_use` 只记录 |
| 设备类型 | **phone / tablet** 可提醒；**TV / computer** 只记录 |
| 触发依据 | 结构化字段（`screen_device_visible`、`screen_use_active` 等），不靠 `activity=玩手机` |
| 与 posture | 结构化看屏优先，避免低头看手机双播 |
| 默认配置 | `minObservationSeconds=90`，`cooldownSeconds=1800`，`dailyLimit=3`，`confidenceThreshold=0.72` |
| App | 看护能力第 4 项 + 提醒方式（持续时长 / 间隔 / 每日上限；间隔最低 1 分钟） |

联调修复已合入 `1ba2852` 并推送 `origin/kindergarten-v1`。

---

## V2 目标

在 **不破坏 V1 合同测试** 的前提下，让「屏幕管理」更贴近家长预期：更细的场景区分、更合理的提醒节奏、更少误报/漏报。

### 产品目标

1. **设备与场景细分** — TV / 电脑、作业旁有屏、休闲看屏等，策略可区分「只记录 / 可提醒 / 永不提醒」。
2. **更智能的 Kimi 触发** — 屏幕能力开启时，person heartbeat 可缩短（ability-aware），低运动看屏不被 900s general heartbeat 拖慢。
3. **更严格的家长控制** — 提醒方式支持「严格模式」预设（更短间隔、更高每日上限），与 V1 1 分钟下限兼容。
4. **可观测与可回归** — 补 E2E runbook 段落、Flutter widget 测试、gate/policy 合同测试。

### 非目标（V2 不做）

- 不把 `screen_use` 塞回 `transition`
- 不恢复「靠 description 正则猜看屏」
- 不做端侧 NPU / 硬件下沉（见视觉预检长期计划）
- 不实现完整 eval UI 或 prompt 在线编辑器

---

## 计划任务

### P0 · 能力与策略

| ID | 任务 | 说明 | 依赖 |
|----|------|------|------|
| SU2-1 | TV / computer 可选提醒 | 按 `screen_device_type` 配置：默认仍只记录，家长可单独开启 | policy + payload |
| SU2-2 | `screen_use_context` 策略矩阵 | homework / leisure / meal / unknown 分别映射 record-only / remind / defer-to-meal | enrich + policy |
| SU2-3 | 作业场景看屏 | 写作业 + 平板辅助：区分「工具性看屏」与「分心刷视频」 | prompt + schema 细化 |
| SU2-4 | 距离风险分级 | `screen_distance_risk` ok / too_close / unknown 与 sustained 组合策略 | 已有 signal，补 policy 文档 |
| SU2-5 | 全局 speak 抑制（轻量） | 同一 tick 多 signal 时明确优先级表（非新引擎，扩展 winner-takes-all 文档） | payload_builder |

### P0 · Gate 与观察

| ID | 任务 | 说明 | 依赖 |
|----|------|------|------|
| SU2-6 | ability-aware heartbeat | `screen_use`（及 posture）开启时，`resolve_person_heartbeat_seconds()` 返回 300–600s | observation_cloud_gate |
| SU2-7 | screen interval 与 capability 对齐 | gate interval 可读 capability `minObservationSeconds`，减少 env 硬编码 | care_config + gate |
| SU2-8 | motion_active 采样文档化 | `motion_active_sample_seconds` 已在 `1ba2852` 落地；V2 补 `.env.example` 与 runbook 说明 | ✅ V1 已实现 |

### P1 · App 与体验

| ID | 任务 | 说明 |
|----|------|------|
| SU2-9 | 提醒方式「严格模式」预设 | 一键：持续 1min / 间隔 1min / 每日 6 次 |
| SU2-10 | 看护记录 copy 优化 | 区分「短暂看屏」「持续看屏」「距离过近」展示文案 |
| SU2-11 | Flutter widget 测试 | 覆盖「提醒方式」sheet、screen_use 摘要行 |
| SU2-12 | E2E runbook 增补 | 在 `docs/e2e-care-reminder-runbook.md` 增加 screen_use 四场景验收表 |

### P2 · 后续

| ID | 任务 | 说明 |
|----|------|------|
| SU2-13 | 屏幕时间日报/周报 | 只记录聚合，不新增 scenario |
| SU2-14 | 与任务模块联动 | 例如「完成作业后可看 20 分钟」— 需任务域 API，单独立项 |
| SU2-15 | prompt 版本 eval | 使用 prompt registry + scenario case，无完整 eval UI |

---

## 建议实施顺序

**V2 第一优先级（建议下一轮先做方案，不直接改代码）：**

1. **SU2-6** ability-aware heartbeat — 看屏/坐姿能力开启时缩短 person heartbeat
2. **SU2-7** screen interval 与 capability `minObservationSeconds` 对齐

原因：直接影响「看屏提醒是否及时」与「Kimi 成本是否可控」。TV/电脑提醒、严格模式、日报统计可后置。

```text
Phase A（gate 小迭代）: SU2-6 + SU2-7 → 方案 + 测试矩阵 → 再编码
Phase B（策略扩展）:     SU2-1 + SU2-2
Phase C（App 体验）:     SU2-9 + SU2-11 + SU2-12
Phase D（后续）:         SU2-3 + SU2-13 + SU2-14
```

---

## 验收标准（V2 Definition of Done）

- [ ] 合同测试：`test_screen_use_observation.py` + gate screen 用例全绿
- [ ] 后端全量 `unittest discover` 全绿
- [ ] Flutter `analyze` + `test` 全绿
- [ ] Runbook 四场景手动验收：短暂看屏 / 持续 phone / 餐窗看手机 / 低头看手机
- [ ] Kimi 调用频率：单摄像头 screen 场景 **≤ 计划 SLA**（10–60s 进 Kimi 判断，非每 tick）
- [ ] 无 `transition` / `activity=玩手机` 旧路径回归

---

## 相关文件（V1 基线）

| 层 | 路径 |
|----|------|
| 模型 | `backend/models/care.py` |
| Vision schema | `backend/schemas/vision.py`，`backend/prompts/vision/scene_observation_v1.md` |
| 信号 | `backend/services/vision_observation_enrich.py`，`observation_payload_builder.py` |
| Policy | `backend/services/care_policy_engine.py` |
| Gate | `backend/services/observation_cloud_gate.py` |
| 播报 | `backend/prompts/reminders/screen_use_v1.md` |
| App | `mobile/lib/src/features/profile/presentation/profile_pages.dart` |
| 测试 | `backend/tests/test_screen_use_observation.py`，`test_observation_cloud_gate.py` |

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-06-30 | 初版：V1 收口后整理 V2 backlog |
| 2026-06-30 | 同步 `1ba2852` checkpoint；调整 V2 优先级为 SU2-6/SU2-7 |
