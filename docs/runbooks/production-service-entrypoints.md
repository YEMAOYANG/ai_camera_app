# Mira 学习闭环生产服务入口

本文只覆盖学生学习闭环的四个服务入口：Student Web、OpenMAIC、Runtime Gateway 和 Backend。数据库迁移、课程发布及业务数据不由这些启动命令执行。

## 1. 网络边界

生产拓扑固定为：

```text
https://learn.example.com      -> Caddy -> 127.0.0.1:3000 Student Web
https://classroom.example.com  -> Caddy -> 127.0.0.1:3101 Runtime Gateway
https://api.example.com        -> Caddy -> 127.0.0.1:8000 Backend
                                           127.0.0.1:3100 OpenMAIC（仅内部）
```

不得给 `127.0.0.1:3100` 配置公网或局域网入口。OpenMAIC 管理端只接受 Backend 和 Runtime Gateway 的内部访问。Backend、Gateway 与 OpenMAIC 通过 compose 的私有 `runtime` 网络通信，Gateway 固定使用 `http://backend:8000`；映射给宿主机 Caddy 的端口仍只绑定 loopback，避免绕过 TLS edge。

三个公开地址应使用无路径、无查询参数、无账号信息的 HTTPS origin。建议 Student 与 Classroom 使用同一注册域下的不同子域，例如 `learn.example.com` 与 `classroom.example.com`。

## 2. Backend

在 `backend/.env` 中准备真实生产配置。至少应满足现有 `AppConfig` 的生产校验：真实 MySQL、明确且不含 `*` 的 CORS、非 development SMS/摄像头 adapter、私有 `APP_STUDENT_AUTH_PEPPER`、`INTERNAL_API_TOKEN`，以及 HTTPS 的 `OPENMAIC_FULL_RUNTIME_PUBLIC_URL`。不要把密钥写入启动脚本、Caddyfile 或本说明。

Backend 默认随第 4 节的 compose 一起构建和启动。镜像不复制 `.env`、本地数据或测试目录；必须显式设置 `MIRA_BACKEND_ENV_FILE`，让它指向服务器上的生产 env 文件，课程媒体放在命名卷中。不要把当前开发 `.env` 直接当成生产配置。

如需在不使用 compose 的单机环境单独启动 Backend，可安装依赖并启动：

```bash
cd backend
python3 -m pip install -r requirements.txt
./scripts/start-prod.sh
```

`backend/scripts/start-prod.sh` 强制 `APP_ENV=production`，默认只监听 `127.0.0.1:8000`，并固定 Gunicorn 为一个 worker、默认 8 个线程。容器入口仅允许通过 `MIRA_BACKEND_BIND=0.0.0.0:8000` 在容器网络内监听，宿主机映射仍为 `127.0.0.1:8000`。当前 `create_app()` 会启动任务调度、课程准备和媒体等后台线程，因此不得把 worker 数改成多个，否则每个进程都会重复启动这些后台任务。线程数可通过 `MIRA_BACKEND_THREADS` 在 2—64 之间调整；超时可通过 `MIRA_BACKEND_TIMEOUT_SECONDS` 在 30—900 秒之间调整。

长期扩容前，应先把后台 runner 拆为独立进程，再单独增加 Web worker。

## 3. Student Web

正式构建使用已验收的 Webpack 路径。以下三个环境变量必须在 build 和 start 两个阶段保持一致；其中 Backend 是仅由 Student BFF 访问的内部地址：

```bash
cd student-web
export NODE_ENV=production
export MIRA_STUDENT_WEB_PUBLIC_URL=https://learn.example.com
export OPENMAIC_FULL_RUNTIME_PUBLIC_URL=https://classroom.example.com
export MIRA_BACKEND_URL=http://127.0.0.1:8000
npm ci
npm run build
npm run start -- --hostname 127.0.0.1 --port 3000
```

`MIRA_STUDENT_WEB_PUBLIC_URL` 必须与家长 App 的 `STUDENT_WEB_BASE_URL` 完全一致。生产模式会拒绝 HTTP 学生地址；HTTP 的 Runtime 地址也不会获得课堂页的麦克风 Permissions-Policy。

## 4. OpenMAIC 与 Runtime Gateway

不要使用 `scripts/native-runtime.sh` 作为生产入口；它明确启动 Next.js dev server。使用现有的 multi-stage production Dockerfile 和 compose：

```bash
cd openmaic-runtime
export MIRA_STUDENT_WEB_ORIGIN=https://learn.example.com
export MIRA_RUNTIME_PUBLIC_ORIGIN=https://classroom.example.com
export MIRA_RUNTIME_PORT=3101
export MIRA_BACKEND_ENV_FILE=/etc/mira/backend.env
# Provider 凭据和 MIRA_INTERNAL_API_TOKEN 由服务器密钥管理注入，不写入仓库。
docker compose up --build -d backend openmaic gateway
```

`MIRA_STUDENT_WEB_ORIGIN` 和 `MIRA_RUNTIME_PUBLIC_ORIGIN` 没有 HTTP 默认值，缺失时 compose 会直接拒绝启动。`MIRA_STUDENT_WEB_ORIGIN` 同时用于 OpenMAIC build-time frame ancestor 和 Gateway runtime CSP；更换学生域名后必须重新 build OpenMAIC。Gateway production image 设置 `NODE_ENV=production`，因此课堂 cookie 带 `Secure`，且启动时拒绝 HTTP public origin。Gateway 到 Backend 的内部地址固定为 `http://backend:8000`，Backend 到 OpenMAIC 固定为 `http://openmaic:3000`，不依赖 Docker Desktop 专有的宿主机别名。Compose 还会把同一个 `MIRA_INTERNAL_API_TOKEN` 注入 Backend 的 `INTERNAL_API_TOKEN`，确保内部签名契约一致。

## 5. Caddy TLS edge

公开域名已正确解析且可由公开 CA 签发时：

```bash
export MIRA_STUDENT_ORIGIN=https://learn.example.com
export MIRA_CLASSROOM_ORIGIN=https://classroom.example.com
export MIRA_API_ORIGIN=https://api.example.com
export MIRA_STUDENT_WEB_ORIGIN=https://learn.example.com
export MIRA_RUNTIME_PUBLIC_ORIGIN=https://classroom.example.com
python3 deploy/validate_production_origins.py
caddy validate --config deploy/Caddyfile
caddy run --config deploy/Caddyfile
```

`deploy/Caddyfile` 只代理 3000、3101、8000，不代理 OpenMAIC 3100。生产进程应交给 systemd、launchd 或容器编排托管，不应依赖一个终端会话。

## 6. LAN 麦克风 Secure Context

其他手机或 iPad 访问 `http://192.168.x.x` 不属于 Secure Context，无法作为正式麦克风链路。`localhost` 的浏览器例外只适用于运行服务的同一台设备，不能覆盖 LAN 客户端。

LAN 验收必须同时满足：

1. Student 顶层页为 HTTPS；
2. Classroom Gateway iframe 也为 HTTPS；
3. 两个证书在测试终端上均受信；
4. Student 专用 OpenMAIC 路由的 Permissions-Policy 精确包含 Classroom origin；
5. Gateway 的 CSP `frame-ancestors` 精确包含 Student origin。

如果没有可用的公开受信域名，可为三个 LAN 名称配置本地 DNS，并使用 Caddy 内部 CA：

```bash
export MIRA_STUDENT_ORIGIN=https://learn.mira.test
export MIRA_CLASSROOM_ORIGIN=https://classroom.mira.test
export MIRA_API_ORIGIN=https://api.mira.test
export MIRA_STUDENT_WEB_ORIGIN=https://learn.mira.test
export MIRA_RUNTIME_PUBLIC_ORIGIN=https://classroom.mira.test
python3 deploy/validate_production_origins.py
caddy validate --config deploy/Caddyfile.lan
caddy run --config deploy/Caddyfile.lan
```

`deploy/Caddyfile.lan` 使用 `tls internal`。必须把 Caddy 根证书安装到每台测试手机、平板和电脑，并在系统证书设置中启用完整信任。仅在浏览器中跳过自签名证书警告不算通过验收。

## 7. 启动后只读检查

```bash
curl --fail https://api.example.com/api/health
curl --fail https://classroom.example.com/health
curl --fail --head https://learn.example.com/today
curl --fail http://127.0.0.1:3100/api/health
```

随后用真实学生设备确认：登录、打开正式课堂、浏览器请求麦克风权限、ASR 返回、权威课堂事件写回。正式切换前仍应运行 Student Web 的 lint/typecheck/test/build、Gateway 测试、Backend 测试和 OpenMAIC healthcheck。
