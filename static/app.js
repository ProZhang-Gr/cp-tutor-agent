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
let pendingSelection = "";     // 当前引用的选中代码片段
let pendingSimilar = [];       // 检索到的相似题（待确认是有效题目后再渲染）
let analysisStale = true;      // 当前题目是否尚未分析 / 分析已过期
let currentProblemId = "";     // 当前题目在题单中的 id（题库 P..../ 自建 U....），空=未入库的新题

// 已明确判定「当前题面不是算法题」（且分析未过期）
function isKnownNonProblem() {
  return !analysisStale && currentAnalysis.is_problem === false;
}
function nonProblemHint() {
  toast("这不是一道算法题～点题目下方「💬 让导师解答」，或直接在右下角问导师");
}
function resetAnalysisState() {
  currentAnalysis = {}; analysisStale = true;
  $("#analysis-result").classList.add("hidden");
  $("#strategies").classList.add("hidden");
  hintLevel = 0; hintHistory = [];
  $("#hint-level-num").textContent = "0"; $("#hint-box").innerHTML = "";
}

/* 智能体定义：node 名 -> 卡片 */
const AGENTS = [
  { id: "retrieve", icon: "🔍", name: "题库检索官", role: "RAG 相似题检索" },
  { id: "analyze",  icon: "🧠", name: "题目分析师", role: "题型/难度/突破口" },
  { id: "plan",     icon: "🗺️", name: "策略规划师", role: "多解法 + 复杂度" },
  { id: "tutor",    icon: "🎓", name: "苏格拉底导师", role: "分层提示 / 答疑" },
  { id: "review",   icon: "🔬", name: "代码审查师", role: "bug 定位 + 优化" },
  { id: "test",     icon: "⚖️", name: "判题官", role: "真值判定 / 差分对拍" },
  { id: "debug",    icon: "🛠️", name: "调试工程师", role: "ReAct 实验定位 bug" },
];
const NODE2AGENT = { retrieve:"retrieve", analyze:"analyze", plan:"plan",
                     review:"review", judge:"test", summarize:null };

/* ---------------- 初始化 ---------------- */
function initAgentTeam() {
  $("#agent-team").innerHTML = AGENTS.map(a => `
    <div class="agent" id="agent-${a.id}">
      <div class="a-icon">${a.icon}</div>
      <div class="a-info"><div class="a-name">${a.name}</div><div class="a-role">${a.role}</div></div>
      <div class="a-state">待命</div>
    </div>`).join("");
  $("#team-dots").innerHTML = AGENTS.map(a =>
    `<span class="team-dot" id="dot-${a.id}" title="${a.name}">${a.icon}</span>`).join("");
}
function setAgent(id, state) {
  const el = $(`#agent-${id}`);
  if (el) {
    el.classList.remove("working", "done");
    const label = $(`#agent-${id} .a-state`);
    if (state === "working") { el.classList.add("working"); label.textContent = "工作中"; }
    else if (state === "done") { el.classList.add("done"); label.textContent = "完成 ✓"; }
    else { label.textContent = "待命"; }
  }
  const dot = $(`#dot-${id}`);
  if (dot) {
    dot.classList.remove("working", "done");
    if (state === "working" || state === "done") dot.classList.add(state);
  }
  // 工作时自动展开秀协作（导师对话不打扰），结束后自动收起
  if (state === "working" && id !== "tutor") openTeam();
  if (state === "done") scheduleTeamAutoClose();
}
function resetAgents(ids) { ids.forEach(id => setAgent(id, "idle")); }

/* ---- 智能体面板：迷你条 / 展开 ---- */
let teamPinned = false, teamCloseTimer = null;
function setTeamOpenClass(open) { $("#team").classList.toggle("open", open); }
function openTeam() { clearTimeout(teamCloseTimer); setTeamOpenClass(true); }
function scheduleTeamAutoClose() {
  if (teamPinned) return;                       // 用户钉住则不自动收
  clearTimeout(teamCloseTimer);
  teamCloseTimer = setTimeout(() => {
    const busy = AGENTS.some(a => {
      const e = $(`#agent-${a.id}`); return e && e.classList.contains("working");
    });
    if (!busy) setTeamOpenClass(false);
  }, 2500);
}
function toggleTeam() {
  teamPinned = !$("#team").classList.contains("open");
  localStorage.setItem("cp_team_open", teamPinned ? "1" : "0");
  clearTimeout(teamCloseTimer);
  setTeamOpenClass(teamPinned);
}

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
  // 恢复上次代码
  const savedCode = localStorage.getItem("cp_code");
  if (savedCode) editor.setValue(savedCode);
  // 自动保存（防抖）
  let codeTimer;
  editor.onDidChangeModelContent(() => {
    clearTimeout(codeTimer);
    codeTimer = setTimeout(() => localStorage.setItem("cp_code", editor.getValue()), 500);
  });
  // 编辑器内快捷键
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => runCode());
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => submitCode());
  // 右键菜单：框选代码后「问导师这段」
  editor.addAction({
    id: "ask-tutor-selection",
    label: "💬 问导师这段代码",
    contextMenuGroupId: "navigation",
    contextMenuOrder: 1,
    run: () => captureSelection(),
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

  try {
    const deep = $("#deep-check") && $("#deep-check").checked && currentBilling.is_pro;
    await sseStream("/api/analyze", { problem, deep }, (ev) => {
      if (ev.event !== "node") { if (ev.event === "error") toast("分析出错：" + ev.message); return; }
      const aid = NODE2AGENT[ev.node];
      if (aid) setAgent(aid, "done");
      if (ev.node === "retrieve") {
        pendingSimilar = ev.data.similar || [];
        setAgent("analyze", "working");
      } else if (ev.node === "analyze") {
        // 先判断是不是有效题目：是 → 继续渲染并规划；不是 → 提示去问导师
        if (renderAnalysis(ev.data.analysis)) {
          renderSimilar(pendingSimilar);
          setAgent("plan", "working");
        }
      } else if (ev.node === "plan") {
        renderStrategies(ev.data.strategies);
      }
    });
    // 有效新题 → 用分析师起的标题自动命名、纳入「我的题目」
    if (currentAnalysis.is_problem !== false && !currentProblemId) {
      try {
        const r = await fetch("/api/save-problem", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: currentAnalysis.title || "未命名题目",
            type: currentAnalysis.type || "其他",
            difficulty: currentAnalysis.difficulty || "未知",
            description: problem,
          }),
        }).then(r => r.json());
        if (r.id) {
          currentProblemId = r.id;
          await loadProblemList();
          $("#problem-select").value = r.id;
          toast("📌 已加入「我的题目」：" + (currentAnalysis.title || ""));
        }
      } catch (e) {}
    } else {
      toast(currentAnalysis.is_problem === false ? "这看起来不是一道算法题" : "✅ 分析完成");
    }
  } catch (e) { toast("请求失败：" + e.message); }
  finally { btn.disabled = false; btn.textContent = "🚀 启动智能体分析"; }
}

function renderAnalysis(a) {
  currentAnalysis = a || {};
  analysisStale = false;      // 刚对当前题面做完分析
  $("#analysis-result").classList.remove("hidden");
  // 非有效题目：只给友好提示 + 转交导师的入口
  if (a && a.is_problem === false) {
    $("#analysis-notice-text").textContent = a.message ||
      "这看起来不像一道完整的算法题。你可以粘贴含输入/输出与样例的题面再分析，或点下方让导师直接解答～";
    $("#analysis-notice").classList.remove("hidden");
    $("#analysis-body").classList.add("hidden");
    $("#strategies").classList.add("hidden");
    return false;
  }
  $("#analysis-notice").classList.add("hidden");
  $("#analysis-body").classList.remove("hidden");
  $("#ana-type").textContent = a.type || "—";
  $("#ana-diff").textContent = a.difficulty || "—";
  const score = a.difficulty_score || 0;
  $("#ana-stars").textContent = "★".repeat(Math.round(score / 2)) + "☆".repeat(5 - Math.round(score / 2));
  $("#ana-complexity").textContent = a.target_complexity || "—";
  $("#ana-insight").textContent = a.key_insight || "—";
  if (a.deep_dive) { $("#ana-deepdive").textContent = a.deep_dive; $("#ana-deepdive-wrap").classList.remove("hidden"); }
  else $("#ana-deepdive-wrap").classList.add("hidden");
  $("#ana-pitfalls").innerHTML = (a.pitfalls || []).map(p => `<li>${esc(p)}</li>`).join("") || "<li>—</li>";
  $("#ana-knowledge").innerHTML = (a.knowledge_points || []).map(k => `<span class="chip">${esc(k)}</span>`).join("");
  return true;
}
function askTutorAbout() {
  const text = $("#problem-input").value.trim();
  if (!text) return;
  if ($("#workspace").classList.contains("right-collapsed")) setCollapsed("right", false);
  $("#chat-input").value = text;
  sendChat();
  $("#chat-log").scrollIntoView({ behavior: "smooth", block: "center" });
  toast("已转交导师解答");
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
  if (isKnownNonProblem()) return nonProblemHint();
  if (!code.trim()) return toast("请先在编辑器里写代码");
  const btn = $("#btn-submit");
  btn.disabled = true; btn.textContent = "⚙️ 评测中…";
  switchIO("result");
  $("#verdict-bar").classList.add("hidden");
  $("#test-results").innerHTML = "<div class='empty-hint'>智能体评测进行中…</div>";
  resetAgents(["review", "test", "debug"]);
  setAgent("review", "working");
  lastEval.problem = problem; lastEval.code = code; lastEval.counter = null;

  try {
    const meta = analysisStale ? {} : currentAnalysis;   // 题面改过则不沿用旧分析的标签
    await sseStream("/api/evaluate", {
      problem, code, language: $("#lang-select").value,
      problem_id: currentProblemId,
      problem_title: meta.title || "未命名",
      problem_type: meta.type || "其他",
      difficulty: meta.difficulty || "未知",
    }, (ev) => {
      if (ev.event === "node") {
        if (ev.node === "review") { setAgent("review", "done"); setAgent("test", "working"); renderReview(ev.data.review); }
        if (ev.node === "judge") renderTests(ev.data.judge);
        if (ev.node === "summarize") { setAgent("test", "done"); renderVerdict(ev.data.summary); }
      } else if (ev.event === "error") { toast("评测出错：" + ev.message); }
    });
    toast("✅ 评测完成");
  } catch (e) { toast("评测失败：" + e.message); }
  finally { btn.disabled = false; btn.textContent = "✅ 提交评测"; }
}

let reviewData = null;
let lastEval = { problem: "", code: "", counter: null };
function renderReview(r) { reviewData = r; }
function renderTests(judge) {
  if (!judge) return;
  lastEval.counter = judge.counter = judge.counterexample || null;
  const mode = judge.mode;
  const modeLabel = mode === "truth"
    ? `🟢 真值判定 · 官方测试数据 ${judge.passed}/${judge.total} 通过`
    : `🟡 差分对拍 · 暴力解当真值${judge.stress ? "（" + esc(judge.stress.note) + "）" : ""}`;

  // 最小反例 + 调试入口（最重要，放最上面）
  let counterHtml = "";
  const ce = judge.counterexample;
  if (ce) {
    counterHtml = `
      <div class="counter-box">
        <div class="counter-head">⚠️ 最小反例 · ${esc(ce.reason || "WA")}</div>
        <div class="io-row"><label>输入</label><pre>${esc(ce.input || "(空)")}</pre></div>
        <div class="io-row"><label>正确答案</label><pre>${esc(ce.expected || "")}</pre></div>
        <div class="io-row"><label>你的输出</label><pre>${esc(ce.actual || "(空)")}</pre></div>
        <button id="btn-debug" class="btn btn-accent btn-block" onclick="startDebug()">🛠️ 让调试 agent 帮我定位</button>
        <div id="debug-panel" class="debug-panel"></div>
      </div>`;
  }

  const cases = (judge.results || []).map((t, i) => `
    <div class="test-case">
      <div class="tc-head" onclick="this.nextElementSibling.classList.toggle('open')">
        <span class="tc-status ${t.status}">${t.status}</span>
        <span class="tc-name">用例 ${(t.index != null ? t.index : i) + 1}</span>
        <span class="tc-cat">${esc(t.kind || "")}</span>
      </div>
      <div class="tc-detail">
        <div class="io-row"><label>输入</label><pre>${esc(t.input || "(空)")}</pre></div>
        <div class="io-row"><label>期望输出</label><pre>${esc(t.expected || "(未提供)")}</pre></div>
        <div class="io-row"><label>实际输出</label><pre>${esc(t.actual || "(空)")}</pre></div>
      </div>
    </div>`).join("");

  $("#test-results").innerHTML =
    `<div class="judge-mode ${mode}">${modeLabel}</div>` + counterHtml +
    (cases ? `<div class="cases-wrap">${cases}</div>` : "");
}

/* ---------------- Agentic 调试回路 ---------------- */
async function startDebug() {
  const ce = lastEval.counter;
  if (!ce) return toast("没有可用于调试的反例");
  const panel = $("#debug-panel");
  if (!panel) return;
  panel.innerHTML = "";
  const btn = $("#btn-debug");
  if (btn) { btn.disabled = true; btn.textContent = "🛠️ 调试 agent 工作中…"; }
  setAgent("debug", "working");
  let stepEl = null;
  try {
    await sseStream("/api/debug",
      { problem: lastEval.problem, code: lastEval.code, counterexample: ce },
      (ev) => {
        const d = ev.data || {};
        if (ev.event === "thought") {
          stepEl = document.createElement("div");
          stepEl.className = "dbg-step";
          stepEl.innerHTML = `<div class="dbg-thought"><b>💭 第 ${d.step} 步思考</b><div>${esc(d.text)}</div></div>`;
          panel.appendChild(stepEl);
        } else if (ev.event === "action") {
          const a = document.createElement("div");
          a.className = "dbg-action";
          a.innerHTML = `<div class="dbg-label">🔧 运行探针（stdin: ${esc((d.stdin || "").slice(0, 36))}）</div><pre>${esc(d.code || "")}</pre>`;
          (stepEl || panel).appendChild(a);
        } else if (ev.event === "observation") {
          const o = document.createElement("div");
          o.className = "dbg-obs";
          o.innerHTML = `<div class="dbg-label">👁 观察 · ${esc(d.status)}</div><pre>${esc(d.stdout || d.stderr || "(空)")}</pre>`;
          (stepEl || panel).appendChild(o);
        } else if (ev.event === "conclusion") {
          const c = document.createElement("div");
          c.className = "dbg-conclusion";
          c.innerHTML = `<div class="dbg-label">✅ 定位结论</div>
            <div><b>根因：</b>${esc(d.root_cause || "")}</div>
            ${d.evidence ? `<div><b>证据：</b>${esc(d.evidence)}</div>` : ""}
            ${d.fix_hint ? `<div class="dbg-fix"><b>修复方向：</b>${esc(d.fix_hint)}</div>` : ""}`;
          panel.appendChild(c);
        } else if (ev.event === "error") { toast("调试出错：" + ev.message); }
        panel.scrollTop = panel.scrollHeight;
      });
  } catch (e) { toast("调试失败：" + e.message); }
  finally {
    setAgent("debug", "done");
    if (btn) { btn.disabled = false; btn.textContent = "🛠️ 再调试一次"; }
  }
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
  if (pass && currentProblemId) { toast("🎉 已通过，已在题单标记"); loadProblemList(); }
}

/* ---------------- 苏格拉底提示流 ---------------- */
async function requestHint() {
  const problem = $("#problem-input").value.trim();
  if (!problem) return toast("请先输入题目");
  if (isKnownNonProblem()) return nonProblemHint();
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
      problem, analysis: analysisStale ? {} : currentAnalysis, question: "",
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
  const sel = pendingSelection;
  addMsg("user", q + (sel ? "  〔已引用选中代码 " + sel.split("\n").length + " 行〕" : ""));
  clearQuote();
  setAgent("tutor", "working");
  const aMsg = addMsg("assistant", "");
  let acc = "";
  aMsg.classList.add("cursor-blink");
  try {
    await sseStream("/api/chat", {
      problem: $("#problem-input").value.trim(), question: q, history: chatHistory,
      code: editor ? editor.getValue() : "", selection: sel,
    }, (ev) => {
      if (ev.event === "token") { acc += ev.text; aMsg.innerHTML = marked.parse(acc);
        $("#chat-log").scrollTop = $("#chat-log").scrollHeight; }
    });
    chatHistory.push({ role: "user", content: q }, { role: "assistant", content: acc });
  } catch (e) { aMsg.textContent = "回复失败"; }
  finally { aMsg.classList.remove("cursor-blink"); setAgent("tutor", "done"); }
}
function captureSelection() {
  if (!editor) return;
  const sel = editor.getModel().getValueInRange(editor.getSelection());
  if (!sel || !sel.trim()) { toast("请先在编辑器里选中一段代码"); return; }
  pendingSelection = sel;
  $("#quote-lines").textContent = sel.split("\n").length;
  $("#quote-chip").classList.remove("hidden");
  $("#chat-input").focus();
}
function clearQuote() {
  pendingSelection = "";
  $("#quote-chip").classList.add("hidden");
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
  const [bank, mine, solvedResp] = await Promise.all([
    fetch("/api/problems").then(r => r.json()),
    fetch("/api/my-problems").then(r => r.json()).catch(() => []),
    fetch("/api/solved").then(r => r.json()).catch(() => ({ solved: [] })),
  ]);
  const solved = new Set(solvedResp.solved || []);
  const opt = (p) => {
    const ok = solved.has(p.id) ? "✓ " : "";
    return `<option value="${p.id}">${ok}${esc(p.title)}（${esc(p.difficulty)}·${esc(p.type)}）</option>`;
  };
  let html = '<option value="">— 从题库选择 —</option>';
  html += `<optgroup label="题库">${bank.map(opt).join("")}</optgroup>`;
  if (mine && mine.length)
    html += `<optgroup label="我的题目">${mine.map(opt).join("")}</optgroup>`;
  const cur = $("#problem-select").value;
  $("#problem-select").innerHTML = html;
  if (cur) $("#problem-select").value = cur;     // 刷新后保留当前选择
}
async function loadProblem(pid) {
  if (!pid) return;
  const p = await fetch("/api/problems/" + pid).then(r => r.json());
  if (!p || p.error) return;
  let text = p.description;
  if (p.sample_input) text += `\n\n样例输入：\n${p.sample_input}\n\n样例输出：\n${p.sample_output}`;
  $("#problem-input").value = text;
  localStorage.setItem("cp_problem", text);
  resetAnalysisState();          // 换题 → 旧分析/提示作废
  currentProblemId = pid;        // 记住当前题目 id（用于 AC 标记）
  $("#problem-select").value = pid;
  toast("已载入：" + p.title);
}

/* ---------------- 每日报告（Pro） ---------------- */
let lastReport = null;
async function genReport() {
  const btn = $("#btn-gen-report"); btn.disabled = true; btn.textContent = "生成中…";
  try {
    const r = await fetch("/api/daily-report");
    const data = await r.json();
    if (!r.ok) { $("#report-body").innerHTML = `<span class="empty-hint">${esc(data.error || "生成失败")}</span>`; $("#btn-dl-report").classList.add("hidden"); return; }
    lastReport = data;
    const st = data.stats || {};
    $("#report-body").innerHTML =
      `<div class="r-stats">📅 ${esc(data.date)} ｜ 尝试 ${st.attempted} · 通过 ${st.ac} · AI互动 ${st.llm_calls} 次</div>` +
      `<div class="r-narr">${marked.parse(data.narrative || "")}</div>`;
    $("#btn-dl-report").classList.remove("hidden");
  } catch (e) { toast("生成失败"); }
  finally { btn.disabled = false; btn.textContent = "生成今日报告"; }
}
async function downloadReport() {
  if (!lastReport) return;
  try {
    const r = await fetch("/api/daily-report/pdf", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: lastReport.date, narrative: lastReport.narrative, stats: lastReport.stats }),
    });
    if (!r.ok) return toast("下载失败");
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "ARENA学习日报_" + lastReport.date + ".pdf";
    a.click(); URL.revokeObjectURL(url);
  } catch (e) { toast("下载失败"); }
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

function copyCode() {
  if (!editor) return;
  navigator.clipboard.writeText(editor.getValue())
    .then(() => toast("已复制代码")).catch(() => toast("复制失败"));
}

/* ---------------- 面板：折叠 / 拖宽 / 记忆 ---------------- */
const MIN_W = 220, MAX_W = 560;
function setCollapsed(side, on) {
  const ws = $("#workspace");
  ws.classList.toggle(side + "-collapsed", on);   // Flex 下 display:none 即可，中间自动占满
  localStorage.setItem(side === "left" ? "cp_lc" : "cp_rc", on ? "1" : "0");
  const btn = document.querySelector(`.col-toggle[data-side="${side}"]`);
  if (btn) btn.textContent = side === "left" ? (on ? "›" : "‹") : (on ? "‹" : "›");
}
function initPanels() {
  const ws = $("#workspace");
  const lw = localStorage.getItem("cp_lw"), rw = localStorage.getItem("cp_rw");
  if (lw) ws.style.setProperty("--left-w", lw + "px");
  if (rw) ws.style.setProperty("--right-w", rw + "px");
  if (localStorage.getItem("cp_lc") === "1") setCollapsed("left", true);
  if (localStorage.getItem("cp_rc") === "1") setCollapsed("right", true);

  $$(".col-toggle").forEach(btn => btn.addEventListener("click", (e) => {
    e.stopPropagation();
    const side = btn.dataset.side;
    setCollapsed(side, !ws.classList.contains(side + "-collapsed"));
  }));

  $$(".gutter").forEach(g => g.addEventListener("mousedown", (e) => {
    if (e.target.classList.contains("col-toggle")) return;     // 点按钮不拖
    const side = g.dataset.side;
    if (ws.classList.contains(side + "-collapsed")) return;    // 折叠时不拖
    e.preventDefault();
    document.body.classList.add("resizing");
    const rect = ws.getBoundingClientRect();
    const move = (ev) => {
      let w = side === "left" ? ev.clientX - rect.left - 18 : rect.right - ev.clientX - 18;
      w = Math.max(MIN_W, Math.min(MAX_W, w));
      ws.style.setProperty(side === "left" ? "--left-w" : "--right-w", w + "px");
      localStorage.setItem(side === "left" ? "cp_lw" : "cp_rw", Math.round(w));
    };
    const up = () => {
      document.body.classList.remove("resizing");
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }));
}

/* ---------------- 题目自动保存 ---------------- */
function initPersistence() {
  const inp = $("#problem-input");
  const saved = localStorage.getItem("cp_problem");
  if (saved) inp.value = saved;
  const savedH = localStorage.getItem("cp_problem_h");
  if (savedH) inp.style.height = savedH + "px";
  let t;
  inp.addEventListener("input", () => {
    analysisStale = true;        // 题面改了 → 之前的分析判定作废
    currentProblemId = "";       // 手动改题 → 视为新题（待分析后入库）
    clearTimeout(t); t = setTimeout(() => localStorage.setItem("cp_problem", inp.value), 400);
  });
  // 记忆题目框被拖拽后的高度
  if (window.ResizeObserver) {
    let ht;
    new ResizeObserver(() => {
      clearTimeout(ht);
      ht = setTimeout(() => localStorage.setItem("cp_problem_h", Math.round(inp.offsetHeight)), 300);
    }).observe(inp);
  }
}

/* ---------------- 事件绑定 ---------------- */
function bind() {
  $("#btn-analyze").onclick = runAnalyze;
  $("#btn-run").onclick = runCode;
  $("#btn-submit").onclick = submitCode;
  $("#btn-copy").onclick = copyCode;
  $("#btn-hint").onclick = requestHint;
  $("#btn-chat").onclick = sendChat;
  $("#btn-quote").onclick = captureSelection;
  $("#quote-clear").onclick = clearQuote;
  $("#team-strip").onclick = toggleTeam;
  $("#btn-ask-tutor").onclick = askTutorAbout;
  $("#btn-gen-report").onclick = genReport;
  $("#btn-dl-report").onclick = downloadReport;
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
  // 全局快捷键：Ctrl+S 提交（编辑器外也生效）
  window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); submitCode(); }
  });
}

/* ---------------- 认证 / 画像 ---------------- */
let currentUser = null, currentProfile = null, currentBilling = { credits: 0, is_pro: false }, authMode = "login";

async function loadMe() {
  try {
    const r = await fetch("/api/me").then(r => r.json());
    currentUser = r.user; currentProfile = r.profile; currentBilling = r.billing || currentBilling;
    renderAuthArea(); renderAdaptiveNote();
  } catch (e) {}
}
function renderAuthArea() {
  const a = $("#auth-area");
  if (currentUser) {
    const p = currentProfile || {}, b = currentBilling || {};
    const member = b.is_pro
      ? `<span class="pro-badge" title="算力点 ${b.credits}">PRO · ${b.credits}点</span>`
      : `<span class="credits-chip">${b.credits || 0} 点</span>`;
    a.innerHTML = `<span class="user-chip">
        <span class="user-name">${esc(currentUser.username)}</span>
        <span class="tier-badge ${p.tier || "novice"}" title="${esc(p.summary || "")}">${esc(p.tier_label || "新手")}</span>
        ${member}
      </span><button class="recharge-link" id="recharge-btn">充值</button><button class="logout-btn" id="logout-btn">退出</button>`;
    $("#logout-btn").onclick = logout;
    $("#recharge-btn").onclick = () => $("#recharge-modal").classList.remove("hidden");
  } else {
    a.innerHTML = `<button class="auth-btn ghost" data-open="login">登录</button>
                   <button class="auth-btn" data-open="register">注册</button>`;
    a.querySelectorAll("[data-open]").forEach(b => b.onclick = () => openAuth(b.dataset.open));
  }
}
function renderAdaptiveNote() {
  const n = $("#adaptive-note");
  if (currentUser && currentProfile && !currentProfile.is_empty) {
    n.classList.remove("hidden");
    n.innerHTML = `已按你的画像 <b>${esc(currentProfile.tier_label)}档</b> 因材施教` +
      (currentProfile.weak_types && currentProfile.weak_types.length
        ? `（薄弱：${esc(currentProfile.weak_types.join("、"))}）` : "");
  } else { n.classList.add("hidden"); }
}
function openAuth(mode) {
  authMode = mode;
  $("#auth-modal").classList.remove("hidden");
  $("#auth-err").textContent = "";
  $$(".modal-tab").forEach(t => t.classList.toggle("active", t.dataset.auth === mode));
  $("#auth-submit").textContent = mode === "login" ? "登录" : "注册";
  $("#auth-username").focus();
}
function closeAuth() { $("#auth-modal").classList.add("hidden"); }
async function submitAuth() {
  const username = $("#auth-username").value.trim(), password = $("#auth-password").value;
  if (!username || !password) { $("#auth-err").textContent = "请输入用户名和密码"; return; }
  const url = authMode === "login" ? "/api/login" : "/api/register";
  try {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }) });
    const data = await r.json();
    if (!r.ok) { $("#auth-err").textContent = data.error || "操作失败"; return; }
    closeAuth(); $("#auth-password").value = "";
    await loadMe();
    toast(authMode === "login" ? "已登录" : "注册成功，已登录");
    if ($("#view-dashboard").classList.contains("active")) loadDashboard();
  } catch (e) { $("#auth-err").textContent = "网络错误"; }
}
async function logout() {
  await fetch("/api/logout", { method: "POST" });
  await loadMe(); toast("已退出");
  if ($("#view-dashboard").classList.contains("active")) loadDashboard();
}
async function recharge(yuan) {
  try {
    const r = await fetch("/api/recharge", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ yuan }),
    }).then(r => r.json());
    if (r.error) return toast(r.error);
    $("#recharge-modal").classList.add("hidden");
    await loadMe();
    toast("✨ 充值成功，当前 " + r.credits + " 算力点，Pro 已开通");
  } catch (e) { toast("充值失败"); }
}
function bindAuth() {
  $("#auth-close").onclick = closeAuth;
  $("#auth-submit").onclick = submitAuth;
  $$("#auth-modal .modal-tab").forEach(t => t.onclick = () => openAuth(t.dataset.auth));
  $("#auth-modal").onclick = (e) => { if (e.target.id === "auth-modal") closeAuth(); };
  $("#auth-password").onkeydown = (e) => { if (e.key === "Enter") submitAuth(); };
  // 充值
  $("#recharge-close").onclick = () => $("#recharge-modal").classList.add("hidden");
  $("#recharge-modal").onclick = (e) => { if (e.target.id === "recharge-modal") $("#recharge-modal").classList.add("hidden"); };
  $$("#recharge-pkgs .pkg").forEach(b => b.onclick = () => recharge(parseInt(b.dataset.yuan)));
  // 深度分析仅 Pro
  $("#deep-check").onchange = (e) => {
    if (e.target.checked && !currentBilling.is_pro) {
      toast("深度分析是 Pro 功能，请先充值开通"); e.target.checked = false;
    }
  };
}

/* ---------------- 启动 ---------------- */
initAgentTeam();
teamPinned = localStorage.getItem("cp_team_open") === "1";
setTeamOpenClass(teamPinned);   // 默认收起为迷你状态条
bind();
bindAuth();
initPanels();
initPersistence();
loadProblemList();
loadMe();
