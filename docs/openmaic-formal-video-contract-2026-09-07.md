# OpenMAIC 正式视频合同

新目标的内容 Provider profile 为 `mira.learning.question-provider-profile.v106-deepseek-professional-video`。
原 `PROFESSIONAL_POLICY` 保留 adaptive.v2 图片模式的原对象；新增 `VIDEO_PROFESSIONAL_POLICY` 作为默认正式创作策略，复用原技能选择、年级边界、图片、联网研究与最终教学质量检查，仅增加独立 `video` 策略。

视频固定为 HappyHorse `happyhorse-1.0-t2v`，策略 `mira-formal-happyhorse-video.v1`；按教学需要使用，每课最多调用一次、生成一段 5 秒、720p、16:9 视频。允许零视频，视频能力开启不代表必须使用视频。旧策略的 `enableVideoGeneration` 保持 false；新请求传 true，实际选中的策略和开关同时进入原正式请求哈希。

专业创作回执新增 `videoGenerationEnabled: true`、`videoPolicyId`，只允许新策略使用。视频另存 `result.video` / `manifest.video`，不改变图片 `media` v1 的结构。视频回执 schema 为 `mira.openmaic.formal-video-receipt.v1`，包括请求、构建项、课堂、会话身份及 Provider/model、`videoCount`、`assets`、`receiptSha256`。

资产只接受同课堂 `/api/classroom-media/<stage>/media/generated-<sha256>.mp4`，MIME 为 `video/mp4`，大小不超过 200 MiB，实际尺寸 1280×720；容器时长允许 4900–5100 毫秒的帧误差，提交请求仍固定 5 秒。每项保存 SHA-256、字节数、尺寸、时长和真实引用它的场景 ID。后端检查身份、回执哈希、数量、场景引用和媒体可读性；Runtime 对源文件进行实际生成轨迹、哈希和 ffprobe 验证。完成、发布、学生启动均要求证据一致，早期目录 SQL 也要求新视频合同的回执，不会把缺回执的页面显示为可启动。

历史兼容按原 v105 profile 和原策略重建精确目标，保留四个已有指纹：

| 历史策略 | 指纹 |
| --- | --- |
| legacy | `174a787e2ddbb8dd9c50e859a829bd2fe08fec71838448a8c5e5b0d2246766f1` |
| image | `48cceefd0543abe9e3bfcf2f8d640ef21b8e03503cfa3dc6ef89a0428bcef2df` |
| integrated.v1 | `7d4c0980789621cffb338e14b39c7dbc7b0d34c40013be0725c0076dad3b90a3` |
| adaptive.v2 | `c8fb538cb53fe365f86d0fd62bb9f270c9a2c17a39d5b0b8ce425cf7e0051f4a` |

新视频目标指纹为 `e7f3d4be11e40d516d68b793682c67afe6e515b9e18bab1cd12d6649435cc0cc`。自动调度范围增加新视频目标，并保留此前已启用的 integrated/adaptive 队列；legacy/image 仍只允许显式恢复。终态、未知指纹、课程合同变化、有效租约、Provider 模糊结果等原门禁继续生效，不改写已持久化任务，也不重新派发已有请求。

后端离线验收覆盖真实 client 请求构造、重复查询不重派、原四种目标哈希、真实内存 SQL 的调度和视频可见性、零/一视频回执、跨课堂或会话、尺寸/时长/数量/哈希错误、未引用或不可读资产、发布和学生启动拒绝缺失回执。测试不调用 Provider、不写业务库。
