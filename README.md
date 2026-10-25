# 暖瞳（Mira Guardian）

家长端 Flutter App、学生学习网页和 Python 后端共用一个仓库。家长管理孩子、设备、任务、看护和奖励；学生通过独立网页配对、学习、复习及订正作业；OpenMAIC 提供课件生成和课堂运行能力。

## 从哪里看

| 入口 | 用途 |
| --- | --- |
| [PRODUCT.md](PRODUCT.md) | 产品定位、品牌和设计原则 |
| [mobile/README.md](mobile/README.md) | 家长 App 运行、真机连接和环境配置 |
| [student-web/README.md](student-web/README.md) | 学生网页登录、课堂和后端连接 |
| [backend/README.md](backend/README.md) | 后端配置、API 和数据库开发 |
| [openmaic-runtime/README.md](openmaic-runtime/README.md) | 课堂运行环境、补丁和网关 |
| [deploy/README.md](deploy/README.md) | 服务器部署、完整数据备份与恢复 |
| [app-prototype-v4/index.html](app-prototype-v4/index.html) | 主要业务流程和交互状态参考 |
| [design/mira_guardian_high_fidelity_ui.html](design/mira_guardian_high_fidelity_ui.html) | 视觉参考 |

## 目录用途

| 目录 | 内容 | 清理原则 |
| --- | --- | --- |
| `mobile/lib/` | 家长 App 的页面、状态、网络和路由 | 业务源码 |
| `student-web/src/`、`public/` | 学生网页源码、插画、字体和当前模型 | 业务源码与运行资源 |
| `backend/routes/`、`services/`、`repositories/` | API、业务逻辑、数据库访问 | 业务源码 |
| `backend/content/`、`prompts/` | 教材、AI 政策、版本化提示词 | 部分 Markdown 是程序输入，不能按扩展名删除 |
| `backend/migrations/` | PostgreSQL 表结构的有序变更（`mysql/` 是合并前的 MySQL 历史） | 保留已应用迁移，新环境依赖完整历史 |
| `backend/data/` | 作业附件、生成媒体、调用回执和设备密钥存储 | 不是数据库目录；其中包含有效运行数据 |
| `backend/tests/`、`mobile/test/`、学生端 `*.test.*` 与 `tests/` | 回归测试、场景夹具和视觉基线 | 保留有效测试；截图失败产物可清 |
| `openmaic-runtime/patches/` | 对上游课堂源码的持久修改 | 运行环境重建依赖这些补丁 |
| `openmaic-runtime/.runtime/OpenMAIC/` | 当前上游源码、依赖、构建和正式课堂数据 | 正在运行的环境，不能整体当缓存清理 |
| `docs/`、`brand/`、`design/` | 需求来源、品牌素材及参考设计 | 复用现有入口，避免重复报告 |
| `output/` | 历史验证产物，也有课件发布和恢复所需文件 | 逐项核对；不能整体删除 |
| `.local_backups/` | 历史备份及部分开发样本的私有归属记录 | 先核对用途，保留恢复或身份校验必需记录 |
| `tools/` | 可复用开发工具，包括临时工作区托管 | 保留通用工具，不堆放一次性脚本 |
| `build/`、`.gradle/`、`__pycache__/`、`tmp/`、`temp/` | 构建、编译缓存或临时产物 | 确认无任务使用后可重新生成 |
| `node_modules/`、`.venv/`、`ios/Pods/` | 已安装依赖 | 可重装；清理后相应开发或运行任务会不可用 |
| `.git/` | 版本历史和未提交工作状态 | 保留 |

文件名含 `test` 不代表无用，文件位于 `output` 也不代表可以删除。App 中部分图片路径由后端字典下发，不能只按前端静态引用判断是否使用。

## 本地运行

已有完整本地环境时，在仓库根目录检查或启动受管服务：

```sh
openmaic-runtime/scripts/local-test-stack.sh status
openmaic-runtime/scripts/local-test-stack.sh start
```

服务包括后端 `8000`、学生网页 `3000`、课堂运行时 `3100`、课堂网关 `3101`。状态和日志默认在 `/tmp/mira-local-test-stack/`。脚本按进程身份管理服务，不会按端口直接结束未知进程。课程生成另有开关和预算，启动服务不代表授权新的付费生成。

家长 App：

```sh
cd mobile
flutter pub get
flutter run
```

独立开发学生网页需 Node.js 24：

```sh
cd student-web
npm ci
npm run dev
```

独立开发后端：

```sh
cd backend
python3 -m pip install -r requirements.txt
python3 app.py
```

首次安装、环境变量和数据库准备分别查看各工程 README。已有数据库不应通过初始化、迁移或种子脚本来排查普通启动问题。

## 数据库用途

全部数据在一个 PostgreSQL 数据库 `mira` 里：业务表在 `app` schema，课堂表在 `public` schema。连接以 `backend/.env` 的 `APP_DATABASE_URL`（业务）和 `MIRA_OPENMAIC_AGENT_DATABASE_URL`（课堂）为准，两者指向同一个库。数据不存放在 `backend/data/`。

本机 PostgreSQL 自 2026-10-25 起运行在 Docker Desktop：`docker compose -f deploy/compose.local-db.yml --env-file deploy/env/local-db.env up -d`（127.0.0.1:5433，库 `mira`）；`mira_test` 供测试清空重建。程序和数据库浏览工具共用登录账号 `mira`，密码在 git 忽略的 `deploy/env/local-db.env`。数据保存在 Docker 卷 `mira-pgdata`：不要执行 `docker compose down -v`、`docker volume prune`，也不要在 Docker Desktop 中清除数据。本地服务启动前 Docker Desktop 必须已运行。原来的 MySQL 业务库和 Homebrew PostgreSQL 里的旧课堂库已于 2026-10-26 删除，数据都在 Docker 库 `mira` 里；Docker 之外另有一份 `pg_dump` 备份在 `.local_backups/mira-postgres-*/`（git 忽略，用 `pg_restore` 恢复）。

| 表组 | 负责什么 |
| --- | --- |
| 账号、家庭、学生认证 | 家长登录、家庭权限、学生配对、可信设备和会话 |
| 设备、看护、语音 | 设备配置、命令、观察事件、提醒与对话 |
| 任务、积分、奖励 | 任务执行、积分流水、奖励与兑换 |
| 教材、学习、复习 | 家长选书、课程安排、作答、掌握度和复习 |
| 作业 | 上传、识别、判题、订正、辅导和调用预算 |
| 课程生成、发布、媒体 | 备课状态、预算凭据、音频、质量审核和课堂绑定 |
| `schema_migrations` | 已应用迁移版本，支持安全升级 |
| `public` schema `document_*`、`stage_meta` | 课堂场景和课件文档 |
| `public` schema `agent_*` | Agent 会话、工具结果、事件重放、生成和恢复证据 |

空表可能是尚未使用的功能，也可能在代码中承担预留接口。删表必须同时核对读写代码、外键、迁移历史和有效数据；数据库整理不能只看表名或当前行数。

## 验证与产物约定

家长 App 使用 `flutter analyze`、`flutter test`；学生网页使用 `npm run lint`、`npm run typecheck`、`npm test` 和发布构建。后端测试按 [backend/README.md](backend/README.md) 运行，涉及数据库的测试会重置专用测试库，不应对开发库执行。

日常修改默认在聊天中说明结果，必要的长期说明更新现有文档。常规检查直接输出到终端，不为每次成功执行保存一份日志或 JSON 报告。

确实需要临时产物时，使用 `python3 tools/task_tmp.py --name check -- <命令及参数>`，将脚本、截图和中间文件集中到命令环境中的 `MIRA_TASK_TMPDIR`。工具同时为子命令设置 `TMPDIR`；独立截图工具仍需明确指定输出路径。成功后自动清理，失败保留非空诊断目录并显示位置，`--keep` 可显式保留。该入口只适用于前台检查，不用于常驻服务、数据库、原始私有附件、付费回执或恢复备份。课件与恢复资料按现有运行依赖管理。
