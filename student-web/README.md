# Mira Student Web

面向小学一至六年级学生的真实学习网页。学生完成专属配对登录后，可以查看当天课程，并按“老师讲解 → 示范题 → 引导/独立练习 → 总结报告”的顺序学习。课程、判题、报告和掌握度的唯一数据源仍是现有 Python backend，浏览器不保存答案权威，也不持有 Kimi/OpenMAIC 密钥。

## 已完成的学习闭环

- `/today`：读取后端自动安排的当天语文、数学、英语课程和完成进度。
- `/lesson/[taskId]`：读取已发布的 LessonPackage，严格按“讲解 → q1 示范 → q2/q3 引导 → q4/q5 独立检查 → 复盘”执行。
- `/lesson/[taskId]/classroom`：完整 OpenMAIC runtime 专用路由。受信课堂 iframe 位于 Mira/暖瞳课堂顶栏下方，学生始终可以硬导航返回课程列表；runtime、语音或能力未就绪时明确报错，绝不降级到 Mira 播放器。
- 讲授阶段：使用 Mira 受控 React 模板；一年级拼音金样板提供 a/o/e 发音卡、口型提示、点读波纹和示范步骤。
- 练习阶段：支持数值、文本、单选和排序题，答案提交到学生专用学习 API 判定；引导关没有真实答题结果时不能推进。
- 完成阶段：展示真实得分、提示次数、学习建议和课程总结；生成式课程只有 q4/q5 首答 2/2 正确才标记本节 `mastered`。
- 学生身份只能访问自己绑定孩子的任务、会话和报告；兄弟姐妹资源按不存在处理。

OpenMAIC/Kimi 仍在后端生成并校验课程内容，Student Web 只负责播放已经发布的课程包。OpenMAIC 的课堂链只输出 `mira.openmaic.classroom_intent.v2` 结构化教学意图；Python 后端经过能力边界、模板白名单、常见误区、复盘措辞和答案泄漏检查后，编译成受控五段场景。新课程不会直接执行模型生成的 HTML、Canvas 或 JavaScript；旧版已发布课堂仍保留隔离 sandbox fallback。视频、标准发音音频和富媒体资产发布链路尚未加入本版本。

## 登录模型

1. 学生打开 `/pair`，网页生成 5 分钟有效的登录二维码和 4 位核对码。
2. 家长点击 App 首页右上角扫码按钮，确认浏览器、孩子和两端相同的 4 位核对码；首次授权时设置 4 位学习 PIN。
3. 网页在家长授权后以一次性 verifier 交换只绑定该孩子的可信设备凭证；二维码不可重放。
4. 无法扫码时可展开配对码入口，沿用 10 分钟有效的一次性配对码。
5. 学生 access/refresh token 只保存在 Next.js HttpOnly Cookie 中。
6. 会话结束后保留可信设备凭证，下次在 `/unlock` 输入 PIN 解锁。
7. 学生身份无法访问家长、家庭成员、设备、摄像头直播或课程生成接口。

## 本地运行

```bash
cp .env.example .env.local
npm install
npm run dev
```

将 `.env.local` 中的 `MIRA_STUDENT_WEB_PUBLIC_URL` 改为家长手机能够识别的学生网页公开地址。本地真机联调应填写电脑局域网地址，例如 `http://192.168.1.100:3000`；不要填写 `localhost`。该地址用于生成登录二维码，必须与家长 App 的 `STUDENT_WEB_BASE_URL` 完全一致。正式环境必须使用 HTTPS。

使用受管本地测试栈时，电脑浏览器也可以通过 `localhost:3000` 或 `127.0.0.1:3000` 进入。显式本地模式会先验证后端返回的课堂网关地址，再将课堂地址映射到同一环回主机，保留网关端口和一次性票据，避免 iframe 跨站导致登录 Cookie 丢失。该映射只允许配置地址及固定环回别名，生产域名校验保持不变。

开发环境继续使用 Next.js Turbopack；正式构建默认使用已经完整验收的
Webpack 路径。`npm run build:turbopack` 保留为显式实验命令，供正常宿主或
CI 验证 Turbopack 兼容性，不作为发布阻塞项。

默认连接 `http://127.0.0.1:8000` 的 Python backend。

`OPENMAIC_FULL_RUNTIME_PUBLIC_URL` 必须填写受信 OpenMAIC gateway 的公开地址。正式环境只接受 HTTPS；该精确 origin 会同时用于校验一次性 launch URL，并只在完整课堂专用路由的 `Permissions-Policy` 中授权麦克风。其他页面继续使用 `microphone=()`。开发环境未填写时默认使用 `http://127.0.0.1:3101`。

主要 BFF 路由：

- `/api/auth/qr/start|exchange`
- `/api/auth/pair|unlock|refresh|logout|me`
- `/api/learning/today|today/assign`
- `/api/learning/sessions`
- `/api/learning/sessions/[sessionId]/answer`
- `/api/learning/sessions/[sessionId]/runtime`
- `/api/learning/sessions/[sessionId]/openmaic-launch`
- `/api/learning/sessions/[sessionId]/actions/[actionId]/complete`
- `/api/learning/reports/latest`

## 验证

```bash
npm run lint
npm run typecheck
npm test
npm run build
```
