# 《天地人》可玩样板

已由项目内的 OpenMAIC 原生课堂接入取代，8767 独立样板已停用。此目录仅保留早期方案记录。

当前入口：学生端教材目录 → 《天地人》。接入说明见 `docs/architecture/2026-09-29-tiandiren-openmaic-native.md`。

内容包括自由探索、拖字找图、角色配音演示、六轮角色游戏、六题首次挑战、按目标补练、六道生活情境验证、六道延迟复习题、家长反馈和自由复玩。语音读题适配初识字孩子；游戏没有倒计时或错误扣分。

## 在项目根目录运行

已有素材包时：

```sh
backend/.venv/bin/python backend/scripts/serve_textbook_sample.py --port 8767
```

首次准备素材，或修改 `lesson.json` 后：

```sh
backend/.venv/bin/python backend/scripts/prepare_textbook_sample.py
```

准备工具需要现有 `output/textbook-publication-20260924/prepared-release.json`、原版 OpenMAIC 发布媒体、本机 macOS 中文 Tingting 语音和 `ffmpeg`。读取并校验原素材，不重生成原课件，不调用付费 Provider。生成到 `output/tiandiren-play-v2/`。本机语音引擎在受限沙箱中可能返回零帧音频；工具会拒绝此结果，需要允许本机语音进程运行后重试，不能把空文件当成功。

`lesson.json` 含私有题目，不能作为静态资源发布。服务只公开当前活动及完成后允许查看的反馈；HTTP 不提供该 JSON、未来题库或通用文件读取。不要将这个仅供本机使用的服务直接暴露到公网。

进度文件是包目录内的 `sample-progress.sqlite3`，与业务库完全分开。匿名会话使用 HttpOnly Cookie；刷新、关页、服务重启可恢复。教材内容摘要变化时开启新体验，旧样板行保留，不将旧内容结果迁移到新题目。不同浏览器、不同主机名及隐私窗口的样板会话各自独立。

## 验证

```sh
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_textbook_sample.py'
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_textbook_sample_http.py'
```

第二条需要先准备素材，测试仅绑定临时本机端口并使用临时库。样板服务并发更新使用事务、版本检查及幂等请求，避免双击或丢回执导致重复计分。

正式接入仍需将此状态机接入已授权的教材会话和现有 tasks / 报告入口，发布新教学版本，保留原 OpenMAIC 师生对话及课堂能力。当前样板没有实时 AI 对话、自动朗读评分或正式家长端接入。新增本机参考配音尚未完成正式教师音色及 ASR 审核。现有教材权利与专业教研审核状态没有改变。

设计和接口说明见项目内 `docs/architecture/2026-09-28-tiandiren-play-sample.md`；验收见 `docs/reviews/2026-09-28-tiandiren-play-sample-acceptance.md`。
