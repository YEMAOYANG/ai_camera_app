# 一至六年级循序渐进课程：只读检查与上线操作

课程目录、已经生成的课件、正式可用课件、孩子当前能学的课是四种不同状态。当前注册表有 187 个单元、1038 个细课次；这些数字不能说明已经有相同数量的课件。实际版本和内容身份以只读命令输出为准，不在运维操作中手填哈希。

架构和版本边界见 [分级课程架构](../architecture/2026-09-16-progressive-primary-curriculum.md)。新课使用 `mira.primary.progressive.v1`，旧冻结任务按原合同恢复，不能给旧课改一个课次编号就当成新课发布。每个年级分别从本年级的入门内容开始，同年级内按前置知识推进。basic不是统一从一年级开始；缺少历史记录不能触发低年级补课，缺本年级课不能拿其他年级补位。

## 1. 只读检查

从项目根目录，使用已安装后端依赖的 Python 环境：

```sh
python3 backend/scripts/progressive_curriculum_readiness.py --help
python3 backend/scripts/progressive_curriculum_readiness.py
python3 backend/scripts/progressive_curriculum_readiness.py --grade primary_1 --subject chinese
python3 backend/scripts/progressive_curriculum_readiness.py --child-id EXISTING_CHILD_ID
```

命令使用现有 `AppConfig.from_env()` 和数据库连接配置，包括 `backend/.env`；在服务器上应由现有私有环境注入后端配置。不要把连接串或密钥放进命令行、检查报告或工单。命令不会创建 Flask 应用、启动 worker、创建摸底/学习任务、登记供给请求、执行迁移或调用 Provider。连接后使用 MySQL 只读事务，结束时 rollback；调用边界也拒绝非读取操作。

输出为 `mira.learning.progressive-readiness.v1` JSON。退出码 `0` 表示所请求的数据库检查完成且未发现阻断；`2` 表示阻断或验证范围不完整。参数错误由 argparse 返回 `2`。`deploymentReady` 始终为 `null`：数据库检查不能证明线上进程运行了当前代码，也不能替代浏览器课堂验收。

| 输出字段 | 含义 |
| --- | --- |
| `catalog.lessonCount / unitCount` | 注册表里的课次/单元定义数量，属于源代码目录 |
| `catalog.curriculumVersion / identitySha256` | 本次运行实际加载的版本与数据身份 |
| `database.pendingMigrations` | 未登记为已执行的 080、081 迁移 |
| `database.missingRequiredTables` | 当前查询需要但数据库没有的表 |
| `inventory.declaredCoursewareCount` | 数据库中声明为当前版本的未退役课件数，尚未证明可用 |
| `inventory.boundCandidateCount` | 有当前版本有效期内绑定行的候选数，尚未通过内容和发布校验 |
| `inventory.verifiedContentAndBindingCoursewareCount` | 内容哈希、注册表绑定、原始生成/独立验收记录均通过当前 host 校验的数量 |
| `inventory.formallyReadyCoursewareCount` | 上述候选中，通过现有精确发布供给查询的可复用课件版本数 |
| `inventory.distinctAssessmentSets` | 可用库存内按“课次 + assessment set”去重的组数；不表示孩子已完成或掌握 |
| `inventory.byGradeSubject` | 已验证可用库存按课程原年级、学科的数量 |
| `child.subjects[].nextLesson` | 真实学习路线推荐的下一课，以及该孩子是否有可续学/未使用的正式课件 |

库存复用 `published_supply()`：每个精确冻结目标槽位取当前优先的可复用课件，再对课程版本去重。它核对正式单课发布凭证、精确 course/package/runtime 关联、当前 Runtime 合同、完整 TTS/ASR 和必需媒体状态。增量发布和仍然有效的历史细课次批次可被识别；不要求先发布整个年级。仅有 `course.status = published` 或一个绑定行不够。

`--child-id` 复用真实 `ProgressiveLearningService.get_path()`，并对候选重新检查 host 验收和 `progressive_formal_authority()`。它保留本年级的前置关系、已使用的独立组、已有课堂续学和观察确认规则。它不创建或完成摸底，也不写入掌握记录。报告不输出孩子姓名、家庭 ID、问题答案或课程正文。`--grade` 只筛选库存；孩子的路线始终只按实际年级计算。

默认最多验证 200 个课程版本、24 个正式目标，连接后读取预算 45 秒，每条 SELECT 上限 5 秒。可以缩小范围，或显式增加 `--max-courses`、`--max-targets`、`--timeout-seconds`。数据库连接使用现有驱动超时设置，不包含在连接后的读取预算里。达到数量/时间上限时，已验证数量只是下限；`complete=false` 或 `status=partial/unknown` 不能当作全库结论。网络或数据库不可达时数量为 `null`，不会伪装成零库存。

## 2. 处理阻断

| code | 下一步 |
| --- | --- |
| `pending_migrations` | 备份并确认迁移权限后，通过既有迁移工具执行 080、081；重新检查 |
| `required_tables_missing / database_schema_drift` | 对比迁移记录与实际结构，处理失败/未完成的版本迁移；不要手动伪造 applied 记录 |
| `migration_source_missing` | 补齐同一发布版本的迁移文件 |
| `database_unavailable / database_read_access_denied` | 核对私有配置、网络、数据库状态与读取权限；不粘贴连接信息 |
| `inventory_check_limited / verification_timeout` | 按年级/学科缩小检查，必要时提高显式上限；保留未知状态 |
| `course_provenance_invalid` | 核对原始生成验收、内容哈希、冻结目标和注册表身份；不能重标旧课绕过 |
| `no_formally_ready_courseware / formal_evidence_missing_or_stale` | 核对生成、课件、课堂、音频/ASR、媒体和单课正式发布凭证；补齐实际缺口 |
| `child_next_courseware_unavailable` | 供给该孩子本年级下一课的未用独立组；不得用其他年级的课填补库存 |
| `child_not_found / child_grade_not_primary` | 使用当前数据库内有效的一至六年级孩子资料 |
| `read_only_operation_rejected / readiness_verification_failed` | 保持只读，检查依赖或配置兼容性；不要据此声称已经可用 |

080 建立细课次绑定、证据、进度，并扩展正式生产状态；081 建立 `learning_placement_attempts`、`learning_placement_questions`。缺失时命令会在访问相关业务表之前返回明确阻断。检查迁移记录和表存在不能证明每个 CHECK 约束都已按当前脚本执行；若实际结构发生漂移，需要迁移审计。

## 3. 迁移和受管构建

以下是获准上线窗口内的操作说明；只读检查命令不会替你执行这些步骤。先核对代码版本和数据库备份，停止会写入的应用/备课任务，再执行既有迁移器。MySQL DDL 并非可依赖事务整体回滚，失败时应按实际执行位置修复，不直接重写迁移记录。

本地或按既有后端方式部署的环境：

```sh
cd backend
python3 scripts/migrate.py
```

迁移器会执行所有尚未登记的迁移，不只执行 080/081；执行前须核对完整待迁移清单。迁移器使用同库 MySQL 命名锁防止并发，逐文件成功登记后提交；失败会给出具体文件与语句位置。DDL 仍可能已提交，不能依据 rollback 盲目重放。完成后从项目根目录重跑只读检查。

本地课堂使用受管脚本，保留其 PID/cwd/启动身份校验；不要按端口杀未知进程：

```sh
./openmaic-runtime/scripts/local-test-stack.sh status
./openmaic-runtime/scripts/local-test-stack.sh stop-curriculum-worker
./openmaic-runtime/scripts/native-runtime.sh build-openmaic-production
./openmaic-runtime/scripts/local-test-stack.sh build-student-web-production
MIRA_LOCAL_TEST_REPAIR_MODE=0 MIRA_LOCAL_TEST_CURRICULUM_WORKER_ENABLED=0 ./openmaic-runtime/scripts/local-test-stack.sh restart
MIRA_LOCAL_TEST_REPAIR_MODE=0 MIRA_LOCAL_TEST_CURRICULUM_WORKER_ENABLED=0 ./openmaic-runtime/scripts/local-test-stack.sh status
```

`restart` 会替换已确认身份的本地服务；要在允许中断的窗口执行。上述独立开关启动正常 API，保留任务调度与实时事件，同时暂停备课 worker。查询状态时也带上同一开关；未明确设置时，worker 默认行为仍为开启。需要完全无后台调度的隔离修复时才使用 `MIRA_LOCAL_TEST_REPAIR_MODE=1`，它优先使用 passive API。对已运行服务使用 start 不会自动切换其角色；角色变更要通过受管 restart。脚本拒绝身份不明的进程时，应查明所属进程，不绕过校验。

本机后端使用 `backend/.venv/bin/python`，依赖来自已安装的本地环境；目录受 Git 忽略，不依赖临时测试目录或 macOS 的 Xcode Python 入口。

服务器容器部署遵循 [部署说明](../../deploy/README.md)，不套用本地端口和启动方式。现有服务器更新入口为：

```sh
python3 deploy/server.py --env /etc/mira/compose.env check
python3 deploy/server.py --env /etc/mira/compose.env migrate
python3 deploy/server.py --env /etc/mira/compose.env start
python3 deploy/server.py --env /etc/mira/compose.env status
```

这些命令仍需遵循部署说明中的停写、备份、代码/镜像构建和恢复步骤。默认消费已发布课程的配置保持 `generation` profile 关闭，不使用开启 worker 的方式验证部署。

## 4. 实际可用验收和后续供给

本地六年级首课两组试制、运行时修复及当前可用状态见 [2026-09-17 交付记录](2026-09-17-progressive-classroom-delivery.md)；该记录不代表全部课次已备齐或无人值守日更已就绪。

数据库检查后，还要确认 Backend、Student Web、Gateway、OpenMAIC 的实际进程/构建身份与当前版本一致，再用一个真实孩子走“本年级学习路线 → 本年级下一课 → 课堂 → 首次独立作答 → 返回路线”。默认不得出现低年级必修或摸底清单。观察类课次仍需要授权观察确认；重复练习或看过答案不能伪装成新的正式掌握证据。

保持备课 worker 暂停，直到明确确认本次付费范围：实际课次、年级、独立组、调用阶段和预算。代码已接通不等于授权立即生成 1038 课。日常供给只请求孩子本年级下一处缺口；同课至少两个独立组，组用完仍未掌握时追加新批次，保留旧正式课件和已有 session。生成后仍需走全部课堂、音频/ASR、媒体与正式发布门禁，随后重跑库存及该孩子的只读检查。
