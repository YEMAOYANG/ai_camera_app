"use strict";

const $ = (selector) => document.querySelector(selector);
const app = $("#app");
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        character
      ],
  );
const paths = {
  sound:
    '<path d="m11 5-5 4H3v6h3l5 4V5Z"/><path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',
  mute: '<path d="m11 5-5 4H3v6h3l5 4V5Z"/><path d="m16 9 6 6m0-6-6 6"/>',
  next: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  hint: '<path d="M9 18h6m-5 3h4M8 14a7 7 0 1 1 8 0c-1 1-1 2-1 2H9s0-1-1-2Z"/>',
  mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2m-7 9v3m-4 0h8"/>',
  check: '<path d="m5 12 4 4L20 5"/>',
  play: '<path d="m8 4 13 8-13 8V4Z"/>',
  leaf: '<path d="M20 3c-8 0-17 2-17 10a7 7 0 0 0 7 7c8 0 10-9 10-17Z"/><path d="m4 20 10-10"/>',
  book: '<path d="M12 5c-3-3-7-3-10-2v16c4-1 7 0 10 2m0-16c3-3 7-3 10-2v16c-4-1-7 0-10 2V5Z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 3"/>',
};
const icon = (name) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.play}</svg>`;
const button = (action, label, options = {}) =>
  `<button type="button" data-action="${esc(action)}"${options.choice != null ? ` data-choice="${esc(options.choice)}"` : ""}${options.disabled ? " disabled" : ""}${options.pressed != null ? ` aria-pressed="${options.pressed}"` : ""}${options.aria ? ` aria-label="${esc(options.aria)}"` : ""} class="${options.className || ""}">${options.icon ? icon(options.icon) : ""}${esc(label)}</button>`;
const words = ["天", "地", "人", "我", "你", "他"];
const names = {
  sky: "天空",
  earth: "地面",
  coral: "红衣女孩",
  teal: "蓝衣男孩",
  yellow: "黄衣男孩",
};
const titles = {
  explore: "点开字宝宝的名字",
  hunt: "字宝宝，躲在哪里？",
  "role-demo": "你来选，谁说话",
  roles: "换个人，称呼变一变",
  check: "六个字，我来认",
  repair: "这一小步，再试试",
  transfer: "换个故事，还会吗？",
  review: "隔了一天，还记得吗？",
  "review-preview": "试试复习怎么玩",
};
let state = null;
let selection = null;
let busy = false;
let muted = false;
let lastAudio = [];
let player = null;
let audioEpoch = 0;
let audioStatus = "";
let reportData = null;

function stopAudio() {
  audioEpoch += 1;
  if (player) {
    player.pause();
    player.onended = player.onerror = null;
    player.removeAttribute("src");
    player.load();
    player = null;
  }
}

function playAudio(keys) {
  stopAudio();
  lastAudio = [...keys];
  audioStatus = "";
  updateAudioError();
  if (
    muted ||
    document.hidden ||
    $("#pause-dialog").open ||
    $("#parent-dialog").open ||
    !keys.length
  )
    return;
  const epoch = audioEpoch;
  const queue = [...keys];
  const next = () => {
    if (epoch !== audioEpoch || !queue.length) return;
    const current = new Audio(`/assets/${encodeURIComponent(queue.shift())}`);
    player = current;
    const failed = () => {
      if (epoch !== audioEpoch) return;
      audioStatus = "声音没放出来，点一下再试。";
      updateAudioError();
    };
    current.onended = next;
    current.onerror = failed;
    void current.play().catch(failed);
  };
  next();
}

function updateAudioError() {
  const target = $("#audio-status");
  if (target)
    target.innerHTML = audioStatus
      ? `<span>${esc(audioStatus)}</span>${button("audio-retry", "重试播放", { icon: "sound" })}`
      : "";
}

function cue(value = state) {
  if (value.answered || value.solved) return value.feedbackAudio;
  if (value.question) return [value.question.audio];
  return value.cueAudio || [];
}

async function request(path, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(path, {
      method: body ? "POST" : "GET",
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
      ...(body
        ? {
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }
        : {}),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "进度暂时没连上。");
    return data;
  } finally {
    clearTimeout(timer);
  }
}

function connectionError(error) {
  stopAudio();
  const message =
    error.name === "AbortError"
      ? "连接慢了一点。"
      : error instanceof TypeError
        ? "暂时没连上。"
        : error.message;
  $("#connection span").textContent = `${message} 点“恢复进度”接着玩。`;
  $("#connection").hidden = false;
}

async function load(initial = false) {
  if (busy) return;
  busy = true;
  app.setAttribute("aria-busy", "true");
  try {
    state = await request("/api/session");
    reportData = ["complete", "review-complete"].includes(state.phase)
      ? await request("/api/report")
      : null;
    selection = null;
    $("#connection").hidden = true;
    render();
    if (initial && state.hasStarted) {
      $("#pause-title").textContent = "接着上次的探险";
      $("#pause-dialog").showModal();
    }
  } catch (error) {
    connectionError(error);
  } finally {
    busy = false;
    app.setAttribute("aria-busy", "false");
  }
}

async function act(action, choice) {
  if (busy || !state || !$("#connection").hidden) return;
  stopAudio();
  busy = true;
  app.classList.add("busy");
  app.setAttribute("aria-busy", "true");
  const previous = state;
  const focusedAction = document.activeElement?.dataset.action;
  const focusedChoice = document.activeElement?.dataset.choice;
  try {
    state = await request("/api/action", {
      action,
      ...(choice != null ? { choice } : {}),
      revision: previous.revision,
      requestId: crypto.randomUUID(),
    });
    selection = null;
    if (["complete", "review-complete"].includes(state.phase))
      reportData = await request("/api/report");
    render();
    const moved =
      state.phase !== previous.phase || state.index !== previous.index;
    const audio = moved
      ? [
          ...(state.phase !== previous.phase
            ? [state.phase === "review-complete" ? "complete" : state.phase]
            : []),
          ...cue(),
        ]
      : state.feedbackAudio;
    playAudio(audio);
    if (moved) $("#lesson-title")?.focus();
    else if (state.canContinue && action === "choose")
      $('[data-action="next"]')?.focus();
    else if (focusedAction)
      $(
        `[data-action="${CSS.escape(focusedAction)}"]${focusedChoice ? `[data-choice="${CSS.escape(focusedChoice)}"]` : ""}`,
      )?.focus();
  } catch (error) {
    connectionError(error);
  } finally {
    busy = false;
    app.classList.remove("busy");
    app.setAttribute("aria-busy", "false");
  }
}

function chapter() {
  const phase = state.phase;
  return ["explore", "hunt"].includes(phase)
    ? 0
    : ["role-demo", "roles"].includes(phase)
      ? 1
      : ["check", "repair"].includes(phase)
        ? 2
        : 3;
}

function route() {
  return `<ol class="route" aria-label="探险路线">${["找一找", "换角色", "自己试", "再发现"].map((label, index) => `<li${index === chapter() ? ' aria-current="step"' : ""} class="${index < chapter() ? "done" : ""}"><span>${index < chapter() ? "✓" : index + 1}</span>${label}</li>`).join("")}</ol>`;
}

function stamps(lit = []) {
  return `<div class="word-strip" aria-label="六个字宝宝">${words.map((word) => `<span class="stamp${lit.includes(word) ? " lit" : ""}">${word}</span>`).join("")}</div>`;
}

function header() {
  const phase = state.phase;
  return `<div class="lesson-head"><div><p class="eyebrow">天地人 · ${phase === "review-preview" ? "提前体验，不计入次日复习" : ["review", "review-complete"].includes(phase) ? "回来认一认" : "字宝宝花园"}</p><div class="stage-title"><h1 id="lesson-title" tabindex="-1">${esc(titles[phase])}</h1>${!["explore", "role-demo"].includes(phase) ? `<span class="round">${state.index + 1} / ${state.total}</span>` : ""}</div></div>${route()}</div>`;
}

function garden(interactive = true, flipped = false) {
  const phase = state.phase;
  const nature =
    ["explore", "hunt"].includes(phase) ||
    (phase === "repair" && ["天", "地", "人"].includes(state.word));
  const zones = nature
    ? ["sky", "earth", "coral", "teal", "yellow"]
    : ["coral", "teal", "yellow"];
  const disabled = state.solved || phase === "role-demo";
  return `<div class="garden${flipped ? " flipped" : ""}" aria-label="原创花园图"><img src="/assets/garden" alt="花园中，红衣女孩和蓝衣男孩相对站着，黄衣男孩在旁边挥手；头顶是天空，脚下是小路。" draggable="false">${interactive ? zones.map((zone) => `<button class="zone ${zone}${state.highlight?.includes(zone) ? " highlight" : ""}${state.wrongChoices?.includes(zone) && !state.solved ? " retry" : ""}${state.hintLevel >= 2 && !state.solved && state.highlight?.includes(zone) ? " focus-hint" : ""}${phase === "explore" && state.highlight?.includes(zone) ? " labeled" : ""}" type="button" data-action="${phase === "explore" ? "explore" : "choose"}" data-choice="${zone}" aria-label="${names[zone]}"${disabled ? " disabled" : ""}><span class="zone-name">${names[zone]}</span>${state.speaker === zone ? `<span class="mic" aria-hidden="true">${icon("mic")}</span>` : ""}</button>`).join("") : ""}${state.speaker ? `<div class="speaker-line">${icon("mic")}${names[state.speaker]}在说话</div>` : ""}</div>`;
}

function audioError() {
  return '<div id="audio-status" class="audio-error" role="status"></div>';
}

function welcome() {
  return `<section class="welcome"><div class="welcome-copy"><p class="eyebrow">一年级 · 原创互动课</p><h1 id="lesson-title" tabindex="-1">天地人</h1><h2>把字宝宝，找进生活里。</h2><p>在花园里找一找，换个人说一说。最后，自己来闯关。</p><div class="welcome-actions">${button("start", "开始探险", { choice: "play", className: "primary", icon: "play" })}${button("start", "我会了，先挑战", { choice: "check" })}</div><div class="welcome-note">${icon("clock")}不计时，按你的速度来</div>${button("welcome-audio", "听听怎么玩", { className: "quiet welcome-listen", icon: "sound" })}</div>${garden(false)}</section><div class="welcome-foot"><span>${icon("leaf")}动手找字</span><span>${icon("mic")}换角色说话</span><span>${icon("book")}明天再认一认</span></div>${audioError()}`;
}

function game() {
  const phase = state.phase;
  const exploredWords = state.explored.map(
    (key) => ({ sky: "天", earth: "地", person: "人" })[key],
  );
  const collected =
    phase === "explore"
      ? exploredWords
      : phase === "hunt"
        ? words.slice(0, state.index + (state.solved ? 1 : 0))
        : phase === "roles"
          ? words.slice(
              0,
              3 + Math.floor((state.index + (state.solved ? 1 : 0)) / 2),
            )
          : words.slice(0, 3);
  const demo = phase === "role-demo";
  const message =
    state.feedback ||
    (phase === "explore"
      ? "点天空、地面和小朋友，听听它们的名字。"
      : demo
        ? "选谁来说话，再点一个字。"
        : `听一听，再在图里找到“${state.word}”。`);
  const canContinue = state.canContinue;
  return `${header()}<div class="collection-rail"><span>我的字宝宝</span>${stamps(collected)}</div><div class="play-workspace"><div class="picture-stage">${garden(true, phase === "repair")}${demo ? `<div class="demo-controls"><div class="segmented" role="group" aria-label="选谁来说话">${["teal", "coral"].map((person) => button("demo", names[person] + "说", { choice: person, pressed: state.demoSpeaker === person, icon: "mic" })).join("")}</div><div class="segmented words" role="group" aria-label="看看称呼指向谁">${["me", "you", "he"].map((role) => button("demo", { me: "我", you: "你", he: "他" }[role], { choice: role, pressed: state.demoRole === role })).join("")}</div></div>` : ""}</div><div class="play-dock"><div class="listen-wrap">${button("listen", "听一听", { icon: "sound" })}${!["explore", "role-demo"].includes(phase) ? button("hint", state.hintLevel ? "再给点提示" : "一点提示", { icon: "hint", disabled: state.solved || state.hintLevel >= 2 }) : ""}</div><div class="target">${state.word ? `${["hunt", "repair"].includes(phase) && !state.solved ? `<button type="button" class="word-token" data-action="token" aria-label="听字音，也可以把${esc(state.word)}字牌拖进图里">${esc(state.word)}</button>` : `<strong>${esc(state.word)}</strong>`}<small>${demo ? "称呼跟着说话人变" : phase === "explore" ? "字宝宝找到了" : state.solved ? "找到了" : ["hunt", "repair"].includes(phase) ? "拖进图里，或直接点图" : "点图里找一找"}</small>` : stamps(collected)}</div>${button("next", demo ? "我来试试" : canContinue ? (state.index + 1 === state.total ? "去下一站" : "下一步") : phase === "explore" ? `还差 ${3 - state.explored.length} 个发现` : "找到后，继续", { className: "primary advance", icon: "next", disabled: !canContinue })}</div></div><div class="feedback${state.solved ? " success" : state.correct === false ? " retry-text" : ""}" aria-live="polite">${icon(state.solved ? "check" : state.hintLevel ? "hint" : "sound")}<span>${esc(message)}</span></div>${audioError()}<div class="quiz-foot"><span>${demo ? "换说话人时，我和你也会换。" : state.hintLevel ? "用了提示也没关系，找到后再试一次。" : "没有倒计时，想好了再点。"}</span>${!["explore", "role-demo"].includes(phase) ? button("adult", state.adultHelp ? "已记下帮助" : "大人帮了一下", { className: "quiet", disabled: state.adultHelp || state.solved }) : ""}</div>`;
}

function quiz() {
  const question = state.question;
  const story = ["transfer", "review", "review-preview"].includes(state.phase);
  return `${header()}<div class="quiz-layout">${story ? `<div class="story-panel"><div class="story-mark">${icon("book")}听一个生活小故事</div><p>${esc(question.prompt)}</p></div>` : `<div class="quiz-picture"><img src="/assets/garden" alt="红衣女孩、蓝衣男孩和黄衣男孩在花园里"></div>`}<section class="quiz-side" aria-label="选一个字">${!story ? `<h2 class="question">${esc(question.prompt)}</h2>` : ""}<div class="quiz-audio">${button("listen", "听题目", { icon: "sound" })}<span class="hint-label">${state.adultHelp ? "这题有大人帮忙" : state.hintLevel ? "这题用过提示" : "读题不会算作提示"}</span></div><div class="options" role="group" aria-label="可选的字">${question.options.map((option) => `<button type="button" data-action="select" data-choice="${esc(option.value)}" aria-pressed="${(state.answered ? state.selected : selection) === option.value}" class="option${state.answered && option.value === state.answer ? " correct" : state.answered && option.value === state.selected && !state.correct ? " wrong" : ""}"${state.answered ? " disabled" : ""}>${esc(option.label)}${state.answered && option.value === state.answer ? '<span class="option-mark" aria-label="正确答案">✓</span>' : state.answered && option.value === state.selected && !state.correct ? '<span class="option-mark" aria-label="这次选择">↻</span>' : ""}</button>`).join("")}</div><div class="quiz-actions"><div class="quiz-meta">${button("hint", "一点提示", { icon: "hint", disabled: state.answered || state.hintLevel >= 2 })}</div>${state.answered ? button("next", state.index === 5 ? "去下一站" : "下一题", { className: "primary", icon: "next" }) : button("submit", "选好了", { className: "primary", icon: "check", disabled: !selection })}</div><p class="quiz-feedback" aria-live="polite">${esc(state.feedback || "")}</p>${audioError()}</section></div><div class="quiz-foot"><span>${state.phase === "review-preview" ? "这次只体验玩法，不记入次日复习。" : "选错也没关系，我们会一起练一练。"}</span>${button("adult", state.adultHelp ? "已记下帮助" : "大人帮了一下", { className: "quiet", disabled: state.answered || state.adultHelp })}</div>`;
}

function dateLabel(timestamp) {
  return timestamp
    ? new Date(timestamp * 1000).toLocaleString("zh-CN", {
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    : "";
}

function finish() {
  const result = reportData;
  if (!result) return "<p>正在整理这次的发现…</p>";
  const reviewed = state.phase === "review-complete";
  const observation = reviewed ? result.review : result.transfer;
  return `<section class="finish"><div class="finish-words">${stamps(words)}</div><p class="eyebrow">${reviewed ? "今天的复习完成了" : "字宝宝花园 · 探险完成"}</p><h1 id="lesson-title" tabindex="-1">${observation.independent === 6 ? "换个故事，也找到了！" : "今天，又多了一点发现。"}</h1><p>${observation.independent === 6 ? "六个字，在新的故事里认出来了。休息一下，下次再来。" : "有些字已经认识，有些还要再看看。今天先休息，下次接着来。"}</p><div class="evidence"><div><b>${result.check.independent}<small> / 6</small></b><p>第一轮 · 无提示首次答对</p></div><div><b>${observation.independent}<small> / 6</small></b><p>${reviewed ? "隔天复习" : "新的故事"} · 无提示答对</p></div></div><p class="review-date">${reviewed ? "本次隔天复习已记录。" : result.reviewAvailable ? "复习时间到了，可以再认一认。" : `${dateLabel(result.reviewDueAt)} 后，再回来认一认。`}</p><div class="finish-actions">${result.reviewAvailable ? button("review", "开始今日复习", { choice: "due", className: "primary", icon: "play" }) : button("rest", "歇一会儿", { className: "primary", icon: "leaf" })}${button("replay", "再玩一次")}${button("review", "试试复习玩法", { choice: "preview" })}${button("report", "给家长看看")}</div>${audioError()}</section>`;
}

function render() {
  if (!state) return;
  app.innerHTML =
    state.phase === "welcome"
      ? welcome()
      : ["complete", "review-complete"].includes(state.phase)
        ? finish()
        : state.question
          ? quiz()
          : game();
  updateAudioError();
}

async function parentReport() {
  stopAudio();
  const target = $("#parent-content");
  target.innerHTML =
    '<h2 id="parent-title">这次学得怎么样</h2><p>正在整理学习过程…</p>';
  $("#parent-dialog").showModal();
  try {
    const data = await request("/api/report");
    const outcome = (result) =>
      !result
        ? "还没做"
        : result.independent
          ? "独立答对"
          : result.correct
            ? "帮助后答对"
            : "需要再认";
    target.innerHTML = `<h2 id="parent-title">${data.interventionSuggested ? "可以陪孩子看一小会儿" : data.completed ? "日常陪练，先交给课件" : "正在积累这次的发现"}</h2><p class="parent-intro">天地人 · 本机样板体验记录</p><div class="report-metrics"><span>游戏重试 ${data.practiceRetries} 次</span><span>提示 ${data.hintedRounds} 轮</span><span>成人帮助 ${data.adultHelpRounds} 轮</span></div><table class="report-table"><thead><tr><th>字</th><th>第一轮</th><th>新情境</th><th>隔天复习</th></tr></thead><tbody>${data.objectives.map((item) => `<tr><td>${esc(item.word)}</td><td>${outcome(item.check)}</td><td>${outcome(item.transfer)}</td><td>${outcome(item.review)}</td></tr>`).join("")}</tbody></table><div class="report-next"><strong>接下来做什么</strong><p>${esc(data.nextStep)}</p></div>${data.repairWords.length ? `<p class="report-note">本轮已安排补练：${data.repairWords.map(esc).join("、")}。补练和反复尝试不会覆盖第一次结果。</p>` : ""}<p class="report-note">这些是本次点选表现，尚未评价${data.notAssessed.map(esc).join("、")}。成人帮助由体验者主动标记，系统不能自动判断身边是否有人辅导。</p><p class="report-note">样板记录与正式孩子记录独立。提前体验复习玩法不算隔天复习；没有据此估算已节省的家长时间。</p>`;
  } catch (error) {
    target.innerHTML = `<h2 id="parent-title">暂时没取到记录</h2><p>${esc(error.message)} 请关闭后重试。</p>`;
  }
}

app.addEventListener("click", (event) => {
  const control = event.target.closest("button[data-action]");
  if (!control || control.disabled || busy) return;
  const { action, choice } = control.dataset;
  if (action === "select") {
    selection = choice;
    render();
    $(`[data-action="select"][data-choice="${choice}"]`)?.focus();
  } else if (action === "submit") {
    if (selection) void act("choose", selection);
  } else if (action === "listen") {
    const audio = cue();
    playAudio(
      audio.length
        ? audio
        : state.feedbackAudio.length
          ? state.feedbackAudio
          : [state.phase],
    );
  } else if (action === "token") playAudio(cue());
  else if (action === "welcome-audio") playAudio(["welcome"]);
  else if (action === "audio-retry") playAudio(lastAudio);
  else if (action === "report") void parentReport();
  else if (action === "rest") showPause();
  else void act(action, choice);
});

function showPause() {
  stopAudio();
  $("#pause-title").textContent = "歇一小会儿";
  $("#pause-dialog").showModal();
}

// One submission path for mouse, touch, and keyboard. Dragging is optional;
// the large picture buttons remain fully operable without precision gestures.
let drag = null;
app.addEventListener("pointerdown", (event) => {
  const token = event.target.closest(".word-token");
  if (!token || busy || event.button !== 0) return;
  drag = {
    id: event.pointerId,
    token,
    startX: event.clientX,
    startY: event.clientY,
    ghost: null,
  };
  token.setPointerCapture(event.pointerId);
});
app.addEventListener("pointermove", (event) => {
  if (!drag || drag.id !== event.pointerId) return;
  if (
    !drag.ghost &&
    Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) > 8
  ) {
    const ghost = document.createElement("span");
    ghost.className = "drag-word";
    ghost.textContent = state.word;
    ghost.setAttribute("aria-hidden", "true");
    document.body.append(ghost);
    drag.ghost = ghost;
  }
  if (drag.ghost) {
    event.preventDefault();
    drag.ghost.style.transform = `translate(${event.clientX - 34}px, ${event.clientY - 34}px)`;
  }
});
function releaseDrag(event) {
  if (!drag || drag.id !== event.pointerId) return;
  const active = drag;
  drag = null;
  active.ghost?.remove();
  if (active.token.hasPointerCapture(event.pointerId))
    active.token.releasePointerCapture(event.pointerId);
  if (event.type === "pointercancel" || !active.ghost) return;
  const zone = document
    .elementFromPoint(event.clientX, event.clientY)
    ?.closest("button.zone");
  if (zone && !zone.disabled && zone.dataset.action === "choose")
    void act("choose", zone.dataset.choice);
}
app.addEventListener("pointerup", releaseDrag);
app.addEventListener("pointercancel", releaseDrag);

$("#pause").addEventListener("click", showPause);
$("#resume").addEventListener("click", () => {
  $("#pause-dialog").close();
  if (!state) return;
  playAudio(
    state.feedbackAudio.length
      ? state.feedbackAudio
      : [
          ...[state.phase === "review-complete" ? "complete" : state.phase],
          ...cue(),
        ],
  );
});
$("#parent").addEventListener("click", () => void parentReport());
$("#close-parent").addEventListener("click", () => $("#parent-dialog").close());
$("#recover").addEventListener("click", () => void load());
$("#sound").innerHTML = icon("sound");
$("#sound").addEventListener("click", () => {
  muted = !muted;
  $("#sound").innerHTML = icon(muted ? "mute" : "sound");
  $("#sound").setAttribute("aria-pressed", String(muted));
  $("#sound").setAttribute("aria-label", muted ? "打开声音" : "关闭声音");
  if (muted) stopAudio();
  else if (lastAudio.length) playAudio(lastAudio);
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) stopAudio();
});
window.addEventListener("pagehide", stopAudio);
void load(true);
