const refs = {
  study: "./assets/generated/care-scene.png",
  room: "./assets/generated/alert-scene.png",
  desk: "./assets/generated/care-scene.png",
  device: "./assets/generated/device-setup.png",
  empty: "./assets/generated/empty-state.png",
  bedtime: "./assets/generated/care-scene.png",
};

const screen = document.getElementById("screen");
const dock = document.getElementById("dock");
const toastLane = document.getElementById("toast");
const device = document.querySelector(".mira-device");

const state = {
  view: "welcome",
  createOpen: false,
  selectedDay: "今天",
  taskFilter: "all",
  taskSearch: "",
  alertFilter: "unread",
  sheet: "",
  modal: "",
  formStatus: "default",
  setupSaving: false,
  setupError: "",
  bindingStatus: "default",
  permissionDenied: false,
  onboardingIndex: 0,
  parentRole: "妈妈",
  parentName: "妈妈",
  phone: "",
  agreed: false,
  loginError: "",
  agreementError: "",
  loginLoading: false,
  verifyPhone: "",
  verifyCode: "",
  verifyError: "",
  verifyLoading: false,
  resendLeft: 0,
  childProfile: {
    name: "小宇",
    age: "8 岁",
    relation: "妈妈",
    grade: "二年级",
    stage: "小学",
    className: "二年级 3 班",
  },
  childDraft: {
    name: "",
    age: "",
    relation: "妈妈",
    birthday: "2018-06-12",
    stage: "小学",
    grade: "二年级",
    className: "二年级 3 班",
  },
  wakeName: "米拉",
  boundaryLevel: "平衡",
  contactDraft: {
    name: "爸爸",
    phone: "13900139000",
  },
  taskDraft: {
    title: "英语朗读 10 分钟",
    start: "20:10",
    reward: "3",
  },
  selectedTaskDate: "2026-05-28",
  taskWeekOffset: 0,
  taskView: "date",
  evidenceStatus: "pending",
  rewardStatus: "requested",
  alertStatus: "unread",
  safetyStatus: "unread",
  pointBalance: 46,
  pointUnit: "积分",
  pointThreshold: 10,
  pointThresholdDraft: "10",
  milestoneHandled: false,
  manualRewardKey: "outdoor",
  rewardEditingKey: "",
  rewardDraftName: "周末一起骑车",
  rewardDraftCost: "20",
  childRewardDeducted: false,
  lastManualReward: "",
  rewardItems: [
    { key: "outdoor", title: "周末户外活动", cost: 20, desc: "和家长一起去公园或骑车", tone: "blue" },
    { key: "story", title: "睡前故事加 10 分钟", cost: 10, desc: "适合睡前流程完成后兑现", tone: "warm" },
    { key: "lego", title: "周五拼搭时间", cost: 30, desc: "需要提前安排 40 分钟", tone: "green" },
  ],
  schoolbagMode: "按课表",
  packingStatus: {
    mathbook: "done",
    bottle: "missing",
    scarf: "todo",
    pencil: "done",
  },
  packingExtra: ["美术彩纸"],
  packingDraft: "跳绳",
  settings: {
    remoteHint: true,
    privacyMask: false,
    taskEvidence: true,
    freeChatLimit: true,
    sleepDnd: true,
    reportPush: true,
    soundAlert: true,
    deviceOffline: true,
  },
};

function appHeader(kicker, title, action = "") {
  return `
    <header class="topbar app-topbar">
      <div>
        <p class="kicker">${kicker}</p>
        <h1 class="page-title">${title}</h1>
      </div>
      ${action}
    </header>
  `;
}

function backHeader(title, subtitle = "", back = "home") {
  return `
    <header class="detail-topbar">
      <button class="round-action compact" data-nav="${back}" aria-label="返回">${icon("chevron-left")}</button>
      <div>
        <h1>${title}</h1>
        ${subtitle ? `<p>${subtitle}</p>` : ""}
      </div>
    </header>
  `;
}

function stateCard(kind, title, body, action = "") {
  return `
    <section class="state-card ${kind}">
      <span class="state-icon">${icon(kind === "danger" ? "triangle-alert" : kind === "success" ? "check-circle-2" : "info", "w-5 h-5")}</span>
      <h2>${title}</h2>
      <p>${body}</p>
      ${action}
    </section>
  `;
}

function deviceStatusRows(mode = "online") {
  const rows = {
    online: [
      ["shield-check", "看护设备在线", "书房 · 电量 86% · Wi-Fi 稳定", "success"],
      ["lock-keyhole", "隐私灯开启", "远程查看时孩子端会收到提示", "ai"],
      ["refresh-cw", "固件版本 1.8.2", "已是最新版本", "info"],
    ],
    offline: [
      ["wifi-off", "设备离线", "最后在线 18:42，已保留本地任务编辑", "danger"],
      ["route", "建议检查路由器", "如果孩子端断电，任务提醒会延后同步", "warning"],
      ["clock", "历史证据可查看", "离线不影响已保存证据和日报", "info"],
    ],
    updating: [
      ["download-cloud", "固件更新中", "进度 62%，请勿断电或解绑设备", "warning"],
      ["lock", "暂不可修改设备", "更新完成后自动恢复设置入口", "info"],
    ],
  };
  return (rows[mode] || rows.online)
    .map(
      ([iconName, title, desc, tone]) => `
        <button class="settings-row ${tone}" data-toast="${title}">
          <span>${icon(iconName, "w-4 h-4")}</span>
          <div><strong>${title}</strong><small>${desc}</small></div>
          ${icon("chevron-right", "w-4 h-4")}
        </button>
      `,
    )
    .join("");
}

const fullViews = {
  setup() {
    return views.setupStart();
  },

  setupStart() {
    return `
      <section class="setup-flow">
        <div class="setup-bg" aria-hidden="true"></div>
        <header class="setup-step-head">
          <span>首次设置</span>
          <b>1 / 9</b>
        </header>
        <section class="setup-hero-panel">
          <span class="setup-icon">${icon("user-check", "w-6 h-6")}</span>
          <h1>先确认家长身份</h1>
          <p>后续绑定设备、处理告警、删除儿童数据都需要明确家庭管理员。这个身份只用于 App 内权限和通知文案。</p>
          <div class="role-grid">
            ${["妈妈", "爸爸", "祖辈", "其他家人"].map((role) => `<button class="${state.parentRole === role ? "active" : ""}" data-action="parent-role" data-role="${role}">${state.parentRole === role ? icon("check", "w-4 h-4") : ""}${role}</button>`).join("")}
          </div>
          <label class="app-field quiet">
            <span>你的称呼</span>
            <input data-parent-name maxlength="10" value="${state.parentName}" placeholder="例如：妈妈" />
          </label>
          <div class="setup-checks">
            <span>${icon("shield-check", "w-4 h-4")}手机号已验证</span>
            <span>${icon("user-round-cog", "w-4 h-4")}默认管理员</span>
          </div>
        </section>
        <section class="setup-actions">
          <button class="auth-primary" type="button" data-nav="setupDevice">继续绑定设备</button>
          <button class="auth-secondary" type="button" data-nav="home">稍后进入首页预览</button>
        </section>
      </section>
    `;
  },

  setupChild() {
    return `
      <section class="setup-flow form-flow">
        <header class="setup-step-head"><span>孩子档案</span><b>5 / 9</b></header>
        ${backHeader("孩子资料", "用于任务、证据和告警文案，后续可在我的页修改。", "setupBindDone")}
        <form class="setup-form" novalidate>
          <label class="app-field ${state.setupError ? "error" : ""}">
            <span>孩子称呼</span>
            <input data-child-name maxlength="12" value="${state.childDraft.name}" placeholder="例如：小宇" />
            ${state.setupError ? `<small>${state.setupError}</small>` : ""}
          </label>
          <div class="two-fields">
            <label class="app-field">
              <span>年龄</span>
              <input data-child-age inputmode="numeric" maxlength="2" value="${state.childDraft.age}" />
            </label>
            <label class="app-field">
              <span>学段</span>
              <input data-child-stage maxlength="8" value="${state.childDraft.stage}" />
            </label>
          </div>
          <div class="two-fields">
            <label class="app-field">
              <span>年级</span>
              <input data-child-grade maxlength="8" value="${state.childDraft.grade}" />
            </label>
            <label class="app-field">
              <span>班级</span>
              <input data-child-class maxlength="12" value="${state.childDraft.className}" />
            </label>
          </div>
          <section class="ai-bubble compact">
            <div class="ai-bubble-head">
              <span class="ai-mark">${icon("sparkles", "w-4 h-4")}</span>
              <div><strong>为什么要先建档？</strong><small>AI 只会在任务和安全事件中使用这些称呼</small></div>
            </div>
            <p>未绑定设备前，不会采集孩子画面；资料只用于后续提醒和证据归档。</p>
          </section>
          <button class="auth-primary ${state.setupSaving ? "loading" : ""}" type="button" data-save-child>
            ${state.setupSaving ? `<span class="loading-dot"></span>保存中...` : "保存并设置称呼"}
          </button>
        </form>
      </section>
    `;
  },

  setupDevice() {
    const loading = state.bindingStatus === "loading";
    const failed = state.bindingStatus === "failed";
    return `
      <section class="setup-flow">
        <header class="setup-step-head"><span>设备绑定</span><b>2 / 9</b></header>
        ${backHeader("设备绑定", "扫码或蓝牙发现设备，绑定后进入 Wi-Fi 配网。", "setupStart")}
        <section class="device-bind-card ${failed ? "failed" : loading ? "loading" : ""}">
          <div class="scan-frame">
            ${loading ? `<span class="loading-dot blue"></span>` : icon(failed ? "wifi-off" : "scan-qr-code", "w-10 h-10")}
          </div>
          <h2>${failed ? "暂未发现设备" : loading ? "正在识别设备" : "扫描设备二维码"}</h2>
          <p>${failed ? "请确认设备已通电并靠近手机，或改用蓝牙发现。" : loading ? "正在校验设备和家庭账户关系。" : "二维码通常在设备底部或包装盒内。也可以使用蓝牙发现。"}</p>
          <div class="chip-row center">
            <button class="chip primary" data-start-binding>${loading ? "识别中" : "开始绑定"}</button>
            <button class="chip" data-bind-fail>模拟失败</button>
          </div>
        </section>
        <section class="mini-list">
          ${deviceStatusRows(failed ? "offline" : "online")}
        </section>
      </section>
    `;
  },

  setupWifi() {
    return `
      <section class="setup-flow form-flow">
        <header class="setup-step-head"><span>Wi-Fi 配网</span><b>3 / 9</b></header>
        ${backHeader("连接家庭网络", "已发现设备：书房摄像头 M1。", "setupDevice")}
        <form class="setup-form" novalidate>
          <label class="app-field"><span>家庭 Wi-Fi</span><input value="Home_5G" /></label>
          <label class="app-field"><span>Wi-Fi 密码</span><input type="password" value="guardian2026" /></label>
          <section class="ai-bubble compact">
            <div class="ai-bubble-head"><span class="ai-mark">${icon("lock-keyhole", "w-4 h-4")}</span><div><strong>连接前不会开启看护</strong><small>设备只会完成网络校验和隐私灯测试</small></div></div>
            <p>配网成功后会检测隐私灯、提示音和摄像头视角，确认后再创建孩子档案。</p>
          </section>
          <button type="button" class="auth-primary" data-nav="setupBindDone" data-toast="设备已连接 Home_5G">开始配网</button>
        </form>
      </section>
    `;
  },

  setupBindDone() {
    return `
      <section class="setup-flow">
        <header class="setup-step-head"><span>绑定完成</span><b>4 / 9</b></header>
        <section class="done-card">
          <img class="setup-result-image" src="${refs.device}" alt="摄像头连接成功的柔和插画" />
          <span class="done-icon">${icon("check", "w-8 h-8")}</span>
          <h1>设备已绑定</h1>
          <p>隐私灯和提示音测试通过。接下来创建孩子档案，任务、证据和告警都会按孩子资料归档。</p>
          <div class="setup-checks">
            <span>${icon("wifi", "w-4 h-4")}网络稳定</span>
            <span>${icon("lightbulb", "w-4 h-4")}隐私灯正常</span>
            <span>${icon("camera", "w-4 h-4")}视角待校准</span>
          </div>
          <button class="auth-primary" data-nav="setupChild">创建孩子档案</button>
        </section>
      </section>
    `;
  },

  setupPermissions() {
    return `
      <section class="setup-flow">
        <header class="setup-step-head"><span>权限授权</span><b>8 / 9</b></header>
        ${backHeader("权限授权", "只开启必要权限，家长可随时在设置里修改。", "setupContacts")}
        <section class="permission-stack">
          <button class="permission-card success" data-permission="notice">
            <span>${icon("bell-ring", "w-5 h-5")}</span>
            <div><strong>通知提醒</strong><small>任务完成、告警和奖励申请需要推送</small></div>
            <b>已允许</b>
          </button>
          <button class="permission-card ${state.permissionDenied ? "danger" : ""}" data-permission="camera">
            <span>${icon("camera", "w-5 h-5")}</span>
            <div><strong>相机 / 相册</strong><small>用于扫码绑定和保存必要证据</small></div>
            <b>${state.permissionDenied ? "已拒绝" : "去授权"}</b>
          </button>
          <button class="permission-card" data-permission="mic">
            <span>${icon("mic", "w-5 h-5")}</span>
            <div><strong>麦克风</strong><small>仅在你主动发起通话时使用</small></div>
            <b>按需开启</b>
          </button>
        </section>
        ${state.permissionDenied ? stateCard("danger", "权限被拒绝", "可以继续进入 App，但扫码、通话和证据保存会受限。", `<button class="auth-secondary" data-toast="已打开系统权限说明">查看解决方法</button>`) : ""}
        <button class="auth-primary setup-fixed" data-nav="setupPrivacy">继续隐私说明</button>
      </section>
    `;
  },

  setupName() {
    return `
      <section class="setup-flow form-flow">
        <header class="setup-step-head"><span>AI 称呼与边界</span><b>6 / 9</b></header>
        ${backHeader("设置设备称呼", "孩子端唤醒和互动边界后续可修改。", "setupChild")}
        <form class="setup-form" novalidate>
          <label class="app-field">
            <span>孩子呼叫设备时使用</span>
            <input data-wake-name maxlength="8" value="${state.wakeName}" />
          </label>
          <section class="filter-row boundary-row" aria-label="互动边界">
            ${["宽松", "平衡", "严格"].map((level) => `<button type="button" class="${state.boundaryLevel === level ? "active" : ""}" data-action="boundary-level" data-level="${level}">${level}</button>`).join("")}
          </section>
          <section class="ai-bubble compact">
            <div class="ai-bubble-head"><span class="ai-mark">${icon("shield-check", "w-4 h-4")}</span><div><strong>默认互动边界</strong><small>${state.boundaryLevel}模式</small></div></div>
            <p>作业模式只允许任务相关问答；睡前关闭长时间自由聊天；普通闲聊默认只保存主题摘要。</p>
            <div class="chip-row"><button class="chip" type="button" data-sheet="boundaries">查看边界说明</button></div>
          </section>
          <button class="auth-primary" type="button" data-nav="setupContacts">继续设置联系人</button>
        </form>
      </section>
    `;
  },

  setupContacts() {
    return `
      <section class="setup-flow form-flow">
        <header class="setup-step-head"><span>紧急联系人</span><b>7 / 9</b></header>
        ${backHeader("添加紧急联系人", "安全事件只在必要时通知家庭成员。", "setupName")}
        <form class="setup-form" novalidate>
          <label class="app-field"><span>联系人</span><input data-contact-name maxlength="10" value="${state.contactDraft.name}" /></label>
          <label class="app-field"><span>手机号</span><input data-contact-phone inputmode="numeric" maxlength="11" value="${state.contactDraft.phone}" /></label>
          <section class="mini-list">
            <button type="button" class="settings-row" data-sheet="contact"><span>${icon("user-plus", "w-4 h-4")}</span><div><strong>再添加一位联系人</strong><small>例如外婆、爸爸或其他家人</small></div>${icon("chevron-right", "w-4 h-4")}</button>
            <button type="button" class="settings-row" data-toast="邀请已生成"><span>${icon("send", "w-4 h-4")}</span><div><strong>邀请另一位家长</strong><small>可处理告警和查看日报</small></div>${icon("chevron-right", "w-4 h-4")}</button>
          </section>
          <button class="auth-primary" type="button" data-nav="setupPermissions">继续权限授权</button>
        </form>
      </section>
    `;
  },

  setupPrivacy() {
    return `
      <section class="setup-flow">
        <header class="setup-step-head"><span>隐私边界</span><b>9 / 9</b></header>
        ${backHeader("隐私边界", "看护不是全天监控，孩子端会看到远程查看提示。", "setupPermissions")}
        <section class="privacy-principles">
          <div><span>${icon("eye-off", "w-5 h-5")}</span><strong>不保存全天录像</strong><p>只围绕任务证据和安全事件保留必要片段。</p></div>
          <div><span>${icon("lightbulb", "w-5 h-5")}</span><strong>远程查看有提示</strong><p>看护开启时设备端会亮起隐私灯和提示音。</p></div>
          <div><span>${icon("user-check", "w-5 h-5")}</span><strong>关键判断由家长确认</strong><p>AI 只做建议，完成、误报、奖励都需要你确认。</p></div>
        </section>
        <button class="auth-primary setup-fixed" data-nav="setupDone">同意并完成设置</button>
      </section>
    `;
  },

  setupDone() {
    return `
      <section class="setup-flow">
        <section class="done-card">
          <span class="done-icon">${icon("check", "w-8 h-8")}</span>
          <h1>家庭看护已准备好</h1>
          <p>${childName()} 的任务、看护和安全提醒已经可以开始使用。你仍然可以在“我的”里修改设备和隐私规则。</p>
          <button class="auth-primary" data-nav="home">进入首页</button>
        </section>
      </section>
    `;
  },

  homeLoading() {
    return `
      <section class="scene app-page">
        ${appHeader("同步家庭状态", "正在整理今天要看的事")}
        <div class="skeleton-hero"></div>
        <div class="skeleton-list">${Array.from({ length: 4 }).map(() => `<span></span>`).join("")}</div>
      </section>
    `;
  },

  homeEmpty() {
    return `
      <section class="scene app-page">
        ${appHeader("今日概览", "还没有家庭看护数据", `<button class="round-action" data-nav="setupStart">${icon("plus")}</button>`)}
        ${stateCard("info", "先绑定设备并创建孩子档案", "绑定后，这里会显示当前状态、待处理事项、今日任务和设备隐私摘要。", `<button class="auth-primary" data-nav="setupStart">开始设置</button>`)}
        <section class="empty-suggestions">
          <button data-nav="setupChild">${icon("user-round-plus", "w-4 h-4")}创建孩子档案</button>
          <button data-nav="setupDevice">${icon("camera", "w-4 h-4")}绑定设备</button>
          <button data-nav="setupPermissions">${icon("bell-ring", "w-4 h-4")}开启通知</button>
        </section>
      </section>
    `;
  },

  homeOffline() {
    return `
      <section class="scene app-page">
        ${appHeader("今日概览", "设备离线，先看摘要", `<button class="round-action notice-dot" data-nav="alerts">${icon("bell")}</button>`)}
        ${stateCard("danger", "书房摄像头已离线", "最后在线 18:42。任务计划仍可编辑，证据和实时提醒会在设备上线后同步。", `<button class="auth-primary" data-nav="deviceSettings">查看重连步骤</button>`)}
        <section class="priority-panel">
          <div class="section-head compact"><div><span class="mini-kicker">离线可用</span><h3>你仍然可以处理这些事</h3></div></div>
          <button class="queue-item" data-nav="taskEvidence"><span class="queue-icon">${icon("file-check-2", "w-4 h-4")}</span><span class="queue-copy"><strong>查看已保存任务证据</strong><small>离线不影响历史证据和日报</small></span>${icon("chevron-right", "w-4 h-4")}</button>
          <button class="queue-item" data-nav="taskEdit"><span class="queue-icon warm">${icon("calendar-plus", "w-4 h-4")}</span><span class="queue-copy"><strong>编辑明天任务</strong><small>设备上线后自动同步提醒</small></span>${icon("chevron-right", "w-4 h-4")}</button>
        </section>
      </section>
    `;
  },

  homeError() {
    return `
      <section class="scene app-page">
        ${appHeader("今日概览", "加载失败")}
        ${stateCard("danger", "家庭状态暂时无法加载", "网络请求失败。你可以重试，或直接进入任务与设置查看本地缓存。", `<div class="chip-row center"><button class="chip primary" data-toast="正在重新加载">重试</button><button class="chip" data-nav="tasks">去任务</button></div>`)}
      </section>
    `;
  },

  unauthorized() {
    return `
      <section class="scene app-page">
        ${appHeader("权限受限", "当前角色不能处理这项操作")}
        ${stateCard("warning", "仅管理员可修改设备与隐私规则", "你可以查看家庭摘要和日报，但不能解绑设备、删除儿童数据或修改 AI 规则。", `<button class="auth-primary" data-nav="familySettings">查看成员权限</button>`)}
      </section>
    `;
  },

  permissionDenied() {
    return `
      <section class="scene app-page">
        ${appHeader("系统权限未开启", "部分功能暂不可用")}
        ${stateCard("danger", "相机或通知权限被拒绝", "扫码绑定、通话和安全推送会受影响。可以继续使用任务编辑和历史证据。", `<button class="auth-primary" data-nav="setupPermissions">重新查看权限说明</button>`)}
      </section>
    `;
  },

  bindingFailed() {
    return `
      <section class="scene app-page">
        ${appHeader("绑定失败", "没有发现可用设备")}
        ${stateCard("danger", "设备未进入配网模式", "请确认设备已通电、靠近手机，并长按配网键 5 秒后重试。", `<div class="chip-row center"><button class="chip primary" data-nav="setupDevice">重新绑定</button><button class="chip" data-toast="已切换蓝牙发现">蓝牙发现</button></div>`)}
      </section>
    `;
  },

  deviceAbnormal() {
    return `
      <section class="scene app-page">
        ${appHeader("设备异常", "麦克风和网络需要检查")}
        ${stateCard("warning", "检测到麦克风采集异常", "实时看护画面仍可用，但异常声音告警可能延迟。建议先重启设备，再测试麦克风。", `<button class="auth-primary" data-nav="deviceSettings">进入设备管理</button>`)}
      </section>
    `;
  },

  taskDetail() {
    return `
      <section class="scene app-page">
        ${backHeader("任务详情", `${childName()} · 今天 19:30-20:00`, "tasks")}
        <section class="detail-hero soft-blue">
          <span class="capsule ai">${icon("timer", "w-3.5 h-3.5")}进行中</span>
          <h2>数学口算 20 题</h2>
          <p>AI 会在任务结束后整理完成证据，家长只需要确认，不需要一直盯屏。</p>
          <div class="progress-track"><span style="width: 68%"></span></div>
          <div class="hero-actions static">
            <button class="primary-cta" data-nav="taskEvidence">${icon("file-check-2", "w-4 h-4")}查看证据</button>
            <button class="ghost-cta" data-nav="taskEdit">${icon("pencil", "w-4 h-4")}编辑</button>
          </div>
        </section>
        <section class="ai-bubble">
          <div class="ai-bubble-head"><span class="ai-mark">${icon("sparkles", "w-4 h-4")}</span><div><strong>AI 观察摘要</strong><small>置信度 91%</small></div></div>
          <p>书桌区域连续活动，暂未检测到离席。任务结束后会生成 2 张关键截图和用时记录。</p>
          <div class="chip-row"><button class="chip primary" data-toast="已发送轻提醒">轻提醒</button><button class="chip" data-sheet="delayTask">延后 10 分钟</button></div>
        </section>
      </section>
    `;
  },

  taskEdit() {
    const saving = state.formStatus === "saving";
    const saved = state.formStatus === "saved";
    return `
      <section class="scene app-page">
        ${backHeader("创建 / 编辑任务", "任务会先保存到 App，设备在线时同步提醒。", "tasks")}
        <form class="app-form-card" novalidate>
          <label class="app-field ${state.taskDraft.title ? "" : "error"}"><span>任务名称</span><input data-task-title value="${state.taskDraft.title}" placeholder="例如：英语朗读 10 分钟" />${state.taskDraft.title ? "" : "<small>请输入任务名称</small>"}</label>
          <div class="two-fields"><label class="app-field"><span>开始时间</span><input value="${state.taskDraft.start}" /></label><label class="app-field"><span>奖励积分</span><input data-task-reward inputmode="numeric" value="${state.taskDraft.reward}" /></label></div>
          <section class="form-options">
            <button type="button" class="option-row selected" data-toast="已选择 AI 观察 + 家长确认">${icon("camera", "w-4 h-4")}AI 观察 + 家长确认</button>
            <button type="button" class="option-row" data-toast="已选择仅家长打卡">${icon("hand", "w-4 h-4")}仅家长打卡</button>
          </section>
          <button type="button" class="auth-primary ${saving ? "loading" : saved ? "success" : ""}" data-save-form="${state.taskDraft.title ? "task" : "invalid"}" ${state.taskDraft.title ? "" : "disabled"}>
            ${saving ? `<span class="loading-dot"></span>保存中...` : saved ? "已保存" : "保存任务"}
          </button>
        </form>
      </section>
    `;
  },

  taskEvidence() {
    const [label, tone] = evidenceLabel();
    return `
      <section class="scene app-page evidence-page">
        ${backHeader("任务证据", label, "taskDetail")}
        <section class="evidence-media">
          <img src="${refs.study}" alt="孩子在书桌前完成任务的证据截图" />
          <span class="capsule ${tone}">${icon("file-check-2", "w-3.5 h-3.5")}${label}</span>
        </section>
        <section class="detail-sheet inline">
          <section class="live-panel">
            <div class="ai-bubble-head"><span class="ai-mark">${icon("sparkles", "w-4 h-4")}</span><div><strong>AI 判断：完成度较高</strong><small>置信度 88% · 仍需家长确认</small></div></div>
            <p class="mt-3 text-[13px] font-semibold leading-6 text-[#697A89]">检测到书写动作持续 22 分钟，离席 1 次 40 秒。建议确认完成，并允许奖励积分自动入账。</p>
            <div class="decision-actions">
              <button class="auth-primary" data-sheet="evidence">处理证据</button>
              <button class="auth-secondary" data-sheet="partialEvidence">部分完成</button>
              <button class="danger-link" data-sheet="rejectEvidence">驳回/误报</button>
            </div>
          </section>
        </section>
      </section>
    `;
  },

  taskRunning() {
    return `
      <section class="scene app-page">
        ${backHeader("专注计时", "不鼓励一直盯屏，优先看摘要。", "tasks")}
        <section class="timer-card">
          <span>剩余</span><strong>12:08</strong><p>米拉会在任务结束后自动整理证据。</p>
          <div class="chip-row center"><button class="chip primary" data-toast="已暂停任务">暂停</button><button class="chip" data-sheet="delayTask">延后</button><button class="chip danger" data-sheet="endTask">结束</button></div>
        </section>
      </section>
    `;
  },

  taskReward() {
    const [label, tone] = rewardLabel();
    return `
      <section class="scene app-page">
        ${backHeader("奖励申请", "需要家长确认", "home")}
        ${stateCard(tone, `${childName()} 申请兑换 20 ${state.pointUnit}`, `状态：${label}。来源：本周 4 次任务完成。当前余额 ${state.pointBalance}，兑换后剩余 ${Math.max(0, state.pointBalance - 20)}。`, `<div class="chip-row center"><button class="chip primary" data-sheet="reward">处理申请</button><button class="chip" data-action="reward-planned">同意稍后</button><button class="chip danger" data-sheet="rewardReject">暂不兑换</button></div>`)}
      </section>
    `;
  },

  taskNoResult() {
    return `
      <section class="scene app-page">
        ${backHeader("任务搜索", "筛选无结果", "tasks")}
        <section class="search-card"><input data-task-search value="${state.taskSearch}" placeholder="搜索任务、模板、奖励" /><button data-toast="已清除筛选">清除</button></section>
        ${stateCard("info", "没有找到匹配任务", "可以清除筛选，或创建新的任务模板。", `<button class="auth-primary" data-nav="taskEdit">创建任务</button>`)}
      </section>
    `;
  },

  watchOffline() {
    return `
      <section class="scene app-page">
        ${backHeader("实时看护", "设备离线", "watch")}
        ${stateCard("danger", "暂时无法连接书房设备", "最后在线 18:42。你可以查看历史片段，或进入设备管理按步骤重连。", `<div class="chip-row center"><button class="chip primary" data-nav="deviceSettings">重连设备</button><button class="chip" data-nav="alerts">看历史事件</button></div>`)}
        <section class="mini-list">${deviceStatusRows("offline")}</section>
      </section>
    `;
  },

  watchAlert() {
    return `
      <section class="scene app-page evidence-page">
        ${backHeader("看护告警", "异常声音片段", "watch")}
        <section class="evidence-media danger">
          <img src="${refs.room}" alt="家庭门口和客厅区域的安全事件截图" />
          <span class="capsule danger">${icon("siren", "w-3.5 h-3.5")}19:18 异常声音</span>
        </section>
        <section class="detail-sheet inline">
          <section class="live-panel">
            <div class="ai-bubble-head"><span class="ai-mark danger">${icon("triangle-alert", "w-4 h-4")}</span><div><strong>AI 建议：先确认，不急于升级</strong><small>触发规则：门口声音 + 未见陌生人</small></div></div>
            <p class="mt-3 text-[13px] font-semibold leading-6 text-[#697A89]">片段中只检测到门口轻敲声，未检测到陌生人入画。建议联系孩子确认，再决定是否标记误报。</p>
            <div class="decision-actions"><button class="auth-primary" data-sheet="callChild">联系孩子</button><button class="auth-secondary" data-sheet="resolveAlert">标记已处理</button><button class="danger-link" data-sheet="falseAlarm">误报</button></div>
          </section>
        </section>
      </section>
    `;
  },

  watchPrivacy() {
    return `
      <section class="scene app-page">
        ${backHeader("隐私模式", "实时画面已暂停", "watch")}
        ${stateCard("info", "当前处于隐私遮罩", "孩子端开启了隐私模式，实时画面不会显示。你仍可以接收安全告警和任务摘要。", `<button class="auth-primary" data-nav="privacySettings">查看隐私规则</button>`)}
      </section>
    `;
  },

  watchUpdating() {
    return `
      <section class="scene app-page">
        ${backHeader("设备更新中", "看护暂不可用", "watch")}
        ${stateCard("warning", "固件更新 62%", "更新期间暂停实时画面、通话和解绑操作。预计 4 分钟后恢复。", `<button class="auth-secondary" data-toast="已开启完成提醒">完成后提醒我</button>`)}
        <section class="mini-list">${deviceStatusRows("updating")}</section>
      </section>
    `;
  },

  watchAbnormal() {
    return views.watchAlert();
  },

  alerts() {
    const items = [
      ["安全事件", "19:18 门口异常声音", "未读", "danger", "alertDetail"],
      ["任务提醒", "数学口算证据待确认", "处理中", "warning", "taskEvidence"],
      ["设备事件", "书房设备 18:42 离线后重连", "已读", "info", "deviceSettings"],
      ["系统通知", "隐私政策摘要已更新", "已读", "info", "privacySettings"],
    ];
    return `
      <section class="scene app-page">
        ${appHeader("消息与告警", "先处理需要判断的事", `<button class="round-action" data-toast="已全部标记已读">${icon("check-check")}</button>`)}
        <section class="filter-row" aria-label="告警筛选">
          ${["unread:未读", "processing:处理中", "resolved:已处理", "false:误报"].map((item) => {
            const [id, label] = item.split(":");
            return `<button class="${state.alertFilter === id ? "active" : ""}" data-alert-filter="${id}">${label}</button>`;
          }).join("")}
        </section>
        <section class="alert-list">
          ${items
            .map(
              ([type, title, status, tone, route]) => `
                <button class="alert-item ${tone}" data-nav="${route}">
                  <span>${icon(tone === "danger" ? "siren" : tone === "warning" ? "file-clock" : "bell", "w-4 h-4")}</span>
                  <div><small>${type} · ${status}</small><strong>${title}</strong><p>${status === "未读" ? "需要家长确认后归档。" : "已进入今日记录。"}</p></div>
                  ${icon("chevron-right", "w-4 h-4")}
                </button>
              `,
            )
            .join("")}
        </section>
      </section>
    `;
  },

  alertDetail() {
    return `
      <section class="scene app-page evidence-page">
        ${backHeader("告警详情", "安全事件 · 未读", "alerts")}
        <section class="evidence-media danger">
          <img src="${refs.room}" alt="家庭门口安全告警证据图" />
          <span class="capsule danger">${icon("siren", "w-3.5 h-3.5")}证据片段 12s</span>
        </section>
        <section class="detail-sheet inline">
          <section class="live-panel">
            <div class="ai-bubble-head"><span class="ai-mark danger">${icon("triangle-alert", "w-4 h-4")}</span><div><strong>门口异常声音</strong><small>19:18 · 触发安全边界规则</small></div></div>
            <p class="mt-3 text-[13px] font-semibold leading-6 text-[#697A89]">检测到短促敲击声，未检测到陌生人入画。系统没有自动联系紧急联系人，等待家长确认。</p>
            <ol class="timeline"><li>19:18 捕获声音片段</li><li>19:19 AI 过滤普通环境噪音</li><li>19:20 推送给家长确认</li></ol>
            <div class="decision-actions"><button class="auth-primary" data-sheet="callChild">联系孩子</button><button class="auth-secondary" data-sheet="resolveAlert">标记已处理</button><button class="danger-link" data-sheet="falseAlarm">误报</button></div>
          </section>
        </section>
      </section>
    `;
  },

  my() {
    return `
      <section class="scene app-page">
        ${appHeader("我的", "家庭账号与设置", `<button class="round-action" data-nav="alerts">${icon("bell")}</button>`)}
        <section class="family-card">
          <div><span class="avatar">${childName().slice(0, 1)}</span><div><h2>${childName()}的家庭看护</h2><p>${state.childProfile.relation} · 2 名家庭成员 · 1 台设备</p></div></div>
          <button class="chip primary" data-nav="familySettings">成员</button>
        </section>
        <section class="summary-strip app-summary">
          <button class="summary-unit" data-nav="alerts"><strong>2</strong><span>待处理</span></button>
          <button class="summary-unit" data-nav="deviceSettings"><strong>1</strong><span>设备在线</span></button>
          <button class="summary-unit" data-nav="privacySettings"><strong>3</strong><span>隐私规则</span></button>
        </section>
        <section class="settings-groups">
          <div class="settings-group"><h3>看护与规则</h3>${[
            ["deviceSettings", "camera", "设备管理", "网络、固件、解绑和房间视角"],
            ["aiRules", "bot", "AI 规则", "任务判断、自由聊天和睡前限制"],
            ["privacySettings", "lock-keyhole", "隐私与数据", "远程查看边界、数据删除"],
            ["education", "graduation-cap", "教育与内容边界", "小书包、答题边界和内容规则"],
          ].map(([route, ico, title, desc]) => `<button class="settings-row" data-nav="${route}"><span>${icon(ico, "w-4 h-4")}</span><div><strong>${title}</strong><small>${desc}</small></div>${icon("chevron-right", "w-4 h-4")}</button>`).join("")}</div>
          <div class="settings-group"><h3>报告与奖励</h3>${[
            ["report", "file-text", "今日日报", "任务完成、证据和 AI 建议"],
            ["weekly", "chart-line", "本周趋势", "专注、睡前和安全变化"],
            ["points", "badge-check", "积分与奖励", "阶段阈值、兑换和奖励商店"],
            ["moments", "sparkles", "成长时刻", "收藏、隐藏和分享积极片段"],
          ].map(([route, ico, title, desc]) => `<button class="settings-row" data-nav="${route}"><span>${icon(ico, "w-4 h-4")}</span><div><strong>${title}</strong><small>${desc}</small></div>${icon("chevron-right", "w-4 h-4")}</button>`).join("")}</div>
          <div class="settings-group"><h3>账号与通知</h3>${[
            ["notificationSettings", "bell-ring", "通知设置", "告警、任务、奖励申请"],
            ["subscription", "badge-dollar-sign", "订阅与权益", "云端报告与高级趋势"],
            ["accountSettings", "shield", "账号安全", "手机号、登录设备、退出"],
            ["helpFeedback", "message-circle", "帮助与反馈", "提交问题和查看协议"],
          ].map(([route, ico, title, desc]) => `<button class="settings-row" data-nav="${route}"><span>${icon(ico, "w-4 h-4")}</span><div><strong>${title}</strong><small>${desc}</small></div>${icon("chevron-right", "w-4 h-4")}</button>`).join("")}</div>
        </section>
      </section>
    `;
  },

  deviceSettings() {
    return `
      <section class="scene app-page">
        ${backHeader("设备管理", "书房摄像头 · 在线", "my")}
        <section class="device-card-large"><img src="${refs.desk}" alt="书房设备视角" /><div><span class="capsule blue">在线 · 38ms</span><h2>书桌视角</h2><p>隐私灯开启，远程看护会提示孩子。</p></div></section>
        <section class="settings-group">${deviceStatusRows("online")}</section>
        <section class="settings-group"><h3>设备操作</h3><button class="settings-row" data-toast="正在校准视角"><span>${icon("scan", "w-4 h-4")}</span><div><strong>校准视角</strong><small>重新确认书桌和安全区域</small></div>${icon("chevron-right", "w-4 h-4")}</button><button class="settings-row danger" data-sheet="unbindDevice"><span>${icon("unlink", "w-4 h-4")}</span><div><strong>解绑设备</strong><small>需要管理员二次确认</small></div>${icon("chevron-right", "w-4 h-4")}</button></section>
      </section>
    `;
  },

  privacySettings() {
    const saving = state.formStatus === "saving";
    return `
      <section class="scene app-page">
        ${backHeader("隐私与数据", "控制远程查看边界", "my")}
        <section class="privacy-principles app">
          <div><span>${icon("eye-off", "w-5 h-5")}</span><strong>隐私遮罩</strong><p>孩子端开启时，家长只能看到摘要和告警。</p></div>
          <div><span>${icon("database", "w-5 h-5")}</span><strong>证据最小化</strong><p>任务证据只保存关键片段，不保存全天录像。</p></div>
        </section>
        <section class="settings-group">
          <button class="settings-row" data-sheet="privacyMode"><span>${icon("lock-keyhole", "w-4 h-4")}</span><div><strong>远程查看提示</strong><small>开启中 · 设备端亮灯并提示</small></div><b class="toggle on"></b></button>
          <button class="settings-row" data-sheet="deleteData"><span>${icon("trash-2", "w-4 h-4")}</span><div><strong>删除儿童数据</strong><small>危险操作，需要管理员确认</small></div>${icon("chevron-right", "w-4 h-4")}</button>
        </section>
        <button class="auth-primary ${saving ? "loading" : ""}" data-save-form="privacy">${saving ? `<span class="loading-dot"></span>保存中...` : "保存隐私设置"}</button>
      </section>
    `;
  },

  aiRules() {
    return `
      <section class="scene app-page">
        ${backHeader("AI 规则", "AI 只能建议，关键判断由家长确认。", "my")}
        <section class="app-form-card">
          <label class="app-field"><span>自由聊天时长</span><input value="每天 20 分钟" /></label>
          <label class="app-field"><span>作业模式</span><input value="只提醒，不直接给答案" /></label>
          <button class="option-row selected" data-sheet="aiWarning">${icon("shield-alert", "w-4 h-4")}睡前 21:15 后关闭自由聊天</button>
          <button class="auth-primary" data-save-form="ai">保存 AI 规则</button>
        </section>
      </section>
    `;
  },

  familySettings() {
    return `
      <section class="scene app-page">
        ${backHeader("家庭成员", "管理员可调整查看和处理权限", "my")}
        <section class="alert-list">
          ${["妈妈 · 管理员", "爸爸 · 可处理告警", "外婆 · 仅查看日报"].map((item, index) => `<button class="alert-item" data-sheet="memberRole"><span>${icon("user-round", "w-4 h-4")}</span><div><small>家庭成员</small><strong>${item}</strong><p>${index === 0 ? "可管理设备、隐私和成员。" : "可根据权限查看任务和安全摘要。"}</p></div>${icon("chevron-right", "w-4 h-4")}</button>`).join("")}
        </section>
      </section>
    `;
  },

  notificationSettings() {
    return `
      <section class="scene app-page">
        ${backHeader("通知设置", "只推送需要家长判断的事", "my")}
        <section class="settings-group">
          ${["安全告警", "任务证据确认", "奖励申请", "设备离线", "日报生成"].map((title, index) => `<button class="settings-row" data-toast="${title} 已更新"><span>${icon(index === 0 ? "siren" : "bell-ring", "w-4 h-4")}</span><div><strong>${title}</strong><small>${index < 3 ? "立即推送" : "汇总提醒"}</small></div><b class="toggle ${index === 4 ? "" : "on"}"></b></button>`).join("")}
        </section>
      </section>
    `;
  },

  accountSettings() {
    return `
      <section class="scene app-page">
        ${backHeader("账号安全", "手机号、登录设备和退出", "my")}
        <section class="settings-group">
          <button class="settings-row" data-sheet="changePhone"><span>${icon("smartphone", "w-4 h-4")}</span><div><strong>手机号</strong><small>+86 138 0013 8000</small></div>${icon("chevron-right", "w-4 h-4")}</button>
          <button class="settings-row" data-sheet="loginDevices"><span>${icon("monitor-smartphone", "w-4 h-4")}</span><div><strong>登录设备</strong><small>当前手机 + 1 台备用设备</small></div>${icon("chevron-right", "w-4 h-4")}</button>
          <button class="settings-row danger" data-sheet="logout"><span>${icon("log-out", "w-4 h-4")}</span><div><strong>退出登录</strong><small>不会删除家庭数据</small></div>${icon("chevron-right", "w-4 h-4")}</button>
        </section>
      </section>
    `;
  },

  helpFeedback() {
    return `
      <section class="scene app-page">
        ${backHeader("帮助与反馈", "告诉我们哪里还不顺手", "my")}
        <section class="app-form-card">
          <label class="app-field"><span>反馈内容</span><textarea data-feedback placeholder="例如：设备离线时希望先看到哪些信息？"></textarea></label>
          <button class="auth-primary" data-save-form="feedback">提交反馈</button>
        </section>
        <section class="settings-group"><button class="settings-row" data-sheet="terms"><span>${icon("file-text", "w-4 h-4")}</span><div><strong>用户协议</strong><small>查看服务条款摘要</small></div>${icon("chevron-right", "w-4 h-4")}</button><button class="settings-row" data-sheet="privacyPolicy"><span>${icon("scroll-text", "w-4 h-4")}</span><div><strong>隐私政策</strong><small>儿童数据与音视频处理说明</small></div>${icon("chevron-right", "w-4 h-4")}</button></section>
      </section>
    `;
  },

  care() {
    return `
      <section class="scene app-page">
        ${appHeader("待家长处理", "只展示需要你判断的事", `<button class="round-action" data-toast="已按紧急程度排序">${icon("list-filter")}</button>`)}
        <section class="priority-panel">
          <div class="section-head compact"><div><span class="mini-kicker">今天</span><h3>4 件待处理</h3></div><button data-toast="已全部稍后提醒">稍后</button></div>
          <button class="queue-item urgent" data-nav="taskEvidence"><span class="queue-icon">${icon("file-check-2", "w-4 h-4")}</span><span class="queue-copy"><strong>数学口算证据待确认</strong><small>确认后进入日报和积分流水</small></span>${icon("chevron-right", "w-4 h-4")}</button>
          <button class="queue-item" data-nav="taskReward"><span class="queue-icon warm">${icon("gift", "w-4 h-4")}</span><span class="queue-copy"><strong>奖励申请待确认</strong><small>${childName()} 想兑换周末户外活动</small></span>${icon("chevron-right", "w-4 h-4")}</button>
          <button class="queue-item" data-nav="safetyDetail"><span class="queue-icon danger">${icon("siren", "w-4 h-4")}</span><span class="queue-copy"><strong>门口声音片段待判断</strong><small>AI 建议先联系孩子确认</small></span>${icon("chevron-right", "w-4 h-4")}</button>
          <button class="queue-item" data-sheet="boundaries"><span class="queue-icon">${icon("bot", "w-4 h-4")}</span><span class="queue-copy"><strong>AI 对话边界待确认</strong><small>睡前自由聊天限制建议开启</small></span>${icon("chevron-right", "w-4 h-4")}</button>
        </section>
        <section class="ai-bubble"><div class="ai-bubble-head"><span class="ai-mark">${icon("sparkles", "w-4 h-4")}</span><div><strong>处理建议</strong><small>先证据，再安全，再奖励</small></div></div><p>证据确认会影响积分；安全事件需要你决定处理或误报；奖励可以同意稍后兑现。</p></section>
      </section>
    `;
  },

  sleep() {
    return `
      <section class="scene app-page">
        ${backHeader("睡前与晨起流程", "减少催促，把睡前拆成可完成步骤。", "home")}
        <section class="detail-hero soft-blue">
          <span class="capsule ai">${icon("moon", "w-3.5 h-3.5")}21:10 开始</span>
          <h2>今晚睡前流程</h2>
          <p>洗漱、整理桌面、书包放门口。睡前 21:15 后自动关闭自由聊天。</p>
          <div class="progress-track"><span style="width: 35%"></span></div>
          <div class="hero-actions static"><button class="primary-cta" data-sheet="flowItem">提醒下一步</button><button class="ghost-cta" data-toast="已延后 10 分钟">延后</button></div>
        </section>
        <section class="settings-group">
          ${[
            ["check-circle-2", "洗漱", "已完成 · 家长无需处理", "success"],
            ["clock", "整理桌面", "待开始 · 预计 5 分钟", "warning"],
            ["backpack", "小书包放门口", "和小书包清单联动", "info"],
          ].map(([ico, title, desc, tone]) => `<button class="settings-row ${tone}" data-sheet="flowItem"><span>${icon(ico, "w-4 h-4")}</span><div><strong>${title}</strong><small>${desc}</small></div>${icon("chevron-right", "w-4 h-4")}</button>`).join("")}
        </section>
      </section>
    `;
  },

  flow() {
    return `
      <section class="scene app-page">
        ${backHeader("任务模板", `${state.childProfile.stage} · ${state.childProfile.grade}`, "tasks")}
        <section class="h-scroll">
          ${[
            ["book-open-check", "放学后基础流", "口算、朗读、小书包", "accent"],
            ["moon", "睡前轻任务", "洗漱、整理、阅读", ""],
            ["mic", "朗读打卡", "声音证据 + 家长抽查", ""],
          ].map(([ico, title, desc, cls]) => `<button class="template-card ${cls}" data-sheet="taskTemplates"><span class="capsule blue">${icon(ico, "w-3.5 h-3.5")}模板</span><h4>${title}</h4><p>${desc}</p></button>`).join("")}
        </section>
        <section class="ai-bubble"><div class="ai-bubble-head"><span class="ai-mark">${icon("bot", "w-4 h-4")}</span><div><strong>AI 推荐</strong><small>基于今天任务和睡前时间</small></div></div><p>建议只套用“小书包检查”，避免增加新的学习任务。</p><div class="chip-row"><button class="chip primary" data-action="day-template-apply">套用推荐</button><button class="chip" data-nav="taskEdit">手动创建</button></div></section>
      </section>
    `;
  },

  packing() {
    return `
      <section class="scene app-page">
        ${backHeader("小书包检查", `${state.schoolbagMode} · 明早 7:40 前`, "tasks")}
        <section class="detail-hero soft-blue">
          <span class="capsule warn">${icon("backpack", "w-3.5 h-3.5")}还有 2 项待确认</span>
          <h2>明天上学物品</h2>
          <p>AI 只做识别建议，缺失项需要家长或孩子最终确认。</p>
          <div class="chip-row"><button class="chip primary" data-sheet="packing">临时加一项</button><button class="chip" data-toast="已发送小书包提醒">提醒孩子</button></div>
        </section>
        <section class="settings-group">${packingRows()}</section>
        ${state.packingExtra.length ? `<section class="settings-group"><h3>临时物品</h3>${state.packingExtra.map((item, index) => `<button class="settings-row" data-action="packing-extra-remove" data-index="${index}"><span>${icon("plus-circle", "w-4 h-4")}</span><div><strong>${item}</strong><small>家长临时添加</small></div><b class="status-tag warning">移除</b></button>`).join("")}</section>` : ""}
      </section>
    `;
  },

  focus() {
    return fullViews.taskRunning();
  },

  playback() {
    return `
      <section class="scene app-page">
        ${backHeader("事件回放", "只保存任务证据和安全片段。", "watch")}
        <section class="alert-list">
          ${[
            ["数学口算证据", "20:02 · 22 分钟 · 待确认", "taskEvidence", "file-check-2"],
            ["门口声音片段", "19:18 · 12 秒 · 未升级", "safetyDetail", "siren"],
            ["书桌离席片段", "18:36 · 40 秒 · 已归档", "alertDetail", "footprints"],
          ].map(([title, desc, route, ico]) => `<button class="alert-item" data-nav="${route}"><span>${icon(ico, "w-4 h-4")}</span><div><small>回放片段</small><strong>${title}</strong><p>${desc}</p></div>${icon("chevron-right", "w-4 h-4")}</button>`).join("")}
        </section>
      </section>
    `;
  },

  zones() {
    return `
      <section class="scene app-page">
        ${backHeader("安全区域", "区域规则只用于安全提醒，不参与奖励扣减。", "watch")}
        <section class="device-card-large"><img src="${refs.room}" alt="家庭空间安全区域视角" /><div><span class="capsule blue">3 个区域</span><h2>书房与门口边界</h2><p>门口、厨房、窗边区域已启用冷却时间。</p></div></section>
        <section class="settings-group">
          ${[
            ["door-open", "门口区域", "陌生人/持续敲门 · 立即提醒", "danger"],
            ["utensils", "厨房区域", "夜间进入 · 汇总提醒", "warning"],
            ["scan", "自定义书桌区", "离开 5 分钟后提醒", "info"],
          ].map(([ico, title, desc, tone]) => `<button class="settings-row ${tone}" data-sheet="zone"><span>${icon(ico, "w-4 h-4")}</span><div><strong>${title}</strong><small>${desc}</small></div>${icon("chevron-right", "w-4 h-4")}</button>`).join("")}
        </section>
        <button class="auth-primary" data-sheet="zone">新增安全区域</button>
      </section>
    `;
  },

  safety() {
    return `
      <section class="scene app-page">
        ${backHeader("安全中心", "先确认，再升级。", "watch")}
        ${stateCard("warning", "1 条安全事件待判断", "门口短促声音，未检测到陌生人入画。AI 建议联系孩子确认。", `<div class="chip-row center"><button class="chip primary" data-nav="safetyDetail">查看事件</button><button class="chip" data-sheet="safety">测试联系人</button></div>`)}
        <section class="settings-group">
          <button class="settings-row success" data-nav="zones"><span>${icon("scan", "w-4 h-4")}</span><div><strong>安全区域</strong><small>3 个区域启用，门口规则较敏感</small></div>${icon("chevron-right", "w-4 h-4")}</button>
          <button class="settings-row" data-nav="familySettings"><span>${icon("users", "w-4 h-4")}</span><div><strong>紧急联系人</strong><small>妈妈、爸爸，外婆待邀请</small></div>${icon("chevron-right", "w-4 h-4")}</button>
        </section>
      </section>
    `;
  },

  safetyDetail() {
    return fullViews.alertDetail().replace("告警详情", "安全事件详情").replace("alerts", "safety");
  },

  report() {
    return `
      <section class="scene app-page">
        ${backHeader("今日日报", "自动汇总，不鼓励全天盯屏。", "home")}
        <section class="summary-strip app-summary"><button class="summary-unit"><strong>4</strong><span>任务</span></button><button class="summary-unit"><strong>88%</strong><span>完成度</span></button><button class="summary-unit"><strong>1</strong><span>待确认</span></button></section>
        <section class="ai-bubble"><div class="ai-bubble-head"><span class="ai-mark">${icon("sparkles", "w-4 h-4")}</span><div><strong>今日摘要</strong><small>AI 汇总 · 家长可纠错</small></div></div><p>${childName()} 晚间任务整体稳定，数学口算需要确认证据，睡前流程建议提前 10 分钟开始。</p><div class="chip-row"><button class="chip primary" data-nav="taskEvidence">确认关键证据</button><button class="chip" data-sheet="moment">收藏成长时刻</button></div></section>
        <section class="settings-group"><button class="settings-row" data-nav="weekly"><span>${icon("chart-line", "w-4 h-4")}</span><div><strong>查看周报趋势</strong><small>专注时长、任务完成、睡前稳定性</small></div>${icon("chevron-right", "w-4 h-4")}</button></section>
      </section>
    `;
  },

  weekly() {
    return `
      <section class="scene app-page">
        ${backHeader("本周趋势", "只看对家长决策有用的变化。", "report")}
        <section class="detail-hero soft-blue"><span class="capsule ai">${icon("chart-no-axes-combined", "w-3.5 h-3.5")}7 天趋势</span><h2>睡前任务更稳定</h2><p>完成率从 71% 提升到 86%，但周三设备离线导致证据缺失 1 次。</p><div class="progress-track"><span style="width: 86%"></span></div></section>
        <section class="settings-group">${["数学口算连续 4 天完成", "小书包漏带风险下降", "睡前自由聊天建议继续限制"].map((title) => `<button class="settings-row" data-toast="${title}"><span>${icon("check-circle-2", "w-4 h-4")}</span><div><strong>${title}</strong><small>已进入周报摘要</small></div>${icon("chevron-right", "w-4 h-4")}</button>`).join("")}</section>
      </section>
    `;
  },

  moments() {
    return `
      <section class="scene app-page">
        ${backHeader("成长时刻", "优先收藏积极行为。", "my")}
        <section class="alert-list">${[
          ["主动整理书桌", "今天 20:16 · 睡前流程"],
          ["完成朗读后主动复盘", "昨天 20:42 · 英语朗读"],
          ["小书包一次准备齐", "周二 21:03 · 小书包"],
        ].map(([title, desc]) => `<button class="alert-item" data-sheet="moment"><span>${icon("sparkles", "w-4 h-4")}</span><div><small>成长时刻</small><strong>${title}</strong><p>${desc}</p></div>${icon("chevron-right", "w-4 h-4")}</button>`).join("")}</section>
      </section>
    `;
  },

  points() {
    const stage = Math.floor(state.pointBalance / state.pointThreshold);
    const [status, tone] = stage > 0 && !state.milestoneHandled ? ["可兑换", "warning"] : ["继续累积", "info"];
    return `
      <section class="scene app-page">
        ${backHeader("积分与奖励", `${pointUnitAmount(state.pointBalance)} · ${status}`, "my")}
        <section class="detail-hero soft-blue">
          <span class="capsule ${tone}">${icon("badge-check", "w-3.5 h-3.5")}${state.pointUnit}阶段</span>
          <h2>${pointUnitAmount(state.pointBalance)}</h2>
          <p>每 ${state.pointThreshold} ${state.pointUnit}提醒家长选择兑换或继续累积。奖励必须由家长确认。</p>
          <div class="progress-track"><span style="width: ${Math.min(100, (state.pointBalance % state.pointThreshold) / state.pointThreshold * 100)}%"></span></div>
          <div class="hero-actions static"><button class="primary-cta" data-sheet="manualReward">家长主动兑换</button><button class="ghost-cta" data-sheet="pointRule">阶段规则</button></div>
        </section>
        ${stage > 0 && !state.milestoneHandled ? stateCard("warning", `${state.pointUnit}已积满`, "可以现在兑换奖品，也可以继续累积到更大的奖励。", `<div class="chip-row center"><button class="chip primary" data-sheet="manualReward">选择奖品</button><button class="chip" data-action="milestone-continue">继续累积</button></div>`) : ""}
        <section class="settings-group"><button class="settings-row" data-nav="reward"><span>${icon("gift", "w-4 h-4")}</span><div><strong>奖励商店</strong><small>${rewardOptions().length} 个奖品可选</small></div>${icon("chevron-right", "w-4 h-4")}</button></section>
      </section>
    `;
  },

  reward() {
    const [label, tone] = rewardLabel();
    return `
      <section class="scene app-page">
        ${backHeader("奖励商店", `${label} · 当前 ${pointUnitAmount(state.pointBalance)}`, "points")}
        ${stateCard(tone, `${childName()} 申请兑换周末户外活动`, "摄像头只转达申请，不会向孩子直接承诺奖励。", `<div class="chip-row center"><button class="chip primary" data-sheet="reward">处理申请</button><button class="chip" data-sheet="rewardEdit">新增奖励</button></div>`)}
        <section class="settings-group">
          ${rewardOptions().map((item) => `<button class="settings-row" data-action="manual-reward-open" data-reward="${item.key}"><span>${icon("gift", "w-4 h-4")}</span><div><strong>${item.title}</strong><small>${item.desc} · ${pointUnitAmount(item.cost)}</small></div><b class="status-tag info">兑换</b></button>`).join("")}
        </section>
      </section>
    `;
  },

  checkin() {
    return `
      <section class="scene app-page">
        ${backHeader("打卡审核", "家长确认后进入日报。", "tasks")}
        ${stateCard("warning", "朗读打卡待审核", "检测到 10 分钟朗读声音，但有 2 分钟背景噪音较高。", `<div class="chip-row center"><button class="chip primary" data-toast="已通过打卡">通过</button><button class="chip danger" data-toast="已要求重拍">要求重拍</button></div>`)}
      </section>
    `;
  },

  settings() {
    return fullViews.my();
  },

  conversation() {
    return fullViews.aiRules();
  },

  accountProfile() {
    return `
      <section class="scene app-page">
        ${backHeader("个人资料", "用于家庭成员和通知称呼。", "accountSettings")}
        <section class="app-form-card"><label class="app-field"><span>称呼</span><input data-parent-name value="${state.parentName}" /></label><label class="app-field"><span>家庭角色</span><input value="${state.parentRole}" /></label><button class="auth-primary" data-save-form="profile">保存资料</button></section>
      </section>
    `;
  },

  accountSecurity() {
    return fullViews.accountSettings();
  },

  subscription() {
    return `
      <section class="scene app-page">
        ${backHeader("订阅与权益", "核心看护功能不因降级失效。", "my")}
        <section class="detail-hero soft-blue"><span class="capsule blue">${icon("sparkles", "w-3.5 h-3.5")}家庭版</span><h2>云端报告高级版</h2><p>长期趋势、更多人设和多设备云备份。任务提醒、实时查看、本地日报、隐私控制仍为基础能力。</p><div class="hero-actions static"><button class="primary-cta" data-toast="已打开续费">续费</button><button class="ghost-cta" data-sheet="subscriptionDowngrade">取消或降级</button></div></section>
      </section>
    `;
  },

  education() {
    return `
      <section class="scene app-page">
        ${backHeader("教育与内容边界", "摄像头不替代家长和老师。", "my")}
        <section class="settings-group"><button class="settings-row" data-nav="packing"><span>${icon("backpack", "w-4 h-4")}</span><div><strong>小书包规则</strong><small>${state.schoolbagMode} · 按年级推荐</small></div>${icon("chevron-right", "w-4 h-4")}</button><button class="settings-row" data-nav="conversation"><span>${icon("bot", "w-4 h-4")}</span><div><strong>答题边界</strong><small>不直接给答案，只做提示</small></div>${icon("chevron-right", "w-4 h-4")}</button></section>
      </section>
    `;
  },

  feedback() {
    return fullViews.helpFeedback();
  },

  about() {
    return `
      <section class="scene app-page">
        ${backHeader("关于", "版本、原则与协议", "my")}
        <section class="settings-group"><button class="settings-row"><span>${icon("info", "w-4 h-4")}</span><div><strong>版本 0.9.2</strong><small>HTML 高保真原型</small></div></button><button class="settings-row" data-sheet="terms"><span>${icon("file-text", "w-4 h-4")}</span><div><strong>用户协议</strong><small>查看服务条款摘要</small></div>${icon("chevron-right", "w-4 h-4")}</button><button class="settings-row" data-sheet="privacyPolicy"><span>${icon("scroll-text", "w-4 h-4")}</span><div><strong>隐私政策</strong><small>儿童数据处理说明</small></div>${icon("chevron-right", "w-4 h-4")}</button></section>
      </section>
    `;
  },

};

function renderOverlay() {
  const key = state.sheet || state.modal;
  const simple = (title, body, primary = "确认", action = "", danger = false) => `
    <h2>${title}</h2>
    <p>${body}</p>
    <div class="sheet-actions">
      <button class="auth-primary ${danger ? "danger" : ""}" ${action ? `data-action="${action}"` : `data-confirm="${title}"`}>${primary}</button>
      <button class="auth-secondary" data-close-layer>取消</button>
    </div>
  `;
  const contentMap = {
    createTask: `
      <h2>创建任务</h2>
      <p>选择任务类型，后续仍由家长确认是否需要证据、奖励或提醒。</p>
      <div class="sheet-actions">
        <button class="action-row" data-nav="taskEdit">${icon("check-square", "w-4 h-4")}普通任务${icon("chevron-right", "w-4 h-4")}</button>
        <button class="action-row" data-nav="packing">${icon("backpack", "w-4 h-4")}小书包${icon("chevron-right", "w-4 h-4")}</button>
        <button class="action-row" data-nav="sleep">${icon("moon", "w-4 h-4")}睡前 / 打卡${icon("chevron-right", "w-4 h-4")}</button>
        <button class="action-row" data-nav="flow">${icon("sparkles", "w-4 h-4")}AI 推荐模板${icon("chevron-right", "w-4 h-4")}</button>
      </div>
    `,
    taskTemplates: `
      <h2>套用任务模板</h2>
      <p>模板会合并到当前日期，不会覆盖你已经创建的任务。</p>
      <div class="sheet-actions">
        <button class="action-row" data-action="day-template-apply">${icon("book-open-check", "w-4 h-4")}放学后基础流<span>3 项</span></button>
        <button class="action-row" data-nav="sleep">${icon("moon", "w-4 h-4")}睡前轻任务<span>4 项</span></button>
        <button class="action-row" data-nav="packing">${icon("backpack", "w-4 h-4")}小书包检查<span>明早</span></button>
      </div>
    `,
    taskDate: `
      <h2>选择任务日期</h2>
      <p>历史日期只能查看和复制，不能新增任务。</p>
      <div class="sheet-actions">
        ${["今天", "明天", "周六", "下周一"].map((day) => `<button class="action-row" data-action="task-day" data-day-label="${day}">${icon("calendar-days", "w-4 h-4")}${day}${icon("chevron-right", "w-4 h-4")}</button>`).join("")}
      </div>
    `,
    timePicker: `
      <h2>选择开始时间</h2>
      <p>任务结束时间会按持续时长自动推算。</p>
      <div class="sheet-grid">
        ${["18:30", "19:00", "19:30", "20:10", "20:35", "21:10"].map((time) => `<button data-action="time-select" data-time="${time}">${time}</button>`).join("")}
      </div>
    `,
    confirmEvidence: simple("确认任务完成", "确认后将进入日报，并按规则发放奖励积分。", "确认完成", "evidence-confirm"),
    partialEvidence: simple("标记部分完成", "可以补充说明，避免 AI 误判影响孩子。", "标记部分完成", "evidence-partial"),
    rejectEvidence: simple("驳回 AI 判断", "本次不会发放奖励，系统会记录为一次纠错样本。", "驳回 / 误报", "evidence-reject", true),
    evidence: `
      <h2>处理任务证据</h2>
      <p>确认结果会进入日报和奖励流水。若 AI 判断不准，可以标记误判原因。</p>
      <div class="sheet-actions">
        <button class="auth-primary" data-action="evidence-confirm">确认完成</button>
        <button class="auth-secondary" data-action="evidence-partial">改为部分完成</button>
        <button class="danger-link" data-action="evidence-reject">驳回 / 误报</button>
      </div>
    `,
    delayTask: simple("延后任务", "设备在线时会同步轻提醒，处理记录会进入今日任务日志。", "延后 10 分钟", "task-delay"),
    endTask: simple("结束当前任务", "结束后会立即生成证据摘要，并进入家长确认。", "结束并生成证据", "task-end", true),
    flowItem: simple("任务操作", "对卡住的任务可以延后、提醒、完成或跳过，所有操作都会进入处理记录。", "发送温和提醒", "flow-remind"),
    sleepTask: simple("睡前 / 打卡任务", "适合整理书桌、洗漱、睡前阅读。", "进入睡前流程", "open-sleep"),
    rewardApprove: simple("同意兑现奖励", "会扣除积分并记录到奖励流水。孩子端只会收到温和确认。", "同意并兑现", "reward-fulfilled"),
    rewardReject: simple("暂不兑换", "孩子端会收到温和反馈，不显示拒绝理由。", "暂不兑换", "reward-rejected", true),
    reward: `
      <h2>确认奖励申请</h2>
      <p>${childName()} 申请兑换“周末户外活动”。当前 ${pointUnitAmount(state.pointBalance)}，该奖励需要 ${pointUnitAmount(20)}。</p>
      <div class="sheet-actions">
        <button class="auth-primary" data-action="reward-fulfilled">同意并兑现</button>
        <button class="auth-secondary" data-action="reward-planned">同意稍后</button>
        <button class="danger-link" data-action="reward-rejected">暂不兑换</button>
      </div>
    `,
    manualReward: `
      <h2>家长主动兑换</h2>
      <p>当前可用 ${pointUnitAmount(state.pointBalance)}。确认后会扣除对应${state.pointUnit}，记录到奖励流水。</p>
      <div class="sheet-actions">
        ${rewardOptions().map((item) => `<button class="action-row ${state.manualRewardKey === item.key ? "selected" : ""}" data-action="manual-reward-select" data-reward="${item.key}">${icon("gift", "w-4 h-4")}${item.title}<span>${pointUnitAmount(item.cost)}</span></button>`).join("")}
        <button class="auth-primary" data-action="manual-reward-confirm">确认兑换</button>
      </div>
    `,
    pointRule: `
      <h2>奖励阶段设置</h2>
      <p>达到阈值后提醒家长兑换或继续累积，AI 不会自动承诺奖励。</p>
      <label class="app-field quiet"><span>每个阶段需要</span><input data-point-threshold inputmode="numeric" value="${state.pointThresholdDraft}" /></label>
      <div class="sheet-grid">${["积分", "小红花", "小星星"].map((unit) => `<button class="${state.pointUnit === unit ? "active" : ""}" data-action="point-unit" data-unit="${unit}">${unit}</button>`).join("")}</div>
      <button class="auth-primary" data-action="point-rule-save">保存设置</button>
    `,
    rewardEdit: `
      <h2>${state.rewardEditingKey ? "修改奖励" : "添加奖励"}</h2>
      <label class="app-field quiet"><span>奖品名称</span><input data-reward-name value="${state.rewardDraftName}" /></label>
      <label class="app-field quiet"><span>所需${state.pointUnit}</span><input data-reward-cost inputmode="numeric" value="${state.rewardDraftCost}" /></label>
      <button class="auth-primary" data-action="reward-save">保存奖励</button>
    `,
    packing: `
      <h2>添加到小书包</h2>
      <p>${state.childProfile.stage}会按“${state.schoolbagMode}”准备，也可以临时加一项。</p>
      <label class="app-field quiet"><span>物品名称</span><input data-packing-draft value="${state.packingDraft}" /></label>
      <button class="auth-primary" data-action="packing-add">保存到小书包</button>
    `,
    boundaries: `
      <h2>默认互动边界</h2>
      <p>作业模式只允许任务相关问答；睡前限制自由聊天；普通闲聊默认只保存主题摘要。</p>
      <div class="sheet-grid">${["宽松", "平衡", "严格"].map((level) => `<button class="${state.boundaryLevel === level ? "active" : ""}" data-action="boundary-level" data-level="${level}">${level}</button>`).join("")}</div>
      <button class="auth-primary" data-nav="conversation">去设置</button>
    `,
    contact: `
      <h2>添加紧急联系人</h2>
      <label class="app-field quiet"><span>联系人</span><input data-contact-name value="${state.contactDraft.name}" /></label>
      <label class="app-field quiet"><span>手机号</span><input data-contact-phone inputmode="numeric" value="${state.contactDraft.phone}" /></label>
      <button class="auth-primary" data-confirm="联系人已添加">保存</button>
    `,
    memberRole: `
      <h2>成员权限</h2>
      <p>权限会影响是否能处理告警、解绑设备和删除儿童数据。</p>
      <div class="sheet-actions">
        ${["管理员", "监护人", "仅查看日报"].map((role) => `<button class="action-row" data-confirm="已设为${role}">${icon("user-round-cog", "w-4 h-4")}${role}${icon("chevron-right", "w-4 h-4")}</button>`).join("")}
      </div>
    `,
    zone: simple("新增安全区域", "选择摄像头视角中的区域，设置触发条件、冷却时间和通知对象。", "开始自定义框选", "zone-save"),
    moment: simple("成长时刻操作", "成长时刻优先收藏积极行为。家长可以收藏、隐藏、删除或分享给家庭成员。", "收藏", "moment-save"),
    callChild: simple("发起音频通话", "通话前设备端会提示孩子“家长正在联系你”。", "开始通话", "call-child"),
    resolveAlert: simple("标记已处理", "处理记录会进入今日安全日志，后续可在报告中查看。", "标记已处理", "alert-resolve"),
    falseAlarm: simple("标记误报", "这会帮助 AI 调整后续告警阈值，本次不会升级给紧急联系人。", "确认误报", "alert-false", true),
    safety: simple("测试紧急联系人", "测试会给管理员和第二联系人发送模拟安全通知，不会触发真实报警。", "发送测试", "safety-test"),
    privacyMode: simple("远程查看提示", "建议保持开启，让孩子知道家长正在查看。", "保持开启", "toggle-remote-hint"),
    pauseCareConfirm: simple("暂停实时看护", "暂停后不会显示实时画面，也不会保存新的实时截图；安全告警仍按隐私规则运行。", "暂停 30 分钟", "toggle-remote-hint"),
    deviceException: simple("设备异常处理", "建议先重启设备并测试麦克风。如果 5 分钟内仍异常，保留历史证据并联系家庭成员确认。", "按步骤处理", "safety-test"),
    deleteData: simple("删除儿童数据", "删除会影响报告、证据和成长时刻。安全事件只保留最小必要内容。", "提交删除申请", "delete-data", true),
    unbindDevice: simple("确认解绑设备", "解绑后无法查看实时画面和新证据。需要管理员二次确认。", "继续解绑", "unbind-device", true),
    changePhone: simple("更换手机号", "更换后用于登录、安全验证和重要通知。", "确认更换", "change-phone"),
    loginDevices: simple("登录设备", "当前手机今天 14:20 活跃；MacBook Safari 昨天 21:04 登录。", "移除非当前设备", "remove-login-device"),
    logout: simple("退出登录", "退出后不会影响设备继续执行任务和安全提醒。", "退出登录", "logout", true),
    subscriptionDowngrade: simple("取消或降级说明", "取消订阅不会影响任务提醒、实时查看、本地日报、隐私控制和儿童数据删除。", "知道了", "subscription-read"),
    terms: simple("用户协议摘要", "服务协议包含家庭成员权限、设备绑定、订阅权益、客服支持和使用边界。", "知道了"),
    privacyPolicy: simple("隐私政策摘要", "隐私政策说明儿童数据采集、保存、查看、导出和删除规则。", "知道了"),
    aiWarning: simple("确认 AI 规则变更", "放宽聊天或记录策略前需要确认边界，关键判断仍由家长处理。", "确认保存", "ai-rule-save"),
  };
  const content = contentMap[key] || simple("确认操作", "请确认是否继续。");
  const danger = ["rejectEvidence", "falseAlarm", "unbindDevice", "deleteData", "logout", "rewardReject"].includes(key);
  return `
    <div class="overlay-scrim" data-close-layer></div>
    <section class="bottom-sheet ${danger ? "danger" : ""}" role="dialog" aria-modal="true">
      <span class="sheet-handle" aria-hidden="true"></span>
      ${content}
    </section>
  `;
}

const navItems = [
  ["home", "house", "首页"],
  ["tasks", "calendar-days", "任务"],
  ["create", "plus", "创建"],
  ["watch", "video", "看护"],
  ["my", "user-round", "我的"],
];

const setupRoutes = [
  "setup",
  "setupStart",
  "setupDevice",
  "setupWifi",
  "setupBindDone",
  "setupChild",
  "setupName",
  "setupContacts",
  "setupPermissions",
  "setupPrivacy",
  "setupDone",
];

const routeGroups = {
  home: ["home", "care", "sleep", "report", "weekly", "homeEmpty", "homeOffline", "homeLoading", "homeError", "permissionDenied"],
  tasks: ["tasks", "flow", "packing", "taskDetail", "taskEdit", "taskEvidence", "taskRunning", "focus", "taskReward", "taskNoResult", "checkin"],
  watch: ["watch", "playback", "zones", "safety", "safetyDetail", "watchOffline", "watchAlert", "watchPrivacy", "watchUpdating", "watchAbnormal"],
  my: [
    "my",
    "alerts",
    "alertDetail",
    "moments",
    "points",
    "reward",
    "settings",
    "deviceSettings",
    "privacySettings",
    "aiRules",
    "conversation",
    "familySettings",
    "notificationSettings",
    "accountSettings",
    "accountProfile",
    "accountSecurity",
    "subscription",
    "education",
    "helpFeedback",
    "feedback",
    "about",
    "unauthorized",
    "bindingFailed",
    "deviceAbnormal",
  ],
};

function activeTabFor(view) {
  return Object.entries(routeGroups).find(([, routes]) => routes.includes(view))?.[0] || view;
}

function childName() {
  return state.childProfile.name || "孩子";
}

function parentLabel() {
  return state.parentName || state.parentRole || "家长";
}

function pointUnitAmount(amount) {
  return `${amount} ${state.pointUnit}`;
}

function evidenceLabel() {
  const map = {
    pending: ["待确认", "warning"],
    confirmed: ["已确认完成", "success"],
    partial: ["部分完成", "warning"],
    rejected: ["已驳回 / 误报", "danger"],
  };
  return map[state.evidenceStatus] || map.pending;
}

function rewardLabel() {
  const map = {
    requested: ["待家长确认", "warning"],
    fulfilled: ["已兑现", "success"],
    planned: ["已同意稍后兑现", "info"],
    rejected: ["暂不兑换", "danger"],
  };
  return map[state.rewardStatus] || map.requested;
}

function rewardOptions() {
  return state.rewardItems;
}

function selectedReward() {
  return rewardOptions().find((item) => item.key === state.manualRewardKey) || rewardOptions()[0];
}

function packingRows() {
  const labels = {
    mathbook: ["book-open-check", "数学本", "明天第一节数学课"],
    bottle: ["cup-soda", "水杯", "AI 未在书包侧袋识别到"],
    scarf: ["badge-check", "红领巾", "早晨出门前提醒"],
    pencil: ["pencil", "铅笔盒", "已在书桌右侧"],
  };
  const statusCopy = {
    done: ["已确认", "success"],
    missing: ["缺失", "danger"],
    todo: ["待检查", "warning"],
  };
  return Object.entries(labels)
    .map(([key, [ico, title, desc]]) => {
      const [status, tone] = statusCopy[state.packingStatus[key] || "todo"];
      return `
        <button class="settings-row ${tone}" data-action="packing-status" data-item="${key}" data-status="${state.packingStatus[key] === "done" ? "todo" : "done"}">
          <span>${icon(ico, "w-4 h-4")}</span>
          <div><strong>${title}</strong><small>${desc}</small></div>
          <b class="status-tag ${tone}">${status}</b>
        </button>
      `;
    })
    .join("");
}

const onboardingHabitAssets = {
  companion: "./assets/onboarding/generated/habit-companion-welcome.webp",
  selfStart: "./assets/onboarding/generated/habit-self-start.webp",
  lifeTable: "./assets/onboarding/generated/habit-life-table.webp",
  reward: "./assets/onboarding/generated/habit-reward-confirm.webp",
  plan: "./assets/onboarding/generated/habit-plan-rhythm.webp",
};

const onboardingSlides = [
  {
    asset: onboardingHabitAssets.companion,
    titleLines: ["把今天的", "节奏理顺"],
    description: "学习、餐桌、收纳和睡前任务会被整理好，需要你判断的事会放到前面。",
    kicker: "习惯节奏",
    support: "少催促",
    supportIcon: "volume-1",
    chips: ["自动整理", "关键在前", "少催促"],
    alt: "家长安静查看手机，孩子在书桌前自己开始写作业，米拉在旁边温和陪伴",
  },
  {
    asset: onboardingHabitAssets.selfStart,
    titleLines: ["先让孩子", "自己开始"],
    description: "AI 只给一个小动作提示，等孩子进入状态后，就安静记录进度。",
    kicker: "自启动",
    support: "低打扰",
    supportIcon: "sparkles",
    chips: ["一个动作", "低打扰", "看见进度"],
    alt: "孩子在家庭书桌前自主开始学习，旁边有柔和的习惯节奏光层",
  },
  {
    asset: onboardingHabitAssets.lifeTable,
    titleLines: ["小习惯", "也能被看见"],
    description: "吃饭收尾、小书包和玩具归位，会按家里规则拆成可完成的小步骤。",
    kicker: "生活习惯",
    support: "小步骤",
    supportIcon: "utensils",
    chips: ["餐桌收尾", "小书包", "睡前准备"],
    alt: "温暖家庭场景中，孩子完成日常习惯任务，家长无需反复催促",
  },
  {
    asset: onboardingHabitAssets.reward,
    titleLines: ["奖励这件事", "还是你决定"],
    description: "AI 只转交申请和证据，是否兑现、何时兑现，由家长最后确认。",
    kicker: "家长确认",
    support: "有边界",
    supportIcon: "shield-check",
    chips: ["证据清楚", "申请转交", "家长确认"],
    alt: "家长查看任务证据和奖励申请，AI 只提供建议，最终由家长确认",
  },
  {
    asset: onboardingHabitAssets.plan,
    titleLines: ["先设好", "今天怎么过"],
    description: "创建档案后，把任务、提醒边界和奖励规则排好，少一点临时催促。",
    kicker: "准备开始",
    support: "家长可控",
    supportIcon: "sliders-horizontal",
    chips: ["任务节奏", "提醒边界", "奖励规则"],
    alt: "家长和孩子在温暖书房中准备使用米拉设置每日习惯节奏",
  },
];

let resendTimer = null;

function digitsOnly(value) {
  return String(value || "").replace(/\D/g, "");
}

function isValidPhone(value) {
  return /^1[3-9]\d{9}$/.test(digitsOnly(value));
}

function formatPhone(value) {
  const phone = digitsOnly(value);
  if (phone.length !== 11) return phone;
  return `${phone.slice(0, 3)} ${phone.slice(3, 7)} ${phone.slice(7)}`;
}

function isKnownParent(value) {
  const phone = digitsOnly(value);
  return phone.startsWith("138") || phone.startsWith("139") || phone.endsWith("1234");
}

function clearResendTimer() {
  if (!resendTimer) return;
  clearInterval(resendTimer);
  resendTimer = null;
}

function updateResendText() {
  const resend = screen.querySelector("[data-resend-code]");
  if (!resend) return;
  const waiting = state.resendLeft > 0;
  resend.disabled = waiting;
  resend.textContent = waiting ? `${state.resendLeft}s 后重新发送` : "重新发送验证码";
}

function startResendCountdown() {
  clearResendTimer();
  state.resendLeft = 45;
  updateResendText();
  resendTimer = setInterval(() => {
    state.resendLeft = Math.max(0, state.resendLeft - 1);
    updateResendText();
    if (state.resendLeft === 0) clearResendTimer();
  }, 1000);
}

function goTo(view) {
  state.view = view;
  state.createOpen = false;
  if (view !== "verify") clearResendTimer();
  render();
}

function icon(name, cls = "") {
  return `<i data-lucide="${name}" class="${cls}"></i>`;
}

function render() {
  screen.innerHTML = views[state.view]();
  const isWelcome = state.view === "welcome";
  const isSetup = setupRoutes.includes(state.view);
  const isAuth = ["login", "verify"].includes(state.view) || isSetup;
  const isAuthEntry = ["login", "verify"].includes(state.view);
  const hideDock = isWelcome || isAuth;
  screen.classList.toggle("onboarding-port", isWelcome);
  screen.classList.toggle("auth-port", isAuth && !isSetup);
  screen.classList.toggle("setup-port", isSetup);
  device?.classList.toggle("auth-entry", isAuthEntry);
  dock.hidden = hideDock;
  dock.innerHTML = hideDock ? "" : renderDock();
  dock.classList.toggle("open", !hideDock && state.createOpen);
  if (state.sheet || state.modal) screen.insertAdjacentHTML("beforeend", renderOverlay());
  if (window.lucide) window.lucide.createIcons();
  updateResendText();
  screen.scrollTop = 0;
  history.replaceState(null, "", `#${state.view}`);
}

function renderDock() {
  return `
    <div class="create-fan" aria-hidden="${state.createOpen ? "false" : "true"}">
      <button class="fan-action" data-sheet="createTask">${icon("check-square")}</button>
      <button class="fan-action" data-nav="packing">${icon("backpack")}</button>
      <button class="fan-action" data-nav="sleep">${icon("moon")}</button>
    </div>
    <button class="create-core" aria-label="创建任务" aria-expanded="${state.createOpen}" data-create-toggle>
      ${icon("plus")}
    </button>
    <div class="nav-base">
      ${navItems
        .map(([id, iconName, label]) => {
          if (id === "create") return `<span aria-hidden="true"></span>`;
          const active = activeTabFor(state.view) === id;
          return `
            <button class="nav-btn ${active ? "active" : ""}" data-nav="${id}">
              ${icon(iconName)}
              <span>${label}</span>
            </button>
          `;
        })
        .join("")}
    </div>
    <span class="nav-home-indicator" aria-hidden="true"></span>
  `;
}

const views = {
  welcome() {
    const slide = onboardingSlides[state.onboardingIndex];
    const isLast = state.onboardingIndex === onboardingSlides.length - 1;
    const titleLines = slide.titleLines || [slide.title];
    const titleMarkup = titleLines
      .map((line, index) => `<span class="${index === titleLines.length - 1 ? "title-emphasis" : ""}">${line}</span>`)
      .join("");
    const valueChips = (slide.chips || []).map((chip) => `<span>${chip}</span>`).join("");
    return `
      <section class="onboarding-scene" aria-labelledby="welcome-title">
        <header class="onboard-top">
          <button class="onboard-skip" data-nav="login">跳过</button>
        </header>

        <section class="onboard-visual" aria-label="${slide.alt}">
          <div class="orbital-field" aria-hidden="true">
            <span class="orbit orbit-one"></span>
            <span class="orbit orbit-two"></span>
            <span class="orbit-dot dot-a"></span>
            <span class="orbit-dot dot-b"></span>
          </div>
          <span class="arc-cut arc-left" aria-hidden="true"></span>
          <span class="arc-cut arc-right" aria-hidden="true"></span>
          <div class="onboard-image-frame">
            <img class="onboard-illustration" src="${slide.asset}" alt="${slide.alt}" />
            <div class="onboard-image-glow" aria-hidden="true"></div>
            <div class="onboard-mini-rhythm" aria-hidden="true">
              <span></span><span></span><span></span>
            </div>
          </div>
          <div class="onboard-float float-status">
            ${icon(state.onboardingIndex === 3 ? "check-circle-2" : "sparkles", "w-4 h-4")}
            <span>${slide.kicker}</span>
          </div>
          <div class="onboard-float float-ai">
            ${icon(slide.supportIcon || "sparkles", "w-4 h-4")}
            <span>${slide.support}</span>
          </div>
        </section>

        <section class="onboard-copy">
          <h1 id="welcome-title">${titleMarkup}</h1>
          <p>${slide.description}</p>
          ${valueChips ? `<div class="onboard-value-row" aria-label="本页重点">${valueChips}</div>` : ""}
        </section>

        <footer class="onboard-footer">
          <div class="onboard-control-row">
            <button class="circle-nav" data-onboard="prev" ${state.onboardingIndex === 0 ? "disabled" : ""} aria-label="上一屏">
              ${icon("chevron-left", "w-5 h-5")}
            </button>
            <div class="pager-dots" aria-label="第 ${state.onboardingIndex + 1} 页，共 ${onboardingSlides.length} 页">
              ${onboardingSlides
                .map(
                  (_, index) => `
                    <button class="${index === state.onboardingIndex ? "active" : ""}" data-onboard-index="${index}" aria-label="第 ${index + 1} 屏"></button>
                  `,
                )
                .join("")}
            </div>
            <button class="circle-nav primary" data-onboard="next" aria-label="${isLast ? "开始使用" : "下一屏"}">
              ${icon(isLast ? "check" : "chevron-right", "w-5 h-5")}
            </button>
          </div>
        </footer>
      </section>
    `;
  },

  login() {
    const phoneReady = isValidPhone(state.phone);
    const canSend = phoneReady && state.agreed && !state.loginLoading;
    const agreementHint = phoneReady && !state.agreed && !state.loginLoading;
    return `
      <section class="auth-scene login-scene" aria-labelledby="login-title">
        <div class="auth-calm-space" aria-hidden="true"></div>

        <section class="auth-copy-block">
          <h1 id="login-title">用手机号继续</h1>
          <p>验证家长身份，继续设置家庭看护</p>
        </section>

        <form class="auth-form" novalidate>
          <label class="auth-field ${state.loginError ? "error" : ""}">
            <span>手机号</span>
            <div class="auth-input-shell">
              ${icon("smartphone", "w-5 h-5")}
              <input
                data-phone-input
                type="tel"
                inputmode="numeric"
                maxlength="11"
                autocomplete="tel"
                placeholder="请输入 11 位手机号"
                value="${state.phone}"
                aria-label="手机号"
              />
            </div>
            ${state.loginError ? `<small>${state.loginError}</small>` : ""}
          </label>

          <label class="auth-agreement ${state.agreementError ? "error" : ""}">
            <input data-agree type="checkbox" ${state.agreed ? "checked" : ""} />
            <span>我已阅读并同意 <button type="button" data-toast="用户协议将在正式版打开">用户协议</button> 和 <button type="button" data-toast="隐私政策将在正式版打开">隐私政策</button></span>
          </label>
          ${state.agreementError ? `<p class="form-error">${state.agreementError}</p>` : agreementHint ? `<p class="form-hint">勾选协议后即可获取验证码。</p>` : ""}

          <button class="auth-primary ${state.loginLoading ? "loading" : ""}" type="button" data-send-code ${canSend ? "" : "disabled"}>
            ${state.loginLoading ? `<span class="loading-dot"></span>获取中...` : "获取验证码"}
          </button>

          <p class="auth-footnote">未注册手机号验证后将自动创建家长账户</p>
        </form>
      </section>
    `;
  },

  verify() {
    const phone = state.verifyPhone || state.phone || "13800138000";
    const code = state.verifyCode.padEnd(6, " ");
    const canVerify = state.verifyCode.length === 6 && !state.verifyLoading;
    return `
      <section class="auth-scene verify-scene" aria-labelledby="verify-title">
        <div class="auth-calm-space verify-calm" aria-hidden="true"></div>

        <button class="auth-back" data-auth-back>
          ${icon("chevron-left", "w-4 h-4")}
        </button>

        <section class="auth-copy-block">
          <h1 id="verify-title">输入验证码</h1>
          <p>验证码已发送至 <strong>+86 ${formatPhone(phone)}</strong></p>
        </section>

        <form class="auth-form verify-form" novalidate>
          <label class="otp-wrap ${state.verifyError ? "error" : ""}">
            <input
              data-code-input
              class="otp-native"
              type="tel"
              inputmode="numeric"
              maxlength="6"
              autocomplete="one-time-code"
              value="${state.verifyCode}"
              aria-label="6 位验证码"
            />
            <span class="otp-slots" aria-hidden="true">
              ${Array.from({ length: 6 })
                .map((_, index) => `<b class="${state.verifyCode.length === index ? "active" : ""}">${code[index] === " " ? "" : code[index]}</b>`)
                .join("")}
            </span>
            ${state.verifyError ? `<small>${state.verifyError}</small>` : ""}
          </label>

          <div class="verify-meta">
            <button type="button" data-resend-code>45s 后重新发送</button>
            <span>验证码 5 分钟内有效</span>
          </div>

          <button class="auth-primary ${state.verifyLoading ? "loading" : ""}" type="button" data-verify-code ${canVerify ? "" : "disabled"}>
            ${state.verifyLoading ? `<span class="loading-dot"></span>验证中...` : "验证并继续"}
          </button>
        </form>
      </section>
    `;
  },

  setup() {
    return `
      <section class="auth-scene setup-scene" aria-labelledby="setup-title">
        <div class="auth-soft-orb" aria-hidden="true"></div>
        <section class="auth-visual compact" aria-label="账户创建成功">
          <div class="auth-device-mark">
            <span class="auth-camera">${icon("user-check", "w-6 h-6")}</span>
            <span class="auth-shield">${icon("sparkles", "w-5 h-5")}</span>
          </div>
          <div class="auth-visual-copy">
            <strong>家长账户已准备好</strong>
            <span>下一步完成家庭看护设置</span>
          </div>
        </section>
        <section class="auth-copy-block">
          <p class="auth-eyebrow">首次设置</p>
          <h1 id="setup-title">继续设置家庭看护</h1>
          <p>先绑定设备并创建孩子档案，再开启任务、看护和安全提醒。</p>
        </section>
        <div class="auth-form">
          <button class="auth-primary" type="button" data-toast="首次设置流程将在确认后补齐">开始绑定设备</button>
          <button class="auth-secondary" type="button" data-nav="home">稍后进入首页</button>
        </div>
      </section>
    `;
  },

  home() {
    return `
      <section class="scene decision-home">
        <header class="topbar">
          <div>
            <p class="kicker">周四 19:42 · 书房 · AI 看护中</p>
            <h1 class="page-title">小宇正在写数学口算</h1>
          </div>
          <button class="round-action notice-dot" data-toast="2 件待确认：证据、奖励申请" aria-label="通知">${icon("bell")}</button>
        </header>

        <section class="guardian-hero" aria-label="孩子当前状态">
          <img src="${refs.study}" alt="孩子在家中书桌前做作业的真实照片" />
          <div class="guardian-shade" aria-hidden="true"></div>
          <div class="guardian-topline">
            <span class="capsule">${icon("map-pin", "w-3.5 h-3.5")}书桌视角</span>
            <span class="capsule">${icon("wifi", "w-3.5 h-3.5")}设备在线</span>
          </div>
          <div class="guardian-verdict">
            <span class="verdict-dot"></span>
            <div>
              <strong>当前安全正常</strong>
              <small>AI 判断：连续专注 18 分钟，没有离席或异常声音</small>
            </div>
          </div>
          <div class="guardian-bottom">
            <div>
              <p class="hero-label">当前任务</p>
              <h2>数学口算 20 题</h2>
              <p>剩余 12 分钟，结束后自动生成任务证据。</p>
            </div>
            <div class="time-pill">
              <strong>12</strong>
              <span>分钟</span>
            </div>
          </div>
          <div class="hero-actions">
            <button class="primary-cta" data-nav="watch">${icon("video", "w-4 h-4")}进入实时看护</button>
            <button class="ghost-cta" data-toast="证据将在任务结束后自动汇总">${icon("file-check-2", "w-4 h-4")}查看证据</button>
          </div>
        </section>

        <section class="priority-panel" aria-label="待家长处理队列">
          <div class="section-head compact">
            <div>
              <span class="mini-kicker">第一优先级</span>
              <h3>2 件待确认</h3>
            </div>
            <button data-toast="已打开全部待确认">处理全部</button>
          </div>
          <button class="queue-item urgent" data-nav="taskEvidence">
            <span class="queue-icon">${icon("file-check-2", "w-4 h-4")}</span>
            <span class="queue-copy">
              <strong>数学口算证据即将生成</strong>
              <small>12 分钟后需要确认完成/部分完成/驳回</small>
            </span>
            ${icon("chevron-right", "w-4 h-4")}
          </button>
          <button class="queue-item" data-nav="taskReward">
            <span class="queue-icon warm">${icon("gift", "w-4 h-4")}</span>
            <span class="queue-copy">
              <strong>小宇申请兑换周末户外活动</strong>
              <small>需要你确认 20 积分奖励是否通过</small>
            </span>
            ${icon("chevron-right", "w-4 h-4")}
          </button>
          <div class="quick-row">
            <button class="chip primary" data-nav="care">处理待确认</button>
            <button class="chip" data-toast="已设置 20 分钟后提醒">稍后提醒</button>
          </div>
        </section>

        <section class="task-progress-panel" aria-label="当前任务进度">
          <div class="progress-copy">
            <span class="mini-kicker">第二优先级</span>
            <h3>任务进度 68%</h3>
            <p>还剩 12 分钟。结束后 Mira 会自动汇总关键画面、用时和离席记录。</p>
            <div class="progress-track" aria-label="任务完成 68%">
              <span style="width: 68%"></span>
            </div>
          </div>
          <button class="soft-cta dark" data-nav="tasks">${icon("calendar-days", "w-4 h-4")}下一步</button>
        </section>

        <section class="health-grid" aria-label="安全与设备摘要">
          <div class="section-head compact">
            <div>
              <span class="mini-kicker">第三优先级</span>
              <h3>安全 / 设备摘要</h3>
            </div>
          </div>
          <div class="health-cards">
            <button class="health-card ok" data-toast="安全区域正常">
              ${icon("shield-check", "w-4 h-4")}
              <strong>安全正常</strong>
              <span>无陌生人/门口异常</span>
            </button>
            <button class="health-card ok" data-toast="网络延迟 38ms">
              ${icon("signal", "w-4 h-4")}
              <strong>网络稳定</strong>
              <span>38ms · 低清稳定</span>
            </button>
            <button class="health-card privacy" data-toast="隐私灯已开启">
              ${icon("lock-keyhole", "w-4 h-4")}
              <strong>隐私灯开启</strong>
              <span>远程查看会提示孩子</span>
            </button>
            <button class="health-card warn" data-toast="19:18 门口声音已归档，未升级告警">
              ${icon("siren", "w-4 h-4")}
              <strong>最近告警 1</strong>
              <span>门口声音 · 已归档</span>
            </button>
          </div>
        </section>

        <section class="plan-panel" aria-label="今日计划与睡前提醒">
          <div class="section-head compact">
            <div>
              <span class="mini-kicker">第四优先级</span>
              <h3>今日计划</h3>
            </div>
            <button data-nav="tasks">管理</button>
          </div>
          <button class="plan-row active" data-nav="tasks">
            <span>19:30</span>
            <div>
              <strong>数学口算 20 题</strong>
              <small>进行中 · 结束后证据确认</small>
            </div>
          </button>
          <button class="plan-row" data-nav="packing">
            <span>20:35</span>
            <div>
              <strong>小书包检查</strong>
              <small>水杯、数学本、红领巾</small>
            </div>
          </button>
          <button class="plan-row bedtime" data-nav="sleep">
            <span>21:10</span>
            <div>
              <strong>睡前流程</strong>
              <small>洗漱、整理桌面、关闭自由聊天</small>
            </div>
          </button>
        </section>

        <section class="ai-bubble">
          <div class="ai-bubble-head">
            <span class="ai-mark">${icon("sparkles", "w-4 h-4")}</span>
            <div>
              <strong>米拉判断：现在不用打断孩子</strong>
              <small>AI-generated · 置信度 91%</small>
            </div>
          </div>
          <p>书桌活动连续、没有异常声音，设备在线且隐私灯开启。建议等任务结束后一次处理证据和奖励申请。</p>
          <div class="chip-row">
            <button class="chip primary" data-nav="report">查看处理建议</button>
            <button class="chip" data-toast="已标记稍后提醒">稍后提醒我</button>
          </div>
        </section>
      </section>
    `;
  },

  tasks() {
    const days = [
      ["今天", "28"],
      ["明天", "29"],
      ["周六", "30"],
      ["周日", "31"],
      ["周一", "01"],
    ];
    return `
      <section class="scene">
        <header class="topbar">
          <div>
            <p class="kicker">任务节奏</p>
            <h1 class="page-title">今天只盯关键任务</h1>
          </div>
          <button class="round-action" data-toast="模板推荐已刷新" aria-label="AI 推荐">${icon("sparkles")}</button>
        </header>

        <section class="date-strip" aria-label="日期选择">
          ${days
            .map(
              ([label, num]) => `
                <button class="day-pill ${state.selectedDay === label ? "active" : ""}" data-day="${label}">
                  <b>${num}</b>
                  <span>${label}</span>
                </button>
              `,
            )
            .join("")}
        </section>

        <section class="search-card compact-search">
          <input data-task-search value="${state.taskSearch}" placeholder="搜索任务、模板、小书包" />
          <button data-nav="${state.taskSearch ? "taskNoResult" : "flow"}">${state.taskSearch ? "搜索" : "筛选"}</button>
        </section>
        <section class="filter-row" aria-label="任务筛选">
          ${["all:全部", "todo:待做", "doing:进行中", "done:已完成"].map((item) => {
            const [id, label] = item.split(":");
            return `<button class="${state.taskFilter === id ? "active" : ""}" data-task-filter="${id}">${label}</button>`;
          }).join("")}
        </section>

        <section class="mission-hero">
          <div class="mission-top">
            <div>
              <span class="capsule ai">${icon("timer", "w-3.5 h-3.5")}进行中 · 第二轮</span>
              <h2>数学口算 20 题</h2>
            </div>
            <div class="progress-ring" aria-label="任务完成 68%"><span>68%</span></div>
          </div>
          <div class="mission-bottom">
            <div>
              <span class="capsule light">${icon("clock", "w-3.5 h-3.5")}还剩 12 分钟</span>
              <p class="mt-3 text-[13px] font-semibold leading-6 text-[#697A89]">
                结束后自动生成证据，家长只需确认完成/部分完成/驳回。
              </p>
            </div>
            <button class="soft-cta" data-nav="taskDetail">${icon("play", "w-4 h-4")}查看</button>
          </div>
        </section>

        <div class="section-head">
          <h3>模板和小书包</h3>
          <button data-toast="全量模板页将在确认后迁移">管理</button>
        </div>
        <section class="h-scroll" aria-label="任务模板">
          <button class="template-card accent" data-nav="packing">
            <span class="capsule">${icon("backpack", "w-3.5 h-3.5")}小书包</span>
            <h4>明早 7:40 前确认</h4>
            <p>数学本、水杯、红领巾还有 2 项待补。</p>
          </button>
          <button class="template-card" data-nav="sleep">
            <span class="capsule blue">${icon("moon", "w-3.5 h-3.5")}睡前</span>
            <h4>21:10 开始</h4>
            <p>洗漱、整理桌面、关闭自由聊天。</p>
          </button>
          <button class="template-card" data-nav="flow">
            <span class="capsule warn">${icon("mic", "w-3.5 h-3.5")}朗读</span>
            <h4>英语 10 分钟</h4>
            <p>声音检测 + 家长抽查，更适合睡前前置。</p>
          </button>
        </section>

        <section class="ai-bubble">
          <div class="ai-bubble-head">
            <span class="ai-mark">${icon("bot", "w-4 h-4")}</span>
            <div>
              <strong>AI 建议：不要再加新任务</strong>
              <small>根据今天作业时长和睡前目标</small>
            </div>
          </div>
          <p>今天 21:10 后有睡前流程。如果临时加任务，建议只加“小书包检查”，避免挤占上床时间。</p>
          <div class="chip-row">
              <button class="chip primary" data-nav="packing">加小书包</button>
            <button class="chip" data-toast="已延后英语朗读到明天">延到明天</button>
          </div>
        </section>
      </section>
    `;
  },

  watch() {
    return `
      <section class="scene">
        <section class="live-stage">
          <img src="${refs.desk}" alt="书桌与电脑学习场景真实照片" />
          <div class="live-hud">
            <span class="capsule">${icon("radio", "w-3.5 h-3.5")}LIVE</span>
            <span class="capsule">${icon("shield-check", "w-3.5 h-3.5")}远程查看提示中</span>
          </div>
          <div class="live-copy">
            <div class="pill-line">
              <span class="capsule">${icon("wifi", "w-3.5 h-3.5")}38ms</span>
              <span class="capsule">${icon("eye", "w-3.5 h-3.5")}低清稳定</span>
            </div>
            <h2>书桌视角已连接</h2>
            <p>孩子正在写数学口算。米拉建议保持观察，不主动打断。</p>
          </div>
          <div class="live-toolbar" aria-label="实时看护操作">
            <button class="live-tool" data-toast="截图已保存到事件回放" aria-label="截图">${icon("camera")}</button>
            <button class="live-tool primary" data-toast="正在发起音频通话" aria-label="通话">${icon("phone")}</button>
            <button class="live-tool" data-toast="已发送轻提醒" aria-label="提醒">${icon("bell-ring")}</button>
          </div>
        </section>

        <section class="detail-sheet">
          <section class="live-panel">
            <div class="ai-bubble-head">
              <span class="ai-mark">${icon("sparkles", "w-4 h-4")}</span>
              <div>
                <strong>为什么判断正常？</strong>
                <small>AI-generated · 置信度 91%</small>
              </div>
            </div>
            <p class="mt-3 text-[13px] font-semibold leading-6 text-[#697A89]">
              书桌区域连续活动 18 分钟，未检测到离席、异常声音或陌生人入画。证据只关联当前任务，不保存全天连续录像。
            </p>
            <div class="chip-row">
              <button class="chip primary" data-nav="playback">查看证据</button>
              <button class="chip" data-nav="privacySettings">隐私说明</button>
            </div>
          </section>

          <div class="section-head">
            <h3>当前上下文</h3>
            <button data-nav="tasks">任务</button>
          </div>
          <section class="h-scroll" aria-label="实时上下文">
            <button class="story-tile blue" data-nav="tasks">
              <span class="capsule blue">${icon("book-open-check", "w-3.5 h-3.5")}任务</span>
              <h4>数学口算</h4>
              <p>剩余 12 分钟，结束后进入证据确认。</p>
            </button>
            <button class="story-tile warm" data-nav="deviceSettings">
              <span class="capsule warn">${icon("signal", "w-3.5 h-3.5")}网络</span>
              <h4>低清稳定模式</h4>
              <p>保持流畅优先，截图仍可保存。</p>
            </button>
          </section>
        </section>
      </section>
    `;
  },
};

Object.assign(views, fullViews);

const premiumViewAliases = {
  setupComplete: "setupDone",
  setupChildError: "setupChild",
  setupDeviceFailed: "bindingFailed",
  setupPermissionsFailed: "permissionDenied",
  watchPrivacyPaused: "watchPrivacy",
  taskSearchNoResult: "taskNoResult",
  pendingDecisions: "care",
};

function pStatus(label, tone = "info", iconName = "sparkles") {
  return `<span class="p-status ${tone}">${icon(iconName, "w-3.5 h-3.5")}<span>${label}</span></span>`;
}

function pHeader({ kicker, title, subtitle = "", back = "", action = "" }) {
  return `
    <header class="p-header">
      ${back ? `<button class="p-icon-button" data-nav="${back}" aria-label="返回">${icon("chevron-left")}</button>` : ""}
      <div class="p-header-copy">
        <p>${kicker}</p>
        <h1>${title}</h1>
        ${subtitle ? `<span>${subtitle}</span>` : ""}
      </div>
      ${action || `<button class="p-icon-button notice-dot" data-nav="alerts" aria-label="通知">${icon("bell")}</button>`}
    </header>
  `;
}

function pShell({ kicker, title, subtitle = "", back = "", action = "", cls = "", body = "" }) {
  return `
    <section class="scene premium-app ${cls}">
      <div class="p-light-field" aria-hidden="true"></div>
      ${pHeader({ kicker, title, subtitle, back, action })}
      <div class="p-stack">${body}</div>
    </section>
  `;
}

function pActionRow(actions = []) {
  return `<div class="p-action-row">${actions.map(([label, attrs = "", tone = ""]) => `<button class="p-button ${tone}" ${attrs}>${label}</button>`).join("")}</div>`;
}

function pAiCard({ title, body, confidence = "91%", evidence = "3 项证据", tone = "ai", actions = [] }) {
  return `
    <section class="p-ai-card ${tone}">
      <div class="p-card-sheen" aria-hidden="true"></div>
      <div class="p-ai-head">
        <span class="p-ai-orb">${icon("sparkles", "w-4 h-4")}</span>
        <div>
          <strong>${title}</strong>
          <small>AI-generated · 置信度 ${confidence} · ${evidence}</small>
        </div>
      </div>
      <p>${body}</p>
      ${actions.length ? pActionRow(actions) : ""}
    </section>
  `;
}

function pEvidenceCard(title, desc, tone = "info", route = "evidencePreview") {
  const iconMap = { info: "file-check-2", success: "check-circle-2", warning: "triangle-alert", danger: "siren", ai: "bot" };
  return `
    <button class="p-evidence-card ${tone}" data-nav="${route}">
      <span>${icon(iconMap[tone] || "file-check-2", "w-4 h-4")}</span>
      <div><strong>${title}</strong><small>${desc}</small></div>
      ${icon("chevron-right", "w-4 h-4")}
    </button>
  `;
}

function pMetric(label, value, desc, tone = "info") {
  return `<div class="p-metric ${tone}"><strong>${value}</strong><span>${label}</span><small>${desc}</small></div>`;
}

function pBentoCard({ cls = "", eyebrow = "", title = "", desc = "", status = "", route = "", children = "", action = "" }) {
  const tag = route ? "button" : "section";
  const routeAttr = route ? `data-nav="${route}"` : "";
  return `
    <${tag} class="p-bento-card ${cls}" ${routeAttr}>
      <div class="p-card-sheen" aria-hidden="true"></div>
      ${status ? `<div class="p-bento-status">${status}</div>` : ""}
      ${eyebrow ? `<span class="p-eyebrow">${eyebrow}</span>` : ""}
      ${title ? `<h2>${title}</h2>` : ""}
      ${desc ? `<p>${desc}</p>` : ""}
      ${children}
      ${action}
    </${tag}>
  `;
}

function pStatePage({ kind = "info", title, body, back = "home", actions = [], extra = "" }) {
  const iconMap = {
    info: "info",
    loading: "loader-2",
    empty: "circle-dashed",
    error: "cloud-off",
    danger: "triangle-alert",
    warning: "octagon-alert",
    success: "check-circle-2",
    offline: "wifi-off",
  };
  return pShell({
    kicker: "状态说明",
    title,
    subtitle: body,
    back,
    cls: `state-lab ${kind}`,
    body: `
      <section class="p-state-hero ${kind}">
        <span class="p-state-icon">${icon(iconMap[kind] || "info", "w-7 h-7")}</span>
        <h2>${title}</h2>
        <p>${body}</p>
        ${actions.length ? pActionRow(actions) : ""}
      </section>
      ${extra}
    `,
  });
}

function pInlineState({ kind = "info", title, body, actions = [] }) {
  return `
    <section class="p-state-hero ${kind} compact">
      <span class="p-state-icon">${icon(kind === "warning" ? "octagon-alert" : kind === "danger" ? "triangle-alert" : kind === "success" ? "check-circle-2" : "info", "w-6 h-6")}</span>
      <h2>${title}</h2>
      <p>${body}</p>
      ${actions.length ? pActionRow(actions) : ""}
    </section>
  `;
}

function pDecisionList(items) {
  return `<section class="p-decision-list">${items.map(([title, desc, tone, route, meta = "待家长判断"]) => pEvidenceCard(title, `${meta} · ${desc}`, tone, route)).join("")}</section>`;
}

function pLiveLens({ mode = "normal", title = "书桌视角已连接", desc = "米拉建议保持观察，不主动打断。", badges = [], actions = true }) {
  const modeTone = {
    normal: "success",
    alert: "danger",
    offline: "danger",
    privacy: "info",
    low: "warning",
    updating: "warning",
  };
  const defaultBadges = badges.length ? badges : [
    ["LIVE", "radio", "success"],
    ["38ms", "wifi", "info"],
    ["隐私提示中", "shield-check", "ai"],
  ];
  return `
    <section class="p-live-lens ${mode}">
      <img src="${refs.desk}" alt="家庭书桌看护画面" />
      <div class="p-live-overlay" aria-hidden="true"></div>
      <div class="p-live-top">${defaultBadges.map(([label, ico, tone]) => pStatus(label, tone, ico)).join("")}</div>
      <div class="p-live-copy">
        ${pStatus(mode === "normal" ? "安全正常" : mode === "privacy" ? "隐私暂停" : mode === "low" ? "低置信度" : mode === "offline" ? "设备离线" : "需要判断", modeTone[mode] || "info", mode === "offline" ? "wifi-off" : "sparkles")}
        <h2>${title}</h2>
        <p>${desc}</p>
      </div>
      ${
        actions
          ? `<div class="p-live-tools">
              <button aria-label="截图" data-toast="截图已保存到证据预览">${icon("camera")}</button>
              <button class="primary" aria-label="通话" data-sheet="callChild">${icon("phone")}</button>
              <button aria-label="提醒" data-toast="已发送温和提醒">${icon("bell-ring")}</button>
            </div>`
          : ""
      }
    </section>
  `;
}

function pSettingsGroup(title, rows) {
  return `
    <section class="p-control-group">
      <div class="p-section-title"><h3>${title}</h3></div>
      ${rows.map(([ico, label, desc, route, tone = ""]) => pEvidenceCard(label, desc, tone || "info", route)).join("")}
    </section>
  `;
}

function pNotificationPage(type, title, desc, tone = "info") {
  return pShell({
    kicker: "通知详情",
    title,
    subtitle: desc,
    back: "alerts",
    body: `
      ${pBentoCard({
        cls: `wide ${tone}`,
        status: pStatus(type, tone, tone === "danger" ? "siren" : "bell"),
        title,
        desc,
        children: `<div class="p-evidence-grid">${pMetric("触达", "已读", "妈妈 19:22 查看", "success")}${pMetric("处理", "待确认", "保留 24 小时", tone)}</div>`,
      })}
      ${pAiCard({ title: "建议处理方式", body: "先查看证据，再决定标记已处理、误报或稍后提醒。所有处理都会进入今日报告。", confidence: "88%", evidence: "通知来源 / 设备状态", actions: [["查看证据", 'data-nav="evidencePreview"', "primary"], ["稍后提醒", 'data-toast="已设置稍后提醒"', "secondary"]] })}
    `,
  });
}

function authStatePage({ kind = "error", title, body, back = "login", actions = [] }) {
  const iconName = kind === "loading" ? "loader-2" : kind === "success" ? "check-circle-2" : "circle-alert";
  return `
    <section class="auth-scene auth-state-scene ${kind}" aria-labelledby="${kind}-auth-title">
      <div class="auth-calm-space" aria-hidden="true"></div>
      <button class="auth-back" data-nav="${back}" aria-label="返回">
        ${icon("chevron-left", "w-4 h-4")}
      </button>
      <section class="auth-state-copy">
        <span class="auth-state-mark ${kind}">${icon(iconName, "w-7 h-7")}</span>
        <h1 id="${kind}-auth-title">${title}</h1>
        <p>${body}</p>
        ${
          actions.length
            ? `<div class="auth-state-actions">
                ${actions
                  .map(
                    ({ label, attrs = "", tone = "primary", loading = false }) => `
                      <button class="auth-primary ${tone} ${loading ? "loading" : ""}" type="button" ${attrs}>
                        ${loading ? `<span class="loading-dot"></span>` : ""}${label}
                      </button>
                    `,
                  )
                  .join("")}
              </div>`
            : ""
        }
      </section>
    </section>
  `;
}

const premiumViews = {
  setup() {
    return pShell({
      kicker: "新用户设置",
      title: "家庭看护指挥台已准备好",
      subtitle: "老用户会直接进入首页；新用户先完成设备、孩子档案、权限和隐私边界。",
      cls: "setup-command",
      action: `<button class="p-icon-button" data-nav="login" aria-label="返回登录">${icon("x")}</button>`,
      body: `
        ${pBentoCard({
          cls: "hero ai",
          status: pStatus("新用户路径", "ai", "sparkles"),
          title: "先把看护边界设清楚",
          desc: "绑定设备后，米拉只在任务、安全和家长确认场景下整理证据。",
          action: pActionRow([["开始设置", 'data-nav="setupStart"', "primary"], ["老用户预览", 'data-nav="home"', "secondary"]]),
        })}
        <section class="p-step-rail">
          ${["家长身份", "绑定设备", "孩子档案", "权限授权", "隐私边界"].map((label, index) => `<span class="${index === 0 ? "active" : ""}"><b>${index + 1}</b>${label}</span>`).join("")}
        </section>
      `,
    });
  },

  loginError() {
    return authStatePage({
      kind: "error",
      title: "登录暂时失败",
      body: "网络异常或手机号格式不正确。请检查后重新获取验证码。",
      back: "login",
      actions: [
        { label: "返回登录", attrs: 'data-nav="login"' },
        { label: "隐私说明", attrs: 'data-sheet="privacyPolicy"', tone: "secondary" },
      ],
    });
  },

  verifyError() {
    return authStatePage({
      kind: "error",
      title: "验证码不正确",
      body: "请输入短信中的 6 位验证码，或重新发送验证码。",
      back: "verify",
      actions: [
        { label: "重新输入", attrs: 'data-nav="verify"' },
        { label: "重新发送", attrs: 'data-toast="验证码已重新发送"', tone: "secondary" },
      ],
    });
  },

  verifyLoading() {
    return authStatePage({
      kind: "loading",
      title: "正在验证",
      body: "正在确认家长身份，请稍等。",
      back: "verify",
      actions: [{ label: "验证中...", attrs: "disabled", loading: true }],
    });
  },

  newUserBranch() {
    return pStatePage({ kind: "success", title: "已创建家长账户", body: "接下来完成设备绑定、孩子档案、权限和隐私边界。", back: "login", actions: [["开始设置", 'data-nav="setupStart"', "primary"]] });
  },

  returningUserBranch() {
    return pStatePage({ kind: "success", title: "欢迎回来", body: "已识别家庭账户，正在进入今日家庭决策台。", back: "login", actions: [["进入首页", 'data-nav="home"', "primary"], ["查看告警", 'data-nav="alerts"', "secondary"]] });
  },

  home() {
    return pShell({
      kicker: "周一 19:42 · 米拉陪伴中",
      title: "小宇的习惯节奏",
      subtitle: "今晚重点练习学习自启动、餐桌收尾和睡前准备；1 件需要你确认。",
      cls: "home-command habit-home",
      body: `
        <section class="habit-hero" aria-label="今日主习惯">
          <img src="${refs.study}" alt="孩子在书桌前开始学习" />
          <div class="habit-hero-glow" aria-hidden="true"></div>
          <div class="habit-hero-copy">
            <div class="habit-status-row">
              ${pStatus("米拉陪伴中", "ai", "sparkles")}
              ${pStatus("低打扰", "success", "volume-1")}
            </div>
            <span class="habit-label">今日主练习</span>
            <h2>自己启动数学口算</h2>
            <p>米拉只做短句提醒：坐好、拿出口算本、先完成前 20 题。现在不用家长催。</p>
          </div>
          <div class="habit-orbit-panel">
            <div class="habit-ring" aria-label="自启动进度 72%">
              <strong>72%</strong>
              <span>自启动</span>
            </div>
            <div class="habit-next">
              <strong>8 分钟</strong>
              <span>后提醒休息</span>
            </div>
          </div>
          <div class="habit-hero-actions">
            <button class="p-button primary" data-nav="care">处理待确认</button>
            <button class="p-button secondary" data-nav="watch">看一眼画面</button>
          </div>
        </section>

        <section class="habit-rhythm-strip" aria-label="今晚习惯节奏">
          <button class="done" data-nav="taskDetail">
            <b>19:30</b>
            <strong>作业启动</strong>
            <small>已自启</small>
          </button>
          <button class="active" data-nav="taskDetail">
            <b>19:42</b>
            <strong>口算中</strong>
            <small>18 分钟</small>
          </button>
          <button data-nav="packing">
            <b>20:20</b>
            <strong>小书包</strong>
            <small>检查水杯</small>
          </button>
          <button data-nav="sleep">
            <b>21:10</b>
            <strong>睡前</strong>
            <small>少催促</small>
          </button>
        </section>

        <section class="habit-bento-grid" aria-label="家长今日需要看什么">
          <button class="habit-card parent" data-nav="taskEvidence">
            <span>${icon("file-check-2", "w-4 h-4")}</span>
            <small>家长确认</small>
            <strong>口算证据稍后生成</strong>
            <p>完成后确认 / 部分完成 / 驳回 AI 判断。</p>
          </button>
          <button class="habit-card reward" data-nav="rewardRequest">
            <span>${icon("gift", "w-4 h-4")}</span>
            <small>奖励申请</small>
            <strong>想换周末骑车</strong>
            <p>米拉只转交，不向孩子承诺。</p>
          </button>
          <button class="habit-card table" data-nav="tasks">
            <span>${icon("utensils", "w-4 h-4")}</span>
            <small>餐桌习惯</small>
            <strong>晚饭收尾更快</strong>
            <p>比昨天少 9 分钟，明天继续低频提醒。</p>
          </button>
          <button class="habit-card sleep" data-nav="sleep">
            <span>${icon("moon", "w-4 h-4")}</span>
            <small>睡前准备</small>
            <strong>建议提前 10 分钟</strong>
            <p>小书包和洗漱不要挤到最后。</p>
          </button>
        </section>

        <section class="habit-coach-card" aria-label="米拉陪伴说明">
          <div class="habit-coach-head">
            <span>${icon("sparkles", "w-4 h-4")}</span>
            <div>
              <strong>米拉建议：继续练“自己开始”</strong>
              <small>证据：提醒记录 / 响应时间 / 任务进度 · 置信度 88%</small>
            </div>
          </div>
          <p>今天小宇在第二次短提醒后自己回到书桌。建议今晚不要追加新学习任务，只在口算结束后确认证据，并用一句具体表扬收尾。</p>
          <div class="habit-coach-steps">
            <span>少催促</span>
            <span>先自启</span>
            <span>证据后确认</span>
          </div>
          ${pActionRow([["查看证据", 'data-nav="evidencePreview"', "primary"], ["调整明日节奏", 'data-nav="tasks"', "secondary"], ["今日报告", 'data-nav="dailyReportDetail"', "secondary"]])}
        </section>
      `,
    });
  },

  homeLoading() {
    return pStatePage({
      kind: "loading",
      title: "正在汇总家庭状态",
      body: "米拉正在同步设备、任务、告警和今日报告。",
      actions: [["查看离线摘要", 'data-nav="homeOffline"', "secondary"]],
      extra: `<section class="p-skeleton-stack"><span></span><span></span><span></span></section>`,
    });
  },

  homeEmpty() {
    return pStatePage({
      kind: "empty",
      title: "还没有家庭看护数据",
      body: "先绑定设备并创建孩子档案，首页会变成每日决策台。",
      actions: [["开始设置", 'data-nav="setupStart"', "primary"], ["创建孩子档案", 'data-nav="setupChild"', "secondary"]],
      extra: `
        <img class="p-state-image" src="${refs.empty}" alt="空桌面、家庭摄像头和待开始文件夹的空状态插画" />
        <section class="p-bento-grid two">${pBentoCard({ title: "设备", desc: "扫码或蓝牙发现摄像头", route: "setupDevice", status: pStatus("未绑定", "warning", "camera") })}${pBentoCard({ title: "权限", desc: "通知、相机、麦克风说明", route: "setupPermissions", status: pStatus("待开启", "info", "bell") })}</section>
      `,
    });
  },

  homeOffline() {
    return pStatePage({
      kind: "offline",
      title: "书房摄像头已离线",
      body: "最后在线 18:42。任务计划、历史证据和日报仍可查看。",
      actions: [["重连设备", 'data-nav="deviceSettings"', "primary"], ["看历史证据", 'data-nav="evidencePreview"', "secondary"]],
      extra: pAiCard({ title: "离线期间如何处理？", body: "设备上线后会同步提醒和本地任务变更。安全告警无法实时触发，建议先检查电源和路由器。", confidence: "设备状态", evidence: "最后心跳 / Wi-Fi 记录", actions: [["稍后提醒", 'data-toast="已在 20 分钟后提醒检查设备"', "secondary"]] }),
    });
  },

  homeAbnormal() {
    return pStatePage({
      kind: "warning",
      title: "今日有 1 条异常需要判断",
      body: "19:18 门口短促声音，未检测到陌生人入画。建议先联系孩子确认。",
      actions: [["查看安全事件", 'data-nav="safetyDetail"', "primary"], ["标记误报", 'data-sheet="falseAlarm"', "danger"]],
      extra: pDecisionList([["门口异常声音", "8 秒声音片段，未升级紧急联系人", "danger", "safetyDetail", "安全事件"], ["设备麦克风采集波动", "实时画面可用，声音告警可能延迟", "warning", "deviceSettings", "设备异常"]]),
    });
  },

  homeError() {
    return pStatePage({ kind: "error", title: "家庭状态暂时无法加载", body: "网络请求失败。你可以重试，或直接查看任务与本地缓存。", actions: [["重试", 'data-toast="正在重新加载"', "primary"], ["去任务", 'data-nav="tasks"', "secondary"]] });
  },

  todayStatusDetail() {
    return pShell({
      kicker: "今日状态详情",
      title: "孩子、任务、设备一页看清",
      subtitle: "按家长决策顺序组织，而不是流水账。",
      back: "home",
      body: `
        <section class="p-evidence-grid">${pMetric("专注", "18m", "连续书桌活动", "success")}${pMetric("任务", "68%", "口算进行中", "ai")}${pMetric("安全", "0", "未升级事件", "success")}</section>
        ${pDecisionList([["当前任务", "数学口算剩余 12 分钟", "ai", "taskDetail", "进行中"], ["设备边界", "隐私提示灯开启，低清稳定", "success", "privacySettings", "正常"], ["奖励申请", "周末户外活动等待确认", "warning", "rewardRequest", "待判断"]])}
        ${pAiCard({ title: "今日重点", body: "不要新增学习任务。建议保留小书包检查，把睡前流程提前 10 分钟。", actions: [["查看日报", 'data-nav="dailyReportDetail"', "primary"], ["管理任务", 'data-nav="tasks"', "secondary"]] })}
      `,
    });
  },

  care() {
    return pShell({
      kicker: "待确认事项",
      title: "只处理需要你判断的事",
      subtitle: "AI 可以整理证据，但不会替家长下结论。",
      back: "home",
      body: `
        ${pDecisionList([["数学口算证据", "确认完成、部分完成或误报", "warning", "taskEvidence", "任务证据"], ["周末户外活动", "20 积分奖励申请", "ai", "rewardRequest", "奖励申请"], ["门口声音片段", "建议先联系孩子确认", "danger", "safetyDetail", "安全事件"], ["AI 对话边界", "睡前自由聊天限制建议开启", "info", "conversation", "规则确认"]])}
        ${pAiCard({ title: "处理顺序建议", body: "先处理安全事件，再确认任务证据，最后处理奖励申请。所有操作会进入今日报告。", actions: [["全部稍后提醒", 'data-toast="已设置稍后提醒"', "secondary"]] })}
      `,
    });
  },

  aiSuggestionDetail() {
    return pShell({
      kicker: "AI 建议详情",
      title: "为什么现在不用打断孩子",
      subtitle: "建议只作为辅助判断，最终由家长确认。",
      back: "home",
      body: `
        ${pAiCard({ title: "建议结论", body: "保持观察，等待任务结束后一次处理证据和奖励。", confidence: "91%", evidence: "活动连续性 / 声音 / 任务进度", actions: [["接受建议", 'data-toast="已接受建议"', "primary"], ["稍后提醒", 'data-toast="已稍后提醒"', "secondary"], ["标记不准", 'data-sheet="falseAlarm"', "danger"]] })}
        ${pDecisionList([["证据 1：书桌活动连续", "18 分钟内没有离席", "success", "evidencePreview"], ["证据 2：无异常声音", "仅有键盘和翻书声", "success", "playback"], ["证据 3：任务仍在进行", "剩余 12 分钟，不宜打断", "ai", "taskDetail"]])}
      `,
    });
  },

  evidencePreview() {
    return pShell({
      kicker: "证据快速预览",
      title: "只看和判断有关的片段",
      subtitle: "证据按任务和事件保存，不做全天连续录像。",
      back: "home",
      body: `
        ${pBentoCard({ cls: "hero visual evidence", status: pStatus("任务证据", "ai", "file-check-2"), title: "数学口算关键片段", desc: "3 张关键帧 + 18 分钟活动摘要。", children: `<img src="${refs.study}" alt="任务证据预览" />`, action: pActionRow([["确认完成", 'data-sheet="confirmEvidence"', "primary"], ["部分完成", 'data-sheet="partialEvidence"', "secondary"], ["误报", 'data-sheet="rejectEvidence"', "danger"]]) })}
        ${pAiCard({ title: "证据说明", body: "系统只抽取任务开始、稳定进行、结束前的关键帧。家长可以改判，改判会影响奖励和报告。", confidence: "89%", evidence: "关键帧 / 活动时间 / 声音状态" })}
      `,
    });
  },

  tasks() {
    return pShell({
      kicker: "任务节奏板",
      title: "今天只盯关键任务",
      subtitle: "时间、证据、奖励和确认状态集中到一张节奏板。",
      cls: "task-command",
      action: `<button class="p-icon-button" data-sheet="taskTemplates" aria-label="模板">${icon("sparkles")}</button>`,
      body: `
        <section class="p-date-rail">${["今天:28", "明天:29", "周六:30", "周日:31", "周一:01"].map((item) => { const [label, num] = item.split(":"); return `<button class="${state.selectedDay === label ? "active" : ""}" data-day="${label}"><b>${num}</b><span>${label}</span></button>`; }).join("")}</section>
        <section class="p-searchbar"><input data-task-search value="${state.taskSearch}" placeholder="搜索任务、模板、小书包" /><button data-nav="${state.taskSearch ? "taskSearchNoResult" : "flow"}">${state.taskSearch ? "搜索" : "筛选"}</button></section>
        <section class="p-filter-rail">${["all:全部", "todo:待做", "doing:进行中", "done:已完成"].map((item) => { const [id, label] = item.split(":"); return `<button class="${state.taskFilter === id ? "active" : ""}" data-task-filter="${id}">${label}</button>`; }).join("")}</section>
        ${pBentoCard({ cls: "hero mission", status: `${pStatus("进行中", "ai", "timer")}${pStatus("证据待生成", "warning", "file-check-2")}`, title: "数学口算 20 题", desc: "剩余 12 分钟。结束后自动生成证据，家长确认后进入积分流水。", children: `<div class="p-progress-orbit"><span>68%</span></div>`, action: pActionRow([["查看任务", 'data-nav="taskDetail"', "primary"], ["结束并确认", 'data-nav="taskConfirm"', "secondary"]]) })}
        <section class="p-bento-grid three">
          ${pBentoCard({ title: "小书包", desc: "明早 7:40 前确认 4 项", route: "packing", status: pStatus("2 项待补", "warning", "backpack") })}
          ${pBentoCard({ title: "睡前流程", desc: "21:10 开始，建议提前 10 分钟", route: "sleep", status: pStatus("今晚", "info", "moon") })}
          ${pBentoCard({ title: "模板库", desc: "朗读、打卡、周五检查", route: "flow", status: pStatus("AI 推荐", "ai", "sparkles") })}
        </section>
        ${pAiCard({ title: "AI 建议：不要再加新学习任务", body: "今天 21:10 后有睡前流程。如果临时加任务，建议只加小书包检查。", evidence: "任务时长 / 睡前目标", actions: [["加小书包", 'data-nav="packing"', "primary"], ["延到明天", 'data-toast="已延后英语朗读到明天"', "secondary"]] })}
      `,
    });
  },

  taskDetail() {
    return pShell({
      kicker: "任务详情",
      title: "数学口算 20 题",
      subtitle: "进行中 · 证据将在结束后由家长确认。",
      back: "tasks",
      body: `
        ${pBentoCard({ cls: "hero mission", status: pStatus("进行中 · 第二轮", "ai", "timer"), title: "剩余 12 分钟", desc: "Mira 正在观察书桌活动、离席和异常声音。", children: `<div class="p-progress-line"><span style="width:68%"></span></div>`, action: pActionRow([["查看证据", 'data-nav="taskEvidence"', "primary"], ["编辑", 'data-nav="taskEdit"', "secondary"], ["延后", 'data-sheet="delayTask"', "secondary"]]) })}
        ${pDecisionList([["证据策略", "AI 观察 + 家长确认", "ai", "taskEvidence"], ["奖励规则", `完成后 +${state.taskDraft.reward || 3} ${state.pointUnit}`, "success", "points"], ["超时处理", "超过 20:05 自动转待确认", "warning", "taskTimeout"]])}
      `,
    });
  },

  taskEdit() {
    return pShell({
      kicker: "编辑任务",
      title: "任务规则由家长确认",
      subtitle: "AI 只负责提醒和整理证据。",
      back: "taskDetail",
      body: `
        <section class="p-form-card">
          <label class="app-field ${state.taskDraft.title ? "" : "error"}"><span>任务名称</span><input data-task-title value="${state.taskDraft.title}" placeholder="例如：英语朗读 10 分钟" />${state.taskDraft.title ? "" : "<small>请输入任务名称</small>"}</label>
          <div class="two-fields"><label class="app-field"><span>开始时间</span><input value="${state.taskDraft.start}" /></label><label class="app-field"><span>奖励${state.pointUnit}</span><input data-task-reward inputmode="numeric" value="${state.taskDraft.reward}" /></label></div>
          ${pDecisionList([["AI 观察 + 家长确认", "推荐：只在任务结束时整理证据", "ai", "taskEvidence"], ["仅家长打卡", "不调用摄像头判断", "info", "taskConfirm"]])}
          <button class="auth-primary ${state.formStatus === "saving" ? "loading" : state.formStatus === "saved" ? "success" : ""}" data-save-form="${state.taskDraft.title ? "task" : "invalid"}" ${state.taskDraft.title ? "" : "disabled"}>${state.formStatus === "saving" ? "保存中..." : state.formStatus === "saved" ? "已保存" : "保存任务"}</button>
        </section>
      `,
    });
  },

  taskEvidence() {
    const [label, tone] = evidenceLabel();
    return pShell({
      kicker: "任务证据",
      title: "数学口算证据待确认",
      subtitle: `当前状态：${label}`,
      back: "tasks",
      body: `
        ${pBentoCard({ cls: `hero visual evidence ${tone}`, status: pStatus(label, tone, "file-check-2"), title: "18 分钟书桌活动摘要", desc: "AI 判断完成度较高，但奖励必须由家长确认。", children: `<img src="${refs.study}" alt="数学任务证据" />`, action: pActionRow([["确认完成", 'data-sheet="confirmEvidence"', "primary"], ["部分完成", 'data-sheet="partialEvidence"', "secondary"], ["驳回/误报", 'data-sheet="rejectEvidence"', "danger"]]) })}
        ${pAiCard({ title: "为什么给出这个判断？", body: "任务时间内书桌区域活动连续，未检测到长时间离席。题目内容不被识别，仅判断任务流程。", confidence: "89%", evidence: "活动连续性 / 任务时间 / 关键帧" })}
      `,
    });
  },

  taskConfirm() {
    return pStatePage({ kind: "success", title: "任务确认完成", body: "确认后进入今日报告和积分流水。", back: "tasks", actions: [["确认完成", 'data-sheet="confirmEvidence"', "primary"], ["查看证据", 'data-nav="taskEvidence"', "secondary"]] });
  },

  taskReward() {
    return premiumViews.rewardRequest();
  },

  taskTimeout() {
    return pStatePage({ kind: "warning", title: "任务已超时", body: "Mira 暂停自动提醒，等待家长决定延后、结束或跳过。", back: "tasks", actions: [["延后 10 分钟", 'data-sheet="delayTask"', "primary"], ["结束任务", 'data-sheet="endTask"', "danger"]] });
  },

  taskFailed() {
    return pStatePage({ kind: "danger", title: "任务提醒发送失败", body: "设备离线或网络不稳定，任务已保存到 App，设备上线后同步。", back: "tasks", actions: [["查看设备", 'data-nav="deviceSettings"', "primary"], ["稍后同步", 'data-toast="已稍后同步"', "secondary"]] });
  },

  taskEmpty() {
    return pStatePage({ kind: "empty", title: "今天还没有任务", body: "可以从模板开始，或创建一个只需家长确认的轻任务。", back: "tasks", actions: [["套用模板", 'data-sheet="taskTemplates"', "primary"], ["手动创建", 'data-nav="taskEdit"', "secondary"]] });
  },

  taskNoResult() {
    return pStatePage({ kind: "empty", title: "没有找到匹配任务", body: "清除筛选，或从模板新建一个任务。", back: "tasks", actions: [["清除筛选", 'data-toast="已清除筛选"', "secondary"], ["创建任务", 'data-nav="taskEdit"', "primary"]] });
  },

  taskSearchNoResult() {
    return premiumViews.taskNoResult();
  },

  flow() {
    return pShell({
      kicker: "模板和小书包",
      title: "按今天节奏推荐任务",
      subtitle: "模板不会覆盖已有任务，只会追加到当前日期。",
      back: "tasks",
      body: `
        <section class="p-bento-grid two">
          ${pBentoCard({ cls: "ai", title: "放学后基础流", desc: "口算、阅读、小书包 3 项", route: "tasks", status: pStatus("推荐", "ai", "sparkles"), action: pActionRow([["套用", 'data-action="day-template-apply"', "primary"]]) })}
          ${pBentoCard({ title: "睡前轻任务", desc: "洗漱、整理、关闭自由聊天", route: "sleep", status: pStatus("21:10", "info", "moon") })}
          ${pBentoCard({ title: "小书包检查", desc: "按明日课表自动生成", route: "packing", status: pStatus("明早", "warning", "backpack") })}
          ${pBentoCard({ title: "英语朗读", desc: "声音检测 + 家长抽查", route: "taskEdit", status: pStatus("可延后", "info", "mic") })}
        </section>
        ${pAiCard({ title: "今日模板建议", body: "只套用小书包，避免新增学习任务挤压睡前流程。", actions: [["套用推荐", 'data-action="day-template-apply"', "primary"], ["手动创建", 'data-nav="taskEdit"', "secondary"]] })}
      `,
    });
  },

  packing() {
    return pShell({
      kicker: "小书包",
      title: "明早前确认 4 项物品",
      subtitle: "摄像头只辅助识别，不替代孩子自己整理。",
      back: "tasks",
      body: `
        ${pBentoCard({ cls: "hero warm", status: pStatus("2 项待处理", "warning", "backpack"), title: "水杯可能漏带", desc: "AI 未在书包侧袋识别到水杯，建议睡前提醒孩子自己确认。", action: pActionRow([["添加物品", 'data-sheet="packing"', "primary"], ["查看规则", 'data-nav="education"', "secondary"]]) })}
        <section class="p-decision-list">${packingRows()}</section>
        ${state.packingExtra.length ? `<section class="p-control-group"><div class="p-section-title"><h3>临时添加</h3></div>${state.packingExtra.map((item, index) => `<button class="p-evidence-card info" data-action="packing-extra-remove" data-index="${index}"><span>${icon("plus", "w-4 h-4")}</span><div><strong>${item}</strong><small>点击移除临时物品</small></div>${icon("x", "w-4 h-4")}</button>`).join("")}</section>` : ""}
      `,
    });
  },

  sleep() {
    return pShell({
      kicker: "睡前 / 晨起",
      title: "把节奏提前，不催促",
      subtitle: "睡前流程强调边界和温和提醒。",
      back: "tasks",
      body: `
        ${pBentoCard({ cls: "hero night", status: pStatus("21:10 开始", "info", "moon"), title: "今晚建议 21:00 提前准备", desc: "当前任务可能延后，睡前自由聊天会在 21:15 后关闭。", action: pActionRow([["提醒孩子", 'data-toast="已发送睡前轻提醒"', "primary"], ["调整规则", 'data-nav="conversation"', "secondary"]]) })}
        ${pDecisionList([["洗漱", "语音提醒，不保存证据", "info", "sleep"], ["整理桌面", "任务区收纳确认", "ai", "evidencePreview"], ["关闭自由聊天", "睡前边界自动启用", "success", "conversation"]])}
      `,
    });
  },

  focus() {
    return pStatePage({ kind: "info", title: "专注计时中", body: "当前任务剩余 12 分钟。家长可以暂停、延后或结束。", back: "taskDetail", actions: [["暂停", 'data-toast="已暂停任务"', "secondary"], ["延后", 'data-sheet="delayTask"', "primary"], ["结束", 'data-sheet="endTask"', "danger"]] });
  },

  watch() {
    return pShell({
      kicker: "AI 安全镜头",
      title: "摘要优先，不鼓励盯屏",
      subtitle: "实时画面只用于需要判断的片段和家长主动查看。",
      cls: "watch-command",
      body: `
        ${pLiveLens({ mode: "normal" })}
        ${pAiCard({ title: "为什么判断正常？", body: "书桌区域连续活动 18 分钟，未检测到离席、异常声音或陌生人入画。证据只关联当前任务。", evidence: "区域活动 / 声音 / 安全区域", actions: [["AI 判断详情", 'data-nav="aiJudgementDetail"', "primary"], ["隐私说明", 'data-nav="privacySettings"', "secondary"], ["暂停看护", 'data-sheet="pauseCareConfirm"', "secondary"]] })}
        <section class="p-bento-grid two">${pBentoCard({ title: "当前任务", desc: "数学口算剩余 12 分钟", route: "taskDetail", status: pStatus("进行中", "ai", "timer") })}${pBentoCard({ title: "事件回放", desc: "只保存任务和告警相关片段", route: "playback", status: pStatus("3 段", "info", "history") })}</section>
      `,
    });
  },

  watchOffline() {
    return pShell({
      kicker: "实时看护",
      title: "设备离线，实时画面不可用",
      subtitle: "历史证据仍可查看，任务编辑会待同步。",
      back: "watch",
      body: `${pLiveLens({ mode: "offline", title: "书房摄像头离线", desc: "最后在线 18:42。请检查电源和路由器。", badges: [["OFFLINE", "wifi-off", "danger"], ["历史可看", "history", "info"]], actions: false })}${pAiCard({ title: "离线处理建议", body: "如果孩子端断电，安全告警无法实时触发。可以先查看历史片段，并在设备管理里按步骤重连。", confidence: "设备状态", evidence: "最后心跳 / Wi-Fi", actions: [["重连设备", 'data-nav="deviceSettings"', "primary"], ["看历史事件", 'data-nav="playback"', "secondary"]] })}`,
    });
  },

  watchAlert() {
    return pShell({
      kicker: "实时看护",
      title: "有安全事件需要判断",
      subtitle: "门口短促声音，未检测到陌生人入画。",
      back: "watch",
      body: `${pLiveLens({ mode: "alert", title: "门口声音片段待判断", desc: "AI 建议先联系孩子确认，再决定是否标记误报。", badges: [["ALERT", "siren", "danger"], ["置信度 76%", "sparkles", "warning"]] })}${pActionRow([["联系孩子", 'data-sheet="callChild"', "primary"], ["标记已处理", 'data-sheet="resolveAlert"', "secondary"], ["误报", 'data-sheet="falseAlarm"', "danger"]])}`,
    });
  },

  watchPrivacy() {
    return pShell({
      kicker: "隐私暂停",
      title: "孩子端开启了隐私遮罩",
      subtitle: "实时画面暂停，但安全告警和任务摘要仍可工作。",
      back: "watch",
      body: `${pLiveLens({ mode: "privacy", title: "实时画面已遮罩", desc: "此状态下不会显示画面，也不会保存新的实时截图。", badges: [["隐私暂停", "lock-keyhole", "info"], ["边界生效", "shield-check", "success"]], actions: false })}${pAiCard({ title: "隐私边界说明", body: "孩子端可以在特定时段启用隐私遮罩。管理员可查看规则，但不建议绕过孩子端提示。", confidence: "规则说明", evidence: "隐私设置 / 时间段", actions: [["查看隐私规则", 'data-nav="privacySettings"', "primary"], ["稍后提醒", 'data-toast="已稍后提醒"', "secondary"]] })}`,
    });
  },

  watchPrivacyPaused() {
    return premiumViews.watchPrivacy();
  },

  watchLowConfidence() {
    return pShell({
      kicker: "AI 判断详情",
      title: "低置信度，需要家长判断",
      subtitle: "光线偏暗，书桌区域被遮挡，AI 不做强结论。",
      back: "watch",
      body: `${pLiveLens({ mode: "low", title: "画面置信度较低", desc: "建议查看证据片段或稍后再判断，不自动发放奖励。", badges: [["置信度 54%", "sparkles", "warning"], ["低光", "moon", "warning"]] })}${pAiCard({ title: "为什么不自动确认？", body: "孩子手部和书本区域被遮挡，任务完成度无法稳定判断。建议家长确认关键帧。", confidence: "54%", evidence: "低光 / 遮挡 / 活动不足", actions: [["查看证据", 'data-nav="evidencePreview"', "primary"], ["标记不确定", 'data-toast="已标记不确定"', "secondary"]] })}`,
    });
  },

  watchUpdating() {
    return pStatePage({ kind: "warning", title: "固件更新中 62%", body: "更新期间暂停实时画面、通话和解绑操作。预计 4 分钟后恢复。", back: "watch", actions: [["完成后提醒我", 'data-toast="已开启完成提醒"', "primary"], ["设备管理", 'data-nav="deviceSettings"', "secondary"]] });
  },

  watchAbnormal() {
    return pStatePage({ kind: "warning", title: "麦克风采集异常", body: "实时画面仍可用，但声音告警可能延迟。建议重启设备后测试麦克风。", back: "watch", actions: [["进入设备管理", 'data-nav="deviceSettings"', "primary"], ["查看安全事件", 'data-nav="safety"', "secondary"]] });
  },

  realtimeDetail() {
    return premiumViews.watch();
  },

  aiJudgementDetail() {
    return pShell({
      kicker: "AI 判断详情",
      title: "当前安全正常的证据",
      subtitle: "AI 只给建议，不替家长做不可逆决定。",
      back: "watch",
      body: `
        ${pAiCard({ title: "判断结论", body: "保持观察，不主动打断。当前任务仍在进行，安全区域无异常。", confidence: "91%", evidence: "3 类信号", actions: [["接受", 'data-toast="已接受判断"', "primary"], ["查看证据", 'data-nav="evidenceExplain"', "secondary"], ["标记不准", 'data-sheet="falseAlarm"', "danger"]] })}
        ${pDecisionList([["区域活动", "书桌区域连续活动 18 分钟", "success", "evidenceExplain"], ["声音", "无异常尖锐声或门口持续声", "success", "playback"], ["安全区域", "门口区域未出现陌生人", "success", "zones"]])}
      `,
    });
  },

  evidenceExplain() {
    return pShell({
      kicker: "证据说明",
      title: "证据如何被生成和保存",
      subtitle: "默认只保存任务与事件相关片段。",
      back: "watch",
      body: `
        ${pDecisionList([["任务证据", "开始、稳定、结束前关键帧", "ai", "taskEvidence"], ["安全事件", "触发前后短片段和规则", "danger", "safetyDetail"], ["隐私边界", "隐私遮罩期间不保存实时画面", "info", "privacySettings"]])}
        ${pAiCard({ title: "家长可纠错", body: "任何 AI 判断都可以被标记误报或改判，改判会记录到报告，不会直接对孩子做负面反馈。", confidence: "产品规则", evidence: "隐私策略 / 家长确认" })}
      `,
    });
  },

  playback() {
    return pShell({
      kicker: "事件回放",
      title: "只回看关键片段",
      subtitle: "按任务、告警、成长时刻分类，不做全天浏览。",
      back: "watch",
      body: `${pDecisionList([["数学口算关键帧", "任务证据 · 3 张关键帧", "ai", "taskEvidence"], ["门口声音片段", "安全事件 · 8 秒", "danger", "safetyDetail"], ["整理桌面", "成长时刻 · 可收藏", "success", "moments"]])}${pAiCard({ title: "回放边界", body: "回放保留最小必要内容，家长可隐藏或删除成长时刻。", confidence: "隐私规则", evidence: "保存策略", actions: [["管理隐私", 'data-nav="privacySettings"', "primary"]] })}`,
    });
  },

  zones() {
    return pShell({
      kicker: "安全区域",
      title: "区域规则要清楚，不制造焦虑",
      subtitle: "门口、窗边、书桌三类区域启用。",
      back: "watch",
      body: `
        ${pDecisionList([["门口区域", "短促声音触发待判断", "warning", "safetyDetail"], ["书桌区域", "任务活动识别稳定", "success", "watch"], ["窗边区域", "仅异常停留提醒", "info", "zones"]])}
        <button class="auth-primary" data-sheet="zone">新增安全区域</button>
      `,
    });
  },

  safety() {
    return pShell({
      kicker: "安全中心",
      title: "安全事件按判断处理",
      subtitle: "不把所有通知都变成警报。",
      back: "watch",
      body: `${pDecisionList([["门口异常声音", "未检测到陌生人入画", "danger", "safetyDetail"], ["紧急联系人", "妈妈、爸爸，外婆待邀请", "info", "familySettings"], ["安全区域", "3 个区域启用，门口规则较敏感", "success", "zones"]])}${pActionRow([["测试联系人", 'data-sheet="safety"', "secondary"], ["查看告警", 'data-nav="alerts"', "primary"]])}`,
    });
  },

  safetyDetail() {
    return premiumViews.alertDetail("安全事件详情", "门口异常声音");
  },

  alerts() {
    const filters = ["unread:未读", "processing:处理中", "resolved:已处理", "false:误报"];
    return pShell({
      kicker: "决策 inbox",
      title: "先处理需要判断的事",
      subtitle: "消息按安全、任务、设备、系统分组。",
      cls: "alert-command",
      action: `<button class="p-icon-button" data-toast="已全部标记已读" aria-label="全部已读">${icon("check-check")}</button>`,
      body: `
        <section class="p-filter-rail">${filters.map((item) => { const [id, label] = item.split(":"); return `<button class="${state.alertFilter === id ? "active" : ""}" data-alert-filter="${id}" data-nav="${id === "false" ? "falseAlarm" : id}">${label}</button>`; }).join("")}</section>
        ${pDecisionList([["19:18 门口异常声音", "安全事件 · 未读", "danger", "safetyNotification"], ["数学口算证据待确认", "任务提醒 · 处理中", "warning", "taskNotification"], ["书房设备离线后重连", "设备事件 · 已读", "info", "deviceNotification"], ["隐私政策摘要已更新", "系统通知 · 已读", "info", "systemNotification"]])}
      `,
    });
  },

  alertDetail(title = "告警详情", eventTitle = "门口异常声音") {
    return pShell({
      kicker: "安全事件",
      title: eventTitle,
      subtitle: "需要家长确认后归档。",
      back: "alerts",
      body: `
        ${pBentoCard({ cls: "hero visual alert", status: pStatus("待判断", "danger", "siren"), title: "19:18 门口短促声音", desc: "未检测到陌生人入画。AI 建议先联系孩子确认。", children: `<img src="${refs.room}" alt="家庭门口安全事件证据" />`, action: pActionRow([["联系孩子", 'data-sheet="callChild"', "primary"], ["标记已处理", 'data-sheet="resolveAlert"', "secondary"], ["误报", 'data-sheet="falseAlarm"', "danger"]]) })}
        ${pAiCard({ title: "触发规则", body: "门口区域在 6 秒内出现高于阈值的短促声音，但画面未出现陌生人。", confidence: "76%", evidence: "声音片段 / 门口区域 / 规则阈值" })}
      `,
    });
  },

  unread() {
    return premiumViews.alerts();
  },

  processing() {
    return pNotificationPage("处理中", "数学口算证据待确认", "已进入今日记录，等待家长完成证据判断。", "warning");
  },

  resolved() {
    return pNotificationPage("已处理", "书房设备已恢复在线", "设备在 18:47 重新连接，离线期间的任务变更已同步。", "success");
  },

  falseAlarm() {
    return pNotificationPage("误报", "门口声音已标记误报", "本次不会升级联系人，AI 会降低相似场景敏感度。", "danger");
  },

  systemNotification() {
    return pNotificationPage("系统通知", "隐私政策摘要已更新", "新增儿童数据删除和证据保存周期说明。", "info");
  },

  deviceNotification() {
    return pNotificationPage("设备通知", "书房设备离线后重连", "离线 5 分钟后恢复，期间未触发安全事件。", "info");
  },

  taskNotification() {
    return pNotificationPage("任务通知", "数学口算证据待确认", "任务结束后生成 3 张关键帧和活动摘要。", "warning");
  },

  safetyNotification() {
    return premiumViews.alertDetail("安全通知", "门口异常声音");
  },

  my() {
    return pShell({
      kicker: "家庭控制台",
      title: "小宇的家庭看护",
      subtitle: "成员、设备、隐私、AI 规则集中管理。",
      cls: "settings-command",
      body: `
        ${pBentoCard({ cls: "hero account", status: pStatus("管理员", "ai", "user-round-cog"), title: "妈妈 · 2 名家庭成员 · 1 台设备", desc: "看护规则、隐私边界和数据删除需要管理员确认。", action: pActionRow([["成员", 'data-nav="familySettings"', "primary"], ["权限管理", 'data-nav="permissionManagement"', "secondary"]]) })}
        <section class="p-evidence-grid">${pMetric("待处理", "2", "证据与奖励", "warning")}${pMetric("设备", "1", "在线", "success")}${pMetric("隐私", "3", "规则启用", "ai")}</section>
        ${pSettingsGroup("看护与规则", [["camera", "设备管理", "网络、固件、解绑和房间视角", "deviceSettings", "info"], ["bot", "AI 规则", "任务判断、自由聊天和睡前限制", "aiRules", "ai"], ["lock-keyhole", "隐私与数据", "远程查看边界、数据删除", "privacySettings", "info"], ["graduation-cap", "教育与内容边界", "小书包、答题边界和内容规则", "education", "info"]])}
        ${pSettingsGroup("报告与奖励", [["chart-line", "本周趋势", "专注、睡前和安全变化", "weekly", "success"], ["gift", "积分奖励", `${state.pointBalance} ${state.pointUnit} 可用`, "points", "warning"], ["sparkles", "成长时刻", "收藏积极片段", "moments", "ai"]])}
      `,
    });
  },

  settings() {
    return premiumViews.my();
  },

  deviceSettings() {
    return pShell({
      kicker: "设备管理",
      title: "书房摄像头",
      subtitle: "在线 · 电量 86% · Wi-Fi 稳定。",
      back: "my",
      body: `
        ${pBentoCard({ cls: "hero device visual", status: `${pStatus("在线", "success", "wifi")}${pStatus("固件 1.8.2", "info", "download-cloud")}`, title: "设备状态正常", desc: "实时看护、任务证据和安全区域均可用。", children: `<img src="${refs.device}" alt="摄像头连接成功的设备状态插画" />`, action: pActionRow([["校准视角", 'data-toast="正在校准视角"', "primary"], ["异常处理", 'data-sheet="deviceException"', "secondary"]]) })}
        ${pSettingsGroup("设备操作", [["scan", "房间视角", "重新确认书桌和门口区域", "zones", "info"], ["download-cloud", "固件更新", "已是最新版本，可查看更新状态", "watchUpdating", "success"], ["wifi-off", "离线处理", "重连步骤和历史证据说明", "watchOffline", "warning"], ["unlink", "解绑设备", "危险操作，需要管理员二次确认", "deviceSettings", "danger"]])}
        <button class="danger-link" data-sheet="unbindDevice">解绑设备</button>
      `,
    });
  },

  privacySettings() {
    return pShell({
      kicker: "隐私与数据",
      title: "看护要有边界",
      subtitle: "儿童数据、实时画面和证据保存都需要透明规则。",
      back: "my",
      body: `
        ${pBentoCard({ cls: "hero privacy", status: pStatus("隐私提示开启", "success", "lock-keyhole"), title: "远程查看会提示孩子", desc: "隐私遮罩期间不显示画面，也不保存新截图。", action: pActionRow([["权限管理", 'data-nav="permissionManagement"', "primary"], ["数据删除", 'data-nav="dataDeletion"', "danger"]]) })}
        ${pSettingsGroup("隐私规则", [["eye", "远程查看提示", "设备端亮灯并提示", "privacySettings", "success"], ["database", "证据保存周期", "任务 30 天，安全事件 90 天", "evidenceExplain", "info"], ["trash-2", "删除儿童数据", "需要管理员确认", "dataDeletion", "danger"]])}
        <button class="auth-primary ${state.formStatus === "saving" ? "loading" : ""}" data-save-form="privacy">保存隐私设置</button>
      `,
    });
  },

  permissionManagement() {
    return pShell({
      kicker: "权限管理",
      title: "谁能看、谁能改、谁能删除",
      subtitle: "权限影响告警处理、解绑设备和数据删除。",
      back: "privacySettings",
      body: `${pDecisionList([["妈妈", "管理员 · 可管理全部规则", "success", "familySettings"], ["爸爸", "可处理告警和查看日报", "info", "familySettings"], ["外婆", "仅查看日报，不能查看实时画面", "warning", "familySettings"]])}${pAiCard({ title: "权限建议", body: "只给主要照护人处理安全事件权限，数据删除和解绑设备保留管理员二次确认。", confidence: "规则建议", evidence: "家庭成员 / 操作风险" })}`,
    });
  },

  dataDeletion() {
    return pShell({
      kicker: "数据删除",
      title: "删除儿童数据需要二次确认",
      subtitle: "删除会影响报告、证据和成长时刻。",
      back: "privacySettings",
      body: `${pBentoCard({ cls: "hero danger", status: pStatus("危险操作", "danger", "trash-2"), title: "可删除任务证据、报告和成长时刻", desc: "安全事件会保留最小必要处理记录，用于家庭安全审计。", action: pActionRow([["提交删除申请", 'data-sheet="deleteData"', "danger"], ["导出说明", 'data-toast="正式版将打开导出说明"', "secondary"]]) })}${pAiCard({ title: "删除前请确认", body: "删除后无法恢复。建议先导出报告或只删除指定时间段证据。", confidence: "产品规则", evidence: "数据权利 / 安全审计" })}`,
    });
  },

  familySettings() {
    return pShell({
      kicker: "家庭成员",
      title: "家庭权限按照护责任分层",
      subtitle: "新增成员默认不能删除数据或解绑设备。",
      back: "my",
      body: `${pDecisionList([["妈妈 · 管理员", "设备、隐私、成员、删除数据", "success", "permissionManagement"], ["爸爸 · 可处理告警", "可联系孩子和标记已处理", "ai", "permissionManagement"], ["外婆 · 仅查看日报", "不可查看实时画面", "info", "permissionManagement"]])}${pActionRow([["邀请成员", 'data-sheet="contact"', "primary"], ["修改权限", 'data-sheet="memberRole"', "secondary"]])}`,
    });
  },

  childProfile() {
    return pShell({
      kicker: "孩子资料",
      title: `${childName()} 的档案`,
      subtitle: "用于任务、证据和告警文案，不用于营销画像。",
      back: "my",
      body: `<section class="p-form-card"><label class="app-field"><span>称呼</span><input data-child-name value="${state.childProfile.name}" /></label><div class="two-fields"><label class="app-field"><span>年龄</span><input data-child-age value="8" /></label><label class="app-field"><span>年级</span><input data-child-grade value="${state.childProfile.grade}" /></label></div><button class="auth-primary" data-save-form="profile">保存资料</button></section>`,
    });
  },

  notificationSettings() {
    return pShell({
      kicker: "通知设置",
      title: "通知只打扰重要判断",
      subtitle: "安全告警即时推送，报告类汇总提醒。",
      back: "my",
      body: pSettingsGroup("通知类型", [["siren", "安全告警", "立即推送", "safetyNotification", "danger"], ["file-check-2", "任务证据确认", "即时提醒", "taskNotification", "warning"], ["gift", "奖励申请", "汇总提醒", "rewardRequest", "ai"], ["wifi-off", "设备离线", "5 分钟后提醒", "deviceNotification", "info"], ["chart-line", "日报生成", "每日 21:30", "dailyReportDetail", "success"]]),
    });
  },

  aiRules() {
    return pShell({
      kicker: "AI 规则",
      title: "AI 只做判断建议",
      subtitle: "任务、聊天、睡前边界都需要家长确认。",
      back: "my",
      body: `${pBentoCard({ cls: "hero ai", status: pStatus("Human in control", "ai", "sparkles"), title: "所有 AI 建议都有确认入口", desc: "确认、稍后提醒、误报和查看证据是所有建议的基础动作。", action: pActionRow([["保存规则", 'data-sheet="aiWarning"', "primary"], ["查看边界", 'data-sheet="boundaries"', "secondary"]]) })}${pDecisionList([["任务判断", "证据必须由家长确认", "ai", "taskEvidence"], ["自由聊天", "睡前 21:15 后关闭", "warning", "conversation"], ["安全告警", "未确认前不升级联系人", "danger", "safety"]])}`,
    });
  },

  conversation() {
    return premiumViews.aiRules();
  },

  education() {
    return pShell({
      kicker: "教育与内容边界",
      title: "辅助习惯，不替孩子完成",
      subtitle: "小书包、答题边界和内容规则统一管理。",
      back: "my",
      body: `${pDecisionList([["小书包规则", `${state.schoolbagMode} · 按年级推荐`, "warning", "packing"], ["答题边界", "不直接给答案，只做提示", "ai", "conversation"], ["内容边界", "睡前减少自由聊天和视频内容", "info", "sleep"]])}${pAiCard({ title: "教育边界建议", body: "任务提醒保持温和，不用摄像头评价孩子表现，只在家长需要判断时整理证据。", confidence: "产品原则", evidence: "任务规则 / 睡前目标" })}`,
    });
  },

  accountSettings() {
    return pShell({
      kicker: "账号设置",
      title: "家长账户安全",
      subtitle: "手机号、登录设备和退出登录。",
      back: "my",
      body: pSettingsGroup("账号", [["smartphone", "手机号", "+86 138 0013 8000", "accountSecurity", "info"], ["monitor-smartphone", "登录设备", "当前手机 + 1 台备用设备", "accountSecurity", "info"], ["user-round", "个人信息", "称呼和家庭角色", "accountProfile", "ai"]]) + `<button class="danger-link" data-sheet="logout">退出登录</button>`,
    });
  },

  accountProfile() {
    return pShell({ kicker: "个人信息", title: "家长资料", subtitle: "影响家庭内称呼和通知文案。", back: "accountSettings", body: `<section class="p-form-card"><label class="app-field"><span>称呼</span><input data-parent-name value="${state.parentName}" /></label><label class="app-field"><span>家庭角色</span><input value="${state.parentRole}" /></label><button class="auth-primary" data-save-form="profile">保存资料</button></section>` });
  },

  accountSecurity() {
    return pShell({ kicker: "账号安全", title: "登录与验证", subtitle: "关键操作需要二次验证。", back: "accountSettings", body: pSettingsGroup("安全", [["smartphone", "更换手机号", "用于登录和安全验证", "accountSecurity", "info"], ["monitor-smartphone", "登录设备", "MacBook Safari 昨天登录", "accountSecurity", "warning"], ["shield-check", "关键操作验证", "删除数据、解绑设备必须确认", "dataDeletion", "success"]]) + pActionRow([["更换手机号", 'data-sheet="changePhone"', "primary"], ["管理登录设备", 'data-sheet="loginDevices"', "secondary"]]) });
  },

  helpFeedback() {
    return premiumViews.feedback();
  },

  feedback() {
    return pShell({ kicker: "帮助反馈", title: "告诉我们哪里不够清楚", subtitle: "反馈不会上传儿童画面。", back: "my", body: `<section class="p-form-card"><label class="app-field"><span>反馈内容</span><textarea data-feedback placeholder="例如：设备离线时希望先看到哪些信息？"></textarea></label><button class="auth-primary" data-save-form="feedback">提交反馈</button></section>${pSettingsGroup("帮助", [["file-text", "用户协议", "查看服务条款摘要", "about", "info"], ["scroll-text", "隐私政策", "儿童数据处理说明", "privacySettings", "info"]])}` });
  },

  subscription() {
    return pShell({ kicker: "订阅套餐", title: "家庭版权益", subtitle: "基础看护能力不因取消订阅失效。", back: "my", body: `${pBentoCard({ cls: "hero ai", status: pStatus("家庭版", "ai", "sparkles"), title: "云端报告高级版", desc: "长期趋势、更多人设和多设备云备份。", action: pActionRow([["续费", 'data-toast="已打开续费"', "primary"], ["取消或降级", 'data-sheet="subscriptionDowngrade"', "secondary"]]) })}` });
  },

  about() {
    return pShell({ kicker: "关于 Mira", title: "可信家庭 AI 摄像头", subtitle: "版本 0.9.2 · HTML 高保真原型。", back: "my", body: pSettingsGroup("协议与版本", [["info", "版本", "0.9.2", "about", "info"], ["file-text", "用户协议", "查看服务条款摘要", "about", "info"], ["scroll-text", "隐私政策", "儿童数据处理说明", "privacySettings", "info"]]) });
  },

  report() {
    return premiumViews.dailyReportDetail();
  },

  dailyReportDetail() {
    return pShell({
      kicker: "今日报告",
      title: "今天的关键判断",
      subtitle: "报告强调建议和待确认，不评价孩子。",
      back: "home",
      body: `
        ${pBentoCard({ cls: "hero report", status: pStatus("AI 汇总 · 可纠错", "ai", "sparkles"), title: "整体稳定，睡前建议提前 10 分钟", desc: "数学口算需要确认证据，小书包水杯待补，奖励申请待处理。", action: pActionRow([["确认关键证据", 'data-nav="taskEvidence"', "primary"], ["收藏成长时刻", 'data-sheet="moment"', "secondary"]]) })}
        <section class="p-evidence-grid">${pMetric("专注", "32m", "比昨天 +8m", "success")}${pMetric("待确认", "2", "证据 / 奖励", "warning")}${pMetric("告警", "1", "未升级", "danger")}</section>
        ${pAiCard({ title: "明天建议", body: "保留小书包检查，把英语朗读放到晚饭后，不建议睡前新增学习任务。", confidence: "86%", evidence: "今日任务 / 睡前节奏" })}
      `,
    });
  },

  reportLoading() {
    return pStatePage({ kind: "loading", title: "正在生成今日报告", body: "米拉正在汇总任务、奖励、安全和睡前节奏。", back: "my", extra: `<section class="p-skeleton-stack"><span></span><span></span><span></span></section>` });
  },

  reportEmpty() {
    return pStatePage({ kind: "empty", title: "今天还没有报告", body: "绑定设备并完成至少一个任务后，报告会在睡前生成。", back: "my", actions: [["去任务", 'data-nav="tasks"', "primary"], ["看设置", 'data-nav="setupStart"', "secondary"]] });
  },

  weekly() {
    return pShell({ kicker: "周报趋势", title: "一周只看趋势，不看碎片", subtitle: "专注、睡前、漏带风险和安全事件。", back: "my", body: `<section class="p-evidence-grid">${pMetric("专注", "+18%", "比上周", "success")}${pMetric("漏带", "-2", "小书包改善", "success")}${pMetric("睡前", "21:18", "平均上床前准备", "ai")}</section>${pDecisionList([["数学口算连续 4 天完成", "进入周报摘要", "success", "dailyReportDetail"], ["小书包漏带风险下降", "水杯仍需提醒", "warning", "packing"], ["睡前自由聊天建议继续限制", "规则稳定", "ai", "conversation"]])}` });
  },

  points() {
    const stage = Math.floor(state.pointBalance / state.pointThreshold);
    return pShell({ kicker: "积分与奖励", title: `${state.pointBalance} ${state.pointUnit} 可用`, subtitle: "奖励由家长确认，AI 不会承诺。", back: "my", body: `${pBentoCard({ cls: "hero reward", status: pStatus(`阶段 ${stage}`, "warning", "gift"), title: "奖励余额", desc: `每 ${state.pointThreshold} ${state.pointUnit} 一个阶段。`, action: pActionRow([["家长主动兑换", 'data-sheet="manualReward"', "primary"], ["阶段规则", 'data-sheet="pointRule"', "secondary"]]) })}${state.milestoneHandled ? "" : pInlineState({ kind: "warning", title: `${state.pointUnit}已积满`, body: "可以现在兑换奖品，也可以继续累积。", actions: [["选择奖品", 'data-sheet="manualReward"', "primary"], ["继续累积", 'data-action="milestone-continue"', "secondary"]] })}${pSettingsGroup("奖励", [["gift", "奖励商店", `${rewardOptions().length} 个奖品可选`, "reward", "warning"], ["chart-line", "奖励流水", state.lastManualReward || "暂无兑换", "points", "info"]])}` });
  },

  reward() {
    return pShell({ kicker: "奖励商店", title: "奖励是家长承诺，不是 AI 承诺", subtitle: "孩子申请后需要家长确认。", back: "points", body: `${premiumViews.rewardRequest().match(/<section class="p-state-hero[\s\S]*?<\/section>/)?.[0] || ""}<section class="p-decision-list">${rewardOptions().map((item) => `<button class="p-evidence-card info" data-action="manual-reward-open" data-reward="${item.key}"><span>${icon("gift", "w-4 h-4")}</span><div><strong>${item.title}</strong><small>${item.desc} · ${pointUnitAmount(item.cost)}</small></div><b class="status-tag info">兑换</b></button>`).join("")}</section><button class="auth-secondary" data-sheet="rewardEdit">新增奖励</button>` });
  },

  rewardRequest() {
    const [label, tone] = rewardLabel();
    return pStatePage({ kind: tone === "danger" ? "warning" : tone, title: `${childName()} 申请兑换周末户外活动`, body: `状态：${label}。当前余额 ${state.pointBalance}，该奖励需要 20 ${state.pointUnit}。`, back: "points", actions: [["同意兑现", 'data-action="reward-fulfilled"', "primary"], ["同意稍后", 'data-action="reward-planned"', "secondary"], ["暂不兑换", 'data-sheet="rewardReject"', "danger"]] });
  },

  rewardApproved() {
    return pStatePage({ kind: "success", title: "奖励已同意兑现", body: "积分已扣除，孩子端收到温和确认。", back: "reward", actions: [["查看流水", 'data-nav="points"', "primary"]] });
  },

  rewardRejected() {
    return pStatePage({ kind: "warning", title: "奖励暂不兑换", body: "孩子端只会收到温和反馈，不显示拒绝理由。", back: "reward", actions: [["返回奖励", 'data-nav="reward"', "primary"]] });
  },

  moments() {
    return pShell({ kicker: "成长时刻", title: "只收藏积极片段", subtitle: "家长可隐藏、删除或分享给家庭成员。", back: "my", body: pDecisionList([["主动整理桌面", "可收藏到周报", "success", "moments"], ["读完睡前故事", "只保存摘要", "ai", "dailyReportDetail"]]) + pActionRow([["收藏", 'data-sheet="moment"', "primary"], ["管理隐私", 'data-nav="privacySettings"', "secondary"]]) });
  },

  checkin() {
    return pStatePage({ kind: "warning", title: "朗读打卡待审核", body: "检测到 10 分钟朗读声音，但有 2 分钟背景噪音较高。", back: "my", actions: [["通过", 'data-toast="已通过打卡"', "primary"], ["要求重拍", 'data-toast="已要求重拍"', "danger"]] });
  },

  componentStates() {
    return pShell({
      kicker: "组件状态实验台",
      title: "全局状态覆盖",
      subtitle: "按钮、chips、证据卡、AI 卡、空错加载、危险确认。",
      back: "my",
      body: `
        ${pBentoCard({ title: "按钮状态", desc: "default / pressed / disabled / loading / success / danger", children: `<div class="p-button-demo"><button class="p-button primary">Default</button><button class="p-button secondary">Secondary</button><button class="p-button" disabled>Disabled</button><button class="p-button loading"><span class="loading-dot blue"></span>Loading</button><button class="p-button danger">Danger</button></div>` })}
        ${pAiCard({ title: "AI 解释卡", body: "所有 AI 建议都有置信度、证据和家长确认入口。", actions: [["确认", 'data-toast="已确认"', "primary"], ["误报", 'data-sheet="falseAlarm"', "danger"]] })}
        ${pDecisionList([["Loading skeleton", "见 reportLoading", "info", "reportLoading"], ["Empty state", "见 reportEmpty", "info", "reportEmpty"], ["Danger confirm", "见删除数据", "danger", "dataDeletion"]])}
      `,
    });
  },
};

Object.entries(premiumViewAliases).forEach(([alias, target]) => {
  premiumViews[alias] = () => premiumViews[target] ? premiumViews[target]() : views[target]();
});

Object.assign(views, premiumViews);

setupRoutes.push("loginError", "verifyError", "verifyLoading", "newUserBranch", "returningUserBranch", "setupChildError", "setupDeviceFailed", "setupPermissionsFailed", "setupComplete");
routeGroups.home.push("homeAbnormal", "todayStatusDetail", "pendingDecisions", "aiSuggestionDetail", "evidencePreview", "dailyReportDetail", "reportLoading", "reportEmpty");
routeGroups.tasks.push("taskConfirm", "taskTimeout", "taskFailed", "taskEmpty", "taskSearchNoResult");
routeGroups.watch.push("watchPrivacyPaused", "watchLowConfidence", "realtimeDetail", "aiJudgementDetail", "evidenceExplain");
routeGroups.my.push("childProfile", "permissionManagement", "dataDeletion", "rewardRequest", "rewardApproved", "rewardRejected", "dailyReportDetail", "reportLoading", "reportEmpty", "componentStates", "systemNotification", "deviceNotification", "taskNotification", "safetyNotification", "unread", "processing", "resolved", "falseAlarm");

function showToast(message) {
  const id = `toast-${Date.now()}`;
  toastLane.insertAdjacentHTML(
    "beforeend",
    `<div id="${id}" class="toast">${icon("check-circle", "w-4 h-4")}<span>${message}</span></div>`,
  );
  if (window.lucide) window.lucide.createIcons();
  setTimeout(() => document.getElementById(id)?.remove(), 2600);
}

function closeActiveLayer() {
  state.sheet = "";
  state.modal = "";
}

function handleAction(target) {
  const action = target.dataset.action;
  if (!action) return false;

  if (action === "parent-role") {
    const role = target.dataset.role || state.parentRole;
    state.parentRole = role;
    if (!state.parentName || ["妈妈", "爸爸", "祖辈", "其他家人"].includes(state.parentName)) state.parentName = role;
    render();
    return true;
  }

  if (action === "boundary-level") {
    state.boundaryLevel = target.dataset.level || state.boundaryLevel;
    render();
    showToast(`已切换为${state.boundaryLevel}模式`);
    return true;
  }

  if (action === "day-template-apply") {
    closeActiveLayer();
    state.selectedDay = "今天";
    goTo("tasks");
    showToast("已套用推荐任务模板");
    return true;
  }

  if (action === "task-day") {
    state.selectedDay = target.dataset.dayLabel || state.selectedDay;
    closeActiveLayer();
    goTo("tasks");
    showToast(`已切换到${state.selectedDay}`);
    return true;
  }

  if (action === "time-select") {
    state.taskDraft.start = target.dataset.time || state.taskDraft.start;
    closeActiveLayer();
    goTo("taskEdit");
    showToast(`开始时间已改为 ${state.taskDraft.start}`);
    return true;
  }

  if (action.startsWith("evidence-")) {
    const next = action === "evidence-confirm" ? "confirmed" : action === "evidence-partial" ? "partial" : "rejected";
    state.evidenceStatus = next;
    if (next === "confirmed") state.pointBalance += Number(state.taskDraft.reward || 3);
    closeActiveLayer();
    goTo("taskEvidence");
    showToast(next === "confirmed" ? "已确认完成，积分已入账" : next === "partial" ? "已标记部分完成" : "已标记误报/驳回");
    return true;
  }

  if (action === "task-delay") {
    closeActiveLayer();
    goTo("taskDetail");
    showToast("已延后 10 分钟并同步设备");
    return true;
  }

  if (action === "task-end") {
    state.evidenceStatus = "pending";
    closeActiveLayer();
    goTo("taskEvidence");
    showToast("已结束任务，正在生成证据");
    return true;
  }

  if (action === "flow-remind") {
    closeActiveLayer();
    showToast("已发送温和提醒");
    return true;
  }

  if (action === "open-sleep") {
    closeActiveLayer();
    goTo("sleep");
    return true;
  }

  if (action.startsWith("reward-")) {
    const next = action.replace("reward-", "");
    state.rewardStatus = next === "fulfilled" ? "fulfilled" : next === "planned" ? "planned" : "rejected";
    if (next === "fulfilled" && !state.childRewardDeducted) {
      state.pointBalance = Math.max(0, state.pointBalance - 20);
      state.childRewardDeducted = true;
      state.lastManualReward = `语音申请：周末户外活动 -${pointUnitAmount(20)}`;
    }
    closeActiveLayer();
    goTo("reward");
    showToast(next === "fulfilled" ? "奖励已兑现并扣除积分" : next === "planned" ? "已同意稍后兑现" : "已暂不兑换");
    return true;
  }

  if (action === "manual-reward-select" || action === "manual-reward-open") {
    state.manualRewardKey = target.dataset.reward || state.manualRewardKey;
    state.sheet = "manualReward";
    render();
    return true;
  }

  if (action === "manual-reward-confirm") {
    const reward = selectedReward();
    if (!reward) return true;
    if (state.pointBalance < reward.cost) {
      showToast(`${state.pointUnit}不足，先继续累积`);
      return true;
    }
    state.pointBalance -= reward.cost;
    state.lastManualReward = `${reward.title} -${pointUnitAmount(reward.cost)}`;
    state.milestoneHandled = false;
    closeActiveLayer();
    goTo("points");
    showToast(`已兑换 ${reward.title}`);
    return true;
  }

  if (action === "point-unit") {
    state.pointUnit = target.dataset.unit || state.pointUnit;
    render();
    return true;
  }

  if (action === "milestone-continue") {
    state.milestoneHandled = true;
    closeActiveLayer();
    goTo("points");
    showToast("已继续累积");
    return true;
  }

  if (action === "point-rule-save") {
    const nextThreshold = Number(state.pointThresholdDraft);
    if (!Number.isInteger(nextThreshold) || nextThreshold < 1) {
      showToast("请输入阶段阈值");
      return true;
    }
    state.pointThreshold = Math.min(999, nextThreshold);
    closeActiveLayer();
    goTo("points");
    showToast("阶段规则已保存");
    return true;
  }

  if (action === "reward-save") {
    const title = state.rewardDraftName.trim();
    const cost = Number(state.rewardDraftCost);
    if (!title || !cost) {
      showToast("请填写奖品名称和所需数量");
      return true;
    }
    if (state.rewardEditingKey) {
      state.rewardItems = state.rewardItems.map((item) => (item.key === state.rewardEditingKey ? { ...item, title, cost } : item));
    } else {
      const key = `custom-${Date.now()}`;
      state.rewardItems = [...state.rewardItems, { key, title, cost, desc: "家长新增奖励", tone: "blue" }];
      state.manualRewardKey = key;
    }
    closeActiveLayer();
    goTo("reward");
    showToast(state.rewardEditingKey ? "奖励已修改" : "奖励已添加");
    return true;
  }

  if (action === "packing-status") {
    const item = target.dataset.item;
    if (item) state.packingStatus[item] = target.dataset.status || "done";
    render();
    showToast("小书包状态已更新");
    return true;
  }

  if (action === "packing-add") {
    const item = (state.packingDraft || "").trim();
    if (item && !state.packingExtra.includes(item)) state.packingExtra.push(item);
    state.packingDraft = "跳绳";
    closeActiveLayer();
    goTo("packing");
    showToast("已添加到小书包");
    return true;
  }

  if (action === "packing-extra-remove") {
    const index = Number(target.dataset.index);
    state.packingExtra = state.packingExtra.filter((_, itemIndex) => itemIndex !== index);
    render();
    showToast("已移除临时物品");
    return true;
  }

  const toastActions = {
    "zone-save": "已开始自定义安全区域",
    "moment-save": "已收藏成长时刻",
    "call-child": "正在发起音频通话",
    "alert-resolve": "已标记处理完成",
    "alert-false": "已标记误报",
    "safety-test": "测试通知已发送",
    "toggle-remote-hint": "远程查看提示已保持开启",
    "delete-data": "已提交删除申请",
    "unbind-device": "已进入管理员确认",
    "change-phone": "手机号已更新",
    "remove-login-device": "已移除备用登录设备",
    logout: "已退出登录",
    "subscription-read": "已了解订阅降级说明",
    "ai-rule-save": "AI 规则已保存",
  };
  if (toastActions[action]) {
    if (action === "alert-resolve") state.alertStatus = "resolved";
    if (action === "alert-false") state.alertStatus = "false";
    closeActiveLayer();
    render();
    showToast(toastActions[action]);
    return true;
  }

  return false;
}

document.addEventListener("click", (event) => {
  const closeLayer = event.target.closest("[data-close-layer]");
  if (closeLayer) {
    closeActiveLayer();
    render();
    return;
  }

  const close = event.target.closest("[data-close]");
  if (close) {
    closeActiveLayer();
    render();
    return;
  }

  const action = event.target.closest("[data-action]");
  if (action && handleAction(action)) return;

  const sheet = event.target.closest("[data-sheet]");
  if (sheet) {
    state.sheet = sheet.dataset.sheet;
    state.createOpen = false;
    render();
    return;
  }

  const confirm = event.target.closest("[data-confirm]");
  if (confirm) {
    const message = confirm.dataset.confirm || "操作已完成";
    state.sheet = "";
    state.modal = "";
    state.formStatus = "saved";
    render();
    showToast(message.includes("误报") ? "已标记误报" : message.includes("解绑") ? "已提交管理员确认" : "操作已记录");
    return;
  }

  const saveChild = event.target.closest("[data-save-child]");
  if (saveChild) {
    state.setupError = "";
    const name = state.childDraft.name.trim();
    if (!name) {
      state.setupError = "请输入孩子称呼";
      render();
      return;
    }
    state.setupSaving = true;
    render();
    setTimeout(() => {
      state.childProfile.name = name;
      state.childProfile.age = `${state.childDraft.age || 8} 岁`;
      state.childProfile.relation = parentLabel();
      state.childProfile.stage = state.childDraft.stage || "小学";
      state.childProfile.grade = state.childDraft.grade || "二年级";
      state.childProfile.className = state.childDraft.className || "";
      state.setupSaving = false;
      showToast("孩子资料已保存");
      goTo("setupName");
    }, 620);
    return;
  }

  const startBinding = event.target.closest("[data-start-binding]");
  if (startBinding) {
    state.bindingStatus = "loading";
    render();
    setTimeout(() => {
      state.bindingStatus = "success";
      showToast("设备已识别");
      goTo("setupWifi");
    }, 900);
    return;
  }

  const bindFail = event.target.closest("[data-bind-fail]");
  if (bindFail) {
    state.bindingStatus = "failed";
    render();
    showToast("暂未发现设备");
    return;
  }

  const permission = event.target.closest("[data-permission]");
  if (permission) {
    if (permission.dataset.permission === "camera") {
      state.permissionDenied = !state.permissionDenied;
      render();
      showToast(state.permissionDenied ? "已模拟权限拒绝" : "相机权限已允许");
      return;
    }
    showToast("权限设置已更新");
    return;
  }

  const saveForm = event.target.closest("[data-save-form]");
  if (saveForm) {
    if (saveForm.dataset.saveForm === "invalid") {
      showToast("请先补全必填信息");
      return;
    }
    state.formStatus = "saving";
    render();
    setTimeout(() => {
      state.formStatus = "saved";
      render();
      showToast(saveForm.dataset.saveForm === "task" ? "任务已保存" : saveForm.dataset.saveForm === "privacy" ? "隐私设置已保存" : "设置已保存");
    }, 720);
    return;
  }

  const alertFilter = event.target.closest("[data-alert-filter]");
  if (alertFilter) {
    state.alertFilter = alertFilter.dataset.alertFilter;
    render();
    return;
  }

  const taskFilter = event.target.closest("[data-task-filter]");
  if (taskFilter) {
    state.taskFilter = taskFilter.dataset.taskFilter;
    render();
    showToast(`已筛选${taskFilter.textContent.trim()}任务`);
    return;
  }

  const onboardIndex = event.target.closest("[data-onboard-index]");
  if (onboardIndex) {
    state.onboardingIndex = Number(onboardIndex.dataset.onboardIndex);
    render();
    return;
  }

  const onboard = event.target.closest("[data-onboard]");
  if (onboard) {
    const direction = onboard.dataset.onboard;
    if (direction === "prev") {
      state.onboardingIndex = Math.max(0, state.onboardingIndex - 1);
      render();
      return;
    }
    if (state.onboardingIndex >= onboardingSlides.length - 1) {
      goTo("login");
      return;
    }
    state.onboardingIndex += 1;
    render();
    return;
  }

  const nav = event.target.closest("[data-nav]");
  if (nav) {
    const toast = nav.dataset.toast;
    if (toast) showToast(toast);
    if (!views[nav.dataset.nav]) return;
    state.sheet = "";
    state.modal = "";
    goTo(nav.dataset.nav);
    return;
  }

  const authBack = event.target.closest("[data-auth-back]");
  if (authBack) {
    state.verifyError = "";
    state.verifyCode = "";
    goTo("login");
    return;
  }

  const sendCode = event.target.closest("[data-send-code]");
  if (sendCode) {
    const phone = digitsOnly(state.phone);
    state.loginError = "";
    state.agreementError = "";
    if (!phone) state.loginError = "请输入手机号";
    else if (!isValidPhone(phone)) state.loginError = "请输入正确的 11 位手机号";
    else if (!state.agreed) state.agreementError = "请先勾选用户协议和隐私政策";
    if (state.loginError || state.agreementError) {
      render();
      return;
    }

    state.loginLoading = true;
    render();
    setTimeout(() => {
      state.loginLoading = false;
      if (phone.endsWith("0000")) {
        state.loginError = "网络异常，请稍后再试";
        render();
        showToast("网络异常，请检查连接");
        return;
      }
      state.verifyPhone = phone;
      state.verifyCode = "";
      state.verifyError = "";
      goTo("verify");
      startResendCountdown();
      showToast("验证码已发送");
    }, 720);
    return;
  }

  const verifyCode = event.target.closest("[data-verify-code]");
  if (verifyCode) {
    state.verifyError = "";
    if (!state.verifyCode) state.verifyError = "请输入验证码";
    else if (state.verifyCode.length !== 6) state.verifyError = "请输入 6 位验证码";
    if (state.verifyError) {
      render();
      return;
    }

    state.verifyLoading = true;
    render();
    setTimeout(() => {
      state.verifyLoading = false;
      if (state.verifyCode !== "123456") {
        state.verifyError = "验证码错误，请重新输入";
        render();
        showToast("验证码错误");
        return;
      }
      if (isKnownParent(state.verifyPhone)) {
        showToast("验证成功，欢迎回来");
        goTo("home");
      } else {
        showToast("已为你创建家长账户");
        goTo("setup");
      }
    }, 820);
    return;
  }

  const resend = event.target.closest("[data-resend-code]");
  if (resend) {
    if (state.resendLeft > 0) return;
    state.verifyError = "";
    startResendCountdown();
    showToast("验证码已重新发送");
    return;
  }

  const day = event.target.closest("[data-day]");
  if (day) {
    state.selectedDay = day.dataset.day;
    showToast(`已切换到${state.selectedDay}`);
    render();
    return;
  }

  const create = event.target.closest("[data-create-toggle]");
  if (create) {
    state.createOpen = !state.createOpen;
    render();
    return;
  }

  const toast = event.target.closest("[data-toast]");
  if (toast) {
    showToast(toast.dataset.toast);
  }
});

document.addEventListener("keydown", (event) => {
  if (state.view === "welcome" && event.key === "ArrowLeft") {
    state.onboardingIndex = Math.max(0, state.onboardingIndex - 1);
    render();
    return;
  }

  if (state.view === "welcome" && event.key === "ArrowRight") {
    if (state.onboardingIndex >= onboardingSlides.length - 1) {
      goTo("login");
      return;
    } else {
      state.onboardingIndex += 1;
    }
    render();
    return;
  }

  if (event.key !== "Escape") return;
  if (state.createOpen) {
    state.createOpen = false;
    render();
  }
});

document.addEventListener("input", (event) => {
  const parentNameInput = event.target.closest("[data-parent-name]");
  if (parentNameInput) {
    state.parentName = parentNameInput.value;
    state.childProfile.relation = parentNameInput.value || state.parentRole;
    return;
  }

  const childNameInput = event.target.closest("[data-child-name]");
  if (childNameInput) {
    state.childDraft.name = childNameInput.value;
    state.setupError = "";
    return;
  }

  const childAge = event.target.closest("[data-child-age]");
  if (childAge) {
    state.childDraft.age = digitsOnly(childAge.value).slice(0, 2);
    childAge.value = state.childDraft.age;
    return;
  }

  const childRelation = event.target.closest("[data-child-relation]");
  if (childRelation) {
    state.childDraft.relation = childRelation.value;
    return;
  }

  const childStage = event.target.closest("[data-child-stage]");
  if (childStage) {
    state.childDraft.stage = childStage.value;
    return;
  }

  const childGrade = event.target.closest("[data-child-grade]");
  if (childGrade) {
    state.childDraft.grade = childGrade.value;
    return;
  }

  const childClass = event.target.closest("[data-child-class]");
  if (childClass) {
    state.childDraft.className = childClass.value;
    return;
  }

  const wakeName = event.target.closest("[data-wake-name]");
  if (wakeName) {
    state.wakeName = wakeName.value;
    return;
  }

  const contactName = event.target.closest("[data-contact-name]");
  if (contactName) {
    state.contactDraft.name = contactName.value;
    return;
  }

  const contactPhone = event.target.closest("[data-contact-phone]");
  if (contactPhone) {
    state.contactDraft.phone = digitsOnly(contactPhone.value).slice(0, 11);
    contactPhone.value = state.contactDraft.phone;
    return;
  }

  const taskTitle = event.target.closest("[data-task-title]");
  if (taskTitle) {
    state.taskDraft.title = taskTitle.value;
    state.formStatus = "default";
    const button = screen.querySelector("[data-save-form]");
    if (button) button.disabled = !state.taskDraft.title.trim();
    return;
  }

  const taskReward = event.target.closest("[data-task-reward]");
  if (taskReward) {
    state.taskDraft.reward = digitsOnly(taskReward.value).slice(0, 2);
    taskReward.value = state.taskDraft.reward;
    return;
  }

  const taskSearch = event.target.closest("[data-task-search]");
  if (taskSearch) {
    state.taskSearch = taskSearch.value;
    return;
  }

  const pointThreshold = event.target.closest("[data-point-threshold]");
  if (pointThreshold) {
    state.pointThresholdDraft = digitsOnly(pointThreshold.value).slice(0, 3);
    pointThreshold.value = state.pointThresholdDraft;
    return;
  }

  const rewardName = event.target.closest("[data-reward-name]");
  if (rewardName) {
    state.rewardDraftName = rewardName.value;
    return;
  }

  const rewardCost = event.target.closest("[data-reward-cost]");
  if (rewardCost) {
    state.rewardDraftCost = digitsOnly(rewardCost.value).slice(0, 3);
    rewardCost.value = state.rewardDraftCost;
    return;
  }

  const packingDraft = event.target.closest("[data-packing-draft]");
  if (packingDraft) {
    state.packingDraft = packingDraft.value;
    return;
  }

  const phoneInput = event.target.closest("[data-phone-input]");
  if (phoneInput) {
    state.phone = digitsOnly(phoneInput.value).slice(0, 11);
    phoneInput.value = state.phone;
    state.loginError = "";
    state.agreementError = "";
    const button = screen.querySelector("[data-send-code]");
    if (button) button.disabled = !(isValidPhone(state.phone) && state.agreed) || state.loginLoading;
    return;
  }

  const codeInput = event.target.closest("[data-code-input]");
  if (codeInput) {
    state.verifyCode = digitsOnly(codeInput.value).slice(0, 6);
    state.verifyError = "";
    render();
    requestAnimationFrame(() => screen.querySelector("[data-code-input]")?.focus());
  }
});

document.addEventListener("change", (event) => {
  const agreement = event.target.closest("[data-agree]");
  if (!agreement) return;
  state.agreed = agreement.checked;
  state.agreementError = "";
  const button = screen.querySelector("[data-send-code]");
  if (button) button.disabled = !(isValidPhone(state.phone) && state.agreed) || state.loginLoading;
});

document.addEventListener(
  "focusout",
  (event) => {
    const phoneInput = event.target.closest("[data-phone-input]");
    if (!phoneInput) return;
    const phone = digitsOnly(phoneInput.value);
    if (!phone) state.loginError = "请输入手机号";
    else if (!isValidPhone(phone)) state.loginError = "请输入正确的 11 位手机号";
    if (state.loginError) render();
  },
  true,
);

const initial = location.hash.replace("#", "");
if (views[initial]) state.view = initial;
if (state.view === "verify" && !state.verifyPhone) {
  state.verifyPhone = "13800138000";
  state.phone = state.verifyPhone;
}
render();
if (state.view === "verify") startResendCountdown();
