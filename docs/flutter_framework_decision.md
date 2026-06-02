# Flutter 框架选型记录

日期：2026-06-02

## GitHub/模板调研结论

没有一个可以直接称为“完美”的 Flutter 模板适合照搬。更稳妥的做法是用成熟工程能力做底座，再按米拉家长端的业务域建立模块。

| 方案 | 优点 | 不足 | 结论 |
|---|---|---|---|
| Very Good CLI / Very Good Core | 官方化程度高，带多平台、多 flavor、i18n、Bloc、测试和 CI | 默认是 Bloc + counter 起步，对米拉的设备/任务/证据/告警域仍需大量改造 | 作为工程质量参考，不直接照搬 |
| momshaddinury/flutter_template | Clean Architecture、Riverpod、go_router、代码生成、测试目录完整 | 星标和生态沉淀弱于 Very Good CLI，直接克隆会带入无关结构 | 作为 Riverpod Clean Architecture 参考 |
| SimpleBoilerplates/Flutter | RiverPod、Dio、go_router、Freezed，并由 very_good_cli 生成 | 模板偏通用，业务域仍需重建 | 参考其技术组合 |

## 本项目采用

当前仓库新增 `mobile/` Flutter 工程，采用：

- Flutter 官方工程作为干净起点，避免模板遗留代码和未知依赖。
- Riverpod 做状态管理与依赖注入，适合设备状态、任务状态、证据审核、告警、家庭权限等多状态流。
- go_router 做声明式路由，先形成家长端五个主入口：首页、任务、看护、告警、我的。
- Dio 做 API 客户端，后续对接 Python AI 后端、任务服务、设备服务和报告服务。
- Feature-first 目录，围绕 `home`、`tasks`、`live_care`、`alerts`、`profile` 扩展。

## 后续建议

1. 接入真实 API 前，先把 mock provider 替换为 repository 接口，保留 mock 与 remote 双实现。
2. 任务、证据、告警、报告四个域优先建立 domain model，再接 UI。
3. 等接口稳定后再引入 Freezed/json_serializable/codegen，避免早期反复生成文件。
4. 如果后续需要严格 CI，可再引入 Very Good Analysis 和覆盖率门槛。
