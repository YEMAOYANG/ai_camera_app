# 已有账号、课程和音频的迁移

`data_bundle.py` 只做离线迁移包、校验及文件恢复；不会停止服务、调用模型、重新生成课程、重新发布课程或写入数据库。数据库导入使用本目录的服务器部署入口，并且只允许空的新环境。

## 必须一起迁移的内容

| 迁移包文件 | 内容 |
| --- | --- |
| `mysql.sql` | 家长、孩子、学生身份、任务、积分、课程目录/发布状态、学习进度、预算授权和账本等 MySQL 数据与结构 |
| `postgres.dump` | OpenMAIC Agent/课堂持久化 PostgreSQL，`pg_dump` custom 格式 |
| `backend-data.tar` | 整个 `backend/data`：学习媒体、设备密钥文件和密文、Provider 回复与恢复审计等 |
| `openmaic-data.tar` | 整个 OpenMAIC `data`：课堂、生成任务、TTS/ASR job 与音频、验收/修复证据、预算绑定等 |
| `learning-budget-policy.json` | 当前预算政策的原始字节，包含政策版本、计价、额度与授权窗口；不扩展额度或续期 |
| `manifest.json` | 文件 SHA-256 和大小、源数据库版本、配置密钥名及指纹、恢复路径约定 |

`backend/data` 不是业务数据库。只复制它或只执行数据库迁移建表，都无法带走现有完整课程。源代码也要部署同一版本，包括 OpenMAIC 的补丁集合。迁移保持课程 ID、发布状态、未完成/`ambiguous` 任务状态原样；它不把尚未验收的课程变成可发布课程。

## 1. 只读盘点

在项目根目录执行（Python 3.10+，仅标准库）：

```bash
python3 deploy/data_bundle.py inventory
```

只读取两个 dotenv 文件、目录元数据及政策文件，打印文件数量、大小、路径、政策 SHA 和必要密钥的指纹，不读数据库内容、不显示密钥值。可以用 `--backend-env`、`--runtime-env` 和 `--openmaic-source` 指定实际运行配置/源码。

工具按本项目的规范目录布局导出。如果 `.env` 将学习媒体、设备密钥、正式音频或 Provider readiness 指向其他目录，会明确停止，避免生成缺数据的备份；需要先针对自定义布局扩展迁移方案。运行时通过进程环境或一次性命令传入的覆盖值，必须核对并反映在指定 dotenv 中。

## 2. 停止写入，再导出

先检查任务状态，等现有课程生成和付费调用结束，停止后端、学生端、OpenMAIC、网关、全部 worker 及单独运行的生成/修复脚本。不要在不明确的 Provider 调用中途强杀并重试。项目管理的本地栈可使用 `openmaic-runtime/scripts/local-test-stack.sh stop`，但仍要确认没有独立运行的 operator/worker。MySQL 和 PostgreSQL 保持运行。

```bash
python3 deploy/data_bundle.py export-local \
  --backend-env backend/.env \
  --runtime-env openmaic-runtime/.env \
  --output /absolute/private-backups/mira-first-export \
  --services-stopped
```

输出父目录须已存在，输出目录须不存在。`--services-stopped` 是操作者确认，不会替你停进程或证明跨库一致。数据库和两份文件目录必须来自同一段没有写入的时间，否则会出现课件、发布记录和音频对不上的情况。

导出需要 `mysqldump`、`pg_dump` 和 `pg_restore`，也可以分别用 `--mysqldump`、`--pg-dump`、`--pg-restore` 指定可执行文件。工具使用临时 0600 客户端配置/密码文件传递数据库凭据，数据库 URL 和密码不会放进进程参数、日志或 manifest；不会通过 shell `source` 加载配置。数据库客户端必须兼容源服务器版本。

预算政策按 `--budget-policy` → 后端 dotenv 的 `LEARNING_BUDGET_POLICY_PATH` → `backend/content/learning_budget_policy.json` 读取，相对配置路径从 `backend/` 解析。代码默认政策是 disabled，不能把它误认为当前课堂政策。如果实际运行时在进程内覆盖过政策，必须显式加 `--budget-policy /absolute/path/to/actual-policy.json`。本项目没有 `LEARNING_CLASSROOM_BUDGET_POLICY_PATH` 配置。

失败导出没有有效完成 manifest，不得导入。不要覆盖失败目录继续导出；保留排查后使用新目录。数据包包括家庭个人数据、课程、设备密钥和审计，只放在私密存储并通过 SSH/SCP 等安全渠道传输，不能提交 Git 或放到公开网页目录。

## 3. 独立迁移服务端配置

env 文件和模型 API Key 不进入数据包。服务器使用新的数据库账号、域名和内部地址；模型 Provider 的 Key/Base URL 必须匹配。根据 manifest 的 `secretsToMigrateSeparately` 校验并安全迁移下列身份密钥：

- `APP_STUDENT_AUTH_PEPPER`：改变后，旧 PIN 和学生凭证不能直接沿用。若本地没有设置而使用开发默认 pepper，生产配置必须使用新的私密 pepper，然后通过家长端重新配对/重设 PIN，不放宽生产检查。
- `APP_DEVICE_SECRET_KEY` 或已归档的 `.device-secret.key`：保留同一设备加密密钥，才能解密已有设备密文。
- 内部 API token 和 OpenMAIC persistence token：两边服务配置必须一致；若轮换，旧的临时票据应重新签发，不改课程内容和持久化 ID。

指纹只能帮助检查配置是否相同，不是签名，也不能代替可信来源和安全传输。带 `configured: false` 的项必须结合本地运行时配置确认，不能假定无密钥。

## 4. 校验并恢复到空环境

```bash
python3 deploy/data_bundle.py verify /absolute/private-backups/mira-first-export
```

服务器数据库镜像必须与 manifest 记录的源版本兼容。尤其不允许把本地 MySQL 9.x 的 dump 直接导入默认 MySQL 8.x；选择相同大版本，或另行执行经过验证的迁移升级方案。不要复制 MySQL/PostgreSQL 的底层数据库目录跨系统启动。

文件恢复子命令如下。它只恢复文件，不导入数据库：

```bash
python3 deploy/data_bundle.py restore-files \
  /absolute/private-backups/mira-first-export \
  --target /absolute/new-empty-data-root
```

目标必须为空，将得到 `backend-data/` 和 `openmaic-data/`。两者分别挂载到对应服务的 `/app/data`。政策额外写入 `backend-data/deployment-policies/learning-budget-policy.json`，后端配置 `LEARNING_BUDGET_POLICY_PATH=/app/data/deployment-policies/learning-budget-policy.json`。归档里的已有文件不改内容；若已有同名部署政策且内容不同，恢复停止。

恢复先检查全部 SHA-256 并拒绝绝对路径、`..`、软链接、硬链接及特殊文件。目录默认 0700，文件 0600；服务器部署入口应根据镜像运行 UID/GID 设置属主，再启动服务。不要用 `chmod 777`。中途失败可能留下部分文件，不能跳过空目标检查覆盖恢复。

数据库导入必须在所有应用和 worker 停止、目标库为空、版本已检查时进行。`mysql.sql` 是单库结构与数据，没有创建服务器用户的 SQL；`postgres.dump` 不携带源 owner/ACL，使用目标账号导入。导入后再执行项目版本需要的结构迁移，保留原课程 ID 与发布状态。

## 5. 核验后启用应用

对照导出前的课程数、发布状态、课堂 ID、媒体文件数与哈希，确认音频可读、家长登录及学生重新配对正常，再完成一次已有已发布课堂的播放/报告检查。自动备课和付费生成任务保持关闭，直到另外确认需要和预算。旧的失败或不明确任务先看原审计，不因为迁移而重新生成。

本工具的自动测试只使用临时夹具和模拟数据库客户端，不代表已经做过真实导出/服务器恢复。服务器首次实际恢复及浏览器验收仍是部署交付的必要步骤。
