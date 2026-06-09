# Mira Guardian App Flow and State Matrix v1

更新日期：2026-05-28  
适用范围：Figma 设计范围、页面查缺补漏、组件状态设计、后续 Flutter 页面验收  
来源：`README.md`、`docs/ai_camera_parent_needs_product_tech_plan.md`、`design/mira_guardian_high_fidelity_ui.html` 的业务页面/交互状态

## 1. 产品信息架构 IA

```text
Mira Guardian 家长端 App
  Onboarding / 首次使用
    欢迎页
    登录注册
    手机验证码
    家长身份
    创建家庭
    扫码绑定设备
    蓝牙发现
    Wi-Fi 配网
    绑定成功
    孩子档案
    摄像头命名
    紧急联系人
    权限引导
  主导航
    首页
      孩子当前状态
      设备状态
      当前任务
      下一步
      家长待处理
      风险与异常
      快捷入口
    任务
      今天
      明天
      本周
      日历
      任务模板
      任务详情
      专注计时
      任务证据
      小书包
    + 创建任务
      普通任务
      小书包
      睡前任务
      打卡任务
      奖励规则
    看护
      实时画面
      音频通话
      截图
      云台视角
      事件回放
      安全区域
      安全事件
    我的
      家庭账户
      个人信息
      账号安全
      订阅套餐
      报告中心
      日报
      周报
      成长时刻
      积分奖励
      奖励商店
      打卡审核
      家庭成员
      设备管理
      对话与人设
      AI 规则
      隐私与权限
      通知设置
      学习内容
      帮助反馈
      关于我们
```

导航原则：

- 底部 tabbar：`首页 / 任务 / + 创建任务 / 看护 / 我的`。
- `+ 创建任务` 为全局 action，不是普通内容页。
- `报告、积分、打卡审核、设备、隐私、通知、订阅` 收进 `我的`，避免底部导航失焦。
- 安全事件可从首页、看护、通知、我的入口进入，但必须落到同一个事件详情模型。

## 2. 完整页面清单

### 2.1 主流程页面

| 页面 ID | 页面 | 层级 | 入口 | 来源 | 备注 |
|---|---|---|---|---|---|
| `welcome` | 欢迎页 | 主流程 | 首次打开 | HTML | 可作为 onboarding 首屏 |
| `login` | 登录注册 | 主流程 | 欢迎页 | HTML/README | 手机号+验证码 |
| `parentIdentity` | 家长身份 | 主流程 | 登录后 | HTML/README | 妈妈/爸爸/祖辈/其他家人 |
| `bind` | 扫码绑定 | 主流程 | 家长身份后 | HTML/README | 二维码、蓝牙发现 |
| `wifi` | Wi-Fi 配网 | 主流程 | 扫码成功 | HTML/需求补齐 | 需要 loading/error/offline |
| `bindDone` | 绑定成功 | 主流程 | 配网成功 | HTML | 进入孩子档案 |
| `child` | 孩子档案 | 主流程/二级 | onboarding/我的 | HTML/README | 首次与编辑态不同 |
| `name` | 摄像头命名 | 主流程/二级 | 孩子档案后 | HTML/产品方案 | 孩子起唤醒名 |
| `contacts` | 紧急联系人 | 主流程/二级 | 命名后/安全 | HTML/README | SOS 兜底联系人 |
| `home` | 首页 | 主流程 | tab | HTML/README | 状态、下一步、待处理 |
| `tasks` | 任务首页 | 主流程 | tab | HTML/README | 日期、任务列表、筛选 |
| `createTaskSheet` | 创建任务 | 主动作 | 中置 + | 需求补齐 | 新视觉必须独立高保真 |
| `watch` | 实时看护 | 主流程 | tab | HTML/README | 画面、隐私、通话 |
| `my` | 我的总览 | 主流程 | tab | HTML/README | 家庭账户中心 |

### 2.2 二级页面

| 页面 ID | 页面 | 所属模块 | 入口 | 来源 |
|---|---|---|---|---|
| `care` | 协作待办 | 首页/我的 | 首页待处理、我的 | HTML |
| `sleep` | 睡眠晨起 | 首页/任务 | 首页快捷、任务 | HTML/README |
| `flow` | 任务模板 | 任务 | 任务页、创建任务 | HTML |
| `packing` | 小书包 | 任务 | 首页、任务模板、创建任务 | HTML/README |
| `taskDetail` | 任务详情/证据 | 任务 | 任务列表、待处理 | HTML/README |
| `focus` | 专注计时 | 任务 | 任务详情 | HTML/README |
| `playback` | 事件回放 | 看护 | 看护页、报告、成长时刻 | HTML |
| `zones` | 安全区域 | 看护/我的 | 安全、设备规则 | HTML/README |
| `safety` | 安全事件中心 | 看护/我的 | 首页异常、看护 | HTML |
| `safetyDetail` | 安全事件详情 | 看护 | 告警、推送、事件中心 | HTML |
| `report` | 日报 | 我的/首页 | 首页、我的报告中心 | HTML/README |
| `weekly` | 周报 | 我的 | 我的报告中心 | HTML/README |
| `moments` | 成长时刻 | 我的 | 报告、我的 | HTML/README |
| `points` | 积分总览 | 我的 | 首页、我的 | HTML/README |
| `reward` | 奖励商店 | 我的 | 首页申请、积分 | HTML/README |
| `checkin` | 打卡审核 | 我的 | 我的、待处理 | HTML/README |
| `conversation` | 对话与人设/AI 规则 | 我的 | 我的设置 | HTML/README |
| `privacy` | 隐私与权限 | 我的 | 我的、看护、AI 规则 | HTML/README |
| `family` | 家庭成员 | 我的 | 我的、设置 | HTML/README |
| `device` | 设备管理 | 我的 | 我的、设置 | HTML/README |
| `notifications` | 通知设置 | 我的 | 我的右上角/设置 | HTML/README |
| `education` | 学习内容 | 我的 | 设置 | HTML/产品方案 |
| `subscription` | 订阅套餐 | 我的 | 我的顶部 | HTML/产品方案 |
| `accountProfile` | 个人信息 | 我的 | 家庭账户卡 | HTML/README |
| `accountSecurity` | 账号安全 | 我的 | 设置 | HTML/README |
| `settings` | 设备与规则聚合 | 我的 | 我的管理入口 | HTML |
| `feedback` | 帮助反馈 | 关于我们 | 关于我们 | HTML |
| `about` | 关于我们 | 我的 | 我的 | HTML |

### 2.3 三级页与弹层

| ID | 类型 | 所属 | 用途 |
|---|---|---|---|
| `evidenceSheet` | bottom sheet | 任务证据 | 确认完成、部分完成、驳回 |
| `taskDateSheet` | bottom sheet | 创建任务 | 选择今天、明天、未来日期 |
| `taskTemplatesSheet` | bottom sheet | 创建任务 | 套用一天任务模板 |
| `taskEditSheet` | bottom sheet | 任务详情 | 修改、延后、复制、删除 |
| `timePickerSheet` | bottom sheet | 创建/编辑任务 | 选择开始/结束时间 |
| `privacySheet` | bottom sheet | 看护 | 实时看护隐私提示 |
| `privacyNoticeSheet` | bottom sheet | 登录 | 儿童音视频采集说明 |
| `rewardRequestSheet` | bottom sheet | 奖励 | 同意兑现、同意稍后、暂不兑换 |
| `manualRewardSheet` | bottom sheet | 积分 | 家长主动兑换 |
| `rewardEditSheet` | bottom sheet | 奖励商店 | 添加/修改奖品 |
| `pointRuleSheet` | bottom sheet | 积分 | 阶段阈值和计量类型 |
| `pointMilestoneSheet` | bottom sheet | 积分 | 积满阶段后的处理 |
| `callSheet` | confirmation sheet | 看护/安全 | 发起音频通话 |
| `safetyTestSheet` | confirmation sheet | 安全 | 测试紧急联系人 |
| `zoneSheet` | action sheet | 安全区域 | 新增区域 |
| `memberSheet` | action sheet | 家庭成员 | 修改权限 |
| `contactSheet` | bottom sheet | 联系人 | 添加紧急联系人 |
| `packingSheet` | bottom sheet | 小书包 | 临时添加物品 |
| `deleteDataSheet` | confirmation sheet | 隐私 | 删除儿童数据 |
| `unbindSheet` | confirmation sheet | 设备 | 解绑设备 |
| `changePhoneSheet` | bottom sheet | 账号安全 | 更换手机号 |
| `loginDevicesSheet` | bottom sheet | 账号安全 | 登录设备管理 |
| `logoutSheet` | confirmation sheet | 我的 | 退出登录 |
| `deleteAccountSheet` | confirmation sheet | 账号安全 | 注销账号流程 |
| `termsSheet` | info sheet | 关于我们 | 服务协议摘要 |
| `privacyPolicySheet` | info sheet | 关于我们 | 隐私政策摘要 |
| `subscriptionDowngradeSheet` | info sheet | 订阅 | 降级说明 |
| `feedbackSheet` | bottom sheet | 帮助反馈 | 提交反馈 |

### 2.4 查缺补漏页面

旧 HTML 原型没有全部独立呈现，但需求和状态矩阵需要补齐：

| 页面/状态 | 为什么需要 | 处理方式 |
|---|---|---|
| 通知权限引导 | 安全告警、任务确认依赖推送 | onboarding 或首次进入首页后弹出 |
| 相机/相册/麦克风权限说明 | 看护截图、通话、打卡素材需要 | 看护/打卡首次使用局部状态 |
| 设备离线全页 | 首页、看护、设备管理高频异常 | 必须独立高保真 |
| 固件升级状态 | 设备管理必备 | 设备详情局部高保真 |
| 弱网/重连状态 | 看护页必备 | 看护页面局部状态 |
| 隐私模式阻断页 | 看护和记录入口受限 | 必须独立高保真 |
| 搜索/筛选无结果 | 任务、报告、事件回放、奖励商店 | 组件状态 |
| 角色无权限 | 祖辈/其他家人/临时查看者场景 | 组件状态 + 权限说明页 |
| 多设备/多孩预留空状态 | 后续扩展但 MVP 暂缓 | 空状态组件 |
| AI 误判上报 | 任务证据、看护事件 | sheet 或详情页入口 |
| 权限引导独立页 `permissions` | 通知、相机、麦克风、相册权限贯穿 onboarding、看护、打卡 | 必须有可点击页面，支持 default/loading/error/success/permission denied |
| 设备离线全页 `deviceOffline` | 首页、看护、设备管理都需要进入同一离线解释模型 | 独立高保真页面，展示最后在线时间、重连步骤和本地可用能力 |
| 隐私阻断页 `privacyBlock` | 隐私模式会阻断实时看护、回放、部分记录入口 | 独立高保真页面，展示开启原因、可见范围和管理员操作入口 |
| 组件状态总览 `componentStates` | 验收需要确认按钮、卡片、标签、表单、搜索/筛选/排序状态 | 原型中提供可点击的组件状态实验台，作为全局状态展示页 |

## 3. 用户任务流

### 3.1 首次进入

```text
欢迎页
  -> 登录注册
  -> 验证码
  -> 家长身份
  -> 创建家庭
  -> 扫码绑定
  -> Wi-Fi 配网
  -> 绑定成功
  -> 孩子档案
  -> 摄像头命名
  -> 紧急联系人
  -> 通知/隐私权限引导
  -> 首页
```

关键状态：

- 登录验证码发送 loading、倒计时、错误码。
- 扫码失败、蓝牙发现失败、无设备。
- Wi-Fi 密码错误、配网中、配网超时、绑定成功。
- 孩子档案必填校验。
- 摄像头命名可跳过但要提示后续入口。
- 通知权限拒绝时进入 permission denied 状态。

### 3.2 查看监控

```text
首页实时看护入口 / 看护 tab
  -> 检查设备在线
  -> 检查家长权限
  -> 检查隐私模式
  -> 连接实时画面
  -> 显示设备端远程查看提示
  -> 通话 / 截图 / 提醒 / 事件回放
```

关键状态：

- loading：连接设备、获取视频流。
- permission denied：家长角色无权限或本机权限缺失。
- offline：设备离线。
- privacy mode：隐私模式阻断实时画面。
- weak network：画面卡顿，显示重连和低清模式。
- success：截图保存、通话发起、提醒发送。

### 3.3 处理告警

```text
推送 / 首页异常 / 看护异常
  -> 安全事件详情
  -> 查看截图/短片/触发规则
  -> 联系孩子或家庭成员
  -> 标记已处理 / 误报 / 升级联系人
  -> 处理记录进入日报/事件流
```

关键状态：

- abnormal：安全区域、陌生人/敲门、异常声音、长时间未出现。
- loading：拉取证据。
- empty：证据不可用或已过期。
- confirmation sheet：联系孩子、测试联系人、标记误报、删除事件。
- success toast：已处理、已联系、已标记误报。
- error toast：通知失败、联系人不可达、设备离线。

### 3.4 管理设备

```text
我的
  -> 设备与规则
  -> 设备管理
  -> 设备详情
  -> 修改名称/房间/视角
  -> 网络状态/固件升级/隐私模式
  -> 解绑或转移设备
```

关键状态：

- default：设备在线，显示固件、网络、隐私模式。
- offline：只保留本地设置和重连建议。
- updating：固件升级进度，不允许解绑或断电操作。
- abnormal：摄像头、麦克风、扬声器、网络异常。
- confirmation sheet：解绑、转移、重启。
- success toast：保存成功、校准完成、升级完成。

### 3.5 配置 AI 规则

```text
我的
  -> 设备与规则
  -> 对话与人设 / AI 规则
  -> 设置唤醒名、声线、自由聊天时长
  -> 设置作业模式、睡前限制、记录策略
  -> 保存
  -> 进入隐私与权限复核
```

关键状态：

- default：显示当前规则。
- validation error：时长过长、免打扰冲突、逐字记录未确认。
- permission denied：非管理员不可改。
- success toast：规则已保存。
- warning sheet：开启逐字记录、放宽睡前聊天、关闭作业限制时需要确认。

### 3.6 创建任务

```text
中置 +
  -> 创建任务 action sheet
  -> 选择普通任务 / 小书包 / 睡前任务 / 打卡任务 / 奖励规则
  -> 选择日期
  -> 填写任务名称、时间、检测方式、提醒方式、证据要求
  -> 保存
  -> 任务详情 / 当天任务列表
```

关键状态：

- disabled：未选日期或必填字段为空。
- validation error：结束时间早于开始时间、奖励数量无效。
- loading：保存中。
- success toast：任务已创建。
- error toast：设备离线时保存到 App，待设备上线同步。

### 3.7 处理任务证据

```text
首页待处理 / 任务详情 / 日报
  -> 任务证据详情
  -> 查看截图、AI 判断、置信度、触发规则
  -> 确认完成 / 部分完成 / 驳回
  -> 奖励流水和日报更新
```

关键状态：

- pending：等待家长确认。
- confirmed：确认完成。
- partial：部分完成。
- rejected：驳回 AI 判断。
- revoked：撤销自动加分。

### 3.8 处理奖励申请

```text
首页待处理 / 奖励商店 / 积分页
  -> 奖励申请 sheet
  -> 查看申请来源和当前余额
  -> 同意并兑现 / 同意稍后 / 暂不兑换
  -> 更新积分流水和兑现记录
```

关键状态：

- requested：待确认。
- fulfilled：已兑现并扣除。
- planned：已同意稍后提醒。
- rejected：暂不兑换并温和反馈给孩子。
- insufficient：余额不足，不能确认兑换。

## 4. 页面状态矩阵

状态定义：

| 状态 | 含义 |
|---|---|
| `default` | 页面正常展示可操作内容 |
| `loading` | 拉取数据、连接设备、保存中 |
| `empty` | 当前模块没有数据 |
| `error` | 网络、服务端、保存、加载失败 |
| `success` | 操作完成后的页面/局部反馈 |
| `permission denied` | 角色、系统权限或隐私授权不足 |
| `no result` | 搜索/筛选后无匹配 |
| `offline` | 设备离线 |
| `abnormal` | 安全、健康、设备、行为异常 |
| `updating` | 固件、配置或规则同步中 |

### 4.1 Onboarding 状态矩阵

| 页面 | default | loading | empty/no result | error | success | permission denied | device state |
|---|---|---|---|---|---|---|---|
| 欢迎页 | 产品价值和开始按钮 | 初始化配置 | N/A | 配置失败 | 进入登录 | N/A | N/A |
| 登录注册 | 手机号、验证码 | 发送验证码、登录中 | N/A | 验证码错误、手机号无效 | 登录成功 | N/A | N/A |
| 家长身份 | 角色选择、显示名 | 保存中 | 未选角色 | 保存失败 | 进入绑定 | N/A | N/A |
| 扫码绑定 | 扫码框、蓝牙发现 | 扫码识别、蓝牙扫描 | 未发现设备 | 二维码无效 | 进入配网 | 相机权限拒绝 | 设备待配网 |
| Wi-Fi 配网 | SSID、密码 | 配网中 | 未发现网络 | 密码错误、超时 | 绑定成功 | N/A | 弱网、配网失败 |
| 绑定成功 | 设备成功卡 | 同步设备信息 | N/A | 同步失败 | 进入孩子档案 | N/A | 在线/待校准 |
| 孩子档案 | 表单 | 保存中 | N/A | 字段错误 | 保存成功 | 无权编辑 | N/A |
| 摄像头命名 | 唤醒名、试听 | 保存/试听 | N/A | 识别失败 | 命名成功 | 麦克风权限拒绝 | 设备未连接时只保存 App |
| 紧急联系人 | 联系人列表 | 邀请中 | 暂无联系人 | 邀请失败 | 联系人已添加 | 无通讯录权限 | N/A |
| 权限引导 | 通知/相机/麦克风说明 | 请求权限 | N/A | 权限请求失败 | 授权完成 | 权限拒绝 | N/A |

### 4.2 首页与任务状态矩阵

| 页面 | default | loading | empty | error | success | permission denied | no result | device state |
|---|---|---|---|---|---|---|---|---|
| 首页 | 当前状态、下一步、待处理 | 拉取家庭状态 | 未绑定设备/无孩子档案 | 首页加载失败 | 处理完成后刷新 | 临时查看者只读 | N/A | offline、abnormal、privacy mode、updating |
| 协作待办 | 待处理队列 | 加载待办 | 无待处理 | 加载失败 | 已处理 | 无权处理 | 筛选无结果 | 设备离线时标记不可远程提醒 |
| 任务首页 | 日期条、任务列表 | 加载任务 | 当天无任务 | 加载失败 | 新建/修改成功 | 无权编辑 | 筛选无结果 | offline 时可编辑但待同步 |
| 创建任务 sheet | 类型选择/表单 | 保存中 | 模板为空 | 保存失败 | 任务已创建 | 无权创建 | N/A | offline 待同步、updating 禁止设备提醒 |
| 任务模板 | 推荐模板 | 加载推荐 | 暂无推荐 | 生成失败 | 套用成功 | 无权启用 | 搜索无结果 | N/A |
| 任务详情 | 任务信息、证据 | 加载详情 | 证据为空 | 加载失败 | 修改成功 | 无权改判 | N/A | offline 不能发送提醒 |
| 专注计时 | 倒计时、观察状态 | 同步计时 | 无进行中任务 | 同步失败 | 暂停/延后/结束成功 | 无权控制 | N/A | offline、abnormal |
| 小书包 | 清单、规则、状态 | 生成清单 | 无明日物品 | 生成失败 | 添加/标记成功 | 无权编辑 | 筛选无结果 | offline 时摄像头不能语音提醒 |
| 睡眠晨起 | 睡前任务、闹铃 | 加载睡眠数据 | 无睡眠记录 | 加载失败 | 设置保存 | 无权编辑 | N/A | offline、abnormal、夜间免打扰 |

### 4.3 看护与安全状态矩阵

| 页面 | default | loading | empty | error | success | permission denied | no result | device state |
|---|---|---|---|---|---|---|---|---|
| 实时看护 | 实时画面、通话、截图 | 连接中 | 无可用画面 | 连接失败 | 截图/提醒/通话成功 | 角色无权、系统权限拒绝 | N/A | offline、privacy mode、weak network、reconnecting、updating |
| 事件回放 | 片段列表 | 加载片段 | 无事件 | 加载失败 | 收藏/分享/删除成功 | 无权查看 | 筛选无结果 | offline 不影响历史片段 |
| 安全区域 | 区域列表 | 加载区域 | 无区域 | 保存失败 | 区域已启用 | 无权编辑 | N/A | offline 时只保存规则 |
| 安全事件中心 | 今日安全摘要 | 加载事件 | 无事件 | 加载失败 | 事件处理成功 | 无权处理 | 筛选无结果 | abnormal、offline |
| 安全事件详情 | 证据、规则、操作 | 拉取证据 | 证据缺失 | 证据加载失败 | 已联系/已处理/误报 | 无权查看 | N/A | abnormal、offline、weak network |
| 音频通话 sheet | 通话确认 | 发起中 | N/A | 呼叫失败 | 正在通话 | 隐私模式/无权 | N/A | offline、privacy mode |

### 4.4 我的与设置状态矩阵

| 页面 | default | loading | empty | error | success | permission denied | no result | device state |
|---|---|---|---|---|---|---|---|---|
| 我的总览 | 家庭账户、常用入口 | 加载账户 | 无家庭 | 加载失败 | 保存后返回 | N/A | N/A | 设备状态摘要 |
| 个人信息 | 家长资料表单 | 保存中 | N/A | 保存失败 | 个人信息已保存 | N/A | N/A | N/A |
| 账号安全 | 手机号、登录设备 | 加载设备 | 无其他设备 | 加载失败 | 已移除/已更换 | N/A | N/A | N/A |
| 订阅套餐 | 当前套餐、权益 | 加载权益 | 无订阅记录 | 支付/加载失败 | 套餐已更新 | N/A | N/A | N/A |
| 日报 | 今日结论、指标、证据 | 生成中 | 当天无记录 | 生成失败 | 报告已生成 | 无权查看 | N/A | offline 影响实时数据但不影响历史 |
| 周报 | 趋势、建议 | 生成中 | 本周无记录 | 生成失败 | 周报已生成 | 无权查看 | N/A | N/A |
| 成长时刻 | 精选片段 | 加载片段 | 暂无收藏 | 加载失败 | 收藏/隐藏/删除成功 | 无权查看 | 筛选无结果 | N/A |
| 积分总览 | 余额、流水、阶段 | 加载流水 | 暂无积分 | 加载失败 | 兑换/撤销成功 | 无权调整 | 筛选无结果 | N/A |
| 奖励商店 | 奖品、申请 | 加载奖品 | 无奖品 | 保存失败 | 奖励已添加/修改 | 无权管理 | 搜索无结果 | N/A |
| 打卡审核 | 素材待审 | 加载素材 | 无待审素材 | 加载失败 | 通过/重拍成功 | 无权审核 | 筛选无结果 | N/A |
| 对话与人设/AI 规则 | 当前规则 | 加载规则 | N/A | 保存失败 | 规则已保存 | 非管理员不可改 | N/A | offline 待同步、updating |
| 隐私与权限 | 隐私开关、数据权利 | 加载设置 | N/A | 保存失败 | 设置已保存 | 无权删除数据 | N/A | privacy mode、offline |
| 家庭成员 | 成员列表 | 加载成员 | 只有当前用户 | 邀请失败 | 权限已更新 | 无权管理 | 搜索无结果 | N/A |
| 设备管理 | 设备详情 | 加载设备 | 未绑定设备 | 操作失败 | 校准/保存成功 | 无权解绑 | N/A | offline、abnormal、updating |
| 通知设置 | 推送开关 | 加载设置 | N/A | 保存失败 | 设置已保存 | 系统通知权限拒绝 | N/A | N/A |
| 学习内容 | 小书包/合作内容 | 加载内容 | 无课程 | 加载失败 | 设置已保存 | 无权配置 | 搜索无结果 | N/A |
| 帮助反馈 | 反馈入口 | 提交中 | N/A | 提交失败 | 反馈已提交 | N/A | 搜索无结果 | N/A |
| 关于我们 | 品牌、协议、版本 | 检查更新 | N/A | 检查失败 | 已是最新 | N/A | N/A | N/A |

## 5. 关键操作交互反馈

| 操作 | pressed | loading | disabled | success toast | error toast | sheet/validation |
|---|---|---|---|---|---|---|
| 登录/验证码 | 按钮轻压 | 发送中、倒计时 | 手机号不合法 | 验证码已发送 | 验证码错误 | 字段下提示 |
| 扫码绑定 | 扫码框反馈 | 识别中 | 无相机权限 | 已识别设备 | 二维码无效 | 权限说明 sheet |
| Wi-Fi 配网 | 开始按钮轻压 | 配网进度 | 密码为空 | 设备绑定成功 | 密码错误/超时 | 表单校验 |
| 创建任务 | 中置 + pressed | 保存中 | 未选日期/必填缺失 | 任务已创建 | 保存失败/待同步 | action sheet + validation |
| 套用模板 | 模板卡 pressed | 套用中 | 未选日期 | 已套用模板 | 套用失败 | 选择日期 sheet |
| 任务证据处理 | 操作按钮 pressed | 保存判定 | 已处理不可重复 | 已确认/已驳回 | 保存失败 | confirmation sheet |
| 延后/提醒/跳过任务 | 按钮 pressed | 发送中 | 设备离线不可提醒 | 已延后/已提醒 | 摄像头离线 | action sheet |
| 实时看护截图 | 图标 pressed | 保存中 | 无画面 | 截图已保存 | 保存失败 | N/A |
| 音频通话 | 通话按钮 pressed | 呼叫中 | 隐私模式/无权限 | 正在发起通话 | 呼叫失败 | confirmation sheet |
| 安全事件处理 | 危险按钮 pressed | 提交中 | 已处理 | 已标记处理 | 通知失败 | confirmation sheet |
| 奖励申请 | 按钮 pressed | 处理中 | 积分不足 | 已兑现/已安排 | 处理失败 | confirmation sheet |
| 积分规则保存 | 按钮 pressed | 保存中 | 阈值无效 | 阶段规则已保存 | 保存失败 | inline validation |
| 添加奖品 | 按钮 pressed | 保存中 | 名称/数量为空 | 奖励已添加 | 保存失败 | form validation |
| 小书包标记 | chip pressed | 保存中 | 无权编辑 | 已标记 | 保存失败 | N/A |
| 设置开关 | toggle pressed | 同步中 | 无权修改 | 设置已保存 | 同步失败 | warning sheet for risky toggles |
| 删除数据 | danger pressed | 提交中 | 非管理员 | 已提交删除申请 | 提交失败 | danger confirmation |
| 解绑设备 | danger pressed | 校验中 | 固件升级中 | 已进入管理员确认 | 解绑失败 | danger confirmation |

Toast 文案规则：

- 成功 toast：短句，例如 `任务已创建`、`规则已保存`。
- 错误 toast：说明原因和下一步，例如 `设备离线，已保存到 App，摄像头上线后同步`。
- 安全类 toast 不应轻描淡写，必须保留可追溯处理记录。

## 6. 全局组件状态

### 6.1 Navigation

| 组件 | 状态 | 规则 |
|---|---|---|
| 底部 tab | selected | icon + label 使用 `accent`，可用浅色胶囊背景 |
| 底部 tab | unselected | icon + label 使用 `muted` |
| 中置创建按钮 | default | 圆形主按钮，使用 `accent` |
| 中置创建按钮 | pressed | 轻微缩放或降低亮度，不改变布局 |
| 中置创建按钮 | loading | 打开 sheet 前短暂 progress，避免重复点击 |
| 中置创建按钮 | disabled | onboarding、登录、权限阻断页不展示或不可点 |
| tab badge | unread/alert | 只用于待处理、安全告警、任务确认 |

### 6.2 Buttons

| 状态 | 视觉/交互 |
|---|---|
| default | 高对比、明确 hit area |
| pressed | 80-120ms 压低/变暗 |
| disabled | 低对比但可读，说明原因 |
| loading | spinner + 禁止重复提交 |
| success | 短暂成功态或 toast |
| danger | `danger` 色，只用于删除、解绑、告警升级 |

### 6.3 Cards / List items

| 状态 | 适用 |
|---|---|
| default | 普通任务、报告、设备、奖励 |
| pressed | 点击态 |
| selected | 日期、筛选、模板、视角 |
| unread | 新告警、新待办 |
| pending review | 任务证据、打卡素材、奖励申请 |
| resolved | 已处理事件 |
| warning | 延后、待确认、弱网 |
| danger | 安全告警、删除 |
| offline | 设备不可用 |
| skeleton | 加载态 |

### 6.4 Tags / Chips

| 状态 | 用途 |
|---|---|
| default | 标签展示 |
| selected | 筛选/日期/阶段 |
| disabled | 当前不可选 |
| semantic-success | 在线、正常、已完成 |
| semantic-warning | 待确认、弱网、延后 |
| semantic-danger | 告警、危险、删除 |
| semantic-info | AI 建议、普通信息 |

### 6.5 Forms

| 状态 | 规则 |
|---|---|
| default | label 明确，字段可编辑 |
| focused | 明确 focus ring |
| filled | 保持可读 |
| error | 字段下内联提示 |
| disabled | 说明不可编辑原因 |
| saving | 表单锁定，按钮 loading |
| saved | toast + 返回或留在页面 |
| dirty | 离开页面前需要确认 |

### 6.6 Search / Filter / Sort

| 状态 | 规则 |
|---|---|
| empty query | 展示默认列表 |
| typing | debounce，不阻塞输入 |
| loading | 局部 skeleton |
| no result | 明确显示无匹配并提供清除筛选 |
| active filter | chip 显示已选条件 |
| clearable | 一键清除 |
| sort changed | 列表稳定重排，不跳动 |

## 7. 高保真页面与组件状态拆分

### 7.1 必须做独立高保真页面

- 欢迎页
- 登录注册
- 扫码绑定
- Wi-Fi 配网 loading/error
- 绑定成功
- 孩子档案
- 摄像头命名
- 首页 default
- 首页 abnormal/待处理
- 任务首页 default
- 创建任务 sheet
- 任务详情/证据确认
- 小书包
- 实时看护 default
- 实时看护 offline
- 实时看护 privacy mode
- 安全事件详情
- 我的总览
- 设备管理 default
- 设备管理 updating/offline
- AI 规则/对话人设
- 隐私与权限
- 日报
- 奖励申请确认

### 7.2 需要局部高保真状态

- 首页设备离线 banner。
- 首页安全异常卡。
- 任务列表 empty/no result。
- 任务保存到设备待同步。
- 专注计时 paused/delayed。
- 事件回放空状态。
- 安全区域新增 sheet。
- 通知权限拒绝。
- 角色无权操作。
- 固件升级进度。
- 积分不足。
- 奖励删除/修改 swipe action。
- 打卡通过/重拍反馈。

### 7.3 可做组件状态展示

- 按钮 default/pressed/disabled/loading/success/danger。
- Toast success/error/warning。
- 普通 skeleton loading。
- 普通 empty state。
- tag/chip selected/unselected。
- 筛选、搜索、排序。
- 表单 focused/error/disabled/saving。
- list item unread/resolved/pending。
- bottom sheet 基础样式。
- confirmation sheet 基础样式。

## 8. 设计验收清单

- 页面范围覆盖旧 HTML 的 41 个 screen 和 28 个 sheet，不遗漏业务流程。
- 视觉不沿用旧 HTML 的 CSS、Liquid Glass、蓝紫主视觉或舞台布局。
- 新视觉遵守 `app-design-brief.md` 的专业、高端、可信、效率工具方向。
- 所有设备相关页面都有 offline、abnormal、updating、privacy mode 至少一种异常状态。
- 所有数据列表都有 loading、empty、error、no result。
- 所有表单都有 validation、disabled、saving、success、error。
- 所有 AI 判断都有证据入口或触发规则说明。
- 所有危险操作都有 confirmation sheet。
- 所有安全/隐私操作有清晰说明和处理记录。
