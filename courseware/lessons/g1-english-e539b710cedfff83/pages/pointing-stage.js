(() => {
  "use strict";

  const items = {
    window: { image: "__IMG:window__", label: "窗户" },
    door: { image: "__IMG:door__", label: "门" },
    desk: { image: "__IMG:desk__", label: "课桌" },
    chair: { image: "__IMG:chair__", label: "椅子" },
    may: { image: "__IMG:may__", label: "长耳朵的May" },
    ben: { image: "__IMG:ben__", label: "圆耳朵的Ben" },
    jo: { image: "__IMG:jo__", label: "穿背心的Jo" },
    stand: { image: "__IMG:stand__", label: "站起来" },
    sit: { image: "__IMG:sit__", label: "坐下来" },
    ceiling: { image: "__IMG:ceiling__", label: "天花板" },
    floor: { image: "__IMG:floor__", label: "地板" },
  };
  const clips = {
    window: "/api/classroom-media/__STAGE__/media/tts-listen-point-4-a85ba55076bdc615ad063e381b0384ac24c9982295647063b84389ae204c3563.wav",
    door: "/api/classroom-media/__STAGE__/media/tts-listen-point-8-4e37fe4065d5cbfaaf53b53fc12acf186eca447b09c7ba6a62d3fa9c67a895be.wav",
    desk: "/api/classroom-media/__STAGE__/media/tts-room-relay-9-39157bb2030c34c4f318ed59ba2daa2bc24a1722d1e4392fe77da63eedbdfc11.wav",
    chair: "/api/classroom-media/__STAGE__/media/tts-room-relay-12-aeef262dad185001dccee6825da52014a3bae3871b76d8460f1f165414c75002.wav",
    may: "/api/classroom-media/__STAGE__/media/tts-name-voices-5-2f8344f44b0b6472f496db42d444d280c97f7cfebd1cc76576f385234504dc20.wav",
    ben: "/api/classroom-media/__STAGE__/media/tts-name-voices-8-021899d4f357a49b81697cc65e5b12a76d538df4514e4acee3771621eee500d0.wav",
    jo: "/api/classroom-media/__STAGE__/media/tts-name-voices-11-32e811ce94e38b589601af8c0f80d350f153ac944a35cec83273a2b8425a2b82.wav",
    stand: "/api/classroom-media/__STAGE__/media/tts-room-beat-5-f7bb0049cfc6f1a72e8aa3e25c8c0c15444605cfe8b693fdb1c51e1470775b42.wav",
    sit: "/api/classroom-media/__STAGE__/media/tts-room-beat-8-9f5607e8eecdcfa13209189938f8b5bed520b362de8157c4eae21b3ac25b3cd1.wav",
    ceiling: "/api/classroom-media/__STAGE__/media/tts-room-beat-11-6bf462fe0836579dec28292518cb6fa22b691942a5c9fe37e39e8acef8f4b24d.wav",
    floor: "/api/classroom-media/__STAGE__/media/tts-room-beat-15-62bcbab80f58b6e6df9882af3dc68609282c926b2f0e11b51e5b424fc2e3d85a.wav",
    again: "/api/classroom-media/__STAGE__/media/tts-listen-point-14-c3b780c6fe01055b9b47ea2361ea417d6cdea704eb5ebf35b1315654d6619c07.wav",
    retry: "/api/classroom-media/__STAGE__/media/tts-listen-point-15-18fe2d909e1220fdbb2c0a52acc93fa9bb57172fd06a0bba182f08dbdb43c1a7.wav",
    "hello-may": "/api/classroom-media/__STAGE__/media/tts-stage-friends-5-5cfb5648dc12c0066add815b4090cb83270873428a2150a2e8bda500e1f9ccc4.wav",
    "hello-ben": "/api/classroom-media/__STAGE__/media/tts-stage-friends-8-db8ca4860eaacaccb0609d5ede0769805690c50d8a61401a28db9744122d5206.wav",
    "hello-jo": "/api/classroom-media/__STAGE__/media/tts-stage-friends-11-30fbc53e964df3c78f3211771c753076d1a8d66756a6ffc70ea04d82c595bc68.wav",
  };
  const room = ["window", "door", "desk", "chair"];
  const faces = ["may", "ben", "jo"];
  const poseChoices = ["stand", "sit", "ceiling", "floor"];
  const surfaceChoices = ["ceiling", "floor", "window", "door"];

  const activities = {
    "先听，再指": {
      heading: "听清指令，手再动",
      note: "听一听，然后指一指",
      mode: "point",
      choices: room.slice(0, 2),
      rounds: ["window", "window", "door"],
    },
    "教室指向接力": {
      heading: "听最后的词",
      note: "找一找窗、门、课桌和椅子",
      mode: "point",
      choices: room,
      rounds: ["chair", "window", "desk", "door"],
    },
    "听名字找朋友": {
      heading: "谁听到了自己的名字？",
      note: "三个朋友交换了位置",
      mode: "face",
      choices: faces,
      rounds: ["ben", "may", "jo"],
    },
    "跟着节奏做动作": {
      heading: "一拍，做一个动作",
      note: "听指令，选择动作或指向的地方",
      mode: "beat",
      choices: ["stand", "sit", "ceiling", "floor", "window", "door"],
      rounds: ["stand", "ceiling", "sit", "door", "floor", "window"],
    },
    "指错了，换一个": {
      heading: "手指的地方对吗？",
      note: "再听一次，把手转到对的地方",
      mode: "fix",
      choices: room,
      rounds: ["desk", "door", "chair"],
      firstPoint: ["chair", "window", "desk"],
    },
    "剧场里指给大家看": {
      heading: "听名字，请朋友登场",
      note: "朋友站到台前，一起来问好",
      mode: "role",
      choices: faces,
      rounds: ["jo", "ben", "may"],
    },
  };

  const activity = activities[document.title];
  const options = K.$("#object-options");
  const listener = K.$("#listen-again");
  const actor = K.$("#actor-picture");
  const badge = K.$("#actor-badge");
  const pointing = K.$("#pointing-path");
  const trace = K.$("#point-trace");
  const speech = new Audio();
  speech.preload = "none";
  let audioRound = 0;
  let narrationAllowed = window.parent === window;
  let finishRoleSpeech = null;
  let round = 0;
  let revision = 0;
  let misses = 0;
  let locked = false;
  let teaching = false;

  K.$("#activity-heading").textContent = activity.heading;
  K.$("#activity-note").textContent = activity.note;

  function stopSpeech() {
    audioRound += 1;
    speech.pause();
    speech.onended = null;
    speech.onerror = null;
    speech.onplaying = null;
    listener.dataset.playing = "false";
    finishRoleSpeech = null;
  }

  function speak(key, { onDone, task = false } = {}) {
    stopSpeech();
    if (!narrationAllowed || document.hidden) {
      if (onDone) onDone();
      if (task) K.say("等老师讲完，再点喇叭。");
      return;
    }
    const attempt = audioRound;
    const finish = () => {
      if (attempt !== audioRound) return;
      stopSpeech();
      if (onDone) onDone();
    };
    speech.src = clips[key];
    speech.onended = finish;
    speech.onerror = finish;
    if (onDone) finishRoleSpeech = finish;
    listener.dataset.playing = "true";
    if (onDone) {
      const startupDeadline = setTimeout(finish, 10000);
      speech.onplaying = () => clearTimeout(startupDeadline);
    }
    speech.play().catch(finish);
    if (task) K.say("听完指令，再动手。");
  }

  function setActor(key, stateText) {
    actor.hidden = false;
    actor.src = items[key].image;
    actor.alt = items[key].label;
    K.$("#actor-panel .image-fallback")?.remove();
    badge.textContent = stateText;
  }

  function showFallback(image) {
    if (image.hidden) return;
    image.hidden = true;
    const fallback = document.createElement("span");
    fallback.className = "image-fallback";
    fallback.textContent = image.alt;
    image.after(fallback);
    image.parentElement.addEventListener("click", function retry(event) {
      if (!image.hidden) return;
      event.stopImmediatePropagation();
      const url = image.src;
      image.removeAttribute("src");
      image.hidden = false;
      fallback.remove();
      image.src = url;
      image.parentElement.removeEventListener("click", retry, true);
    }, true);
  }

  actor.addEventListener("error", () => showFallback(actor));

  function markChoice(key, outcome) {
    for (const choice of options.children) {
      delete choice.dataset.outcome;
    }
    trace.removeAttribute("d");
    if (!key) return;
    const choice = K.$(`[data-item="${key}"]`, options);
    if (!choice) return;
    choice.dataset.outcome = outcome;
    if (activity.mode === "face" || activity.mode === "role") return;
    const from = K.pos(K.$("#actor-panel"));
    const to = K.pos(choice);
    const frame = K.pos(K.$("#activity-board"));
    const x = from.x + from.w - frame.x - 13;
    const y = from.y + from.h * .55 - frame.y;
    const endX = to.x - frame.x + 12;
    const endY = to.y + to.h / 2 - frame.y;
    pointing.dataset.outcome = outcome;
    trace.setAttribute("d", `M${x} ${y} Q${x + (endX - x) * .46} ${endY} ${endX} ${endY}`);
  }

  function setEnabled(enabled) {
    listener.disabled = !enabled;
    for (const choice of options.children) choice.disabled = !enabled;
  }

  function rotation(keys, n) {
    const pivot = n % keys.length;
    return [...keys.slice(pivot), ...keys.slice(0, pivot)];
  }

  function showOptions(keys) {
    options.dataset.count = String(keys.length);
    options.replaceChildren();
    for (const key of keys) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "object-choice";
      button.dataset.item = key;
      button.setAttribute("aria-label", items[key].label);
      const picture = document.createElement("img");
      picture.alt = items[key].label;
      picture.addEventListener("error", () => showFallback(picture));
      picture.src = items[key].image;
      button.append(picture);
      button.addEventListener("click", () => choose(key, button));
      options.append(button);
    }
  }

  function choicesFor(target) {
    if (activity.mode !== "beat") return activity.choices;
    return poseChoices.includes(target) ? poseChoices : surfaceChoices;
  }

  function resetRound() {
    const target = activity.rounds[round];
    misses = 0;
    locked = false;
    stopSpeech();
    showOptions(rotation(choicesFor(target), round));
    setActor("jo", activity.mode === "fix" ? "先看看手指哪里" : "准备好了");
    markChoice(activity.firstPoint?.[round], "demo");
    K.levels(activity.rounds.length, round);
    K.say("点喇叭，听这一回合。");
    setEnabled(true);
  }

  function startGame() {
    revision += 1;
    teaching = false;
    round = 0;
    K.stars = 0;
    K.star(0);
    resetRound();
  }

  function nextRound() {
    round += 1;
    if (round < activity.rounds.length) {
      resetRound();
      return;
    }
    stopSpeech();
    K.levels(activity.rounds.length, round);
    K.finish({ title: "这一组完成了", sub: "你可以再听一轮。", again: startGame });
  }

  function choose(key, button) {
    if (locked || teaching) return;
    stopSpeech();
    const target = activity.rounds[round];
    if (key !== target) {
      misses += 1;
      markChoice(key, "retry");
      K.say(misses === 1 ? "听一听，再试一次。" : "留意最后听到的词。", "no");
      K.shake(button);
      speak(misses === 1 ? "again" : "retry");
      return;
    }
    locked = true;
    setEnabled(false);
    markChoice(key, "correct");
    if (activity.mode === "face" || activity.mode === "role") setActor(key, "站到台前");
    if (activity.mode === "beat") setActor(key, "这一拍跟上了");
    if (activity.mode === "fix") badge.textContent = "改指成功";
    K.star(1, button);
    K.say("听对了，指对了。", "ok");
    const current = revision;
    const advance = () => {
      if (revision === current) nextRound();
    };
    if (activity.mode === "role") {
      speak("hello-" + key, { onDone: advance });
    } else {
      K.sfx.ok();
      setTimeout(advance, 940);
    }
  }

  listener.addEventListener("click", () => {
    if (activity.mode !== "beat") {
      speak(activity.rounds[round], { task: true });
      return;
    }
    if (!narrationAllowed || document.hidden) {
      K.say("等老师讲完，再点喇叭。");
      return;
    }
    stopSpeech();
    const attempt = audioRound;
    K.sfx.tick(round % 4);
    setTimeout(() => {
      if (audioRound === attempt) speak(activity.rounds[round], { task: true });
    }, 220);
  });
  function suspendNarration() {
    if (finishRoleSpeech) finishRoleSpeech();
    else stopSpeech();
  }
  window.addEventListener("message", (event) => {
    if (event.source !== window.parent || event.data?.type !== "MIRA_NARRATION_VISIBILITY"
        || typeof event.data.visible !== "boolean") return;
    narrationAllowed = event.data.visible;
    if (!narrationAllowed) suspendNarration();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) suspendNarration();
  });
  window.addEventListener("pagehide", stopSpeech);
  K.onStart = startGame;
  K.onState = (state) => {
    if (state.ready) {
      startGame();
      return;
    }
    const key = state.demo;
    if (!key) return;
    revision += 1;
    teaching = true;
    stopSpeech();
    if (key === "rhythm" && activity.mode === "beat") {
      showOptions(["stand", "sit", "door"]);
      setActor("jo", "一拍一个动作");
      markChoice(null, "demo");
      K.say("从左到右，跟老师做三拍。");
      setEnabled(false);
      return;
    }
    const targets = key === "start" ? choicesFor(activity.rounds[0]) : choicesFor(key);
    showOptions(targets);
    setActor(
      key !== "start" && ["face", "role", "beat"].includes(activity.mode) ? key : "jo",
      "老师示范",
    );
    markChoice(key === "start" ? null : key, "demo");
    K.say("先听老师示范。");
    setEnabled(false);
  };

  K.hud({ title: document.title, levels: activity.rounds.length, icon: "" });
  K.owl();
  K.ready({ title: document.title, sub: "听一听，动一动", emoji: "▶" });
})();
