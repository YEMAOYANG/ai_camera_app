# 教材目录增量同步

来源规则：语文、数学一至六年级，以及英语三至六年级，优先采用国家中小学智慧教育平台的电子课本。英语一、二年级参考用户指定的 [ChinaTextbook 仓库](https://github.com/TapXWorld/ChinaTextbook/tree/master/%E5%B0%8F%E5%AD%A6/%E8%8B%B1%E8%AF%AD)，并与国家平台同步课堂的版本、起点、主编、年级、册次交叉核对。GitHub 存档不代表当前年度新版。

后续按用户要求补齐外研社一年级起点（陈琳主编）三至六年级：电子课本列表未找到该系列，但国家平台同步课堂有一至六年级 12 册，故全部采用官方目录，GitHub 只交叉核验。具体范围、8 册增量和验证见 [外研社补充记录](2026-09-28-fltrp-primary-supplement.md)。下方数量是首次同步时的快照，不包含后续科学和外研社增量。

## 本次范围和真实覆盖

- 2026-09-28 核对国家平台当前书目 303 册：语文 22、数学 100、英语 181，包含六三和五四学制。年级、册次不能互相替代。
- 低年级英语补充人教版（一年级起点，吴欣主编）、外研社版（一年级起点，陈琳主编）、冀教版（一年级起点）、北京版、清华大学版，共 20 册上下册目录。原上海教育部门确认的 2 册沪教育版书目继续保留，其目录尚未核验；不把旧牛津上海版填进去。
- 当前可选书目合计 325 册，其中 98 册具备已核验目录，计 3,647 条末级目录节点。节点包含课程、复习及教材附录，**不等同于已生成的课件数**。另有 227 册仅具备书目，目录待补齐。
- 既有 311 个教材修订文件及数据库修订、1 条已发布课件绑定、家长选择与选择历史均保持不变。新导入 122 个修订（25 个书目、97 个目录），再次导入新增 0 条。
- 没有调用模型、TTS 或 OpenMAIC 生成。没有复制课文、原题、插图或音视频到产品目录；没有修改数据库结构。

按科目、年级的覆盖数量在 [覆盖清单](../../backend/content/textbooks/sources/textbook-sync-coverage-20260928.json)。这次接通程序和可核验目录，不代表所有出版社版本的目录已经齐全。

## 数据来源与核验

1. `smartedu_ebook_mapping`：官方电子课本详情的资源 ID、`EBOOK_RELATION` 的目标资源 ID 和目录 ID、`ebook_mapping` 的目录 ID 三者对应；保存平台目录层级、原节点 ID 和页码映射。
2. `smartedu_sync_classroom`：用于逐册核验的英语补充教材。原一、二年级白名单为 `sources/smartedu-sync-english-20260928.json`，外研社陈琳一年级起点三至六年级增量为 `sources/smartedu-sync-fltrp-primary-20260928.json`。用 GitHub 目录页核对主题单元，平台目录提供课次细分。来源必须与记录中的版本、年级、册次、主编及目录 ID 对应；未确认的课本页码保持空值。
3. `smartedu_preview_directory`：用于平台没有独立目录映射、但目录页可以逐项目视核验的电子课本。本次补充北京版六年级上册、人教吴欣版六年级下册。只录入实际目录标题、层级和印刷页码，保留目录页 URL、图片摘要；不猜测 PDF 页码或新增课内小栏目。

国家平台有个别源文件自身的冲突：资源 `9e2878bf-964d-47fb-85ba-937cf61159a5` 的第 5 页目录第一单元写作 “How can I get there?”，第 7 页第一单元首页写作 “Amazing places”。该资源仍是书目状态，未将冲突目录导入。

GitHub 仅记录固定提交链接、文件 Git blob 摘要及 SHA-256，清单见 `sources/github-low-grade-english-20260928.json`。PDF 和临时 OCR 文件不进入仓库。

## 不重复与不自动生成

`backend/scripts/sync_textbook_directories.py` 将抓取、离线构建与数据库导入分开。已有任何非空目录（含部分目录）直接保留；已有文件内容相同则跳过、不同则报冲突。目录修订 ID 由来源快照摘要生成，官方节点 ID 保持不变。

新增目录的教学任务书是 `draft`，目标与知识点列表留空；使用依据仍为 `pending`。生成入口继续要求使用依据通过和目标获批，导入目录不会创建课件任务。

## 家长选择和两端 API

沿用 `mira.learning.textbooks.v1`。课次新增可选 `sectionTitle`，保留多层官方目录的中间层标题，其余响应兼容。

家长此前选择的是空书目时，读取接口可使用同一资源、同一教材身份、明确声明 `baseRevisionId` 的第一个目录补充修订。这个解析发生在共享仓储层，家长端、学生端、课程策略和课堂校验一致；不写回选择记录，不改变 CAS 修订号。已存在目录、当前课次或任何课件构建的选择不自动改变。

国家平台已经替换资源 ID 的 9 个旧书目不再作为新选项展示；已选择旧书的家庭保留原选择，不能自动迁移到新书。

两端区分目录未齐、目录已有但课件未生成、课程已开放与前序课程限制。目录同步本身不会使“开始上课”可用。家长仍自主选择每科教材，年级与上下学期沿用此前确认流程。

## 操作方式

```sh
# 网络获取仅限官方元数据，不导入数据库，不获取教材正文。
backend/.venv/bin/python backend/scripts/sync_textbook_directories.py fetch \
  --indexes backend/content/textbooks \
  --snapshots /tmp/mira-textbook-snapshots \
  --report /tmp/mira-textbook-fetch.json

# 用已核验快照构建；重复执行保留已有目录。
backend/.venv/bin/python backend/scripts/sync_textbook_directories.py build \
  --indexes backend/content/textbooks \
  --snapshots backend/content/textbooks/sources/smartedu-directories-20260928 \
  --output backend/content/textbooks/official-directories-v1 \
  --report /tmp/mira-textbook-build.json

backend/.venv/bin/python backend/scripts/textbooks.py validate-catalog \
  backend/content/textbooks/official-directories-v1
```

数据库导入单独使用 `textbooks.py import-catalog`，先核对目标和备份教材表；不运行 migration、seed、reset、prepare、publish。来源目录完整度与教学目标、课件质量审查分开管理。

本地运行使用 `openmaic-runtime/scripts/local-test-stack.sh`，保持 `MIRA_LOCAL_TEST_CURRICULUM_WORKER_ENABLED=0`。进程记录失效时先核对 PID、启动时间、工作目录和端口归属，由脚本清理失效记录。

本次发现学生端使用 `nohup` 启动但没有脱离调用进程组，启动命令退出后进程会被清理。启动器现沿用后端的 `setsid + exec` 方式，始终保留同一 PID 和严格身份校验。再次启动后，在独立命令中确认进程持续运行，8000、3000、3100、3101 均健康。浏览器实际打开学生端并到达 PIN 解锁页；未代填 PIN、修改真实家长教材选择或启动课件。

## 验证记录

- 后端教材相关测试 73 项通过，覆盖来源、导入幂等、空书目补充、跨家庭边界和既有发布绑定保留。
- 学生端 lint、TypeScript 检查、250 项测试及生产构建通过；最终文案调整后重新验证教材页面 7 项测试。
- Flutter analyze 无问题；Flutter test 371 项通过、1 项既有跳过。确认两张视觉差异仅为目录状态文案后更新对应基线。
- 托管启动脚本检查通过；通过真实开发库的合成只读上下文核对六个年级均返回语数英，未创建或读取真实孩子资料。
- 同步前后既有教材文件、数据库修订和发布绑定保持不变；选择与历史只在数据库内取摘要核对。

这些验证覆盖本次教材同步与启动修复，不是全仓库所有后端业务或真机端到端验收。
