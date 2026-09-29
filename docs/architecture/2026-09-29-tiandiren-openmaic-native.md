# 《天地人》接入现有 OpenMAIC 课堂

学生入口继续使用教材目录的已发布课程 `b4d82c5bbde5b2b7deaa486c469121dab7dc43a6f2142cac5b67932e8e2f6f2c`。

## 接入位置

- `backend/content/textbooks/activities/tiandiren.v1.json`：与准确发布 SHA 绑定的版本化活动配置，复用已有审核配图、语音，不调用生成模型。
- `backend/content/textbook_activity.py`：找图、切换说话人、首次选择、针对性再练、换种玩法的服务端状态机。
- `TextbookClassroomService` 在公开课堂副本中注入 `miraActivity`；原发布 JSON、哈希与媒体保持不变。其他教材不匹配此活动。
- OpenMAIC 补丁 `0131` 在原生 `SceneRenderer` 中渲染 `TextbookPlay`，取代该课互动场景与测验场景的旧展示。继续使用原课堂老师、同学、讨论、语音与导航。
- 两个活动场景的公开副本移除旧线性动作和旧 HTML；由原生组件播放当前任务的既有语音，避免一边找地面、一边自动读下一道天空题。讲解场景的老师配音仍沿用原播放引擎。

## 接口与数据

`GET /mira/textbook-play` 返回学生当前两个活动分区、版本、当前题目和已发生的学习证据。未答题时不返回答案、解析、技能答案提示或未来题目。

`POST /mira/textbook-play` 接收 `{section, version, action, choice?}`；section 是 `games` 或 `challenge`，action 是 `answer / next / hint / adult / replay`。网关沿用课堂 HttpOnly 会话，将请求转发至 `/internal/learning/textbooks/runtime/play`。

服务端验证学生、教材选择、年级版本、课程与学习会话，用行锁修改 `learning_sessions.runtime_state_json.textbookPlay`；与原有讲解进度共存，不新增数据库表。过期版本返回 409，客户端重新读取已保存进度，断网后不盲目重放答案。

选择题第一次提交不可修改；提示和大人帮助排除在独立正确数外。只对首次错误或有帮助的知识点安排再练，再练不改首次成绩；最后用点图和角色变化再认六字，单独计数。游戏可重玩，保留第一次游戏记录和原测验分数。未评价朗读、书写、长期记忆，也未在本补丁增加隔日复习调度。

完成规则要求原讲解页面、游戏与后续练习完成。活动自己的声音可能暂停原讲解，活动通过与原音频播放证据分别保留，不伪造 `action_completed`。

## 运行方式

使用 `local-test-stack.sh` 核验并停止已有服务，通过 `native-runtime.sh build-openmaic-production` 应用固定补丁并生产构建，再由本地管理脚本启动。Student Web 原入口不变，不再使用 8767 的独立 HTML 样板作为交付入口。
