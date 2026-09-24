# 固定教材第一课与本机数据库落地

## 数据库处理

沿用本机 MySQL `ai_camera_app_dev`，不重置原数据。迁移 `082` 新增教材身份、修订、家长选书、正式课程绑定和选书历史五张表；`083` 新增私有课程预览表。教材正文/PDF、账号密码不进入教材表。

2026-09-24 先备份，再在关闭网络的独立临时 MySQL 中完整恢复 113 张表，执行两个迁移并导入目录。恢复后的数据摘要与源库一致；迁移及导入后所有原业务表摘要保持不变。随后应用相同迁移到已确认的本机开发库，再次核对原业务表摘要。

- 原数据：16 份课程、18 次学习会话，均保留。
- 新数据：22 册语文教材索引、23 个资料修订；多出的修订是第一课六字范围的核验更新，不是第 23 本教材。
- 备份：`output/textbook-first-course-20260924/database-backup/database.sql`，约 19.8 MB，目录权限 0700、文件 0600，已被 Git 忽略。
- 验证记录：同目录 `verification.json`；实际迁移记录：`output/textbook-first-course-20260924/database-applied.json`。
- `verify_textbook_database_upgrade.py` 只备份和验证副本，不迁移源库，仅接受明确命名的本机数据库及预期迁移。

同一册教材的资料修订不会在选书页面重复成两本。默认展示最新导入修订；若家长已确认旧修订，继续保持原选择，不自动改写学习对应关系。

## 第一课内容边界

对应官方统编版六年制一年级语文上册，第一单元识字，`1 天地人`，印刷第 8 页、PDF 第 13 页。2026-09-24 在官方阅读器核对到六字范围：天、地、人、你、我、他。

新资料在 `backend/content/textbooks/revisions/pep-chinese-g1-upper.preview.v2.json`，旧修订不覆盖。OpenMAIC 生成后进行内容与交互审阅，修正不适合本课的偏旁、字源解释及角色称呼，补充六题读题语音；审阅修正在 `backend/content/textbooks/reviews/`。未提交教材 PDF、原图、课文或原题。八个场景覆盖六字认识、你我他角色变化互动、六题辨认和生活迁移，不要求拼音、书写或后续课次知识。

教材使用依据与教师终审仍为 pending/draft。预览使用独立合同 `mira.learning.textbook-private-preview.v1`，明确 `publicationAllowed:false`，不冒充正式审核通过的教材课程。

## 生成与复用合同

不新增学生生成接口。运营 CLI 通过已有 OpenMAIC `POST /api/generate-classroom` 发起一个普通课堂预览，通过 `GET /api/generate-classroom/{jobId}` 和 `GET /api/classroom?id=...` 读取结果。关闭联网、图片素材、视频和原生一体式配音；先完成并保存课件。随后 `narrate` 复用私有 `POST/GET /api/mira/formal-audio/tts` 的幂等音频服务，按课程与段落冻结请求编号，生成/下载每段语音，独立保存成功片段。这是复用音频基础设施，不是授予预览正式课程资格，也没有 ASR 审核结论。AI 凭据仍由 OpenMAIC 服务端管理。

冻结教材身份、资料摘要、节点、知识任务书、原创及预览提示版本和生成选项，规范化摘要作为 `preview_key`。数据库先提交 `queued → dispatching` 原子领取，再发起网络请求，收到任务编号后记录 `generating`。并发或再次执行返回已有任务。

原生普通生成接口没有服务端幂等编号，因此超时标记 `dispatch_unknown`；进程退出留下 `dispatching`。两者都不会自动重发，必须先核对原任务及输入追踪编号，不能清空状态盲目重试。

完成后保存课堂编号、课件 JSON 快照和摘要。音频保留在 OpenMAIC 媒体目录，数据库备份不能代替媒体目录备份。结构检查失败也保留产物，标记 `review_required`，不重新生成整课。`preview_ready` 仅表示生成及结构检查完成；正式发布仍需原有发布链路和审核。

```sh
backend/.venv/bin/python backend/scripts/textbook_preview.py prepare
backend/.venv/bin/python backend/scripts/textbook_preview.py start --key <previewKey>
backend/.venv/bin/python backend/scripts/textbook_preview.py status --key <previewKey>
backend/.venv/bin/python backend/scripts/textbook_preview.py narrate --key <previewKey> --classroom-directory openmaic-runtime/.runtime/OpenMAIC/data/classrooms
backend/.venv/bin/python backend/scripts/textbook_preview.py freeze --key <previewKey>
```

命令不隐式导入教材、不迁移、不发布，不开启批量生成。再次 `start`、`narrate` 或 `freeze` 已完成的同一任务不会调用 AI。每段配音先查询原记录，失败或不确定结果不会换编号重发。`freeze` 保存内容摘要命名的预览快照，避免 OpenMAIC 编辑器缓存继续展示旧稿，旧快照不覆盖。

## 验证

- 教材/预览相关 21 项 Python 检查通过，覆盖权限、不可变版本、家长选择、重复提交、超时不重发、运行地址变化、缺页/缺音频、音频请求复用及不可变预览快照。
- 独立 MySQL 验证通过：4 路预览准备产生 1 个记录，4 路并发开始只派发 1 次模拟任务；原目录导入、制作任务、选书 CAS 与发布 CHECK 继续通过，无真实 Provider 调用。
- 扩展检查发现既有 `test_formal_multigrade_registry` 的公平调度测试使用不带 `execute` 的 `object` 数据库替身，当前失败；该正式调度代码未在本次修改，不能宣称全仓测试通过。
- 第一次尝试 `EO-9Gjew3Y` 在普通 TTS 的 30 秒超时后失败。原通道在所有配音完成后才保存课件，没有可恢复的课件文件；保留原失败任务和部分音频。修改为先保存课件再逐段配音，以新的冻结输入执行一次替代任务 `vuPQhbx9SQ`。未清除旧记录，也未把失败任务改成成功。
- 完成的输入摘要：`78e667acb79a9850320b102647581ed092b671380cae947edfc4aca5c20edf9d`；原始课堂 `aFUbum5CNW`；最终固定预览 `tbprev_914d573f3a5d91fecc1da930`。
- [打开第一课预览](http://127.0.0.1:3100/classroom/tbprev_914d573f3a5d91fecc1da930)：8 个场景、6 道练习、50 段 Qwen 配音，WAV 总时长 332.24 秒。含跟读/操作/作答按 8–10 分钟设计，实际学习时长取决于学生速度。
- 50 个媒体链接全部通过同源音频读取检查；快照摘要校验通过。用禁止 Provider 调用的替身替换生成方法后，再次执行真实记录的 start/narrate/freeze，均复用原结果。
- 浏览器已核对六字展示、讲解播放推进、互动正确/错误反馈及角色交换；六题故意错一题得到 50/60 并显示解释。检查发现并修正互动配置 `widgetConfig:null` 导致的缓存保存错误，最终版本播放未出现新的浏览器错误。
- 验证文件：`output/textbook-first-course-20260924/acceptance.json`、`final-preview.json`、`original-classroom.json`、`reviewed-classroom.json`。音频独立收据和断点在原始课堂目录 `textbook-preview-audio/`；Qwen 服务保存原始幂等请求记录。

本阶段完成本机数据库与第一课审核预览。正式学生教材课程发布绑定、教师审核和教材使用依据确认仍需后续完成。其余多数教材目前只有版本索引，不代表完整目录和全部课程。错题周测、家长报告、拍照作业分析不属于本次变更。
