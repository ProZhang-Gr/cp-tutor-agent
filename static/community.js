/* ====================================================================
   社群讨论区 — 前端逻辑
   帖子列表 / 标签筛选 / 发帖 / 详情回帖 / 点赞
   复用 app.js 的全局：esc / toast / currentUser / openAuth
==================================================================== */
(function () {
  const $c = (s) => document.querySelector(s);
  const TAG_CLS = { "求助": "ask", "题解": "solu", "讨论": "disc", "反馈": "fb" };
  const TAGS = ["求助", "题解", "讨论", "反馈"];
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
  let cmTag = "";
  let cmInited = false;

  function fmtTime(ts) {
    const diff = Date.now() / 1000 - ts;
    if (diff < 60) return "刚刚";
    if (diff < 3600) return Math.floor(diff / 60) + " 分钟前";
    if (diff < 86400) return Math.floor(diff / 3600) + " 小时前";
    if (diff < 86400 * 7) return Math.floor(diff / 86400) + " 天前";
    const d = new Date(ts * 1000);
    return `${d.getMonth() + 1}-${String(d.getDate()).padStart(2, "0")}`;
  }
  function tagBadge(t) { return `<span class="cm-tag-badge ${TAG_CLS[t] || "disc"}">${E(t)}</span>`; }
  function E(s) { return (window.esc || ((x) => x))(s); }
  function loggedIn() { return !!(window.currentUser); }
  function needLogin(action) {
    (window.toast || console.log)("请先登录再" + action);
    if (window.openAuth) window.openAuth("login");
  }

  async function loadList() {
    const list = $c("#cm-list");
    list.innerHTML = '<div class="cm-empty">加载中…</div>';
    try {
      const r = await fetch("/api/community/posts?tag=" + encodeURIComponent(cmTag)).then((r) => r.json());
      renderList(r.posts || []);
    } catch (e) { list.innerHTML = '<div class="cm-empty">加载失败，请稍后再试</div>'; }
  }

  function renderList(posts) {
    const list = $c("#cm-list");
    if (!posts.length) { list.innerHTML = '<div class="cm-empty">这个板块还没有帖子，来发第一帖吧～</div>'; return; }
    list.innerHTML = posts.map((p) => `
      <button type="button" class="cm-card" data-id="${p.id}">
        <div class="cm-card-top">${tagBadge(p.tag)}<span class="cm-card-title">${E(p.title)}</span></div>
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
  function openComposer() {
    if (!loggedIn()) return needLogin("发帖");
    $c("#cm-drawer-body").innerHTML = `
      <div class="cm-compose">
        <h3 class="cm-drawer-title">✎ 发表新帖</h3>
        <div class="cm-field-label">选择板块</div>
        <div class="cm-compose-tags" id="cm-c-tags">
          ${TAGS.map((t, i) => `<button type="button" class="cm-ctag ${TAG_CLS[t]}${i === 2 ? " active" : ""}" data-tag="${t}">${t}</button>`).join("")}
        </div>
        <div class="cm-field-label">标题</div>
        <input id="cm-c-title" class="cm-input" maxlength="80" placeholder="一句话说清问题，如「快排为什么会退化到 O(n²)」">
        <div class="cm-field-label">正文</div>
        <textarea id="cm-c-body" class="cm-textarea" placeholder="详细描述你的问题 / 思路 / 反馈…"></textarea>
        <div class="cm-compose-foot">
          <span class="cm-guard-note">⚖️ 发布前会经敏感词 + AI 审核护栏</span>
          <button id="cm-c-submit" class="btn btn-primary">发布</button>
        </div>
        <div id="cm-c-err" class="cm-err"></div>
      </div>`;
    let tag = "讨论";
    const applyPH = (t) => {
      const ph = PH[t] || PH["讨论"];
      $c("#cm-c-title").placeholder = ph.t;
      $c("#cm-c-body").placeholder = ph.b;
    };
    $c("#cm-c-tags").querySelectorAll(".cm-ctag").forEach((b) => (b.onclick = () => {
      tag = b.dataset.tag;
      $c("#cm-c-tags").querySelectorAll(".cm-ctag").forEach((x) => x.classList.toggle("active", x === b));
      applyPH(tag);   // 切板块 → 占位提示随之变化
    }));
    applyPH(tag);     // 初始占位提示与默认板块（讨论）一致
    $c("#cm-c-submit").onclick = () => submitPost(() => tag);
    openDrawer();
    setTimeout(() => $c("#cm-c-title").focus(), 80);
  }

  async function submitPost(getTag) {
    const title = $c("#cm-c-title").value.trim();
    const body = $c("#cm-c-body").value.trim();
    const err = $c("#cm-c-err");
    const btn = $c("#cm-c-submit");
    if (!title) { err.textContent = "标题不能为空"; return; }
    if (body.length < 2) { err.textContent = "正文太短了"; return; }
    err.textContent = "";
    btn.disabled = true; btn.textContent = "审核中…";
    try {
      const r = await fetch("/api/community/posts", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tag: getTag(), title, body }),
      });
      const data = await r.json();
      if (!r.ok) { err.textContent = data.error || "发布失败"; return; }
      (window.toast || console.log)("✅ 发布成功");
      closeDrawer();
      cmTag = ""; syncTagButtons();
      loadList();
    } catch (e) { err.textContent = "网络错误，请重试"; }
    finally { btn.disabled = false; btn.textContent = "发布"; }
  }

  /* ---------------- 详情 + 回帖 ---------------- */
  async function openDetail(id) {
    $c("#cm-drawer-body").innerHTML = '<div class="cm-empty">加载帖子…</div>';
    openDrawer();
    let p;
    try { p = await fetch("/api/community/posts/" + id).then((r) => r.json()); }
    catch (e) { $c("#cm-drawer-body").innerHTML = '<div class="cm-empty">加载失败</div>'; return; }
    if (!p || p.error) { $c("#cm-drawer-body").innerHTML = '<div class="cm-empty">帖子不存在</div>'; return; }
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
        <div class="cm-detail-body">${E(p.body)}</div>
        <div class="cm-detail-actions">
          <button id="cm-like-btn" class="cm-like${p.liked ? " liked" : ""}">👍 <span id="cm-like-n">${p.likes}</span></button>
        </div>
        <div class="cm-replies-head">💬 ${p.reply_count} 条回复</div>
        <div class="cm-replies" id="cm-replies">${replies || '<div class="cm-empty-sm">还没有回复，来抢个沙发～</div>'}</div>
        <div class="cm-reply-box">
          <textarea id="cm-r-body" class="cm-textarea cm-reply-input" placeholder="写下你的思路或解答…（回复同样经过审核）"></textarea>
          <div class="cm-reply-foot"><span id="cm-r-err" class="cm-err"></span>
            <button id="cm-r-submit" class="btn btn-primary cm-mini">回复</button></div>
        </div>
      </div>`;
    $c("#cm-like-btn").onclick = () => toggleLike(p.id);
    $c("#cm-r-submit").onclick = () => submitReply(p.id);
  }

  async function toggleLike(id) {
    if (!loggedIn()) return needLogin("点赞");
    try {
      const r = await fetch("/api/community/posts/" + id + "/like", { method: "POST" });
      const data = await r.json();
      if (!r.ok) return (window.toast || console.log)(data.error || "操作失败");
      const btn = $c("#cm-like-btn");
      $c("#cm-like-n").textContent = data.likes;
      btn.classList.toggle("liked", data.liked);
    } catch (e) { (window.toast || console.log)("点赞失败"); }
  }

  async function submitReply(id) {
    if (!loggedIn()) return needLogin("回复");
    const body = $c("#cm-r-body").value.trim();
    const err = $c("#cm-r-err");
    const btn = $c("#cm-r-submit");
    if (body.length < 2) { err.textContent = "回复太短了"; return; }
    err.textContent = "";
    btn.disabled = true; btn.textContent = "审核中…";
    try {
      const r = await fetch("/api/community/posts/" + id + "/reply", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body }),
      });
      const data = await r.json();
      if (!r.ok) { err.textContent = data.error || "回复失败"; return; }
      openDetail(id);   // 重新拉取以刷新回复列表与计数
      loadList();       // 列表里的回复数也更新
      (window.toast || console.log)("✅ 已回复");
    } catch (e) { err.textContent = "网络错误"; }
    finally { btn.disabled = false; btn.textContent = "回复"; }
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
    $c("#cm-drawer-close").onclick = closeDrawer;
    $c("#cm-overlay").onclick = closeDrawer;
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
  }

  window.loadCommunity = function () {
    if (!cmInited) { bind(); cmInited = true; }
    loadList();
  };
})();
