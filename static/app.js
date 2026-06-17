/* ====================================================================
   算法竞赛辅导智能体 — 前端逻辑
   Monaco 编辑器 · SSE 流式 · 智能体可视化 · Chart.js 仪表盘
==================================================================== */

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

let editor = null;            // Monaco 实例
let currentAnalysis = {};     // 最近一次题目分析结果
let hintLevel = 0;            // 当前提示层级
let hintHistory = [];         // 已给提示文本
let chatHistory = [];         // 对话历史
let charts = {};              // Chart.js 实例缓存

/* 智能体定义：node 名 -> 卡片 */
const AGENTS = [
  { id: "retrieve", icon: "🔍", name: "题库检索官", role: "RAG 相似题检索" },
  { id: "analyze",  icon: "🧠", name: "题目分析师", role: "题型/难度/突破口" },
  { id: "plan",     icon: "🗺️", name: "策略规划师", role: "多解法 + 复杂度" },
  { id: "tutor",    icon: "🎓", name: "苏格拉底导师", role: "分层提示 / 答疑" },
  { id: "review",   icon: "🔬", name: "代码审查师", role: "bug 定位 + 优化" },
  { id: "test",     icon: "🧪", name: "测试生成师", role: "用例构造 + 判题" },
];
const NODE2AGENT = { retrieve:"retrieve", analyze:"analyze", plan:"plan",
                     review:"review", gen_tests:"test", run_tests:"test", summarize:null };

/* ---------------- 初始化 ---------------- */
function initAgentTeam() {
  $("#agent-team").innerHTML = AGENTS.map(a => `
    <div class="agent" id="agent-${a.id}">
      <div class="a-icon">${a.icon}</div>
      <div class="a-info"><div class="a-name">${a.name}</div><div class="a-role">${a.role}</div></div>
      <div class="a-state">待命</div>
    </div>`).join("");
}
function setAgent(id, state) {
  const el = $(`#agent-${id}`);
  if (!el) return;
  el.classList.remove("working", "done");
  const label = $(`#agent-${id} .a-state`);
  if (state === "working") { el.classList.add("working"); label.textContent = "工作中"; }
  else if (state === "done") { el.classList.add("done"); label.textContent = "完成 ✓"; }
  else { label.textContent = "待命"; }
}
function resetAgents(ids) { ids.forEach(id => setAgent(id, "idle")); }

/* Monaco */
require.config({ paths: { vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs" } });
require(["vs/editor/editor.main"], () => {
  // 自定义主题：暖深色「屏幕」，与浅色书桌形成对比，青绿语法点缀
  monaco.editor.defineTheme("arena", {
    base: "vs-dark", inherit: true,
    rules: [
      { token: "comment", foreground: "7d8a72", fontStyle: "italic" },
      { token: "keyword", foreground: "5fb3a1" },
      { token: "string", foreground: "d9b777" },
      { token: "number", foreground: "e0a96d" },
      { token: "function", foreground: "84b6d8" },
    ],
    colors: {
      "editor.background": "#211E18",
      "editor.foreground": "#E8E2D4",
      "editorLineNumber.foreground": "#5a554a",
      "editorLineNumber.activeForeground": "#5fb3a1",
      "editor.selectionBackground": "#1f6f6644",
      "editor.lineHighlightBackground": "#2a261f",
      "editorCursor.foreground": "#5fb3a1",
      "editorIndentGuide.background": "#322e26",
    },
  });
  editor = monaco.editor.create($("#editor"), {
    value: "import sys\n\ndef main():\n    data = sys.stdin.read().split()\n    # 在此编写你的解法\n    print()\n\nmain()\n",
    language: "python", theme: "arena", fontSize: 14, minimap: { enabled: false },
    fontFamily: "JetBrains Mono, Consolas, monospace",
    automaticLayout: true, scrollBeyondLastLine: false, padding: { top: 12 },
  });
});

/* ---------------- SSE 流式工具 ---------------- */
async function sseStream(url, body, onEvent) {
  const resp = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, idx); buf = buf.slice(idx + 2);
      const line = block.split("\n").find(l => l.startsWith("data:"));
      if (line) { try { onEvent(JSON.parse(line.slice(5).trim())); } catch (e) {} }
    }
  }
}

/* ---------------- 题目分析流 ---------------- */
async function runAnalyze() {
  const problem = $("#problem-input").value.trim();
  if (!problem) return toast("请先输入题目");
  const btn = $("#btn-analyze");
  btn.disabled = true; btn.textContent = "🧠 智能体分析中…";
  $("#analysis-result").classList.add("hidden");
  $("#strategies").classList.add("hidden");
  resetAgents(["retrieve", "analyze", "plan"]);
  setAgent("retrieve", "working");
  hintLevel = 0; hintHistory = []; $("#hint-level-num").textContent = "0"; $("#hint-box").innerHTML = "";

  const order = ["retrieve", "analyze", "plan"];
  try {
    await sseStream("/api/analyze", { problem }, (ev) => {
      if (ev.event === "node") {
        const aid = NODE2AGENT[ev.node];
        if (aid) setAgent(aid, "done");
        const next = order[order.indexOf(ev.node) + 1];
        if (next) setAgent(NODE2AGENT[next], "working");
        if (ev.node === "retrieve") renderSimilar(ev.data.similar);
        if (ev.node === "analyze") renderAnalysis(ev.data.analysis);
        if (ev.node === "plan") renderStrategies(ev.data.strategies);
      } else if (ev.event === "error") { toast("分析出错：" + ev.message); }
    });
    toast("✅ 分析完成，可以开始解题了");
  } catch (e) { toast("请求失败：" + e.message); }
  finally { btn.disabled = false; btn.textContent = "🚀 启动智能体分析"; }
}

function renderAnalysis(a) {
  currentAnalysis = a || {};
  $("#analysis-result").classList.remove("hidden");
  $("#ana-type").textContent = a.type || "—";
  $("#ana-diff").textContent = a.difficulty || "—";
  const score = a.difficulty_score || 0;
  $("#ana-stars").textContent = "★".repeat(Math.round(score / 2)) + "☆".repeat(5 - Math.round(score / 2));
  $("#ana-complexity").textContent = a.target_complexity || "—";
  $("#ana-insight").textContent = a.key_insight || "—";
  $("#ana-pitfalls").innerHTML = (a.pitfalls || []).map(p => `<li>${esc(p)}</li>`).join("") || "<li>—</li>";
  $("#ana-knowledge").innerHTML = (a.knowledge_points || []).map(k => `<span class="chip">${esc(k)}</span>`).join("");
}
function renderSimilar(list) {
  $("#ana-similar").innerHTML = (list || []).map(s =>
    `<span class="chip clickable" data-pid="${s.id}">${esc(s.title)} · ${esc(s.type)}</span>`).join("") || "<span class='chip'>无</span>";
  $$("#ana-similar .chip.clickable").forEach(c =>
    c.onclick = () => loadProblem(c.dataset.pid));
}
function renderStrategies(s) {
  if (!s || !s.strategies) return;
  $("#strategies").classList.remove("hidden");
  $("#strategy-list").innerHTML = s.strategies.map(st => {
    const rec = (st.name === s.recommended) ? `<span class="recommend-tag">推荐</span>` : "";
    const stars = "★".repeat(st.rating || 0);
    return `<div class="strategy">
      <div class="strategy-head"><span class="strategy-name">${esc(st.name)} ${rec}</span>
        <span class="strategy-rating">${stars}</span></div>
      <div class="strategy-idea">${esc(st.idea || "")}</div>
      <div class="strategy-meta">
        <span class="cx">⏱ ${esc(st.time || "?")}</span>
        <span class="cx space">💾 ${esc(st.space || "?")}</span>
        ${st.when_to_use ? `<span class="cx" style="color:var(--ink-dim)">${esc(st.when_to_use)}</span>` : ""}
      </div></div>`;
  }).join("");
  $("#strategy-path").textContent = s.learning_path ? "📈 学习路径：" + s.learning_path : "";
}

/* ---------------- 运行代码（自定义输入） ---------------- */
async function runCode() {
  if (!editor) return;
  const code = editor.getValue();
  const stdin = $("#custom-input").value;
  $("#run-output").textContent = "运行中…";
  switchIO("custom");
  try {
    const r = await fetch("/api/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, stdin }),
    }).then(r => r.json());
    if (r.status === "OK") $("#run-output").textContent = r.stdout || "(无输出)";
    else $("#run-output").textContent = `[${r.status}] ${r.stderr || ""}\n${r.stdout || ""}`;
  } catch (e) { $("#run-output").textContent = "运行失败：" + e.message; }
}

/* ---------------- 提交评测流 ---------------- */
async function submitCode() {
  if (!editor) return;
  const code = editor.getValue();
  const problem = $("#problem-input").value.trim();
  if (!problem) return toast("请先输入题目并分析");
  const btn = $("#btn-submit");
  btn.disabled = true; btn.textContent = "⚙️ 评测中…";
  switchIO("result");
  $("#verdict-bar").classList.add("hidden");
  $("#test-results").innerHTML = "<div class='empty-hint'>智能体评测进行中…</div>";
  resetAgents(["review", "test"]);
  setAgent("review", "working");

  try {
    await sseStream("/api/evaluate", {
      problem, code, language: $("#lang-select").value,
      problem_title: currentAnalysis.title || "未命名",
      problem_type: currentAnalysis.type || "其他",
      difficulty: currentAnalysis.difficulty || "未知",
    }, (ev) => {
      if (ev.event === "node") {
        if (ev.node === "review") { setAgent("review", "done"); setAgent("test", "working"); renderReview(ev.data.review); }
        if (ev.node === "run_tests") renderTests(ev.data.judge);
        if (ev.node === "summarize") { setAgent("test", "done"); renderVerdict(ev.data.summary); }
      } else if (ev.event === "error") { toast("评测出错：" + ev.message); }
    });
    toast("✅ 评测完成");
  } catch (e) { toast("评测失败：" + e.message); }
  finally { btn.disabled = false; btn.textContent = "✅ 提交评测"; }
}

let reviewData = null;
function renderReview(r) { reviewData = r; }
function renderTests(judge) {
  const results = (judge && judge.results) || [];
  $("#test-results").innerHTML = results.map(t => `
    <div class="test-case">
      <div class="tc-head" onclick="this.nextElementSibling.classList.toggle('open')">
        <span class="tc-status ${t.status}">${t.status}</span>
        <span class="tc-name">${esc(t.name)}</span>
        <span class="tc-cat">${esc(t.category || "")}</span>
      </div>
      <div class="tc-detail">
        ${t.note ? `<div style="color:var(--ink-mute);margin-bottom:4px">${esc(t.note)}</div>` : ""}
        <div class="io-row"><label>输入</label><pre>${esc(t.input || "(空)")}</pre></div>
        <div class="io-row"><label>期望输出</label><pre>${esc(t.expected || "(未提供)")}</pre></div>
        <div class="io-row"><label>实际输出</label><pre>${esc(t.actual || "(空)")}</pre></div>
        ${t.stderr ? `<div class="io-row"><label>错误信息</label><pre style="color:var(--bad)">${esc(t.stderr)}</pre></div>` : ""}
      </div>
    </div>`).join("");
}
function renderVerdict(s) {
  if (!s) return;
  const bar = $("#verdict-bar");
  bar.classList.remove("hidden", "pass", "partial", "fail");
  const pass = s.passed === s.total && s.total > 0;
  bar.classList.add(pass ? "pass" : (s.passed > 0 ? "partial" : "fail"));
  if (s.total === 0 && reviewData && reviewData.syntax_ok === false)
    $("#test-results").innerHTML = "<div class='empty-hint'>代码存在语法错误，已跳过测试。请先修复后再提交。</div>";
  let extra = "";
  if (reviewData) extra = ` · 静态审查 ${reviewData.score}分 · ${reviewData.bugs.length} 个问题`;
  bar.innerHTML = `<span>${pass ? "🎉" : "🔧"} ${esc(s.verdict)}（${s.passed}/${s.total} 用例）${extra}</span>
                   <span>综合得分 ${s.final_score}</span>`;
  // 把审查师的建议推给导师区
  if (reviewData && reviewData.next_step) {
    addHintEntry("审查师建议", reviewData.next_step + (reviewData.bugs.length ?
      "\n\n主要问题：" + reviewData.bugs.map(b => `[${b.severity}] ${b.issue}`).join("；") : ""));
  }
}

/* ---------------- 苏格拉底提示流 ---------------- */
async function requestHint() {
  const problem = $("#problem-input").value.trim();
  if (!problem) return toast("请先输入题目");
  if (hintLevel >= 4) return toast("已到最深提示层级");
  hintLevel++;
  $("#hint-level-num").textContent = hintLevel;
  setAgent("tutor", "working");
  const entry = addHintEntry("第 " + hintLevel + " 层提示", "");
  const body = entry.querySelector(".hint-text");
  let acc = "";
  body.classList.add("cursor-blink");
  try {
    await sseStream("/api/hint", {
      problem, analysis: currentAnalysis, question: "",
      hint_level: hintLevel, history: hintHistory.join("\n---\n"),
    }, (ev) => {
      if (ev.event === "token") { acc += ev.text; body.innerHTML = marked.parse(acc); }
    });
    hintHistory.push(acc);
  } catch (e) { toast("提示获取失败"); }
  finally { body.classList.remove("cursor-blink"); setAgent("tutor", "done"); }
}
function addHintEntry(label, text) {
  const div = document.createElement("div");
  div.className = "hint-entry";
  div.innerHTML = `<div class="lvl">${esc(label)}</div><div class="hint-text">${text ? marked.parse(text) : ""}</div>`;
  $("#hint-box").appendChild(div);
  div.scrollIntoView({ behavior: "smooth", block: "nearest" });
  return div;
}

/* ---------------- 自由对话流 ---------------- */
async function sendChat() {
  const q = $("#chat-input").value.trim();
  if (!q) return;
  $("#chat-input").value = "";
  addMsg("user", q);
  setAgent("tutor", "working");
  const aMsg = addMsg("assistant", "");
  let acc = "";
  aMsg.classList.add("cursor-blink");
  try {
    await sseStream("/api/chat", {
      problem: $("#problem-input").value.trim(), question: q, history: chatHistory,
    }, (ev) => {
      if (ev.event === "token") { acc += ev.text; aMsg.innerHTML = marked.parse(acc);
        $("#chat-log").scrollTop = $("#chat-log").scrollHeight; }
    });
    chatHistory.push({ role: "user", content: q }, { role: "assistant", content: acc });
  } catch (e) { aMsg.textContent = "回复失败"; }
  finally { aMsg.classList.remove("cursor-blink"); setAgent("tutor", "done"); }
}
function addMsg(role, text) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  div.innerHTML = text ? (role === "assistant" ? marked.parse(text) : esc(text)) : "";
  $("#chat-log").appendChild(div);
  $("#chat-log").scrollTop = $("#chat-log").scrollHeight;
  return div;
}

/* ---------------- 题库 ---------------- */
async function loadProblemList() {
  const list = await fetch("/api/problems").then(r => r.json());
  $("#problem-select").innerHTML = '<option value="">— 从题库选择 —</option>' +
    list.map(p => `<option value="${p.id}">${p.title}（${p.difficulty}·${p.type}）</option>`).join("");
}
async function loadProblem(pid) {
  if (!pid) return;
  const p = await fetch("/api/problems/" + pid).then(r => r.json());
  if (!p || p.error) return;
  let text = p.description;
  if (p.sample_input) text += `\n\n样例输入：\n${p.sample_input}\n\n样例输出：\n${p.sample_output}`;
  $("#problem-input").value = text;
  $("#problem-select").value = pid;
  toast("已载入：" + p.title);
}

/* ---------------- 仪表盘 ---------------- */
async function loadDashboard() {
  const s = await fetch("/api/stats").then(r => r.json());
  $("#st-total").textContent = s.total;
  $("#st-solved").textContent = s.solved;
  $("#st-rate").textContent = s.solve_rate + "%";
  $("#st-avg").textContent = s.avg_score;

  // 雷达图：题型掌握度
  const rLabels = s.type_mastery.map(m => m.type);
  const rData = s.type_mastery.map(m => m.rate);
  drawChart("radar", "chart-radar", {
    type: "radar",
    data: { labels: rLabels.length ? rLabels : ["暂无数据"],
      datasets: [{ label: "掌握度 %", data: rData.length ? rData : [0],
        backgroundColor: "rgba(31,111,102,.16)", borderColor: "#1F6F66",
        borderWidth: 2, pointBackgroundColor: "#1F6F66", pointBorderColor: "#FBF7EF" }] },
    options: radarOpts(),
  });
  // 判题结果分布
  const errColors = { AC: "#3C8B57", WA: "#BF4A30", TLE: "#C2922E", RE: "#7C5BC0", CE: "#7C5BC0", RUN: "#3A6EA5" };
  const eLabels = Object.keys(s.error_dist);
  drawChart("error", "chart-error", {
    type: "doughnut",
    data: { labels: eLabels.length ? eLabels : ["暂无数据"],
      datasets: [{ data: eLabels.length ? Object.values(s.error_dist) : [1],
        backgroundColor: eLabels.length ? eLabels.map(k => errColors[k] || "#1F6F66") : ["#E1D8C6"],
        borderColor: "#FBF7EF", borderWidth: 3 }] },
    options: { plugins: { legend: { labels: { color: "#6E6657", font: { family: "IBM Plex Sans" } } } } },
  });
  // 薄弱点
  $("#weak-list").innerHTML = s.weak_points.length ? s.weak_points.map(w => `
    <div class="weak-item"><span class="weak-name">${esc(w.type)}</span>
      <div class="weak-bar-wrap"><div class="weak-bar"><div class="weak-fill" style="width:${w.rate}%"></div></div>
      <span class="weak-pct">${w.rate}%</span></div></div>`).join("")
    : "<div class='empty-hint'>暂无薄弱点，继续加油！</div>";
  // 近期
  $("#recent-body").innerHTML = s.recent.length ? s.recent.map(r => `
    <tr><td>${esc(r.problem_title)}</td><td>${esc(r.problem_type)}</td>
    <td><span class="res-pill ${r.error_kind}">${r.error_kind}</span></td><td>${r.score}</td></tr>`).join("")
    : "<tr><td colspan='4' class='empty-hint'>还没有提交记录</td></tr>";
}
function radarOpts() {
  return { scales: { r: { angleLines: { color: "rgba(110,102,87,.18)" },
    grid: { color: "rgba(110,102,87,.18)" },
    pointLabels: { color: "#6E6657", font: { size: 12, family: "IBM Plex Sans" } },
    ticks: { color: "#9C9484", backdropColor: "transparent", stepSize: 25 }, min: 0, max: 100 } },
    plugins: { legend: { labels: { color: "#6E6657", font: { family: "IBM Plex Sans" } } } } };
}
function drawChart(key, canvasId, cfg) {
  if (charts[key]) charts[key].destroy();
  charts[key] = new Chart($("#" + canvasId), cfg);
}

/* ---------------- 通用 ---------------- */
function esc(s) { return String(s == null ? "" : s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function switchIO(which) {
  $$(".io-tab").forEach(t => t.classList.toggle("active", t.dataset.io === which));
  $$(".io-pane").forEach(p => p.classList.toggle("active", p.id === "io-" + which));
}
let toastTimer;
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
}

/* ---------------- 事件绑定 ---------------- */
function bind() {
  $("#btn-analyze").onclick = runAnalyze;
  $("#btn-run").onclick = runCode;
  $("#btn-submit").onclick = submitCode;
  $("#btn-hint").onclick = requestHint;
  $("#btn-chat").onclick = sendChat;
  $("#chat-input").onkeydown = (e) => { if (e.key === "Enter") sendChat(); };
  $("#problem-select").onchange = (e) => loadProblem(e.target.value);
  $$(".io-tab").forEach(t => t.onclick = () => switchIO(t.dataset.io));
  $$(".tab").forEach(t => t.onclick = () => {
    $$(".tab").forEach(x => x.classList.remove("active"));
    t.classList.add("active");
    $$(".view").forEach(v => v.classList.remove("active"));
    $("#view-" + t.dataset.view).classList.add("active");
    if (t.dataset.view === "dashboard") loadDashboard();
  });
}

/* ---------------- 启动 ---------------- */
initAgentTeam();
bind();
loadProblemList();
