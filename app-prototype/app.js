const images = {
  study:
    "https://images.unsplash.com/photo-1509062522246-3755977927d7?auto=format&fit=crop&w=1000&q=82",
  room:
    "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?auto=format&fit=crop&w=1000&q=82",
  desk:
    "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=1000&q=82",
  hallway:
    "https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?auto=format&fit=crop&w=1000&q=82",
  family:
    "https://images.unsplash.com/photo-1609220136736-443140cffec6?auto=format&fit=crop&w=1000&q=82",
  notebook:
    "https://images.unsplash.com/photo-1517842645767-c639042777db?auto=format&fit=crop&w=1000&q=82",
  calendar:
    "https://images.unsplash.com/photo-1506784983877-45594efa4cbe?auto=format&fit=crop&w=1000&q=82",
  device:
    "https://images.unsplash.com/photo-1767059439653-b5cfd1f22f74?auto=format&fit=crop&w=1000&q=82",
  bedtime:
    "https://images.unsplash.com/photo-1616627561950-9f746e330187?auto=format&fit=crop&w=1000&q=82",
};

const app = document.getElementById("app");
const tabbar = document.getElementById("tabbar");
const pageMap = document.getElementById("pageMap");
const sheetMap = document.getElementById("sheetMap");
const pageCount = document.getElementById("pageCount");
const sheetCount = document.getElementById("sheetCount");
const stateChips = document.getElementById("stateChips");
const sheetRoot = document.getElementById("sheetRoot");
const modalRoot = document.getElementById("modalRoot");
const toastRoot = document.getElementById("toastRoot");
const pageSearch = document.getElementById("pageSearch");

const STATUS = {
  default: { label: "default", icon: "panel-top", tone: "neutral" },
  loading: { label: "loading", icon: "loader-circle", tone: "info" },
  empty: { label: "empty", icon: "inbox", tone: "neutral" },
  error: { label: "error", icon: "circle-alert", tone: "danger" },
  success: { label: "success", icon: "circle-check", tone: "success" },
  permissionDenied: { label: "permission denied", icon: "lock-keyhole", tone: "warning" },
  noResult: { label: "no result", icon: "search-x", tone: "neutral" },
  offline: { label: "offline", icon: "wifi-off", tone: "danger" },
  abnormal: { label: "abnormal", icon: "siren", tone: "danger" },
  updating: { label: "updating", icon: "refresh-cw", tone: "info" },
  privacyMode: { label: "privacy mode", icon: "shield-off", tone: "warning" },
  weakNetwork: { label: "weak network", icon: "signal-low", tone: "warning" },
  reconnecting: { label: "reconnecting", icon: "radio-tower", tone: "info" },
};

const ALL_STATES = Object.keys(STATUS);

const SHEETS = [
  ["createTaskSheet", "创建任务", "action sheet", "中置 +"],
  ["evidenceSheet", "任务证据", "bottom sheet", "确认、部分完成、驳回"],
  ["taskDateSheet", "选择日期", "bottom sheet", "今天、明天、未来日期"],
  ["taskTemplatesSheet", "任务模板", "bottom sheet", "套用一天模板"],
  ["taskEditSheet", "编辑任务", "bottom sheet", "修改、延后、复制、删除"],
  ["timePickerSheet", "时间选择", "bottom sheet", "开始/结束时间"],
  ["privacySheet", "看护隐私提示", "bottom sheet", "实时查看前说明"],
  ["privacyNoticeSheet", "儿童采集说明", "info sheet", "登录/绑定前说明"],
  ["rewardRequestSheet", "奖励申请", "bottom sheet", "兑现、稍后、暂不兑换"],
  ["manualRewardSheet", "主动兑换", "bottom sheet", "家长手动兑换"],
  ["rewardEditSheet", "编辑奖品", "bottom sheet", "添加/修改奖品"],
  ["pointRuleSheet", "积分规则", "bottom sheet", "阶段阈值"],
  ["pointMilestoneSheet", "积分阶段", "bottom sheet", "阶段完成处理"],
  ["callSheet", "音频通话", "confirmation sheet", "发起通话"],
  ["safetyTestSheet", "测试联系人", "confirmation sheet", "安全兜底"],
  ["zoneSheet", "新增区域", "action sheet", "书桌/床/门口"],
  ["memberSheet", "成员权限", "action sheet", "邀请与改权"],
  ["contactSheet", "紧急联系人", "bottom sheet", "添加联系人"],
  ["packingSheet", "小书包物品", "bottom sheet", "临时添加物品"],
  ["deleteDataSheet", "删除儿童数据", "confirmation sheet", "危险操作"],
  ["unbindSheet", "解绑设备", "confirmation sheet", "危险操作"],
  ["changePhoneSheet", "更换手机号", "bottom sheet", "安全验证"],
  ["loginDevicesSheet", "登录设备", "bottom sheet", "移除设备"],
  ["logoutSheet", "退出登录", "confirmation sheet", "退出当前账号"],
  ["deleteAccountSheet", "注销账号", "confirmation sheet", "账号删除"],
  ["termsSheet", "服务协议", "info sheet", "协议摘要"],
  ["privacyPolicySheet", "隐私政策", "info sheet", "隐私摘要"],
  ["subscriptionDowngradeSheet", "套餐降级", "info sheet", "降级说明"],
  ["feedbackSheet", "提交反馈", "bottom sheet", "反馈与误判"],
];

const PAGES = [
  page("welcome", "欢迎页", "Onboarding", "家长端入口", "sparkles", ["default", "loading", "error", "success"]),
  page("login", "登录注册", "Onboarding", "手机号与验证码", "smartphone", ["default", "loading", "error", "success"]),
  page("parentIdentity", "家长身份", "Onboarding", "角色与家庭显示名", "badge-check", ["default", "loading", "empty", "error", "success"]),
  page("bind", "扫码绑定", "Onboarding", "二维码与蓝牙发现", "scan-line", ["default", "loading", "empty", "error", "success", "permissionDenied"]),
  page("wifi", "Wi-Fi 配网", "Onboarding", "设备入网", "wifi", ["default", "loading", "error", "success", "offline", "weakNetwork"]),
  page("bindDone", "绑定成功", "Onboarding", "设备加入家庭", "circle-check", ["default", "loading", "error", "success"]),
  page("child", "孩子档案", "Onboarding", "孩子资料与年级", "user-round", ["default", "loading", "error", "success", "permissionDenied"]),
  page("name", "摄像头命名", "Onboarding", "唤醒名与声线", "volume-2", ["default", "loading", "error", "success", "permissionDenied", "offline"]),
  page("contacts", "紧急联系人", "Onboarding", "SOS 兜底联系人", "phone-call", ["default", "loading", "empty", "error", "success", "permissionDenied"]),
  page("permissions", "权限引导", "Onboarding", "通知、相机、麦克风", "shield-check", ["default", "loading", "error", "success", "permissionDenied"]),

  page("home", "首页", "首页", "当前状态、下一步、待处理", "layout-dashboard", ["default", "loading", "empty", "error", "success", "permissionDenied", "offline", "abnormal", "updating", "privacyMode"]),
  page("care", "协作待办", "首页", "真正需要家长判断的事", "bell-ring", ["default", "loading", "empty", "error", "success", "permissionDenied", "noResult", "offline"]),
  page("sleep", "睡眠晨起", "首页", "睡前任务与晨起节奏", "moon", ["default", "loading", "empty", "error", "success", "permissionDenied", "offline", "abnormal"]),

  page("tasks", "任务首页", "任务", "日期、任务列表、筛选", "calendar-days", ["default", "loading", "empty", "error", "success", "permissionDenied", "noResult", "offline"]),
  page("createTask", "创建任务表单", "任务", "普通任务、小书包、睡前、打卡", "plus-circle", ["default", "loading", "empty", "error", "success", "permissionDenied", "offline", "updating"]),
  page("flow", "任务模板", "任务", "一天任务模板与 AI 建议", "workflow", ["default", "loading", "empty", "error", "success", "permissionDenied", "noResult"]),
  page("packing", "小书包", "任务", "物品、课程表、提醒规则", "backpack", ["default", "loading", "empty", "error", "success", "permissionDenied", "noResult", "offline"]),
  page("taskDetail", "任务详情/证据", "任务", "证据、AI 判断、家长确认", "file-check-2", ["default", "loading", "empty", "error", "success", "permissionDenied", "offline"]),
  page("focus", "专注计时", "任务", "倒计时、暂停、延后", "timer", ["default", "loading", "empty", "error", "success", "permissionDenied", "offline", "abnormal"]),

  page("watch", "实时看护", "看护", "画面、通话、截图、提醒", "video", ["default", "loading", "empty", "error", "success", "permissionDenied", "offline", "privacyMode", "weakNetwork", "reconnecting", "updating"]),
  page("playback", "事件回放", "看护", "历史片段与筛选", "history", ["default", "loading", "empty", "error", "success", "permissionDenied", "noResult", "offline"]),
  page("zones", "安全区域", "看护", "书桌、床、门口、玩具区", "map", ["default", "loading", "empty", "error", "success", "permissionDenied", "offline"]),
  page("safety", "安全事件中心", "看护", "告警队列与处理记录", "shield-alert", ["default", "loading", "empty", "error", "success", "permissionDenied", "noResult", "offline", "abnormal"]),
  page("safetyDetail", "安全事件详情", "看护", "证据、规则、联系人", "siren", ["default", "loading", "empty", "error", "success", "permissionDenied", "offline", "abnormal", "weakNetwork"]),
  page("deviceOffline", "设备离线全页", "看护", "离线解释与重连步骤", "wifi-off", ["default", "loading", "error", "success", "offline", "abnormal"]),
  page("privacyBlock", "隐私阻断页", "看护", "隐私模式受限说明", "shield-off", ["default", "loading", "error", "success", "permissionDenied", "privacyMode"]),

  page("my", "我的总览", "我的", "家庭账户与管理入口", "user-cog", ["default", "loading", "empty", "error", "success", "offline"]),
  page("accountProfile", "个人信息", "我的", "家长资料表单", "id-card", ["default", "loading", "error", "success"]),
  page("accountSecurity", "账号安全", "我的", "手机号、登录设备、注销", "shield-check", ["default", "loading", "empty", "error", "success"]),
  page("subscription", "订阅套餐", "我的", "权益、云存储、报告", "badge-dollar-sign", ["default", "loading", "empty", "error", "success"]),
  page("report", "日报", "我的", "今日结论、证据、建议", "file-text", ["default", "loading", "empty", "error", "success", "permissionDenied", "offline"]),
  page("weekly", "周报", "我的", "趋势、建议、风险", "chart-line", ["default", "loading", "empty", "error", "success", "permissionDenied"]),
  page("moments", "成长时刻", "我的", "精选片段与收藏", "images", ["default", "loading", "empty", "error", "success", "permissionDenied", "noResult"]),
  page("points", "积分总览", "我的", "余额、流水、阶段", "coins", ["default", "loading", "empty", "error", "success", "permissionDenied", "noResult"]),
  page("reward", "奖励商店", "我的", "奖品、申请、兑换", "gift", ["default", "loading", "empty", "error", "success", "permissionDenied", "noResult"]),
  page("checkin", "打卡审核", "我的", "素材待审与重拍", "clipboard-check", ["default", "loading", "empty", "error", "success", "permissionDenied", "noResult"]),
  page("conversation", "对话与人设/AI 规则", "我的", "唤醒名、声线、边界", "bot", ["default", "loading", "error", "success", "permissionDenied", "offline", "updating"]),
  page("privacy", "隐私与权限", "我的", "记录策略与数据权利", "lock-keyhole", ["default", "loading", "error", "success", "permissionDenied", "offline", "privacyMode"]),
  page("family", "家庭成员", "我的", "成员、角色、权限", "users", ["default", "loading", "empty", "error", "success", "permissionDenied", "noResult"]),
  page("device", "设备管理", "我的", "设备详情、网络、固件", "camera", ["default", "loading", "empty", "error", "success", "permissionDenied", "offline", "abnormal", "updating"]),
  page("notifications", "通知设置", "我的", "安全告警与任务待办", "bell", ["default", "loading", "error", "success", "permissionDenied"]),
  page("education", "学习内容", "我的", "小书包和内容生态", "book-open", ["default", "loading", "empty", "error", "success", "permissionDenied", "noResult"]),
  page("settings", "设备与规则聚合", "我的", "设备、联系人、AI、安全", "settings", ["default", "loading", "empty", "error", "success", "permissionDenied", "offline", "updating"]),
  page("feedback", "帮助反馈", "我的", "问题追踪与误判上报", "message-square", ["default", "loading", "error", "success", "noResult"]),
  page("about", "关于我们", "我的", "品牌、协议、版本", "aperture", ["default", "loading", "error", "success"]),

  page("componentStates", "组件状态总览", "验收", "按钮、卡片、标签、表单、筛选", "sliders-horizontal", ALL_STATES),
  page("coverage", "矩阵覆盖说明", "验收", "逐项对照 app-flow-and-state-matrix", "list-checks", ["default"]),
];

const pageById = Object.fromEntries(PAGES.map((item) => [item.id, item]));
const sheetById = Object.fromEntries(SHEETS.map((item) => [item[0], item]));

const state = {
  page: location.hash.replace("#", "") && pageById[location.hash.replace("#", "")]
    ? location.hash.replace("#", "")
    : "home",
  mode: "default",
  search: "",
  parentRole: "妈妈",
  childName: "小宇",
  selectedDay: "今天",
  toggles: {
    "安全告警": true,
    "任务待确认": true,
    "隐私模式": true,
    "自由聊天": true,
    "睡前不主动聊天": true,
    "普通闲聊逐字记录": false,
  },
};

function page(id, name, group, subtitle, icon, states) {
  return { id, name, group, subtitle, icon, states };
}

function icon(name, className = "") {
  return `<i data-lucide="${name}" class="${className}"></i>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function render() {
  const pageData = pageById[state.page] || pageById.home;
  app.innerHTML = renderScreen(pageData);
  renderTabbar(pageData);
  renderPanel();
  hydrateIcons();
  app.scrollTop = 0;
  history.replaceState(null, "", `#${pageData.id}`);
}

function hydrateIcons() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

function renderScreen(pageData) {
  const forced = state.page === "deviceOffline" && state.mode === "default"
    ? "offline"
    : state.page === "privacyBlock" && state.mode === "default"
      ? "privacyMode"
      : state.mode;

  if (forced !== "default" && state.page !== "componentStates" && state.page !== "coverage") {
    return renderStateScene(pageData, forced);
  }

  const custom = CUSTOM_RENDERERS[pageData.id];
  if (custom) return `<section class="screen">${custom(pageData)}</section>`;
  return `<section class="screen">${renderGenericPage(pageData)}</section>`;
}

function screenHeader(title, subtitle, right = "") {
  return `
    <header class="screen-header">
      <div>
        <p>${subtitle}</p>
        <h2>${title}</h2>
      </div>
      ${right || `<button class="icon-button" type="button" data-go="coverage" aria-label="查看覆盖">${icon("list-checks")}</button>`}
    </header>
  `;
}

function pill(label, tone = "neutral", iconName = "") {
  return `<span class="pill ${tone}">${iconName ? icon(iconName) : ""}${label}</span>`;
}

function metric(label, value, tone = "neutral") {
  const color = {
    success: "var(--success)",
    warning: "var(--warning)",
    danger: "var(--danger)",
    ai: "var(--accent-ai)",
    info: "var(--info)",
    neutral: "var(--ink)",
  }[tone] || "var(--ink)";
  return `<div class="metric"><strong style="color:${color}">${value}</strong><span>${label}</span></div>`;
}

function row(iconName, title, desc, action = "", tone = "neutral", attrs = "") {
  return `
    <div class="row pressable" role="button" tabindex="0" ${attrs}>
      <span class="row-icon ${tone}">${icon(iconName)}</span>
      <span class="row-main">
        <span class="row-title">${title}</span>
        <span class="row-desc">${desc}</span>
      </span>
      <span class="row-action">${action || icon("chevron-right")}</span>
    </div>
  `;
}

function primary(label, attrs = "", iconName = "arrow-right") {
  return `<button class="primary-button" type="button" ${attrs}>${label}${icon(iconName)}</button>`;
}

function secondary(label, attrs = "", iconName = "") {
  return `<button class="secondary-button" type="button" ${attrs}>${iconName ? icon(iconName) : ""}${label}</button>`;
}

function danger(label, attrs = "", iconName = "triangle-alert") {
  return `<button class="danger-button" type="button" ${attrs}>${icon(iconName)}${label}</button>`;
}

function renderGenericPage(pageData) {
  const rows = genericRows(pageData);
  return `
    ${screenHeader(pageData.name, pageData.subtitle)}
    <section class="card status-rail">
      <div class="card-head">
        <div>
          <p class="card-title">${pageData.name}状态</p>
          <p class="card-subtitle">${pageData.subtitle}。此页支持矩阵里的 loading、empty、error、success、permission denied 和设备异常状态。</p>
        </div>
        ${pill("default", "success", "circle-check")}
      </div>
      <div class="metric-grid">
        ${metric("待处理", pageData.group === "看护" ? "3" : "2", pageData.group === "看护" ? "danger" : "warning")}
        ${metric("同步", "在线", "success")}
        ${metric("AI 置信", "91%", "ai")}
      </div>
    </section>
    <section class="section-stack">
      ${rows}
    </section>
    <section class="card">
      <div class="card-head">
        <div>
          <p class="card-title">状态切换</p>
          <p class="card-subtitle">右侧控制台可切换所有页面状态；这里保留核心操作入口。</p>
        </div>
      </div>
      <div class="button-row mt-3">
        ${secondary("显示 loading", 'data-state="loading"', "loader-circle")}
        ${secondary("显示 error", 'data-state="error"', "circle-alert")}
      </div>
    </section>
  `;
}

function genericRows(pageData) {
  const byGroup = {
    "Onboarding": [
      row("shield-check", "隐私说明已准备", "儿童音视频采集会在绑定设备后单独授权", pill("可追溯", "info"), "info", 'data-sheet="privacyNoticeSheet"'),
      row("wifi", "设备待配置", "Mira Cam M1 正在等待家庭网络", pill("待配网", "warning"), "warning", 'data-go="wifi"'),
    ],
    "首页": [
      row("file-check-2", "作业证据待确认", "AI 判断完成，但需要家长最终确认", pill("待处理", "warning"), "warning", 'data-go="taskDetail"'),
      row("gift", "奖励申请", "小宇想兑换周末户外活动", pill("申请中", "info"), "info", 'data-sheet="rewardRequestSheet"'),
    ],
    "任务": [
      row("calendar-check", "今日任务", "数学口算、英语朗读、小书包检查", pill("6 项", "info"), "info", 'data-go="tasks"'),
      row("file-check-2", "证据确认", "查看截图、AI 规则和置信度", pill("91%", "ai"), "ai", 'data-go="taskDetail"'),
    ],
    "看护": [
      row("video", "实时画面", "儿童房书桌视角，远程查看提示已显示", pill("在线", "success"), "success", 'data-go="watch"'),
      row("siren", "安全事件", "门口区域 19:18 触发异常声音", pill("未处理", "danger"), "danger", 'data-go="safetyDetail"'),
    ],
    "我的": [
      row("camera", "设备与规则", "网络、固件、隐私模式、AI 边界", pill("在线", "success"), "success", 'data-go="settings"'),
      row("lock-keyhole", "隐私与权限", "记录策略、数据导出、儿童数据删除", pill("已启用", "info"), "info", 'data-go="privacy"'),
    ],
  };
  return (byGroup[pageData.group] || byGroup["我的"]).join("");
}

const CUSTOM_RENDERERS = {
  welcome: renderWelcome,
  login: renderLogin,
  parentIdentity: renderParentIdentity,
  bind: renderBind,
  wifi: renderWifi,
  bindDone: renderBindDone,
  child: renderChild,
  name: renderName,
  contacts: renderContacts,
  permissions: renderPermissions,
  home: renderHome,
  care: renderCare,
  sleep: renderSleep,
  tasks: renderTasks,
  createTask: renderCreateTask,
  flow: renderFlow,
  packing: renderPacking,
  taskDetail: renderTaskDetail,
  focus: renderFocus,
  watch: renderWatch,
  playback: renderPlayback,
  zones: renderZones,
  safety: renderSafety,
  safetyDetail: renderSafetyDetail,
  deviceOffline: renderDeviceOffline,
  privacyBlock: renderPrivacyBlock,
  my: renderMy,
  accountProfile: renderAccountProfile,
  accountSecurity: renderAccountSecurity,
  subscription: renderSubscription,
  report: renderReport,
  weekly: renderWeekly,
  moments: renderMoments,
  points: renderPoints,
  reward: renderReward,
  checkin: renderCheckin,
  conversation: renderConversation,
  privacy: renderPrivacy,
  family: renderFamily,
  device: renderDevice,
  notifications: renderNotifications,
  education: renderEducation,
  settings: renderSettings,
  feedback: renderFeedback,
  about: renderAbout,
  componentStates: renderComponentStates,
  coverage: renderCoverage,
};

function renderWelcome() {
  return `
    <section class="hero-card">
      <div class="hero-media">
        <img src="${images.study}" alt="孩子在学习空间写作业的真实照片" />
        <div class="hero-overlay">
          <p class="eyebrow">Mira Guardian 家长端</p>
          <h2 class="hero-title">家庭 AI 智护控制台</h2>
          <p class="hero-copy">把看护、任务、证据、奖励和安全告警收成清楚的家长决策流。</p>
        </div>
      </div>
    </section>
    <section class="card">
      <div class="metric-grid">
        ${metric("设备", "在线", "success")}
        ${metric("待处理", "2", "warning")}
        ${metric("安全", "正常", "success")}
      </div>
    </section>
    <section class="section-stack">
      ${primary("开始设置", 'data-go="login"')}
      ${secondary("查看演示首页", 'data-go="home"', "play")}
    </section>
  `;
}

function renderLogin() {
  return `
    ${screenHeader("登录或创建家庭", "账户", `<button class="icon-button" data-sheet="privacyNoticeSheet" aria-label="隐私说明">${icon("shield-check")}</button>`)}
    <section class="form-card">
      <div class="input-group">
        <label for="phone">手机号<span>用于安全验证</span></label>
        <input id="phone" class="field" inputmode="tel" value="138 0000 2026" />
      </div>
      <div class="input-group">
        <label for="code">验证码<span>4 位数字</span></label>
        <div class="grid grid-cols-[1fr_106px] gap-2">
          <input id="code" class="field" inputmode="numeric" value="0426" />
          <button class="secondary-button mt-[7px]" type="button" data-action="send-code">获取</button>
        </div>
        <p class="form-hint">继续表示监护人同意创建家庭空间；儿童音视频权限会在绑定设备后单独确认。</p>
      </div>
    </section>
    <section class="section-stack">
      ${primary("继续", 'data-action="login"')}
      ${secondary("查看儿童采集说明", 'data-sheet="privacyNoticeSheet"', "file-text")}
    </section>
  `;
}

function renderParentIdentity() {
  const roles = ["妈妈", "爸爸", "祖辈", "其他照护人"];
  return `
    ${screenHeader("家长身份", "怎么称呼你？")}
    <section class="form-card">
      <p class="card-subtitle">这会影响通知分发、处理记录和报告称呼。第一个创建家庭的家长默认为管理员。</p>
      <div class="dense-grid mt-3">
        ${roles
          .map((role) => `<button class="secondary-button ${state.parentRole === role ? "is-selected" : ""}" data-action="select-role" data-value="${role}">${state.parentRole === role ? icon("check") : ""}${role}</button>`)
          .join("")}
      </div>
      <div class="input-group">
        <label for="parentName">家庭显示名<span>会出现在处理记录</span></label>
        <input id="parentName" class="field" value="${state.parentRole}的家庭" />
      </div>
    </section>
    ${primary("继续绑定设备", 'data-go="bind"')}
  `;
}

function renderBind() {
  return `
    ${screenHeader("扫描摄像头二维码", "设备绑定")}
    <section class="card">
      <div class="grid place-items-center rounded-[12px] bg-[#17201C] p-7 text-white">
        <div class="relative grid h-48 w-48 place-items-center rounded-[16px] border border-white/20">
          <div class="grid h-32 w-32 grid-cols-3 gap-2 rounded-[8px] bg-white p-3">
            <span class="rounded bg-[#17201C]"></span><span></span><span class="rounded bg-[#17201C]"></span>
            <span></span><span class="rounded bg-[#17201C]"></span><span></span>
            <span class="rounded bg-[#17201C]"></span><span></span><span class="rounded bg-[#17201C]"></span>
          </div>
          <span class="absolute inset-x-6 top-1/2 h-0.5 bg-[#49D7B3]"></span>
        </div>
      </div>
      <p class="form-hint">无法扫码时可使用蓝牙发现。相机权限拒绝时会进入 permission denied 状态。</p>
    </section>
    <section class="button-row">
      ${secondary("蓝牙发现", 'data-action="scan-bluetooth"', "bluetooth")}
      ${primary("模拟扫码成功", 'data-go="wifi"', "scan-line")}
    </section>
  `;
}

function renderWifi() {
  return `
    ${screenHeader("连接家庭 Wi-Fi", "配网")}
    <section class="form-card">
      ${row("camera", "Mira Cam M1", "距离约 1.8 米，处于待配网状态", pill("待配网", "warning"), "warning")}
      <div class="input-group">
        <label for="ssid">Wi-Fi 名称<span>支持 2.4G / 5G</span></label>
        <input id="ssid" class="field" value="Mira Home 5G" />
      </div>
      <div class="input-group">
        <label for="wifiPwd">Wi-Fi 密码<span>仅发送到设备本地</span></label>
        <input id="wifiPwd" class="field" type="password" value="mira2026home" />
      </div>
      <p class="form-hint">配网过程中摄像头只接收网络信息，不会开始录像或录音。</p>
    </section>
    ${primary("开始绑定", 'data-action="bind-device"', "link")}
  `;
}

function renderBindDone() {
  return `
    <section class="state-card text-center">
      <div class="mx-auto grid h-18 w-18 place-items-center rounded-full bg-[var(--success-soft)] text-[var(--success)]">${icon("check", "h-9 w-9")}</div>
      <h2 class="mt-4 text-2xl font-black">设备绑定成功</h2>
      <p class="mt-2 text-sm leading-6 text-[var(--muted)]">儿童房摄像头已加入“小宇家”。接下来创建孩子档案和紧急联系人。</p>
    </section>
    <section class="media-card hero-card mt-3">
      <div class="hero-media min-h-[210px]"><img src="${images.room}" alt="儿童房真实室内图片" /></div>
    </section>
    ${primary("创建孩子档案", 'data-go="child"')}
  `;
}

function renderChild() {
  return `
    ${screenHeader("孩子档案", "让任务更合适")}
    <section class="form-card">
      <div class="input-group">
        <label for="childName">孩子称呼<span>用于提醒和报告</span></label>
        <input id="childName" class="field" value="${state.childName}" />
      </div>
      <div class="grid grid-cols-[1fr_1.1fr] gap-2">
        <div class="input-group">
          <label for="birthday">生日</label>
          <input id="birthday" class="field" type="date" value="2018-09-05" />
        </div>
        <div class="input-group">
          <label for="stage">就读阶段</label>
          <select id="stage" class="select-field"><option>小学一年级</option><option>幼儿园大班</option><option>小学二年级</option></select>
        </div>
      </div>
      <div class="input-group">
        <label for="className">班级<span>生成小书包规则</span></label>
        <input id="className" class="field" value="1 年级 3 班" />
      </div>
    </section>
    <section class="card">
      <p class="card-title">小书包预设</p>
      <p class="card-subtitle">小学一年级默认关注课本、作业本、水杯、红领巾和手工作业材料。</p>
      <div class="button-row mt-3">
        ${secondary("查看小书包", 'data-go="packing"', "backpack")}
        ${secondary("套用模板", 'data-sheet="taskTemplatesSheet"', "workflow")}
      </div>
    </section>
    ${primary("继续命名摄像头", 'data-go="name"')}
  `;
}

function renderName() {
  return `
    ${screenHeader("人设与语音", "孩子给摄像头起名")}
    <section class="card">
      <div class="rounded-[12px] bg-[#17201C] p-4 text-white">
        <p class="text-sm text-white/60">摄像头会问孩子</p>
        <p class="mt-3 text-xl font-bold leading-8">“那你也给我起一个名字吧。以后你叫这个名字，我就知道你在找我。”</p>
      </div>
      <div class="input-group">
        <label for="wakeName">唤醒名<span>建议 2-4 个字</span></label>
        <input id="wakeName" class="field" value="小豆" />
      </div>
      <div class="button-row mt-3">
        ${secondary("试听声线", 'data-action="play-voice"', "volume-2")}
        ${secondary("边界说明", 'data-sheet="privacySheet"', "shield")}
      </div>
    </section>
    ${primary("设置紧急联系人", 'data-go="contacts"')}
  `;
}

function renderContacts() {
  return `
    ${screenHeader("添加紧急联系人", "安全")}
    <section class="section-stack">
      ${row("user-round", "妈妈", "管理员，接收全部安全告警", pill("已验证", "success"), "success")}
      ${row("user-plus", "爸爸", "第二联系人，SOS 兜底通知", `<button class="secondary-button !min-h-[36px] !w-auto px-3" data-action="invite-contact">邀请</button>`, "info")}
      ${row("phone-call", "社区邻居", "紧急情况可由家长手动启用", pill("可选", "neutral"), "neutral", 'data-sheet="contactSheet"')}
    </section>
    ${secondary("添加联系人", 'data-sheet="contactSheet"', "plus")}
    ${primary("进入首页", 'data-go="home"', "home")}
  `;
}

function renderPermissions() {
  return `
    ${screenHeader("权限引导", "通知、相机、麦克风、相册")}
    <section class="section-stack">
      ${row("bell", "通知权限", "安全告警、任务确认、奖励申请依赖推送", pill("建议开启", "warning"), "warning", 'data-action="request-permission" data-permission="通知"')}
      ${row("camera", "相机权限", "扫码绑定和打卡素材补充时使用", pill("按需", "info"), "info", 'data-action="request-permission" data-permission="相机"')}
      ${row("mic", "麦克风权限", "音频通话与语音确认时使用", pill("按需", "info"), "info", 'data-action="request-permission" data-permission="麦克风"')}
      ${row("images", "相册权限", "保存截图、导出证据、提交反馈时使用", pill("按需", "neutral"), "neutral", 'data-action="request-permission" data-permission="相册"')}
    </section>
    ${primary("授权完成，进入首页", 'data-go="home"', "arrow-right")}
  `;
}

function renderHome() {
  return `
    ${screenHeader("小宇现在", "周一 19:42", `<button class="icon-button" data-go="care" aria-label="待处理">${icon("bell-ring")}</button>`)}
    <section class="card status-rail">
      <div class="flex flex-wrap gap-2">
        ${pill("设备在线", "success", "wifi")}
        ${pill("隐私灯亮起", "info", "shield-check")}
        ${pill("小学一年级", "neutral")}
      </div>
      <h3 class="mt-5 text-[25px] leading-tight font-black">书桌前写作业，状态正常。</h3>
      <p class="mt-2 text-sm leading-6 text-[var(--muted)]">当前任务是数学口算，第 2 个专注轮次；12 分钟后需要家长确认证据。</p>
      <div class="metric-grid">
        ${metric("安全", "正常", "success")}
        ${metric("下一步", "12m", "ai")}
        ${metric("待处理", "2", "warning")}
      </div>
    </section>
    <section class="card">
      <div class="card-head">
        <div>
          <p class="card-title">需要你处理</p>
          <p class="card-subtitle">只放真正需要家长判断的事</p>
        </div>
        <button class="text-button" data-go="care">全部</button>
      </div>
      <div class="mt-3">
        ${row("file-check-2", "作业证据待确认", "确认后进入日报和奖励流水", `<button class="primary-button !min-h-[36px] !w-auto px-3" data-go="taskDetail">处理</button>`, "warning")}
        ${row("gift", "奖励申请待确认", "小宇想兑换周末户外活动", `<button class="secondary-button !min-h-[36px] !w-auto px-3" data-sheet="rewardRequestSheet">确认</button>`, "info")}
      </div>
    </section>
    <section class="button-row">
      ${secondary("实时看护", 'data-go="watch"', "video")}
      ${secondary("设备状态", 'data-go="device"', "camera")}
    </section>
    <section class="dense-grid">
      ${quickCard("小书包", "2 项待确认", "backpack", "packing")}
      ${quickCard("睡眠晨起", "21:10 开始", "moon", "sleep")}
      ${quickCard("安全事件", "1 条未处理", "shield-alert", "safety")}
      ${quickCard("日报", "19:30 已生成", "file-text", "report")}
    </section>
  `;
}

function quickCard(title, desc, iconName, target) {
  return `
    <button class="card text-left pressable" data-go="${target}">
      <span class="row-icon">${icon(iconName)}</span>
      <p class="mt-3 card-title">${title}</p>
      <p class="card-subtitle">${desc}</p>
    </button>
  `;
}

function renderCare() {
  return `
    ${screenHeader("协作待办", "今天还有 4 个家长判断点")}
    <section class="section-stack">
      ${row("file-check-2", "数学作业证据", "AI 判断：完成 87%，需家长确认", pill("待确认", "warning"), "warning", 'data-go="taskDetail"')}
      ${row("gift", "奖励兑换申请", "小宇申请周末户外活动", pill("申请中", "info"), "info", 'data-sheet="rewardRequestSheet"')}
      ${row("siren", "门口异常声音", "19:18 触发，证据片段 12 秒", pill("安全", "danger"), "danger", 'data-go="safetyDetail"')}
      ${row("clipboard-check", "手工作业打卡", "3 张素材待审核", pill("待审", "warning"), "warning", 'data-go="checkin"')}
    </section>
  `;
}

function renderSleep() {
  return `
    ${screenHeader("睡眠晨起", "睡前任务与早晨节奏")}
    <section class="media-card hero-card">
      <div class="hero-media min-h-[190px]"><img src="${images.bedtime}" alt="卧室睡前真实环境" /></div>
    </section>
    <section class="card">
      <div class="metric-grid">
        ${metric("上床目标", "21:30", "info")}
        ${metric("免打扰", "22:00", "success")}
        ${metric("晨起", "07:10", "warning")}
      </div>
    </section>
    <section class="section-stack">
      ${row("moon", "睡前流程", "洗漱、收拾书包、关闭自由聊天", pill("21:10", "info"), "info")}
      ${row("bell", "晨起提醒", "先柔声提醒，再通知家长", pill("已开启", "success"), "success")}
      ${row("shield", "夜间隐私", "夜间只保留异常声音和 SOS", pill("低采集", "success"), "success", 'data-go="privacy"')}
    </section>
  `;
}

function renderTasks() {
  const days = ["今天", "明天", "周三", "周四", "周五"];
  return `
    ${screenHeader("任务", "今天 6 项，2 项待确认", `<button class="icon-button" data-sheet="taskTemplatesSheet" aria-label="模板">${icon("sparkles")}</button>`)}
    <section class="card">
      <div class="component-strip">
        ${days.map((day) => `<button class="state-chip ${state.selectedDay === day ? "is-active" : ""}" data-action="select-day" data-value="${day}">${day}</button>`).join("")}
      </div>
    </section>
    <section class="section-stack">
      ${row("book-open-check", "数学口算 20 题", "19:20-19:45，证据：桌面截图 + AI 完成判断", pill("进行中", "ai"), "ai", 'data-go="focus"')}
      ${row("mic", "英语朗读 10 分钟", "检测方式：声音 + 家长抽查", pill("待开始", "neutral"), "neutral", 'data-go="taskDetail"')}
      ${row("backpack", "小书包检查", "语文书、数学本、水杯、红领巾", pill("2 项待确认", "warning"), "warning", 'data-go="packing"')}
      ${row("moon", "睡前准备", "洗漱、整理桌面、上床", pill("21:10", "info"), "info", 'data-go="sleep"')}
    </section>
    ${primary("创建任务", 'data-sheet="createTaskSheet"', "plus")}
  `;
}

function renderCreateTask() {
  return `
    ${screenHeader("创建任务", "普通任务 / 小书包 / 睡前 / 打卡")}
    <section class="form-card">
      <div class="component-strip">
        ${["普通任务", "小书包", "睡前任务", "打卡任务"].map((item, index) => `<button class="state-chip ${index === 0 ? "is-active" : ""}" type="button">${item}</button>`).join("")}
      </div>
      <div class="input-group">
        <label for="taskTitle">任务名称<span>必填</span></label>
        <input id="taskTitle" class="field" value="数学口算 20 题" />
        <p id="taskTitleHint" class="form-hint">真实业务数据：小学一年级每日口算练习。</p>
      </div>
      <div class="grid grid-cols-2 gap-2">
        <div class="input-group">
          <label for="taskDate">日期</label>
          <input id="taskDate" class="field" type="date" value="2026-05-28" />
        </div>
        <div class="input-group">
          <label for="taskReward">奖励</label>
          <input id="taskReward" class="field" inputmode="numeric" value="3" />
        </div>
      </div>
      <div class="grid grid-cols-2 gap-2">
        <div class="input-group">
          <label for="taskStart">开始</label>
          <input id="taskStart" class="field" type="time" value="19:20" />
        </div>
        <div class="input-group">
          <label for="taskEnd">结束</label>
          <input id="taskEnd" class="field" type="time" value="19:45" />
        </div>
      </div>
      <div class="input-group">
        <label for="taskEvidence">证据要求</label>
        <select id="taskEvidence" class="select-field">
          <option>桌面截图 + AI 完成判断</option>
          <option>家长手动确认</option>
          <option>声音检测 + 抽查</option>
        </select>
      </div>
    </section>
    <section class="button-row">
      ${secondary("套用模板", 'data-sheet="taskTemplatesSheet"', "workflow")}
      ${primary("保存任务", 'data-action="save-task"', "check")}
    </section>
  `;
}

function renderFlow() {
  return `
    ${screenHeader("任务模板", "按年龄和家庭节奏推荐")}
    <section class="section-stack">
      ${row("sun", "上学日模板", "晨起、作业、英语朗读、小书包、睡前", pill("推荐", "success"), "success", 'data-sheet="taskTemplatesSheet"')}
      ${row("moon", "睡前模板", "洗漱、整理书桌、关闭自由聊天、上床", pill("低打扰", "info"), "info", 'data-sheet="taskTemplatesSheet"')}
      ${row("backpack", "周五小书包", "兴趣班材料、周末作业、校服清洗提醒", pill("周五", "warning"), "warning", 'data-sheet="taskTemplatesSheet"')}
    </section>
  `;
}

function renderPacking() {
  return `
    ${screenHeader("小书包", "明天 7:40 前需要确认")}
    <section class="card">
      <div class="metric-grid">
        ${metric("必须", "5", "info")}
        ${metric("已确认", "3", "success")}
        ${metric("待补", "2", "warning")}
      </div>
    </section>
    <section class="section-stack">
      ${row("book-open", "语文书", "AI 识别到书桌左侧", pill("已放入", "success"), "success")}
      ${row("notebook", "数学练习册", "未在书包区域出现", pill("待确认", "warning"), "warning")}
      ${row("droplets", "水杯", "门口区域未检测到", pill("待补", "warning"), "warning")}
      ${row("scissors", "手工材料", "临时添加，明早提醒", pill("新增", "info"), "info", 'data-sheet="packingSheet"')}
    </section>
    ${secondary("临时添加物品", 'data-sheet="packingSheet"', "plus")}
  `;
}

function renderTaskDetail() {
  return `
    ${screenHeader("数学口算 20 题", "任务详情 / 证据确认")}
    <section class="media-card hero-card">
      <div class="hero-media min-h-[210px]"><img src="${images.notebook}" alt="作业本与学习桌真实照片" /></div>
    </section>
    <section class="card status-rail ai">
      <div class="card-head">
        <div>
          <p class="card-title">AI 判断</p>
          <p class="card-subtitle">检测到桌面纸笔活动 22 分钟，作业本翻页 3 次，置信度 91%。</p>
        </div>
        ${pill("待家长确认", "warning")}
      </div>
      <div class="metric-grid">
        ${metric("完成度", "87%", "ai")}
        ${metric("奖励", "+3", "success")}
        ${metric("证据", "2", "info")}
      </div>
    </section>
    <section class="button-row three">
      ${primary("确认", 'data-action="evidence-confirm"', "check")}
      ${secondary("部分完成", 'data-sheet="evidenceSheet"', "split")}
      ${danger("驳回", 'data-sheet="evidenceSheet"', "x")}
    </section>
  `;
}

function renderFocus() {
  return `
    ${screenHeader("专注计时", "数学口算进行中")}
    <section class="card text-center">
      <p class="eyebrow">Focus Round 2 / 3</p>
      <div class="my-5 text-[54px] font-black tabular-nums">12:08</div>
      <p class="text-sm leading-6 text-[var(--muted)]">摄像头仅判断坐姿、书桌区域和任务相关动作，不进行全天连续录像。</p>
      <div class="metric-grid">
        ${metric("离席", "0", "success")}
        ${metric("提醒", "1", "info")}
        ${metric("状态", "正常", "success")}
      </div>
    </section>
    <section class="button-row three">
      ${secondary("暂停", 'data-action="quick-success" data-message="计时已暂停"', "pause")}
      ${secondary("延后", 'data-sheet="taskEditSheet"', "clock")}
      ${primary("结束", 'data-action="quick-success" data-message="已结束并进入证据确认"', "check")}
    </section>
  `;
}

function renderWatch() {
  return `
    ${screenHeader("实时看护", "儿童房书桌视角", `<button class="icon-button" data-sheet="privacySheet" aria-label="隐私提示">${icon("shield")}</button>`)}
    <section class="live-video">
      <img src="${images.desk}" alt="书桌与电脑学习场景真实照片" />
      <div class="live-hud">
        <span class="video-label">LIVE · 低清稳定</span>
        <span class="video-label">隐私灯已亮起</span>
      </div>
    </section>
    <section class="card">
      <div class="metric-grid">
        ${metric("连接", "38ms", "success")}
        ${metric("画质", "720p", "info")}
        ${metric("电量", "插电", "success")}
      </div>
    </section>
    <section class="button-row three">
      ${secondary("截图", 'data-action="capture"', "camera")}
      ${primary("通话", 'data-sheet="callSheet"', "phone")}
      ${secondary("回放", 'data-go="playback"', "history")}
    </section>
    <section class="section-stack">
      ${row("shield-alert", "门口区域 19:18", "异常声音触发，未发现陌生人入画", pill("待处理", "danger"), "danger", 'data-go="safetyDetail"')}
      ${row("map", "安全区域", "书桌、床、门口、玩具区规则正常", pill("4 区", "info"), "info", 'data-go="zones"')}
    </section>
  `;
}

function renderPlayback() {
  return `
    ${screenHeader("事件回放", "今天 8 条片段")}
    <section class="component-strip mb-3">
      ${["全部", "任务证据", "安全", "成长时刻"].map((item, index) => `<button class="state-chip ${index === 0 ? "is-active" : ""}" data-action="quick-toast" data-message="筛选：${item}">${item}</button>`).join("")}
    </section>
    <section class="section-stack">
      ${row("file-check-2", "19:45 作业结束", "数学口算证据片段，12 秒", pill("任务", "ai"), "ai", 'data-go="taskDetail"')}
      ${row("siren", "19:18 门口异常声音", "安全区域触发，待处理", pill("安全", "danger"), "danger", 'data-go="safetyDetail"')}
      ${row("star", "18:40 主动整理书桌", "成长时刻已收藏", pill("精选", "success"), "success", 'data-go="moments"')}
    </section>
  `;
}

function renderZones() {
  return `
    ${screenHeader("安全区域", "书桌、床、门口、玩具区")}
    <section class="media-card hero-card">
      <div class="hero-media min-h-[210px]"><img src="${images.hallway}" alt="家庭门厅真实照片" /></div>
    </section>
    <section class="section-stack">
      ${row("desk", "书桌区", "离开超过 8 分钟提醒，作业模式开启", pill("启用", "success"), "success")}
      ${row("bed", "床区", "22:00 后只保留异常声音检测", pill("夜间", "info"), "info")}
      ${row("door-open", "门口区", "异常声音、长时间停留、SOS 兜底", pill("重点", "danger"), "danger")}
    </section>
    ${secondary("新增区域", 'data-sheet="zoneSheet"', "plus")}
  `;
}

function renderSafety() {
  return `
    ${screenHeader("安全事件", "今日 1 条未处理")}
    <section class="card status-rail danger">
      <div class="card-head">
        <div>
          <p class="card-title">门口异常声音</p>
          <p class="card-subtitle">19:18 触发，声音持续 6 秒，未检测到已登记家庭成员。</p>
        </div>
        ${pill("待处理", "danger")}
      </div>
      <div class="button-row mt-3">
        ${primary("查看详情", 'data-go="safetyDetail"', "arrow-right")}
        ${secondary("标记误报", 'data-confirm="标记为误报？" data-confirm-message="系统会保留原始触发记录，后续同类声音权重降低。"', "flag")}
      </div>
    </section>
    <section class="section-stack">
      ${row("shield-check", "18:05 书桌离席", "已由妈妈处理", pill("已处理", "success"), "success")}
      ${row("bell", "17:30 长时间未出现", "爸爸已联系孩子", pill("已联系", "success"), "success")}
    </section>
  `;
}

function renderSafetyDetail() {
  return `
    ${screenHeader("门口异常声音", "安全事件详情")}
    <section class="media-card hero-card">
      <div class="hero-media min-h-[220px]"><img src="${images.hallway}" alt="家庭门口区域真实照片" /></div>
    </section>
    <section class="card status-rail danger">
      <div class="card-head">
        <div>
          <p class="card-title">触发规则</p>
          <p class="card-subtitle">门口区出现 6 秒异常声音；设备在线，证据片段已加密保存。</p>
        </div>
        ${pill("abnormal", "danger", "siren")}
      </div>
      <div class="timeline">
        <div class="timeline-item"><p class="row-title">19:18:03 检测到敲击声</p><p class="row-desc">置信度 88%，未检测到家庭成员人声。</p></div>
        <div class="timeline-item"><p class="row-title">19:18:10 推送给妈妈和爸爸</p><p class="row-desc">爸爸 19:19 已读，妈妈未处理。</p></div>
      </div>
    </section>
    <section class="button-row">
      ${primary("联系孩子", 'data-sheet="callSheet"', "phone")}
      ${secondary("测试联系人", 'data-sheet="safetyTestSheet"', "shield-check")}
    </section>
    <section class="button-row">
      ${secondary("标记已处理", 'data-action="resolve-safety"', "check")}
      ${danger("误报", 'data-confirm="确认标记误报？" data-confirm-message="误报会记录到模型纠错样本，原始事件仍保留在日报里。"', "flag")}
    </section>
  `;
}

function renderDeviceOffline() {
  return renderStateScene(pageById.deviceOffline, "offline");
}

function renderPrivacyBlock() {
  return renderStateScene(pageById.privacyBlock, "privacyMode");
}

function renderMy() {
  return `
    ${screenHeader("家庭账户", "我的", `<button class="icon-button" data-go="notifications" aria-label="通知设置">${icon("bell")}</button>`)}
    <section class="card">
      <div class="flex items-center gap-3">
        <div class="grid h-14 w-14 place-items-center rounded-[12px] bg-[#17201C] text-white">${icon("user-round", "h-7 w-7")}</div>
        <div class="min-w-0">
          <p class="card-title">${state.parentRole}的家庭</p>
          <p class="card-subtitle">管理员 · 小宇 7 岁 · Mira Cam M1</p>
        </div>
      </div>
      <div class="metric-grid">
        ${metric("成员", "3", "info")}
        ${metric("设备", "1", "success")}
        ${metric("待处理", "2", "warning")}
      </div>
    </section>
    <section class="dense-grid">
      ${quickCard("报告中心", "日报、周报、成长", "file-text", "report")}
      ${quickCard("积分奖励", "奖励与兑换", "gift", "reward")}
      ${quickCard("打卡审核", "3 张素材", "clipboard-check", "checkin")}
      ${quickCard("家庭成员", "权限管理", "users", "family")}
    </section>
    <section class="section-stack">
      ${row("id-card", "个人信息", "家庭显示名、手机号、家长身份", "", "neutral", 'data-go="accountProfile"')}
      ${row("shield-check", "账号安全", "登录设备、更换手机号、注销流程", "", "neutral", 'data-go="accountSecurity"')}
      ${row("settings", "设备与规则", "设备、联系人、AI 规则、安全区域", "", "neutral", 'data-go="settings"')}
      ${row("lock-keyhole", "隐私与权限", "记录策略、数据导出、儿童数据删除", "", "neutral", 'data-go="privacy"')}
      ${row("aperture", "关于我们", "协议、隐私承诺、帮助反馈", "", "neutral", 'data-go="about"')}
    </section>
  `;
}

function renderAccountProfile() {
  return `
    ${screenHeader("个人信息", "当前家长")}
    <section class="form-card">
      <div class="input-group">
        <label for="profileName">家庭显示名</label>
        <input id="profileName" class="field" value="${state.parentRole}的家庭" />
      </div>
      <div class="input-group">
        <label for="profileRole">家长身份</label>
        <select id="profileRole" class="select-field"><option>${state.parentRole}</option><option>爸爸</option><option>祖辈</option><option>其他照护人</option></select>
      </div>
      ${row("smartphone", "登录手机号", "138 **** 2026，用于登录和安全验证", `<button class="secondary-button !min-h-[36px] !w-auto px-3" data-sheet="changePhoneSheet">更换</button>`, "info")}
    </section>
    ${primary("保存个人信息", 'data-action="quick-success" data-message="个人信息已保存"', "check")}
  `;
}

function renderAccountSecurity() {
  return `
    ${screenHeader("账号安全", "登录与设备")}
    <section class="section-stack">
      ${row("smartphone", "登录手机号", "138 **** 2026", `<button class="secondary-button !min-h-[36px] !w-auto px-3" data-sheet="changePhoneSheet">更换</button>`, "info")}
      ${row("monitor-smartphone", "登录设备", "本机 iPhone，今天 14:20 活跃", `<button class="secondary-button !min-h-[36px] !w-auto px-3" data-sheet="loginDevicesSheet">查看</button>`, "success")}
      ${row("trash-2", "注销账号", "注销前需要转移管理员或解绑设备", pill("危险", "danger"), "danger", 'data-sheet="deleteAccountSheet"')}
    </section>
  `;
}

function renderSubscription() {
  return `
    ${screenHeader("订阅与套餐", "米拉会员")}
    <section class="card bg-[#17201C] !text-white">
      <p class="text-sm text-white/60">当前套餐</p>
      <h3 class="mt-2 text-2xl font-black">基础版</h3>
      <p class="mt-2 text-sm leading-6 text-white/70">任务提醒、实时看护、本地日报、隐私控制和儿童数据删除保持可用。</p>
      <div class="metric-grid">
        ${metric("云存储", "7天", "info")}
        ${metric("成员", "3", "success")}
        ${metric("报告", "基础", "warning")}
      </div>
    </section>
    <section class="section-stack">
      ${row("sparkles", "家庭增强版", "长期趋势、更多云存储、更多 AI 人设", pill("推荐", "info"), "info", 'data-action="quick-success" data-message="套餐已更新"')}
      ${row("arrow-down-circle", "降级说明", "降级后云端历史片段保留到当前周期结束", "", "warning", 'data-sheet="subscriptionDowngradeSheet"')}
    </section>
  `;
}

function renderReport() {
  return `
    ${screenHeader("今日日报", "2026-05-28")}
    <section class="card status-rail">
      <p class="card-title">今天整体平稳，有 2 个家长确认点。</p>
      <p class="card-subtitle">作业完成质量正常，小书包还缺水杯；门口异常声音已进入待处理。</p>
      <div class="metric-grid">
        ${metric("任务完成", "5/6", "success")}
        ${metric("待确认", "2", "warning")}
        ${metric("安全", "1", "danger")}
      </div>
    </section>
    <section class="section-stack">
      ${row("file-check-2", "作业证据", "数学口算完成度 87%，待确认", pill("待确认", "warning"), "warning", 'data-go="taskDetail"')}
      ${row("backpack", "小书包", "水杯、数学练习册未确认", pill("待补", "warning"), "warning", 'data-go="packing"')}
      ${row("shield-alert", "安全事件", "门口异常声音待处理", pill("安全", "danger"), "danger", 'data-go="safetyDetail"')}
    </section>
  `;
}

function renderWeekly() {
  return `
    ${screenHeader("周报", "本周趋势与建议")}
    <section class="card">
      <div class="metric-grid">
        ${metric("专注均值", "32m", "success")}
        ${metric("睡前准时", "4/5", "info")}
        ${metric("异常", "2", "warning")}
      </div>
    </section>
    <section class="section-stack">
      ${row("chart-line", "趋势判断", "周三以后作业开始时间稳定提前 12 分钟", pill("改善", "success"), "success")}
      ${row("lightbulb", "家长建议", "把英语朗读放到晚饭后，减少睡前任务堆叠", pill("建议", "ai"), "ai")}
      ${row("shield", "隐私摘要", "本周无逐字聊天记录，保留 7 条事件截图", pill("可控", "success"), "success")}
    </section>
  `;
}

function renderMoments() {
  return `
    ${screenHeader("成长时刻", "精选片段")}
    <section class="media-card hero-card">
      <div class="hero-media min-h-[210px]"><img src="${images.family}" alt="家庭亲子互动真实照片" /></div>
    </section>
    <section class="section-stack">
      ${row("star", "主动整理书桌", "18:40，已收藏到成长时刻", pill("精选", "success"), "success")}
      ${row("book-open", "独立完成朗读", "英语朗读 10 分钟，语音清晰", pill("进步", "ai"), "ai")}
      ${row("heart", "周末户外活动", "奖励申请已同意稍后兑现", pill("计划中", "info"), "info")}
    </section>
  `;
}

function renderPoints() {
  return `
    ${screenHeader("积分总览", "余额与阶段")}
    <section class="card">
      <div class="metric-grid">
        ${metric("余额", "36", "success")}
        ${metric("本周新增", "+12", "info")}
        ${metric("阶段", "72%", "ai")}
      </div>
    </section>
    <section class="section-stack">
      ${row("plus", "数学口算确认", "+3 积分，妈妈确认", pill("已入账", "success"), "success")}
      ${row("gift", "周末户外活动", "-20 积分，待兑现", pill("申请中", "warning"), "warning", 'data-sheet="rewardRequestSheet"')}
      ${row("settings", "积分规则", "阶段阈值和奖励单位", "", "neutral", 'data-sheet="pointRuleSheet"')}
    </section>
  `;
}

function renderReward() {
  return `
    ${screenHeader("奖励商店", "亲子活动优先")}
    <section class="section-stack">
      ${row("trees", "周末户外活动", "20 积分，孩子已申请", `<button class="primary-button !min-h-[36px] !w-auto px-3" data-sheet="rewardRequestSheet">处理</button>`, "info")}
      ${row("cookie", "烘焙时间", "15 积分，周六下午可用", `<button class="secondary-button !min-h-[36px] !w-auto px-3" data-sheet="rewardEditSheet">修改</button>`, "success")}
      ${row("gamepad-2", "平板 20 分钟", "30 积分，需家长现场确认", `<button class="secondary-button !min-h-[36px] !w-auto px-3" data-sheet="manualRewardSheet">兑换</button>`, "warning")}
    </section>
    ${secondary("添加奖品", 'data-sheet="rewardEditSheet"', "plus")}
  `;
}

function renderCheckin() {
  return `
    ${screenHeader("打卡审核", "素材待审")}
    <section class="media-card hero-card">
      <div class="hero-media min-h-[220px]"><img src="${images.notebook}" alt="手工作业或作业素材真实照片" /></div>
    </section>
    <section class="card">
      <p class="card-title">兴趣班手工作业成品照</p>
      <p class="card-subtitle">摄像头已拍摄 3 张素材，家长审核后可保存或分享到其他 App。</p>
      <div class="button-row mt-3">
        ${primary("通过", 'data-action="quick-success" data-message="素材已通过"', "check")}
        ${secondary("要求重拍", 'data-action="quick-error" data-message="已要求重拍，孩子会收到温和提醒"', "refresh-cw")}
      </div>
    </section>
  `;
}

function renderConversation() {
  return `
    ${screenHeader("对话与人设", "AI 规则")}
    <section class="section-stack">
      ${row("badge", "摄像头唤醒名", "小豆，支持近似发音", `<button class="secondary-button !min-h-[36px] !w-auto px-3" data-go="name">修改</button>`, "info")}
      ${row("volume-2", "原创声线", "温柔女声，语速偏慢", `<button class="secondary-button !min-h-[36px] !w-auto px-3" data-action="play-voice">试听</button>`, "success")}
      ${settingLine("自由聊天", "单次 5 分钟，每日 20 分钟", "自由聊天")}
      ${settingLine("作业模式限制", "作业中只允许任务相关问答和温和提示", "任务待确认")}
      ${settingLine("睡前不主动聊天", "22:00 后不主动开启长时间自由聊天", "睡前不主动聊天")}
      ${settingLine("普通闲聊逐字记录", "默认关闭，只保存主题摘要", "普通闲聊逐字记录", true)}
    </section>
    <section class="button-row">
      ${secondary("隐私复核", 'data-go="privacy"', "lock-keyhole")}
      ${primary("保存 AI 规则", 'data-action="save-rules"', "check")}
    </section>
  `;
}

function renderPrivacy() {
  return `
    ${screenHeader("隐私与权限", "数据可控")}
    <section class="section-stack">
      ${settingLine("隐私模式", "开启后实时看护和记录入口受限", "隐私模式")}
      ${settingLine("远程查看提示", "家长查看时设备端显示工作状态", "安全告警")}
      ${settingLine("普通闲聊逐字记录", "默认关闭，只展示主题摘要", "普通闲聊逐字记录", true)}
      ${settingLine("只保存事件截图", "不保存全天连续录像", "任务待确认")}
    </section>
    <section class="card">
      <p class="card-title">儿童数据权利</p>
      <p class="card-subtitle">支持导出、删除、最小必要保存和处理记录追踪。</p>
      <div class="button-row mt-3">
        ${secondary("导出数据", 'data-action="quick-success" data-message="已提交导出请求"', "download")}
        ${danger("删除数据", 'data-sheet="deleteDataSheet"', "trash-2")}
      </div>
    </section>
  `;
}

function renderFamily() {
  return `
    ${screenHeader("家庭成员", "权限管理")}
    <section class="section-stack">
      ${row("user-round", "妈妈", "管理员，全部权限", pill("管理员", "success"), "success")}
      ${row("user-round", "爸爸", "监护人，看护、报告、安全事件", pill("监护人", "info"), "info")}
      ${row("user-round", "奶奶", "临时查看者，只看今日待办和提醒", pill("只读", "warning"), "warning")}
    </section>
    ${primary("邀请成员", 'data-sheet="memberSheet"', "user-plus")}
  `;
}

function renderDevice() {
  return `
    ${screenHeader("设备管理", "儿童房摄像头")}
    <section class="media-card hero-card">
      <div class="hero-media min-h-[190px]"><img src="${images.device}" alt="智能摄像头设备真实照片" /></div>
    </section>
    <section class="section-stack">
      ${row("camera", "Mira Cam M1", "在线，固件 1.2.8，儿童房", pill("在线", "success"), "success")}
      ${row("wifi", "网络状态", "Mira Home 5G，信号良好，延迟 38ms", pill("良好", "success"), "success")}
      ${row("refresh-cw", "固件升级", "1.2.9 可用，预计 4 分钟", `<button class="secondary-button !min-h-[36px] !w-auto px-3" data-state="updating">升级</button>`, "info")}
      ${row("rotate-3d", "云台校准", "书桌、床、门口、玩具区", `<button class="secondary-button !min-h-[36px] !w-auto px-3" data-action="calibrate">校准</button>`, "info")}
      ${row("power", "解绑或转移", "需要管理员确认，升级中不可解绑", `<button class="danger-button !min-h-[36px] !w-auto px-3" data-sheet="unbindSheet">解绑</button>`, "danger")}
    </section>
  `;
}

function renderNotifications() {
  return `
    ${screenHeader("通知设置", "只提醒真正重要的事")}
    <section class="section-stack">
      ${settingLine("安全告警", "SOS、门口、危险区域和异常声音", "安全告警")}
      ${settingLine("任务待确认", "作业证据、打卡素材和奖励申请确认", "任务待确认")}
      ${settingLine("任务提醒", "小书包、睡前任务、晨起闹铃", "自由聊天")}
      ${settingLine("普通闲聊摘要", "每天最多一次，不打扰工作时间", "普通闲聊逐字记录", true)}
    </section>
  `;
}

function renderEducation() {
  return `
    ${screenHeader("学习内容", "内容生态入口")}
    <section class="section-stack">
      ${row("backpack", "小书包设置", "课程表、老师通知、上学物品", pill("已启用", "success"), "success", 'data-go="packing"')}
      ${row("graduation-cap", "合作内容", "预留授权内容入口，不绕过第三方规则", pill("规划中", "warning"), "warning")}
      ${row("brain", "学习缺漏诊断", "长期数据积累后开启", pill("P2", "neutral"), "neutral")}
    </section>
  `;
}

function renderSettings() {
  return `
    ${screenHeader("设备与规则", "管理聚合")}
    <section class="section-stack">
      ${row("camera", "设备管理", "网络、固件、隐私灯、云台校准", pill("在线", "success"), "success", 'data-go="device"')}
      ${row("bot", "AI 规则", "唤醒名、声线、自由聊天、作业模式", pill("平衡", "ai"), "ai", 'data-go="conversation"')}
      ${row("map", "安全区域", "书桌、床、门口、玩具区规则", pill("4 区", "info"), "info", 'data-go="zones"')}
      ${row("phone-call", "紧急联系人", "SOS 和安全告警兜底联系人", pill("2 人", "success"), "success", 'data-go="contacts"')}
      ${row("bell", "通知设置", "告警、任务确认、奖励申请", "", "neutral", 'data-go="notifications"')}
    </section>
  `;
}

function renderFeedback() {
  return `
    ${screenHeader("帮助与反馈", "让问题能被追踪")}
    <section class="section-stack">
      ${row("message-square", "提交产品反馈", "体验问题、建议、误判样例", `<button class="secondary-button !min-h-[36px] !w-auto px-3" data-sheet="feedbackSheet">提交</button>`, "info")}
      ${row("bug", "上报 AI 误判", "关联证据、任务和处理结果", `<button class="secondary-button !min-h-[36px] !w-auto px-3" data-sheet="feedbackSheet">上报</button>`, "warning")}
      ${row("headphones", "联系客服", "工作日 9:00 - 21:00", `<button class="secondary-button !min-h-[36px] !w-auto px-3" data-action="quick-toast" data-message="正在连接客服">联系</button>`, "success")}
    </section>
  `;
}

function renderAbout() {
  return `
    ${screenHeader("Mira Guardian 米拉", "关于我们")}
    <section class="card text-center">
      <div class="mx-auto grid h-16 w-16 place-items-center rounded-[14px] bg-[#17201C] text-white">${icon("aperture", "h-8 w-8")}</div>
      <h3 class="mt-4 text-xl font-black">家庭 AI 智护与成长中枢</h3>
      <p class="mt-2 text-sm leading-6 text-[var(--muted)]">以家长规则为边界，以孩子真实生活场景为中心。</p>
    </section>
    <section class="section-stack">
      ${row("message-square", "帮助与反馈", "误判上报、客服、常见问题", "", "info", 'data-go="feedback"')}
      ${row("download-cloud", "当前版本", "v0.9.0 高保真原型 · 2026.05.28", `<button class="secondary-button !min-h-[36px] !w-auto px-3" data-action="quick-success" data-message="已是最新版本">检查</button>`, "info")}
      ${row("file-text", "服务协议", "查看服务条款和家庭使用说明", "", "neutral", 'data-sheet="termsSheet"')}
      ${row("lock-keyhole", "隐私政策", "儿童数据、权限和删除说明", "", "neutral", 'data-sheet="privacyPolicySheet"')}
    </section>
  `;
}

function settingLine(title, desc, key, risky = false) {
  const enabled = !!state.toggles[key];
  return `
    <button class="row setting-line" type="button" data-action="toggle" data-value="${key}" ${risky ? 'data-risky="true"' : ""}>
      <span class="row-icon ${enabled ? "success" : "neutral"}">${icon(risky ? "shield-alert" : "toggle-right")}</span>
      <span class="row-main">
        <span class="row-title">${title}</span>
        <span class="row-desc">${desc}</span>
      </span>
      <span class="relative inline-flex h-7 w-12 items-center rounded-full ${enabled ? "bg-[var(--accent)]" : "bg-[var(--line)]"}">
        <span class="absolute h-5 w-5 rounded-full bg-white shadow ${enabled ? "right-1" : "left-1"}"></span>
      </span>
    </button>
  `;
}

function renderStateScene(pageData, mode) {
  const meta = STATUS[mode] || STATUS.default;
  if (mode === "loading") {
    return `
      <section class="screen">
        ${screenHeader(pageData.name, `${meta.label} · ${pageData.subtitle}`)}
        <section class="card">
          <div class="skeleton h-8 w-36"></div>
          <div class="skeleton mt-4 h-24 w-full"></div>
          <div class="metric-grid">
            <div class="skeleton h-20"></div>
            <div class="skeleton h-20"></div>
            <div class="skeleton h-20"></div>
          </div>
        </section>
        <section class="section-stack mt-3">
          <div class="skeleton h-16"></div>
          <div class="skeleton h-16"></div>
          <div class="skeleton h-16"></div>
        </section>
      </section>
    `;
  }

  const scene = {
    empty: ["inbox", "这里暂时没有内容", `${pageData.name}没有可展示的数据。可以创建任务、绑定设备，或清除筛选后再查看。`, "创建或刷新", "plus"],
    error: ["circle-alert", "加载失败", `${pageData.name}暂时无法加载。请检查网络或稍后重试，已保留本地最近一次可用内容。`, "重试", "refresh-cw"],
    success: ["circle-check", "操作已完成", `${pageData.name}已更新，处理记录会进入日报与家庭协作流水。`, "返回默认", "check"],
    permissionDenied: ["lock-keyhole", "暂无权限", `当前家庭角色不能操作${pageData.name}。可以联系管理员调整权限，或查看只读内容。`, "查看权限说明", "shield"],
    noResult: ["search-x", "没有匹配结果", `${pageData.name}当前筛选条件没有命中。可以清除筛选、换日期或查看全部记录。`, "清除筛选", "x"],
    offline: ["wifi-off", "设备离线", "Mira Cam M1 最后在线时间为 19:31。实时看护、设备提醒和通话暂不可用，本地任务会等待同步。", "查看重连步骤", "wifi"],
    abnormal: ["siren", "发现异常", `${pageData.name}检测到需要家长判断的异常。请查看证据、触发规则和处理记录。`, "进入事件详情", "arrow-right"],
    updating: ["refresh-cw", "正在更新", "设备或规则正在同步。升级期间不可解绑设备、关闭电源或修改关键提醒。", "查看进度", "activity"],
    privacyMode: ["shield-off", "隐私模式已开启", "实时画面和部分记录入口被阻断。管理员可以在隐私与权限里查看原因并调整。", "打开隐私设置", "lock-keyhole"],
    weakNetwork: ["signal-low", "网络较弱", "画面已切换为低清稳定模式，截图和通话可能延迟。可尝试重连或检查家庭 Wi-Fi。", "尝试重连", "radio-tower"],
    reconnecting: ["radio-tower", "正在重连", "摄像头连接中断，系统正在重新建立实时通道。历史事件仍可查看。", "继续等待", "loader-circle"],
  }[mode] || ["panel-top", "默认状态", pageData.subtitle, "返回默认", "arrow-right"];

  const target = {
    abnormal: "safetyDetail",
    privacyMode: "privacy",
    offline: "deviceOffline",
    permissionDenied: "family",
  }[mode];

  return `
    <section class="screen">
      ${screenHeader(pageData.name, `${meta.label} · ${pageData.subtitle}`)}
      <section class="state-card text-center status-rail ${meta.tone === "danger" ? "danger" : meta.tone === "warning" ? "warning" : meta.tone === "info" ? "ai" : ""}">
        <div class="mx-auto grid h-16 w-16 place-items-center rounded-full ${stateToneBg(meta.tone)}">${icon(scene[0], "h-8 w-8")}</div>
        <h3 class="mt-4 text-2xl font-black">${scene[1]}</h3>
        <p class="mt-2 text-sm leading-6 text-[var(--muted)]">${scene[2]}</p>
        <div class="button-row mt-5">
          ${secondary("切回 default", 'data-state="default"', "panel-top")}
          ${primary(scene[3], target ? `data-go="${target}"` : `data-action="state-feedback" data-mode="${mode}"`, scene[4])}
        </div>
      </section>
      <section class="card">
        <p class="card-title">这个状态覆盖的验收点</p>
        <p class="card-subtitle">状态：${meta.label}；页面：${pageData.name}；模块：${pageData.group}。</p>
        <div class="component-strip mt-3">
          ${pill("toast", "info", "message-square")}
          ${pill("button feedback", "success", "mouse-pointer-click")}
          ${pill("state switch", "neutral", "sliders-horizontal")}
        </div>
      </section>
    </section>
  `;
}

function stateToneBg(tone) {
  return {
    danger: "bg-[var(--danger-soft)] text-[var(--danger)]",
    warning: "bg-[var(--warning-soft)] text-[var(--warning)]",
    success: "bg-[var(--success-soft)] text-[var(--success)]",
    info: "bg-[var(--info-soft)] text-[var(--info)]",
  }[tone] || "bg-[var(--surface-2)] text-[var(--muted)]";
}

function renderComponentStates() {
  return `
    ${screenHeader("组件状态总览", "全局组件状态实验台")}
    <section class="card">
      <p class="card-title">Buttons</p>
      <div class="grid gap-2 mt-3">
        ${primary("default / pressed", 'data-action="quick-success" data-message="按钮 pressed + success toast 已触发"', "check")}
        ${secondary("loading", 'data-action="demo-loading"', "loader-circle")}
        <button class="secondary-button" disabled>${icon("ban")}disabled：角色无权或字段缺失</button>
        ${danger("danger", 'data-sheet="unbindSheet"', "trash-2")}
      </div>
    </section>
    <section class="card">
      <p class="card-title">Cards / List items / Tags</p>
      <div class="component-strip mt-3">
        ${pill("selected", "success", "check")}
        ${pill("pending review", "warning", "clock")}
        ${pill("danger", "danger", "siren")}
        ${pill("AI 建议", "ai", "bot")}
        ${pill("offline", "danger", "wifi-off")}
      </div>
      <div class="mt-3">
        ${row("file-check-2", "pending review", "任务证据、打卡素材、奖励申请", pill("待审", "warning"), "warning")}
        ${row("shield-check", "resolved", "已处理事件进入日报和处理记录", pill("已处理", "success"), "success")}
      </div>
    </section>
    <section class="form-card">
      <p class="card-title">Forms / Search / Filter / Sort</p>
      <div class="input-group">
        <label for="stateInput">表单字段<span>focused / error / saving</span></label>
        <input id="stateInput" class="field field-error" value="结束时间早于开始时间" />
        <p class="form-hint error">请调整结束时间，或改为“无结束时间”。</p>
      </div>
      <div class="search-row mt-3">
        ${icon("search")}
        <input value="门口事件" aria-label="搜索演示" />
      </div>
      <div class="button-row mt-3">
        ${secondary("no result", 'data-state="noResult"', "search-x")}
        ${secondary("error toast", 'data-action="quick-error" data-message="保存失败，请检查网络后重试"', "circle-alert")}
      </div>
    </section>
  `;
}

function renderCoverage() {
  const groups = ["Onboarding", "首页", "任务", "看护", "我的", "验收"];
  const rows = groups
    .map((group) => {
      const pages = PAGES.filter((item) => item.group === group);
      const pageNames = pages.map((item) => item.name).join("、");
      const states = [...new Set(pages.flatMap((item) => item.states.map((key) => STATUS[key]?.label || key)))].join(" / ");
      return `<tr><td>${group}</td><td>${pages.length} 页</td><td>${pageNames}</td><td>${states}</td><td>已覆盖，可通过右侧页面清单和状态 chips 点击验证</td></tr>`;
    })
    .join("");
  return `
    ${screenHeader("矩阵覆盖说明", "基于 app-flow-and-state-matrix.md")}
    <section class="card">
      <p class="card-title">覆盖范围</p>
      <p class="card-subtitle">当前原型实现 ${PAGES.length} 个页面入口、${SHEETS.length} 个 sheet/弹层入口、${ALL_STATES.length} 类全局状态。旧 HTML 只用于业务范围核对，视觉没有沿用。</p>
    </section>
    <table class="coverage-table" aria-label="状态矩阵覆盖表">
      <thead><tr><th>模块</th><th>数量</th><th>页面</th><th>状态</th><th>覆盖说明</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <section class="card">
      <p class="card-title">补充矩阵项</p>
      <p class="card-subtitle">已把 permissions、deviceOffline、privacyBlock、componentStates 补进矩阵，作为验收时可点击的独立页面/状态实验台。</p>
    </section>
  `;
}

function renderTabbar(pageData) {
  const root = rootFor(pageData);
  const items = [
    ["home", "layout-dashboard", "首页"],
    ["tasks", "calendar-check", "任务"],
    ["create", "plus", "创建"],
    ["watch", "video", "看护"],
    ["my", "user-cog", "我的"],
  ];
  const disabled = pageData.group === "Onboarding";
  tabbar.innerHTML = items
    .map(([id, iconName, label]) => {
      if (id === "create") {
        return `<button class="tab-create" type="button" data-sheet="${disabled ? "" : "createTaskSheet"}" data-disabled-toast="${disabled ? "完成登录与绑定后才能创建任务" : ""}" aria-label="创建任务">${icon(iconName)}</button>`;
      }
      return `<button class="tab-item ${root === id ? "is-active" : ""}" type="button" data-go="${disabled ? "" : id}" data-disabled-toast="${disabled ? "完成首次设置后进入主导航" : ""}" aria-label="${label}">${icon(iconName)}<span>${label}</span></button>`;
    })
    .join("");
}

function rootFor(pageData) {
  if (["home", "care", "sleep"].includes(pageData.id)) return "home";
  if (["tasks", "createTask", "flow", "packing", "taskDetail", "focus"].includes(pageData.id)) return "tasks";
  if (["watch", "playback", "zones", "safety", "safetyDetail", "deviceOffline", "privacyBlock"].includes(pageData.id)) return "watch";
  if (pageData.group === "我的") return "my";
  return "";
}

function renderPanel() {
  pageCount.textContent = `${PAGES.length} 页`;
  sheetCount.textContent = `${SHEETS.length} 个`;

  stateChips.innerHTML = ALL_STATES.map((key) => {
    const meta = STATUS[key];
    const active = state.mode === key ? "is-active" : "";
    return `<button class="state-chip ${active}" type="button" data-state="${key}">${icon(meta.icon)}${meta.label}</button>`;
  }).join("");

  const query = state.search.trim().toLowerCase();
  const groups = [...new Set(PAGES.map((item) => item.group))];
  pageMap.innerHTML = groups
    .map((group) => {
      const pages = PAGES.filter((item) => item.group === group).filter((item) => {
        if (!query) return true;
        return `${item.name} ${item.subtitle} ${item.group} ${item.states.join(" ")}`.toLowerCase().includes(query);
      });
      if (!pages.length) return "";
      return `
        <div class="page-group">
          <p class="page-group-title">${group}</p>
          ${pages.map((item) => `<button class="page-pill ${state.page === item.id ? "is-active" : ""}" type="button" data-go="${item.id}"><span>${icon(item.icon)}${item.name}</span><small>${item.states.length} states</small></button>`).join("")}
        </div>
      `;
    })
    .join("");

  sheetMap.innerHTML = SHEETS.map(([id, name, type]) => `<button class="sheet-pill" type="button" data-sheet="${id}" title="${type}">${name}</button>`).join("");
}

function openSheet(id) {
  const meta = sheetById[id] || [id, "操作", "bottom sheet", "操作确认"];
  const content = sheetContent(id, meta);
  sheetRoot.innerHTML = `
    <div class="sheet-backdrop" data-close-layer="sheet">
      <section class="sheet" role="dialog" aria-modal="true" aria-label="${meta[1]}">
        <div class="sheet-handle"></div>
        <div class="sheet-head">
          <div>
            <h3>${meta[1]}</h3>
            <p>${meta[2]} · ${meta[3]}</p>
          </div>
          <button class="icon-button" type="button" data-close-sheet aria-label="关闭">${icon("x")}</button>
        </div>
        <div class="mt-4">${content}</div>
      </section>
    </div>
  `;
  hydrateIcons();
}

function sheetContent(id) {
  if (id === "createTaskSheet") {
    return `
      <div class="section-stack">
        ${row("check-square", "普通任务", "作业、朗读、运动、家务", "", "info", 'data-go="createTask" data-close-sheet')}
        ${row("backpack", "小书包", "按课程表生成明日物品", "", "info", 'data-go="packing" data-close-sheet')}
        ${row("moon", "睡前任务", "洗漱、整理、上床节奏", "", "info", 'data-go="sleep" data-close-sheet')}
        ${row("clipboard-check", "打卡任务", "兴趣班、手工、阅读素材", "", "info", 'data-go="checkin" data-close-sheet')}
        ${row("gift", "奖励规则", "积分、奖品、阶段阈值", "", "info", 'data-go="reward" data-close-sheet')}
      </div>
    `;
  }
  if (id.includes("delete") || id === "unbindSheet" || id === "logoutSheet") {
    return `
      <div class="card !shadow-none">
        <p class="card-title">确认前请检查影响范围</p>
        <p class="card-subtitle">危险操作会写入处理记录，部分操作需要管理员二次验证。</p>
      </div>
      <div class="button-row mt-3">
        ${secondary("取消", "data-close-sheet", "x")}
        ${danger("确认", 'data-action="danger-confirm"', "triangle-alert")}
      </div>
    `;
  }
  if (id === "feedbackSheet") {
    return `
      <div class="form-card !shadow-none">
        <div class="input-group">
          <label for="feedbackType">类型</label>
          <select id="feedbackType" class="select-field"><option>AI 误判</option><option>设备离线</option><option>交互建议</option></select>
        </div>
        <div class="input-group">
          <label for="feedbackText">问题描述</label>
          <textarea id="feedbackText" class="text-area">数学口算完成后，AI 把整理橡皮的动作误判成离席。</textarea>
        </div>
      </div>
      ${primary("提交反馈", 'data-action="submit-feedback"', "send")}
    `;
  }
  if (id === "rewardRequestSheet") {
    return `
      <div class="card !shadow-none">
        <p class="card-title">小宇申请兑换“周末户外活动”</p>
        <p class="card-subtitle">当前余额 36 积分，本次扣除 20。申请来源：数学口算连续 5 天完成。</p>
      </div>
      <div class="button-row mt-3">
        ${primary("同意兑现", 'data-action="reward-fulfilled"', "check")}
        ${secondary("同意稍后", 'data-action="reward-planned"', "clock")}
      </div>
      <button class="danger-button mt-2" data-action="reward-rejected">${icon("x")}暂不兑换</button>
    `;
  }
  if (id === "evidenceSheet") {
    return `
      <div class="section-stack">
        ${row("check", "确认完成", "奖励 +3，进入日报", "", "success", 'data-action="evidence-confirm"')}
        ${row("split", "部分完成", "奖励 +1，保留家长备注", "", "warning", 'data-action="evidence-partial"')}
        ${row("x", "驳回 AI 判断", "进入误判样本，撤销自动加分", "", "danger", 'data-action="evidence-reject"')}
      </div>
    `;
  }
  if (id === "callSheet") {
    return `
      <div class="card !shadow-none">
        <p class="card-title">发起音频通话？</p>
        <p class="card-subtitle">设备端会亮起提示灯并播放来电铃声；隐私模式下不可通话。</p>
      </div>
      <div class="button-row mt-3">
        ${secondary("取消", "data-close-sheet", "x")}
        ${primary("发起通话", 'data-action="start-call"', "phone")}
      </div>
    `;
  }
  if (id === "privacyNoticeSheet" || id === "privacyPolicySheet" || id === "termsSheet" || id === "privacySheet") {
    return `
      <div class="section-stack">
        ${row("shield-check", "最小必要采集", "只在任务、看护和安全事件需要时处理相关数据", pill("原则", "success"), "success")}
        ${row("eye", "远程查看提示", "家长查看实时画面时设备端会有可见提示", pill("透明", "info"), "info")}
        ${row("trash-2", "可导出与删除", "儿童数据可由管理员申请导出或删除", pill("可控", "warning"), "warning", 'data-go="privacy" data-close-sheet')}
      </div>
    `;
  }
  return `
    <div class="section-stack">
      ${row("settings", "默认操作", "该弹层已覆盖真实 UI、pressed、loading、success/error toast", pill("可点击", "info"), "info", 'data-action="quick-success" data-message="设置已保存"')}
      ${row("clock", "保存中状态", "点击后会展示按钮 loading，再给出成功反馈", "", "neutral", 'data-action="demo-loading"')}
      ${row("circle-alert", "错误反馈", "用于验证 error toast 和表单/操作失败提示", "", "danger", 'data-action="quick-error" data-message="操作失败，请稍后重试"')}
    </div>
  `;
}

function openModal(title, message, dangerMode = false) {
  modalRoot.innerHTML = `
    <div class="modal-backdrop" data-close-layer="modal">
      <section class="modal-card" role="dialog" aria-modal="true" aria-label="${title}">
        <h3>${title}</h3>
        <p>${message}</p>
        <div class="button-row mt-4">
          ${secondary("取消", "data-close-modal", "x")}
          ${dangerMode ? danger("确认", 'data-action="modal-confirm"', "triangle-alert") : primary("确认", 'data-action="modal-confirm"', "check")}
        </div>
      </section>
    </div>
  `;
  hydrateIcons();
}

function closeSheet() {
  sheetRoot.innerHTML = "";
}

function closeModal() {
  modalRoot.innerHTML = "";
}

function toast(type, title, message = "") {
  const id = `toast-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const iconName = {
    success: "circle-check",
    error: "circle-alert",
    warning: "triangle-alert",
    info: "info",
  }[type] || "info";
  toastRoot.insertAdjacentHTML(
    "beforeend",
    `<div id="${id}" class="toast ${type}">${icon(iconName)}<div><strong>${title}</strong>${message ? `<span>${message}</span>` : ""}</div></div>`,
  );
  hydrateIcons();
  setTimeout(() => {
    const el = document.getElementById(id);
    if (el) el.remove();
  }, 3200);
}

function setMode(mode) {
  state.mode = mode;
  render();
}

function go(pageId) {
  if (!pageId || !pageById[pageId]) return;
  state.page = pageId;
  state.mode = "default";
  closeSheet();
  closeModal();
  render();
}

function simulateLoading(button, successTitle, successMessage = "") {
  if (!button) return;
  const old = button.innerHTML;
  button.disabled = true;
  button.innerHTML = `<span class="mini-spinner"></span>处理中`;
  hydrateIcons();
  setTimeout(() => {
    button.disabled = false;
    button.innerHTML = old;
    toast("success", successTitle, successMessage);
    hydrateIcons();
  }, 850);
}

function validateTask(button) {
  const title = document.getElementById("taskTitle");
  const start = document.getElementById("taskStart");
  const end = document.getElementById("taskEnd");
  const hint = document.getElementById("taskTitleHint");
  [title, start, end].forEach((el) => el?.classList.remove("field-error"));
  if (!title?.value.trim()) {
    title.classList.add("field-error");
    if (hint) {
      hint.classList.add("error");
      hint.textContent = "任务名称不能为空。";
    }
    toast("error", "表单校验失败", "请填写任务名称。");
    return;
  }
  if (start?.value && end?.value && start.value >= end.value) {
    end.classList.add("field-error");
    toast("error", "时间不合法", "结束时间必须晚于开始时间。");
    return;
  }
  simulateLoading(button, "任务已创建", "已加入今天 19:20 的任务列表。");
  setTimeout(() => go("taskDetail"), 920);
}

function handleAction(action, target) {
  const message = target.dataset.message || "";
  switch (action) {
    case "send-code":
      simulateLoading(target, "验证码已发送", "60 秒后可重新获取。");
      break;
    case "login":
      simulateLoading(target, "登录成功", "正在进入家长身份设置。");
      setTimeout(() => go("parentIdentity"), 920);
      break;
    case "select-role":
      state.parentRole = target.dataset.value;
      render();
      break;
    case "scan-bluetooth":
      simulateLoading(target, "已发现 Mira Cam M1", "距离约 1.8 米，可以继续配网。");
      break;
    case "bind-device":
      simulateLoading(target, "设备绑定成功", "隐私灯测试通过。");
      setTimeout(() => go("bindDone"), 920);
      break;
    case "play-voice":
      toast("info", "正在试听声线", "温柔女声，语速偏慢。");
      break;
    case "invite-contact":
      simulateLoading(target, "邀请已发送", "爸爸会收到家庭成员邀请。");
      break;
    case "request-permission":
      simulateLoading(target, `${target.dataset.permission}权限已请求`, "如果系统拒绝，可在设置中重新开启。");
      break;
    case "select-day":
      state.selectedDay = target.dataset.value;
      render();
      break;
    case "save-task":
      validateTask(target);
      break;
    case "evidence-confirm":
    case "evidence-partial":
    case "evidence-reject":
      closeSheet();
      simulateLoading(target, "证据处理完成", "结果已进入日报、积分流水和 AI 纠错记录。");
      break;
    case "capture":
      simulateLoading(target, "截图已保存", "已存入事件回放，可用于日报或反馈。");
      break;
    case "start-call":
      closeSheet();
      simulateLoading(target, "正在发起通话", "设备端会亮起远程通话提示。");
      break;
    case "resolve-safety":
      simulateLoading(target, "事件已标记处理", "处理记录已写入安全事件详情。");
      break;
    case "calibrate":
      simulateLoading(target, "云台校准完成", "书桌、床、门口视角已更新。");
      break;
    case "save-rules":
      openModal("保存 AI 规则？", "修改自由聊天、作业模式或逐字记录时，会同步到设备并进入隐私复核。", false);
      break;
    case "toggle": {
      const key = target.dataset.value;
      if (target.dataset.risky === "true" && !state.toggles[key]) {
        openModal("开启高敏感记录？", "逐字记录会增加儿童数据敏感度。建议只在明确需要时短期开启，并保留处理记录。", false);
      }
      state.toggles[key] = !state.toggles[key];
      toast("success", "设置已保存", `${key} 已${state.toggles[key] ? "开启" : "关闭"}。`);
      render();
      break;
    }
    case "quick-success":
      simulateLoading(target, message || "操作已完成");
      break;
    case "quick-error":
      toast("error", "操作失败", message || "请检查网络后重试。");
      break;
    case "quick-toast":
      toast("info", message || "已操作");
      break;
    case "state-feedback":
      toast(STATUS[target.dataset.mode]?.tone === "danger" ? "error" : "info", "状态反馈已触发", STATUS[target.dataset.mode]?.label || target.dataset.mode);
      break;
    case "demo-loading":
      simulateLoading(target, "loading 已完成", "按钮从 loading 回到 success toast。");
      break;
    case "reward-fulfilled":
    case "reward-planned":
    case "reward-rejected":
      closeSheet();
      toast(action === "reward-rejected" ? "warning" : "success", "奖励申请已处理", action === "reward-fulfilled" ? "已兑现并扣除 20 积分。" : action === "reward-planned" ? "已安排周末提醒。" : "已温和反馈给孩子。");
      break;
    case "danger-confirm":
      closeSheet();
      toast("warning", "危险操作已进入二次确认", "管理员会收到安全验证。");
      break;
    case "submit-feedback":
      closeSheet();
      simulateLoading(target, "反馈已提交", "关联证据会进入 AI 误判排查队列。");
      break;
    case "modal-confirm":
      closeModal();
      toast("success", "已确认", "操作结果已记录。");
      break;
    default:
      toast("info", "操作已触发", action || "unknown action");
  }
}

document.addEventListener("click", (event) => {
  const disabled = event.target.closest("[data-disabled-toast]");
  if (disabled && disabled.dataset.disabledToast) {
    toast("warning", "当前不可用", disabled.dataset.disabledToast);
    return;
  }

  const closeSheetBtn = event.target.closest("[data-close-sheet]");
  if (closeSheetBtn) closeSheet();

  const closeModalBtn = event.target.closest("[data-close-modal]");
  if (closeModalBtn) closeModal();

  const layer = event.target.closest("[data-close-layer]");
  if (layer && event.target === layer) {
    if (layer.dataset.closeLayer === "sheet") closeSheet();
    if (layer.dataset.closeLayer === "modal") closeModal();
  }

  const goTarget = event.target.closest("[data-go]");
  if (goTarget && goTarget.dataset.go) {
    go(goTarget.dataset.go);
    return;
  }

  const stateTarget = event.target.closest("[data-state]");
  if (stateTarget) {
    setMode(stateTarget.dataset.state);
    return;
  }

  const sheetTarget = event.target.closest("[data-sheet]");
  if (sheetTarget && sheetTarget.dataset.sheet) {
    openSheet(sheetTarget.dataset.sheet);
    return;
  }

  const confirmTarget = event.target.closest("[data-confirm]");
  if (confirmTarget) {
    openModal(confirmTarget.dataset.confirm, confirmTarget.dataset.confirmMessage || "确认执行该操作？", true);
    return;
  }

  const actionTarget = event.target.closest("[data-action]");
  if (actionTarget) {
    handleAction(actionTarget.dataset.action, actionTarget);
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const actionable = event.target.closest('[role="button"][data-go], [role="button"][data-sheet], [role="button"][data-action], [role="button"][data-state]');
  if (!actionable) return;
  event.preventDefault();
  actionable.click();
});

pageSearch.addEventListener("input", (event) => {
  state.search = event.target.value;
  renderPanel();
  hydrateIcons();
});

render();
