# 科学教材目录与两端接入

2026-09-28：科学成为固定教材的第四门学科。家长在同一教材设置页选择版本，学生书包增加科学 3D 课本，目录和课程开放状态共用后端固定教材接口。没有生成 OpenMAIC 课件。

## 来源和覆盖

来源为[国家中小学智慧教育平台电子教材](https://basic.smartedu.cn/tchMaterial)。逐册对应平台资源 ID、版本、学制、年级、上下册，不把一个版本的目录套用到其他版本。

| 平台版本 | 册数 | 完整目录 | 部分目录 |
| --- | ---: | ---: | ---: |
| 人教鄂教版 | 12 | 12 | 0 |
| 冀人版 | 12 | 12 | 0 |
| 大象社版 | 12 | 12 | 0 |
| 教科版 | 12 | 12 | 0 |
| 沪科技版 | 7 | 6 | 1 |
| 湘科版 | 12 | 12 | 0 |
| 粤教科技版 | 12 | 12 | 0 |
| 苏教版 | 12 | 12 | 0 |
| 青岛版 | 22 | 22 | 0 |
| 合计 | 113 | 112 | 1 |

其中六三学制 96 册，覆盖一至六年级上下册；五四学制 17 册，按平台实际在架书目收录。共 2,281 个末级目录条目，包含课程、活动、复习及附录，不等同于 2,281 个已生成课件。

- 25 册采用官方电子课本的目录关系、目录树和页码映射。
- 88 册采用官方公开预览目录页，OCR 辅助定位后逐页面视核对，保存目录页 URL、SHA-256、标题、层级和印刷页码。未推测 PDF 页码或课内小栏目。
- [沪科技版五四学制五年级上册](https://basic.smartedu.cn/tchMaterial/detail?contentId=48634ae3-10cd-b59d-ca1e-7affae2cf192)官方预览第 4 页缺少目录文字，仅第 5 页可核实第 4、5 单元共 5 课。本册保留 `partial`，未补写第 1—3 单元。后续补齐需要新的显式修订，不能覆盖已有目录。

书目清单在 `backend/content/textbooks/sources/smartedu-science-20260928.json`；核验快照在 `sources/smartedu-science-directories-20260928/`；统计在 [科学覆盖清单](../../backend/content/textbooks/sources/science-sync-coverage-20260928.json)。产品仓库仅存目录元数据，不存这些教材正文或预览图片。

此前语数英的 227 册空书目仍维持“目录待同步”；本次科学补充不表示其他三科的所有出版社目录已经齐全。

## 两端行为与接口

沿用 `mira.learning.textbooks.v1`，固定教材 `subject` 增加 `science`。家长批量选书最多 4 科，服务端原子保存，继续校验家庭权限、年级学期和选择修订；某一科冲突时整批回滚。各科可稍后选择，不自动替家长确认。

Flutter 注册后的教材设置与“我的 → 孩子资料”共用 `SchoolTextbooksPage`。家长首页和孩子资料的课程状态都显示四科；目录尚未生成课件时明确显示待生成，部分目录有单独提示。学期仍沿用日期建议与家长手动修改规则。

学生端新增科学书、原创科学封面和对应的拾取、展开、返回动作。3D 模型 v4 包含四本科目，四科文字入口保持可用；375 像素窄屏分为两行。仅显示家长确认的版本，未选科学时提示家长选书，不能自行换版本或启动生成。

原始封面出处及制作说明见 [封面说明](../design-assets/book-covers-v3/README.md)。固定教材学科与旧的自动生成课程学科类型分开，未扩展或启用旧生成任务。

## 增量同步与本地数据库

新增 113 个书目修订、113 个目录修订。修订 ID 由核验快照摘要产生；已有任意非空目录直接保留。重复离线构建保留全部 113 册，重复数据库导入新增 0 条。

新增目录的教学任务书为 `draft`，使用依据为 `pending`；没有调用模型、TTS、课件生成、发布或课程准备操作。

`084_textbook_science_selection.sql` 只扩大学科 CHECK 约束，保留学期和修订号约束。按用户本轮批准，在 `127.0.0.1:3306/ai_camera_app_dev` 应用；应用前已备份表结构、教材元数据，并在独立 socket MySQL 验证科学可写、非法学科/学期/修订仍被拒绝。084 已登记，不能再次盲目执行原始 ALTER。

数据库导入验证结果：

- 新增 226 个科学修订；再次导入新增 0 条。
- 既有 433 个教材修订逐条不变，1 条已发布课件绑定不变。
- 选择记录与历史在数据库内取摘要核对，结果不变，未读取真实孩子资料。
- 导入后数据库共 447 个教材身份；剔除此前已被官方替换的 9 个新选项，当前可选书目为 438 册。
- 合计 211 册具备完整或部分目录，5,928 个末级目录条目；另有 227 册仍只有书目。

备份和执行证据存于本机 `output/science-sync-20260928/`，不随产品源文件发布。

可重复的离线构建命令：

```sh
backend/.venv/bin/python backend/scripts/sync_textbook_directories.py build \
  --indexes backend/content/textbooks/science-v1 \
  --snapshots backend/content/textbooks/sources/smartedu-science-directories-20260928 \
  --output backend/content/textbooks/science-v1 \
  --report /tmp/science-repeat-build.json

backend/.venv/bin/python backend/scripts/textbooks.py validate-catalog \
  backend/content/textbooks/science-v1
```

## 验证

- 后端教材相关测试 78 项通过，包含四科原子保存、科学修订冲突回滚、越权隔离、冻结来源摘要、部分目录保留和生成入口限制。
- 开发库通过合成只读上下文检查 6 个年级 × 2 个学期，均返回四科和非空科学目录；无真实孩子记录写入。
- 学生端 lint、TypeScript 检查、252 项测试及生产构建通过。
- Flutter analyze 无问题；完整 Flutter test 371 项通过，1 个按开关跳过的视觉采集用例。单独开启视觉采集时教材页 18 项全部通过。SDK 仍提示 `flutter_webrtc` 尚不支持 iOS Swift Package Manager，当前分析与测试不受影响。
- 真实浏览器使用独立的合成会话和仓库科学目录，验证桌面/375 像素窄屏 WebGL 就绪、四科入口、无横向溢出、点击 3D 科学封面、目录课件待生成和返回书包。手机入口约 165 × 90 像素。
- Flutter 实际控件截图核对科学版本选择、四科保存布局；320 像素及放大文字流程测试无溢出。

本地受管后端、学生端已刷新，课程 worker 保持 `MIRA_LOCAL_TEST_CURRICULUM_WORKER_ENABLED=0`。这些检查不等同于手机真机安装、真实家庭账号端到端验收或全仓库所有后端业务测试。

实际截图：

- [学生四科书包](../../output/playwright/science-schoolbag-desktop.png)
- [学生手机书包](../../output/playwright/science-schoolbag-mobile.png)
- [科学目录](../../output/playwright/science-directory-desktop.png)
- [家长四科选择](../../output/parent-profile-redesign-20260928/subjects-selected.png)
- [家长科学版本](../../output/parent-profile-redesign-20260928/science-versions.png)
