/* ====================================================================
   社群讨论区 — 前端逻辑
   帖子列表 / 标签筛选 / 发帖 / 详情回帖 / 点赞
   复用 app.js 的全局：esc / toast / currentUser / openAuth
==================================================================== */
(function () {
  const $c = (s) => document.querySelector(s);
  const TAG_CLS = { "求助": "ask", "题解": "solu", "讨论": "disc", "反馈": "fb" };
  const TAGS = ["求助", "题解", "讨论", "反馈"];
  // 轻量中英：内容数据（帖子正文）不译，只译界面文案；与 i18n.js 的语言状态联动
  const EN = () => window.I18N && window.I18N.get() === "en";
  const T = (zh, en) => (EN() ? en : zh);
  const TAG_EN = { "求助": "Help", "题解": "Solution", "讨论": "Discuss", "反馈": "Feedback" };
  const tagText = (t) => (EN() ? (TAG_EN[t] || t) : t);
  // 不同板块给不同的标题 / 正文占位提示
  const PH = {
    "求助": { t: "描述你卡在哪，如「二分边界总差一，lo/hi 到底怎么定？」",
              b: "贴上题目、你的思路、卡住的点或报错信息，方便大家帮你定位…" },
    "题解": { t: "你的解法亮点，如「单调栈 O(n) 解接雨水」",
              b: "讲讲核心思路、时空复杂度、关键代码或你踩过的坑…" },
    "讨论": { t: "想讨论的话题，如「DP 的状态到底怎么定义才不漏」",
              b: "抛出你的观点或疑问，欢迎大家一起来聊…" },
    "反馈": { t: "你的建议或遇到的问题，如「希望算法图解加并查集」",
              b: "具体描述你想要的功能，或使用中遇到的问题…" },
  };
  const PH_EN = {
    "求助": { t: "Where are you stuck? e.g. “binary-search boundary is always off by one”",
              b: "Paste the problem, your idea, where you're stuck, or the error message…" },
    "题解": { t: "Your solution highlight, e.g. “monotonic stack O(n) for trapping rain water”",
              b: "Explain the core idea, time/space complexity, key code, or pitfalls…" },
    "讨论": { t: "A topic to discuss, e.g. “how to define DP states without missing cases”",
              b: "Share your view or question — let's talk it through…" },
    "反馈": { t: "Your suggestion or issue, e.g. “please add union-find to the visualizer”",
              b: "Describe the feature you want, or the issue you ran into…" },
  };
  let cmTag = "";
  let cmKeyword = "";
  let cmSort = "hot";   // 默认按点赞热度排序，可切「最新」
  let cmInited = false;
  let cmProblems = null;   // 题库 + 我的题目缓存，供发帖时关联
  let cmProbMap = {};      // display -> {id,title}
  async function ensureProblems() {
    if (cmProblems) return cmProblems;
    try {
      const [bank, mine] = await Promise.all([
        fetch("/api/problems").then((r) => r.json()).catch(() => []),
        fetch("/api/my-problems").then((r) => r.json()).catch(() => []),
      ]);
      cmProblems = [].concat(bank || [], mine || []).map((p) => {
        const id = String(p.id), title = p.title || "未命名", display = id + " · " + title;
        cmProbMap[display] = { id, title };
        return { id, title, display };
      });
    } catch (e) { cmProblems = []; }
    return cmProblems;
  }

  function fmtTime(ts) {
    const diff = Date.now() / 1000 - ts;
    if (diff < 60) return T("刚刚", "just now");
    if (diff < 3600) return Math.floor(diff / 60) + T(" 分钟前", "m ago");
    if (diff < 86400) return Math.floor(diff / 3600) + T(" 小时前", "h ago");
    if (diff < 86400 * 7) return Math.floor(diff / 86400) + T(" 天前", "d ago");
    const d = new Date(ts * 1000);
    return `${d.getMonth() + 1}-${String(d.getDate()).padStart(2, "0")}`;
  }
  function tagBadge(t) { return `<span class="cm-tag-badge ${TAG_CLS[t] || "disc"}">${E(tagText(t))}</span>`; }
  function E(s) { return (window.esc || ((x) => x))(s); }
  function loggedIn() { return !!(window.currentUser); }
  function needLogin(zh, en) {
    if (window.openAuth) window.openAuth("login", T("登录后即可" + zh + "，并参与社群讨论", "Sign in to " + en + " and join the community"));
    else (window.toast || console.log)(T("请先登录再" + zh, "Please sign in first"));
  }

  async function loadList() {
    const list = $c("#cm-list");
    list.innerHTML = '<div class="cm-empty">' + T("加载中…", "Loading…") + '</div>';
    try {
      const url = "/api/community/posts?tag=" + encodeURIComponent(cmTag) +
                  "&q=" + encodeURIComponent(cmKeyword) +
                  "&sort=" + encodeURIComponent(cmSort);
      const r = await fetch(url).then((r) => r.json());
      renderList(r.posts || []);
    } catch (e) { list.innerHTML = '<div class="cm-empty">' + T("加载失败，请稍后再试", "Failed to load, try again later") + '</div>'; }
  }

  function renderList(posts) {
    const list = $c("#cm-list");
    if (!posts.length) {
      list.innerHTML = cmKeyword
        ? '<div class="cm-empty">' + T('没有找到与「' + E(cmKeyword) + '」匹配的帖子，换个关键词试试～', 'No posts match “' + E(cmKeyword) + '”, try another keyword') + '</div>'
        : '<div class="cm-empty">' + T("这个板块还没有帖子，来发第一帖吧～", "No posts in this board yet — be the first!") + '</div>';
      return;
    }
    list.innerHTML = posts.map((p) => `
      <button type="button" class="cm-card" data-id="${p.id}">
        <div class="cm-card-top">${tagBadge(p.tag)}<span class="cm-card-title">${E(p.title)}</span></div>
        ${p.problem_title ? `<div class="cm-card-prob">📎 ${E(p.problem_title)}</div>` : ""}
        <div class="cm-card-snip">${E(p.snippet)}</div>
        <div class="cm-card-foot">
          <span class="cm-card-author">👤 ${E(p.username)}</span>
          <span class="cm-card-time">${fmtTime(p.created_at)}</span>
          <span class="cm-card-stat">👍 ${p.likes}</span>
          <span class="cm-card-stat">💬 ${p.reply_count}</span>
        </div>
      </button>`).join("");
    list.querySelectorAll(".cm-card").forEach((b) => (b.onclick = () => openDetail(Number(b.dataset.id))));
  }

  /* ---------------- 抽屉 ---------------- */
  function openDrawer() { $c("#cm-overlay").classList.add("open"); $c("#cm-drawer").classList.add("open"); }
  function closeDrawer() { $c("#cm-overlay").classList.remove("open"); $c("#cm-drawer").classList.remove("open"); }

  /* ---------------- 发帖 ---------------- */
  function openComposer(presetTag) {
    if (!loggedIn()) return needLogin("发帖", "post");
    const initTag = TAGS.indexOf(presetTag) >= 0 ? presetTag : "讨论";
    $c("#cm-drawer-body").innerHTML = `
      <div class="cm-compose">
        <h3 class="cm-drawer-title">${T("✎ 发表新帖", "✎ New post")}</h3>
        <div class="cm-field-label">${T("选择板块", "Board")}</div>
        <div class="cm-compose-tags" id="cm-c-tags">
          ${TAGS.map((t) => `<button type="button" class="cm-ctag ${TAG_CLS[t]}${t === initTag ? " active" : ""}" data-tag="${t}">${tagText(t)}</button>`).join("")}
        </div>
        <div class="cm-field-label">${T("标题", "Title")}</div>
        <input id="cm-c-title" class="cm-input" maxlength="80" placeholder="${T("一句话说清问题，如「快排为什么会退化到 O(n²)」", "Sum it up in one line, e.g. “Why does quicksort degrade to O(n²)?”")}">
        <div class="cm-field-label">${T("正文", "Body")}</div>
        <textarea id="cm-c-body" class="cm-textarea" placeholder="${T("详细描述你的问题 / 思路 / 反馈…", "Describe your question / idea / feedback in detail…")}"></textarea>
        <div class="cm-field-label">${T("关联题目", "Linked problem")} <span class="cm-field-opt">${T("可选 · 便于在题目页聚合题解", "optional · aggregates solutions on the problem page")}</span></div>
        <input id="cm-c-prob" class="cm-input" list="cm-prob-list" placeholder="${T("输入题号或题名检索，如 P1001 两数之和", "Search by id or name, e.g. P1001 Two Sum")}" autocomplete="off">
        <datalist id="cm-prob-list"></datalist>
        <div class="cm-compose-foot">
          <span class="cm-guard-note">${T("⚖️ 发布前会经敏感词 + AI 审核护栏", "⚖️ Posts pass a keyword + AI moderation guard")}</span>
          <button id="cm-c-submit" class="btn btn-primary">${T("发布", "Publish")}</button>
        </div>
        <div id="cm-c-err" class="cm-err"></div>
      </div>`;
    let tag = initTag;
    const applyPH = (tg) => {
      const src = EN() ? PH_EN : PH;
      const ph = src[tg] || src["讨论"];
      $c("#cm-c-title").placeholder = ph.t;
      $c("#cm-c-body").placeholder = ph.b;
    };
    $c("#cm-c-tags").querySelectorAll(".cm-ctag").forEach((b) => (b.onclick = () => {
      tag = b.dataset.tag;
      $c("#cm-c-tags").querySelectorAll(".cm-ctag").forEach((x) => x.classList.toggle("active", x === b));
      applyPH(tag);   // 切板块 → 占位提示随之变化
    }));
    applyPH(tag);     // 初始占位提示与默认板块（讨论）一致
    ensureProblems().then((list) => {
      const dl = $c("#cm-prob-list");
      if (dl) dl.innerHTML = list.map((p) => `<option value="${E(p.display)}"></option>`).join("");
      const cur = window.cpCurrentProblem && window.cpCurrentProblem();   // 默认带上当前在做的题
      if (cur && cur.id) {
        const found = list.find((p) => p.id === String(cur.id));
        if (found && $c("#cm-c-prob")) $c("#cm-c-prob").value = found.display;
      }
    });
    $c("#cm-c-submit").onclick = () => submitPost(() => tag);
    openDrawer();
    setTimeout(() => $c("#cm-c-title").focus(), 80);
  }

  async function submitPost(getTag) {
    const title = $c("#cm-c-title").value.trim();
    const body = $c("#cm-c-body").value.trim();
    const err = $c("#cm-c-err");
    const btn = $c("#cm-c-submit");
    if (!title) { err.textContent = T("标题不能为空", "Title can't be empty"); return; }
    if (body.length < 2) { err.textContent = T("正文太短了", "Body is too short"); return; }
    err.textContent = "";
    const probEl = $c("#cm-c-prob");
    let problem_id = "", problem_title = "";
    if (probEl && probEl.value.trim()) {
      let hit = cmProbMap[probEl.value.trim()];
      if (!hit) {   // 容错：用户只敲了题号
        const token = probEl.value.trim().split(/[\s·]+/)[0].toLowerCase();
        hit = (cmProblems || []).find((p) => p.id.toLowerCase() === token);
      }
      if (hit) { problem_id = hit.id; problem_title = hit.title; }
    }
    btn.disabled = true; btn.textContent = T("审核中…", "Moderating…");
    try {
      const r = await fetch("/api/community/posts", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tag: getTag(), title, body, problem_id, problem_title }),
      });
      const data = await r.json();
      if (!r.ok) { err.textContent = data.error || T("发布失败", "Failed to publish"); return; }
      rewardToast(data.reward, T("✅ 发布成功", "✅ Published"));
      if (window.refreshBilling) window.refreshBilling();   // 发帖奖励算力点 → 即时刷新顶栏
      closeDrawer();
      cmTag = ""; syncTagButtons();
      loadList();
    } catch (e) { err.textContent = T("网络错误，请重试", "Network error, try again"); }
    finally { btn.disabled = false; btn.textContent = T("发布", "Publish"); }
  }
  // 答疑激励：后端发了算力点就连带提示「+N」，否则只报成功
  function rewardToast(reward, okMsg) {
    const r = Number(reward) || 0;
    const msg = r > 0
      ? okMsg + T("　🎁 答疑奖励 +" + r + " 算力点", "　🎁 +" + r + " credits")
      : okMsg;
    (window.toast || console.log)(msg);
  }

  /* ---------------- 详情 + 回帖 ---------------- */
  async function openDetail(id) {
    $c("#cm-drawer-body").innerHTML = '<div class="cm-empty">' + T("加载帖子…", "Loading post…") + '</div>';
    openDrawer();
    let p;
    try { p = await fetch("/api/community/posts/" + id).then((r) => r.json()); }
    catch (e) { $c("#cm-drawer-body").innerHTML = '<div class="cm-empty">' + T("加载失败", "Failed to load") + '</div>'; return; }
    if (!p || p.error) { $c("#cm-drawer-body").innerHTML = '<div class="cm-empty">' + T("帖子不存在", "Post not found") + '</div>'; return; }
    renderDetail(p);
  }

  function renderDetail(p) {
    const replies = (p.replies || []).map((r) => `
      <div class="cm-reply">
        <div class="cm-reply-head"><span class="cm-reply-author">👤 ${E(r.username)}</span>
          <span class="cm-reply-time">${fmtTime(r.created_at)}</span></div>
        <div class="cm-reply-body">${E(r.body)}</div>
      </div>`).join("");
    $c("#cm-drawer-body").innerHTML = `
      <div class="cm-detail">
        <div class="cm-detail-top">${tagBadge(p.tag)}<span class="cm-detail-time">${fmtTime(p.created_at)}</span></div>
        <h3 class="cm-detail-title">${E(p.title)}</h3>
        <div class="cm-detail-meta">👤 ${E(p.username)}</div>
        ${p.problem_title ? `<button type="button" class="cm-detail-prob" data-pid="${E(p.problem_id || "")}">${T("📎 关联题目：", "📎 Linked: ")}${E(p.problem_title)}${T(" · 去做这题 →", " · solve it →")}</button>` : ""}
        <div class="cm-detail-body">${E(p.body)}</div>
        <div class="cm-detail-actions">
          <button id="cm-like-btn" class="cm-like${p.liked ? " liked" : ""}">👍 <span id="cm-like-n">${p.likes}</span></button>
        </div>
        <div class="cm-replies-head">💬 ${p.reply_count} ${T("条回复", "replies")}</div>
        <div class="cm-replies" id="cm-replies">${replies || '<div class="cm-empty-sm">' + T("还没有回复，来抢个沙发～", "No replies yet — grab the first seat!") + '</div>'}</div>
        <div class="cm-reply-box">
          <textarea id="cm-r-body" class="cm-textarea cm-reply-input" placeholder="${T("写下你的思路或解答…（回复同样经过审核）", "Write your idea or answer… (replies are moderated too)")}"></textarea>
          <div class="cm-reply-foot"><span id="cm-r-err" class="cm-err"></span>
            <button id="cm-r-submit" class="btn btn-primary cm-mini">${T("回复", "Reply")}</button></div>
        </div>
      </div>`;
    $c("#cm-like-btn").onclick = () => toggleLike(p.id);
    $c("#cm-r-submit").onclick = () => submitReply(p.id);
    const probBtn = $c("#cm-drawer-body").querySelector(".cm-detail-prob");
    if (probBtn) probBtn.onclick = () => {
      const pid = probBtn.dataset.pid;
      if (pid && window.cpLoadProblem) { closeDrawer(); window.cpLoadProblem(pid); }
    };
  }

  async function toggleLike(id) {
    if (!loggedIn()) return needLogin("点赞", "like");
    try {
      const r = await fetch("/api/community/posts/" + id + "/like", { method: "POST" });
      const data = await r.json();
      if (!r.ok) return (window.toast || console.log)(data.error || T("操作失败", "Action failed"));
      const btn = $c("#cm-like-btn");
      $c("#cm-like-n").textContent = data.likes;
      btn.classList.toggle("liked", data.liked);
    } catch (e) { (window.toast || console.log)(T("点赞失败", "Like failed")); }
  }

  async function submitReply(id) {
    if (!loggedIn()) return needLogin("回复", "reply");
    const body = $c("#cm-r-body").value.trim();
    const err = $c("#cm-r-err");
    const btn = $c("#cm-r-submit");
    if (body.length < 2) { err.textContent = T("回复太短了", "Reply is too short"); return; }
    err.textContent = "";
    btn.disabled = true; btn.textContent = T("审核中…", "Moderating…");
    try {
      const r = await fetch("/api/community/posts/" + id + "/reply", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body }),
      });
      const data = await r.json();
      if (!r.ok) { err.textContent = data.error || T("回复失败", "Reply failed"); return; }
      openDetail(id);   // 重新拉取以刷新回复列表与计数
      loadList();       // 列表里的回复数也更新
      rewardToast(data.reward, T("✅ 已回复", "✅ Replied"));
      if (window.refreshBilling) window.refreshBilling();   // 答疑奖励算力点 → 即时刷新顶栏
    } catch (e) { err.textContent = T("网络错误", "Network error"); }
    finally { btn.disabled = false; btn.textContent = T("回复", "Reply"); }
  }

  /* ---------------- 标签筛选 ---------------- */
  function syncTagButtons() {
    document.querySelectorAll("#cm-tags .cm-tag").forEach((b) => b.classList.toggle("active", (b.dataset.tag || "") === cmTag));
  }
  function bind() {
    document.querySelectorAll("#cm-tags .cm-tag").forEach((b) => (b.onclick = () => {
      cmTag = b.dataset.tag || ""; syncTagButtons(); loadList();
    }));
    $c("#cm-new-btn").onclick = openComposer;
    const sortBox = $c("#cm-sort");
    if (sortBox) sortBox.querySelectorAll(".cm-sort-btn").forEach((b) => (b.onclick = () => {
      cmSort = b.dataset.sort || "hot";
      sortBox.querySelectorAll(".cm-sort-btn").forEach((x) => x.classList.toggle("active", x === b));
      loadList();
    }));
    $c("#cm-drawer-close").onclick = closeDrawer;
    $c("#cm-overlay").onclick = closeDrawer;
    const search = $c("#cm-search");
    if (search) {
      let st;
      search.oninput = () => {
        clearTimeout(st);
        st = setTimeout(() => { cmKeyword = search.value.trim(); loadList(); }, 250);
      };
    }
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
  }

  window.loadCommunity = function () {
    if (!cmInited) { bind(); cmInited = true; }
    loadList();
  };
  // 供 app.js 从「题目剖析」一键跳到某帖详情
  window.cmOpenPost = function (id) {
    if (!cmInited) { cmSyncSort(); bind(); cmInited = true; }
    openDetail(id);
  };
  // 供 app.js 从题目页一键发本题题解（自动带上当前题目关联，默认「题解」板块）
  window.cmNewPost = function (presetTag) {
    if (!cmInited) { cmSyncSort(); bind(); cmInited = true; }
    openComposer(presetTag);
  };
  // 让排序按钮的高亮与当前 cmSort 一致（首次进入或被外部入口唤起时）
  function cmSyncSort() {
    const box = $c("#cm-sort");
    if (box) box.querySelectorAll(".cm-sort-btn").forEach((x) =>
      x.classList.toggle("active", (x.dataset.sort || "hot") === cmSort));
  }

  // 语言切换：重拉列表（卡片里的标签徽章/时间等界面文案随之切换）
  window.addEventListener("langchange", () => { if (cmInited) loadList(); });
})();
