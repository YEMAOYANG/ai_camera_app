# 服务器部署与现有课程迁移

这套配置用于把家长网页、学生网页、Python 后端和 OpenMAIC 课堂放到同一台 Linux 服务器。浏览器连接公网 HTTPS 域名，数据库和服务之间走私有网络。后端打包得到 Docker 镜像；启动容器后，它会一直运行，不依赖开发电脑开机。

当前交付是可检查的部署配置和操作工具。没有在真实服务器上完成 Docker 构建、数据恢复和浏览器验收，不能把下面的命令等同于已经上线。家长 Flutter Web 的浏览器兼容性也需要单独验收。

## 1. 准备服务器和入口

准备安装了 Docker Engine、Docker Compose v2 插件和 Python 3.10+ 的 Linux 服务器，以及一个可以管理 DNS 的域名。服务器必须能访问镜像仓库、依赖仓库和项目实际使用的模型接口。首次构建会下载较多依赖，应预留磁盘和构建内存。

示例域名如下，均替换为自己的域名：

| 入口 | 示例 | 用途 |
| --- | --- | --- |
| 家长网页 | `https://parent-test.example.com` | 家长端浏览器演示 |
| 后端 API | `https://api-test.example.com` | 家长网页调用接口 |
| 实时消息 | `https://realtime-test.example.com` | 客户端使用对应 `wss://` 地址 |
| 学生网页 | `https://learn-test.example.com` | 学生配对、选课和报告 |
| 课堂 | `https://classroom-test.example.com` | 受控课堂网关 |

五个域名都解析到服务器公网 IP。学生网页和课堂使用同一主域名下的子域名，并保持配置中的 origin 完全一致，以满足 Cookie、iframe 和麦克风授权条件。

服务器只公开 Caddy 的 80/443 端口；SSH 按运维需要限制访问。不要把 PostgreSQL、8000、8001、3000 或 3101 直接开放到公网。TLS 签发还要求域名解析正确且证书验证流量能到达 Caddy。受限 preview 使用直接 DNS，不在前面套 CDN 或未配置受信客户端 IP 的代理，以免白名单识别成代理地址。

### 局域网麦克风验收

手机或平板通过 `http://192.168.x.x` 访问不属于浏览器的 Secure Context，无法作为正式麦克风链路；`localhost` 例外只适用于运行服务的同一台设备。Student 顶层页面和 Classroom iframe 都必须使用 HTTPS，两个证书都必须在终端上受信。Student 的 Permissions-Policy 要精确包含 Classroom origin，Gateway 的 CSP `frame-ancestors` 要精确包含 Student origin。

本地受管学习栈可使用 `deploy/Caddyfile.lan` 的 `tls internal`，配置本地 DNS 后，校验三个入口：

```sh
export MIRA_STUDENT_ORIGIN=https://learn.mira.test
export MIRA_CLASSROOM_ORIGIN=https://classroom.mira.test
export MIRA_API_ORIGIN=https://api.mira.test
export MIRA_STUDENT_WEB_ORIGIN=https://learn.mira.test
export MIRA_RUNTIME_PUBLIC_ORIGIN=https://classroom.mira.test
python3 deploy/validate_production_origins.py
caddy validate --config deploy/Caddyfile.lan
```

本地 Student 的 `MIRA_STUDENT_WEB_PUBLIC_URL`、后端的 `OPENMAIC_FULL_RUNTIME_PUBLIC_URL` 与这些公开入口保持一致；修改域名后重新构建相关前端。必须在每台验收设备安装 Caddy 根证书，并在系统证书设置中启用完整信任，不能只跳过浏览器证书警告。Caddy 仅代理 Student 3000、Gateway 3101 和 API 8000；本地 OpenMAIC 管理入口 `127.0.0.1:3100` 仅供内部访问。

这段配置用于本地三服务入口验收；服务器的五域名部署继续使用下文的 `deploy/server.py` 和 Compose 配置。

## 2. 放置代码，生成服务器配置

将经过确认的项目版本放到服务器，例如 `/srv/mira/app`。不要上传电脑里的 `.env`、`node_modules` 或整个本地工作目录作为服务器配置；密钥和待迁移数据分别处理。

下文服务器命令均从项目根目录运行，使用有权管理 Docker、`/etc/mira` 和 `/srv/mira` 的部署用户；若云服务器控制台使用管理员账号，则在该账号下操作。先准备配置：

```sh
cd /srv/mira/app
python3 deploy/server.py --help
python3 deploy/server.py init --config-dir /etc/mira
```

`init` 用于生成配置起点，不会替你购买资源或完成上线。按照生成文件中的注释填写域名、密码、接口和模式，然后运行：

```sh
python3 deploy/server.py --env /etc/mira/compose.env check
```

主要文件：

| 文件 | 内容 |
| --- | --- |
| `/etc/mira/compose.env` | 域名、部署模式、镜像、数据目录及配置文件位置 |
| `/etc/mira/backend.env` | 后端登录、数据库、课堂入口和业务开关 |
| `/etc/mira/openmaic.env` | OpenMAIC 的 Provider、模型、语音等私有配置 |

这些文件仅供服务器读取，不提交 Git，不放进家长或学生网页构建产物。工具要求配置文件权限为600，且数据、前端产物和密钥路径互不重叠；编辑配置时保留原权限。不要把完整配置文件内容或展开后的 Compose 配置贴到聊天、工单或公开日志里。

### 选择正式模式或受限演示模式

正式模式在 `compose.env` 中设置 `MIRA_DEPLOY_MODE=production`，使用 `compose.production.yml`，保留生产登录约束。当前真实短信 Provider 尚未实现完整接入；正式启动应明确阻断此情况，不能只把 Provider 名称改成阿里云或腾讯云就视为接通。

自己和老板演示时，设置 `MIRA_DEPLOY_MODE=preview`，由工具叠加 `compose.preview.yml`。preview 使用开发短信适配器、关闭调试模式，并要求填写 `MIRA_ACCESS_CIDRS`。所有浏览器入口都受 Caddy IP 白名单限制；不能保留生产模板中的 `0.0.0.0/0` 或 `::/0`。

同时将 `MIRA_BASE_DOMAIN` 改为实际主域名，并设置五个 `MIRA_*_ORIGIN`。例如白名单可采用 `MIRA_ACCESS_CIDRS='你的公网IPv4/32 老板的公网IPv4/32'` 的格式；这行只是格式说明，地址必须替换成真实值。

填写的是你和老板访问互联网时的公网出口 IP，不是电脑上的 `192.168.x.x`。IPv4 单个地址使用 `/32`，IPv6 单个地址使用 `/128`。更换网络后如果看到拒绝访问，先更新白名单；不能通过取消限制来解决。preview 的开发验证码仅用于受限演示，不作为正式用户登录方案。

### 服务地址如何填写

后端、网关和可选备课 worker 与 OpenMAIC 共享私有网络命名空间，保留现有正式语音接口的 loopback 校验：

- OpenMAIC：`127.0.0.1:3000`。
- 后端：`0.0.0.0:8000`，实时消息为8001。
- 网关：`0.0.0.0:3101`，内部访问 `127.0.0.1:3000`。
- Student Web 在独立容器，通过私有地址 `http://backend:8000` 访问后端。

内部配置使用容器之间的地址，公开配置使用 HTTPS 域名。不要将公网课堂域名替换为 `http://openmaic:3000`，也不要把所有内部地址机械地改成服务器公网 IP。OpenMAIC 的 `MIRA_BACKEND_INTERNAL_URL` 和后端的 `LEARNING_BUDGET_INTERNAL_URL` 在此拓扑下均为 `http://127.0.0.1:8000`。

## 3. 构建服务和家长网页

首次上传或克隆主项目时，`openmaic-runtime/.runtime/OpenMAIC` 是被 Git 忽略的目录，通常不会一起出现。服务器需要先准备固定版本的 OpenMAIC 源码和项目补丁：

```sh
cd /srv/mira/app
command -v git
command -v shasum
OPENMAIC_SOURCE_DIR=/srv/mira/app/openmaic-runtime/.runtime/OpenMAIC \
  bash openmaic-runtime/scripts/bootstrap-upstream.sh
```

该脚本从 GitHub 获取 `THU-MAIC/OpenMAIC`，切换到项目固定提交，核对 MIT 许可与 `upstream.lock.json` 中的补丁清单，并依次应用 `openmaic-runtime/patches/`。服务器须具备 Bash、Git、`shasum`，首次获取还需要访问 GitHub。不要手动复制一个未打补丁的上游最新版本。遇到“已有补丁之外的改动”报错时，先确认工作目录与版本，不能直接重置一个含未保存工作或运行数据的目录。

Docker 构建会安装 Node/Python 依赖，不需要在服务器先运行 `pnpm install` 或启动本地开发栈。Compose 的构建目录固定为 `openmaic-runtime/.runtime/OpenMAIC`；本地导出若使用其他源码目录，通过数据工具的 `--openmaic-source` 指定。更多源码约定见 `openmaic-runtime/README.md`。

```sh
python3 deploy/server.py --env /etc/mira/compose.env build
```

该步骤构建镜像，不生成新课程，不恢复电脑里的数据库，也不代表服务已经可用。Provider 密钥应通过运行期配置注入，不作为前端构建参数。

家长端浏览器产物由 Flutter Web 构建，再将完整 `mobile/build/web/` 内容上传到 `/srv/mira/parent-web/`，该目录中应直接存在 `index.html`。例如受限 preview 模式在开发电脑执行：

```sh
cd mobile
flutter build web --release \
  --dart-define=APP_FLAVOR=development \
  --dart-define=API_BASE_URL=https://api-test.example.com \
  --dart-define=TASK_WS_BASE_URL=wss://realtime-test.example.com \
  --dart-define=STUDENT_WEB_BASE_URL=https://learn-test.example.com
```

这里的 development 是应用业务环境，用于演示登录；Flutter 编译仍为 release。正式部署应采用 production flavor，并先完成真实短信接入。实时连接路径应与当前 Caddy 及客户端契约核对，不能只凭构建通过就认为 WebSocket 可用。

如果 Flutter Web 编译或实际页面遇到移动端专用 API，需要先完成浏览器适配。至少验收登录、日期选择、配对码、任务更新和报告。网页部署不会让浏览器自动具备手机的蓝牙、局域网发现和相机能力。

## 4. 选择新环境或迁移现有课程

### A. 使用全新测试数据

在配置检查和镜像构建完成后，准备空数据库并应用后端表结构：

```sh
python3 deploy/server.py --env /etc/mira/compose.env prepare
```

`prepare` 准备持久化目录、课堂预算政策及空数据库，然后通过 `operations` profile 的 `database-migrate` 服务执行后端表结构迁移。整套系统只用一个 PostgreSQL 数据库 `mira`：后端表在 `app` 模式，OpenMAIC 课堂表在 `public` 模式，程序都用登录账号 `mira` 连接；数据库容器首次启动时由 `deploy/postgres/init/` 建好账号、数据库和 `app` 模式。该迁移服务用于维护操作，不启动应用或备课 worker。新库没有现有课程，此步骤也不会调用模型备课或把本地已发布课程自动复制过来。若需要展示已有课程，采用下面的迁移流程。

### B. 迁移电脑上已经生成的课程

课程依赖数据库 `mira` 里的后端业务记录和课堂记录、后端媒体、OpenMAIC 文件及预算策略。只复制一个课程 JSON、音频目录或数据库都不完整。

先在开发电脑的项目根目录做只读盘点：

```sh
python3 deploy/data_bundle.py inventory
```

如果系统自带 Python 无法运行，改用已安装的 Python 3 解释器路径；不必因此改动项目环境。若实际运行进程覆盖了预算策略路径，以下导出命令必须用 `--budget-policy` 指向那份实际文件。

导出前停止所有可能写入的应用进程：后端、Student Web、OpenMAIC、网关、备课和媒体 worker，以及仍在运行的恢复或课程验收操作。使用项目的受管启动脚本停止已经确认身份的本地服务。**PostgreSQL 保持运行**，供导出工具读取。`--services-stopped` 是你确认写入已停的声明，工具不会自动停进程。

```sh
python3 deploy/data_bundle.py export-local \
  --services-stopped \
  --output /tmp/mira-migration-20260916
python3 deploy/data_bundle.py verify /tmp/mira-migration-20260916
```

输出目录必须尚不存在，且不能位于待备份的数据目录内部。数据库导出需要可用的 `pg_dump` 和 `pg_restore`；非默认位置可用导出命令的对应参数指定。工具会记录源数据库版本，目标镜像的数据库主版本应匹配，不能把更高版本的源库直接恢复到较低版本。

数据包包括：

- `postgres.dump`（整个数据库 `mira`，含 `app` 和 `public` 两个模式）。
- `backend-data.tar`、`openmaic-data.tar`。
- `learning-budget-policy.json`。
- `manifest.json`，记录文件校验和及数据库版本。

数据包含账号、孩子、课程、媒体和审计信息，应通过受控通道传到服务器并限制文件访问。它不会导出 Provider 密钥或完整 `.env`。`APP_STUDENT_AUTH_PEPPER`、已有设备密钥及其他必要的原生密钥要按清单单独安全迁移；服务器 Compose 用 `MIRA_STUDENT_AUTH_PEPPER` 向后端注入该 pepper。若设备密钥来自 data 中的 `.device-secret.key`，该文件随数据归档迁移；若来自环境变量 `APP_DEVICE_SECRET_KEY`，需要单独保留原值。更换 pepper 或解密密钥会影响已有身份和设备数据。

`init` 生成的是新密钥，不能自动匹配旧数据；`restore` 会核对必要密钥的指纹并拒绝不匹配。源环境若没有显式设置 `APP_STUDENT_AUTH_PEPPER`、使用本地默认 pepper，不得把默认值带进 production；应使用新私密值，并由家长重新设置学习 PIN、重新配对。不要将默认 pepper 写进生产配置以绕过检查。

在服务器检查数据包，并恢复到**空目标**：

```sh
python3 deploy/data_bundle.py verify /srv/mira/backups/mira-migration-20260916
python3 deploy/server.py --env /etc/mira/compose.env restore \
  /srv/mira/backups/mira-migration-20260916
```

恢复期间不得运行应用和 worker。`restore` 先恢复原数据库及文件（以 `mira` 账号身份导入，对象归属与源库一致），再通过同一个 `database-migrate` 服务补齐当前项目版本所需的结构。不要先在目标环境注册账号、创建课程或使用 `prepare` 写入业务表再覆盖恢复；恢复工具的空目标检查失败时，应查明目标状态，不能删掉校验或强行覆盖。

`data_bundle.py restore-files` 只解包文件，不恢复数据库；完整服务器恢复使用 `server.py restore`。恢复后，预算策略路径必须指向 `/app/data/deployment-policies/learning-budget-policy.json`，并保留原有付费账本、授权范围、ID、课程哈希、发布状态及 ambiguous 记录。不能通过改状态或重新生成课程来掩盖迁移问题。

旧课程可能含绝对媒体地址。先检查迁移数据中的 localhost、局域网地址和旧域名引用；不要对 SQL 或课堂 JSON 全局替换字符串，这可能破坏内容哈希及验收回执。发现需要调整的历史引用，应单独处理并重新核对证据。迁移工具的边界和完整参数见 [data-migration.md](data-migration.md)。

### C. 服务器不用 Docker 运行数据库

数据库也可以直接安装在服务器上（PostgreSQL 16，与本地同一大版本），布局保持一致：一个登录账号 `mira`、一个数据库 `mira`、其中的 `app` 模式归 `mira` 所有。用数据库管理员身份执行：

```sh
psql -v ON_ERROR_STOP=1 -d postgres -c "CREATE ROLE mira LOGIN PASSWORD '<强密码>'"
psql -v ON_ERROR_STOP=1 -d postgres -c "CREATE DATABASE mira ENCODING 'UTF8' LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8' TEMPLATE template0"
psql -v ON_ERROR_STOP=1 -d mira -v db=mira -f deploy/postgres/init/database-setup.psql
```

后端配置 `APP_DATABASE_URL=postgresql://mira:<密码>@<数据库地址>:5432/mira`，课堂运行时使用同一个地址。恢复迁移包时按 [data-migration.md](data-migration.md) 第 4 节：先删除空的 `app` 模式，再用 `pg_restore --no-owner --no-privileges --role=mira` 导入，最后运行 `backend/scripts/migrate.py`。数据库只监听内网地址，不开放到公网。

## 5. 启动与浏览器验收

```sh
python3 deploy/server.py --env /etc/mira/compose.env check
python3 deploy/server.py --env /etc/mira/compose.env start
python3 deploy/server.py --env /etc/mira/compose.env status
python3 deploy/server.py --env /etc/mira/compose.env logs
```

默认只消费已经发布的课程：不启动 `generation` profile 中的备课 worker，关闭后端生成及候选课程自动处理，同时禁用 OpenMAIC 作者/Agent 自动执行。后者避免恢复 PostgreSQL 后，旧的未完成 Agent 任务在服务启动时自动继续调用模型；原任务及账本仍原样保留。已经发布的学生课堂路由不依赖作者 Agent 自动运行。

部署工具会拒绝打开受控的自动生成开关。启动网页和后端并不授予新增模型费用，也不会自动补齐课程库存。需要新课程时，应另行确认预算、生成配置和恢复任务边界，再扩展部署流程。

原来的 localhost/LAN Cookie 不会变成新域名的 Cookie。你和老板在新入口重新登录、分别使用测试账号，并通过配对码重新配对学生网页。至少完成一次：

1. 家长网页登录、查看孩子与任务。
2. 同一电脑打开学生标签页，用配对码绑定同一孩子。
3. 打开已发布课程，检查页面、全部必要音频、麦克风权限与课堂交互。
4. 完成课程后查看学生报告和家长端学习结果。
5. 验证实时任务更新；再重启服务，确认数据仍存在。
6. 从不在白名单的网络检查 preview 入口被拒绝访问。

健康接口通过只证明部分服务可达，不能代替上述浏览器流程。已经生成的静态内容可以随数据迁移；AI 对话、语音识别或新的语音生成仍可能产生 Provider 费用，按现有预算授权范围测试。

## 6. 数据目录、备份和更新

默认持久化布局：

```text
/srv/mira/data/
  postgres/
  backend-data/
  openmaic-data/
  caddy-data/
  caddy-config/
/srv/mira/parent-web/
/etc/mira/
```

更换容器镜像不应删除这些目录。PostgreSQL 的运行目录不能在数据库运行时直接复制充当完整备份。

备份前先停止应用与所有其他写入者，再按工具要求执行逻辑导出；输出目录必须是新目录，其父目录须存在。`server.py stop` 停止网页、网关、后端、OpenMAIC 和备课 worker，保留 PostgreSQL 运行，以供导出；另行运行的操作脚本也需要先停止。`backup` 只接受数据库仍运行且其他服务已停止的状态，不会代为停服务：

```sh
python3 deploy/server.py --env /etc/mira/compose.env stop
mkdir -p /srv/mira/backups
python3 deploy/server.py --env /etc/mira/compose.env backup \
  /srv/mira/backups/mira-before-update-20260916
```

备份完成后校验数据包，再恢复启动。密钥配置、域名设置和 Caddy 持久化目录需独立备份；课程数据包不是整台服务器镜像。

更新采用“记录版本 → 停写备份 → 更新代码与镜像 → 执行必要数据库迁移 → 启动 → 浏览器验收”的顺序。更新代码、补丁和镜像后，在应用保持停止时运行 `python3 deploy/server.py --env /etc/mira/compose.env migrate`，成功后再 `start`。OpenMAIC、后端、网关及共享其网络命名空间的 worker 应成组重建，不能只替换 namespace 所属容器后保留旧依附容器。涉及数据库结构变化时，回滚不能只切旧镜像，应使用已核验的备份和对应代码版本。

`start` 会检查部署标记、数据库目录和预算政策，目录丢失时拒绝自动创建空库。首次迁移默认也关闭 OpenMAIC 的资源回收，避免验收之前清理历史素材；验收完成后再评估保留策略。当前 PostgreSQL 挂载布局支持 14—17，若来源为 18 或更新版本，需要先调整并验证官方镜像的数据目录布局，不能降级恢复。

## 尚需现场验证的事项

- 没有真实 Docker/服务器运行证据前，构建成功、数据库恢复、自动HTTPS和外网访问仍待验证。
- 正式模式需要完成真实短信 Provider 接入；preview 必须持续保留访问白名单。
- 家长 Flutter Web 的移动端专用功能、实时消息和浏览器兼容性尚需验收。
- 自动备课需单独确认模型配置、预算授权、队列状态和生成发布门槛，再决定是否开启。不能直接启用 worker 来验证部署。
- 正式课件验收使用 Chromium sandbox；安装浏览器不代表容器 sandbox 已可用，应先完成不调用 Provider 的浏览器环境验证。
- 公网连接家中摄像头是独立链路，部署家长网页、后端和学生课堂不会自动完成硬件远程连接。
