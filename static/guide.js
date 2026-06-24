/* ====================================================================
   新手引导（首次进入的可跳过浮层）+ 系统公告
   纯前端，无依赖；自带中英（跟随 i18n.js 的语言状态）。
   引导：聚光高亮某个元素，其余区域压暗一点；逐步「下一步/上一步/跳过」。
   公告：顶栏 📢 铃铛 + 弹窗列出公告；有未读时自动弹一次。
==================================================================== */
(function () {
  const $ = (s) => document.querySelector(s);
  const EN = () => window.I18N && window.I18N.get() === "en";
  const T = (zh, en) => (EN() ? en : zh);

  /* ============================ 新手引导 ============================ */
  const TOUR_KEY = "cp_onboarded_v1";   // 版本号后缀：将来引导更新可重新弹
  const STEPS = [
    { sel: null,
      zh: { t: "欢迎来到 ARENA 👋", b: "这是一个算法竞赛辅导智能体。半分钟带你认识主要功能——随时可以跳过。" },
      en: { t: "Welcome to ARENA 👋", b: "An AI tutor for competitive programming. A 30-second tour of the essentials — skip anytime." } },
    { sel: "#pb-toggle",
      zh: { t: "① 从这里选题", b: "打开题库挑一道题，或直接粘贴你自己的题目到左侧。" },
      en: { t: "① Pick a problem", b: "Open the problem set, or paste your own problem on the left." } },
    { sel: "#btn-analyze",
      zh: { t: "② 让智能体分析", b: "点这里，智能体团队会判断题型、难度、突破口，并给出多种解法策略。" },
      en: { t: "② Run agent analysis", b: "The agent team identifies the type, difficulty, key insight and candidate strategies." } },
    { sel: "#editor",
      zh: { t: "③ 在这里写代码", b: "支持自动补全、运行自定义输入。写好后就能提交评测。" },
      en: { t: "③ Write your code", b: "Autocomplete and custom-input runs included. Then submit for judging." } },
    { sel: "#btn-submit",
      zh: { t: "④ 提交评测", b: "双轨判题：有官方数据走真值判定，没有就用暴力解对拍抓最小反例。" },
      en: { t: "④ Submit", b: "Dual-track judging: ground-truth tests when available, else stress-testing to find a minimal counterexample." } },
    { sel: "#panel-tutor",
      zh: { t: "⑤ 卡住了找导师", b: "苏格拉底导师按层给提示，不直接给答案；也能让导师审阅你的代码。" },
      en: { t: "⑤ Ask the tutor", b: "The Socratic tutor gives layered hints instead of answers, and can review your code." } },
    { sel: ".tabs",
      zh: { t: "⑥ 更多功能", b: "算法图解（看动图）、社群（一起讨论、答疑得算力点）、学习仪表盘（画像与数据）都在这里。" },
      en: { t: "⑥ More features", b: "Visualizer (animations), Community (discuss & earn credits), and Dashboard (profile & data) are up here." } },
    { sel: "#lang-toggle",
      zh: { t: "⑦ 一键中英切换", b: "随时点这里在中文 / English 之间切换整个界面。" },
      en: { t: "⑦ Switch language", b: "Flip the whole interface between 中文 / English anytime." } },
    { sel: null,
      zh: { t: "准备好了 🚀", b: "去做你的第一道题吧！想再看公告，点右上角的 📢。" },
      en: { t: "You're all set 🚀", b: "Go solve your first problem! Tap 📢 at the top-right for announcements." } },
  ];
  let idx = 0;

  function buildOverlay() {
    if ($("#guide-overlay")) return;
    const ov = document.createElement("div");
    ov.id = "guide-overlay";
    ov.innerHTML =
      '<div id="guide-spot"></div>' +
      '<div id="guide-card" role="dialog" aria-modal="true">' +
      '  <div class="guide-step" id="guide-step"></div>' +
      '  <h3 id="guide-title"></h3>' +
      '  <p id="guide-body"></p>' +
      '  <div class="guide-actions">' +
      '    <button class="guide-skip" id="guide-skip"></button>' +
      '    <div class="guide-nav">' +
      '      <button class="guide-btn ghost" id="guide-prev"></button>' +
      '      <button class="guide-btn primary" id="guide-next"></button>' +
      '    </div>' +
      '  </div>' +
      '</div>';
    document.body.appendChild(ov);
    $("#guide-skip").onclick = endTour;
    $("#guide-prev").onclick = () => { if (idx > 0) { idx--; render(); } };
    $("#guide-next").onclick = () => { if (idx < STEPS.length - 1) { idx++; render(); } else endTour(); };
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", reposition);
  }
  function onKey(e) {
    if (!$("#guide-overlay")) return;
    if (e.key === "Escape") endTour();
    else if (e.key === "ArrowRight" || e.key === "Enter") $("#guide-next").click();
    else if (e.key === "ArrowLeft") $("#guide-prev").click();
  }
  function positionCard(card, r) {
    const cw = card.offsetWidth, ch = card.offsetHeight, M = 14, pad = 12;
    let top = r.bottom + M;
    if (top + ch > window.innerHeight - pad) top = Math.max(pad, r.top - ch - M);
    let left = r.left;
    if (left + cw > window.innerWidth - pad) left = window.innerWidth - cw - pad;
    left = Math.max(pad, left);
    card.style.top = top + "px"; card.style.left = left + "px"; card.style.transform = "none";
  }
  function reposition() {
    const step = STEPS[idx]; if (!step) return;
    const spot = $("#guide-spot"), card = $("#guide-card");
    const target = step.sel ? document.querySelector(step.sel) : null;
    if (target) {
      const r = target.getBoundingClientRect(), p = 8;
      spot.style.display = "block";
      spot.style.left = (r.left - p) + "px"; spot.style.top = (r.top - p) + "px";
      spot.style.width = (r.width + 2 * p) + "px"; spot.style.height = (r.height + 2 * p) + "px";
      $("#guide-overlay").classList.remove("full");
      positionCard(card, r);
    } else {
      spot.style.display = "none";
      $("#guide-overlay").classList.add("full");   // 无目标：整屏压暗，卡片居中
      card.style.top = "50%"; card.style.left = "50%"; card.style.transform = "translate(-50%,-50%)";
    }
  }
  function render() {
    const step = STEPS[idx], L = EN() ? step.en : step.zh;
    $("#guide-step").textContent = (idx + 1) + " / " + STEPS.length;
    $("#guide-title").textContent = L.t;
    $("#guide-body").textContent = L.b;
    $("#guide-skip").textContent = T("跳过引导", "Skip");
    $("#guide-prev").textContent = T("上一步", "Back");
    $("#guide-prev").style.visibility = idx === 0 ? "hidden" : "visible";
    $("#guide-next").textContent = idx === STEPS.length - 1 ? T("开始使用", "Get started") : T("下一步", "Next");
    const target = step.sel ? document.querySelector(step.sel) : null;
    if (target) target.scrollIntoView({ block: "center", inline: "nearest" });
    requestAnimationFrame(reposition);
  }
  function startTour() {
    idx = 0; buildOverlay(); render();
  }
  function endTour() {
    try { localStorage.setItem(TOUR_KEY, "1"); } catch (e) {}
    const ov = $("#guide-overlay");
    if (ov) { window.removeEventListener("keydown", onKey); window.removeEventListener("resize", reposition); ov.remove(); }
    maybeAutoAnnounce();   // 引导结束后，若有未读公告再弹一次
  }
  // 供「再看一遍引导」入口复用
  window.cpStartTour = startTour;

  /* ============================== 公告 ============================== */
  const SEEN_KEY = "cp_announce_seen";
  // 公告列表（新的放最前）。将来可改为后端下发；现按客户端清单维护。
  const ANNOUNCEMENTS = [
    { id: "beta-2026-06", date: "2026-06-24", tag: "公测", tagEn: "Beta",
      zh: { t: "🎉 系统开始公测啦！", b: "ARENA 算法竞赛辅导智能体正式开放公测。判题、智能体分析、导师审阅、算法图解对所有人免费，欢迎体验，并在「社群」留下你的反馈。" },
      en: { t: "🎉 Public beta is live!", b: "ARENA CP Tutor Agent is now in public beta. Judging, agent analysis, tutor review and the visualizer are free for everyone — try it out and leave feedback in the Community." } },
    { id: "i18n-incentive-2026-06", date: "2026-06-24", tag: "新功能", tagEn: "New",
      zh: { t: "🌐 中英切换 · 每日签到 · 学习画像 上线", b: "顶栏一键切换中文 / English；每日签到领算力点；社群答疑也能得算力点；学习仪表盘新增「用户画像」与「学习投入」分析。" },
      en: { t: "🌐 Language switch · daily check-in · learner profile", b: "Toggle 中文 / English in the top bar; check in daily for credits; earn credits by helping in the Community; the dashboard now shows your profile and engagement analytics." } },
    { id: "cert-2026-06", date: "2026-06-24", tag: "新功能", tagEn: "New",
      zh: { t: "🎓 结业证书上线", b: "累计攻克 3 道题，即可在「学习仪表盘」一键生成专属结业证书（带二维码），可保存、可分享。" },
      en: { t: "🎓 Certificate of completion", b: "Solve 3 problems to generate your personal certificate (with QR code) from the Dashboard — save it or share it." } },
  ];
  function seenSet() {
    try { return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || "[]")); }
    catch (e) { return new Set(); }
  }
  function unreadCount() {
    const s = seenSet();
    return ANNOUNCEMENTS.filter(a => !s.has(a.id)).length;
  }
  function markAllSeen() {
    try { localStorage.setItem(SEEN_KEY, JSON.stringify(ANNOUNCEMENTS.map(a => a.id))); } catch (e) {}
    refreshBell();
  }
  function refreshBell() {
    const dot = $("#announce-dot");
    if (dot) dot.style.display = unreadCount() > 0 ? "block" : "none";
    const btn = $("#announce-btn");
    if (btn) btn.title = T("系统公告", "Announcements");
  }
  function buildAnnounceModal() {
    if ($("#announce-modal")) return;
    const m = document.createElement("div");
    m.className = "modal-overlay hidden";
    m.id = "announce-modal";
    m.innerHTML =
      '<div class="modal modal-announce">' +
      '  <button class="modal-close" id="announce-close">×</button>' +
      '  <h3 class="announce-h" id="announce-h"></h3>' +
      '  <div class="announce-list" id="announce-list"></div>' +
      '  <button class="btn btn-primary btn-block" id="announce-ok"></button>' +
      '</div>';
    document.body.appendChild(m);
    $("#announce-close").onclick = closeAnnounce;
    $("#announce-ok").onclick = closeAnnounce;
    m.onclick = (e) => { if (e.target.id === "announce-modal") closeAnnounce(); };
  }
  function renderAnnounceList() {
    const s = seenSet();
    $("#announce-h").textContent = T("📢 系统公告", "📢 Announcements");
    $("#announce-ok").textContent = T("知道了", "Got it");
    $("#announce-list").innerHTML = ANNOUNCEMENTS.map(a => {
      const L = EN() ? a.en : a.zh, tag = EN() ? a.tagEn : a.tag;
      const isNew = !s.has(a.id);
      return '<div class="announce-item' + (isNew ? " unread" : "") + '">' +
        '<div class="announce-top"><span class="announce-tag">' + esc(tag) + "</span>" +
        '<span class="announce-date">' + esc(a.date) + "</span>" +
        (isNew ? '<span class="announce-new">' + T("未读", "New") + "</span>" : "") + "</div>" +
        '<div class="announce-title">' + esc(L.t) + "</div>" +
        '<div class="announce-body">' + esc(L.b) + "</div></div>";
    }).join("");
  }
  function esc(s) { return (window.esc || ((x) => String(x)))(s); }
  function openAnnounce() {
    buildAnnounceModal(); renderAnnounceList();
    $("#announce-modal").classList.remove("hidden");
  }
  function closeAnnounce() {
    const m = $("#announce-modal"); if (m) m.classList.add("hidden");
    markAllSeen();
  }
  function maybeAutoAnnounce() { if (unreadCount() > 0) openAnnounce(); }

  /* ===== 顶栏铃铛按钮：注入到语言切换右侧 ===== */
  function ensureBell() {
    if ($("#announce-btn")) return;
    const lang = $("#lang-toggle");
    const btn = document.createElement("button");
    btn.id = "announce-btn";
    btn.className = "announce-btn";
    btn.title = T("系统公告", "Announcements");
    btn.innerHTML = '📢<span id="announce-dot" class="announce-dot"></span>';
    btn.onclick = openAnnounce;
    if (lang && lang.parentNode) lang.parentNode.insertBefore(btn, lang.nextSibling);
    else { const h = document.querySelector(".topbar"); if (h) h.appendChild(btn); }
    refreshBell();
  }

  /* 语言切换时，若公告弹窗开着就重渲染文案 */
  window.addEventListener("langchange", () => {
    if ($("#announce-modal") && !$("#announce-modal").classList.contains("hidden")) renderAnnounceList();
    if ($("#guide-overlay")) render();
    refreshBell();
  });

  /* ============================== 启动 ============================== */
  function init() {
    ensureBell();
    let onboarded = false;
    try { onboarded = !!localStorage.getItem(TOUR_KEY); } catch (e) {}
    if (!onboarded) setTimeout(startTour, 900);   // 首次进入：稍候再弹，等布局稳定
    else maybeAutoAnnounce();                       // 老用户：有未读公告就弹一次
  }
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", () => setTimeout(init, 300));
  else setTimeout(init, 300);
})();
