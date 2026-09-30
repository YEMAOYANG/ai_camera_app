# 自主学习与家长减负：优化验收

本轮在现有 Student Web、OpenMAIC 原生课堂、后端会话和 Flutter 家长报告上修改，没有另建课件网站或独立 HTML。沿用当前教材选择、发布审核和按孩子隔离的学习记录。

## 已落地的行为

| 环节 | 当前行为 | 对家长时间的作用 |
| --- | --- | --- |
| 进入学习 | 一二年级优先显示到期复习、继续学习或后端核实可用的课程图片；完成后显示休息和复习日期 | 减少家长替孩子找课的操作 |
| 选课 | 四科有不同含义的原创插画；低年级先看已开放课件的大图片，完整文字目录由家长展开 | 降低文字阅读门槛 |
| 听懂下一步 | 18 段预制 Qwen Serena 语音覆盖进入、继续、复习、休息和结束；保留重听 | 不用浏览器系统朗读；自动播放被限制时仍有大按钮 |
| 原生课堂 | 图片任务占主区域；目录、对话和完整工具按需展开；找老师同时打开对话与原有提问入口 | 减少默认界面的分心和寻找操作 |
| 家长帮助 | 根据尚未独立完成的目标给出一个具体生活动作，并提示把任务交还孩子 | 避免只说“请家长辅导” |
| 家长记录 | 日周报告可选填实际辅导分钟、介入原因和以往相近任务分钟数 | 可以观察实际投入，不拿播放时长或求助次数当作家长时间 |
| 课程扩展 | 活动定义绑定课程发布哈希；目标、题数、报告分母、图像题和声音包按课配置 | 后续课程不再强制复用《天地人》的六个目标 |

首次成绩、独立新情境证据、复习表现仍按原有服务端规则记录。家长填用时不会修改孩子的成绩。未填写不等于零；只统计成对的自报对比，允许本次用时更多，不把差值说成产品造成的省时效果。

## 课程供给的实际状态

本轮没有新增正式发布课程；现有《天地人》仍是已开放样板。

后续《金木水火土》《口耳目手足》《日月山川》和《语文园地一》的“六到十”部分已从指定版本的[官方教材阅读器](https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId=1c73b348-e8b6-47d6-84b0-6dbacbe28268&catalogType=tchMaterial&subCatalog=tchMaterial)核对目标范围，形成独立活动草案。目标数分别是 7、7、8、5。“六到十”不是整个语文园地一的完整教学范围。

草案位于 `backend/content/textbooks/learning-units/primary1-literacy.v1.json`，仍标明缺少完整题库、原创教学图、正式音频和逐课审核。缺少素材会在请求模型前拒绝预览，目录和草案不会被当作已发布课件。没有绕过发布门槛，也没有声称已完成连续五课。

## 家长记录接口

- `GET /api/reports/learning/{sessionId}/coaching?recordDate=YYYY-MM-DD`
- `PUT /api/reports/learning/{sessionId}/coaching`，字段为 `recordDate / minutes / usualMinutes / reason / revision`。
- 服务端验证登录、家庭范围、实际学习日期和能力权限；按会话和日期版本化保存，重复请求幂等，409 冲突需重新读取。
- 数据使用现有 `learning_sessions.runtime_state_json.parentCoaching`，没有数据库迁移或新建每日计划域。

## 实际界面检查

在受管本地生产构建上检查书包 → 图片选课 → 已完成《天地人》的 OpenMAIC 课堂 → 语音重听 → 工具展开 → 返回书包，覆盖桌面与 390 × 844。已有孩子的课程完成状态用于只读观察，没有重做题目、修改成绩或伪造家长记录。

窄屏检查发现并修复了异步学习建议将书包位置推下、固定 3D 画布仍停在原处的遮挡问题。新增回归用例模拟同尺寸槽位随页面内容移动。

还修复本地课堂与网关后台进程跟随调用终端清理而退出的问题：独立进程组启动，保持原 PID、开始时间、工作目录和端口归属校验。

Flutter 的 390 × 844 辅导记录截图来自隔离组件测试，不是实际家庭的辅导数据。

## 验证记录

- 后端相关 83 项测试通过，覆盖课程预览/发布、活动和持久化、教材入口、家长记录、学习摘要与成长评估。
- Student Web 全量 257 项通过；随后书包定位修复相关 23 项通过，其中新增 1 项。lint、TypeScript 和生产构建通过。
- Flutter 全量 384 项通过，1 项跳过；随后用时记录及报告相关 4 项通过。`flutter analyze` 无问题。
- 原生 OpenMAIC 以生产专用 TypeScript 配置构建；开发全量类型检查仍存在本轮之前测试文件的类型错误，不能说全仓类型检查通过。
- 本地原生启动器隔离回归通过，包括独立进程组和既有健康策略校验；两端生产构建均通过。
- 图片、导航语音的源文件、时长、哈希和发布路径已核对；新增 0134 补丁反向应用检查通过。

## 仍需实际验证

没有做新的付费实时师生对话，没有在家长真机上填写实际记录，没有进行真实儿童试用或学习效果比较。当前改动减少了需要家长带路和读操作说明的环节，也提供了记录投入的方式；还不能据此宣称已经优于现实课堂、孩子一定能独立完成，或已经节省多少分钟。

后续用真实试用观察：能否自己进入、首次操作求助、在什么地方退出、独立新题与延迟复习表现，以及家长实际投入是否下降。学校课程照常进行，产品定位是课后针对性帮助。

## 截图

![图片选课](/Users/sqcopenclaw/Desktop/ai_camera_app/output/independent-learning-20260929/02-picture-catalog.png)

![默认原生课堂](/Users/sqcopenclaw/Desktop/ai_camera_app/output/independent-learning-20260929/03-classroom-default.png)

![390 像素课堂](/Users/sqcopenclaw/Desktop/ai_camera_app/output/independent-learning-20260929/04-classroom-390.png)

![手机书包完成态及图片入口](/Users/sqcopenclaw/Desktop/ai_camera_app/output/independent-learning-20260929/05-schoolbag-390.png)

![找老师直接打开对话与输入](/Users/sqcopenclaw/Desktop/ai_camera_app/output/independent-learning-20260929/06-teacher-help-390.png)

![家长辅导记录组件](/Users/sqcopenclaw/Desktop/ai_camera_app/output/independent-learning-20260929/parent-coaching-390.png)
