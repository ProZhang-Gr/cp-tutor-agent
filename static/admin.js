/* 运营控制台前端：原生 JS + fetch。管理态走 httponly Cookie，请求默认同源携带。
   覆盖：登录闸门 / 概览仪表盘（KPI·系统健康·14天趋势·实时活动）/ 用户增删改查 +
        重置密码 / 活动审计 / 内容治理。密码列只展示哈希指纹，永不显示明文。 */
(function () {
  "use strict";

  // ---------------- 基础工具 ----------------
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  function api(method, path, body) {
    var opt = { method: method, headers: {}, credentials: "same-origin" };
    if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
    return fetch(path, opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) { throw new Error((j && j.error) || ("HTTP " + r.status)); }
        return j;
      });
    });
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function pad(n) { return n < 10 ? "0" + n : "" + n; }
  function fmtDate(ts) { var d = new Date(ts * 1000); return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function fmtTime(ts) {
    var d = new Date(ts * 1000);
    return pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }
  function fmtAgo(ts) {
    if (!ts) return "—";
    var s = Date.now() / 1000 - ts;
    if (s < 60) return "刚刚";
    if (s < 3600) return Math.floor(s / 60) + " 分钟前";
    if (s < 86400) return Math.floor(s / 3600) + " 小时前";
    if (s < 86400 * 30) return Math.floor(s / 86400) + " 天前";
    return fmtDate(ts);
  }
  function fmtUptime(sec) {
    var d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60);
    if (d) return d + " 天 " + h + " 时";
    if (h) return h + " 时 " + m + " 分";
    return m + " 分钟";
  }

  function toast(msg, isErr) {
    var t = $("#toast");
    t.textContent = msg;
    t.className = "toast" + (isErr ? " err" : "");
    setTimeout(function () { t.className = "toast hidden"; }, 2600);
  }

  // ---------------- 弹窗 ----------------
  function openModal(title, bodyHtml) {
    $("#modal-title").textContent = title;
    $("#modal-body").innerHTML = bodyHtml;
    $("#modal").classList.remove("hidden");
  }
  function closeModal() { $("#modal").classList.add("hidden"); }
  $("#modal-x").onclick = closeModal;
  $("#modal").onclick = function (e) { if (e.target === $("#modal")) closeModal(); };

  // ---------------- 登录闸门 ----------------
  function showShell() {
    $("#gate").classList.add("hidden");
    $("#shell").classList.remove("hidden");
    switchView("overview");
    refreshBadge();
    startClock();
  }

  $("#gate-form").onsubmit = function (e) {
    e.preventDefault();
    var u = $("#gate-user").value.trim(), p = $("#gate-pass").value;
    $("#gate-err").textContent = "";
    $("#gate-btn").disabled = true;
    api("POST", "/api/admin/login", { username: u, password: p }).then(function () {
      showShell();
    }).catch(function (err) {
      $("#gate-err").textContent = err.message || "登录失败";
    }).then(function () { $("#gate-btn").disabled = false; });
  };

  $("#logout-btn").onclick = function () {
    api("POST", "/api/admin/logout").then(function () { location.reload(); });
  };

  // ---------------- 导航 ----------------
  var VIEW_META = {
    overview: ["概览", "平台运营全景"],
    users: ["用户管理", "账号 · 算力点 · 学习行为，增删改查"],
    resets: ["密码申请", "向管理员申请重置密码的工单"],
    activity: ["活动审计", "平台调用与安全取证"],
    content: ["内容治理", "社群帖子审核与下架"]
  };
  function switchView(view) {
    $$(".nav-item").forEach(function (n) { n.classList.toggle("active", n.dataset.view === view); });
    $$(".view").forEach(function (v) { v.classList.add("hidden"); });
    $("#view-" + view).classList.remove("hidden");
    $("#view-title").textContent = VIEW_META[view][0];
    $("#view-sub").textContent = VIEW_META[view][1];
    if (view === "overview") loadOverview();
    if (view === "users") loadUsers();
    if (view === "resets") loadResets();
    if (view === "activity") loadAudit();
    if (view === "content") loadPosts();
  }
  $$(".nav-item").forEach(function (n) { n.onclick = function () { switchView(n.dataset.view); }; });
  document.addEventListener("click", function (e) {
    var j = e.target.closest("[data-jump]");
    if (j) switchView(j.dataset.jump);
  });

  // ---------------- 概览 ----------------
  function kpiCard(label, val, sub, cls) {
    return '<div class="kpi ' + (cls || "") + '">' +
      '<div class="k-label">' + esc(label) + '</div>' +
      '<div class="k-val">' + esc(val) + '</div>' +
      '<div class="k-sub">' + esc(sub || "") + '</div></div>';
  }

  function barChart(series, amber) {
    if (!series || !series.length) return '<svg viewBox="0 0 280 84"></svg>';
    var n = series.length, step = 280 / n, bw = Math.max(3, step * 0.62);
    var max = 0; series.forEach(function (d) { if (d.count > max) max = d.count; });
    max = max || 1;
    var svg = '<svg viewBox="0 0 280 84" preserveAspectRatio="none">';
    series.forEach(function (d, i) {
      var h = Math.round((d.count / max) * 64);
      var x = i * step + (step - bw) / 2, y = 72 - h;
      svg += '<rect class="bar' + (amber ? ' amber' : '') + '" x="' + x.toFixed(1) + '" y="' + y +
        '" width="' + bw.toFixed(1) + '" height="' + Math.max(1, h) + '" rx="1.5"><title>' +
        d.date + "：" + d.count + '</title></rect>';
      if (i % 3 === 0 || i === n - 1) {
        svg += '<text class="lbl" x="' + (i * step + step / 2).toFixed(1) + '" y="82" text-anchor="middle">' + d.date + '</text>';
      }
    });
    svg += '</svg>';
    return svg;
  }

  function loadOverview() {
    api("GET", "/api/admin/overview").then(function (o) {
      var k = o.kpi, sy = o.system;
      $("#kpi-row").innerHTML =
        kpiCard("用户总数", k.total_users, "今日新增 " + k.today_signups) +
        kpiCard("今日活跃", k.dau, "近 24 小时", "good") +
        kpiCard("累计提交", k.total_submissions, "AC 率 " + k.ac_rate + "%") +
        kpiCard("今日 AI 调用", sy.llm_today, "上限 " + (sy.llm_cap || "∞"), "amber") +
        kpiCard("Pro 用户", k.pro_users, "算力点共 " + k.total_credits, "amber") +
        kpiCard("学习时长", k.active_hours + " h", "运行 " + k.total_runs + " · 评测 " + k.total_submits);

      function si(kk, vv) { return '<div class="sys-item"><span class="s-k">' + kk + '</span><span class="s-v">' + vv + '</span></div>'; }
      $("#sys-grid").innerHTML =
        si("数据库", esc(sy.db)) +
        si("在线时长", fmtUptime(sy.uptime_seconds)) +
        si("Python", esc(sy.python)) +
        si("运行平台", esc(sy.platform)) +
        si("题库题量", sy.bank_count + " 题") +
        si("AI 密钥", sy.llm_key ? '<span class="pill ok">已配置</span>' : '<span class="pill warn">缺失</span>');

      var cap = sy.llm_cap || 0, pct = cap ? Math.min(100, sy.llm_cap_pct) : 0;
      $("#cap-text").textContent = cap ? (sy.llm_today + " / " + cap + "（" + pct + "%）") : (sy.llm_today + " / 不限");
      $("#cap-fill").style.width = pct + "%";

      $("#chart-sub").innerHTML = barChart(o.trend_submissions, false);
      $("#chart-llm").innerHTML = barChart(o.trend_llm, true);
    }).catch(function (e) { toast(e.message, true); });

    api("GET", "/api/admin/audit?limit=8").then(function (r) {
      $("#feed").innerHTML = (r.audit || []).map(function (a) {
        return '<div class="feed-row">' +
          '<span class="feed-ep">' + esc(a.endpoint) + '</span>' +
          '<span class="feed-user">' + esc(a.username || "—") + '</span>' +
          '<span class="feed-ip mono">' + esc(a.ip) + '</span>' +
          '<span class="feed-time">' + fmtTime(a.ts) + '</span></div>';
      }).join("") || '<div class="feed-row"><span class="muted">暂无记录</span></div>';
    });
  }

  // ---------------- 用户管理 ----------------
  var userState = { q: "", page: 1, size: 20, total: 0 };

  function pwCell(p) {
    if (!p) return "—";
    return '<div class="pw-cell">' +
      '<span class="pw-algo">🔒 ' + esc(p.algo) + ' · ' + esc(p.iters) + ' 迭代</span>' +
      '<span class="pw-hash">' + esc(p.hash_preview) + '… · salt ' + esc(p.salt_preview) + '…</span></div>';
  }

  function userRow(u) {
    var pro = u.is_pro ? '<span class="tag-pro">PRO</span>' : '<span class="tag-free">普通</span>';
    return '<tr data-uid="' + u.id + '">' +
      '<td class="mono">' + u.id + '</td>' +
      '<td><span class="u-name">' + esc(u.username) + '</span></td>' +
      '<td class="muted">' + fmtDate(u.created_at) + '</td>' +
      '<td><b>' + u.credits + '</b>' + pro + '</td>' +
      '<td class="mono">' + u.submissions + ' / ' + u.ac + '</td>' +
      '<td class="mono">' + u.active_minutes + ' 分</td>' +
      '<td class="muted">' + fmtAgo(u.last_active) + '</td>' +
      '<td>' + pwCell(u.password) + '</td>' +
      '<td class="ta-r"><div class="row-act">' +
        '<button class="mini" data-act="detail">详情</button>' +
        '<button class="mini" data-act="edit">改</button>' +
        '<button class="mini" data-act="reset">重置密码</button>' +
        '<button class="mini danger" data-act="del">删</button>' +
      '</div></td></tr>';
  }

  function loadUsers() {
    api("GET", "/api/admin/users?q=" + encodeURIComponent(userState.q) +
      "&page=" + userState.page + "&size=" + userState.size).then(function (r) {
      userState.total = r.total;
      $("#user-rows").innerHTML = r.users.map(userRow).join("") ||
        '<tr><td colspan="9" class="muted" style="text-align:center;padding:24px">没有匹配的用户</td></tr>';
      $("#user-total").textContent = "共 " + r.total + " 名用户";
      renderPager();
    }).catch(function (e) { toast(e.message, true); });
  }

  function renderPager() {
    var pages = Math.max(1, Math.ceil(userState.total / userState.size));
    var p = userState.page;
    $("#user-pager").innerHTML =
      '<button data-p="prev"' + (p <= 1 ? " disabled" : "") + '>← 上一页</button>' +
      '<span class="muted">第 ' + p + " / " + pages + ' 页</span>' +
      '<button data-p="next"' + (p >= pages ? " disabled" : "") + '>下一页 →</button>';
    $$("#user-pager button").forEach(function (b) {
      b.onclick = function () {
        if (b.dataset.p === "prev" && p > 1) userState.page--;
        if (b.dataset.p === "next" && p < pages) userState.page++;
        loadUsers();
      };
    });
  }

  var searchTimer;
  $("#user-search").oninput = function (e) {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () {
      userState.q = e.target.value.trim(); userState.page = 1; loadUsers();
    }, 280);
  };

  $("#user-rows").onclick = function (e) {
    var btn = e.target.closest("button[data-act]"); if (!btn) return;
    var uid = btn.closest("tr").dataset.uid;
    var act = btn.dataset.act;
    if (act === "detail") openUserDetail(uid);
    if (act === "edit") openUserEdit(uid);
    if (act === "reset") openResetPw(uid);
    if (act === "del") doDeleteUser(uid);
  };

  $("#add-user-btn").onclick = function () {
    openModal("新增用户",
      '<label>用户名<input id="m-user" placeholder="2-20 位，字母/数字/下划线/中文" /></label>' +
      '<label>初始密码<input id="m-pass" type="text" placeholder="至少 8 位" /></label>' +
      '<label>赠送算力点（可空）<input id="m-credits" type="number" min="0" value="0" /></label>' +
      modalActions("创建"));
    bindModalSubmit(function () {
      return api("POST", "/api/admin/users", {
        username: $("#m-user").value.trim(),
        password: $("#m-pass").value,
        credits: parseInt($("#m-credits").value || "0", 10) || 0
      }).then(function () { toast("已创建用户"); closeModal(); loadUsers(); });
    });
  };

  function openUserEdit(uid) {
    api("GET", "/api/admin/users/" + uid).then(function (u) {
      openModal("编辑用户 · " + esc(u.username),
        '<label>用户名<input id="m-user" value="' + esc(u.username) + '" /></label>' +
        '<label>算力点（>0 即 Pro）<input id="m-credits" type="number" min="0" value="' + u.credits + '" /></label>' +
        modalActions("保存"));
      bindModalSubmit(function () {
        return api("PATCH", "/api/admin/users/" + uid, {
          username: $("#m-user").value.trim(),
          credits: parseInt($("#m-credits").value || "0", 10) || 0
        }).then(function () { toast("已保存"); closeModal(); loadUsers(); });
      });
    }).catch(function (e) { toast(e.message, true); });
  }

  function openResetPw(uid) {
    openModal("重置密码",
      '<p class="modal-tip">系统看不到原密码（不可逆哈希）。这里直接为该账号设置一个新密码，' +
      '设好后请把新密码线下告知本人。</p>' +
      '<label>新密码<input id="m-pass" type="text" placeholder="至少 8 位" /></label>' +
      modalActions("重置"));
    bindModalSubmit(function () {
      return api("POST", "/api/admin/users/" + uid + "/reset-password", {
        password: $("#m-pass").value
      }).then(function () { toast("密码已重置"); closeModal(); });
    });
  }

  function doDeleteUser(uid) {
    var row = $('#user-rows tr[data-uid="' + uid + '"]');
    var name = row ? row.querySelector(".u-name").textContent : uid;
    openModal("删除用户",
      '<p class="modal-tip">将删除用户 <b style="color:var(--paper)">' + esc(name) + '</b> 及其提交、学习记录、' +
      '题单与点赞；其社群帖子改为匿名保留，避免破坏他人讨论。此操作不可撤销。</p>' +
      modalActions("确认删除", true));
    bindModalSubmit(function () {
      return api("DELETE", "/api/admin/users/" + uid).then(function () {
        toast("已删除用户"); closeModal(); loadUsers();
      });
    });
  }

  function openUserDetail(uid) {
    api("GET", "/api/admin/users/" + uid).then(function (u) {
      var subs = (u.submissions || []).map(function (s) {
        return '<div>' + fmtTime(s.ts) + ' · ' + esc(s.problem_title || "未命名") +
          ' · ' + (s.passed ? "✅ AC" : "❌ " + esc(s.error_kind)) + ' · ' + s.score + ' 分</div>';
      }).join("") || '<div class="muted">暂无提交</div>';
      var posts = (u.posts || []).map(function (p) {
        return '<div>[' + esc(p.tag) + '] ' + esc(p.title) + ' · 👍' + p.likes + ' 💬' + p.reply_count + '</div>';
      }).join("") || '<div class="muted">暂无发帖</div>';
      openModal("用户详情 · " + esc(u.username),
        '<div class="modal-detail">' +
          '<div><span class="d-k">ID</span>' + u.id + '</div>' +
          '<div><span class="d-k">注册时间</span>' + fmtTime(u.created_at) + '</div>' +
          '<div><span class="d-k">算力点</span>' + u.credits + (u.is_pro ? '（PRO）' : '（普通）') + '</div>' +
          '<div><span class="d-k">密码</span><span class="pw-algo">' + esc(u.password.algo) + ' · ' +
            esc(u.password.iters) + ' 迭代 · ' + esc(u.password.hash_preview) + '… 不可逆</span></div>' +
          '<div><span class="d-k">学习</span>专注 ' + u.study.active_minutes + ' 分 · 运行 ' +
            u.study.runs + ' · 评测 ' + u.study.submits + ' · 击键 ' + u.study.keystrokes + '</div>' +
          '<div class="sec-t">最近提交</div><div class="mini-list">' + subs + '</div>' +
          '<div class="sec-t">社群发帖</div><div class="mini-list">' + posts + '</div>' +
        '</div>');
    }).catch(function (e) { toast(e.message, true); });
  }

  function modalActions(okText, danger) {
    return '<div class="modal-actions">' +
      '<button class="btn-cancel" id="m-cancel">取消</button>' +
      '<button class="btn-primary" id="m-ok"' + (danger ? ' style="background:var(--rose)"' : '') + '>' + okText + '</button></div>';
  }
  function bindModalSubmit(fn) {
    $("#m-cancel").onclick = closeModal;
    $("#m-ok").onclick = function () {
      $("#m-ok").disabled = true;
      fn().catch(function (e) { toast(e.message, true); }).then(function () {
        if ($("#m-ok")) $("#m-ok").disabled = false;
      });
    };
  }

  // ---------------- 密码找回申请 ----------------
  function setBadge(n) {
    var b = $("#reset-badge");
    if (n > 0) { b.textContent = n; b.classList.remove("hidden"); }
    else b.classList.add("hidden");
  }
  function refreshBadge() {
    api("GET", "/api/admin/reset-requests?status=pending").then(function (r) {
      setBadge(r.pending || 0);
    }).catch(function () {});
  }

  function loadResets() {
    var status = $("#reset-filter").value || "pending";
    api("GET", "/api/admin/reset-requests?status=" + status).then(function (r) {
      setBadge(r.pending || 0);
      $("#reset-rows").innerHTML = (r.requests || []).map(function (q) {
        var act = q.status === "pending"
          ? '<button class="mini" data-act="resolve">重置密码</button>' +
            '<button class="mini danger" data-act="dismiss">忽略</button>'
          : '<span class="muted">已处理</span>';
        return '<tr data-rid="' + q.id + '"><td class="mono">' + q.id + '</td>' +
          '<td><span class="u-name">' + esc(q.username) + '</span></td>' +
          '<td>' + (esc(q.contact) || '<span class="muted">—</span>') + '</td>' +
          '<td style="max-width:280px">' + (esc(q.note) || '<span class="muted">—</span>') + '</td>' +
          '<td><span class="status-pill ' + q.status + '">' +
            ({ pending: "待处理", done: "已重置", dismissed: "已忽略" }[q.status] || q.status) + '</span></td>' +
          '<td class="muted">' + fmtTime(q.created_at) + '</td>' +
          '<td class="ta-r"><div class="row-act">' + act + '</div></td></tr>';
      }).join("") || '<tr><td colspan="7" class="muted" style="text-align:center;padding:24px">没有工单</td></tr>';
    }).catch(function (e) { toast(e.message, true); });
  }
  $("#reset-refresh").onclick = loadResets;
  $("#reset-filter").onchange = loadResets;
  $("#reset-rows").onclick = function (e) {
    var btn = e.target.closest("button[data-act]"); if (!btn) return;
    var tr = btn.closest("tr"), rid = tr.dataset.rid;
    var name = tr.querySelector(".u-name").textContent;
    if (btn.dataset.act === "resolve") {
      openModal("重置密码 · " + esc(name),
        '<p class="modal-tip">为账号 <b style="color:var(--paper)">' + esc(name) + '</b> 设置新密码。' +
        '请先核实申请人身份，设好后线下告知本人。系统看不到原密码。</p>' +
        '<label>新密码<input id="m-pass" type="text" placeholder="至少 8 位" /></label>' +
        modalActions("确认重置"));
      bindModalSubmit(function () {
        return api("POST", "/api/admin/reset-requests/" + rid + "/resolve", {
          password: $("#m-pass").value
        }).then(function () { toast("已重置并关闭工单"); closeModal(); loadResets(); });
      });
    } else {
      openModal("忽略工单", '<p class="modal-tip">将该工单标记为已忽略（不重置密码）。</p>' + modalActions("确认忽略", true));
      bindModalSubmit(function () {
        return api("POST", "/api/admin/reset-requests/" + rid + "/dismiss").then(function () {
          toast("已忽略"); closeModal(); loadResets();
        });
      });
    }
  };

  // ---------------- 活动审计 ----------------
  function loadAudit() {
    api("GET", "/api/admin/audit?limit=120").then(function (r) {
      $("#audit-rows").innerHTML = (r.audit || []).map(function (a) {
        return '<tr><td class="muted">' + fmtTime(a.ts) + '</td>' +
          '<td>' + esc(a.username || "—") + '</td>' +
          '<td class="mono">' + esc(a.ip) + '</td>' +
          '<td style="color:var(--teal)">' + esc(a.endpoint) + '</td>' +
          '<td class="mono" style="max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' +
            esc(a.meta) + '">' + esc(a.meta || "—") + '</td></tr>';
      }).join("") || '<tr><td colspan="5" class="muted" style="text-align:center;padding:24px">暂无记录</td></tr>';
    }).catch(function (e) { toast(e.message, true); });
  }
  $("#audit-refresh").onclick = loadAudit;

  // ---------------- 内容治理 ----------------
  function loadPosts() {
    api("GET", "/api/admin/posts?limit=100").then(function (r) {
      $("#post-rows").innerHTML = (r.posts || []).map(function (p) {
        return '<tr data-pid="' + p.id + '"><td class="mono">' + p.id + '</td>' +
          '<td>' + esc(p.username) + (p.anonymous ? ' <span class="tag-free">已注销</span>' : '') + '</td>' +
          '<td><span style="color:var(--teal)">' + esc(p.tag) + '</span></td>' +
          '<td>' + esc(p.title) + '</td>' +
          '<td class="mono">👍' + p.likes + ' 💬' + p.reply_count + '</td>' +
          '<td class="muted">' + fmtDate(p.created_at) + '</td>' +
          '<td class="ta-r"><button class="mini danger" data-act="delpost">删除</button></td></tr>';
      }).join("") || '<tr><td colspan="7" class="muted" style="text-align:center;padding:24px">暂无帖子</td></tr>';
    }).catch(function (e) { toast(e.message, true); });
  }
  $("#content-refresh").onclick = loadPosts;
  $("#post-rows").onclick = function (e) {
    var btn = e.target.closest("button[data-act='delpost']"); if (!btn) return;
    var pid = btn.closest("tr").dataset.pid;
    openModal("删除帖子", '<p class="modal-tip">将删除该帖及其全部回复与点赞，不可撤销。</p>' + modalActions("确认删除", true));
    bindModalSubmit(function () {
      return api("DELETE", "/api/admin/posts/" + pid).then(function () {
        toast("已删除帖子"); closeModal(); loadPosts();
      });
    });
  };

  // ---------------- 时钟 ----------------
  function startClock() {
    function tick() {
      var d = new Date();
      $("#clock").textContent = d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
        " " + pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
    }
    tick(); setInterval(tick, 1000);
  }

  // ---------------- 启动：检查既有管理态 ----------------
  api("GET", "/api/admin/session").then(function (r) {
    if (r.admin) showShell();
  });
})();
