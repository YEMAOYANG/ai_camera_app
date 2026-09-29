# 外研英语教材起点与课标版本核对

家长发现“外研版三年级”的起点容易混淆。本次核对现有全部 32 册外研小学英语，并补入国家平台可核验的陈琳三年级起点 8 册。详细系列数量和官方依据见 [教材修订说明](../../backend/content/textbooks/fltrp-reviewed-v1/README.md)。

## 架构影响与文件

只涉及教材库、后端版本标签和家长选书页；沿用现有持久化、权限、学生读取及课程绑定流程。没有数据库结构变更。

- `backend/content/textbooks/fltrp-reviewed-v1/`：32 份元数据修订、8 份新增书目、8 份新增目录。
- `backend/content/textbooks/sources/fltrp-edition-audit-20260928.json`：逐册核验及修正映射。
- `backend/content/textbooks/sources/smartedu-sync-fltrp-three-year-20260928.json` 和 8 份目录快照：新增系列的官方身份与内容目录证据。
- `backend/content/textbook_metadata.py`：准确显示已有选书的标签，保留原修订号和摘要。
- `backend/content/textbook_catalog.py`：认可精确审查通过的显示修正和新增同步课堂来源。
- `backend/services/textbook_learning_service.py`：家长和学生统一使用核验后的名称。
- `mobile/lib/src/features/learning/presentation/school_textbooks_page.dart`：在选项中显示课标版本。

API 继续使用 `mira.learning.textbooks.v1`，保持 `editionId`、`revisionId`、`sourceUrl`、`editionLabel` 等字段。只有 `editionLabel` 的可读名称得到修正；保存选择和课程授权语义不变。新旧教材与不同起点均为独立身份。

## 本机数据库结果

目标重新确认是 `development`、`127.0.0.1:3306/ai_camera_app_dev`。导入前备份 32 个教材身份、45 个原修订，并在隔离数据库中恢复备份验证增量导入。

事务新增 48 份修订，675 份原修订保持一致，合计 723 份。重复导入新增 0。家长选择、选择事件、课件绑定和迁移历史均在数据库内计算摘要，前后一致；没有导出孩子资料或替家长改选教材。

通过合成只读上下文回查六个年级、上下学期 12 个组合，合计 40 册外研教材，未出现书目与目录的重复选项。三年级上册分别展示：

- 陈琳一年级起点，2011 课标版；
- 陈琳三年级起点，2011 课标版；
- 孙有中、刘兆义、张祖春三年级起点，各自的 2022 课标修订版。

新版尚未核验的目录仍保持待同步，没有用陈琳旧版目录填充新版。课件生成未启动。

仅用项目托管脚本重载已核实身份的本机后端，健康检查通过；使用 `api-passive`，并显式设置 `MIRA_LOCAL_TEST_CURRICULUM_WORKER_ENABLED=0`，本次没有启动课程生成。本次未重启其他运行服务。

## 验证记录

- 723 份教材 manifest 校验通过；本次开始前的 909 个教材和来源 JSON 文件摘要一致。
- 54 项针对性后端测试通过，覆盖两个起点、上下学期、源身份错配、不可变修订、重复导入、已选书名修正和课程读取。
- Flutter 真实渲染截图核验通过：同一主编的一起与三起可同时区分，2022 课标标识可见。截图使用合成测试上下文，不是实际家庭账号。
- 全部 86 项后端教材测试通过。
- `flutter analyze` 无问题；`flutter test` 373 项通过、1 项原有可选视觉测试跳过。

本机核验文件位于 `output/fltrp-audit-20260928/`：官方元数据回查、导入前备份、隔离恢复结果、事务导入结果、只读目录结果和界面截图。未声称完成手机重新安装或真机登录验收。
