const refs = {
  study:
    "https://images.unsplash.com/photo-1758612898114-4b1504db79a7?auto=format&fit=crop&w=1000&q=82",
  room:
    "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?auto=format&fit=crop&w=1000&q=82",
  desk:
    "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=1000&q=82",
  bedtime:
    "https://images.unsplash.com/photo-1616627561950-9f746e330187?auto=format&fit=crop&w=1000&q=82",
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
  },
  childDraft: {
    name: "小宇",
    age: "8",
    relation: "妈妈",
  },
  taskDraft: {
    title: "英语朗读 10 分钟",
    start: "20:10",
    reward: "3",
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
          <b>1 / 5</b>
        </header>
        <section class="setup-hero-panel">
          <span class="setup-icon">${icon("home", "w-6 h-6")}</span>
          <h1>先把家庭看护基础搭好</h1>
          <p>接下来会依次完成孩子资料、设备绑定、权限授权和隐私边界。未完成前不会开启远程看护。</p>
          <div class="setup-checks">
            <span>${icon("user-round-plus", "w-4 h-4")}孩子档案</span>
            <span>${icon("camera", "w-4 h-4")}设备绑定</span>
            <span>${icon("shield-check", "w-4 h-4")}隐私权限</span>
          </div>
        </section>
        <section class="setup-actions">
          <button class="auth-primary" type="button" data-nav="setupChild">开始设置</button>
          <button class="auth-secondary" type="button" data-nav="home">稍后进入首页预览</button>
        </section>
      </section>
    `;
  },

  setupChild() {
    return `
      <section class="setup-flow form-flow">
        ${backHeader("孩子资料", "用于任务、证据和告警文案，后续可在我的页修改。", "setupStart")}
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
              <span>你的身份</span>
              <input data-child-relation maxlength="8" value="${state.childDraft.relation}" />
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
            ${state.setupSaving ? `<span class="loading-dot"></span>保存中...` : "保存并继续"}
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
        ${backHeader("设备绑定", "扫码或蓝牙发现设备，绑定后再配置权限。", "setupChild")}
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

  setupPermissions() {
    return `
      <section class="setup-flow">
        ${backHeader("权限授权", "只开启必要权限，家长可随时在设置里修改。", "setupDevice")}
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

  setupPrivacy() {
    return `
      <section class="setup-flow">
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
    return `
      <section class="scene app-page evidence-page">
        ${backHeader("任务证据", "等待家长确认", "taskDetail")}
        <section class="evidence-media">
          <img src="${refs.study}" alt="孩子在书桌前完成任务的证据截图" />
          <span class="capsule">${icon("file-check-2", "w-3.5 h-3.5")}AI 证据片段</span>
        </section>
        <section class="detail-sheet inline">
          <section class="live-panel">
            <div class="ai-bubble-head"><span class="ai-mark">${icon("sparkles", "w-4 h-4")}</span><div><strong>AI 判断：完成度较高</strong><small>置信度 88% · 仍需家长确认</small></div></div>
            <p class="mt-3 text-[13px] font-semibold leading-6 text-[#697A89]">检测到书写动作持续 22 分钟，离席 1 次 40 秒。建议确认完成，并允许奖励积分自动入账。</p>
            <div class="decision-actions">
              <button class="auth-primary" data-sheet="confirmEvidence">确认完成</button>
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
    return `
      <section class="scene app-page">
        ${backHeader("奖励申请", "需要家长确认", "home")}
        ${stateCard("warning", `${childName()} 申请兑换 20 积分`, "来源：本周 4 次任务完成。当前余额 46，兑换后剩余 26。", `<div class="chip-row center"><button class="chip primary" data-sheet="rewardApprove">同意兑现</button><button class="chip" data-toast="已安排周末提醒">同意稍后</button><button class="chip danger" data-sheet="rewardReject">暂不兑换</button></div>`)}
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
          <div class="settings-group"><h3>报告与奖励</h3>${[
            ["report", "file-text", "今日报告", "结论、证据和待处理建议"],
            ["points", "gift", "积分奖励", "奖励申请、商店和流水"],
            ["checkin", "badge-check", "打卡审核", "素材通过后再发奖励"],
          ].map(([route, ico, title, desc]) => `<button class="settings-row" data-nav="${route}"><span>${icon(ico, "w-4 h-4")}</span><div><strong>${title}</strong><small>${desc}</small></div>${icon("chevron-right", "w-4 h-4")}</button>`).join("")}</div>
          <div class="settings-group"><h3>看护与规则</h3>${[
            ["deviceSettings", "camera", "设备管理", "网络、固件、解绑和房间视角"],
            ["aiRules", "bot", "AI 规则", "任务判断、自由聊天和睡前限制"],
            ["privacySettings", "lock-keyhole", "隐私与数据", "远程查看边界、数据删除"],
            ["education", "book-open", "学习内容", "小书包和任务模板"],
          ].map(([route, ico, title, desc]) => `<button class="settings-row" data-nav="${route}"><span>${icon(ico, "w-4 h-4")}</span><div><strong>${title}</strong><small>${desc}</small></div>${icon("chevron-right", "w-4 h-4")}</button>`).join("")}</div>
          <div class="settings-group"><h3>账号与通知</h3>${[
            ["notificationSettings", "bell-ring", "通知设置", "告警、任务、奖励申请"],
            ["subscription", "credit-card", "订阅套餐", "设备数、回放和家庭权益"],
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

  packing() {
    return `
      <section class="scene app-page">
        ${backHeader("小书包", "明早出门前确认", "tasks")}
        <section class="detail-hero soft-blue"><span class="capsule blue">${icon("backpack", "w-3.5 h-3.5")}3 项待确认</span><h2>数学本、水杯、红领巾</h2><p>设备在线时，米拉会在孩子整理书包时轻提醒，不会持续录像。</p><button class="auth-primary" data-toast="已标记水杯完成">标记水杯已放入</button></section>
        <section class="settings-group"><h3>清单</h3>${["数学本 · 待放入", "水杯 · 待确认", "红领巾 · 已完成", "美术材料 · 明天需要"].map((item, i) => `<button class="settings-row ${i === 2 ? "success" : ""}" data-toast="${item}"><span>${icon(i === 2 ? "check" : "circle", "w-4 h-4")}</span><div><strong>${item}</strong><small>${i === 2 ? "孩子已确认" : "明早 7:40 前提醒"}</small></div>${icon("chevron-right", "w-4 h-4")}</button>`).join("")}</section>
      </section>
    `;
  },

  sleep() {
    return `
      <section class="scene app-page">
        ${backHeader("睡眠晨起", "睡前少打扰，晨起看结果", "tasks")}
        <section class="timer-card"><span>睡前流程</span><strong>21:10</strong><p>洗漱、整理桌面、关闭自由聊天。</p><div class="chip-row center"><button class="chip primary" data-toast="睡前提醒已开启">开启提醒</button><button class="chip" data-sheet="delayTask">延后 15 分钟</button></div></section>
        <section class="ai-bubble"><div class="ai-bubble-head"><span class="ai-mark">${icon("moon", "w-4 h-4")}</span><div><strong>AI 建议：今晚不要加任务</strong><small>根据今日任务时长</small></div></div><p>20:35 后只保留小书包和睡前流程，避免把学习任务压到睡前。</p></section>
      </section>
    `;
  },

  playback() {
    return `
      <section class="scene app-page">
        ${backHeader("事件回放", "只保留必要片段", "watch")}
        <section class="filter-row"><button class="active">全部</button><button>任务证据</button><button>安全事件</button><button>收藏</button></section>
        <section class="alert-list">${[
          ["任务证据", "数学口算完成片段", "22 分钟 · 待确认", "taskEvidence"],
          ["安全事件", "门口异常声音", "12 秒 · 未读", "alertDetail"],
          ["成长时刻", "主动整理书桌", "已收藏", "moments"],
        ].map(([type, title, desc, route]) => `<button class="alert-item" data-nav="${route}"><span>${icon("play", "w-4 h-4")}</span><div><small>${type}</small><strong>${title}</strong><p>${desc}</p></div>${icon("chevron-right", "w-4 h-4")}</button>`).join("")}</section>
      </section>
    `;
  },

  zones() {
    return `
      <section class="scene app-page">
        ${backHeader("安全区域", "只提醒真正需要家长判断的边界", "watch")}
        <section class="device-card-large"><img src="${refs.room}" alt="家庭安全区域示意" /><div><span class="capsule blue">书房 + 门口</span><h2>2 个区域已启用</h2><p>离开书桌超过 8 分钟才会进入待确认，不打断正常活动。</p></div></section>
        <section class="settings-group"><button class="settings-row" data-sheet="zoneSheet"><span>${icon("map", "w-4 h-4")}</span><div><strong>书桌专注区</strong><small>任务期间离开 8 分钟提醒</small></div>${icon("chevron-right", "w-4 h-4")}</button><button class="settings-row warning" data-sheet="zoneSheet"><span>${icon("door-open", "w-4 h-4")}</span><div><strong>门口安全区</strong><small>异常声音 + 人形才升级告警</small></div>${icon("chevron-right", "w-4 h-4")}</button></section>
      </section>
    `;
  },

  report() {
    return `
      <section class="scene app-page">
        ${backHeader("今日报告", "先看结论，再看证据", "my")}
        <section class="detail-hero soft-blue"><span class="capsule ai">${icon("sparkles", "w-3.5 h-3.5")}AI 摘要</span><h2>今天整体稳定</h2><p>完成 2 个任务，1 个奖励申请待确认，安全事件 1 条已归档。</p><button class="auth-primary" data-nav="taskEvidence">查看关键证据</button></section>
        <section class="summary-strip app-summary"><button class="summary-unit"><strong>2/3</strong><span>任务完成</span></button><button class="summary-unit"><strong>1</strong><span>安全事件</span></button><button class="summary-unit"><strong>+8</strong><span>积分</span></button></section>
      </section>
    `;
  },

  weekly() {
    return `
      <section class="scene app-page">
        ${backHeader("周报", "趋势与家长建议", "my")}
        ${stateCard("success", "本周任务节奏更稳定", "平均开始时间提前 11 分钟，睡前打扰减少 2 次。建议下周继续保留小书包检查。", `<button class="auth-primary" data-toast="周报已分享给家庭成员">分享周报</button>`)}
      </section>
    `;
  },

  moments() {
    return `
      <section class="scene app-page">
        ${backHeader("成长时刻", "由家长收藏，不自动公开", "my")}
        <section class="h-scroll">${["主动整理书桌", "按时完成朗读", "睡前自己收书包"].map((title) => `<button class="story-tile blue" data-toast="${title}"><span class="capsule blue">${icon("star", "w-3.5 h-3.5")}已收藏</span><h4>${title}</h4><p>来自任务证据和家长确认。</p></button>`).join("")}</section>
      </section>
    `;
  },

  points() {
    return `
      <section class="scene app-page">
        ${backHeader("积分奖励", "奖励需要家长确认", "my")}
        <section class="timer-card"><span>当前余额</span><strong>46</strong><p>本周已增加 8 分，待确认奖励申请 1 个。</p><div class="chip-row center"><button class="chip primary" data-nav="taskReward">处理申请</button><button class="chip" data-nav="rewardShop">奖励商店</button></div></section>
      </section>
    `;
  },

  rewardShop() {
    return `
      <section class="scene app-page">
        ${backHeader("奖励商店", "由家长管理奖品", "points")}
        <section class="alert-list">${["周末户外活动 · 20 分", "多 15 分钟阅读灯 · 8 分", "家庭电影夜 · 30 分"].map((item) => `<button class="alert-item" data-sheet="rewardApprove"><span>${icon("gift", "w-4 h-4")}</span><div><small>可兑换奖励</small><strong>${item}</strong><p>兑换需要家长确认。</p></div>${icon("chevron-right", "w-4 h-4")}</button>`).join("")}</section>
      </section>
    `;
  },

  checkin() {
    return `
      <section class="scene app-page">
        ${backHeader("打卡审核", "证据通过后再发奖励", "my")}
        ${stateCard("warning", "1 条打卡素材待审核", "孩子提交了英语朗读打卡，AI 只判断音量和时长，是否通过由家长确认。", `<div class="chip-row center"><button class="chip primary" data-toast="打卡已通过">通过</button><button class="chip danger" data-toast="已要求重拍">重拍</button></div>`)}
      </section>
    `;
  },

  subscription() {
    return `
      <section class="scene app-page">
        ${backHeader("订阅套餐", "当前为家庭基础版", "my")}
        ${stateCard("info", "基础版已足够完成 MVP 流程", "包含 1 台设备、7 天事件回放、任务证据和家庭成员管理。", `<button class="auth-secondary" data-sheet="subscriptionDowngrade">查看权益说明</button>`)}
      </section>
    `;
  },

  education() {
    return `
      <section class="scene app-page">
        ${backHeader("学习内容", "小书包和任务模板", "my")}
        <section class="settings-group"><button class="settings-row" data-nav="packing"><span>${icon("backpack", "w-4 h-4")}</span><div><strong>小书包模板</strong><small>按课程自动生成明日物品</small></div>${icon("chevron-right", "w-4 h-4")}</button><button class="settings-row" data-nav="sleep"><span>${icon("moon", "w-4 h-4")}</span><div><strong>睡前流程模板</strong><small>洗漱、整理、关闭自由聊天</small></div>${icon("chevron-right", "w-4 h-4")}</button></section>
      </section>
    `;
  },
};

function renderOverlay() {
  const titleMap = {
    createTask: ["创建任务", "选择任务类型后进入编辑页。"],
    sleepTask: ["睡前 / 打卡任务", "适合整理书桌、洗漱、睡前阅读。"],
    confirmEvidence: ["确认任务完成", "确认后将进入日报，并按规则发放奖励积分。"],
    partialEvidence: ["标记部分完成", "可以补充说明，避免 AI 误判影响孩子。"],
    rejectEvidence: ["驳回 AI 判断", "本次不会发放奖励，系统会记录为一次纠错样本。"],
    delayTask: ["延后任务", "设备在线时会同步轻提醒。"],
    endTask: ["结束当前任务", "结束后会立即生成证据摘要。"],
    rewardApprove: ["同意兑现奖励", "会扣除积分并记录到奖励流水。"],
    rewardReject: ["暂不兑换", "孩子端会收到温和反馈，不显示拒绝理由。"],
    callChild: ["联系孩子", "发起前设备端会提示远程通话。"],
    resolveAlert: ["标记已处理", "处理记录会进入今日安全日志。"],
    falseAlarm: ["标记误报", "这会帮助 AI 调整后续告警阈值。"],
    unbindDevice: ["确认解绑设备", "解绑后无法查看实时画面和新证据。"],
    privacyMode: ["远程查看提示", "建议保持开启，让孩子知道家长正在查看。"],
    deleteData: ["删除儿童数据", "危险操作，需要管理员二次确认。"],
    aiWarning: ["确认 AI 规则变更", "放宽聊天或记录策略前需要确认边界。"],
    memberRole: ["成员权限", "可设置为管理员、处理告警或仅查看摘要。"],
    changePhone: ["更换手机号", "需要验证码确认新的家长身份。"],
    loginDevices: ["登录设备", "可移除不再使用的设备。"],
    logout: ["退出登录", "不会删除已绑定家庭和设备。"],
    terms: ["用户协议摘要", "正式版会打开完整协议文档。"],
    privacyPolicy: ["隐私政策摘要", "说明儿童音视频数据的采集、保存和删除。"],
    zoneSheet: ["安全区域规则", "区域变更会先保存到 App，设备在线时同步生效。"],
    subscriptionDowngrade: ["套餐权益说明", "当前原型只展示家庭基础版，正式版再接入支付。"],
  };
  const [title, body] = titleMap[state.sheet || state.modal] || ["确认操作", "请确认是否继续。"];
  const danger = ["rejectEvidence", "falseAlarm", "unbindDevice", "deleteData", "logout", "rewardReject"].includes(state.sheet);
  return `
    <div class="overlay-scrim" data-close-layer></div>
    <section class="bottom-sheet ${danger ? "danger" : ""}" role="dialog" aria-modal="true" aria-label="${title}">
      <span class="sheet-handle" aria-hidden="true"></span>
      <h2>${title}</h2>
      <p>${body}</p>
      <div class="sheet-actions">
        ${state.sheet === "createTask" ? `
          <button class="action-row" data-nav="taskEdit">${icon("check-square", "w-4 h-4")}普通任务${icon("chevron-right", "w-4 h-4")}</button>
          <button class="action-row" data-nav="taskEdit">${icon("backpack", "w-4 h-4")}小书包${icon("chevron-right", "w-4 h-4")}</button>
          <button class="action-row" data-nav="taskEdit">${icon("moon", "w-4 h-4")}睡前 / 打卡${icon("chevron-right", "w-4 h-4")}</button>
        ` : `
          <button class="auth-primary ${danger ? "danger" : ""}" data-confirm="${title}">${danger ? "确认继续" : "确认"}</button>
          <button class="auth-secondary" data-close-layer>取消</button>
        `}
      </div>
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

const setupRoutes = ["setup", "setupStart", "setupChild", "setupDevice", "setupPermissions", "setupPrivacy", "setupDone"];

const routeGroups = {
  home: ["home", "homeEmpty", "homeOffline", "homeLoading", "homeError", "permissionDenied"],
  tasks: ["tasks", "taskDetail", "taskEdit", "taskEvidence", "taskRunning", "taskReward", "taskNoResult", "packing", "sleep"],
  watch: ["watch", "watchOffline", "watchAlert", "watchPrivacy", "watchUpdating", "watchAbnormal", "playback", "zones"],
  my: [
    "my",
    "alerts",
    "alertDetail",
    "deviceSettings",
    "privacySettings",
    "aiRules",
    "familySettings",
    "notificationSettings",
    "accountSettings",
    "helpFeedback",
    "report",
    "weekly",
    "moments",
    "points",
    "rewardShop",
    "checkin",
    "subscription",
    "education",
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

const onboardingSlides = [
  {
    asset: "./assets/onboarding/onboarding-01-parent-status.png",
    title: "不用一直盯着屏幕",
    description: "米拉帮你汇总孩子状态、任务进展和需要处理的事。",
    kicker: "状态汇总",
    alt: "家长拿着手机查看孩子状态，AI 摄像头在家庭书房中轻量守护",
  },
  {
    asset: "./assets/onboarding/onboarding-02-child-task.png",
    title: "知道孩子正在做什么",
    description: "当前任务、剩余时间和完成证据，会在需要时整理给家长。",
    kicker: "任务看护",
    alt: "孩子在书桌前专注写作业，旁边有轻量任务进度提示",
  },
  {
    asset: "./assets/onboarding/onboarding-03-evidence-reward.png",
    title: "该你确认时再提醒",
    description: "任务完成、奖励申请、打卡证据，只在需要你判断时出现。",
    kicker: "证据与奖励",
    alt: "家长在手机上确认任务证据和奖励申请",
  },
  {
    asset: "./assets/onboarding/onboarding-04-safety-boundary.png",
    title: "安全提醒有边界",
    description: "异常声音、离开区域、陌生人等事件会提示你，同时保留隐私提醒。",
    kicker: "安全与隐私",
    alt: "孩子在安全区域内，门口和隐私灯提示以柔和方式呈现",
  },
  {
    asset: "./assets/onboarding/onboarding-05-start-family.png",
    title: "开始设置家庭看护",
    description: "先绑定设备并创建孩子档案，再开启任务、看护和安全提醒。",
    kicker: "准备开始",
    alt: "家长、孩子和 AI 摄像头在同一家庭场景中准备开始家庭看护设置",
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
      <button class="fan-action" data-nav="taskEdit" data-toast="已打开小书包任务模板">${icon("backpack")}</button>
      <button class="fan-action" data-sheet="sleepTask">${icon("moon")}</button>
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
          <img class="onboard-illustration" src="${slide.asset}" alt="${slide.alt}" />
          <div class="onboard-float float-status">
            ${icon(state.onboardingIndex === 3 ? "lock-keyhole" : "sparkles", "w-4 h-4")}
            <span>${slide.kicker}</span>
          </div>
          <div class="onboard-float float-ai">
            ${icon("camera", "w-4 h-4")}
            <span>AI 轻量守护</span>
          </div>
        </section>

        <section class="onboard-copy">
          <h1 id="welcome-title">${slide.title}</h1>
          <p>${slide.description}</p>
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
          <p class="auth-eyebrow">家长端 AI 摄像头助手</p>
          <h1 id="login-title">用手机号继续</h1>
          <p>验证家长身份，继续设置家庭看护。</p>
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

          <p class="auth-footnote">未注册手机号验证后将自动创建家长账户。</p>
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
          修改手机号
        </button>

        <section class="auth-copy-block">
          <p class="auth-eyebrow">安全验证</p>
          <h1 id="verify-title">输入验证码</h1>
          <p>已发送至 <strong>+86 ${formatPhone(phone)}</strong></p>
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
          <button class="queue-item urgent" data-toast="已打开数学口算证据">
            <span class="queue-icon">${icon("file-check-2", "w-4 h-4")}</span>
            <span class="queue-copy">
              <strong>数学口算证据即将生成</strong>
              <small>12 分钟后需要确认完成/部分完成/驳回</small>
            </span>
            ${icon("chevron-right", "w-4 h-4")}
          </button>
          <button class="queue-item" data-toast="已打开奖励申请">
            <span class="queue-icon warm">${icon("gift", "w-4 h-4")}</span>
            <span class="queue-copy">
              <strong>小宇申请兑换周末户外活动</strong>
              <small>需要你确认 20 积分奖励是否通过</small>
            </span>
            ${icon("chevron-right", "w-4 h-4")}
          </button>
          <div class="quick-row">
            <button class="chip primary" data-toast="已进入待确认队列">处理待确认</button>
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
          <button class="plan-row" data-toast="已打开小书包检查">
            <span>20:35</span>
            <div>
              <strong>小书包检查</strong>
              <small>水杯、数学本、红领巾</small>
            </div>
          </button>
          <button class="plan-row bedtime" data-toast="已设置睡前提醒">
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
            <button class="chip primary" data-toast="已打开证据处理建议">查看处理建议</button>
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
            <button class="soft-cta" data-toast="已进入专注计时">${icon("play", "w-4 h-4")}查看</button>
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
          <button class="template-card" data-toast="已加入英语朗读">
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
            <button class="chip primary" data-toast="已创建小书包检查">加小书包</button>
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
              <button class="chip primary" data-toast="已打开证据说明">查看证据</button>
              <button class="chip" data-toast="已打开隐私说明">隐私说明</button>
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
            <button class="story-tile warm" data-nav="zones">
              <span class="capsule warn">${icon("signal", "w-3.5 h-3.5")}网络</span>
              <h4>低清稳定模式</h4>
              <p>保持流畅优先，截图仍可保存。</p>
            </button>
            <button class="story-tile blue" data-nav="playback">
              <span class="capsule blue">${icon("play", "w-3.5 h-3.5")}回放</span>
              <h4>事件片段</h4>
              <p>只保留任务和安全事件的必要片段。</p>
            </button>
          </section>
        </section>
      </section>
    `;
  },
};

Object.assign(views, fullViews);

function showToast(message) {
  const id = `toast-${Date.now()}`;
  toastLane.insertAdjacentHTML(
    "beforeend",
    `<div id="${id}" class="toast">${icon("check-circle", "w-4 h-4")}<span>${message}</span></div>`,
  );
  if (window.lucide) window.lucide.createIcons();
  setTimeout(() => document.getElementById(id)?.remove(), 2600);
}

document.addEventListener("click", (event) => {
  const closeLayer = event.target.closest("[data-close-layer]");
  if (closeLayer) {
    state.sheet = "";
    state.modal = "";
    render();
    return;
  }

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
      state.childProfile.relation = state.childDraft.relation || "家长";
      state.setupSaving = false;
      showToast("孩子资料已保存");
      goTo("setupDevice");
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
      goTo("setupPermissions");
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
