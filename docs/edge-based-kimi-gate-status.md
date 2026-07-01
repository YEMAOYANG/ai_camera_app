# Edge-based Kimi Gate 计划完成度对照表

> **计划源文件：** [edge-based_kimi_gate_f76b6b18.plan.md](/Users/sqcopenclaw/.cursor/plans/edge-based_kimi_gate_f76b6b18.plan.md)（v4.2 实施基线）  
> **对照日期：** 2026-06-30  
> **仓库 checkpoint：** `1ba2852`（`origin/kindergarten-v1` 已同步）  
> **说明：** 计划 frontmatter 中 slice 2–4 仍标 `pending`，但代码与测试显示**大部分已落地**；本表以仓库实际状态为准。

---

## 执行切片总览

| 切片 | 计划内容 | 状态 | 证据 / 备注 |
|------|----------|------|-------------|
| **1a** | `general_lane` + G1–G4 单测 | ✅ 完成 | `observation_cloud_gate.py`；`test_observation_cloud_gate.py` G1–G4 |
| **1b** | `care_critical_lane` + C1–C11 | ✅ 完成 | posture / toy leave / meal / unsafe 分支 + 单测 |
| **1b-fix** | `meal_habit` policy 餐窗 gating | ✅ 完成 | `care_routine_window_resolver.py`；`test_care_policy_meal_habit_window.py` |
| **2** | runtime `cloud_gate` / `care_behavior` + display 新鲜度 | ✅ 完成 | `observation_runtime_state.py`；`test_observation_runtime_display.py` |
| **3** | `run_tick` 三阶段 + capabilities 三元组 | ✅ 完成 | `camera_observe_service.py`；`test_camera_observe_cloud_gate_tick.py` |
| **4** | API + Flutter 新鲜度 + 联调 | ✅ 完成 | `camera_bridge.py`；`camera_models.dart`；`home_summary_test.dart`；E2E runbook |
| **4∥** | 作息 R1–R7 不可回归 | ✅ 完成 | `test_care_observation_contract.py` routine 系列；全量 discover 249+ OK |
| **track-ui-ia** | 看护/作息 UI 收口 F1–F4 | ✅ 基本完成 | commit `7b58fb6`；`app_smoke_test.dart` F1/F3/F4 |
| **5** | lightweight absent + events 过滤 | ⏸ 未做 | 计划标注可选；events API 未默认过滤 `local_prefilter` |

---

## 硬约束 D1–D4

| ID | 约束 | 状态 | 证据 |
|----|------|------|------|
| **D1** | meal 时间窗 routine 为主，capability `timeWindows` 仅 fallback | ✅ | `care_routine_window_resolver.py`；C12 单测 |
| **D2** | toy unsafe 仅消费结构化 `play_safety_*` | ✅ | C13；enrich + payload_builder |
| **D3** | childId 缺失硬失败，优先级 > force_analyze | ✅ | `missing_child_id`；tick + gate 单测 |
| **D4** | DB 与 Kimi 调用分离（三阶段） | ✅ 实现 | prefilter/gate/Kimi 在 `_load` 与 `_save` 之间；**无独立 C15 单测** |

---

## 测试矩阵

### General / Critical（G + C）

| # | 场景 | 状态 | 测试位置 |
|---|------|------|----------|
| G1 | 空房间 stable 不调 Kimi | ✅ | `test_g1_*` |
| G2 | person_stable 在 heartbeat 内不调 | ✅ | `test_g2_*` |
| G3 | motion cooldown | ✅ | `test_g3_*` |
| G4 | force_analyze 绕过（有 childId） | ✅ | `test_g4_*` |
| — | missing_child_id > force_analyze | ✅ | `test_missing_child_id_*` |
| — | motion_active 周期性采样 | ✅ | `1ba2852`；`test_g5_motion_active_periodic_sample_*` |
| C12 | meal 仅 routine window | ✅ | `test_c12_*`，`test_s3_*` |
| C13 | unsafe 需结构化 toy 上下文 | ✅ | `test_c13_*` |
| C14 | childId 缺失 tick 失败 | ✅ | 同 missing_child_id 用例 |
| C15 | Kimi 期间不嵌套 DB 事务 | ⚠️ 部分 | 架构已分离；**缺命名单测** |

### Scenario 分工 S1–S5

| # | 场景 | 状态 | 测试位置 |
|---|------|------|----------|
| S1 | posture 不受作息窗限制 | ✅ | `test_s1_posture_*`；policy window 测试 |
| S2 | toy_cleanup 不受作息窗限制 | ✅ | `test_s2_toy_cleanup_*`；policy 测试 |
| S3 | meal_habit 仅餐窗内 | ✅ | `test_s3_meal_habit_*` |
| S4 | meal_start / wake_up / nap / bedtime 由 routine tick | ✅ | contract routine 测试（gate 文件内 S4 编号已用于 screen_use） |
| S5 | gate 改造后 R1–R7 仍全绿 | ✅ | 全量 discover 通过 |

### Flutter IA F1–F4

| # | 期望 | 状态 | 备注 |
|---|------|------|------|
| F1 | 看护页：坐姿、玩具、用餐习惯、屏幕；不显示作息型能力 | ✅ | `app_smoke_test` absentTexts |
| F2 | 用餐中看护文案含餐窗说明 | ✅ | 文案为「只在早餐、午餐、晚餐时间内…」 |
| F3 | 作息页：起床、三餐、午睡、晚睡 | ✅ | smoke 断言 |
| F4 | 无 scenario/backend 工程词 | ✅ | 人工 + smoke |

### 作息不可回归 R1–R7

| 范围 | 状态 | 证据 |
|------|------|------|
| R1–R7（到点、cooldown、dailyLimit、allowSpeaker、WS 等） | ✅ | `test_care_observation_contract.py` 多组 routine 用例；E2E runbook 已跑通 |

---

## 验收清单（计划 §验收清单）

| 项 | 状态 | 说明 |
|----|------|------|
| Kimi 降本（无能力家庭不每 tick） | ✅ | general lane + gate skip |
| posture 60s；toy leave 强制 Kimi；meal 仅餐窗 | ✅ | critical lane + 单测 |
| unsafe 结构化；childId 硬失败 | ✅ | |
| DB/Kimi 不同事务 | ✅ | 实现完成；C15 单测待补 |
| 作息 R1–R7 + S1–S5 | ✅ | |
| display 新鲜度 fresh/stale/prefilter_only | ✅ | API + Flutter |
| track-ui-ia F1–F4 | ✅ | V1 后新增第 4 项 screen_use |

---

## 未完成 / 延后项

| 项 | 优先级 | 说明 |
|----|--------|------|
| **切片 5** lightweight absent + events 默认过滤 | 低（计划可选） | `empty_stable` 首条 lightweight 记录；events 仍展示 prefilter 事件 |
| **ability-aware heartbeat** | 中（V2） | v3 讨论预留；当前固定 `APP_CLOUD_PERSON_HEARTBEAT_SECONDS=900` |
| **C15 命名单测** | 低 | mock Kimi 阻塞时 assert transaction 未重入 |
| **计划 frontmatter 同步** | 低 | 将 slice 2–4、track-ui-ia 标为 completed |
| **screen_use critical lane** | — | V1 screen_use 能力；已合入 `c9b5c61` + `1ba2852` |
| **P0 ability-aware gate v2.1** | ✅ | person_return critical、`capability_discovery` 180s、`meal_window_entered`、transition 保守记录、`child_visible` NON_ACTIONABLE；见 `test_observation_cloud_gate.ObservationCloudGateP0Test` |

---

## P0 v2.1（ability-aware gate 收口）

| 项 | 状态 | 说明 |
|----|------|------|
| `person_return` critical lane | ✅ | general 仍 `cloud_gate_person_return`；有 childId + 行为看护能力时 critical 升级 |
| `capability_discovery` 180s | ✅ | person_stable + 有能力 + 无 active monitor |
| `meal_window_entered` | ✅ | 仅 meal_habit 餐窗边沿 |
| transition 保守记录 | ✅ | ≥0.5 写 care event；<0.5 仅 monitor/display |
| `child_visible` NON_ACTIONABLE | ✅ | 不 speak；不抢 screen/posture 等 primary payload |
| P1（idle backoff / ability heartbeat / interval 对齐） | ⏸ 未做 | 见 v2.1 计划 |
| **P1-A idle backoff** | ✅ | `102c59c` |
| **P1-B1 ability-aware heartbeat** | ✅ | `8644455` |
| **P1-B2 active monitor interval 对齐** | 🚧 实现中 | 仅 posture/screen/meal critical interval；不含 screen resample 90s |

---

## P1-B2 说明（active monitor interval）

- Gate critical interval 从 capability `minObservationSeconds` 解析，经 per-scenario clamp，**不等于** policy 连续秒数门槛。
- **不含**：`should_force_screen_use_resample`（仍独立 90s）、toy_cleanup periodic interval。
- 默认 capability 下有效 interval：posture 60、screen 90、meal 120（与 P1-B2 前一致）。

---

## 统计摘要

| 维度 | 数量 |
|------|------|
| 计划内执行切片 | 9 项 |
| 已完成 | **8** |
| 可选未做 | **1**（切片 5） |
| 硬约束 D1–D4 | 4/4 实现，C15 测试待补 |
| 验收清单 | **7/7** 功能达成 |

**结论：** Edge-based Kimi Gate **v4.2 主体已完成**，可视为生产可用基线。剩余工作：可选 slice 5、ability-aware heartbeat（见 [screen-use-v2-plan.md](./screen-use-v2-plan.md) SU2-6）、C15 单测、计划 frontmatter 同步。

---

## 相关文档

- [E2E 联调 Runbook](./e2e-care-reminder-runbook.md)
- [屏幕使用 V2 计划](./screen-use-v2-plan.md)
